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
| 3 | Phạm Cường Quốc | 2A202602469 | | Observability & Evaluation (`quality.py`, `testset.py`, `reporting.py`) | `feat/quoc-quality-eval` | `report/2A202602469_PhamCuongQuoc.md` |

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
4. Phi review (cùng Claude Code), yêu cầu sửa nếu cần, rồi merge. **Không tự merge vào `main`.**
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
  - _[Tự điền]_
- **Điều học được / Đóng góp chính:**
  - _[Tự điền]_

### ## NguyenTruongBao-2A202602540
- **Vai trò:** Data Ingestion & Cleaning.
- **Phạm vi được giao:** `src/ingestion/crossref.py`, `src/ingestion/cleaning.py`, raw & clean artifacts.
- **Công việc chi tiết đã hoàn thành:**
  - _[Tự điền]_
- **Điều học được / Đóng góp chính:**
  - _[Tự điền]_

### ## PhamCuongQuoc-2A202602469
- **Vai trò:** Observability & Evaluation.
- **Phạm vi được giao:** `src/observability/quality.py`, `src/evaluation/testset.py`, `src/observability/reporting.py`.
- **Công việc chi tiết đã hoàn thành:**
  - _[Tự điền]_
- **Điều học được / Đóng góp chính:**
  - _[Tự điền]_
