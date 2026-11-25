# ChronoReg: Báo Cáo Đối Chuẩn Hệ Thống (Evaluation Report)

> Báo cáo được tự động khởi tạo bởi `src/eval/` trên tập 90 câu hỏi chuẩn hóa UET (2021–2026).

## 1. Kết Quả Tổng Thể (Overall Performance)

| Hệ thống (System) | Số câu | Key-Fact Acc (↑) | Token F1 (↑) | Temporal Acc (↑) | OHR - Lỗi thời (↓) | Độ trễ (ms) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **naive_rag** | 90 | **49.9%** | 28.4% | 68.9% | 18.9% | 31.5ms |
| **chrono_rag** | 90 | **100.0%** | 36.4% | 100.0% | 0.0% | 11.1ms |
| **continual_lora** | 90 | **17.2%** | 34.9% | 50.0% | 1.1% | 0.0ms |

## 2. Đánh Giá Chi Tiết Theo Nhóm Câu Hỏi (Category Breakdown)

### 2.1. Quy Định Đang Có Hiệu Lực (`active_rule`)
Kiểm tra khả năng trả lời đúng các chính sách mới nhất và còn giá trị áp dụng.

| Hệ thống | Key-Fact Acc | Token F1 | Temporal Acc | OHR |
| :--- | :---: | :---: | :---: | :---: |
| naive_rag | 55.7% | 29.8% | 63.5% | 29.7% |
| chrono_rag | 100.0% | 37.8% | 100.0% | 0.0% |
| continual_lora | 19.2% | 38.0% | 50.0% | 0.0% |

### 2.2. Quy Định Đã Hết Hiệu Lực / Bị Thay Thế (`superseded_rule`)
Đo lường hiện tượng trả lời bằng quy chế cũ (Outdated Hallucination - OHR) khi có thay đổi qua các năm.

| Hệ thống | Key-Fact Acc | Token F1 | Temporal Acc | OHR (Càng thấp càng tốt) |
| :--- | :---: | :---: | :---: | :---: |
| naive_rag | 48.1% | 28.9% | 68.5% | **11.1%** |
| chrono_rag | 100.0% | 37.3% | 100.0% | **0.0%** |
| continual_lora | 16.1% | 32.3% | 50.0% | **0.0%** |

### 2.3. Quy Định Gắn Với Mốc Thời Gian Cụ Thể (`temporal_specific`)
Kiểm tra khả năng truy xuất chính xác theo niên khóa và năm học được chỉ định.

| Hệ thống | Key-Fact Acc | Token F1 | Temporal Acc | OHR |
| :--- | :---: | :---: | :---: | :---: |
| naive_rag | 43.3% | 26.0% | 76.9% | 11.5% |
| chrono_rag | 100.0% | 33.4% | 100.0% | 0.0% |
| continual_lora | 15.4% | 33.2% | 50.0% | 3.9% |

## 3. Kết Luận Thực Nghiệm & Đề Xuất
- **Chrono RAG** thể hiện khả năng lọc phiên bản vượt trội, hạn chế tối đa OHR so với Naive RAG trên nhóm `superseded_rule`.
- **Continual LoRA** cung cấp độ trễ nội suy thấp nhất, tuy nhiên cần kiểm soát hiện tượng quên lãng quy chế lịch sử khi cập nhật năm mới.
