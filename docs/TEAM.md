# Danh Sách Thành Viên & Báo Cáo Phân Công Nhóm

- **Tên Nhóm:** `3ae`
- **Mã Nhóm / Lớp:** `K4-L3-DAY10`
- **Tên Repository Nộp Bài:** `K4-L3-DAY10-3ae-DataPipeline`

---

## # Thành viên

| STT | Họ và tên | MSSV | Email | Vai trò & Phân công công việc | Nhánh làm việc | Báo cáo cá nhân |
|---:|---|---|---|---|---|---|
| 1 | Đỗ Ngọc Phi | 2A202602531 | | Trưởng nhóm, Corruption & Integration (`corruption.py`, `phase1.py`, `corruption_flow.py`), review & merge | `feat/phi-corruption-integration` | `report/2A202602531_DoNgocPhi.md` |
| 2 | Nguyễn Trường Bảo | 2A202602540 | | Data Ingestion & Cleaning (`crossref.py`, `cleaning.py`) | `feat/bao-ingestion-cleaning` | `report/2A202602540_NguyenTruongBao.md` |
| 3 | Phạm Cường Quốc | 2A202602469 | | Observability & Evaluation (`quality.py`, `testset.py`, `reporting.py`) | `feat/cuongquoc_2A202602469` | `report/2A202602469_PhamCuongQuoc.md` |

---

## # Phân công chi tiết

### Nguyễn Trường Bảo — Data Ingestion & Cleaning (CP0 – CP1)

Phần này **chặn đường của cả nhóm**, nên cần xong trước và push sớm nhất.

| File | Hàm | Yêu cầu |
|---|---|---|
| `src/ingestion/crossref.py` | `parse_crossref_payload` | Duyệt `payload["message"]["items"]`, lấy DOI → `paper_id`, title, abstract (bỏ tag JATS `<jats:p>`…), authors (`given family`), `subject` → categories, dates, URL. Bỏ record thiếu DOI/title/abstract. |
| | `fetch_source_records` | Gọi Crossref với `settings.source_query`, `source_filter`, `max_results`; retry/backoff cho 429/503. Lỗi mạng hoặc `REFRESH_SOURCE` không bật → **fallback đọc snapshot** `data/raw/crossref_response.json` / `crossref_records.json`. Lưu cả 2 file raw. |
| | `load_raw_records` | Đọc JSON → `list[PaperRecord]`. |
| `src/ingestion/cleaning.py` | `build_clean_dataframe` | Chuẩn hóa text, parse ngày, tính `age_days`, tạo các cột helper và `text_for_embedding` (5 phần), dedupe theo `paper_id`, lọc dòng xấu, sort. Phải đúng **Clean schema** bên dưới. |

**Tín hiệu hoàn thành:** `Đã tải 24 bài báo` và `Clean thành công 24 dòng` (lệnh trong `docs/CHECKPOINTS.md` CP0, CP1). Commit kèm `data/clean/papers_clean.json` để Quốc dùng test.

### Phạm Cường Quốc — Observability & Evaluation (CP1 – CP2, reporting)

| File | Hàm | Yêu cầu |
|---|---|---|
| `src/observability/quality.py` | `run_data_quality_checks` | **Cú pháp GX 1.x** (`gx.get_context(mode="ephemeral")` → `data_sources.add_pandas` → `add_dataframe_asset` → `add_batch_definition_whole_dataframe`). 4 expectations: row count 5–5000; not-null `paper_id`/`title`/`text_for_embedding`; unique `paper_id`; `summary` dài ≥ 30. Trả dict có key `success`, ghi JSON vào `data/quality/<report_name>_quality_report.json` (hoặc path trong config). |
| | `build_freshness_report` | `latest_published`, `oldest_published`, `stale_rows` (`age_days > 180`), `total_rows`, `is_fresh` (= tỷ lệ stale ≤ 25%). Ghi JSON. |
| `src/evaluation/testset.py` | `build_test_set` | 10 câu, đủ 4 loại `summary`/`authors`/`date`/`categories`. **Câu hỏi phải khớp keyword trong `retrieval/qa.py`** (xem mục Lưu ý). Ghi `data/eval/test_set.json`. |
| `src/observability/reporting.py` | `generate_phase1_report`, `generate_corruption_report` | Markdown: source summary, bảng metrics, quality, freshness; report so sánh **3 cột Baseline / Corrupted / Repaired** + phân tích. |

**Trong lúc chờ Bảo:** có thể tự dựng tạm DataFrame từ `data/raw/crossref_records.json` theo Clean schema để test, **không commit** code tạm này vào `cleaning.py`.

**Tín hiệu hoàn thành:** `Quality check status = True` trên dữ liệu sạch, `Sinh được 10 câu hỏi test`.

### Đỗ Ngọc Phi — Trưởng nhóm, Corruption & Integration (CP3 – CP5)

| File | Hàm | Yêu cầu |
|---|---|---|
| `src/ingestion/corruption.py` | `corrupt_clean_dataframe` | 6 lỗi: drop 20% bài mới nhất, blank summary, inject noise, truncate title < 8 ký tự, lùi `published` 365 ngày (tính lại `age_days`), duplicate rows. Rebuild `text_for_embedding`, ghi `corruption_log.json`. |
| `src/pipelines/phase1.py` | `main` | Fetch → clean → save CSV/JSON → quality + freshness → build index → test set → evaluate → phase1 report. |
| `src/pipelines/corruption_flow.py` | `main` | Corrupt → index `papers-corrupted` → evaluate → quality (phải FAIL) → repair từ raw → index `papers-repaired` → evaluate → comparison report. |
| — | Review & merge | Review PR của Bảo và Quốc, merge vào `main`, chạy end-to-end, điền `report/group_report.md`. |

---

## # Quy trình làm việc với Git

1. Mỗi người tạo nhánh riêng từ `main` mới nhất: `git checkout main && git pull && git checkout -b <nhánh>`.
2. Commit nhỏ, message rõ ràng (ví dụ `feat(ingestion): parse crossref payload`), **dùng đúng tài khoản GitHub cá nhân** để được tính contributor.
3. Xong phần việc → push nhánh và mở Pull Request vào `main`.
4. Phi review, yêu cầu sửa nếu cần, rồi merge. **Không tự merge vào `main`.**
5. Sau khi `main` được cập nhật, các nhánh còn lại `git pull origin main` (hoặc rebase) để lấy code mới.

**Thứ tự merge:** Bảo (ingestion/cleaning) → Quốc (quality/testset/reporting) → Phi (corruption/pipelines).

**Checklist trước khi mở PR:**
- [ ] Lệnh "Tín hiệu hoàn thành" của phần mình chạy được.
- [ ] Không đổi chữ ký hàm có sẵn; không hardcode đường dẫn tuyệt đối (dùng `settings.paths`).
- [ ] Không commit `.env` / API key.
- [ ] Output đúng contract dưới đây.

---

## # Contract dùng chung

### Clean schema (output của `build_clean_dataframe`)

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `paper_id` | str | DOI, unique, không null |
| `title` | str | đã normalize whitespace |
| `summary` | str | đã bỏ tag JATS/HTML |
| `authors` | list[str] | |
| `categories` | list[str] | |
| `primary_category` | str | |
| `published` | str | `YYYY-MM-DD` |
| `updated` | str | `YYYY-MM-DD` |
| `abs_url`, `pdf_url`, `comment` | str | |
| `authors_joined` | str | `", ".join(authors)` |
| `categories_joined` | str | `", ".join(categories)` |
| `summary_chars` | int | `len(summary)` |
| `age_days` | int | `(run_date - published).days` |
| `text_for_embedding` | str | `Title: …\nAuthors: …\nPublished: …\nCategories: …\nSummary: …` |

`retrieval/index.py` đọc trực tiếp các cột `paper_id`, `title`, `text_for_embedding`, `published`, `authors_joined`, `categories_joined`, `summary`, `abs_url`, `pdf_url`, nên **không được đổi tên**.

### Test set schema

```json
{
  "id": "eval_001",
  "question_type": "summary | authors | date | categories",
  "question": "…'<Title chính xác>'…",
  "ground_truth": "…",
  "ground_truth_doc_ids": ["<paper_id>"]
}
```

**Lưu ý:** `retrieval/qa.py` trả lời theo keyword, không dùng LLM. Để baseline đạt điểm cao:
- Tên bài đặt trong nháy đơn `'...'` (dùng để lookup chính xác theo title).
- `authors`: câu chứa `who authored` hoặc `list the authors` → ground truth = `authors_joined`.
- `date`: câu chứa `when was` hoặc `publication date` → ground truth = `published`.
- `categories`: câu chứa `what categories` → ground truth = `categories_joined`.
- `summary`: ground truth = `core.utils.first_sentence(summary)`.

### Artifact paths
Luôn dùng `settings.paths.*` trong `src/core/config.py`, không tự đặt đường dẫn.

---

## # Cá nhân

> Mỗi thành viên **tự điền** phần này sau khi hoàn thành. Ghi rõ phần đã xong, phần còn thử nghiệm, blocker và bằng chứng (commit, artifact).

### ## DoNgocPhi-2A202602531
- **Vai trò:** Trưởng nhóm, Corruption & Integration, review & merge.
- **Phạm vi được giao:** `src/ingestion/corruption.py`, `src/pipelines/phase1.py`, `src/pipelines/corruption_flow.py`, `report/group_report.md`.
- **Công việc chi tiết đã hoàn thành:**
  - Lập phân công, quy trình nhánh/PR và data contract dùng chung trong `docs/TEAM.md`.
  - `src/ingestion/corruption.py` — `corrupt_clean_dataframe`: 6 kịch bản lỗi tất định (seed 42), áp lên các nhóm dòng không giao nhau: drop 5 bài mới nhất, blank summary, inject noise, truncate title, lùi `published` 365 ngày (tính lại `age_days`), duplicate rows; tính lại `text_for_embedding`; ghi `data/results/corruption_log.json`.
  - `src/pipelines/phase1.py`: 7 bước ingest → clean → quality gate (FAIL thì không index) → Chroma `papers-baseline` → test set (tái sử dụng file cố định) → evaluate → `phase1_report.md`, kèm demo agent tùy chọn.
  - `src/pipelines/corruption_flow.py`: corrupt → quality/freshness → index `papers-corrupted` để đo silent failure → gate FAIL thì auto-repair từ `data/raw/crossref_records.json` → gate PASS → `papers-repaired` → evaluate → `corruption_report.md`, có kiểm tra repaired trùng khớp baseline.
  - Review và merge nhánh của Bảo và Quốc; chạy kiểm chứng CP0–CP2 và tích hợp trước mỗi lần merge; chạy end-to-end trên `main` (exit code 0) với `gpt-4o-mini`.
  - Báo cáo nhóm `report/group_report.md` và báo cáo cá nhân `report/2A202602531_DoNgocPhi.md`.
- **Điều học được / Đóng góp chính:**
  - Repair đúng nghĩa là build lại từ raw bất biến bằng chính code baseline. Cách này idempotent và kiểm chứng được (metrics repaired = baseline: Hit Rate 1.0, Token F1 1.0).
  - Mỗi lớp observability bắt một nhóm lỗi khác nhau: GX bắt duplicate và summary rỗng, Freshness bắt stale date, còn noise và truncate title lọt qua cả hai.
  - Evaluator cũng có thể mắc silent failure: LLM judge chấm câu trả lời rỗng là đúng, nên cần đối chiếu với metric tất định như Token F1.

### ## NguyenTruongBao-2A202602540
- **Vai trò:** Data Ingestion & Cleaning.
- **Phạm vi được giao:** `src/ingestion/crossref.py`, `src/ingestion/cleaning.py`, raw & clean artifacts.
- **Công việc chi tiết đã hoàn thành:**
  - Hoàn thiện `src/ingestion/crossref.py`:
    - `parse_crossref_payload`: bóc tách items từ payload Crossref REST API, làm sạch thẻ JATS XML `<jats:p>`, bóc tách `DOI` -> `paper_id`, `title`, `abstract` -> `summary`, `authors`, `categories`, `primary_category`, `published`, `updated`, `abs_url`, `pdf_url`, `comment`. Lọc bỏ các record thiếu DOI/title/abstract.
    - `fetch_source_records`: gọi Crossref API với query, filter, rows cùng retry/backoff khi gặp 429/503/network error; tự động fallback đọc snapshot local `crossref_response.json` hoặc `crossref_records.json` khi `REFRESH_SOURCE` tắt hoặc mạng lỗi. Bảo toàn cả 2 file raw artifacts.
    - `load_raw_records`: đọc file snapshot JSON và map thành danh sách `PaperRecord`.
  - Hoàn thiện `src/ingestion/cleaning.py`:
    - `build_clean_dataframe`: chuẩn hóa text & khoảng trắng, loại bỏ XML/HTML tags; tính toán `age_days = (run_date - published).days` chuẩn xác; tạo các cột helper `authors_joined`, `categories_joined`, `summary_chars`; sinh cấu trúc `text_for_embedding` 5 phần chuẩn hợp đồng (`Title: ...\nAuthors: ...\nPublished: ...\nCategories: ...\nSummary: ...`); lọc bỏ dòng xấu (`summary_chars < 30`); khử trùng lặp theo `paper_id`; sắp xếp dữ liệu theo ngày xuất bản giảm dần và `paper_id`.
  - Bàn giao đầy đủ artifacts:
    - `data/raw/crossref_response.json` (24 items) & `data/raw/crossref_records.json` (24 records)
    - `data/clean/papers_clean.csv` & `data/clean/papers_clean.json` (24 rows đạt chuẩn Clean schema)
    - Báo cáo cá nhân `report/2A202602540_NguyenTruongBao.md`
  - Đã nghiệm thu:
    - CP0: `Tín hiệu hoàn thành: Đã tải 24 bài báo`
    - CP1: `Tín hiệu hoàn thành: Clean thành công 24 dòng`
- **Điều học được / Đóng góp chính:**
  - Nắm vững nguyên tắc Raw Preservation (Data Lineage) và thiết kế pipeline Idempotent có khả năng tự phục hồi (Self-healing).
  - Kỹ thuật tiền xử lý dữ liệu phi cấu trúc và bán cấu trúc (JATS XML, author name formatting, temporal metadata parsing).
  - Chuẩn hóa contract giao tiếp dữ liệu giữa Data Engineering và AI Retrieval, giúp Vector Store Indexing (`retrieval/index.py`) và Data Quality Gate (`observability/quality.py`) vận hành mượt mà.

### ## PhamCuongQuoc-2A202602469
- **Vai trò:** Observability & Evaluation.
- **Phạm vi được giao:** `src/observability/quality.py`, `src/evaluation/testset.py`, `src/observability/reporting.py`.
- **Công việc chi tiết đã hoàn thành:**
  - `src/observability/quality.py`:
    - `run_data_quality_checks`: Quality Gate chuẩn GX 1.x (`gx.get_context(mode="ephemeral")` → `data_sources.add_pandas` → `add_dataframe_asset` → `add_batch_definition_whole_dataframe` → `ExpectationSuite` + `batch.validate`). 4 nhóm expectation: row count 5–5000; not-null `paper_id`/`title`/`text_for_embedding`; unique `paper_id`; `summary` dài ≥ 30. Trả dict có `success`, `failed_expectations`, chi tiết từng expectation và `freshness_sla` (tham khảo); ghi `data/quality/<report_name>_quality_report.json`.
    - `build_freshness_report`: `latest_published`, `oldest_published`, `stale_rows` (`age_days > 180`), `total_rows`, `stale_ratio`, `is_fresh` (stale ≤ 25%); ghi JSON vào `report_path`.
  - `src/evaluation/testset.py` — `build_test_set`: 10 câu tất định (3 summary / 3 authors / 2 date / 2 categories), title trong nháy đơn, keyword khớp `retrieval/qa.py`, ground truth đúng trường QA trả về. Ghi `data/eval/test_set.json`.
  - `src/observability/reporting.py`: `generate_phase1_report` (source, metrics, GX, freshness) và `generate_corruption_report` (bảng 3 cột Baseline / Corrupted / Repaired + Δ, quality, freshness, phân tích sinh tự động từ số liệu).
  - Đã nghiệm thu: `Quality check status = True` (6/6 expectation), `Sinh được 10 câu hỏi test`; smoke test `LLM_PROVIDER=mock` toàn luồng: baseline Hit Rate 100%, corruption giả lập làm GX FAIL (unique `paper_id`, độ dài `summary`) và `is_fresh = False`.
  - Báo cáo cá nhân: `report/2A202602469_PhamCuongQuoc.md`.
- **Lưu ý cho tích hợp (Phi):** gọi `run_data_quality_checks(df, settings, "baseline" | "corrupted" | "repaired")` — tên `baseline`/`corrupted` khớp `settings.paths.*_quality_report`; `corruption.py` cần tính lại `age_days` sau khi lùi `published` để freshness phát hiện được.
- **Điều học được / Đóng góp chính:**
  - GX (cấu trúc/toàn vẹn) và Freshness SLA (thời gian) bắt các loại lỗi khác nhau — lùi ngày không làm GX fail nhưng làm SLA fail.
  - Bộ đánh giá phải khớp contract của hệ thống được đo để suy giảm metrics quy được về chất lượng dữ liệu.
  - Báo cáo sinh trực tiếp từ artifact để số liệu luôn khớp lần chạy thực tế.
