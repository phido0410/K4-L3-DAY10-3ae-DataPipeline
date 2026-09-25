from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import logging
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from core.config import Settings
from core.utils import normalize_whitespace, read_json, write_json

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PaperRecord:
    paper_id: str
    title: str
    summary: str
    authors: list[str]
    categories: list[str]
    primary_category: str
    published: str
    updated: str
    abs_url: str
    pdf_url: str
    comment: str


def _clean_jats_tags(text: str) -> str:
    """Loại bỏ thẻ XML/HTML (như <jats:p>, <jats:title>, ...) và normalize whitespace."""
    if not text:
        return ""
    stripped = re.sub(r"<[^>]+>", " ", text)
    return normalize_whitespace(stripped)


def parse_crossref_payload(payload: dict) -> list[PaperRecord]:
    """Parse Crossref payload thành danh sách PaperRecord.

    Rules:
    1. Duyệt `payload["message"]["items"]`.
    2. Lấy DOI -> paper_id, title, abstract (bỏ tag JATS), authors, categories, dates, URLs.
    3. Bỏ qua các record thiếu DOI, title, hoặc abstract.
    4. Trả về list[PaperRecord].
    """
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        if "message" in payload and isinstance(payload["message"], dict):
            items = payload["message"].get("items", [])
        else:
            items = payload.get("items", [])
    else:
        items = []

    records: list[PaperRecord] = []

    for item in items:
        if not isinstance(item, dict):
            continue

        # 1. DOI -> paper_id
        doi = item.get("DOI") or item.get("doi")
        if not doi or not isinstance(doi, str) or not doi.strip():
            continue
        paper_id = doi.strip()

        # 2. Title
        raw_title = item.get("title", [])
        if isinstance(raw_title, list):
            title = " ".join(str(t) for t in raw_title if t).strip()
        elif isinstance(raw_title, str):
            title = raw_title.strip()
        else:
            title = ""
        title = normalize_whitespace(title)
        if not title:
            continue

        # 3. Abstract -> summary
        raw_abstract = item.get("abstract", "")
        if not isinstance(raw_abstract, str):
            raw_abstract = ""
        summary = _clean_jats_tags(raw_abstract)
        if not summary:
            continue

        # 4. Authors
        raw_authors = item.get("author", [])
        authors: list[str] = []
        if isinstance(raw_authors, list):
            for a in raw_authors:
                if isinstance(a, dict):
                    given = str(a.get("given", "")).strip()
                    family = str(a.get("family", "")).strip()
                    full = f"{given} {family}".strip() if (given or family) else str(a.get("name", "")).strip()
                    if full:
                        authors.append(normalize_whitespace(full))
                elif isinstance(a, str) and a.strip():
                    authors.append(normalize_whitespace(a.strip()))

        # 5. Categories & primary_category
        raw_subject = item.get("subject", [])
        categories: list[str] = []
        if isinstance(raw_subject, list):
            for s in raw_subject:
                if isinstance(s, str) and s.strip():
                    categories.append(normalize_whitespace(s.strip()))
                elif isinstance(s, dict) and "name" in s:
                    categories.append(normalize_whitespace(str(s["name"])))
        elif isinstance(raw_subject, str) and raw_subject.strip():
            categories.append(normalize_whitespace(raw_subject.strip()))

        primary_category = categories[0] if categories else "General"

        # 6. Published date
        published_str = ""
        date_parts = (
            item.get("published", {}).get("date-parts")
            or item.get("issued", {}).get("date-parts")
            or item.get("created", {}).get("date-parts")
        )
        if date_parts and isinstance(date_parts, list) and len(date_parts) > 0:
            parts = date_parts[0]
            if isinstance(parts, list) and len(parts) > 0:
                try:
                    year = int(parts[0])
                    month = int(parts[1]) if len(parts) >= 2 else 1
                    day = int(parts[2]) if len(parts) >= 3 else 1
                    published_str = f"{year:04d}-{month:02d}-{day:02d}"
                except (ValueError, TypeError):
                    published_str = ""

        if not published_str:
            created_dt = item.get("created", {}).get("date-time", "")
            if isinstance(created_dt, str) and len(created_dt) >= 10:
                published_str = created_dt[:10]
            else:
                published_str = "2026-01-01"

        # 7. Updated date
        updated_str = published_str
        upd_parts = item.get("updated", {}).get("date-parts")
        if upd_parts and isinstance(upd_parts, list) and len(upd_parts) > 0:
            parts = upd_parts[0]
            if isinstance(parts, list) and len(parts) > 0:
                try:
                    year = int(parts[0])
                    month = int(parts[1]) if len(parts) >= 2 else 1
                    day = int(parts[2]) if len(parts) >= 3 else 1
                    updated_str = f"{year:04d}-{month:02d}-{day:02d}"
                except (ValueError, TypeError):
                    updated_str = published_str

        # 8. URLs
        abs_url = str(item.get("URL") or f"https://doi.org/{paper_id}").strip()
        pdf_url = abs_url
        links = item.get("link", [])
        if isinstance(links, list):
            for link in links:
                if isinstance(link, dict) and link.get("content-type") == "application/pdf":
                    pdf_url = str(link.get("URL", abs_url)).strip()
                    break

        comment = f"Crossref record {paper_id}"

        records.append(
            PaperRecord(
                paper_id=paper_id,
                title=title,
                summary=summary,
                authors=authors,
                categories=categories,
                primary_category=primary_category,
                published=published_str,
                updated=updated_str,
                abs_url=abs_url,
                pdf_url=pdf_url,
                comment=comment,
            )
        )

    return records


def fetch_source_records(settings: Settings) -> list[PaperRecord]:
    """Gọi Crossref API, lưu raw response, parse thành records, hỗ trợ fallback offline snapshot."""
    # 1. Nếu không bật REFRESH_SOURCE: ưu tiên fallback đọc snapshot
    if not settings.refresh_source:
        logger.info("REFRESH_SOURCE is disabled. Loading records from local snapshot...")
        if settings.paths.raw_records_json.exists():
            return load_raw_records(settings.paths.raw_records_json)
        if settings.paths.raw_api_response.exists():
            payload = read_json(settings.paths.raw_api_response)
            records = parse_crossref_payload(payload)
            write_json(settings.paths.raw_records_json, [asdict(r) for r in records])
            return records
        raise FileNotFoundError(
            f"Neither {settings.paths.raw_records_json} nor {settings.paths.raw_api_response} exists."
        )

    # 2. Nếu REFRESH_SOURCE bật: gọi Crossref REST API
    base_url = "https://api.crossref.org/works"
    params = {
        "query": settings.source_query,
        "rows": settings.max_results,
    }
    if settings.source_filter:
        params["filter"] = settings.source_filter

    query_str = urlencode(params)
    url = f"{base_url}?{query_str}"
    headers = {
        "User-Agent": "DataObservabilityLab/1.0 (mailto:admin@datapipe.ai)",
        "Accept": "application/json",
    }

    max_retries = 3
    payload = None
    for attempt in range(1, max_retries + 1):
        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=30) as response:
                if response.status == 200:
                    payload = json.loads(response.read().decode("utf-8"))
                    break
        except HTTPError as e:
            logger.warning("HTTP error %d on attempt %d: %s", e.code, attempt, e.reason)
            if e.code in (429, 500, 502, 503, 504) and attempt < max_retries:
                time.sleep(2 ** attempt)
                continue
            break
        except (URLError, TimeoutError, OSError) as e:
            logger.warning("Network error on attempt %d: %s", attempt, str(e))
            if attempt < max_retries:
                time.sleep(2 ** attempt)
                continue
            break
        except Exception as e:
            logger.warning("Unexpected error fetching Crossref records: %s", str(e))
            break

    # Nếu fetch thành công: lưu snapshot và parse
    if payload and "message" in payload:
        write_json(settings.paths.raw_api_response, payload)
        records = parse_crossref_payload(payload)
        write_json(settings.paths.raw_records_json, [asdict(r) for r in records])
        return records

    # 3. Fallback khi API thất bại hoặc quá tải
    logger.warning("Failed to fetch fresh records from Crossref API. Falling back to local snapshot.")
    if settings.paths.raw_records_json.exists():
        return load_raw_records(settings.paths.raw_records_json)
    if settings.paths.raw_api_response.exists():
        fallback_payload = read_json(settings.paths.raw_api_response)
        records = parse_crossref_payload(fallback_payload)
        write_json(settings.paths.raw_records_json, [asdict(r) for r in records])
        return records

    raise RuntimeError("Crossref API fetch failed and no local snapshot found.")


def load_raw_records(path: Path) -> list[PaperRecord]:
    """Đọc snapshot JSON và chuyển thành list[PaperRecord]."""
    data = read_json(path)
    if not isinstance(data, list):
        raise ValueError(f"Expected a list of records in {path}, got {type(data).__name__}")

    records: list[PaperRecord] = []
    for item in data:
        records.append(
            PaperRecord(
                paper_id=str(item["paper_id"]),
                title=str(item["title"]),
                summary=str(item["summary"]),
                authors=list(item.get("authors", [])),
                categories=list(item.get("categories", [])),
                primary_category=str(item.get("primary_category", "General")),
                published=str(item["published"]),
                updated=str(item.get("updated", item["published"])),
                abs_url=str(item.get("abs_url", "")),
                pdf_url=str(item.get("pdf_url", "")),
                comment=str(item.get("comment", "")),
            )
        )
    return records
