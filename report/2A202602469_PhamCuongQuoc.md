# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
| :--- | :--- |
| Họ và tên | Phạm Cường Quốc |
| MSSV | 2A202602469 |
| Khóa/Lớp | K4-L3-DAY10 |
| Tên nhóm | 3ae |
| Vai trò chính | Observability & Evaluation (CP1 – CP2, reporting) |
| Repository | K4-L3-DAY10-3ae-DataPipeline |
| Ngày hoàn thành | 2026-09-25 |

---

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| :--- | :--- | :--- | :--- | :--- |
| Data Quality Gate (GX 1.x) | `src/observability/quality.py` – `run_data_quality_checks` | Clean DataFrame (Clean schema), `Settings`, `report_name` | Dict có `success`, danh sách expectation pass/fail; JSON `data/quality/<report_name>_quality_report.json` | Hoàn thành |
| Freshness SLA | `src/observability/quality.py` – `build_freshness_report` | Clean DataFrame (`published`, `age_days`), `report_path` | JSON `latest_published`, `oldest_published`, `stale_rows`, `total_rows`, `stale_ratio`, `is_fresh` | Hoàn thành |
| Benchmark test set | `src/evaluation/testset.py` – `build_test_set` | Clean DataFrame | `data/eval/test_set.json` (10 câu, 4 loại) | Hoàn thành |
| Báo cáo Markdown | `src/observability/reporting.py` – `generate_phase1_report`, `generate_corruption_report` | Metrics, quality, freshness của từng pha | `data/reports/phase1_report.md`, `data/reports/corruption_report.md` | Hoàn thành (chờ Phi gọi trong pipeline) |

Phần việc phụ thuộc vào `data/clean/papers_clean.json` của **Nguyễn Trường Bảo** và được **Đỗ Ngọc Phi** gọi trong `phase1.py` / `corruption_flow.py`. Chữ ký hàm giữ nguyên như starter repo.

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| :--- | :--- | :--- |
| Smoke test toàn luồng với `LLM_PROVIDER=mock` (index → evaluate → corruption giả lập → report) | Đỗ Ngọc Phi (`phase1.py`, `corruption_flow.py`) | Xác nhận các hàm của tôi ghép được với `LocalEmbeddingIndex.build` và `evaluate_pipeline` trước khi Phi tích hợp |

---

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| :--- | :--- | :--- | :--- |
| Quality Gate GX 1.x với 4 nhóm expectation | `quality.py` | `success = True` trên 24 dòng sạch (6/6 expectation pass) | Lệnh CP1 in `Tín hiệu hoàn thành: Quality check status = True` |
| Freshness SLA | `quality.py` | Dữ liệu sạch: 1/24 bài quá hạn (4.17%), `is_fresh = True` | Gọi `build_freshness_report` trên `papers_clean.json` |
| Sinh test set | `testset.py`, `data/eval/test_set.json` | 10 câu: 3 summary, 3 authors, 2 date, 2 categories | Lệnh CP2 in `Tín hiệu hoàn thành: Sinh được 10 câu hỏi test` |
| Report phase 1 & report so sánh 3 trạng thái | `reporting.py` | Markdown có bảng metrics, quality, freshness, bảng 3 cột Baseline / Corrupted / Repaired + delta + phân tích tự động | Smoke test sinh 2 file report trong thư mục tạm |

---

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Silent failure: dữ liệu bẩn không làm pipeline crash, nên cần một chốt kiểm tra trước khi index (Quality Gate), một tín hiệu độ tươi (Freshness SLA), một bộ đề thi cố định để đo suy giảm, và báo cáo biến số liệu thành bằng chứng đọc được.

### Cách triển khai

1. **Quality Gate (GX 1.x):** `gx.get_context(mode="ephemeral")` → `data_sources.add_pandas` → `add_dataframe_asset` → `add_batch_definition_whole_dataframe` → `get_batch(batch_parameters={"dataframe": df})`. Tạo `ExpectationSuite` và `batch.validate(suite)`:
   - `ExpectTableRowCountToBeBetween(5, 5000)`
   - `ExpectColumnValuesToNotBeNull` cho `paper_id`, `title`, `text_for_embedding`
   - `ExpectColumnValuesToBeUnique("paper_id")`
   - `ExpectColumnValueLengthsToBeBetween("summary", min_value=30)`

   Mỗi kết quả được rút gọn thành `expectation`, `column`, `success`, `observed_value` / `unexpected_count` và vài giá trị lỗi mẫu. `success` chỉ phụ thuộc GX; freshness được ghi kèm trong key `freshness_sla` để tham khảo, không làm thay đổi kết quả gate.
2. **Freshness SLA:** bài quá hạn khi `age_days > settings.freshness_threshold_days` (180). `is_fresh = stale_ratio <= 25%`. Dùng cột `age_days` có sẵn (nên corruption lùi `published` phải tính lại `age_days`); nếu thiếu cột thì tự tính từ `published`.
3. **Test set:** lọc paper hợp lệ (đủ cột, không rỗng, title không chứa `'` vì QA lookup bằng regex `'([^']+)'`), sort theo `paper_id` cho kết quả ổn định, chọn 10 paper cách đều nhau trên corpus và xoay vòng 4 loại câu hỏi. Template chứa đúng keyword mà `retrieval/qa.py` nhận diện (`who authored`, `when was`, `what categories`); ground truth lấy đúng trường mà QA trả về (`authors_joined`, `published`, `categories_joined`, `first_sentence(summary)`).
4. **Reporting:** hàm tạo bảng Markdown dùng chung; report so sánh có cột Δ (điểm phần trăm) so với baseline, và phần Analysis sinh tự động từ số liệu truyền vào, không có câu chữ cố định để tránh ghi số liệu không khớp thực tế.

### Input, output và contract

| Thành phần | Mô tả |
| :--- | :--- |
| Input | Clean DataFrame theo Clean schema (`docs/TEAM.md`); metrics summary từ `evaluation/metrics.py::evaluate_pipeline` |
| Output | Quality dict (`success`, `failed_expectations`, `results`, `freshness_sla`); freshness dict; `test_set.json` theo Test set schema; 2 file Markdown |
| Module phụ thuộc | `core/config.py` (`settings.paths`, `freshness_threshold_days`), `core/utils.py` |
| Module sử dụng output | `pipelines/phase1.py`, `pipelines/corruption_flow.py`, `evaluation/metrics.py` (đọc test set) |
| Điều kiện lỗi cần xử lý | DataFrame thiếu cột / quá ít paper → `ValueError` khi tạo test set; DataFrame rỗng → `is_fresh = False`; cột thiếu trong GX → expectation fail kèm `exception` |

### Cách xác minh

```bash
python -c "from core.config import load_settings; from observability.quality import run_data_quality_checks; import pandas as pd; s=load_settings(); df=pd.read_json(s.paths.clean_json); res=run_data_quality_checks(df, s, 'test'); print(f'Tín hiệu hoàn thành: Quality check status = {res[\"success\"]}')"
python -c "from core.config import load_settings; from evaluation.testset import build_test_set; import pandas as pd; s=load_settings(); df=pd.read_json(s.paths.clean_json); ts=build_test_set(df, s.paths.eval_testset); print(f'Tín hiệu hoàn thành: Sinh được {len(ts)} câu hỏi test')"
```

- Kết quả thực tế: `Quality check status = True` và `Sinh được 10 câu hỏi test`.
- Artifact: `data/eval/test_set.json`.

---

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** `retrieval/qa.py` trả lời theo keyword và lookup title trong nháy đơn, không dùng LLM. Nếu câu hỏi viết tự do, baseline có thể trả lời sai ngay trên dữ liệu sạch, khiến so sánh 3 trạng thái mất ý nghĩa.
- **Các phương án:** (1) sinh câu hỏi tự do / bằng LLM; (2) template khớp contract của QA, ground truth lấy đúng trường QA trả về.
- **Phương án chọn:** (2).
- **Lý do:** baseline phải là mốc "đúng" ổn định để mọi suy giảm ở pha corrupted đều quy được về chất lượng dữ liệu, không phải do câu hỏi. Test set cũng tất định (không random) nên chạy lại cho cùng kết quả.
- **Bằng chứng:** smoke test với `LLM_PROVIDER=mock` cho baseline Hit Rate 100% và Token F1 100%.

---

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng:** chạy lệnh tín hiệu CP1 trên terminal Windows báo `UnicodeEncodeError: 'charmap' codec can't encode character 'ệ'`, dù hàm đã chạy xong.
- **Nguyên nhân gốc:** console dùng code page không hỗ trợ tiếng Việt khi `print` chuỗi "Tín hiệu hoàn thành".
- **Cách xử lý:** đặt `PYTHONIOENCODING=utf-8` trước khi chạy (PowerShell: `$env:PYTHONIOENCODING="utf-8"`).
- **Xác minh:** lệnh in đúng `Tín hiệu hoàn thành: Quality check status = True`.
- **Điều học được:** tách lỗi hiển thị khỏi lỗi logic — xem file JSON output để chắc hàm đã chạy đúng trước khi sửa code.

---

## 7. Hiểu biết về luồng end-to-end

1. **Crossref → vector index:** raw JSON → `PaperRecord` → clean DataFrame với `text_for_embedding` 5 phần → MiniLM embedding → ChromaDB collection `papers-baseline`.
2. **Evaluation set:** mỗi câu có `ground_truth_doc_ids`; Hit Rate = tỷ lệ câu mà top-k chứa đúng doc, Token F1 so câu trả lời với `ground_truth`.
3. **Quality checks vs freshness:** GX kiểm tra cấu trúc/toàn vẹn (số dòng, null, trùng khóa, độ dài summary); freshness kiểm tra độ cũ theo thời gian (`age_days > 180`, ngưỡng 25%). Dữ liệu có thể đúng schema mà vẫn cũ, nên cần cả hai.
4. **Cùng test set cho 3 pha:** để biến số duy nhất là dữ liệu.
5. **Repair thành công khi:** GX `success = True`, `is_fresh = True`, và metrics repaired quay về mức baseline.

---

## 8. Phân tích kết quả

> Số liệu dưới đây là từ **smoke test của tôi** với `LLM_PROVIDER=mock` và một bản corruption giả lập đơn giản (bỏ 5 bài mới nhất, xóa 5 summary, cắt 3 title, lùi `age_days` 10 dòng, nhân bản 3 dòng), không phải kết quả chính thức. Kết quả chính thức nằm trong `data/reports/corruption_report.md` sau khi pipeline của Phi chạy.

| Metric/signal | Baseline | Corrupted (giả lập) | Repaired | Nhận xét |
| :--- | :---: | :---: | :---: | :--- |
| `retrieval_hit_rate` | 100% | 80% | 100% | Giảm do mất bài mới và title bị cắt |
| `mean_token_f1` | 100% | 90% | 100% | Summary rỗng làm câu trả lời sai |
| Quality checks (GX) | PASS (6/6) | FAIL (4/6: unique `paper_id`, độ dài `summary`) | PASS | Gate bắt được duplicate và summary rỗng |
| Freshness | 1/24 stale, fresh | 11/22 stale (50%), not fresh | 1/24 stale, fresh | SLA phát hiện dữ liệu bị lùi ngày |

### Kết luận từ số liệu

- Nhân bản dòng + xóa summary → GX fail đúng 2 expectation tương ứng → gate chặn trước khi index.
- Lùi ngày → stale ratio 50% > 25% → `is_fresh = False`, trong khi GX không bắt được lỗi này: minh chứng cần cả hai lớp giám sát.

---

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. Quality gate và freshness bắt các loại lỗi khác nhau; thiếu một trong hai sẽ bỏ lọt lỗi.
2. Bộ đánh giá phải khớp contract của hệ thống được đo, nếu không metrics phản ánh lỗi của đề thi chứ không phải của dữ liệu.
3. Báo cáo nên sinh trực tiếp từ artifact để số liệu luôn khớp với lần chạy thực tế.

### Nếu có thêm thời gian

Thêm expectation phát hiện noise trong summary (tỷ lệ ký tự không phải chữ) và title quá ngắn (< 8 ký tự) để GX bắt được cả lỗi inject noise và truncate title; viết pytest cho `quality.py` và `testset.py`.

---

## 10. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [x] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Phạm Cường Quốc
**Ngày xác nhận:** 2026-09-25
