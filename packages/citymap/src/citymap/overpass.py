# Copyright (c) 2026 nm_health contributors
"""Fetch the raw OpenStreetMap data for a basemap from the Overpass API: one POST, polite retries, nothing personal.

The network is the boundary this package does not control, so this module is the one place that catches exceptions:
it retries rate limits and gateway timeouts with backoff, and turns every other failure into an OverpassError that
says what was being fetched.
"""

import json
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from citymap.bbox import BBox

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "citymap/0.1"
QUERY_TIMEOUT_S = 180  # the server-side [timeout:] Overpass may spend on the query
HTTP_TIMEOUT_S = 240.0  # how long we wait for the response; longer than the query timeout
MAX_ATTEMPTS = 4
FIRST_BACKOFF_S = 30.0
BACKOFF_FACTOR = 2.0
RETRYABLE_STATUS = frozenset({429, 504})  # rate limited, gateway timeout: both mean "try again later"
ERROR_PREVIEW_CHARS = 300


class OverpassError(RuntimeError):
    """Overpass could not be reached or did not return usable data."""


class _Readable(Protocol):
    def read(self) -> bytes: ...


class Opener(Protocol):
    """The slice of urllib.request.urlopen this module uses (tests pass a fake)."""

    def __call__(self, url: Request, *, timeout: float) -> AbstractContextManager[_Readable]:
        """Send the request and return the response, raising HTTPError or URLError on failure."""
        ...


def _quote(value: str) -> str:
    """An Overpass QL string literal (JSON escaping is a subset Overpass accepts)."""
    return json.dumps(value)


def build_query(box: BBox, highways: tuple[str, ...], boundary: str | None) -> str:
    """One Overpass QL query for the roads, river, water areas and (optionally) the named city boundary."""
    b = box.overpass()
    road_pattern = "^(" + "|".join(highways) + ")$"
    parts = [
        f"way[highway~{_quote(road_pattern)}]({b});",
        f'way[waterway="river"]({b});',
        f'way[natural="water"]({b});',
        f'relation[natural="water"]({b});',
    ]
    if boundary:
        parts.append(f'relation[boundary="administrative"][name={_quote(boundary)}]({b});')
    body = "\n  ".join(parts)
    return f"[out:json][timeout:{QUERY_TIMEOUT_S}];\n(\n  {body}\n);\nout geom;\n"


def _request(query: str) -> Request:
    data = urlencode({"data": query}).encode()
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    return Request(OVERPASS_URL, data=data, headers=headers, method="POST")


def _post_once(request: Request, opener: Opener, *, last_try: bool) -> bytes | None:
    """One POST. The body, or None when Overpass asked us to come back later and we still may."""
    try:
        with opener(request, timeout=HTTP_TIMEOUT_S) as response:
            return response.read()
    except HTTPError as err:
        if err.code in RETRYABLE_STATUS and not last_try:
            return None
        msg = f"Overpass at {OVERPASS_URL} answered HTTP {err.code} {err.reason}"
        raise OverpassError(msg) from err
    except (URLError, TimeoutError) as err:
        msg = f"could not reach Overpass at {OVERPASS_URL}: {err}"
        raise OverpassError(msg) from err


def _parse(body: bytes) -> dict[str, object]:
    """The decoded response, after checking it is Overpass JSON and not an HTML error page or a runtime error."""
    text = body.decode("utf-8")
    if not text.lstrip().startswith("{"):
        msg = f"Overpass did not return JSON: {text[:ERROR_PREVIEW_CHARS]!r}"
        raise OverpassError(msg)
    data = cast("dict[str, object]", json.loads(text))
    remark = str(data.get("remark", ""))
    if "error" in remark.lower():
        msg = f"Overpass reported a query error: {remark[:ERROR_PREVIEW_CHARS]}"
        raise OverpassError(msg)
    return data


def fetch(
    query: str,
    *,
    opener: Opener = urlopen,  # noqa: S310 - the only URL ever requested is the constant https OVERPASS_URL
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, object]:
    """Run one Overpass query, waiting FIRST_BACKOFF_S, then twice that, ... between retries of a 429 or 504."""
    request = _request(query)
    delay = FIRST_BACKOFF_S
    for attempt in range(1, MAX_ATTEMPTS + 1):
        body = _post_once(request, opener, last_try=attempt == MAX_ATTEMPTS)
        if body is not None:
            return _parse(body)
        sleep(delay)
        delay *= BACKOFF_FACTOR
    msg = "unreachable: the last attempt either returns or raises"
    raise AssertionError(msg)
