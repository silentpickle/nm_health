import re  # noqa: CPY001, D100, I001
import subprocess
from typing import Dict, Any, List, Optional  # noqa: F401, UP035
from pathlib import Path
from nm_health.ingest.normalizer import normalize_address, normalize_establishment_name, clean_text  # noqa: F401

# Layout lines that are not part of any inspection's text.
FOOTER_RE = re.compile(r"^\s*Page \d+ of \d+\s*$")
CLASS_LINE_RE = re.compile(r"^\s*\S.*\bClass\s+\w+\s*$")  # "Retail Food Establishment Class 5"


def _drop_layout_lines(page_text: str) -> str:
    """Remove page footers from a detail page."""
    return "\n".join(line for line in page_text.split("\n") if not FOOTER_RE.match(line))


def _pop_blank(lines: list[str]) -> None:
    """Drop trailing blank lines (form feeds count as blank)."""
    while lines and not lines[-1].strip():
        lines.pop()


def _block_end(text: str, next_date_pos: int) -> int:
    """Where an inspection's text ends: before the next block's heading, name/address and permit-class lines."""
    lines = text[:next_date_pos].split("\n")
    _pop_blank(lines)
    if not lines or not CLASS_LINE_RE.match(lines[-1]):
        return next_date_pos
    lines.pop()
    _pop_blank(lines)
    name_line = lines.pop().strip() if lines else ""
    _pop_blank(lines)
    if name_line and lines and lines[-1].strip().startswith(name_line):
        lines.pop()  # the "NAME - ADDRESS - <status>" heading above the block
    return len("\n".join(lines))


# A violation's heading line; the PDF sometimes prints a stray ". " before it.
VIOLATION_HEADING = re.compile(r"\n[\s.]*Violation:\s*")
BULLETS = ("\u2022", "*")
OBSERVATION_PREFIXES = (
    "Observed",
    "Location:",
    "Condition:",
    "Pest Type:",
    "Food Items:",
    "Concentration:",
    "instructed pic",
    "pic cleaned",
)
PEST_WORDS_RE = re.compile(r"pest|mice|mouse|roach|cockroach|rodent|fly|flies|insect|vermin|infestation", re.IGNORECASE)


def _is_bullet(line: str) -> bool:
    return line.startswith(BULLETS)


def _split_bullets(lines: list[str]) -> list[list[str]]:
    """Group a violation's lines into one list per bullet item; lines before the first bullet join it."""
    groups: list[list[str]] = [[]]
    for line in lines:
        if _is_bullet(line) and any(_is_bullet(seen) for seen in groups[-1]):
            groups.append([])
        groups[-1].append(line)
    return groups


def _violation_from(category: str, lines: list[str], raw_text: str) -> dict[str, Any]:
    """One violation record: bullet = item, '-' lines = rule text, 'Observed...' and what follows = observation."""
    item_title = ""
    rule_desc: list[str] = []
    observations: list[str] = []
    for line in lines:
        if _is_bullet(line):
            item_title = line.lstrip("\u2022* ").strip()
            continue
        if line.startswith("-"):
            rule_desc.append(line.lstrip("- ").strip())
            continue
        if line.startswith(OBSERVATION_PREFIXES) or observations:
            observations.append(line)
            continue
        rule_desc.append(line)
    return {
        "category": category,
        "item_title": item_title or category,
        "rule_description": " ".join(rule_desc),
        "observation": " ".join(observations),
        "raw_text": raw_text,
        "is_pest": bool(PEST_WORDS_RE.search(raw_text)),
    }


class InspectionReportParser:
    """
    Parses City of Albuquerque Environmental Health Department
    weekly food inspection PDF reports.
    """  # noqa: D205, D212

    def __init__(self, pdf_path: Path):  # noqa: ANN204, D107
        self.pdf_path = Path(pdf_path)
        if not self.pdf_path.exists():
            raise FileNotFoundError(f"PDF report not found: {self.pdf_path}")  # noqa: EM102, TRY003

    def extract_text_pages(self) -> List[str]:  # noqa: UP006
        """Extract text page-by-page using pdftotext with layout preservation."""
        cmd = ["pdftotext", "-layout", str(self.pdf_path), "-"]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)  # noqa: UP022
            text = res.stdout.decode("utf-8", errors="ignore")
            # pdftotext separates pages with form feed \x0c
            pages = text.split("\x0c")
            return pages  # noqa: RET504, TRY300
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"Failed to extract text from PDF: {e}")  # noqa: B904, EM102, TRY003

    def parse(self) -> Dict[str, Any]:  # noqa: D102, UP006
        pages = self.extract_text_pages()
        if not pages:
            return {"error": "Empty PDF"}

        # 1. Parse Metadata from cover / summary pages
        metadata = self._parse_metadata(pages[0])

        # 2. Identify Summary Pages vs Detail Pages
        summary_pages = []
        detail_pages = []
        for i, page in enumerate(pages):
            if "Summary Table" in page or (i < 8 and "Inspection Date" in page and "Inspection ID Number" in page):  # noqa: PLR2004
                summary_pages.append((i + 1, page))
            else:
                detail_pages.append((i + 1, page))

        # 3. Parse Summary Table records
        summary_records = self._parse_summary_pages(summary_pages)

        # 4. Parse Detailed Inspection Sections and Violations
        detail_records = self._parse_detail_pages(detail_pages)

        # 5. Merge Summary records with Detailed Violations
        establishments_map = {}
        inspections = []

        for item in summary_records:
            insp_id = item["id_num"]
            insp_date = item["date"]
            key = f"{insp_id}_{insp_date}"

            detail_info = detail_records.get(key)
            if not detail_info:
                # Fallback match by ID alone
                detail_info = detail_records.get(insp_id, {})

            violations = detail_info.get("violations", [])
            has_pest = any(v.get("is_pest") for v in violations)
            has_critical = any(
                "closure" in item["status"].lower() or "unsatisfactory" in item["status"].lower() or has_pest
                for _ in [1]
            )

            # Build establishment entry
            est_name = item["establishment"]["name"]
            est_addr = item["establishment"]["address"]
            addr_info = normalize_address(est_addr)
            est_key = addr_info["slug"]

            if est_key not in establishments_map:
                establishments_map[est_key] = {
                    "name": est_name,
                    "raw_address": est_addr,
                    "normalized_address": addr_info["normalized_address"],
                    "permits": {},
                    "inspections": [],
                }

            # Permit
            if item.get("permit"):
                p_num = item["permit"]["permit_number"]
                establishments_map[est_key]["permits"][p_num] = item["permit"]

            # Inspection record
            inspection_entry = {
                "establishment_slug": est_key,
                "establishment_name": est_name,
                "establishment_address": est_addr,
                "permit_number": item["permit"]["permit_number"] if item.get("permit") else None,
                "permit_type": item["permit"]["permit_type"] if item.get("permit") else None,
                "operational_status": item["permit"]["operational_status"] if item.get("permit") else "Open",
                "inspection_id_num": insp_id,
                "inspection_date": self._format_date(insp_date),
                "inspection_type": item["type"],
                "inspection_status": item["status"],
                "summary_page": item["page_num"],
                "detail_page": detail_info.get("page_num"),
                "has_pest_violation": has_pest,
                "has_critical_violation": has_critical,
                "violation_count": len(violations),
                "violations": violations,
                "raw_summary_line": item.get("raw", ""),
            }

            inspections.append(inspection_entry)
            establishments_map[est_key]["inspections"].append(inspection_entry)

        return {
            "metadata": metadata,
            "total_establishments": len(establishments_map),
            "total_inspections": len(inspections),
            "establishments": establishments_map,
            "inspections": inspections,
        }

    def _parse_metadata(self, first_page: str) -> Dict[str, Any]:  # noqa: UP006
        meta = {
            "week_start": None,
            "week_end": None,
            "week_range_str": "",
            "raw_title": "",
            "amendment_notes": "",
        }

        m_week = re.search(r"Week:\s*([A-Za-z]+ \d+, \d+)\s*to\s*([A-Za-z]+ \d+, \d+)", first_page)
        if m_week:
            meta["week_start"] = m_week.group(1).strip()
            meta["week_end"] = m_week.group(2).strip()
            meta["week_range_str"] = f"{meta['week_start']} to {meta['week_end']}"

        m_amend = re.search(r"(Report Amended on [^\n\r]+)", first_page, re.IGNORECASE)
        if m_amend:
            meta["amendment_notes"] = m_amend.group(1).strip()

        m_title = re.search(r"(Media Report [^\n\r]+)", first_page, re.IGNORECASE)
        if m_title:
            meta["raw_title"] = m_title.group(1).strip()

        return meta

    def _format_date(self, d_str: str) -> str:
        """Convert MM/DD/YYYY to YYYY-MM-DD for standard sortable dates."""
        m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", d_str.strip())
        if m:
            return f"{m.group(3)}-{m.group(1)}-{m.group(2)}"
        return d_str.strip()

    def _parse_summary_pages(self, summary_pages: List[tuple]) -> List[Dict[str, Any]]:  # noqa: UP006
        records = []
        current_est = None
        current_permit = None

        est_re = re.compile(r"^([A-Za-z0-9\s#&\'\.\,\-]+?)\s+-\s+(\d+[A-Za-z0-9\s\,\-\.#/]+)$")
        permit_re = re.compile(
            r"^(.*?)\(Permit\s*#\s*-\s*([A-Za-z0-9-]+)\)\s*-\s*Operational\s*Status\s*[-–]\s*([A-Za-z]+)",  # noqa: RUF001
            re.IGNORECASE,
        )
        row_re = re.compile(
            r"^\s*(\d{2}/\d{2}/\d{4})\s+([A-Za-z0-9\-]+)\s+(.+?)\s{2,}([A-Za-z\s\-]+?)\s+(?:Pg\.\s*(\d+)|Page\s*(\d+)|(\d+))\s*$",
            re.IGNORECASE,
        )

        for page_num, text in summary_pages:  # noqa: B007
            lines = text.split("\n")
            for line in lines:
                line_str = line.rstrip()
                if not line_str:
                    continue
                if any(
                    hdr in line_str
                    for hdr in [
                        "City of Albuquerque",
                        "Environmental Health",
                        "Consumer Health",
                        "Summary Table",
                        "Inspection Date",
                        "Page ",
                        "This report includes",
                    ]
                ):
                    continue

                # Check permit line
                m_permit = permit_re.match(line_str.strip())
                if m_permit:
                    current_permit = {
                        "permit_type": m_permit.group(1).strip(),
                        "permit_number": m_permit.group(2).strip(),
                        "operational_status": m_permit.group(3).strip(),
                    }
                    continue

                # Check inspection row
                m_row = row_re.match(line_str)
                if m_row:
                    target_pg = m_row.group(5) or m_row.group(6) or m_row.group(7) or ""
                    records.append(
                        {
                            "establishment": current_est,
                            "permit": current_permit,
                            "date": m_row.group(1),
                            "id_num": m_row.group(2).strip(),
                            "type": m_row.group(3).strip(),
                            "status": m_row.group(4).strip(),
                            "page_str": f"Pg. {target_pg}",
                            "page_num": int(target_pg) if target_pg.isdigit() else None,
                            "raw": line_str.strip(),
                        }
                    )
                    continue

                # Check establishment header
                m_est = est_re.match(line_str.strip())
                if (
                    m_est
                    and not line_str.strip().startswith("Week:")
                    and not line_str.strip().startswith("Report Amended")
                ):
                    current_est = {
                        "name": m_est.group(1).strip(),
                        "address": m_est.group(2).strip(),
                    }

        return records

    def _parse_detail_pages(self, detail_pages: List[tuple]) -> Dict[str, Any]:  # noqa: UP006
        """
        Parses pages containing detailed inspection blocks and violations.
        Returns a dict keyed by '<id_num>_<date>' and '<id_num>'.
        """  # noqa: D205, D212
        detail_records = {}

        # Stitch detail pages while tracking page numbers
        full_detail_text = ""
        page_offsets = []
        current_len = 0
        for page_num, text in detail_pages:
            page_offsets.append((current_len, page_num))
            full_detail_text += _drop_layout_lines(text) + "\n\x0c"
            current_len = len(full_detail_text)

        def get_page_for_pos(pos: int) -> int:
            for offset, p_num in reversed(page_offsets):
                if pos >= offset:
                    return p_num
            return detail_pages[0][0] if detail_pages else 1

        insp_pattern = re.compile(
            r"Date:\s*(\d{2}/\d{2}/\d{4})\s*-\s*#:\s*([^\s-]+(?:-[^\s-]+)*)\s*-\s*Inspection Result:\s*([^\n\r]+)"
        )

        matches = list(insp_pattern.finditer(full_detail_text))
        for i in range(len(matches)):
            m = matches[i]
            insp_date = m.group(1)
            insp_id = m.group(2).strip()
            insp_result = m.group(3).strip()
            block_page = get_page_for_pos(m.start())

            start_pos = m.end()
            end_pos = (
                _block_end(full_detail_text, matches[i + 1].start()) if i + 1 < len(matches) else len(full_detail_text)
            )
            block_text = full_detail_text[start_pos:end_pos]

            violations = self._parse_violations(block_text)

            rec = {
                "inspection_id": insp_id,
                "inspection_date": insp_date,
                "inspection_result": insp_result,
                "page_num": block_page,
                "violations": violations,
            }

            detail_records[f"{insp_id}_{insp_date}"] = rec
            detail_records[insp_id] = rec

        return detail_records

    def _parse_violations(self, block_text: str) -> list[dict[str, Any]]:
        """One record per bullet item under each 'Violation:' category."""
        violations: list[dict[str, Any]] = []
        for part in VIOLATION_HEADING.split(block_text)[1:]:
            lines = [line.strip() for line in part.split("\n") if line.strip()]
            if not lines:
                continue
            groups = _split_bullets(lines[1:])
            for group in groups:
                raw_text = part.strip() if len(groups) == 1 else "\n".join([lines[0], *group])
                violations.append(_violation_from(lines[0], group, raw_text))
        return violations
