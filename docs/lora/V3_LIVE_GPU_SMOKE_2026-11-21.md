# ChronoReg V3 — bằng chứng PEFT inference GPU sau merge (2026-11-21)

## Provenance / phạm vi xác minh

- **Nguồn:** kết quả JSON do người thực hiện thí nghiệm gửi sau khi chạy notebook Kaggle ngày 2026-11-21, `generated_at_utc = 2026-11-21T12:13:34.941793+00:00`. Lưu nguyên nội dung trong `V3_LIVE_GPU_SMOKE_2026-11-21.json`. Đây là **bằng chứng được nộp từ Kaggle**, không phải lần tái chạy độc lập trên CI.
- **Mã đã merge:** PR #38 (`fix(lora): support pinned Transformers and add real PEFT runtime smoke`), `main` ở commit `fa349988e763e54eabb869211271c53de80b02e5` tại thời điểm đối chiếu. Chương trình `scripts/lora_live_smoke.py` yêu cầu CUDA, kiểm tra SHA và không có fallback vào answer bank.
- **Đã xác nhận từ log:** `LIVE_PEFT_SMOKE_PASS_NOT_QUALITY_CERTIFICATION`, `ARTIFACT_INTEGRITY_PASS`, `LIVE_PEFT_GENERATION`; nạp adapter cuối (2026) trên Qwen2.5-3B-Instruct revision `aa8e72537993ba99e69dfaafa59ed015b17504d1` đã xác minh. Thời gian sinh ~46,60 giây.
- **Dữ liệu huấn luyện thực tế:** 396 QA được tuyển chọn từ 53 nguồn/tài liệu, cập nhật liên tục 2022–2026. **Không** đồng nghĩa đã huấn luyện trên toàn bộ kho dữ liệu UET hay toàn bộ các ngành.

## Câu hỏi và đầu ra thực tế

- Checkpoint đã nạp: **2026**; câu hỏi hỏi về **2025–2026**. Đây **không** phải thí nghiệm riêng với checkpoint 2025.
- Câu hỏi: “Trong năm học 2025-2026, học phí UET được quy định như thế nào?”
- Câu trả lời mô hình: “Học phí UET năm học 2025-2026 sẽ được công bố vào tháng 12/2024.”

**Đánh giá:** câu trả lời không đưa ra mức học phí, không dẫn nguồn chính thức và không chứng minh tính đúng đắn của ngày công bố. Chỉ xác nhận pipeline sinh văn bản thật đã hoạt động. **Không sử dụng đầu ra này làm câu trả lời quy chế được xác minh.**

## Ranh giới về kỹ thuật và chất lượng

| Điều kiện | Trạng thái |
|---|---|
| Integrity 5 adapter V3, chuỗi 2022–2026 | PASS |
| Đúng SHA adapter cuối `8fa4bb...6ad24a` | PASS |
| Base revision đã xác minh tại Kaggle | PASS theo JSON thí nghiệm |
| GPU PEFT sinh câu trả lời trực tiếp | PASS theo JSON thí nghiệm |
| Cấu hình versions đúng toàn bộ `requirements.txt` của repo | **Chưa thử** |
| Câu trả lời quy chế có nguồn và chính xác | **Chưa đạt** |
| 90 QA benchmark được chứng nhận V8 | **Chưa** |
| Đủ điều kiện tự động chọn LoRA cho quy chế | **KHÔNG** |

Các phiên bản dùng trong Kaggle: `torch 2.11.0+cu130`, `transformers 4.57.6`, `peft 0.21.2`, `bitsandbytes 0.50.2`, `accelerate 1.15.0`. Repository khai báo `transformers==4.46.3`, `peft==0.13.2`, `bitsandbytes==0.44.1`, `accelerate==1.1.1`. Do đó kết quả này **không chứng nhận** GPU inference trong bộ dependency khóa của repo.

## Điều kiện đóng phần LoRA V3

- Đường nạp PEFT thật, xác minh checksum và smoke test trên GPU: **đã có bằng chứng kỹ thuật**.
- Bản thân chất lượng kiến thức: giữ trạng thái **`NOT_RELEASED` / `quality_qualified=false`**, phù hợp `docs/lora/QUALITY_STATUS_2026-11-21.json` và đánh giá chẩn đoán 90 câu.
- Không thay đổi `retrieval_eligible` của dữ liệu CTĐT hay cổng RAG: đây là quyền phê duyệt dữ liệu độc lập; không thuộc quy trình chứng nhận LoRA.
- Tiếp tục LoRA **chỉ khi** có yêu cầu nghiệm thu bằng phiên bản dependency khóa hoặc đánh giá chất lượng đã được phê duyệt. Không train lại tự phát vì smoke PASS.
