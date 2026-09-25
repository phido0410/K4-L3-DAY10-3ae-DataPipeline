# Phase 1 Report - Baseline Pipeline

_Generated at 2026-09-25T08:42:22+00:00_

## 1. Source Summary

| Field | Value |
| --- | --- |
| source_api | Crossref REST API |
| source_query | agentic retrieval augmented generation large language model |
| source_filter | from-pub-date:2026-03-29,has-abstract:true |
| mode | offline snapshot |
| raw_records | 24 |
| clean_rows | 24 |
| run_date | 2026-09-25T08:41:38.358689+00:00 |
| embedding_model | sentence-transformers/all-MiniLM-L6-v2 |
| collection | papers-baseline |
| top_k | 4 |
| llm_provider | openai |
| llm_model | gpt-4o-mini |

## 2. Retrieval & Answer Quality

| Metric | Value |
| --- | --- |
| Samples | 10 |
| Retrieval Hit Rate | 100.00% |
| Mean Token F1 | 100.00% |
| LLM Judge Accuracy | 100.00% |
| Mean Judge Score (1-5) | 5 |

- Ragas: Set RUN_RAGAS=1 to enable the slower Ragas pass.

## 3. Data Quality Gate (Great Expectations 1.x)

- Overall status: **PASS**
- Expectations passed: 6/6
- Failed expectations: -

| Expectation | Column | Status | Observed |
| --- | --- | --- | --- |
| `expect_table_row_count_to_be_between` | n/a | PASS | 24 |
| `expect_column_values_to_not_be_null` | paper_id | PASS | 0 unexpected / 24 |
| `expect_column_values_to_be_unique` | paper_id | PASS | 0 unexpected / 24 |
| `expect_column_values_to_not_be_null` | title | PASS | 0 unexpected / 24 |
| `expect_column_values_to_not_be_null` | text_for_embedding | PASS | 0 unexpected / 24 |
| `expect_column_value_lengths_to_be_between` | summary | PASS | 0 unexpected / 24 |

## 4. Freshness SLA

Threshold: `age_days > 180` is stale; data is fresh when stale ratio <= 25.00%.

| Field | Value |
| --- | --- |
| Latest published | 2026-07-22 |
| Oldest published | 2026-03-28 |
| Total rows | 24 |
| Stale rows | 1 |
| Stale ratio | 4.17% |
| Is fresh | PASS |
