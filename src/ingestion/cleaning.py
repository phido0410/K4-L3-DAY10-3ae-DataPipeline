from __future__ import annotations

from datetime import date, datetime
import re

import pandas as pd

from core.utils import compact_join, normalize_whitespace
from ingestion.crossref import PaperRecord


def _clean_text(value: str) -> str:
    """Loại bỏ thẻ XML/HTML thừa và chuẩn hóa khoảng trắng."""
    if not value:
        return ""
    stripped = re.sub(r"<[^>]+>", " ", value)
    return normalize_whitespace(stripped)


def build_clean_dataframe(records: list[PaperRecord], run_date: datetime) -> pd.DataFrame:
    """Clean raw records thành dataframe chuẩn, sẵn sàng để embed và đánh chỉ mục vector.

    Clean schema contract:
    - paper_id: str (DOI, unique, not null)
    - title: str (whitespace normalized)
    - summary: str (JATS/HTML tags stripped, whitespace normalized)
    - authors: list[str]
    - categories: list[str]
    - primary_category: str
    - published: str (YYYY-MM-DD)
    - updated: str (YYYY-MM-DD)
    - abs_url: str
    - pdf_url: str
    - comment: str
    - authors_joined: str (", ".join(authors))
    - categories_joined: str (", ".join(categories))
    - summary_chars: int (len(summary))
    - age_days: int ((run_date - published).days)
    - text_for_embedding: str (Title: ...\nAuthors: ...\nPublished: ...\nCategories: ...\nSummary: ...)
    """
    run_date_val = run_date.date() if isinstance(run_date, datetime) else run_date

    rows: list[dict] = []
    for record in records:
        paper_id = normalize_whitespace(record.paper_id)
        if not paper_id:
            continue

        title = normalize_whitespace(record.title)
        if not title:
            continue

        summary = _clean_text(record.summary)
        if not summary:
            continue

        authors = [normalize_whitespace(a) for a in record.authors if normalize_whitespace(a)]
        categories = [normalize_whitespace(c) for c in record.categories if normalize_whitespace(c)]
        primary_category = normalize_whitespace(record.primary_category) if record.primary_category else (categories[0] if categories else "General")

        # Parse published date
        pub_str = record.published[:10] if record.published else "2026-01-01"
        try:
            pub_date = datetime.strptime(pub_str, "%Y-%m-%d").date()
        except ValueError:
            pub_date = date(2026, 1, 1)
            pub_str = "2026-01-01"

        # Parse updated date
        upd_str = record.updated[:10] if record.updated else pub_str
        try:
            datetime.strptime(upd_str, "%Y-%m-%d")
        except ValueError:
            upd_str = pub_str

        # age_days = (run_date - published).days
        age_days = int((run_date_val - pub_date).days)

        authors_joined = compact_join(authors, ", ")
        categories_joined = compact_join(categories, ", ")
        summary_chars = len(summary)

        # 5-part context for embedding
        text_for_embedding = (
            f"Title: {title}\n"
            f"Authors: {authors_joined}\n"
            f"Published: {pub_str}\n"
            f"Categories: {categories_joined}\n"
            f"Summary: {summary}"
        )

        rows.append(
            {
                "paper_id": paper_id,
                "title": title,
                "summary": summary,
                "authors": authors,
                "categories": categories,
                "primary_category": primary_category,
                "published": pub_str,
                "updated": upd_str,
                "abs_url": record.abs_url.strip(),
                "pdf_url": record.pdf_url.strip(),
                "comment": record.comment.strip(),
                "authors_joined": authors_joined,
                "categories_joined": categories_joined,
                "summary_chars": summary_chars,
                "age_days": age_days,
                "text_for_embedding": text_for_embedding,
            }
        )

    columns = [
        "paper_id",
        "title",
        "summary",
        "authors",
        "categories",
        "primary_category",
        "published",
        "updated",
        "abs_url",
        "pdf_url",
        "comment",
        "authors_joined",
        "categories_joined",
        "summary_chars",
        "age_days",
        "text_for_embedding",
    ]

    if not rows:
        return pd.DataFrame(columns=columns)

    df = pd.DataFrame(rows, columns=columns)

    # Lọc dòng xấu: summary_chars >= 30 theo Great Expectations data quality gate
    df = df[df["summary_chars"] >= 30]

    # Khử trùng lặp theo paper_id (giữ bản ghi đầu tiên)
    df = df.drop_duplicates(subset=["paper_id"], keep="first")

    # Sắp xếp theo ngày xuất bản giảm dần, sau đó theo paper_id
    df = df.sort_values(by=["published", "paper_id"], ascending=[False, True]).reset_index(drop=True)

    return df
