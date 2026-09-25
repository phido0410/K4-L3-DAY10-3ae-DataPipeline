from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from core.utils import first_sentence, normalize_whitespace, write_json

TEST_SET_SIZE = 10
MIN_DOCUMENTS = 4
# 3 summary / 3 authors / 2 date / 2 categories, xen ke de moi loai trai deu tren corpus.
QUESTION_TYPES = ["summary", "authors", "date", "categories"]

# Keyword phai khop voi `retrieval/qa.py::_extract_answer`; title nam trong nhay don de lookup chinh xac.
QUESTION_TEMPLATES = {
    "summary": "What is the main finding of the paper '{title}'?",
    "authors": "Who authored the paper '{title}'?",
    "date": "When was the paper '{title}' published?",
    "categories": "What categories does the paper '{title}' belong to?",
}


def _ground_truth(row: pd.Series, question_type: str) -> str:
    if question_type == "authors":
        return str(row["authors_joined"])
    if question_type == "date":
        return str(row["published"])
    if question_type == "categories":
        return str(row["categories_joined"])
    return first_sentence(str(row["summary"]))


def _candidate_papers(df: pd.DataFrame) -> pd.DataFrame:
    required = ["paper_id", "title", "summary", "authors_joined", "categories_joined", "published"]
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(f"Clean dataframe is missing columns required for the test set: {missing}")

    candidates = df.dropna(subset=required).drop_duplicates(subset="paper_id")
    for column in required:
        candidates = candidates[candidates[column].astype(str).str.strip() != ""]
    # Nhay don trong title se lam hong regex lookup `'([^']+)'` cua QA.
    candidates = candidates[~candidates["title"].astype(str).str.contains("'")]
    return candidates.sort_values("paper_id").reset_index(drop=True)


def build_test_set(df: pd.DataFrame, output_path) -> list[dict[str, Any]]:
    """Sinh 10 cau hoi benchmark (summary/authors/date/categories) tu clean dataframe.

    Chon paper cach deu nhau tren corpus (sort theo `paper_id` de ket qua on dinh),
    moi cau mot paper khac nhau khi corpus du lon.
    """
    candidates = _candidate_papers(df)
    if len(candidates) < MIN_DOCUMENTS:
        raise ValueError(f"Need at least {MIN_DOCUMENTS} valid papers to build a test set, got {len(candidates)}.")

    step = len(candidates) / TEST_SET_SIZE
    test_set: list[dict[str, Any]] = []
    for position in range(TEST_SET_SIZE):
        row = candidates.iloc[int(position * step) % len(candidates)]
        question_type = QUESTION_TYPES[position % len(QUESTION_TYPES)]
        title = normalize_whitespace(str(row["title"]))
        test_set.append(
            {
                "id": f"eval_{position + 1:03d}",
                "question_type": question_type,
                "question": QUESTION_TEMPLATES[question_type].format(title=title),
                "ground_truth": _ground_truth(row, question_type),
                "ground_truth_doc_ids": [str(row["paper_id"])],
            }
        )

    write_json(Path(output_path), test_set)
    return test_set
