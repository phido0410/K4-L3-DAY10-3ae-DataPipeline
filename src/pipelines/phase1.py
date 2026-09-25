from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from core.config import Settings, load_settings, normalized_provider
from core.utils import now_utc, read_json, write_csv, write_json
from evaluation.metrics import evaluate_pipeline
from evaluation.testset import build_test_set
from ingestion.cleaning import build_clean_dataframe
from ingestion.crossref import fetch_source_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_phase1_report
from retrieval.index import LocalEmbeddingIndex

METRIC_KEYS = ["retrieval_hit_rate", "mean_token_f1", "judge_accuracy", "mean_judge_score"]


def save_clean_artifacts(df: pd.DataFrame, csv_path: Path, json_path: Path) -> None:
    write_csv(df, csv_path)
    write_json(json_path, df.to_dict(orient="records"))


def load_clean_json(path: Path) -> pd.DataFrame:
    # Build from records instead of pd.read_json to keep dtypes (dates as str, lists as list).
    return pd.DataFrame(read_json(path))


def enforce_quality_gate(quality: dict[str, Any], stage: str) -> None:
    if not quality.get("success"):
        raise RuntimeError(
            f"[{stage}] Data quality gate FAILED - refusing to index this data. "
            "Inspect data/quality/ for the failing expectations."
        )


def load_or_build_test_set(df: pd.DataFrame, settings: Settings) -> list[dict[str, Any]]:
    path = settings.paths.eval_testset
    if path.exists() and not settings.refresh_test_set:
        return read_json(path)
    return build_test_set(df, path)


def _run_agent_demo(settings: Settings, index: LocalEmbeddingIndex, test_set: list[dict[str, Any]]) -> None:
    if normalized_provider(settings) == "mock":
        print("Agent demo skipped (LLM_PROVIDER=mock).")
        return
    try:
        from retrieval.agent import build_agent, run_agent_question

        agent = build_agent(settings, index)
        demo = [
            {"question": item["question"], "answer": run_agent_question(agent, item["question"])}
            for item in test_set[:2]
        ]
        write_json(settings.paths.demo_answers, demo)
        print(f"Agent demo answers -> {settings.paths.demo_answers}")
    except Exception as exc:  # demo is optional, never fail the baseline on it
        print(f"Agent demo skipped: {exc}")


def main() -> None:
    settings = load_settings()
    paths = settings.paths

    # 1. Ingestion (live API or offline snapshot fallback)
    records = fetch_source_records(settings)
    print(f"[1/7] Ingestion: {len(records)} raw records")

    # 2. Cleaning
    run_date = now_utc()
    df = build_clean_dataframe(records, run_date)
    save_clean_artifacts(df, paths.clean_csv, paths.clean_json)
    print(f"[2/7] Cleaning: {len(df)} clean rows -> {paths.clean_csv}")

    # 3. Quality gate + freshness (gate blocks indexing on failure)
    quality = run_data_quality_checks(df, settings, "baseline")
    freshness = build_freshness_report(df, settings, paths.freshness_report)
    print(f"[3/7] Quality gate success={quality.get('success')} | is_fresh={freshness.get('is_fresh')}")
    enforce_quality_gate(quality, "baseline")

    # 4. Embedding + Chroma index
    index = LocalEmbeddingIndex.build(df, settings, paths.embeddings_json)
    print(f"[4/7] Indexed {len(index.documents)} docs into collection '{index.collection_name}'")

    # 5. Evaluation set
    test_set = load_or_build_test_set(df, settings)
    print(f"[5/7] Test set: {len(test_set)} questions -> {paths.eval_testset}")

    # 6. Baseline evaluation
    bundle = evaluate_pipeline(settings, index, paths.eval_testset, paths.baseline_metrics, paths.baseline_answers)
    print("[6/7] Baseline metrics: " + ", ".join(f"{key}={bundle.summary[key]:.3f}" for key in METRIC_KEYS))

    # 7. Report
    source_summary = {
        "source_api": settings.source_api,
        "source_query": settings.source_query,
        "source_filter": settings.source_filter,
        "mode": "live API" if settings.refresh_source else "offline snapshot",
        "raw_records": len(records),
        "clean_rows": len(df),
        "run_date": run_date.isoformat(),
        "embedding_model": settings.embedding_model,
        "collection": index.collection_name,
        "top_k": settings.top_k,
        "llm_provider": settings.llm_provider,
        "llm_model": settings.model_name,
    }
    generate_phase1_report(paths.baseline_report, source_summary, bundle.summary, quality, freshness)
    print(f"[7/7] Report -> {paths.baseline_report}")

    _run_agent_demo(settings, index, test_set)
