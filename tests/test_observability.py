from __future__ import annotations

import pandas as pd
import pytest

from core.utils import first_sentence, read_json
from evaluation.testset import build_test_set
from ingestion.corruption import corrupt_clean_dataframe
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_corruption_report, generate_phase1_report


@pytest.fixture
def corrupted_df(clean_df, settings):
    return corrupt_clean_dataframe(clean_df, settings.paths.corruption_log)


# --- Corruption ---------------------------------------------------------------------------


def test_corruption_applies_all_six_incidents(clean_df, corrupted_df, settings):
    log = read_json(settings.paths.corruption_log)
    counts = {item["type"]: item["affected_rows"] for item in log["corruptions"]}
    assert counts == {
        "drop_latest_records": 5,
        "blank_summary": 3,
        "inject_noise": 3,
        "truncate_title": 3,
        "stale_date": 8,
        "duplicate_rows": 3,
    }
    assert (log["rows_before"], log["rows_after"]) == (24, 22) == (len(clean_df), len(corrupted_df))
    dropped = set(log["corruptions"][0]["affected_paper_ids"])
    assert dropped == set(clean_df.sort_values("published", ascending=False).head(5)["paper_id"])
    assert dropped.isdisjoint(corrupted_df["paper_id"])
    assert corrupted_df["paper_id"].duplicated().sum() == 3
    assert (corrupted_df["summary"] == "").sum() >= 3
    assert (corrupted_df["title"].str.len() < 8).sum() >= 3


def test_corruption_disjoint_rows_and_consistent_derived_columns(clean_df, corrupted_df, settings):
    log = read_json(settings.paths.corruption_log)["corruptions"]
    in_place = [set(item["affected_paper_ids"]) for item in log[1:5]]
    assert sum(len(ids) for ids in in_place) == len(set().union(*in_place))

    before = clean_df.set_index("paper_id")
    for paper_id in log[4]["affected_paper_ids"]:
        row = corrupted_df[corrupted_df["paper_id"] == paper_id].iloc[0]
        assert row["age_days"] == before.loc[paper_id, "age_days"] + 365
        assert f"Published: {row['published']}" in row["text_for_embedding"]
    assert (corrupted_df["summary_chars"] == corrupted_df["summary"].str.len()).all()


def test_corruption_is_deterministic_and_does_not_mutate_input(clean_df, settings):
    snapshot = clean_df.copy()
    first = corrupt_clean_dataframe(clean_df, settings.paths.corruption_log)
    second = corrupt_clean_dataframe(clean_df, settings.paths.corruption_log)
    assert first.equals(second)
    assert clean_df.equals(snapshot)


def test_corruption_handles_string_list_columns(clean_df, settings):
    as_strings = clean_df.assign(authors=clean_df["authors_joined"], categories=None)
    corrupted = corrupt_clean_dataframe(as_strings, settings.paths.corruption_log)
    assert corrupted["authors_joined"].str.len().gt(0).all()
    assert (corrupted["categories_joined"] == "").all()


# --- Quality gate & freshness -------------------------------------------------------------


def test_quality_gate_passes_on_clean_data(clean_df, settings):
    report = run_data_quality_checks(clean_df, settings, "baseline")
    assert report["success"] is True
    assert (report["successful_expectations"], report["evaluated_expectations"]) == (6, 6)
    assert read_json(settings.paths.baseline_quality_report)["success"] is True


def test_quality_gate_fails_on_corrupted_data(corrupted_df, settings):
    report = run_data_quality_checks(corrupted_df, settings, "corrupted")
    assert report["success"] is False
    assert sorted(report["failed_expectations"]) == [
        "expect_column_value_lengths_to_be_between(summary)",
        "expect_column_values_to_be_unique(paper_id)",
    ]
    assert settings.paths.corrupted_quality_report.exists()


def test_quality_gate_reports_missing_columns(settings):
    report = run_data_quality_checks(pd.DataFrame({"paper_id": ["a"] * 6}), settings, "broken")
    assert report["success"] is False
    assert report["freshness_sla"]["stale_rows"] == 0  # no date columns: must not crash


def test_freshness_fresh_vs_stale(clean_df, corrupted_df, settings):
    fresh = build_freshness_report(clean_df, settings, settings.paths.freshness_report)
    assert fresh["is_fresh"] is True and fresh["stale_rows"] == 1
    assert fresh["latest_published"] == "2026-07-22"
    stale = build_freshness_report(corrupted_df, settings, settings.paths.quality_dir / "c.json")
    assert stale["is_fresh"] is False and stale["stale_rows"] == 8


def test_freshness_edge_cases(clean_df, settings):
    empty = build_freshness_report(clean_df.iloc[0:0], settings, settings.paths.quality_dir / "e.json")
    assert empty["is_fresh"] is False and empty["latest_published"] is None
    no_age = build_freshness_report(
        clean_df.drop(columns=["age_days"]), settings, settings.paths.quality_dir / "n.json"
    )
    assert no_age["total_rows"] == 24 and no_age["min_age_days"] is None


# --- Test set -----------------------------------------------------------------------------


def test_test_set_matches_qa_contract(clean_df, settings):
    items = build_test_set(clean_df, settings.paths.eval_testset)
    assert len(items) == 10
    assert sorted({i["question_type"] for i in items}) == ["authors", "categories", "date", "summary"]
    rows = clean_df.set_index("paper_id")
    keywords = {"authors": "who authored", "date": "when was", "categories": "what categories"}
    for item in items:
        row = rows.loc[item["ground_truth_doc_ids"][0]]
        assert f"'{row['title']}'" in item["question"]
        kind = item["question_type"]
        if kind in keywords:
            assert keywords[kind] in item["question"].lower()
        expected = {
            "authors": row["authors_joined"],
            "date": row["published"],
            "categories": row["categories_joined"],
            "summary": first_sentence(row["summary"]),
        }[kind]
        assert item["ground_truth"] == expected
    assert read_json(settings.paths.eval_testset) == items


def test_test_set_validation_errors(clean_df, settings):
    with pytest.raises(ValueError, match="missing columns"):
        build_test_set(clean_df.drop(columns=["summary"]), settings.paths.eval_testset)
    with pytest.raises(ValueError, match="at least"):
        build_test_set(clean_df.head(3), settings.paths.eval_testset)
    quoted = clean_df.assign(title=clean_df["title"] + "'s")
    with pytest.raises(ValueError):
        build_test_set(quoted, settings.paths.eval_testset)


# --- Reporting ----------------------------------------------------------------------------


def _metrics(value, ragas=None):
    return {
        "samples": 10,
        "retrieval_hit_rate": value,
        "mean_token_f1": value,
        "judge_accuracy": value,
        "mean_judge_score": 5 * value,
        "ragas": ragas or {"skipped": "not enabled"},
    }


def test_reports_render_expected_sections(clean_df, corrupted_df, settings):
    quality_ok = run_data_quality_checks(clean_df, settings, "baseline")
    quality_bad = run_data_quality_checks(corrupted_df, settings, "corrupted")
    fresh = build_freshness_report(clean_df, settings, settings.paths.freshness_report)
    stale = build_freshness_report(corrupted_df, settings, settings.paths.quality_dir / "c.json")

    generate_phase1_report(
        settings.paths.baseline_report, {"mode": "offline", "rows": 24}, _metrics(1.0, {"faithfulness": 0.9}),
        quality_ok, fresh,
    )
    phase1 = settings.paths.baseline_report.read_text(encoding="utf-8")
    assert "Great Expectations" in phase1 and "Ragas `faithfulness`" in phase1 and "100.00%" in phase1

    generate_corruption_report(
        settings.paths.comparison_report, _metrics(1.0), _metrics(0.5), _metrics(1.0),
        quality_bad, quality_ok, stale, fresh,
    )
    report = settings.paths.comparison_report.read_text(encoding="utf-8")
    assert "| Metric | Baseline | Corrupted | Repaired |" in report
    assert "-50.0 pp" in report and "chặn được dữ liệu lỗi" in report
    assert "phục hồi về mức baseline" in report


def test_corruption_report_handles_regression_and_missing_values(settings):
    generate_corruption_report(
        settings.paths.comparison_report,
        _metrics(0.5), _metrics(0.7), _metrics(0.6),
        {"success": True}, {"success": True}, {}, {},
    )
    report = settings.paths.comparison_report.read_text(encoding="utf-8")
    assert "tăng từ" in report and "KHÔNG phát hiện" in report and "n/a" in report
    generate_corruption_report(
        settings.paths.comparison_report,
        _metrics(0.5), _metrics(0.5), _metrics(0.5), {}, {}, {}, {},
    )
    assert "không đổi" in settings.paths.comparison_report.read_text(encoding="utf-8")
    generate_corruption_report(
        settings.paths.comparison_report,
        _metrics(0.5), _metrics(0.4), {"samples": None}, {}, {}, {}, {},
    )
    assert "Retrieval Hit Rate**" not in settings.paths.comparison_report.read_text(encoding="utf-8")
