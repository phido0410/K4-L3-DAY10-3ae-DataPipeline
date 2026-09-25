from __future__ import annotations

import io
import json
from dataclasses import replace
from datetime import date
from urllib.error import HTTPError, URLError

import pytest

import ingestion.crossref as crossref
from core.utils import read_json
from ingestion.cleaning import build_clean_dataframe
from ingestion.crossref import fetch_source_records, load_raw_records, parse_crossref_payload
from conftest import RUN_DATE


def _item(**overrides):
    item = {
        "DOI": "10.1/abc",
        "title": ["  A   Title "],
        "abstract": "<jats:p>An abstract that is clearly long enough to be kept.</jats:p>",
        "author": [{"given": "Ada", "family": "Lovelace"}, {"name": "Consortium"}, "Plain Name"],
        "subject": ["AI", {"name": "IR"}],
        "published": {"date-parts": [[2026, 5]]},
        "updated": {"date-parts": [[2026, 6, 2]]},
        "link": [{"content-type": "application/pdf", "URL": "https://x/p.pdf"}],
    }
    item.update(overrides)
    return item


def test_parse_snapshot_matches_records(settings):
    payload = read_json(settings.paths.raw_api_response)
    records = parse_crossref_payload(payload)
    assert len(records) == 24
    assert records == load_raw_records(settings.paths.raw_records_json)
    assert all("<" not in r.summary for r in records)


def test_parse_normalizes_fields():
    [record] = parse_crossref_payload({"message": {"items": [_item()]}})
    assert record.title == "A Title"
    assert record.summary.startswith("An abstract")
    assert record.authors == ["Ada Lovelace", "Consortium", "Plain Name"]
    assert record.categories == ["AI", "IR"] and record.primary_category == "AI"
    assert record.published == "2026-05-01" and record.updated == "2026-06-02"
    assert record.pdf_url == "https://x/p.pdf"


@pytest.mark.parametrize(
    "overrides",
    [{"DOI": ""}, {"title": []}, {"abstract": ""}, {"abstract": 42}],
)
def test_parse_skips_invalid_items(overrides):
    assert parse_crossref_payload({"message": {"items": [_item(**overrides), "junk"]}}) == []


def test_parse_accepts_list_and_items_payloads_and_date_fallbacks():
    item = _item(published={}, issued={}, created={"date-time": "2026-02-03T00:00:00Z"}, subject="Single")
    assert parse_crossref_payload([item])[0].published == "2026-02-03"
    assert parse_crossref_payload({"items": [item]})[0].categories == ["Single"]
    no_date = _item(published={"date-parts": [["x"]]}, subject=[])
    record = parse_crossref_payload([no_date])[0]
    assert record.published == "2026-01-01" and record.primary_category == "General"
    assert parse_crossref_payload("nonsense") == []


def test_load_raw_records_rejects_non_list(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"not": "a list"}))
    with pytest.raises(ValueError):
        load_raw_records(path)


def test_fetch_offline_uses_records_snapshot(settings):
    assert len(fetch_source_records(settings)) == 24


def test_fetch_offline_rebuilds_records_from_response(settings):
    settings.paths.raw_records_json.unlink()
    assert len(fetch_source_records(settings)) == 24
    assert settings.paths.raw_records_json.exists()


def test_fetch_offline_without_snapshot_fails(settings):
    settings.paths.raw_records_json.unlink()
    settings.paths.raw_api_response.unlink()
    with pytest.raises(FileNotFoundError):
        fetch_source_records(settings)


class _Response(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_fetch_live_success_saves_raw(settings, monkeypatch):
    live = replace(settings, refresh_source=True)
    payload = {"message": {"items": [_item()]}}
    monkeypatch.setattr(crossref, "urlopen", lambda *a, **k: _Response(json.dumps(payload).encode()))
    records = fetch_source_records(live)
    assert [r.paper_id for r in records] == ["10.1/abc"]
    assert read_json(live.paths.raw_api_response) == payload


@pytest.mark.parametrize(
    "error",
    [
        HTTPError("u", 429, "Too Many Requests", None, None),
        HTTPError("u", 404, "Not Found", None, None),
        URLError("offline"),
        RuntimeError("boom"),
    ],
)
def test_fetch_live_failure_falls_back_to_snapshot(settings, monkeypatch, error):
    live = replace(settings, refresh_source=True)

    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(crossref, "urlopen", fail)
    monkeypatch.setattr(crossref.time, "sleep", lambda s: None)
    assert len(fetch_source_records(live)) == 24


def test_fetch_live_failure_rebuilds_from_response_or_raises(settings, monkeypatch):
    live = replace(settings, refresh_source=True)
    monkeypatch.setattr(crossref, "urlopen", lambda *a, **k: (_ for _ in ()).throw(URLError("offline")))
    monkeypatch.setattr(crossref.time, "sleep", lambda s: None)
    settings.paths.raw_records_json.unlink()
    assert len(fetch_source_records(live)) == 24
    settings.paths.raw_records_json.unlink()
    settings.paths.raw_api_response.unlink()
    with pytest.raises(RuntimeError):
        fetch_source_records(live)


def test_clean_dataframe_contract(clean_df):
    assert len(clean_df) == 24
    assert clean_df["paper_id"].is_unique
    assert (clean_df["summary_chars"] >= 30).all()
    assert clean_df["published"].is_monotonic_decreasing
    first = clean_df.iloc[0]
    assert first["text_for_embedding"].splitlines()[0] == f"Title: {first['title']}"
    assert [line.split(":")[0] for line in first["text_for_embedding"].splitlines()] == [
        "Title", "Authors", "Published", "Categories", "Summary",
    ]
    assert first["age_days"] == (RUN_DATE.date() - date.fromisoformat(first["published"])).days


def test_clean_dataframe_filters_and_dedupes(raw_records):
    base = raw_records[0]
    messy = [
        replace(base, title=f"  {base.title}\n"),
        base,
        replace(raw_records[1], summary="<jats:p>short</jats:p>"),
        replace(raw_records[2], paper_id=" "),
        replace(raw_records[3], title=""),
        replace(raw_records[4], summary=""),
        replace(raw_records[5], published="garbage", updated="bad", primary_category=""),
    ]
    df = build_clean_dataframe(messy, RUN_DATE)
    assert list(df["paper_id"]) == [base.paper_id, raw_records[5].paper_id]  # sorted by published desc
    assert df.iloc[0]["title"] == base.title
    fallback = df.set_index("paper_id").loc[raw_records[5].paper_id]
    assert fallback["published"] == "2026-01-01" and fallback["updated"] == "2026-01-01"


def test_clean_dataframe_empty_input_keeps_schema():
    df = build_clean_dataframe([], RUN_DATE)
    assert df.empty and "text_for_embedding" in df.columns
