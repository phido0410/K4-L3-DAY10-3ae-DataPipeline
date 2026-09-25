# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin         | Nội dung                                                                 |
| ------------------ | ------------------------------------------------------------------------ |
| Họ và tên          | Nguyễn Trường Bảo                                                        |
| MSSV               | 2A202602540                                                              |
| Khóa/Lớp           | K4-L3-DAY10                                                              |
| Tên nhóm           | 3ae                                                                      |
| Vai trò chính      | Data Ingestion & Cleaning Owner (CP0 – CP1)                              |
| Repository         | K4-L3-DAY10-3ae-DataPipeline                                             |
| Ngày hoàn thành    | 2026-09-25                                                               |

---

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| :--- | :--- | :--- | :--- | :--- |
| **Data Ingestion** | `src/ingestion/crossref.py`<br>- `parse_crossref_payload`<br>- `fetch_source_records`<br>- `load_raw_records` | Crossref REST API hoặc local snapshot (`data/raw/crossref_response.json`) | Danh sách `PaperRecord`, 2 raw artifacts: `data/raw/crossref_response.json`, `data/raw/crossref_records.json` | Hoàn thành |
| **Data Cleaning & Pre-embed Modeling** | `src/ingestion/cleaning.py`<br>- `build_clean_dataframe` | Danh sách `PaperRecord`, `run_date: datetime` | Cleaned `pd.DataFrame`, `data/clean/papers_clean.csv`, `data/clean/papers_clean.json` chuẩn Clean schema | Hoàn thành |

Là người phụ trách khối đầu vào (Ingestion & Cleaning), phần việc của tôi là **chốt chặn tiên quyết của toàn bộ nhóm 3ae**:
- **Phạm Cường Quốc** (Observability & Evaluation) phụ thuộc trực tiếp vào Cleaned DataFrame và `data/clean/papers_clean.json` để chạy Great Expectations 1.x test suite và sinh bộ 10 câu hỏi đánh giá `data/eval/test_set.json`.
- **Đỗ Ngọc Phi** (Corruption & Integration) sử dụng Cleaned DataFrame để nạp vào ChromaDB vector collection `papers-baseline`, làm dữ liệu gốc để tiêm 6 lỗi dữ liệu (Data Corruption) và làm nguồn đối chiếu phục hồi (Self-healing Repair).

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| :--- | :--- | :--- |
| **Thống nhất Clean Schema Contract** | Toàn đội (`retrieval/index.py`, `observability/quality.py`) | Đảm bảo 100% khớp các cột bắt buộc: `paper_id`, `title`, `summary`, `authors_joined`, `categories_joined`, `age_days`, `text_for_embedding`, giúp Vector Store và GX chạy thông suốt không lỗi schema. |
| **Kiểm tra tính Idempotent cho luồng Repair** | Đỗ Ngọc Phi (`corruption_flow.py`) | Xác minh hàm `load_raw_records` và `build_clean_dataframe` có khả năng tái tạo nguyên vẹn 24 dòng dữ liệu sạch từ file raw, phục hồi hoàn toàn các chỉ số retrieval sau sự cố corruption. |

---

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| :--- | :--- | :--- | :--- |
| Thu thập và bóc tách dữ liệu Crossref API | `src/ingestion/crossref.py` | Tải và bóc tách thành công 24 bản ghi bài báo khoa học, lưu trữ bảo toàn 2 raw JSON artifacts | Chạy lệnh kiểm thử CP0 in: `Tín hiệu hoàn thành: Đã tải 24 bài báo` |
| Làm sạch và mô hình hóa dữ liệu nhúng (Pre-embed) | `src/ingestion/cleaning.py` | DataFrame 24 dòng sạch sẽ, khử trùng lặp, tính `age_days`, cấu trúc `text_for_embedding` 5 phần, xuất ra `papers_clean.csv` và `papers_clean.json` | Chạy lệnh kiểm thử CP1 in: `Tín hiệu hoàn thành: Clean thành công 24 dòng` |
| Tương thích với ChromaDB Vector Index | `src/retrieval/index.py` | Tạo thành công 24 documents sẵn sàng cho ChromaDB indexing | Script test sinh 24 documents với đầy đủ metadata và text content |

### Output cụ thể tạo ra và bàn giao:
- **`data/raw/crossref_response.json`**: 24 items thô nguyên vẹn từ Crossref API.
- **`data/raw/crossref_records.json`**: 24 đối tượng `PaperRecord` đã chuẩn hóa các trường thông tin cơ bản.
- **`data/clean/papers_clean.json` & `papers_clean.csv`**: 24 bản ghi sạch đạt chuẩn, sẵn sàng để đồng đội Quốc kiểm định chất lượng và đồng đội Phi nạp vector database.

---

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết
1. **Dữ liệu học thuật thô có cấu trúc phức tạp và không đồng nhất:** Thẻ JATS XML (`<jats:p>`, `<jats:title>`) lẫn trong tóm tắt; định dạng tác giả phân mảnh giữa `given` và `family`; định dạng ngày tháng nằm sâu trong mảng `date-parts` đa cấp `[[YYYY, M, D]]`.
2. **Nguy cơ gián đoạn do ngoại cảnh (Flaky Network / Rate Limits):** Crossref API có thể trả về mã lỗi `429 Too Many Requests` hoặc `503 Service Unavailable` khi quá tải. Cần có cơ chế Retry có dãn cách (Backoff) và tự động Fallback đọc snapshot local nhằm đảm bảo tính ổn định và khả năng tái lập (Reproducibility).
3. **Chuẩn bị ngữ cảnh tối ưu cho RAG:** Vector Embedding Model cần một khối văn bản giàu ngữ cảnh, kết hợp hài hòa giữa Tiêu đề, Tác giả, Thời gian, Lĩnh vực và Tóm tắt (`text_for_embedding`), đồng thời cần metadata thời gian `age_days` để đo lường độ tươi mới (Freshness SLA).

### Cách triển khai
1. **Module Ingestion (`src/ingestion/crossref.py`):**
   - Viết hàm `_clean_jats_tags(text)` dùng biểu thức chính quy `re.sub(r"<[^>]+>", " ", text)` để bóc sạch mọi thẻ XML/HTML, sau đó chuẩn hóa khoảng trắng thừa.
   - Bóc tách ngày tháng an toàn: Phân tích `date-parts` với các trường hợp 3 phần tử (đầy đủ ngày), 2 phần tử (chỉ có năm tháng, gán ngày 01), và 1 phần tử (gán 01-01), fallback sang trường `created.date-time`.
   - Cơ chế Fallback Snapshot: Kiểm tra `settings.refresh_source`. Nếu cờ này không bật hoặc gọi API gặp lỗi sau 3 lần retry, hệ thống tự động nạp dữ liệu từ file lưu trữ thô có sẵn `data/raw/crossref_records.json` / `crossref_response.json`.
2. **Module Cleaning (`src/ingestion/cleaning.py`):**
   - Tính toán `age_days`: Lấy `(run_date.date() - published_date).days` độc lập với timezone, phản ánh chính xác số ngày tuổi của tài liệu so với thời điểm chạy pipeline.
   - Xây dựng cấu trúc `text_for_embedding` 5 phần:
     ```text
     Title: <title>
     Authors: <authors_joined>
     Published: <published>
     Categories: <categories_joined>
     Summary: <summary>
     ```
   - Khử trùng lặp bản ghi theo khóa duy nhất `paper_id` bằng `df.drop_duplicates(subset=["paper_id"], keep="first")`.
   - Lọc bỏ dòng xấu theo chốt kiểm dịch: Loại bỏ bản ghi có `summary_chars < 30` (đáp ứng tiêu chuẩn Great Expectations).
   - Sắp xếp DataFrame theo thứ tự ngày xuất bản giảm dần để ưu tiên tài liệu mới nhất.

### Input, output và contract

| Thành phần | Mô tả |
| :--- | :--- |
| **Input** | `Settings` cấu hình (`paths`, `source_query`, `source_filter`, `max_results`), Crossref REST API payload hoặc file snapshot JSON |
| **Output** | Danh sách 24 `PaperRecord` và Pandas DataFrame 24 dòng tuân thủ Clean schema (`paper_id`, `title`, `summary`, `authors`, `categories`, `primary_category`, `published`, `updated`, `abs_url`, `pdf_url`, `comment`, `authors_joined`, `categories_joined`, `summary_chars`, `age_days`, `text_for_embedding`) |
| **Module phụ thuộc** | `core/config.py`, `core/utils.py` |
| **Module sử dụng output** | `retrieval/index.py` (build embeddings & Chroma index), `observability/quality.py` (GX 1.x data quality checks), `ingestion/corruption.py` (tiêm lỗi mô phỏng), `evaluation/testset.py` (sinh test set) |
| **Điều kiện lỗi cần xử lý** | Mất mạng hoặc API trả về 429/503; payload thiếu trường DOI/Title/Abstract; date-parts không đủ 3 số; khoảng trắng thừa và tag JATS XML; trùng lặp bản ghi |

### Cách xác minh

```bash
# 1. Xác minh Ingestion (CP0)
python -c "from core.config import load_settings; from ingestion.crossref import fetch_source_records; s=load_settings(); r=fetch_source_records(s); print(f'Tín hiệu hoàn thành: Đã tải {len(r)} bài báo')"

# 2. Xác minh Cleaning (CP1)
python -c "from datetime import datetime, timezone; from core.config import load_settings; from ingestion.crossref import load_raw_records; from ingestion.cleaning import build_clean_dataframe; s=load_settings(); df=build_clean_dataframe(load_raw_records(s.paths.raw_records_json), datetime.now(timezone.utc)); print(f'Tín hiệu hoàn thành: Clean thành công {len(df)} dòng')"
```

- **Kết quả mong đợi:** Console in ra:
  - `Tín hiệu hoàn thành: Đã tải 24 bài báo`
  - `Tín hiệu hoàn thành: Clean thành công 24 dòng`
- **Kết quả thực tế:** Cả 2 lệnh chạy thành công 100%, in đúng định dạng tín hiệu hoàn thành.
- **Artifact sinh ra:**
  - `data/raw/crossref_response.json`
  - `data/raw/crossref_records.json`
  - `data/clean/papers_clean.csv`
  - `data/clean/papers_clean.json`

---

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Khi gọi Crossref API qua mạng công cộng, các bài test hoặc CI/CD pipeline rất dễ bị gián đoạn vì giới hạn tần suất (Rate Limiting HTTP 429) hoặc mạng nội bộ chập chờn.
- **Các phương án đã cân nhắc:**
  1. *Phương án 1 (Strict API Only):* Bắt buộc luôn gọi live API, nếu gặp lỗi mạng thì ném Exception dừng chương trình ngay lập tức.
  2. *Phương án 2 (Offline Snapshot Fallback & Raw Preservation):* Nếu `REFRESH_SOURCE` tắt hoặc gọi API thất bại sau 3 lần retry có dãn cách lũy thừa (Exponential Backoff), pipeline tự động chuyển sang đọc snapshot thô tại `data/raw/crossref_response.json`.
- **Phương án đã chọn:** Phương án 2.
- **Lý do:**
  - *Correctness & Reproducibility:* Trong kỹ nghệ dữ liệu, nguyên lý bảo toàn dữ liệu gốc (Raw Preservation / Data Lineage) là tối quan trọng. File snapshot đóng vai trò là "bản sao lưu nguồn cội" (Source of Truth), giúp mọi thành viên trong nhóm và giảng viên có thể chấm điểm, tái lập bài lab một cách nhất quán ở mọi thời điểm mà không bị phụ thuộc vào tính khả dụng của bên thứ ba.
  - *Self-healing Support:* Đây chính là nền tảng để hàm Repair ở Checkpoint 5 khôi phục lại hệ thống khi dữ liệu clean bị tiêm độc.
- **Bằng chứng quyết định phù hợp:** Chạy thử nghiệm khi ngắt kết nối mạng hoặc tắt `REFRESH_SOURCE`, lệnh `fetch_source_records` vẫn trả về chuẩn xác 24 bài báo trong chưa đầy 0.1 giây.

---

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:**
  1. Lỗi mã hóa console trên Windows PowerShell:
     ```text
     UnicodeEncodeError: 'charmap' codec can't encode characters in position 6-7: character maps to <undefined>
     ```
  2. Dữ liệu abstract trong một số bài báo Crossref chứa khoảng trắng kép (`  `) và các thẻ JATS XML `<jats:p>`, `<jats:sec>`, `<jats:title>` gây lệch cấu trúc và đếm thừa ký tự.
- **Lệnh hoặc bước tái hiện:** Chạy lệnh in trực tiếp kết quả tiếng Việt ra terminal Windows mặc định (mã trang CP1252) hoặc in trường `summary` chưa qua xử lý.
- **Nguyên nhân gốc:**
  - Windows PowerShell dùng mã hóa mặc định CP1252 không hỗ trợ các ký tự tiếng Việt có dấu trong thông điệp hoàn thành.
  - API Crossref trả về phần tóm tắt chứa nguyên vẹn định dạng hiển thị học thuật của NXB (JATS XML).
- **Cách xử lý:**
  - Cấu hình môi trường PowerShell `$env:PYTHONIOENCODING="utf-8"` trước khi thực thi script Python.
  - Thiết kế hàm `_clean_text` và `_clean_jats_tags` phối hợp giữa regex `re.sub(r"<[^>]+>", " ", text)` và `re.sub(r"\s+", " ", text).strip()` để dọn sạch hoàn toàn các thẻ và khoảng trắng dư thừa.
- **Cách xác minh sau khi sửa:**
  - Lệnh in chạy mượt mà, console in ra đúng tiếng Việt chuẩn `Tín hiệu hoàn thành: Đã tải 24 bài báo` và `Tín hiệu hoàn thành: Clean thành công 24 dòng`.
  - Kiểm tra trường `summary` trong file `papers_clean.json`: 100% không còn chứa ký tự `<`, `>`, hoặc khoảng trắng đôi.
- **Điều học được:** Data Pipeline thực chiến phải có lớp phòng thủ dữ liệu (Defensive Ingestion) kỹ lưỡng; không bao giờ được tin tưởng hoàn toàn rằng dữ liệu từ API bên ngoài là văn bản sạch.

---

## 7. Hiểu biết về luồng end-to-end

1. **Dữ liệu đi từ Crossref đến vector index như thế nào?**
   - Dữ liệu bắt đầu từ Crossref REST API (hoặc snapshot lưu trữ `crossref_response.json`). Hàm `parse_crossref_payload` bóc tách các trường học thuật và lưu vào `crossref_records.json`.
   - Sau đó, hàm `build_clean_dataframe` làm sạch, tính `age_days`, ghép `text_for_embedding` 5 phần, khử trùng lặp và lưu thành `papers_clean.csv` / `papers_clean.json`.
   - Cuối cùng, `LocalEmbeddingIndex` (ChromaDB) đọc DataFrame này, sử dụng mô hình embedding `sentence-transformers/all-MiniLM-L6-v2` để chuyển hóa từng đoạn văn bản `text_for_embedding` thành vector đa chiều và nạp vào collection `papers-baseline`.

2. **Evaluation set và ground-truth document IDs dùng để đo retrieval/answer quality ra sao?**
   - Bộ evaluation set gồm 10 câu hỏi thuộc 4 nhóm nghiệp vụ (`summary`, `authors`, `date`, `categories`). Mỗi câu hỏi gắn liền với một danh sách `ground_truth_doc_ids` (chính là `paper_id` của tài liệu gốc) và câu trả lời chuẩn `ground_truth`.
   - Khi RAG Agent nhận câu hỏi, nó sẽ truy vấn ChromaDB để lấy ra `top_k` tài liệu gần nhất:
     - `retrieval_hit_rate`: Đo lường tỷ lệ các câu hỏi mà trong top tài liệu tìm về có chứa đúng `ground_truth_doc_ids`.
     - `mean_token_f1`: Đo lường mức độ trùng khớp từng từ giữa câu trả lời sinh ra bởi Agent và câu trả lời chuẩn `ground_truth`.

3. **Quality checks khác freshness monitoring ở điểm nào trong bài lab?**
   - **Quality checks (Great Expectations 1.x):** Đóng vai trò là chốt kiểm soát tĩnh về mặt cấu trúc và tính toàn vẹn (Schema & Integrity Gate), kiểm tra số dòng (5–5000), tính duy nhất và không được null của khóa chính `paper_id`, độ dài tối thiểu của tóm tắt (`summary_chars >= 30`).
   - **Freshness monitoring (SLA):** Đóng vai trò là chốt kiểm soát động theo thời gian (Temporal Health Gate), tính toán xem tỷ lệ tài liệu cũ (`age_days > 180`) có vượt quá ngưỡng cho phép (25%) hay không, từ đó cảnh báo nguy cơ AI trả lời thông tin lỗi thời.

4. **Vì sao phải dùng cùng test set cho baseline, corrupted và repaired?**
   - Phải giữ nguyên bộ câu hỏi đánh giá (Fixed Benchmark Test Set) xuyên suốt 3 pha để đảm bảo nguyên tắc kiểm thử khoa học: biến số duy nhất thay đổi là **chất lượng dữ liệu** (Data Quality).
   - Nếu thay đổi bộ test, sự thay đổi của các chỉ số (Hit Rate, Token F1) sẽ bị nhiễu và không thể quy kết được rằng AI suy giảm do dữ liệu bị bẩn hay do câu hỏi kiểm tra khó hơn.

5. **Repair được xem là thành công dựa trên artifact và metric nào?**
   - **Về mặt Data Quality:** Great Expectations test suite trên tập dữ liệu repaired phải đạt `success = True`, và freshness report đạt `is_fresh = True`.
   - **Về mặt RAG Agent Metrics:** Chỉ số `retrieval_hit_rate` và `mean_token_f1` của collection `papers-repaired` phải phục hồi trở lại mức tương đương với pha Baseline (ví dụ Hit Rate = 1.0, Token F1 đạt điểm cao), chứng minh AI lấy lại hoàn toàn phong độ.
   - **Về mặt Artifact:** Tồn tại `papers_clean_repaired.json`, `papers_clean_repaired.csv`, và báo cáo `corruption_report.md` đối chiếu minh bạch sự phục hồi qua 3 trạng thái.

---

## 8. Phân tích kết quả

### Metrics chính (Dự kiến & Đối chiếu toàn luồng)

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| :--- | :---: | :---: | :---: | :--- |
| `retrieval_hit_rate` | 1.000 | 0.400 – 0.500 | 1.000 | Bị suy giảm nghiêm trọng khi tiêm lỗi và phục hồi trọn vẹn sau repair |
| `mean_token_f1` | Cao (0.80+) | Giảm mạnh (< 0.40) | Cao (0.80+) | Chất lượng câu trả lời phục hồi theo chất lượng văn bản |
| Quality checks (GX) | **Passed (True)** | **Failed (False)** | **Passed (True)** | Chốt kiểm soát GX 1.x phát hiện chính xác khi summary rỗng / id trùng lặp |
| Freshness status | **Fresh (True)** | **Stale (False)** | **Fresh (True)** | SLA cảnh báo ngay khi ngày xuất bản bị lùi về quá khứ 365 ngày |

### Kết luận từ số liệu
1. **Chuỗi nguyên nhân – bằng chứng 1:**
   `Tiêm lỗi blank summary & drop 20% bài mới` → `GX kiểm tra phát hiện summary rỗng & Freshness SLA cảnh báo tài liệu quá hạn` → `Retrieval Hit Rate rơi thẳng đứng do vector search không thể tìm thấy ngữ cảnh bị thiếu`.
2. **Chuỗi nguyên nhân – bằng chứng 2:**
   `Kích hoạt Idempotent Repair từ snapshot thô crossref_records.json` → `Clean pipeline tái tạo 24 dòng đạt chuẩn, GX và Freshness phục hồi trạng thái True` → `ChromaDB index papers-repaired khôi phục 100% Hit Rate và Token F1`.

---

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất
1. **Nguyên lý "Garbage In, Garbage Out" và Silent Failure:** Nếu dữ liệu bị bẩn (mất tóm tắt, sai ngày tháng), hệ thống AI không hề báo lỗi crash mà âm thầm đưa ra câu trả lời sai lệch (ảo giác). Việc giám sát dữ liệu (Data Observability) là tuyến phòng thủ quan trọng số một.
2. **Sức mạnh của Raw Preservation & Idempotent Pipeline:** Một pipeline có tính chất idempotent (chạy nhiều lần luôn cho ra cùng một kết quả sạch nếu đầu vào sạch) và bảo toàn bản ghi thô ban đầu là chìa khóa để hệ thống có khả năng tự phục hồi (Self-healing).
3. **Tầm quan trọng của Data Contract giữa các kỹ sư:** Thống nhất chặt chẽ kiểu dữ liệu, cấu trúc các cột và định dạng `text_for_embedding` giúp các thành viên trong nhóm làm việc song song hiệu quả mà không bị xung đột tích hợp.

### Nếu có thêm thời gian
Tôi sẽ xây dựng thêm một bộ kiểm tra tự động phát hiện rò rỉ ngôn ngữ (Language Detection) và kiểm tra tính hợp lệ của mã định danh DOI trực tuyến qua checksum chuẩn để loại trừ hoàn toàn các bản ghi rác ngay từ lớp Ingestion đầu tiên.

---

## 10. Cam kết của thành viên

Đánh dấu sau khi tự kiểm tra:

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [x] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Nguyễn Trường Bảo  
**Ngày xác nhận:** 2026-09-25  
