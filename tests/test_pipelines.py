from __future__ import annotations

import pytest

import observability.dashboard as dashboard
import pipelines.corruption_flow as corruption_flow
import pipelines.phase1 as phase1
from core.config import load_settings
from core.utils import read_json


@pytest.fixture
def run_in_project(project_dir, monkeypatch):
    """Point every entrypoint at the isolated project copy."""
    for module in (phase1, corruption_flow, dashboard):
        monkeypatch.setattr(module, "load_settings", lambda: load_settings(project_dir))
    return load_settings(project_dir)


def test_end_to_end_baseline_corruption_and_repair(run_in_project, capsys):
    settings = run_in_project
    paths = settings.paths

    phase1.main()
    baseline = read_json(paths.baseline_metrics)
    assert baseline["retrieval_hit_rate"] == 1.0 and baseline["mean_token_f1"] == 1.0
    assert read_json(paths.baseline_quality_report)["success"] is True
    assert "Baseline Pipeline" in paths.baseline_report.read_text(encoding="utf-8")

    corruption_flow.main()
    corrupted = read_json(paths.corrupted_metrics)
    repaired = read_json(paths.repaired_metrics)
    assert corrupted["mean_token_f1"] < baseline["mean_token_f1"]
    assert corrupted["retrieval_hit_rate"] < baseline["retrieval_hit_rate"]
    for key in ("retrieval_hit_rate", "mean_token_f1"):
        assert repaired[key] == baseline[key]
    assert read_json(paths.corrupted_quality_report)["success"] is False
    assert read_json(paths.quality_dir / "repaired_quality_report.json")["success"] is True
    assert read_json(paths.quality_dir / "corrupted_freshness_report.json")["is_fresh"] is False

    output = capsys.readouterr().out
    assert "Gate failed -> auto-repair" in output
    assert "identical to baseline=True" in output
    report = paths.comparison_report.read_text(encoding="utf-8")
    assert "Baseline | Corrupted | Repaired" in report

    html = (paths.project_dir / "data" / "reports" / "dashboard.html").read_text(encoding="utf-8")
    for marker in ("Data Observability Dashboard", "Corrupted", "drop_latest_records", "eval_010", "SLA 180"):
        assert marker in html

    # Idempotent repair: a second run reproduces identical metrics.
    corruption_flow.main()
    assert read_json(paths.repaired_metrics) == repaired
    assert read_json(paths.corrupted_metrics)["mean_token_f1"] == corrupted["mean_token_f1"]


def test_corruption_flow_requires_baseline(run_in_project):
    with pytest.raises(FileNotFoundError, match="run_phase1"):
        corruption_flow.main()


def test_quality_gate_blocks_indexing():
    phase1.enforce_quality_gate({"success": True}, "ok")
    with pytest.raises(RuntimeError, match="refusing to index"):
        phase1.enforce_quality_gate({"success": False}, "baseline")


def test_test_set_is_reused_unless_refresh(run_in_project, clean_df):
    settings = run_in_project
    committed = read_json(settings.paths.eval_testset)
    assert phase1.load_or_build_test_set(clean_df, settings) == committed
    settings.paths.eval_testset.unlink()
    rebuilt = phase1.load_or_build_test_set(clean_df, settings)
    assert len(rebuilt) == 10 and settings.paths.eval_testset.exists()


def test_agent_demo_paths(run_in_project, monkeypatch, capsys):
    from dataclasses import replace

    import retrieval.agent as agent_module

    settings = run_in_project
    test_set = read_json(settings.paths.eval_testset)
    phase1._run_agent_demo(settings, index=None, test_set=test_set)
    assert "skipped (LLM_PROVIDER=mock)" in capsys.readouterr().out

    live = replace(settings, llm_provider="openai")
    phase1._run_agent_demo(live, index=None, test_set=test_set)
    assert "Agent demo skipped" in capsys.readouterr().out

    monkeypatch.setattr(agent_module, "build_agent", lambda settings, index: "agent")
    monkeypatch.setattr(agent_module, "run_agent_question", lambda agent, question: "answer")
    phase1._run_agent_demo(live, index=None, test_set=test_set)
    assert read_json(settings.paths.demo_answers)[0]["answer"] == "answer"


def test_dashboard_without_artifacts(run_in_project, capsys):
    dashboard.main()
    html = (run_in_project.paths.project_dir / "data" / "reports" / "dashboard.html").read_text(encoding="utf-8")
    assert "chưa chạy" in html and "Chưa có corruption log" in html
    assert "Dashboard ->" in capsys.readouterr().out
