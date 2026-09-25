from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from core.config import Settings, load_settings
from ingestion.cleaning import build_clean_dataframe
from ingestion.crossref import PaperRecord, load_raw_records

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_DATE = datetime(2026, 9, 25, tzinfo=UTC)


@pytest.fixture
def project_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolated copy of the inputs so tests never overwrite the submitted artifacts."""
    for sub in ("raw", "eval"):
        shutil.copytree(REPO_ROOT / "data" / sub, tmp_path / "data" / sub)
    for name in ("LLM_PROVIDER", "LLM_MODEL", "REFRESH_SOURCE", "REFRESH_TEST_SET", "RUN_RAGAS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    return tmp_path


@pytest.fixture
def settings(project_dir: Path) -> Settings:
    return load_settings(project_dir)


@pytest.fixture
def raw_records(settings: Settings) -> list[PaperRecord]:
    return load_raw_records(settings.paths.raw_records_json)


@pytest.fixture
def clean_df(raw_records: list[PaperRecord]) -> pd.DataFrame:
    return build_clean_dataframe(raw_records, RUN_DATE)
