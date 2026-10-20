# Metadata Schema — ChronoReg

Mô tả đầy đủ các trường metadata được gắn vào mỗi chunk/tài liệu đã xử lý trong `data/processed/`.

---

## Frontmatter YAML (cấp tài liệu)

```yaml
---
doc_id:         string   # Khóa chính duy nhất, ví dụ: "uet-qddt-2023"
title:          string   # Tiêu đề đầy đủ của văn bản
issuing_body:   string   # Cơ quan ban hành: "UET" | "VNU" | "BGDDT"
source_type:    string   # Loại văn bản (xem bảng bên dưới)
effective_date: date     # Ngày có hiệu lực (ISO 8601: YYYY-MM-DD)
expired_date:   date|null  # Ngày hết hiệu lực; null nếu vẫn còn hiệu lực
superseded_by:  string|null  # doc_id của văn bản thay thế; null nếu vẫn còn hiệu lực
source_file:    string   # Đường dẫn tương đối đến file gốc trong data/raw/
language:       string   # Mặc định "vi"
---
```

### Giá trị hợp lệ cho `source_type`

| Giá trị | Mô tả |
|---|---|
| `quy_che_dao_tao` | Quy chế đào tạo đại học |
| `quy_dinh_hoc_phi` | Quy định học phí |
| `thu_tuc_hanh_chinh` | Thủ tục hành chính (nhập học, bảo lưu...) |
| `thong_bao` | Thông báo, kế hoạch năm học |
| `quyet_dinh` | Quyết định ban hành / sửa đổi |

---

## Metadata cấp Điều (Article-level)

Mỗi Điều được tách thành một section trong Markdown với heading `## Điều X — <tên điều>`.  
Metadata bổ sung được nhúng dưới dạng HTML comment ngay sau heading để không ảnh hưởng render:

```html
<!-- meta
dieu_so: "Điều 15"
khoan_so: null
noi_dung_tom_tat: "Điều kiện xét tốt nghiệp đại học hệ chính quy"
tags: ["tot_nghiep", "dieu_kien", "chinh_quy"]
-->
```

| Trường | Kiểu | Mô tả |
|---|---|---|
| `dieu_so` | string | Số điều, ví dụ `"Điều 15"` |
| `khoan_so` | string\|null | Số khoản nếu chunk nhỏ hơn cấp Điều |
| `noi_dung_tom_tat` | string | Tóm tắt nội dung 1 câu (dùng làm embedding context) |
| `tags` | list[string] | Nhãn chủ đề tự do |

---

## Quan hệ phiên bản

```
doc_A  ──superseded_by──►  doc_B  ──superseded_by──►  doc_C (hiện hành)
        effective: 2021          effective: 2022          effective: 2023
        expired:   2022-08-31    expired:   2023-08-31    expired: null
```

- Để truy vấn tài liệu có hiệu lực tại thời điểm `T`:  
  `effective_date <= T AND (expired_date IS NULL OR expired_date > T)`

---

## Ví dụ file processed hoàn chỉnh

```markdown
---
doc_id: "uet-qddt-2023"
title: "Quy chế đào tạo đại học UET 2023"
issuing_body: "UET"
source_type: "quy_che_dao_tao"
effective_date: "2023-09-01"
expired_date: null
superseded_by: null
source_file: "data/raw/uet/qddt-2023.pdf"
language: "vi"
---

# Quy chế đào tạo đại học UET 2023

## Chương IV — Thi, kiểm tra và đánh giá kết quả học tập

### Điều 15 — Điều kiện xét tốt nghiệp

<!-- meta
dieu_so: "Điều 15"
khoan_so: null
noi_dung_tom_tat: "Điều kiện để sinh viên được xét tốt nghiệp đại học chính quy tại UET"
tags: ["tot_nghiep", "dieu_kien", "chinh_quy"]
-->

Sinh viên được xét công nhận tốt nghiệp khi có đủ các điều kiện sau: ...
```

