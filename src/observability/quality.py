from __future__ import annotations

from pathlib import Path
from typing import Any

import great_expectations as gx
import pandas as pd

from core.config import Settings
from core.utils import now_utc, write_json

MIN_ROWS = 5
MAX_ROWS = 5000
MIN_SUMMARY_CHARS = 30
MAX_STALE_RATIO = 0.25
REQUIRED_NOT_NULL_COLUMNS = ("paper_id", "title", "text_for_embedding")


def _build_expectations() -> list[Any]:
    """4 nhom expectation bat buoc cua Quality Gate."""
    expectations: list[Any] = [
        gx.expectations.ExpectTableRowCountToBeBetween(min_value=MIN_ROWS, max_value=MAX_ROWS),
    ]
    expectations.extend(gx.expectations.ExpectColumnValuesToNotBeNull(column=column) for column in REQUIRED_NOT_NULL_COLUMNS)
    expectations.append(gx.expectations.ExpectColumnValuesToBeUnique(column="paper_id"))
    expectations.append(gx.expectations.ExpectColumnValueLengthsToBeBetween(column="summary", min_value=MIN_SUMMARY_CHARS))
    return expectations


def _summarize_result(result: Any) -> dict[str, Any]:
    config = result.expectation_config
    details = result.result or {}
    summary: dict[str, Any] = {
        "expectation": config.type,
        "column": config.kwargs.get("column"),
        "success": bool(result.success),
    }
    for key in ("observed_value", "element_count", "unexpected_count", "unexpected_percent"):
        if key in details:
            summary[key] = details[key]
    if "partial_unexpected_list" in details:
        summary["sample_unexpected"] = [str(value)[:80] for value in details["partial_unexpected_list"][:5]]
    exception = (result.exception_info or {}).get("exception_message")
    if exception:
        summary["exception"] = exception
    return summary


def _stale_mask(df: pd.DataFrame, settings: Settings) -> pd.Series:
    if "age_days" in df.columns:
        age_days = pd.to_numeric(df["age_days"], errors="coerce")
    else:
        raw_published = df["published"] if "published" in df.columns else pd.Series(pd.NaT, index=df.index)
        published = pd.to_datetime(raw_published, errors="coerce", utc=True)
        age_days = (pd.Timestamp(now_utc()) - published).dt.days
    return age_days > settings.freshness_threshold_days


def run_data_quality_checks(df: pd.DataFrame, settings: Settings, report_name: str) -> dict[str, Any]:
    """Chay Quality Gate bang Great Expectations 1.x tren clean dataframe.

    - 4 expectation bat buoc: row count, not-null, unique `paper_id`, do dai `summary`.
    - `success` chi phu thuoc GX; freshness SLA duoc ghi kem de tham khao.
    - Ghi JSON vao `data/quality/<report_name>_quality_report.json`.
    """
    context = gx.get_context(mode="ephemeral")
    data_source = context.data_sources.add_pandas(name=f"{report_name}_source")
    data_asset = data_source.add_dataframe_asset(name=f"{report_name}_papers")
    batch_definition = data_asset.add_batch_definition_whole_dataframe(f"{report_name}_batch")
    batch = batch_definition.get_batch(batch_parameters={"dataframe": df})

    suite = context.suites.add(gx.ExpectationSuite(name=f"{report_name}_papers_suite"))
    for expectation in _build_expectations():
        suite.add_expectation(expectation)

    validation = batch.validate(suite)
    results = [_summarize_result(item) for item in validation.results]
    failed = [item for item in results if not item["success"]]

    stale_rows = int(_stale_mask(df, settings).sum())
    total_rows = int(len(df))
    stale_ratio = stale_rows / total_rows if total_rows else 1.0

    report = {
        "report_name": report_name,
        "generated_at": now_utc().isoformat(),
        "engine": f"great_expectations {gx.__version__}",
        "success": bool(validation.success),
        "row_count": total_rows,
        "evaluated_expectations": len(results),
        "successful_expectations": len(results) - len(failed),
        "failed_expectations": [
            f"{item['expectation']}({item['column']})" if item["column"] else item["expectation"] for item in failed
        ],
        "results": results,
        "freshness_sla": {
            "threshold_days": settings.freshness_threshold_days,
            "stale_rows": stale_rows,
            "stale_ratio": round(stale_ratio, 4),
            "max_stale_ratio": MAX_STALE_RATIO,
            "passed": total_rows > 0 and stale_ratio <= MAX_STALE_RATIO,
        },
    }
    write_json(settings.paths.quality_dir / f"{report_name}_quality_report.json", report)
    return report


def build_freshness_report(df: pd.DataFrame, settings: Settings, report_path) -> dict[str, Any]:
    """Tong hop Freshness SLA: `is_fresh` = ty le bai `age_days > threshold` <= 25%."""
    published = pd.to_datetime(df["published"], errors="coerce") if "published" in df.columns else pd.Series(dtype="datetime64[ns]")
    valid_published = published.dropna()
    total_rows = int(len(df))
    stale_rows = int(_stale_mask(df, settings).sum()) if total_rows else 0
    stale_ratio = stale_rows / total_rows if total_rows else 1.0
    age_days = pd.to_numeric(df["age_days"], errors="coerce") if "age_days" in df.columns else pd.Series(dtype=float)

    payload = {
        "generated_at": now_utc().isoformat(),
        "threshold_days": settings.freshness_threshold_days,
        "max_stale_ratio": MAX_STALE_RATIO,
        "latest_published": valid_published.max().date().isoformat() if not valid_published.empty else None,
        "oldest_published": valid_published.min().date().isoformat() if not valid_published.empty else None,
        "min_age_days": int(age_days.min()) if age_days.notna().any() else None,
        "max_age_days": int(age_days.max()) if age_days.notna().any() else None,
        "stale_rows": stale_rows,
        "total_rows": total_rows,
        "stale_ratio": round(stale_ratio, 4),
        "is_fresh": total_rows > 0 and stale_ratio <= MAX_STALE_RATIO,
    }
    write_json(Path(report_path), payload)
    return payload
