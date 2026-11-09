# Copyright (c) 2026 nm_health contributors
"""The Overpass query and the fetch loop, with a fake opener: no network."""

import io
from collections.abc import Iterator
from contextlib import contextmanager
from email.message import Message
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest

from citymap.bbox import BBox
from citymap.overpass import (
    BACKOFF_FACTOR,
    FIRST_BACKOFF_S,
    MAX_ATTEMPTS,
    OVERPASS_URL,
    USER_AGENT,
    OverpassError,
    build_query,
    fetch,
)

BOX = BBox.parse("34.94,-106.88,35.22,-106.47")
OK_BODY = b'{"elements": []}'
TOO_MANY_REQUESTS = 429
GATEWAY_TIMEOUT = 504
SERVER_ERROR = 500
STATEMENTS_WITH_BOUNDARY = 5  # roads, river, water ways, water relations, boundary


class FakeOpener:
    """Answers each call with the next scripted outcome: bytes to return, or an exception to raise."""

    def __init__(self, outcomes: list[bytes | Exception]) -> None:
        """Script the outcomes, in call order."""
        self.outcomes = outcomes
        self.requests: list[Request] = []

    @contextmanager
    def __call__(self, url: Request, *, timeout: float) -> Iterator[io.BytesIO]:
        """Record the request, then raise or yield the next outcome."""
        assert timeout > 0
        self.requests.append(url)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        yield io.BytesIO(outcome)


def _http_error(code: int) -> HTTPError:
    return HTTPError(OVERPASS_URL, code, "scripted", Message(), None)


def test_query_asks_for_everything_in_one_statement() -> None:
    """Query asks for everything in one statement."""
    query = build_query(BOX, ("motorway", "trunk"), "Albuquerque")
    assert query.startswith("[out:json]")
    assert query.count("(34.94,-106.88,35.22,-106.47)") == STATEMENTS_WITH_BOUNDARY
    assert '"^(motorway|trunk)$"' in query
    assert '[name="Albuquerque"]' in query
    assert query.rstrip().endswith("out geom;")


def test_query_without_boundary_has_no_admin_relation() -> None:
    """Query without boundary has no admin relation."""
    assert "administrative" not in build_query(BOX, ("motorway",), None)


def test_boundary_name_is_escaped() -> None:
    """Boundary name is escaped."""
    assert r'[name="Say \"hi\""]' in build_query(BOX, ("motorway",), 'Say "hi"')


def test_fetch_posts_once_with_a_generic_user_agent() -> None:
    """Fetch posts once with a generic user agent."""
    opener = FakeOpener([OK_BODY])
    assert fetch("[out:json];", opener=opener, sleep=lambda _s: None) == {"elements": []}
    (request,) = opener.requests
    assert request.get_method() == "POST"
    assert request.full_url == OVERPASS_URL
    assert request.get_header("User-agent") == USER_AGENT


@pytest.mark.parametrize("code", [TOO_MANY_REQUESTS, GATEWAY_TIMEOUT], ids=["rate_limited", "gateway_timeout"])
def test_fetch_backs_off_and_retries(code: int) -> None:
    """Fetch backs off and retries."""
    opener = FakeOpener([_http_error(code), _http_error(code), OK_BODY])
    waits: list[float] = []
    assert fetch("q", opener=opener, sleep=waits.append) == {"elements": []}
    assert waits == [FIRST_BACKOFF_S, FIRST_BACKOFF_S * BACKOFF_FACTOR]


def test_fetch_gives_up_after_max_attempts() -> None:
    """Fetch gives up after max attempts."""
    opener = FakeOpener([_http_error(TOO_MANY_REQUESTS) for _ in range(MAX_ATTEMPTS)])
    waits: list[float] = []
    with pytest.raises(OverpassError, match="HTTP 429") as caught:
        fetch("q", opener=opener, sleep=waits.append)
    assert isinstance(caught.value.__cause__, HTTPError)
    assert len(waits) == MAX_ATTEMPTS - 1


def test_fetch_does_not_retry_other_http_errors() -> None:
    """Fetch does not retry other http errors."""
    opener = FakeOpener([_http_error(SERVER_ERROR), OK_BODY])
    with pytest.raises(OverpassError, match="HTTP 500"):
        fetch("q", opener=opener, sleep=lambda _s: None)
    assert len(opener.requests) == 1


def test_fetch_wraps_connection_failures() -> None:
    """Fetch wraps connection failures."""
    opener = FakeOpener([URLError("no route to host")])
    with pytest.raises(OverpassError, match="could not reach Overpass"):
        fetch("q", opener=opener, sleep=lambda _s: None)


def test_fetch_rejects_html_error_pages() -> None:
    """Fetch rejects html error pages."""
    opener = FakeOpener([b"<html>busy</html>"])
    with pytest.raises(OverpassError, match="did not return JSON"):
        fetch("q", opener=opener, sleep=lambda _s: None)


def test_fetch_surfaces_runtime_errors_reported_in_the_remark() -> None:
    """Fetch surfaces runtime errors reported in the remark."""
    opener = FakeOpener([b'{"elements": [], "remark": "runtime error: Query timed out"}'])
    with pytest.raises(OverpassError, match="timed out"):
        fetch("q", opener=opener, sleep=lambda _s: None)


@pytest.mark.parametrize(
    "text",
    ["1,2,3", "35,-106,34,-105", "35,-105,36,-106", "91,0,92,1", "a,b,c,d", "nan,0,1,1"],
    ids=["three_numbers", "south_above_north", "west_east_swapped", "off_globe", "not_numbers", "not_finite"],
)
def test_bad_bbox_rejected(text: str) -> None:
    """Bad bbox rejected."""
    with pytest.raises(ValueError, match=r"bbox|could not convert"):
        BBox.parse(text)
