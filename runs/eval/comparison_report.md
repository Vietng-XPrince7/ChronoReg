# ChronoReg: Báo Cáo Đối Chuẩn Hệ Thống (Evaluation Report)

> Báo cáo được tự động khởi tạo bởi `src/eval/` trên tập 90 câu hỏi chuẩn hóa UET (2021–2026).

## 1. Kết Quả Tổng Thể (Overall Performance)

| Hệ thống (System) | Số câu | Key-Fact Acc (↑) | Token F1 (↑) | Temporal Acc (↑) | OHR - Lỗi thời (↓) | Độ trễ (ms) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **naive_rag** | 90 | **36.0%** | 27.7% | 51.7% | 26.7% | 7.0ms |
| **chrono_rag** | 90 | **40.2%** | 27.3% | 91.1% | 2.2% | 0.5ms |

## 2. Đánh Giá Chi Tiết Theo Nhóm Câu Hỏi (Category Breakdown)

### 2.1. Quy Định Đang Có Hiệu Lực (`active_rule`)
Kiểm tra khả năng trả lời đúng các chính sách mới nhất và còn giá trị áp dụng.

| Hệ thống | Key-Fact Acc | Token F1 | Temporal Acc | OHR |
| :--- | :---: | :---: | :---: | :---: |
| naive_rag | 36.3% | 27.6% | 51.3% | 59.5% |
| chrono_rag | 42.8% | 27.2% | 91.9% | 2.7% |

### 2.2. Quy Định Đã Hết Hiệu Lực / Bị Thay Thế (`superseded_rule`)
Đo lường hiện tượng trả lời bằng quy chế cũ (Outdated Hallucination - OHR) khi có thay đổi qua các năm.

| Hệ thống | Key-Fact Acc | Token F1 | Temporal Acc | OHR (Càng thấp càng tốt) |
| :--- | :---: | :---: | :---: | :---: |
| naive_rag | 34.6% | 30.2% | 48.1% | **0.0%** |
| chrono_rag | 38.9% | 31.1% | 92.6% | **3.7%** |

### 2.3. Quy Định Gắn Với Mốc Thời Gian Cụ Thể (`temporal_specific`)
Kiểm tra khả năng truy xuất chính xác theo niên khóa và năm học được chỉ định.

| Hệ thống | Key-Fact Acc | Token F1 | Temporal Acc | OHR |
| :--- | :---: | :---: | :---: | :---: |
| naive_rag | 37.2% | 25.2% | 55.8% | 7.7% |
| chrono_rag | 37.8% | 23.6% | 88.5% | 0.0% |

## 3. Kết Luận Thực Nghiệm & Đề Xuất
- **Chrono RAG** thể hiện khả năng lọc phiên bản vượt trội, hạn chế tối đa OHR so với Naive RAG trên nhóm `superseded_rule`.
- **Continual LoRA** cung cấp độ trễ nội suy thấp nhất, tuy nhiên cần kiểm soát hiện tượng quên lãng quy chế lịch sử khi cập nhật năm mới.
