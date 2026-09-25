# Corruption Report - Baseline vs Corrupted vs Repaired

_Generated at 2026-09-25T08:44:43+00:00_

## 1. RAG Metrics

| Metric | Baseline | Corrupted | Repaired | Δ Corrupted | Δ Repaired |
| --- | --- | --- | --- | --- | --- |
| Samples | 10 | 10 | 10 | +0 | +0 |
| Retrieval Hit Rate | 100.00% | 90.00% | 100.00% | -10.0 pp | +0.0 pp |
| Mean Token F1 | 100.00% | 58.21% | 100.00% | -41.8 pp | +0.0 pp |
| LLM Judge Accuracy | 100.00% | 70.00% | 100.00% | -30.0 pp | +0.0 pp |
| Mean Judge Score (1-5) | 5 | 3.8000 | 5 | -1.2000 | +0 |

## 2. Data Quality Gate (Great Expectations 1.x)

| Check | Corrupted | Repaired |
| --- | --- | --- |
| Overall status | FAIL | PASS |
| Row count | 22 | 24 |
| Expectations passed | 4/6 | 6/6 |
| Failed expectations | expect_column_values_to_be_unique(paper_id), expect_column_value_lengths_to_be_between(summary) | - |

### Corrupted - expectation details

| Expectation | Column | Status | Observed |
| --- | --- | --- | --- |
| `expect_table_row_count_to_be_between` | n/a | PASS | 22 |
| `expect_column_values_to_not_be_null` | paper_id | PASS | 0 unexpected / 22 |
| `expect_column_values_to_be_unique` | paper_id | FAIL | 6 unexpected / 22 |
| `expect_column_values_to_not_be_null` | title | PASS | 0 unexpected / 22 |
| `expect_column_values_to_not_be_null` | text_for_embedding | PASS | 0 unexpected / 22 |
| `expect_column_value_lengths_to_be_between` | summary | FAIL | 3 unexpected / 22 |

## 3. Freshness SLA

| Field | Corrupted | Repaired |
| --- | --- | --- |
| Latest published | 2026-06-12 | 2026-07-22 |
| Oldest published | 2025-03-28 | 2026-03-28 |
| Total rows | 22 | 24 |
| Stale rows | 8 | 1 |
| Stale ratio | 36.36% | 4.17% |
| Is fresh | FAIL | PASS |

## 4. Analysis

- **Retrieval Hit Rate**: khi dữ liệu lỗi giảm từ 100.00% xuống 90.00% (-10.0 pp); phục hồi về mức baseline.
- **Mean Token F1**: khi dữ liệu lỗi giảm từ 100.00% xuống 58.21% (-41.8 pp); phục hồi về mức baseline.
- **LLM Judge Accuracy**: khi dữ liệu lỗi giảm từ 100.00% xuống 70.00% (-30.0 pp); phục hồi về mức baseline.
- **Mean Judge Score (1-5)**: khi dữ liệu lỗi giảm từ 5 xuống 3.8000 (-1.2000); phục hồi về mức baseline.
- **Quality Gate** chặn được dữ liệu lỗi (corrupted = FAIL; vi phạm: expect_column_values_to_be_unique(paper_id), expect_column_value_lengths_to_be_between(summary)); sau repair = PASS.
- **Freshness SLA**: corrupted có 8/22 bài quá hạn (is_fresh = FAIL); repaired có 1/24 (is_fresh = PASS).
