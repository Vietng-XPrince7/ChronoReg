# Báo cáo làm sạch, khử trùng lặp và thống nhất CTĐT — 23/11/2026

## Phạm vi và quyết định

Nguồn đối chiếu: `ChronoReg-main (12).zip`; các thư mục `data/raw/uet/curricula`, `data/raw/uet/markdown/curricula`, manifest/versions/checksums, source cards; đối chiếu trạng thái `main` tại thời điểm sửa. **Chưa thay đổi nội dung nguyên bản hoặc kiến thức quy chế ngoài CTĐT**.

1. **53 bản sao nội dung thực sự**: `data/raw/uet/markdown/curricula/tuan_2022_2026/*.md` là Markdown chứa YAML metadata, thông báo và **nguyên văn** file gốc trong `data/raw/uet/curricula/tuan_2022_2026/original/`. Đã tách chính xác đoạn sau marker `## Nội dung từ tài liệu nguồn (giữ nguyên)`, đối chiếu UTF-8 byte và SHA-256 với từng bản gốc: **53/53 trùng 100%**. Chỉ xóa bản **wrapper**, giữ nguyên bản gốc và metadata (doc_id, program_hint, cohort_hint, nguồn, SHA, review flags) trong manifest.
2. **54 bản gốc vẫn còn**: 53 CTĐT, 1 tài liệu hướng dẫn tuyển sinh không nằm trong danh mục CTĐT. Không xóa nhầm.
3. **31 Markdown nội dung chính thức, 31 source cards** đều giữ nguyên; source cards không có toàn bộ CTĐT nên **không** được xác nhận là bản sao nội dung. 110 dấu SHA nguồn được ghi lại ở `source_checksums.json` là 110 giá trị phân biệt. Không xóa các phiên bản học vụ có nội dung tương tự nhưng khác nguồn, khóa, tên ngành, hoặc tín chỉ.
4. **76 lần xuất hiện lặp trong ZIP gốc của Tuấn** vốn đã được khử khi nhập thành 54 tài liệu từ 130 vị trí lưu. Không tính 76 này là 76 file xóa lần này.
5. **84 nội dung chính tắc** (31 website + 53 gốc Tuấn), thống nhất ở `data/raw/uet/curricula/catalog.json`, với trường `content_path`, `content_sha256`, `collection`, `program_identifier`, `cohort_from`, `cohort_to`, `cohort_hint_unverified`, `edition`, `source_url`, `review_status`, `retrieval_eligible`. Một tài liệu gốc -> một `content_path`.
6. Cập nhật `manifest.json` và `versions.csv` của hai kho theo đường dẫn trên; `normalized_path=null` thay vì đường dẫn chết tới bản sao đã xóa. Phần sinh dữ liệu bảy ngành được sửa để lần sinh sau có `content_md_path` và `source_card_path` nhất quán. `INDEX.md` mở Markdown nội dung thật thay vì nhảy ngay sang link ngoài.

## Các trường hợp tương tự nhưng **không** phải dữ liệu trùng có thể xóa

- `civil-engineering` QH-2025 vs QH-2026-plus: TF-IDF cosine khoảng **0,958**; khác khóa và tên ngành, URL trang nguồn và SHA khác nhau.
- `space-engineering` QH-2025 vs QH-2026-plus: cosine khoảng **0,939**; khác khóa và nguồn trích, không xóa.
- AI QH-2022-to-2024-original vs updated: cùng ngành/khóa nhưng **124 vs 123 tín chỉ**; cần xác minh ngày văn bản cập nhật có hiệu lực trước khi lựa chọn.
- Các cặp CNTT chương trình chuẩn, chất lượng cao, Nhật Bản có đoạn tương tự nhưng **khác chương trình đào tạo**; giữ nguyên.

Phân tích độ tương tự chỉ dùng để **lập danh sách nghi ngờ**; chưa đủ làm căn cứ xóa. Trong bản snapshot này, ngoài 53 wrapper sao chép toàn bộ body, không xác minh được cặp Markdown chính tắc nào có cùng toàn bộ nội dung và metadata khóa/phiên bản.

## Kiểm tra/giới hạn

- 53/53 bản gốc có SHA-256 khớp manifest; 31/31 Markdown UET khớp `source_checksums.json`.
- Không thay đổi dữ liệu đầu vào RAG/LoRA hoặc cờ phê duyệt; tất cả 84 mục trong danh mục hiện có `retrieval_eligible=false`.
- Còn cần **người có trách nhiệm đối chiếu nội dung nguồn, ngày hiệu lực và lớp khóa áp dụng**. Khử trùng lặp không có nghĩa bộ dữ liệu đã được phê duyệt đưa vào hệ thống trả lời tự động.
- Trong repository, truy xuất `data/raw/uet/markdown/curricula/*.md` không tự lấy `source_cards` hoặc bản gốc Tuấn; nếu Tuấn có nhánh RAG riêng, cần kiểm tra thêm nhánh đó trước khi đưa mọi thay đổi pipeline lên `main`.

## Công cụ kiểm tra

`python scripts/rebuild_curricula_catalog.py --check` (đối chiếu danh mục và 84 SHA, đảm bảo không còn file wrapper/chỉ dẫn chết, khóa retrieval), `python scripts/audit_owner_7_curricula.py --expect-clean` (đối chiếu dữ liệu bảy ngành chính thức), `pytest tests/test_curricula_catalog.py` (hồi quy). Bằng chứng 53 cặp và SHA ở `data/raw/uet/curricula/DEDUP_EVIDENCE.json`.

## Cảnh báo xung đột với nhánh đang làm của Tuấn (phát hiện 23/11/2026)

Nhánh GitHub `feature/rag-versioned`, commit `e6686dc9b623b178324d7e9caff8e210743726e8`, hiện **chưa được merge**, đã xóa **5 Markdown gốc có nội dung khác nhau** trong `data/raw/uet/curricula/tuan_2022_2026/original/` và chỉnh manifest từ 54 xuống 49 tài liệu. Năm tài liệu gồm:

1. `chuan_dau_ra_chuong_trinh_dao_tao_cntt_clc_2022_tro_di.md`
2. `chuan_dau_ra_chuong_trinh_dao_tao_cntt_nhat_ban_2022_tro_di.md`
3. `gioi_thieu_chung_ve_chuong_trinh_dao_tao_cntt_clc_2022_tro_di.md`
4. `gioi_thieu_chung_ve_chuong_trinh_dao_tao_cntt_nhat_ban_2022_tro_di.md`
5. `noi_dung_chuong_trinh_dao_tao_cntt_clc_2022_tro_di.md`

**Không được coi năm bản này là bản trùng có thể xóa.** Các chương trình CNTT chuẩn, CNTT CLC và định hướng Nhật Bản có nội dung khác nhau, SHA-256 nguồn khác nhau; tương đồng văn phong không đồng nghĩa cùng chương trình. Giữ 54 bản gốc và mọi phiên bản riêng trong `main`.

**Quy tắc tích hợp:** merge nhánh dữ liệu chuẩn hóa này trước, sau đó **rebase/reconcile** nhánh RAG của Tuấn. Không merge nguyên vẹn phần xóa năm bản gốc hoặc reintroduce 53 wrapper phụ từ nhánh cũ. Các test catalog sẽ chặn việc thiếu tài liệu chính tắc. Cần Tuấn kiểm tra riêng phần thay đổi thuật toán RAG và chạy test lại trước khi merge.

Nhánh `feature/rag-versioned` còn để `source_records=130`, `unique_source_records=49`, `duplicate_archive_occurrences=76`; các số này **không nhất quán** vì `49 + 76 = 125`, không phải 130. Bộ kiểm toán mới kiểm tra công thức tổng và số bản ghi để lỗi này không bị bỏ qua khi hợp nhất.

---

## Cập nhật sau báo cáo gốc — quyết định của chủ dự án ngày 23/11/2026

Khuyến nghị bảo toàn 5 bản gốc được ghi trong báo cáo trên là quan điểm kiểm toán trước khi có quyết định mới. **Chủ dự án sau đó đã yêu cầu xóa 5 bản gốc riêng biệt của CNTT CLC và CNTT Nhật Bản**. Thao tác này là loại trừ theo phạm vi dự án, **không phải xóa dữ liệu trùng**. Bản ghi và SHA-256 được giữ tại `tuan_2022_2026/manifest.json` (`owner_excluded_documents`) và báo cáo `docs/data/CURRICULA_OWNER_EXCLUSION_20261123.md`. Chỉ có 48/53 CTĐT gốc do nhóm cung cấp còn hoạt động; catalog còn 79. Các số 54 và 130 mô tả *lịch sử dữ liệu đầu vào ban đầu*, không phải số file còn trên ổ.
