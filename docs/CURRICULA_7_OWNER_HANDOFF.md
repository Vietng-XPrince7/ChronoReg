# Bàn giao dữ liệu 7 ngành UET — khóa QH-2022 đến QH-2026

**Nguồn kiểm tra:** ZIP `ChronoReg-main (6).zip`, commit `f32d4e29e80d93e8efcc350df849387e215a2136`; đối chiếu chỉ mục và trang chương trình chính thức UET ngày 20/11/2026.

## Kết luận thực địa

- **17 hồ sơ** cho 7 ngành: **15 phiên bản chương trình đào tạo áp dụng theo khóa**, **2 đề án mở ngành** (Công nghệ sinh học, Khoa học dữ liệu).
- Có sẵn **17/17 file Markdown toàn văn trích xuất** và **17/17 source card**, tất cả **17 SHA-256** đối chiếu với `source_checksums.json` đều khớp.
- File thực tế nằm ở `data/raw/uet/markdown/curricula/uet-curriculum-*.md`, **KHÔNG** nằm ở `data/raw/uet/curricula/` (thư mục sau chứa manifest, checksums).
- `data/raw/uet/curricula/versions.csv` có đủ 31 hồ sơ cho toàn bộ các ngành của nhóm, trong đó 17 thuộc 7 ngành này.
- Các file *đã tồn tại* không bị ghi đè hoặc tạo lại. Bản vá chỉ sửa trạng thái trích xuất trong metadata và thêm mục lục.
- `retrieval_eligible=false` vẫn giữ: các file còn chờ duyệt nội dung, phạm vi khóa và quan hệ cập nhật; không được gọi là đã được dùng trong production RAG/LoRA.
- Pipeline full-main v5 đã train chỉ sử dụng phần có parser, không đồng nghĩa tất cả 31 tài liệu curricula đã được dùng để train.

## Danh mục file gốc

| Ngành | Phiên bản | QH áp dụng | Tín chỉ | File Markdown | Trang nội dung UET |
| --- | --- | --- | ---: | --- | --- |
| Công nghệ hàng không vũ trụ / Kỹ thuật không gian | QH-2022-to-2024 | 2022–2024 | 152 | [`uet-curriculum-space-engineering-QH-2022-to-2024.md`](../data/raw/uet/markdown/curricula/uet-curriculum-space-engineering-QH-2022-to-2024.md) | [Nội dung](https://uet.edu.vn/chuong-trinh-dao-tao-nganh-cong-nghe-hang-khong-vu-tru-9/) |
| Công nghệ hàng không vũ trụ / Kỹ thuật không gian | QH-2025 | 2025–2025 | 150 | [`uet-curriculum-space-engineering-QH-2025.md`](../data/raw/uet/markdown/curricula/uet-curriculum-space-engineering-QH-2025.md) | [Nội dung](https://uet.edu.vn/chuong-trinh-dao-tao-nganh-cong-nghe-hang-khong-vu-tru-12/) |
| Công nghệ hàng không vũ trụ / Kỹ thuật không gian | QH-2026-plus | 2026–2026+ | 150 | [`uet-curriculum-space-engineering-QH-2026-plus.md`](../data/raw/uet/markdown/curricula/uet-curriculum-space-engineering-QH-2026-plus.md) | [Nội dung](https://uet.vnu.edu.vn/chuong-trinh-dao-tao-ky-thuat-hang-khong-vu-tru-nganh-ky-thuat-khong-gian-3/) |
| Công nghệ kỹ thuật xây dựng / Kỹ thuật xây dựng | QH-2022-to-2024 | 2022–2024 | 150 | [`uet-curriculum-civil-engineering-QH-2022-to-2024.md`](../data/raw/uet/markdown/curricula/uet-curriculum-civil-engineering-QH-2022-to-2024.md) | [Nội dung](https://uet.edu.vn/chuong-trinh-dao-tao-nganh-cong-nghe-ky-thuat-xay-dung-10/) |
| Công nghệ kỹ thuật xây dựng / Kỹ thuật xây dựng | QH-2025 | 2025–2025 | 150 | [`uet-curriculum-civil-engineering-QH-2025.md`](../data/raw/uet/markdown/curricula/uet-curriculum-civil-engineering-QH-2025.md) | [Nội dung](https://uet.edu.vn/chuong-trinh-dao-tao-nganh-cong-nghe-ky-thuat-xay-dung-13/) |
| Công nghệ kỹ thuật xây dựng / Kỹ thuật xây dựng | QH-2026-plus | 2026–2026+ | 150 | [`uet-curriculum-civil-engineering-QH-2026-plus.md`](../data/raw/uet/markdown/curricula/uet-curriculum-civil-engineering-QH-2026-plus.md) | [Nội dung](https://uet.edu.vn/chuong-trinh-dao-tao-nganh-ky-thuat-xay-dung-17/) |
| Thiết kế công nghiệp và đồ họa | QH-2024 | 2024–2024 | 135 | [`uet-curriculum-industrial-graphic-design-QH-2024.md`](../data/raw/uet/markdown/curricula/uet-curriculum-industrial-graphic-design-QH-2024.md) | [Nội dung](https://uet.edu.vn/chuong-trinh-dao-tao-nganh-thiet-ke-cong-nghiep-va-hoa-3/) |
| Thiết kế công nghiệp và đồ họa | QH-2025-plus | 2025–2026+ | 135 | [`uet-curriculum-industrial-graphic-design-QH-2025-plus.md`](../data/raw/uet/markdown/curricula/uet-curriculum-industrial-graphic-design-QH-2025-plus.md) | [Nội dung](https://uet.edu.vn/chuong-trinh-dao-tao-nganh-thiet-ke-cong-nghiep-va-hoa-7/) |
| Công nghệ nông nghiệp | QH-2022-to-2024 | 2022–2024 | 150 | [`uet-curriculum-agricultural-technology-QH-2022-to-2024.md`](../data/raw/uet/markdown/curricula/uet-curriculum-agricultural-technology-QH-2022-to-2024.md) | [Nội dung](https://uet.edu.vn/chuong-trinh-dao-tao-nganh-cong-nghe-nong-nghiep-7/) |
| Công nghệ nông nghiệp | QH-2025-plus | 2025–2026+ | 150 | [`uet-curriculum-agricultural-technology-QH-2025-plus.md`](../data/raw/uet/markdown/curricula/uet-curriculum-agricultural-technology-QH-2025-plus.md) | [Nội dung](https://uet.edu.vn/chuong-trinh-dao-tao-nganh-cong-nghe-nong-nghiep-10/) |
| Công nghệ sinh học | opening-proposal | Đề án, không áp QH | 150 | [`uet-curriculum-biotechnology-opening-proposal.md`](../data/raw/uet/markdown/curricula/uet-curriculum-biotechnology-opening-proposal.md) | [Nội dung](https://uet.edu.vn/chuong-trinh-dao-tao-cong-nghe-ky-thuat-sinh-hoc-nganh-cong-nghe-sinh-hoc-3/) |
| Công nghệ sinh học | QH-2025-plus | 2025–2026+ | 150 | [`uet-curriculum-biotechnology-QH-2025-plus.md`](../data/raw/uet/markdown/curricula/uet-curriculum-biotechnology-QH-2025-plus.md) | [Nội dung](https://uet.edu.vn/chuong-trinh-dao-tao-cong-nghe-ky-thuat-sinh-hoc-nganh-cong-nghe-sinh-hoc-7/) |
| Trí tuệ nhân tạo | QH-2022-to-2024-original | 2022–2024 | 124 | [`uet-curriculum-artificial-intelligence-QH-2022-to-2024-original.md`](../data/raw/uet/markdown/curricula/uet-curriculum-artificial-intelligence-QH-2022-to-2024-original.md) | [Nội dung](https://uet.edu.vn/chuong-trinh-dao-tao-nganh-tri-tue-nhan-tao-3/) |
| Trí tuệ nhân tạo | QH-2022-to-2024-updated | 2022–2024 | 123 | [`uet-curriculum-artificial-intelligence-QH-2022-to-2024-updated.md`](../data/raw/uet/markdown/curricula/uet-curriculum-artificial-intelligence-QH-2022-to-2024-updated.md) | [Nội dung](https://uet.edu.vn/chuong-trinh-dao-tao-nganh-tri-tue-nhan-tao-6/) |
| Trí tuệ nhân tạo | QH-2025-plus | 2025–2026+ | 135 | [`uet-curriculum-artificial-intelligence-QH-2025-plus.md`](../data/raw/uet/markdown/curricula/uet-curriculum-artificial-intelligence-QH-2025-plus.md) | [Nội dung](https://uet.edu.vn/chuong-trinh-dao-tao-nganh-tri-tue-nhan-tao-9/) |
| Khoa học dữ liệu | opening-proposal | Đề án, không áp QH | 130 | [`uet-curriculum-data-science-opening-proposal.md`](../data/raw/uet/markdown/curricula/uet-curriculum-data-science-opening-proposal.md) | [Nội dung](https://uet.edu.vn/chuong-trinh-dao-tao-khoa-hoc-va-ky-thuat-du-lieu-nganh-khoa-hoc-du-lieu-3/) |
| Khoa học dữ liệu | QH-2025-plus | 2025–2026+ | 135 | [`uet-curriculum-data-science-QH-2025-plus.md`](../data/raw/uet/markdown/curricula/uet-curriculum-data-science-QH-2025-plus.md) | [Nội dung](https://uet.edu.vn/chuong-trinh-dao-tao-khoa-hoc-va-ky-thuat-du-lieu-nganh-khoa-hoc-du-lieu-7/) |

## Ranh giới từng năm

- 2022–2023: không tạo file cho Thiết kế công nghiệp và đồ họa, Công nghệ sinh học hoặc Khoa học dữ liệu; chưa có chương trình áp dụng theo khóa này trong chỉ mục chính thức.
- 2024: Thiết kế công nghiệp và đồ họa có chương trình QH-2024; các phiên bản QH-2022–2024 thuộc các ngành còn lại đang tuyển sinh trong nhóm.
- 2025: có chương trình QH-2025 riêng hoặc QH-2025 trở đi; Công nghệ sinh học và Khoa học dữ liệu bắt đầu tuyển sinh theo thông tin chính thức năm 2025.
- 2026: dùng QH-2026 riêng của Hàng không vũ trụ / Kỹ thuật không gian và Xây dựng; các ngành khác có nhãn QH-2025 trở đi nên tiếp tục bao phủ QH-2026, nếu chưa có quyết định đổi mới.
- AI QH-2022–2024 có 124 TC bản gốc, 123 TC bản cập nhật. **Không tự quyết định ngày bản cập nhật thay thế** từ metadata hiện tại.

## Nguồn quan trọng

- UET tuyển sinh mới Công nghệ sinh học và Khoa học dữ liệu năm 2025: https://uet.edu.vn/nam-2025-truong-dai-hoc-cong-nghe-dhqghn-mo-nhieu-nganh-moi-tang-chi-tieu/
- Khoa Công nghệ Xây dựng–Giao thông xác nhận Thiết kế công nghiệp và Đồ họa tuyển sinh từ 2024: https://uet.edu.vn/bo-mon-cong-nghe-xay-dung-giao-thong/
- AI bắt đầu tuyển sinh 2022: https://uet.edu.vn/lop-tien-trinh-dao-tao-tich-cuc-tai-vien-tri-tue-nhan-tao-truong-dai-hoc-cong-nghe-hanh-trinh-pha-va-khang-dinh-ban-linh-sinh-vien-ai/

## Quy trình nghiệm thu trước khi nạp LoRA

1. Chạy `python scripts/audit_owner_7_curricula.py --repo .` để kiểm tra SHA-256, file nguồn và tính đầy đủ bảng học phần.
2. Người phụ trách xác nhận các đoạn quan trọng ở UET, tên ngành, khóa, tín chỉ và bản cập nhật AI; ghi phiếu duyệt riêng, không dùng AI tự xác nhận hộ.
3. Sau khi duyệt, tích hợp có kiểm soát vào `data/versioning` và bộ QA/LoRA; không tự bật `retrieval_eligible` hoặc chạy train trên các tài liệu chưa duyệt.
4. Bảo toàn bản Markdown gốc và checksums; nếu thay đổi nội dung, phải cập nhật checksums và rà soát lại nguồn.

## Trạng thái bàn giao

**ĐÃ CÓ DỮ LIỆU MARKDOWN; CHƯA ĐƯỢC PHÉP PHÁT HÀNH/FINETUNE TỰ ĐỘNG.**

Lý do Tuấn không thấy dữ liệu trong hệ thống RAG: `src/rag/eval_adapter.py` bỏ qua các `doc_id` có `retrieval_eligible=false`. Đây là cổng an toàn có chủ đích, không phải dữ liệu bị mất.

## Các điểm nguồn cần xác minh thủ công trước khi phê duyệt

- **Hàng không vũ trụ QH-2022–2024:** mục `outcomes` trong chỉ mục UET trỏ tới URL có tiêu đề “Chương trình đào tạo ngành Vật lý kỹ thuật”, dù nội dung chuẩn đầu ra trên trang lại nói về hàng không vũ trụ. Đây là sự không nhất quán của nguồn công khai; giữ nguyên link, gắn cờ cần kiểm tra trước khi duyệt.
- **AI QH-2022–2024:** có bản gốc 124 tín chỉ và bản cập nhật 123 tín chỉ; trang danh mục không nêu rõ ngày bản cập nhật thay thế, nên không chọn tự động theo năm lịch.
- **Tính đúng của bảng học phần:** SHA khớp giữa `.md` và `source_checksums.json` chỉ xác nhận file không thay đổi so với snapshot đã ghi, KHÔNG xác nhận lại từng tín chỉ hoặc điều kiện học phần với website UET tại ngày hiện tại.
- **Không chạy nhầm `scripts/build_curricula_markdown_7.py`:** script đang xử lý một nhóm *bảy ngành khác* (Cơ kỹ thuật, Tự động hóa, Cơ điện tử, Vật liệu, Năng lượng, Vật lý kỹ thuật, Kỹ thuật không gian); dữ liệu 7 ngành trong hồ sơ này hiện đã tồn tại, không cần sinh lại.


## Kiểm tra & làm sạch chất lượng nguồn (20/11/2026)

- 17/17 bản `.md` chứa chương trình và bảng học phần; trước khi sửa tất cả khớp checksum ghi tại `source_checksums.json`. Sau khi sửa, 17/17 bản đều được kiểm tra với checksum mới.
- Ba tài liệu Hàng không vũ trụ/Kỹ thuật không gian bị lẫn chân trang WordPress gồm tên người đăng, “Bài trước”, “Bài tiếp theo”, “Bài viết liên quan” và tóm tắt bài khác. Đã loại bỏ chính xác phần chân trang của từng phần trích xuất, không sửa bảng học phần, điểm số, số tín chỉ hoặc URL nguồn. Chỉ cập nhật `sha256_markdown` của ba bản trong `source_checksums.json`; toàn bộ `sha256_html` và `sha256_extracted_md` gốc vẫn giữ nguyên để truy vết.
- 17 source card được cập nhật tình trạng thật (đã có bản MD đầy đủ nhưng chưa duyệt độc lập) và liên kết trực tiếp đến tài liệu. Không thêm tài liệu/năm không có nguồn.
- Đã kiểm tra trực tuyến các trang *nội dung CTĐT* trên `uet.edu.vn`: 16/17 URL có thể đọc được; URL Kỹ thuật không gian QH-2026 nằm trên `uet.vnu.edu.vn`, trình đọc hiện trả `403` dù có nội dung được bộ máy tìm kiếm lập chỉ mục. Kiểm tra online này **không** thay thế đối chiếu bằng chứng khóa/ngày hiệu lực hoặc từng dòng học phần.
- Hai điểm cần kiểm duyệt nguồn thủ công: (1) khóa QH-2022–2024 ngành AI có chương trình gốc và cập nhật, cần quyết định ngày áp dụng phiên bản cập nhật; (2) URL *Chuẩn đầu ra* của Hàng không vũ trụ 2022–2024 đang dùng đường dẫn trang Vật lý kỹ thuật, phải đối chiếu nội dung chính xác.
- `retrieval_eligible: false` được giữ nguyên cho toàn bộ 17 hồ sơ; metadata có nội dung không đồng nghĩa đã được phê duyệt làm đáp án RAG/LoRA.

## Cách đối chiếu sau cập nhật

```powershell
python scripts/audit_owner_7_curricula.py --repo .
```

Lệnh trên không sửa dữ liệu, không duyệt hộ con người. Thông tin checksum và bảng phiên bản còn có thể đối chiếu với `data/raw/uet/curricula/source_checksums.json`, `data/raw/uet/curricula/manifest.json` và `data/raw/uet/curricula/versions.csv`.
