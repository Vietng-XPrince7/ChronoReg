# Dữ liệu chương trình đào tạo UET — quy ước thống nhất

**Đọc tại đây trước khi tìm CTĐT.** Một hồ sơ chỉ có **một file Markdown chứa nội dung**; các file JSON/CSV và `source_cards` chỉ là danh mục/metadata. Dữ liệu này **không đại diện cho toàn bộ quy chế UET**, chỉ cho mảng chương trình đào tạo.

## Điểm vào duy nhất

- [`catalog.json`](catalog.json): danh mục thống nhất **79 tài liệu CTĐT đang giữ**, gồm 31 Markdown trích từ website UET và 48 Markdown gốc do thành viên cung cấp. Mỗi mục có `doc_id`, **`content_path`**, SHA-256, nguồn/khóa/phiên bản, trạng thái duyệt và `retrieval_eligible`.
- [`../markdown/curricula/INDEX.md`](../markdown/curricula/INDEX.md): bảng dễ đọc gồm 31 CTĐT từ trang UET. Nhấn vào tên **phiên bản** để mở Markdown đầy đủ, cột **Trang nguồn** dẫn tới website UET.

## Nơi lưu nội dung chính tắc (canonical content)

| Nguồn dữ liệu | Nội dung thực sự ở đâu? | Metadata | Có thể tự nạp RAG? |
| --- | --- | --- | --- |
| 31 CTĐT trích xuất từ trang UET | `data/raw/uet/markdown/curricula/uet-curriculum-*.md` (ngay cấp này, **không** ở `source_cards/`) | `manifest.json`, `versions.csv`, `source_checksums.json`; `source_cards/` chỉ để tra nguồn | **Không** — đều chờ người duyệt |
| 48 phần CTĐT do Tuấn cung cấp (sau khi chủ dự án yêu cầu loại 5 phần CNTT CLC/Nhật Bản) | `data/raw/uet/curricula/tuan_2022_2026/original/*.md` | `tuan_2022_2026/manifest.json`, `versions.csv` | **Không** — chưa xác minh URL nguồn và khóa áp dụng |
| Một file hướng dẫn tuyển sinh nằm cùng gói Tuấn | Giữ nguyên tại `tuan_2022_2026/original/` | Bản ghi bị loại khỏi danh mục CTĐT | Không |

Các `source_cards/*.md` là **thẻ mô tả, không phải văn bản chương trình**. Link URL trong source card hay `manifest` là bằng chứng nguồn/truy xuất, **không phải bản sao nội dung**. Không được dùng source card để thay văn bản CTĐT hoặc xóa URL xác minh.

## Trùng lặp đã xử lý

- ZIP đầu vào của Tuấn có 130 vị trí chứa file, nhưng chỉ 54 tài liệu SHA-256 riêng biệt. Việc loại 76 lần xuất hiện lặp đã xảy ra từ đợt nhập trước; hiện không có 130 file ở repository.
- 53 file trong `data/raw/uet/markdown/curricula/tuan_2022_2026/` là **wrapper** (phần đầu metadata + toàn bộ nội dung file gốc). Khi bỏ phần đầu sau đúng tiêu đề `## Nội dung từ tài liệu nguồn (giữ nguyên)`, **nội dung trùng 100% ở cấp byte** với 53 file trong `original/`. Đã xóa 53 wrapper và giữ nguyên các bản gốc còn lại + metadata ở `manifest.json`; xem [`DEDUP_EVIDENCE.json`](DEDUP_EVIDENCE.json) để đối chiếu SHA từng cặp.
- **Không xóa vì trùng** các phiên bản khác khóa/niên khóa, kể cả tài liệu giống nhiều từ ngữ: ví dụ AI QH-2022–2024 gốc 124 tín chỉ và cập nhật 123 tín chỉ; hay Công nghệ/Kỹ thuật xây dựng 2025 vs 2026.
- **Không xóa** các `source_cards`: là metadata, không phải bản sao nội dung CTĐT.

## Cách kiểm tra sau khi thay đổi dữ liệu

```powershell
python scripts/rebuild_curricula_catalog.py --repo . --check
python scripts/audit_owner_7_curricula.py --repo . --expect-clean
python -m pytest -q tests/test_curricula_catalog.py
```

Chạy `python scripts/rebuild_curricula_catalog.py --repo . --write` nếu **chủ động** thay manifest hoặc nội dung và đã kiểm duyệt/cập nhật SHA tương ứng. Lệnh này chỉ tạo danh mục, không sao chép, xóa, không duyệt nguồn và không bật `retrieval_eligible`.

**Không tự động bật RAG/LoRA:** bất kỳ tài liệu nào chưa kiểm chứng độc lập phải tiếp tục có `retrieval_eligible=false`; một checksum hợp lệ **không** chứng minh văn bản đúng UET hoặc đúng năm áp dụng.

## Loại khỏi bộ dữ liệu theo quyết định chủ dự án (23/11/2026)

Chủ dự án yêu cầu loại **5 file gốc khác nhau** của các chương trình CNTT chất lượng cao và CNTT định hướng Nhật Bản. Đây **không phải khử trùng lặp**, vì SHA và nội dung khác nhau. Sau loại bỏ: **49/54 file gốc còn trong working tree**, gồm **48 CTĐT + 1 tài liệu tuyển sinh ngoài phạm vi**. Danh mục chính tắc còn **79** (31 website UET + 48 gốc nhóm).

Không sửa lịch sử nguồn ZIP đầu vào: `source_records=130`, `unique_source_records=54`, `duplicate_archive_occurrences=76`. Năm file đã loại được ghi trong `tuan_2022_2026/manifest.json` ở `owner_excluded_documents`, có SHA-256 để tra trong lịch sử Git khi cần. Chi tiết ở `docs/data/CURRICULA_OWNER_EXCLUSION_20261123.md`.
