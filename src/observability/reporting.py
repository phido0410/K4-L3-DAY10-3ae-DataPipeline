from __future__ import annotations

from pathlib import Path
from typing import Any

from core.utils import now_utc, write_text

# (key trong metrics summary, nhan hien thi, co phai ty le 0-1 khong)
METRIC_ROWS = [
    ("samples", "Samples", False),
    ("retrieval_hit_rate", "Retrieval Hit Rate", True),
    ("mean_token_f1", "Mean Token F1", True),
    ("judge_accuracy", "LLM Judge Accuracy", True),
    ("mean_judge_score", "Mean Judge Score (1-5)", False),
]

FRESHNESS_ROWS = [
    ("latest_published", "Latest published"),
    ("oldest_published", "Oldest published"),
    ("total_rows", "Total rows"),
    ("stale_rows", "Stale rows"),
    ("stale_ratio", "Stale ratio"),
    ("is_fresh", "Is fresh"),
]


def _fmt(value: Any, percent: bool = False) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, bool):
        return "PASS" if value else "FAIL"
    if isinstance(value, float):
        return f"{value:.2%}" if percent else f"{value:.4f}"
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value) or "-"
    return str(value)


def _fmt_delta(new: Any, old: Any, percent: bool) -> str:
    if not isinstance(new, (int, float)) or not isinstance(old, (int, float)) or isinstance(new, bool):
        return "n/a"
    delta = new - old
    if percent:
        return f"{delta * 100:+.1f} pp"
    return f"{delta:+.4f}" if isinstance(delta, float) else f"{delta:+d}"


def _table(headers: list[str], rows: list[list[str]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(" --- " for _ in headers) + "|"]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return lines


def _ragas_lines(metrics: dict[str, Any]) -> list[str]:
    ragas = metrics.get("ragas")
    if not isinstance(ragas, dict) or not ragas:
        return []
    if "skipped" in ragas or "error" in ragas:
        return [f"- Ragas: {ragas.get('skipped') or ragas.get('error')}"]
    return [f"- Ragas `{key}`: {_fmt(value)}" for key, value in ragas.items()]


def _quality_detail_lines(quality: dict[str, Any]) -> list[str]:
    rows = []
    for item in quality.get("results", []):
        observed = item.get("observed_value")
        if observed is None and "unexpected_count" in item:
            observed = f"{item['unexpected_count']} unexpected / {item.get('element_count', '?')}"
        rows.append([f"`{item.get('expectation')}`", _fmt(item.get("column")), _fmt(item.get("success")), _fmt(observed)])
    if not rows:
        return []
    return _table(["Expectation", "Column", "Status", "Observed"], rows)


def generate_phase1_report(
    report_path,
    source_summary: dict[str, Any],
    metrics: dict[str, Any],
    quality: dict[str, Any],
    freshness: dict[str, Any],
) -> None:
    """Viet markdown report cho baseline phase: source, metrics, quality gate, freshness."""
    lines = [
        "# Phase 1 Report - Baseline Pipeline",
        "",
        f"_Generated at {now_utc().isoformat(timespec='seconds')}_",
        "",
        "## 1. Source Summary",
        "",
        *_table(["Field", "Value"], [[str(key), _fmt(value)] for key, value in source_summary.items()]),
        "",
        "## 2. Retrieval & Answer Quality",
        "",
        *_table(
            ["Metric", "Value"],
            [[label, _fmt(metrics.get(key), percent)] for key, label, percent in METRIC_ROWS if key in metrics],
        ),
        "",
        *_ragas_lines(metrics),
        "",
        "## 3. Data Quality Gate (Great Expectations 1.x)",
        "",
        f"- Overall status: **{_fmt(quality.get('success'))}**",
        f"- Expectations passed: {quality.get('successful_expectations', 'n/a')}/{quality.get('evaluated_expectations', 'n/a')}",
        f"- Failed expectations: {_fmt(quality.get('failed_expectations') or [])}",
        "",
        *_quality_detail_lines(quality),
        "",
        "## 4. Freshness SLA",
        "",
        f"Threshold: `age_days > {freshness.get('threshold_days', 'n/a')}` is stale; "
        f"data is fresh when stale ratio <= {_fmt(freshness.get('max_stale_ratio'), True)}.",
        "",
        *_table(
            ["Field", "Value"],
            [[label, _fmt(freshness.get(key), key == "stale_ratio")] for key, label in FRESHNESS_ROWS],
        ),
        "",
    ]
    write_text(Path(report_path), "\n".join(lines))


def _analysis_lines(
    baseline: dict[str, Any],
    corrupted: dict[str, Any],
    repaired: dict[str, Any],
    corrupted_quality: dict[str, Any],
    repaired_quality: dict[str, Any],
    corrupted_freshness: dict[str, Any],
    repaired_freshness: dict[str, Any],
) -> list[str]:
    """Nhan xet tu dong, chi dua tren so lieu thuc te duoc truyen vao."""
    lines = []
    for key, label, percent in METRIC_ROWS[1:]:
        base, bad, fixed = baseline.get(key), corrupted.get(key), repaired.get(key)
        if not all(isinstance(value, (int, float)) for value in (base, bad, fixed)):
            continue
        if bad < base:
            trend = f"giảm từ {_fmt(base, percent)} xuống {_fmt(bad, percent)} ({_fmt_delta(bad, base, percent)})"
        elif bad > base:
            trend = f"tăng từ {_fmt(base, percent)} lên {_fmt(bad, percent)} ({_fmt_delta(bad, base, percent)})"
        else:
            trend = f"không đổi ({_fmt(base, percent)})"
        recovered = "phục hồi về mức baseline" if abs(fixed - base) < 1e-9 else f"sau repair đạt {_fmt(fixed, percent)} ({_fmt_delta(fixed, base, percent)} so với baseline)"
        lines.append(f"- **{label}**: khi dữ liệu lỗi {trend}; {recovered}.")

    failed = corrupted_quality.get("failed_expectations") or []
    gate = "chặn được dữ liệu lỗi" if corrupted_quality.get("success") is False else "KHÔNG phát hiện dữ liệu lỗi"
    lines.append(f"- **Quality Gate** {gate} (corrupted = {_fmt(corrupted_quality.get('success'))}; vi phạm: {_fmt(failed)}); sau repair = {_fmt(repaired_quality.get('success'))}.")
    lines.append(
        f"- **Freshness SLA**: corrupted có {corrupted_freshness.get('stale_rows', 'n/a')}/{corrupted_freshness.get('total_rows', 'n/a')} "
        f"bài quá hạn (is_fresh = {_fmt(corrupted_freshness.get('is_fresh'))}); repaired có "
        f"{repaired_freshness.get('stale_rows', 'n/a')}/{repaired_freshness.get('total_rows', 'n/a')} (is_fresh = {_fmt(repaired_freshness.get('is_fresh'))})."
    )
    return lines


def generate_corruption_report(
    report_path,
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
    corrupted_quality: dict[str, Any],
    repaired_quality: dict[str, Any],
    corrupted_freshness: dict[str, Any],
    repaired_freshness: dict[str, Any],
) -> None:
    """Viet markdown report so sanh baseline/corrupted/repaired."""
    metric_rows = [
        [
            label,
            _fmt(baseline_metrics.get(key), percent),
            _fmt(corrupted_metrics.get(key), percent),
            _fmt(repaired_metrics.get(key), percent),
            _fmt_delta(corrupted_metrics.get(key), baseline_metrics.get(key), percent),
            _fmt_delta(repaired_metrics.get(key), baseline_metrics.get(key), percent),
        ]
        for key, label, percent in METRIC_ROWS
    ]
    quality_rows = [
        ["Overall status", _fmt(corrupted_quality.get("success")), _fmt(repaired_quality.get("success"))],
        ["Row count", _fmt(corrupted_quality.get("row_count")), _fmt(repaired_quality.get("row_count"))],
        [
            "Expectations passed",
            f"{corrupted_quality.get('successful_expectations', 'n/a')}/{corrupted_quality.get('evaluated_expectations', 'n/a')}",
            f"{repaired_quality.get('successful_expectations', 'n/a')}/{repaired_quality.get('evaluated_expectations', 'n/a')}",
        ],
        [
            "Failed expectations",
            _fmt(corrupted_quality.get("failed_expectations") or []),
            _fmt(repaired_quality.get("failed_expectations") or []),
        ],
    ]
    freshness_rows = [
        [label, _fmt(corrupted_freshness.get(key), key == "stale_ratio"), _fmt(repaired_freshness.get(key), key == "stale_ratio")]
        for key, label in FRESHNESS_ROWS
    ]

    lines = [
        "# Corruption Report - Baseline vs Corrupted vs Repaired",
        "",
        f"_Generated at {now_utc().isoformat(timespec='seconds')}_",
        "",
        "## 1. RAG Metrics",
        "",
        *_table(["Metric", "Baseline", "Corrupted", "Repaired", "Δ Corrupted", "Δ Repaired"], metric_rows),
        "",
        "## 2. Data Quality Gate (Great Expectations 1.x)",
        "",
        *_table(["Check", "Corrupted", "Repaired"], quality_rows),
        "",
        "### Corrupted - expectation details",
        "",
        *_quality_detail_lines(corrupted_quality),
        "",
        "## 3. Freshness SLA",
        "",
        *_table(["Field", "Corrupted", "Repaired"], freshness_rows),
        "",
        "## 4. Analysis",
        "",
        *_analysis_lines(
            baseline_metrics,
            corrupted_metrics,
            repaired_metrics,
            corrupted_quality,
            repaired_quality,
            corrupted_freshness,
            repaired_freshness,
        ),
        "",
    ]
    write_text(Path(report_path), "\n".join(lines))
