from __future__ import annotations

from typing import Any

import pandas as pd

from core.config import load_settings
from core.utils import now_utc, read_json
from evaluation.metrics import evaluate_pipeline
from ingestion.cleaning import build_clean_dataframe
from ingestion.corruption import corrupt_clean_dataframe
from ingestion.crossref import load_raw_records
from observability.dashboard import build_dashboard
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_corruption_report
from pipelines.phase1 import METRIC_KEYS, enforce_quality_gate, load_clean_json, save_clean_artifacts
from retrieval.index import LocalEmbeddingIndex


def _print_comparison(baseline: dict[str, Any], corrupted: dict[str, Any], repaired: dict[str, Any]) -> None:
    header = f"{'metric':<22}{'baseline':>10}{'corrupted':>11}{'repaired':>10}"
    print(header)
    print("-" * len(header))
    for key in METRIC_KEYS:
        print(f"{key:<22}{baseline[key]:>10.3f}{corrupted[key]:>11.3f}{repaired[key]:>10.3f}")


def _same_dataset(left: pd.DataFrame, right: pd.DataFrame) -> bool:
    # age_days depends on run date, so compare content columns only.
    columns = ["paper_id", "title", "summary", "published", "text_for_embedding"]
    key = ["paper_id"]
    return left[columns].sort_values(key).reset_index(drop=True).equals(
        right[columns].sort_values(key).reset_index(drop=True)
    )


def main() -> None:
    settings = load_settings()
    paths = settings.paths
    if not paths.baseline_metrics.exists() or not paths.clean_json.exists():
        raise FileNotFoundError("Baseline artifacts missing. Run `python script/run_phase1.py` first.")

    baseline_metrics = read_json(paths.baseline_metrics)
    baseline_df = load_clean_json(paths.clean_json)

    # 1. Corrupt the clean dataset
    corrupted_df = corrupt_clean_dataframe(baseline_df, paths.corruption_log)
    save_clean_artifacts(corrupted_df, paths.corrupted_clean_csv, paths.corrupted_clean_json)
    print(f"[1/5] Corruption: {len(baseline_df)} -> {len(corrupted_df)} rows, log -> {paths.corruption_log}")

    # 2. Observability signals on corrupted data
    corrupted_quality = run_data_quality_checks(corrupted_df, settings, "corrupted")
    corrupted_freshness = build_freshness_report(
        corrupted_df, settings, paths.quality_dir / "corrupted_freshness_report.json"
    )
    gate_failed = not corrupted_quality.get("success") or not corrupted_freshness.get("is_fresh")
    print(
        f"[2/5] Corrupted quality success={corrupted_quality.get('success')} "
        f"| is_fresh={corrupted_freshness.get('is_fresh')}"
    )
    if not gate_failed:
        print("WARNING: quality gate did not detect the corruption - check the expectations.")

    # 3. Silent failure: index the corrupted data anyway (bypassing the gate) and measure impact
    corrupted_index = LocalEmbeddingIndex.build(corrupted_df, settings, paths.corrupted_embeddings_json)
    corrupted_bundle = evaluate_pipeline(
        settings, corrupted_index, paths.eval_testset, paths.corrupted_metrics, paths.corrupted_answers
    )
    print(f"[3/5] Corrupted collection '{corrupted_index.collection_name}' evaluated")

    # 4. Idempotent repair: rebuild from immutable raw records, never patch the corrupted rows
    print("[4/5] Gate failed -> auto-repair from raw snapshot" if gate_failed else "[4/5] Repair from raw snapshot")
    records = load_raw_records(paths.raw_records_json)
    repaired_df = build_clean_dataframe(records, now_utc())
    save_clean_artifacts(repaired_df, paths.repaired_clean_csv, paths.repaired_clean_json)
    repaired_quality = run_data_quality_checks(repaired_df, settings, "repaired")
    repaired_freshness = build_freshness_report(
        repaired_df, settings, paths.quality_dir / "repaired_freshness_report.json"
    )
    enforce_quality_gate(repaired_quality, "repaired")
    print(
        f"      Repaired {len(repaired_df)} rows | quality success={repaired_quality.get('success')} "
        f"| is_fresh={repaired_freshness.get('is_fresh')} | identical to baseline={_same_dataset(repaired_df, baseline_df)}"
    )

    repaired_index = LocalEmbeddingIndex.build(repaired_df, settings, paths.repaired_embeddings_json)
    repaired_bundle = evaluate_pipeline(
        settings, repaired_index, paths.eval_testset, paths.repaired_metrics, paths.repaired_answers
    )

    # 5. Three-state comparison
    generate_corruption_report(
        paths.comparison_report,
        baseline_metrics,
        corrupted_bundle.summary,
        repaired_bundle.summary,
        corrupted_quality,
        repaired_quality,
        corrupted_freshness,
        repaired_freshness,
    )
    print(f"[5/5] Comparison report -> {paths.comparison_report}")
    print(f"      Dashboard -> {build_dashboard(settings)}\n")
    _print_comparison(baseline_metrics, corrupted_bundle.summary, repaired_bundle.summary)
