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
| Nhánh làm việc | `feat/cuongquoc_2A202602469` (đã merge vào `main`) |
| Ngày hoàn thành | 2026-09-25 |

---

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| :--- | :--- | :--- | :--- | :--- |
| Data Quality Gate (GX 1.x) | `src/observability/quality.py` – `run_data_quality_checks` | Clean DataFrame, `Settings`, `report_name` | Dict có `success`, `failed_expectations`, chi tiết từng expectation, `freshness_sla`; JSON `data/quality/<report_name>_quality_report.json` | Hoàn thành |
| Freshness SLA | `src/observability/quality.py` – `build_freshness_report` | Clean DataFrame (`published`, `age_days`), `report_path` | JSON `latest_published`, `oldest_published`, `stale_rows`, `total_rows`, `stale_ratio`, `is_fresh` | Hoàn thành |
| Benchmark test set | `src/evaluation/testset.py` – `build_test_set` | Clean DataFrame | `data/eval/test_set.json` (10 câu, 4 loại) | Hoàn thành |
| Báo cáo Markdown | `src/observability/reporting.py` – `generate_phase1_report`, `generate_corruption_report` | Metrics, quality, freshness của từng pha | `data/reports/phase1_report.md`, `data/reports/corruption_report.md` | Hoàn thành |

Phần việc nhận `data/clean/papers_clean.json` từ **Nguyễn Trường Bảo**; các hàm được **Đỗ Ngọc Phi** gọi trong `phase1.py` và `corruption_flow.py`. Không đổi chữ ký hàm của starter repo.

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| :--- | :--- | :--- |
| Smoke test toàn luồng với `LLM_PROVIDER=mock` trước khi tích hợp (index → evaluate → corruption giả lập → report) | Đỗ Ngọc Phi (`phase1.py`, `corruption_flow.py`) | Xác nhận hàm của tôi ghép được với `LocalEmbeddingIndex.build` và `evaluate_pipeline`; ghi chú contract tích hợp trong `docs/TEAM.md` (tên report, cần tính lại `age_days` sau khi lùi ngày) |
| Phân tích từng câu hỏi trên dữ liệu corrupted | Báo cáo nhóm | Phát hiện LLM judge chấm đúng cho câu trả lời rỗng và một câu trả lời "đúng" lấy từ sai tài liệu (mục 8) |

---

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| :--- | :--- | :--- | :--- |
| Quality Gate GX 1.x | `quality.py`, `data/quality/{baseline,corrupted,repaired}_quality_report.json` | Baseline PASS 6/6, Corrupted FAIL 4/6, Repaired PASS 6/6 | Lệnh CP1 in `Quality check status = True`; file JSON trong `data/quality/` |
| Freshness SLA | `quality.py`, `data/quality/{freshness,corrupted_freshness,repaired_freshness}_report.json` | Baseline 1/24 stale (fresh), Corrupted 8/22 = 36.36% (not fresh), Repaired 1/24 (fresh) | File JSON trong `data/quality/` |
| Test set | `testset.py`, `data/eval/test_set.json` | 10 câu: 3 summary / 3 authors / 2 date / 2 categories | Lệnh CP2 in `Sinh được 10 câu hỏi test` |
| Report phase 1 và report 3 trạng thái | `reporting.py`, `data/reports/phase1_report.md`, `data/reports/corruption_report.md` | Bảng metrics 3 cột + Δ, quality, freshness, phân tích sinh từ số liệu | Mở 2 file report sau `run_phase1.py` / `run_corruption_flow.py` |
| Kiểm thử | `tests/test_observability.py` (Phi viết) | 54/54 test pass; coverage `quality.py` 98%, `reporting.py` 99% | `PYTHONUTF8=1 python -m pytest` |

---

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Dữ liệu bẩn không làm pipeline crash — agent vẫn trả lời trơn tru nhưng sai (silent failure). Phần của tôi cung cấp ba thứ: một chốt kiểm tra cấu trúc trước khi index (Quality Gate), một tín hiệu độ cũ theo thời gian (Freshness SLA), và một bộ đề thi cố định cộng báo cáo để đo và chứng minh mức suy giảm.

### Cách triển khai

1. **Quality Gate (GX 1.x):** `gx.get_context(mode="ephemeral")` → `data_sources.add_pandas` → `add_dataframe_asset` → `add_batch_definition_whole_dataframe` → `get_batch(batch_parameters={"dataframe": df})`, rồi `batch.validate(ExpectationSuite)` với:
   - `ExpectTableRowCountToBeBetween(5, 5000)`
   - `ExpectColumnValuesToNotBeNull` cho `paper_id`, `title`, `text_for_embedding`
   - `ExpectColumnValuesToBeUnique("paper_id")`
   - `ExpectColumnValueLengthsToBeBetween("summary", min_value=30)`

   Mỗi kết quả GX được rút gọn thành `expectation`, `column`, `success`, `observed_value`/`unexpected_count` và tối đa 5 giá trị lỗi mẫu. `success` chỉ phụ thuộc GX; trạng thái freshness được ghi kèm trong `freshness_sla` để tham khảo nhưng không làm thay đổi gate.
2. **Freshness SLA:** bài quá hạn khi `age_days > settings.freshness_threshold_days` (180); `is_fresh = stale_ratio <= 25%`. Dùng cột `age_days` có sẵn; nếu thiếu thì tự tính từ `published`. DataFrame rỗng → `is_fresh = False`.
3. **Test set:** lọc paper hợp lệ (đủ cột, không rỗng, title không chứa `'` vì QA tìm title bằng regex `'([^']+)'`), sort theo `paper_id`, chọn 10 paper cách đều nhau và xoay vòng 4 loại câu hỏi. Template chứa đúng keyword `retrieval/qa.py` nhận diện (`who authored`, `when was`, `what categories`), ground truth lấy đúng trường QA trả về (`authors_joined`, `published`, `categories_joined`, `first_sentence(summary)`). Không random nên chạy lại luôn ra cùng bộ đề.
4. **Reporting:** bảng Markdown dùng chung; report so sánh có cột Δ (điểm phần trăm) so với baseline; phần Analysis sinh từ chính số liệu truyền vào, không có câu chữ cố định, nên report luôn khớp lần chạy thực tế.

### Input, output và contract

| Thành phần | Mô tả |
| :--- | :--- |
| Input | Clean DataFrame theo Clean schema (`docs/TEAM.md`); metrics summary từ `evaluation/metrics.py::evaluate_pipeline` |
| Output | Quality dict; freshness dict; `test_set.json` theo Test set schema; 2 file Markdown |
| Module phụ thuộc | `core/config.py` (`settings.paths`, `freshness_threshold_days`), `core/utils.py` |
| Module sử dụng output | `pipelines/phase1.py`, `pipelines/corruption_flow.py`, `evaluation/metrics.py`, `observability/dashboard.py` |
| Điều kiện lỗi cần xử lý | Thiếu cột / quá ít paper → `ValueError` khi tạo test set; DataFrame rỗng → `is_fresh = False`; cột thiếu trong GX → expectation fail kèm `exception` |

### Cách xác minh

```bash
python -c "from core.config import load_settings; from observability.quality import run_data_quality_checks; import pandas as pd; s=load_settings(); df=pd.read_json(s.paths.clean_json); res=run_data_quality_checks(df, s, 'test'); print(f'Tín hiệu hoàn thành: Quality check status = {res[\"success\"]}')"
python -c "from core.config import load_settings; from evaluation.testset import build_test_set; import pandas as pd; s=load_settings(); df=pd.read_json(s.paths.clean_json); ts=build_test_set(df, s.paths.eval_testset); print(f'Tín hiệu hoàn thành: Sinh được {len(ts)} câu hỏi test')"
```

- Kết quả thực tế: `Quality check status = True` và `Sinh được 10 câu hỏi test`.
- Toàn luồng: `python script/run_phase1.py` và `python script/run_corruption_flow.py` sinh đủ các file trong `data/quality/` và `data/reports/`.

---

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** `retrieval/qa.py` trả lời theo keyword và tìm title trong nháy đơn, không dùng LLM. Nếu câu hỏi viết tự do, baseline có thể sai ngay trên dữ liệu sạch, khiến so sánh 3 trạng thái mất ý nghĩa.
- **Các phương án:** (1) sinh câu hỏi tự do hoặc bằng LLM; (2) template khớp contract của QA, ground truth lấy đúng trường QA trả về.
- **Phương án chọn:** (2).
- **Lý do:** baseline phải là mốc "đúng" ổn định để mọi suy giảm ở pha corrupted quy được về chất lượng dữ liệu, không phải do đề thi. Bộ đề tất định nên chạy lại cho cùng kết quả.
- **Bằng chứng:** baseline thực tế đạt Hit Rate 100%, Token F1 100%, Judge Accuracy 100% (`data/results/baseline_metrics.json`).
- **Đánh đổi:** vì QA tìm title chính xác trước khi search, Hit Rate gần như không phản ánh lỗi dữ liệu (chỉ giảm 10 pp) — xem mục 8.

---

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng:** chạy lệnh tín hiệu CP1 trên terminal Windows báo `UnicodeEncodeError: 'charmap' codec can't encode character 'ệ'`, dù hàm đã chạy xong.
- **Nguyên nhân gốc:** console dùng code page không hỗ trợ tiếng Việt khi `print` chuỗi "Tín hiệu hoàn thành".
- **Cách xử lý:** đặt `PYTHONIOENCODING=utf-8` trước khi chạy (PowerShell: `$env:PYTHONIOENCODING="utf-8"`).
- **Xác minh:** lệnh in đúng `Tín hiệu hoàn thành: Quality check status = True`; file JSON output giống hệt lần chạy lỗi.
- **Liên quan:** cùng nguyên nhân, 4 test trong `tests/` gọi `read_text()` không truyền `encoding` nên fail trên Windows (report của tôi ghi UTF-8 đúng); chạy với `PYTHONUTF8=1` thì 54/54 pass. Đã báo lại cho nhóm.
- **Điều học được:** tách lỗi hiển thị khỏi lỗi logic — kiểm tra file output trước khi sửa code.

---

## 7. Hiểu biết về luồng end-to-end

1. **Crossref → vector index:** raw JSON → `PaperRecord` → clean DataFrame với `text_for_embedding` 5 phần → MiniLM embedding → ChromaDB collection `papers-baseline`.
2. **Evaluation set:** mỗi câu có `ground_truth_doc_ids`; Hit Rate = tỷ lệ câu có đúng doc trong top-k; Token F1 so câu trả lời với `ground_truth`; LLM judge (OpenAI `gpt-4o-mini`) chấm 1–5.
3. **Quality checks vs freshness:** GX kiểm tra cấu trúc/toàn vẹn (số dòng, null, trùng khóa, độ dài summary); freshness kiểm tra độ cũ (`age_days > 180`, ngưỡng 25%). Dữ liệu có thể đúng schema mà vẫn cũ, nên cần cả hai.
4. **Cùng test set cho 3 pha:** để biến số duy nhất là dữ liệu.
5. **Repair thành công khi:** GX `success = True`, `is_fresh = True`, metrics repaired bằng baseline — đều đạt trong lần chạy thực tế.

---

## 8. Phân tích kết quả

Số liệu từ lần chạy chính thức (`data/results/*_metrics.json`, `data/quality/*.json`, `data/results/corruption_log.json`, seed 42).

### Metrics chính

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét |
| :--- | :---: | :---: | :---: | :--- |
| `retrieval_hit_rate` | 1.00 | 0.90 | 1.00 | Giảm ít nhất vì QA tìm title chính xác trước khi search |
| `mean_token_f1` | 1.00 | 0.58 | 1.00 | Tín hiệu nhạy nhất (−41.8 pp) |
| `judge_accuracy` | 1.00 | 0.70 | 1.00 | Đánh giá thấp mức suy giảm (xem bên dưới) |
| `mean_judge_score` | 5.0 | 3.8 | 5.0 | |
| Quality Gate (GX) | PASS 6/6 | FAIL 4/6 | PASS 6/6 | Fail: unique `paper_id` (6 dòng), độ dài `summary` (3 dòng) |
| Freshness | 1/24 stale, fresh | 8/22 = 36.36%, **not fresh** | 1/24, fresh | `oldest_published` lùi về 2025-03-28 |

### Mỗi lỗi được phát hiện ở đâu và ảnh hưởng câu hỏi nào

| Lỗi tiêm (số dòng) | GX | Freshness | Câu hỏi bị ảnh hưởng |
| :--- | :---: | :---: | :--- |
| `drop_latest_records` (5) | Không (22 dòng vẫn trong 5–5000) | Không cảnh báo (`latest_published` 2026-07-22 → 2026-06-12 nhưng không có ngưỡng) | eval_004: doc đúng đã mất, Hit = False, nhưng câu trả lời vẫn "đúng" vì lấy từ bài gần trùng *Advanced Perspectives on Multi-Agent Consensus…* có cùng categories |
| `blank_summary` (3) | **Có** (độ dài `summary`) | — | eval_001, eval_005: trả lời **rỗng**, Token F1 = 0 |
| `inject_noise` (3) | Không | — | eval_009: trả lời lẫn `%%%`, `@@##`, Token F1 = 0.82, judge = sai |
| `truncate_title` (3) | Không | — | eval_002, eval_006: vẫn đúng — semantic search còn tìm được doc qua authors/summary |
| `stale_date` (8) | Không | **Có** (36% > 25%) | eval_003, eval_007: trả lời ngày lệch 1 năm, Token F1 = 0 |
| `duplicate_rows` (3) | **Có** (unique `paper_id`) | — | Không thấy ảnh hưởng trong 10 câu |

### Kết luận từ số liệu

1. **Gate bắt được 3/6 loại lỗi** (GX 2, Freshness 1). `drop_latest_records`, `inject_noise`, `truncate_title` lọt qua. Nếu pipeline chỉ dựa vào gate thì 3 lỗi này là silent failure thật.
2. **LLM judge không đáng tin khi câu trả lời rỗng:** eval_001 và eval_005 trả lời chuỗi rỗng nhưng `gpt-4o-mini` vẫn chấm 4/5, `correct = true`. Thực tế có 5/10 câu sai (001, 003, 005, 007, 009) chứ không phải 3/10 như `judge_accuracy = 0.70`. Token F1 (0.58) phản ánh sát hơn.
3. **Hit Rate là tín hiệu yếu với bộ đề này:** chỉ giảm 10 pp, vì QA tìm title chính xác trước khi search. eval_004 cho thấy một câu trả lời trông đúng nhưng lấy từ sai tài liệu — đúng kiểu silent failure bài lab mô tả.
4. **Repair idempotent:** tái tạo từ raw đưa mọi metric và cả hai gate về đúng mức baseline.

---

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. Quality gate và freshness bắt các loại lỗi khác nhau; nhưng cả hai cộng lại vẫn bỏ lọt một nửa số lỗi — gate chỉ tốt bằng các expectation được viết.
2. Không tin một metric duy nhất: judge LLM chấm dễ với câu trả lời rỗng, Hit Rate bị che bởi lookup chính xác; cần đọc từng câu trả lời.
3. Báo cáo nên sinh trực tiếp từ artifact để số liệu luôn khớp lần chạy thực tế.

### Nếu có thêm thời gian

- Thêm expectation: `title` dài ≥ 8 ký tự (bắt `truncate_title`); `summary` khớp regex không chứa chuỗi ký tự rác như `[%@#]{2,}` (bắt `inject_noise`).
- Freshness: cảnh báo khi `latest_published` lùi so với lần chạy trước, hoặc row count giảm > 10% (bắt `drop_latest_records`).
- Judge: tự chấm `correct = false` khi câu trả lời rỗng trước khi gọi LLM.
- Report so sánh: đọc `corruption_log.json` để sinh sẵn bảng "lỗi → gate → câu hỏi bị ảnh hưởng" như trên.

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
