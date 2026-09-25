from __future__ import annotations

import sys
import types

import pytest

import evaluation.metrics as metrics
import retrieval.agent as agent_module
from core.config import load_settings, normalized_provider, require_llm_credentials
from core.utils import compact_join, first_sentence, normalize_whitespace, safe_slug
from retrieval.index import LocalEmbeddingIndex
from retrieval.llm import build_llm
from retrieval.qa import answer_question


def test_utils():
    assert normalize_whitespace("  a \n b ") == "a b"
    assert safe_slug("Hello, World!") == "hello-world" and safe_slug("!!!") == "item"
    assert compact_join(["a", "", "b"]) == "a, b"
    assert first_sentence("One. Two!") == "One."


def test_settings_paths_are_relative_to_project(settings, project_dir):
    assert settings.paths.project_dir == project_dir.resolve()
    assert settings.paths.clean_json.is_relative_to(project_dir.resolve())
    assert settings.llm_provider == "mock" and settings.top_k == 4


@pytest.mark.parametrize(
    ("provider", "key_env", "normalized"),
    [
        ("gemini", "GOOGLE_API_KEY", "gemini"),
        ("OpenAI", "OPENAI_API_KEY", "openai"),
        ("anthorpic", "ANTHROPIC_API_KEY", "anthropic"),
        ("open-router", "OPENROUTER_API_KEY", "openrouter"),
        ("custom llm", "CUSTOM_LLM_BASE_URL", "custom"),
    ],
)
def test_provider_credentials_and_clients(project_dir, monkeypatch, provider, key_env, normalized):
    monkeypatch.setenv("LLM_PROVIDER", provider)
    for env in ("GOOGLE_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "CUSTOM_LLM_BASE_URL"):
        monkeypatch.delenv(env, raising=False)
    settings = load_settings(project_dir)
    assert normalized_provider(settings) == normalized
    with pytest.raises(RuntimeError, match="required"):
        require_llm_credentials(settings)

    monkeypatch.setenv(key_env, "http://localhost:1" if key_env == "CUSTOM_LLM_BASE_URL" else "test-key")
    monkeypatch.setenv("LLM_MODEL", "some-model")
    settings = load_settings(project_dir)
    require_llm_credentials(settings)
    assert build_llm(settings) is not None


def test_local_providers_and_unknown_provider(project_dir, monkeypatch):
    for provider in ("ollama", "mock"):
        monkeypatch.setenv("LLM_PROVIDER", provider)
        assert build_llm(load_settings(project_dir)) is not None
    monkeypatch.setenv("LLM_PROVIDER", "nope")
    with pytest.raises(RuntimeError, match="Unsupported"):
        require_llm_credentials(load_settings(project_dir))


@pytest.fixture
def index(clean_df, settings):
    return LocalEmbeddingIndex.build(clean_df, settings, settings.paths.embeddings_json)


def test_index_build_search_lookup_and_load(index, clean_df, settings):
    assert index.collection_name == "papers-baseline"
    title = clean_df.iloc[0]["title"]
    top = index.search(title, top_k=2)
    assert len(top) == 2 and clean_df.iloc[0]["paper_id"] in {r.paper_id for r in top}  # near-duplicate papers exist
    assert index.lookup(title.upper())["paper_id"] == clean_df.iloc[0]["paper_id"]
    assert index.lookup(clean_df.iloc[1]["paper_id"]) is not None
    assert index.lookup("unknown") is None
    reloaded = LocalEmbeddingIndex.load(settings)
    assert len(reloaded.documents) == 24


def test_index_collection_names(clean_df, settings, tmp_path):
    assert LocalEmbeddingIndex._derive_collection_name(settings, None) == "papers-baseline"
    corrupted = LocalEmbeddingIndex._derive_collection_name(settings, settings.paths.corrupted_embeddings_json)
    assert corrupted == "papers-corrupted"
    assert LocalEmbeddingIndex._derive_collection_name(settings, tmp_path / "My Index.json") == "my-index"


def test_answer_question_routes_by_keyword(index, clean_df):
    row = clean_df.iloc[3]
    cases = {
        f"Who authored the paper '{row['title']}'?": row["authors_joined"],
        f"When was the paper '{row['title']}' published?": row["published"],
        f"What categories does the paper '{row['title']}' belong to?": row["categories_joined"],
        f"What is the main finding of the paper '{row['title']}'?": first_sentence(row["summary"]),
    }
    for question, expected in cases.items():
        result = answer_question(question, settings=index.settings, index=index)
        assert result.answer == expected
        assert result.retrieved_doc_ids[0] == row["paper_id"]
    fuzzy = answer_question("dense retrieval ghost vectors", settings=index.settings, index=index, top_k=2)
    assert len(fuzzy.retrieved_doc_ids) == 2


def test_evaluate_pipeline_with_ragas_stub(index, settings, monkeypatch):
    fake_ragas = types.ModuleType("ragas")
    fake_ragas.evaluate = lambda dataset, **kwargs: {"faithfulness": 1.0, "rows": len(dataset)}
    fake_metrics = types.ModuleType("ragas.metrics")
    for name in ("answer_relevancy", "context_precision", "context_recall", "faithfulness"):
        setattr(fake_metrics, name, object())
    monkeypatch.setitem(sys.modules, "ragas", fake_ragas)
    monkeypatch.setitem(sys.modules, "ragas.metrics", fake_metrics)
    monkeypatch.setenv("RUN_RAGAS", "1")

    bundle = metrics.evaluate_pipeline(
        settings, index, settings.paths.eval_testset, settings.paths.baseline_metrics, settings.paths.baseline_answers
    )
    assert bundle.summary["retrieval_hit_rate"] == 1.0
    assert bundle.summary["ragas"] == {"faithfulness": 1.0, "rows": 10}
    assert "Fallback heuristic" in bundle.answers[0]["judge"]["reasoning"]


def test_judge_uses_llm_when_available(settings, monkeypatch):
    verdict = metrics.JudgeVerdict(score=4, correct=True, reasoning="llm")

    class FakeLLM:
        def with_structured_output(self, schema):
            return self

        def invoke(self, prompt):
            return verdict

    monkeypatch.setattr(metrics, "build_llm", lambda **kwargs: FakeLLM())
    assert metrics._judge_answer(settings, "q", "ref", "pred") is verdict
    assert metrics._token_f1("a b", "") == 0.0 and metrics._token_f1("a b", "c d") == 0.0


def test_ragas_failure_is_reported(settings, monkeypatch):
    monkeypatch.setenv("RUN_RAGAS", "1")
    broken = types.ModuleType("ragas")
    monkeypatch.setitem(sys.modules, "ragas", broken)
    result = metrics._run_ragas(settings, [{"question": "q", "answer": "a", "ground_truth": "g", "retrieved_contexts": []}])
    assert "error" in result


def test_agent_tools_and_runner(index, settings, monkeypatch):
    captured = {}

    def fake_create_agent(model, tools, system_prompt, name):
        captured["tools"] = {tool.name: tool for tool in tools}
        return "agent"

    monkeypatch.setattr(agent_module, "create_agent", fake_create_agent)
    assert agent_module.build_agent(settings, index) == "agent"
    search = captured["tools"]["semantic_search_papers"].invoke({"query": "idempotent indexing", "top_k": 2})
    assert search.count("paper_id:") == 2
    title = index.documents[0]["title"]
    assert "paper_id:" in captured["tools"]["lookup_paper"].invoke({"paper_id_or_title": title})
    assert captured["tools"]["lookup_paper"].invoke({"paper_id_or_title": "nope"}) == "No exact paper match found."

    class FakeAgent:
        def __init__(self, messages):
            self.messages = messages

        def invoke(self, payload):
            return {"messages": self.messages}

    final = types.SimpleNamespace(content="final answer")
    assert agent_module.run_agent_question(FakeAgent([final]), "q") == "final answer"
    assert agent_module.run_agent_question(FakeAgent([]), "q") == ""
