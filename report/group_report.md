# Group Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin bài nộp

| Thông tin | Nội dung |
| --- | --- |
| Khóa/Lớp | K4 — K4-L3-DAY10 |
| Tên nhóm | 3ae |
| Repository | https://github.com/phido0410/K4-L3-DAY10-3ae-DataPipeline |
| Ngày hoàn thành | 2026-09-25 |

### Thành viên và phân công

| STT | Họ và tên | MSSV | Vai trò chính | Module/deliverable sở hữu |
| --: | --- | --- | --- | --- |
| 1 | Đỗ Ngọc Phi | 2A202602531 | Trưởng nhóm, Corruption & Integration, review/merge | `src/ingestion/corruption.py`, `src/pipelines/phase1.py`, `src/pipelines/corruption_flow.py`, artifacts trong `data/results/`, báo cáo nhóm |
| 2 | Nguyễn Trường Bảo | 2A202602540 | Data Ingestion & Cleaning | `src/ingestion/crossref.py`, `src/ingestion/cleaning.py`, `data/raw/`, `data/clean/papers_clean.*` |
| 3 | Phạm Cường Quốc | 2A202602469 | Observability & Evaluation | `src/observability/quality.py`, `src/evaluation/testset.py`, `src/observability/reporting.py`, `data/eval/test_set.json` |

Quy trình: mỗi thành viên làm trên nhánh riêng (`feat/bao-ingestion-cleaning`, `feat/cuongquoc_2A202602469`, `feat/phi-corruption-integration`), trưởng nhóm review, chạy kiểm tra rồi merge vào `main` theo thứ tự Ingestion → Observability → Integration. Contract dữ liệu dùng chung được chốt trước trong `docs/TEAM.md`.

## 2. Tóm tắt kết quả

**Tóm tắt của nhóm:**

Nhóm hoàn thành toàn bộ pipeline 7 tầng: ingestion Crossref (có retry/backoff và fallback snapshot offline), cleaning theo clean schema 16 cột, Quality Gate Great Expectations 1.x (6 expectation thuộc 4 nhóm) kèm Freshness SLA, index ChromaDB với `all-MiniLM-L6-v2`, đánh giá trên test set 10 câu, bộ corruption 6 kịch bản và luồng repair idempotent. Cả `python script/run_phase1.py` và `python script/run_corruption_flow.py` chạy thành công (exit code 0) trên nhánh `main`.

Baseline đạt Hit Rate 100%, Token F1 100%, Judge Accuracy 100%. Sau corruption, **Token F1 giảm mạnh nhất (100% → 58.2%)**, do ba nhóm lỗi: summary bị xóa (câu trả lời rỗng), ngày xuất bản bị lùi 1 năm (agent trả lời sai năm một cách tự tin) và nhiễu ký tự lọt thẳng vào câu trả lời. Quality Gate FAIL ở 2/6 expectation (trùng `paper_id`, summary < 30 ký tự) và Freshness SLA chuyển `is_fresh = False` (36.4% bài quá hạn). Repair tái tạo dữ liệu từ `data/raw/crossref_records.json`; dữ liệu sau repair trùng khớp nội dung với baseline và **mọi metric phục hồi về đúng mức baseline**.

Giới hạn quan trọng nhất: LLM judge (gpt-4o-mini) chấm 2 câu trả lời **rỗng** là đúng (4/5), nên Judge Accuracy của trạng thái corrupted (70%) đang đánh giá cao hơn thực tế (50% nếu loại 2 câu này). Ngoài ra Quality Gate chưa bắt được lỗi truncate title và inject noise.

## 3. Kiến trúc và luồng dữ liệu

### Luồng end-to-end

```text
Crossref API (REFRESH_SOURCE=1) hoặc snapshot offline data/raw/
    -> fetch_source_records: raw response + raw records (data/raw/)
    -> build_clean_dataframe: clean schema, age_days, text_for_embedding (data/clean/)
    -> run_data_quality_checks (GX 1.x) + build_freshness_report (data/quality/)
         └─ gate FAIL => dừng, không index
    -> LocalEmbeddingIndex.build: MiniLM + ChromaDB collection papers-baseline
    -> build_test_set (10 câu, cố định) -> evaluate_pipeline -> baseline metrics
    -> phase1_report.md
    -> corrupt_clean_dataframe (6 lỗi, seed 42) -> quality/freshness FAIL
    -> index papers-corrupted (cố ý bỏ qua gate để đo silent failure) -> evaluate
    -> gate FAIL => auto-repair: load_raw_records -> build_clean_dataframe -> gate PASS
    -> index papers-repaired -> evaluate
    -> corruption_report.md (Baseline vs Corrupted vs Repaired)
```

### Trách nhiệm của từng khối

| Khối | Input | Xử lý chính | Output/artifact | Owner |
| --- | --- | --- | --- | --- |
| Ingestion | Crossref REST API / `data/raw/crossref_response.json` | Gọi API với query + filter, retry/backoff 429/5xx, fallback snapshot, parse DOI/title/abstract/authors/subject/dates/URL, bỏ tag JATS | `data/raw/crossref_response.json`, `data/raw/crossref_records.json` | Bảo |
| Cleaning | `list[PaperRecord]`, `run_date` | Chuẩn hóa text, parse ngày, `age_days`, cột helper, `text_for_embedding`, lọc summary < 30, dedupe `paper_id`, sort | `data/clean/papers_clean.csv`, `.json` | Bảo |
| Embedding/index | Clean DataFrame | MiniLM `all-MiniLM-L6-v2`, ChromaDB cosine, 3 collection riêng | `data/chroma/`, `data/embeddings/*.json` | Starter code, được gọi bởi Phi |
| Evaluation | Clean DataFrame | Test set 10 câu / 4 loại; Hit Rate, Token F1, LLM judge | `data/eval/test_set.json`, `data/results/*_metrics.json` | Quốc (test set), Phi (chạy đánh giá) |
| Observability | DataFrame từng trạng thái | GX 1.x ephemeral context, 6 expectation; Freshness SLA 180 ngày / 25% | `data/quality/*_quality_report.json`, `*freshness_report.json` | Quốc |
| Corruption/repair | Clean DataFrame; raw records | 6 kịch bản lỗi tất định; repair bằng cách build lại từ raw | `data/results/corruption_log.json`, `data/clean/papers_clean_{corrupted,repaired}.*` | Phi |
| Orchestration | Settings, toàn bộ module | `phase1.py` (7 bước), `corruption_flow.py` (5 bước), quality gate chặn index | `data/results/`, `data/reports/` | Phi |
| Reporting | Metrics, quality, freshness | Markdown có bảng 3 cột + Δ, phần phân tích sinh từ số liệu | `data/reports/phase1_report.md`, `corruption_report.md` | Quốc |

## 4. Cách tái hiện kết quả

### Cấu hình không chứa secret

| Biến/cấu hình | Giá trị sử dụng |
| --- | --- |
| `LLM_PROVIDER` | `openai` |
| `LLM_MODEL` | `gpt-4o-mini` |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` |
| Số lượng Crossref records | 24 (`max_results=24`) |
| Retrieval `top_k` | 4 |
| Freshness threshold | `age_days > 180` là stale; `is_fresh` khi stale ratio ≤ 25% |
| Random seed | 42 (corruption); test set tất định, không random |
| Chế độ nguồn | Offline snapshot (mặc định, `REFRESH_SOURCE` không bật) |

### Lệnh cài đặt

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
cp .env.example .env   # điền LLM_PROVIDER, LLM_MODEL, OPENAI_API_KEY
```

### Lệnh chạy

```bash
python script/run_phase1.py
python script/run_corruption_flow.py
```

Không có API key vẫn chạy được với `LLM_PROVIDER=mock`; khi đó judge dùng heuristic dựa trên Token F1.

### Kết quả tái hiện

| Lệnh | Trạng thái | Thời điểm chạy gần nhất | Bằng chứng |
| --- | --- | --- | --- |
| Baseline pipeline | Thành công | 2026-09-25 15:42 (GMT+7) | `data/reports/phase1_report.md`, `data/results/baseline_metrics.json` |
| Corruption flow | Thành công | 2026-09-25 15:44 (GMT+7) | `data/reports/corruption_report.md`, `data/results/{corrupted,repaired}_metrics.json` |

Sau khi merge, nhóm chạy lại cả hai lệnh trên `main` (`python script/run_phase1.py && python script/run_corruption_flow.py`). Kết quả: exit code 0 và metrics trùng khớp với các file đã commit.

## 5. Ingestion, cleaning và data contract

### Nguồn dữ liệu

| Thuộc tính | Giá trị |
| --- | --- |
| Source | Crossref REST API `https://api.crossref.org/works` (snapshot `data/raw/crossref_response.json`) |
| Query/filter | `query=agentic retrieval augmented generation large language model`, `filter=from-pub-date:<run_date − 180 ngày>,has-abstract:true`, `rows=24` |
| Thời điểm lấy dữ liệu | Snapshot offline có sẵn trong repo; các bài xuất bản từ 2026-03-28 đến 2026-07-22 |
| Số record nhận được | 24 items → 24 `PaperRecord` → 24 dòng sạch |
| Cơ chế retry/backoff | 3 lần thử, backoff `2^attempt` giây cho HTTP 429/500/502/503/504 và lỗi mạng; thất bại thì fallback đọc `crossref_records.json` hoặc `crossref_response.json` |

Nhóm đã thử chế độ live (`REFRESH_SOURCE=1`): API trả về 24 record khác (có bài tiếng Nga) và pipeline cleaning xử lý được. Tuy vậy, kết quả nộp dùng snapshot offline để đảm bảo tái lập được.

### Raw và clean schema

| Trường | Kiểu dữ liệu | Bắt buộc? | Ý nghĩa | Xử lý khi thiếu/sai |
| --- | --- | --- | --- | --- |
| `paper_id` | str | Có | DOI, khóa định danh tài liệu | Thiếu → bỏ record; trùng → giữ bản đầu |
| `title` | str | Có | Tiêu đề bài báo | Thiếu → bỏ record; normalize whitespace |
| `summary` | str | Có | Abstract đã bỏ tag JATS | Thiếu → bỏ record; < 30 ký tự → lọc |
| `authors` | list[str] | Không | `given family` | Thiếu → danh sách rỗng |
| `categories` | list[str] | Không | Crossref `subject` | Thiếu → rỗng; `primary_category = "General"` |
| `published` | str `YYYY-MM-DD` | Có | Ngày xuất bản (`published` → `issued` → `created`) | Không parse được → mặc định `2026-01-01` (xem mục 12) |
| `updated` | str `YYYY-MM-DD` | Không | Ngày cập nhật | Thiếu → bằng `published` |
| `abs_url`, `pdf_url`, `comment` | str | Không | Liên kết DOI / PDF, ghi chú nguồn | Thiếu → `https://doi.org/<DOI>` |
| `authors_joined`, `categories_joined` | str | Có (derived) | Chuỗi nối bằng `", "`, dùng làm ground truth và metadata | Sinh từ list |
| `summary_chars` | int | Có (derived) | Độ dài summary | Sinh tự động |
| `age_days` | int | Có (derived) | `(run_date − published).days` | Sinh tự động |
| `text_for_embedding` | str | Có (derived) | Ngữ cảnh 5 phần cho embedding | Sinh tự động |

### Quy tắc cleaning

| Quy tắc | Quality dimension liên quan | Số record bị tác động | Cách xác minh |
| --- | --- | ---: | --- |
| Bỏ tag JATS/HTML (`<jats:p>`) trong abstract | Validity | 24 | `grep "<" data/clean/papers_clean.json` không còn tag trong `summary` |
| Loại record thiếu DOI / title / abstract | Completeness | 0 | 24 raw → 24 clean |
| Lọc `summary_chars < 30` | Completeness | 0 | Summary ngắn nhất 193 ký tự |
| Dedupe theo `paper_id` | Uniqueness | 0 | GX `expect_column_values_to_be_unique(paper_id)` PASS |
| Normalize whitespace title/summary/authors | Consistency | 0 (snapshot đã sạch) | So sánh raw và clean |

Snapshot hiện tại khá sạch nên các quy tắc lọc không loại dòng nào. Tác dụng của chúng được kiểm chứng qua bộ corruption (mục 9) và qua test thủ công với input bẩn: title thừa khoảng trắng, bản ghi trùng và summary `<jats:p>short</jats:p>` được xử lý đúng.

**`text_for_embedding`, document ID và `age_days`:** Document ID là DOI (`paper_id`), giữ ổn định qua mọi trạng thái nên ground truth của test set luôn đối chiếu được. Trong ChromaDB, mỗi dòng có `record_id = <paper_id>::<index>` để bản ghi trùng vẫn nạp được, qua đó mô phỏng lỗi duplicate index. `text_for_embedding` ghép `Title / Authors / Published / Categories / Summary`, mỗi phần một dòng, để embedding chứa cả metadata lẫn nội dung. `age_days` được tính tại thời điểm chạy từ `published` và là đầu vào duy nhất của Freshness SLA. Vì vậy, khi corruption lùi `published`, `age_days` phải được tính lại tương ứng.

## 6. Evaluation setup

| Thành phần | Cấu hình thực tế |
| --- | --- |
| Số câu hỏi | 10 |
| Các `question_type` | `summary` (3), `authors` (3), `date` (2), `categories` (2) |
| Ground-truth document ID | `paper_id` (DOI) của paper được chọn; paper chọn cách đều trên corpus đã sort theo `paper_id` |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` |
| Vector store/collection | ChromaDB persistent `data/chroma/`, cosine; `papers-baseline`, `papers-corrupted`, `papers-repaired` |
| Retrieval `top_k` | 4 |
| LLM provider/model | OpenAI `gpt-4o-mini` (judge, agent demo) |
| Test set dùng chung cho ba trạng thái | `data/eval/test_set.json` (sha256 bắt đầu bằng `5086ca7d3bbe5f40`) |

**Vì sao giữ nguyên test set:** Test set được sinh một lần từ dữ liệu sạch, commit vào repo, và được `phase1.py` tái sử dụng (chỉ tạo lại khi đặt `REFRESH_TEST_SET=1`). Ba trạng thái được đo trên cùng 10 câu và cùng ground truth, nên dữ liệu là biến số duy nhất thay đổi. Nếu sinh lại test set từ dữ liệu bẩn, ground truth sẽ bị bẩn theo và mọi suy giảm sẽ biến mất khỏi metric. Câu hỏi dùng đúng keyword mà `retrieval/qa.py` nhận diện, và tên bài được đặt trong nháy đơn để lookup chính xác. Nhờ vậy baseline là mốc "đúng" ổn định.

## 7. Kết quả baseline

### Artifact checklist

| Artifact | Đường dẫn thực tế | Trạng thái | Ghi chú |
| --- | --- | --- | --- |
| Raw response/records | `data/raw/` | Có | 24 items / 24 records |
| Cleaned dataset | `data/clean/` | Có | `papers_clean.*` + bản `_corrupted`, `_repaired` |
| Embedding manifest/index | `data/embeddings/`, `data/chroma/` | Có | 3 manifest, 3 collection |
| Evaluation set | `data/eval/test_set.json` | Có | 10 câu |
| Baseline metrics | `data/results/baseline_metrics.json` | Có | kèm `baseline_answers.json` |
| Quality/freshness | `data/quality/` | Có | baseline / corrupted / repaired |
| Baseline report | `data/reports/phase1_report.md` | Có | |

### Baseline metrics

| Metric | Giá trị | Diễn giải |
| --- | ---: | --- |
| `retrieval_hit_rate` | 1.000 | 10/10 câu có paper đúng trong top-4 (nhờ exact lookup theo title và semantic search) |
| `mean_token_f1` | 1.000 | QA trích xuất đúng trường metadata trùng với ground truth |
| `judge_accuracy` | 1.000 | gpt-4o-mini chấm 10/10 câu đúng |
| `mean_judge_score` | 5.0 | Mọi câu đạt 5/5 |
| Ragas | N/A | Không bật (`RUN_RAGAS` không đặt) để giảm thời gian và chi phí; không cần cho rubric |

Baseline đạt tuyệt đối là điều có chủ đích: test set được thiết kế khớp contract của QA, nên mọi suy giảm ở trạng thái corrupted đều quy được về chất lượng dữ liệu.

## 8. Data quality và freshness

### Quality checks

| Check | Quality dimension | Ngưỡng/kỳ vọng | Kết quả baseline | Bằng chứng |
| --- | --- | --- | --- | --- |
| `ExpectTableRowCountToBeBetween` | Completeness (volume) | 5–5000 dòng | PASS (24) | `data/quality/baseline_quality_report.json` |
| `ExpectColumnValuesToNotBeNull(paper_id)` | Completeness | 0 null | PASS (0/24) | như trên |
| `ExpectColumnValuesToNotBeNull(title)` | Completeness | 0 null | PASS (0/24) | như trên |
| `ExpectColumnValuesToNotBeNull(text_for_embedding)` | Completeness | 0 null | PASS (0/24) | như trên |
| `ExpectColumnValuesToBeUnique(paper_id)` | Uniqueness | Không trùng | PASS (0/24) | như trên |
| `ExpectColumnValueLengthsToBeBetween(summary)` | Validity | ≥ 30 ký tự | PASS (0/24) | như trên |

GX chạy bằng ephemeral context theo chuẩn 1.x (`gx.get_context(mode="ephemeral")` → `data_sources.add_pandas` → `add_dataframe_asset` → `add_batch_definition_whole_dataframe` → `batch.validate(suite)`). Trong `phase1.py`, gate FAIL thì pipeline dừng trước bước index.

### Freshness

| Thuộc tính | Giá trị |
| --- | --- |
| Freshness được đo tại | Clean dataset (`age_days` của từng paper), `data/quality/freshness_report.json` |
| Timestamp mới nhất | `latest_published = 2026-07-22` (65 ngày) |
| Ngưỡng freshness | Stale khi `age_days > 180`; fresh khi stale ratio ≤ 25% |
| Trạng thái baseline | Fresh |
| Lý do | 1/24 bài quá hạn (4.17%): bài 2026-03-28 có `age_days = 181`, dưới ngưỡng 25% |

Lưu ý: freshness phụ thuộc ngày chạy. Snapshot có tuổi 65–181 ngày, nên nếu chạy muộn hơn khoảng 5 tuần, stale ratio sẽ vượt 25% và baseline sẽ tự bị đánh là stale. Đây là hành vi đúng của một SLA.

## 9. Corruption scenarios và repair

| Corruption | Cách tạo | Record bị tác động | Quality signal kỳ vọng | Tác động thực tế | Cách repair |
| --- | --- | ---: | --- | --- | --- |
| `drop_latest_records` | Xóa 20% bài mới nhất | 5 | Freshness (`latest_published` lùi), row count | `latest_published` 2026-07-22 → 2026-06-12; eval_004 **retrieval miss** (paper 1808 bị xóa) | Build lại từ raw |
| `blank_summary` | Summary = `""` | 3 | GX summary length | GX FAIL 3/22; eval_001, eval_005 trả lời **rỗng**, Token F1 = 0 | Build lại từ raw |
| `inject_noise` | Chèn token rác (`%%%`, `NaN`, `@@##`…) sau ~50% số từ | 3 | Không có expectation tương ứng | GX **không phát hiện**; eval_009 trả lời chứa rác, judge 1/5 | Build lại từ raw |
| `truncate_title` | Cắt title còn 6 ký tự | 3 | Không có expectation tương ứng | GX **không phát hiện**; eval_002, eval_006 vẫn đúng vì semantic search vẫn tìm ra paper | Build lại từ raw |
| `stale_date` | Lùi `published` 365 ngày, tính lại `age_days` | 8 | Freshness SLA | Stale 8/22 = 36.4% → `is_fresh = False`; eval_003, eval_007 trả lời **sai năm** | Build lại từ raw |
| `duplicate_rows` | Nhân bản dòng | 3 | GX unique `paper_id` | GX FAIL (6/22 giá trị không unique); không thấy tác động rõ lên metric ở top-4 | Build lại từ raw (dedupe) |

Corruption log:

- Đường dẫn: `data/results/corruption_log.json`
- Trạng thái: Có
- Nhận xét: Log ghi đủ 6 loại lỗi, số dòng và danh sách `paper_id` bị tác động, title gốc trước khi cắt, seed (42), số dòng trước/sau (24 → 22). Mỗi loại lỗi được áp lên một nhóm dòng riêng (riêng duplicate lấy mẫu trên toàn bộ), nên có thể truy từng câu hỏi thất bại về đúng loại lỗi đã gây ra.

**Repair từ nguồn đáng tin cậy:** Repair không sửa từng dòng lỗi và không lọc kết quả đầu ra. Luồng repair đọc lại `data/raw/crossref_records.json`, một artifact bất biến, vì pipeline chỉ ghi file này khi fetch thành công. Sau đó dữ liệu chạy lại đúng hàm `build_clean_dataframe` của baseline, đi qua Quality Gate (FAIL thì dừng, không index), rồi được nạp vào collection mới `papers-repaired`; collection cũ bị xóa trước khi tạo lại. Vì vậy repair là **idempotent**: chạy lại bao nhiêu lần cũng ra cùng kết quả. Nhóm đã xác minh bằng cách chạy `corruption_flow` nhiều lần, và pipeline tự so sánh nội dung dữ liệu repaired với baseline (`identical to baseline=True`). Repair được **kích hoạt tự động khi gate FAIL**.

## 10. So sánh baseline, corrupted và repaired

| Metric/signal | Baseline | Corrupted | Repaired | Thay đổi do corruption | Mức phục hồi | Nhận xét |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `retrieval_hit_rate` | 1.000 | 0.900 | 1.000 | −10.0 pp | 100% | Chỉ `drop_latest` làm mất tài liệu cần tìm |
| `mean_token_f1` | 1.000 | 0.582 | 1.000 | −41.8 pp | 100% | Suy giảm lớn nhất: summary rỗng, sai năm, nhiễu |
| `judge_accuracy` | 1.000 | 0.700 | 1.000 | −30.0 pp | 100% | Đánh giá cao hơn thực tế: judge chấm 2 câu rỗng là đúng |
| `mean_judge_score` | 5.0 | 3.8 | 5.0 | −1.2 | 100% | |
| Quality checks pass/fail | PASS 6/6 | FAIL 4/6 | PASS 6/6 | −2 expectation | 100% | Bắt duplicate và summary rỗng |
| Freshness status | Fresh (4.2% stale) | Stale (36.4%) | Fresh (4.2%) | +32.2 pp stale | 100% | Bắt stale date |

Kết luận có quan hệ nhân quả:

1. **`stale_date` (8 dòng lùi 365 ngày) → Freshness SLA: stale ratio 4.2% → 36.4%, `is_fresh = False` (GX vẫn PASS phần này) → eval_003 và eval_007 trả lời `2025-03-28`, `2025-06-03` thay vì `2026-…`: Token F1 = 0, judge 2/5.** Agent không báo lỗi, chỉ trả lời sai năm một cách tự tin. Đây đúng là silent failure, và chỉ lớp Freshness bắt được nó.
2. **`blank_summary` + `duplicate_rows` → GX FAIL (`summary` length 3/22, `paper_id` unique 6/22) → eval_001 và eval_005 trả lời chuỗi rỗng, Token F1 = 0.** Quality Gate phát hiện đúng lỗi, và nếu áp gate như ở phase 1 thì dữ liệu này đã bị chặn trước khi vào index.
3. **Repair (rebuild từ raw) → GX PASS 6/6, `is_fresh = True`, dữ liệu trùng khớp baseline → cả 4 metric về đúng 1.000 / 5.0.**

**Kết quả khác kỳ vọng:**

- **LLM judge chấm sai câu trả lời rỗng.** Ở eval_001 và eval_005, câu trả lời là chuỗi rỗng nhưng gpt-4o-mini chấm 4/5 và `correct = true`, với lời giải thích "captures the essence of the reference answer". Judge đã bịa ra nội dung không có trong câu trả lời, nghĩa là bản thân evaluator cũng mắc silent failure. Token F1 (= 0) phản ánh đúng. Nếu tính hai câu này là sai, `judge_accuracy` thực tế của trạng thái corrupted là 5/10 = 50%, không phải 70%. Nhóm giữ nguyên số liệu gốc trong artifact và ghi chú lại ở đây, không sửa tay.
- **Retrieval sai nhưng câu trả lời vẫn đúng (eval_004).** Paper gốc bị `drop_latest` xóa, nhưng corpus có bài gần trùng "Advanced Perspectives on Multi-Agent Consensus…" với cùng categories, nên câu trả lời vẫn khớp. Hit Rate và độ đúng của câu trả lời là hai tín hiệu độc lập.
- **`truncate_title` và `duplicate_rows` không làm giảm metric.** Khi title bị cắt, exact lookup thất bại, nhưng semantic search trên `text_for_embedding` (vẫn còn Authors, Summary) vẫn tìm ra paper. Với duplicate, bản sao chiếm chỗ trong top-4 nhưng không đẩy paper đúng ra ngoài. Ở kích thước corpus 24 bài, hai lỗi này chỉ lộ ra qua Quality Gate (duplicate) hoặc không lộ ra (title).

## 11. Vấn đề tích hợp quan trọng

- **Triệu chứng:** Khi tích hợp thử `corruption_flow.py` với test set tạm (tự viết, trong lúc chờ module của Quốc), Hit Rate của trạng thái corrupted là 0.5. Sau khi ghép test set thật của Quốc, con số này là 0.9, dù dữ liệu corrupted giống hệt.
- **Nguyên nhân:** Metric phụ thuộc vào việc câu hỏi trỏ tới những paper nào và những paper đó dính loại lỗi nào. Test set tạm chọn 10 bài đầu theo thứ tự ngày, trùng với nhóm bài mới nhất bị `drop_latest` xóa. Test set thật chọn cách đều theo `paper_id`, nên chỉ 1 câu trỏ tới bài bị xóa. Nếu test set hoặc corruption không cố định, so sánh giữa các lần chạy sẽ không có ý nghĩa.
- **Cách xử lý:** (1) Corruption dùng seed cố định 42 và ghi danh sách `paper_id` bị tác động vào log. (2) Test set được commit và `phase1.py` tái sử dụng file có sẵn, chỉ sinh lại khi đặt `REFRESH_TEST_SET=1`. (3) Trong báo cáo, mọi câu hỏi thất bại được truy ngược về loại lỗi cụ thể (mục 9, mục 10).
- **Cách xác minh:** Chạy lại `python script/run_phase1.py && python script/run_corruption_flow.py` trên `main`: `test_set.json` không đổi (git diff rỗng), metrics 3 trạng thái trùng khớp với file đã commit.

## 12. Giới hạn và hướng cải thiện

| Giới hạn hiện tại | Ảnh hưởng | Hướng cải thiện có thể kiểm chứng |
| --- | --- | --- |
| LLM judge chấm câu trả lời rỗng là đúng | `judge_accuracy` corrupted bị thổi phồng (70% thay vì 50%) | Chấm câu trả lời rỗng là sai trước khi gọi LLM, và thêm câu "empty answer = incorrect" vào prompt; kiểm chứng bằng cách chạy lại và xem eval_001/005 có `correct = false` |
| GX không bắt `truncate_title`, `inject_noise` | 2/6 loại lỗi lọt qua gate | Thêm `ExpectColumnValueLengthsToBeBetween(title, min_value=8)` và `ExpectColumnValuesToMatchRegex(summary)` loại token rác; kỳ vọng GX FAIL thêm 2 expectation trên dữ liệu corrupted |
| Cleaning mặc định `published = 2026-01-01` khi không parse được ngày | Che lỗi thiếu ngày, làm sai Freshness | Bỏ record hoặc để trống và thêm expectation not-null cho `published` |
| Corpus nhỏ (24 bài) có nhiều bài gần trùng ("Advanced Perspectives on …") | Hit Rate kém nhạy; câu trả lời đúng "nhờ may mắn" (eval_004) | Tăng `max_results`, thêm near-duplicate detection (cosine > 0.95) vào quality gate |
| Freshness phụ thuộc ngày chạy | Snapshot sẽ tự bị đánh là stale sau khoảng 5 tuần | Cho phép cố định `run_date` qua biến môi trường khi cần tái lập kết quả lịch sử |
| Ragas chưa chạy | Thiếu faithfulness / context precision | Chạy với `RUN_RAGAS=1` |

## 13. Checklist trước khi nộp

- [x] Thông tin nhóm và repository chính xác.
- [x] Phân công khớp với module, artifact và kết quả thực tế.
- [x] Lệnh tái hiện đã được chạy lại trên phiên bản dùng để nộp.
- [x] Baseline, corrupted và repaired dùng cùng evaluation set.
- [x] Bảng metrics khớp với các file trong `data/results/`.
- [x] Quality/freshness conclusions khớp với `data/quality/`.
- [x] Các đường dẫn báo cáo và artifact truy cập được.
- [x] Mỗi thành viên đã hoàn thành báo cáo vai trò riêng.
- [x] Không có `.env`, API key, token hoặc secret trong source, report, log hay ảnh.
