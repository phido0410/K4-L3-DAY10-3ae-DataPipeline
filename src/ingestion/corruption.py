from __future__ import annotations

import math
import random
from typing import Any

import pandas as pd

from core.utils import compact_join, normalize_whitespace, now_utc, write_json

SEED = 42
DROP_LATEST_RATIO = 0.2
BLANK_SUMMARY_ROWS = 3
NOISE_ROWS = 3
TRUNCATE_TITLE_ROWS = 3
TRUNCATED_TITLE_LENGTH = 6
STALE_ROWS_RATIO = 0.4
STALE_SHIFT_DAYS = 365
DUPLICATE_ROWS = 3
NOISE_TOKENS = ["@@##", "lorem", "��", "NaN", "<<<>>>", "zzkq", "0xDEADBEEF", "%%%"]


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str) and value:
        return [part.strip() for part in value.split(",") if part.strip()]
    return []


def _rebuild_derived_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["authors_joined"] = df["authors"].map(lambda items: compact_join(_as_list(items)))
    df["categories_joined"] = df["categories"].map(lambda items: compact_join(_as_list(items)))
    df["summary_chars"] = df["summary"].fillna("").map(len).astype(int)
    df["text_for_embedding"] = (
        "Title: " + df["title"].fillna("")
        + "\nAuthors: " + df["authors_joined"]
        + "\nPublished: " + df["published"].fillna("")
        + "\nCategories: " + df["categories_joined"]
        + "\nSummary: " + df["summary"].fillna("")
    )
    return df


def _log_entry(corruption_type: str, description: str, paper_ids: list[str], **details: Any) -> dict[str, Any]:
    return {
        "type": corruption_type,
        "description": description,
        "affected_rows": len(paper_ids),
        "affected_paper_ids": paper_ids,
        **details,
    }


def corrupt_clean_dataframe(df: pd.DataFrame, output_log_path) -> pd.DataFrame:
    """Simulate 6 production data incidents on a clean dataframe.

    Every corruption is deterministic (fixed seed) and hits a disjoint set of rows,
    so each incident can be traced back through the corruption log.
    """
    rng = random.Random(SEED)
    corrupted = df.copy().reset_index(drop=True)
    corrupted["published"] = pd.to_datetime(corrupted["published"]).dt.strftime("%Y-%m-%d")
    rows_before = len(corrupted)
    log: list[dict[str, Any]] = []

    # 1. Drop latest records: newest papers never reach the index (stale knowledge).
    drop_count = math.ceil(len(corrupted) * DROP_LATEST_RATIO)
    latest = corrupted.sort_values(["published", "paper_id"], ascending=[False, True]).head(drop_count)
    corrupted = corrupted.drop(index=latest.index).reset_index(drop=True)
    log.append(
        _log_entry(
            "drop_latest_records",
            f"Dropped the {drop_count} most recently published papers ({DROP_LATEST_RATIO:.0%}).",
            latest["paper_id"].tolist(),
        )
    )

    # Disjoint row pools for the in-place corruptions.
    pool = list(corrupted.index)
    rng.shuffle(pool)
    stale_count = math.ceil(len(corrupted) * STALE_ROWS_RATIO)
    blank_idx = pool[:BLANK_SUMMARY_ROWS]
    noise_idx = pool[BLANK_SUMMARY_ROWS : BLANK_SUMMARY_ROWS + NOISE_ROWS]
    offset = BLANK_SUMMARY_ROWS + NOISE_ROWS
    truncate_idx = pool[offset : offset + TRUNCATE_TITLE_ROWS]
    offset += TRUNCATE_TITLE_ROWS
    stale_idx = pool[offset : offset + stale_count]

    # 2. Blank summary: scraper returned an empty abstract.
    corrupted.loc[blank_idx, "summary"] = ""
    log.append(
        _log_entry(
            "blank_summary",
            "Replaced summary with an empty string.",
            corrupted.loc[blank_idx, "paper_id"].tolist(),
        )
    )

    # 3. Inject noise: garbage tokens interleaved into the summary.
    for idx in noise_idx:
        words = normalize_whitespace(corrupted.at[idx, "summary"]).split()
        noisy: list[str] = []
        for word in words:
            noisy.append(word)
            if rng.random() < 0.5:
                noisy.append(rng.choice(NOISE_TOKENS))
        corrupted.at[idx, "summary"] = " ".join(noisy)
    log.append(
        _log_entry(
            "inject_noise",
            "Inserted garbage tokens after ~50% of the words in the summary.",
            corrupted.loc[noise_idx, "paper_id"].tolist(),
        )
    )

    # 4. Truncate title below 8 characters.
    original_titles = corrupted.loc[truncate_idx, "title"].tolist()
    corrupted.loc[truncate_idx, "title"] = corrupted.loc[truncate_idx, "title"].str[:TRUNCATED_TITLE_LENGTH]
    log.append(
        _log_entry(
            "truncate_title",
            f"Truncated title to {TRUNCATED_TITLE_LENGTH} characters.",
            corrupted.loc[truncate_idx, "paper_id"].tolist(),
            original_titles=original_titles,
        )
    )

    # 5. Stale date: published date shifted back one year, age_days follows.
    shifted = pd.to_datetime(corrupted.loc[stale_idx, "published"]) - pd.Timedelta(days=STALE_SHIFT_DAYS)
    corrupted.loc[stale_idx, "published"] = shifted.dt.strftime("%Y-%m-%d")
    corrupted.loc[stale_idx, "age_days"] = corrupted.loc[stale_idx, "age_days"].astype(int) + STALE_SHIFT_DAYS
    log.append(
        _log_entry(
            "stale_date",
            f"Shifted published date back {STALE_SHIFT_DAYS} days on {STALE_ROWS_RATIO:.0%} of remaining rows.",
            corrupted.loc[stale_idx, "paper_id"].tolist(),
        )
    )

    # 6. Duplicate rows: the same paper ingested twice.
    duplicate_idx = sorted(rng.sample(list(corrupted.index), DUPLICATE_ROWS))
    duplicates = corrupted.loc[duplicate_idx]
    corrupted = pd.concat([corrupted, duplicates], ignore_index=True)
    log.append(
        _log_entry(
            "duplicate_rows",
            "Appended exact copies of existing rows (paper_id no longer unique).",
            duplicates["paper_id"].tolist(),
        )
    )

    corrupted = _rebuild_derived_columns(corrupted)
    corrupted["age_days"] = corrupted["age_days"].astype(int)

    write_json(
        output_log_path,
        {
            "generated_at": now_utc().isoformat(),
            "seed": SEED,
            "rows_before": rows_before,
            "rows_after": len(corrupted),
            "corruptions": log,
        },
    )
    return corrupted
