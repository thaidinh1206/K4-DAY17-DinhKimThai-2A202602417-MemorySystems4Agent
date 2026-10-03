# Day 17 — Báo cáo Kết quả Benchmark & Phân tích Hệ thống Memory

## 1. Kết quả benchmark offline

Chạy `python src/benchmark.py` từ thư mục gốc của repo với cấu hình mặc định (`compact_threshold_tokens=600`, giữ `keep_messages=4`). Các số liệu token được tính theo cơ chế ước lượng heuristic ổn định theo ký tự (`ceil(len/4)`).

| Bộ dữ liệu | Agent | Agent tokens only | Prompt tokens processed | Cross-session recall | Response quality | Memory growth (bytes) | Compactions |
|---|---|---:|---:|---:|---:|---:|---:|
| **Standard** | Baseline | 1158 | 13071 | 0.0% | 0.0% | 0 | 0 |
| **Standard** | Advanced | 1199 | 19046 | 100.0% | 100.0% | 249 | 0 |
| **Long-context stress** | Baseline | 251 | 22181 | 0.0% | 0.0% | 0 | 0 |
| **Long-context stress** | Advanced | 290 | 8314 | 100.0% | 100.0% | 199 | 9 |

---

## 2. Phân tích kết quả cơ bản (Baseline vs. Advanced)

### 2.1. Khả năng nhớ dài hạn (Cross-session Recall)
* **Baseline Agent (0.0% Recall)**: Baseline chỉ duy trì bộ nhớ cục bộ theo từng `thread_id`. Khi chuyển sang câu hỏi recall ở một thread mới, Baseline hoàn toàn không có trạng thái bền vững và không thể trả lời bất kỳ thông tin nào về tên, nơi ở hay sở thích của người dùng.
* **Advanced Agent (100.0% Recall)**: Thông qua lớp lưu trữ bền vững `UserProfileStore` (ghi nhận ra file `state/profiles/<user>/User.md`), các sự thật cốt lõi về người dùng được nạp sẵn vào ngữ cảnh prompt ở mọi thread mới, giúp đạt tỷ lệ recall tuyệt đối 100%.

### 2.2. Chi phí Prompt Token và Trade-off của Compact Memory
* **Ở hội thoại ngắn (Standard Benchmark)**:
  * Advanced Agent xử lý **19.046** prompt tokens, cao hơn đáng kể so với **13.071** của Baseline (~45.7%).
  * *Nguyên nhân*: Do các lượt hội thoại trong bộ Standard chưa đủ dài để vượt ngưỡng nén (`compact_threshold_tokens=600`), trong khi Advanced Agent luôn phải kéo theo nội dung hồ sơ người dùng `User.md` trong ngữ cảnh của mỗi lượt. Đây là **overhead đánh đổi tất yếu** của persistent memory khi cuộc trò chuyện còn ngắn.
* **Ở hội thoại rất dài (Long-Context Stress Benchmark)**:
  * Khi chuỗi hội thoại kéo dài (16 turns dày đặc nội dung tin tức kỹ thuật), bộ nhớ của Baseline tăng tuyến tính và tích tụ đến **22.181** prompt tokens.
  * Trong khi đó, `CompactMemoryManager` của Advanced Agent đã kích hoạt nén **9 lần**, tóm tắt lịch sử cũ thành summary ngắn và chỉ giữ lại 4 tin nhắn gần nhất. Nhờ vậy, prompt tokens của Advanced giảm xuống chỉ còn **8.314** tokens (tiết kiệm **~62.5%** ngữ cảnh so với Baseline).

---

## 3. Phần triển khai Bonus (Mục tiêu 90 – 100 điểm)

Để giải quyết các rủi ro thực tế khi vận hành memory layer, hệ thống đã triển khai giải pháp: **Confidence-Gated Guardrail & Conflict-Aware Structured Facts**.

### 3.1. Bonus giải quyết bài toán gì?
1. **Chống nhiễm độc bộ nhớ (Memory Poisoning từ câu hỏi, đùa cợt, và thông tin tạm thời)**:
   - Trong giao tiếp tự nhiên (đặc biệt ở `advanced_long_context.json`), người dùng thường xuyên đưa ra các câu nói đùa (*"đùa với đồng nghiệp rằng hay là chuyển sang product manager..."*), các câu hỏi thăm dò (*"Tên mình là gì?", "Có phải mình ở Hà Nội không?"*), hoặc nhắc đến các địa điểm tạm thời (*"Hà Nội chỉ là nơi mình vừa bay ra họp hai ngày với đối tác chứ không phải nơi ở hiện tại"*).
   - Nếu trích xuất mù quáng, các thông tin giả/nhiễu này sẽ bị ghi đè thành sự thật vĩnh viễn trong `User.md`.
2. **Quản lý xung đột và đính chính (Conflict Resolution & Audit History)**:
   - Khi người dùng thay đổi thông tin thật (ví dụ: chuyển nơi ở từ Đà Nẵng sang Huế, hoặc từ tuần này làm việc tại Đà Nẵng), hệ thống cần phát hiện xung đột khóa (`key conflict`), cập nhật giá trị mới nhất và ghi nhật ký truy vết (`audit_log`), tuyệt đối không để sót thông tin cũ mâu thuẫn trong file hồ sơ.

### 3.2. Cải thiện chỉ số nào?
* **Cross-session Recall**: Giữ vững độ chính xác 100%, ngăn ngừa triệt để tình trạng trả lời sai do nhiễm độc dữ liệu (ví dụ: không trả lời nhầm nghề nghiệp thành `product manager` hay nơi ở thành `Hà Nội`).
* **Memory Growth & Prompt Token Efficiency**: Tránh cho file `User.md` bị phình to bởi các fact rác, giúp tiết kiệm dung lượng đĩa và hạn chế tối đa số lượng prompt token lãng phí do context bị loãng.

### 3.3. Rủi ro tạo thêm cho hệ thống (System Risks & Trade-offs)
* **Nguy cơ False Negatives (Bỏ sót thông tin thật)**:
  - Nếu người dùng sử dụng lối diễn đạt ngập ngừng, rụt rè hoặc dùng từ mang tính giả định nhẹ (ví dụ: *"Có lẽ từ tháng sau mình chuyển sang làm MLOps engineer chăng?"*), ngưỡng tin cậy `fact_confidence_threshold = 0.75` có thể phân loại câu này là nghi vấn và từ chối lưu, khiến agent bị "mất trí nhớ" đối với thông tin người dùng thực sự muốn chia sẻ.
* **Chi phí tính toán phân tích câu (Clause-level Pre-processing Overhead)**:
  - Việc tách câu và phân tích mẫu câu (câu hỏi, câu đùa, từ phủ định) quanh vị trí trích xuất làm tăng thêm chi phí tính toán CPU trước khi xử lý tin nhắn.
* **Độ phức tạp trong duy trì Rule Heuristic**:
  - Tiếng Việt có nhiều cách diễn đạt phong phú và đa nghĩa (ví dụ: từ viết tắt "AI" - Trí tuệ nhân tạo dễ bị nhầm với từ nghi vấn "ai" trong "ai đó, là ai"). Mặc dù đã dùng boundary matching chặt chẽ, một hệ thống sản xuất thực tế sẽ cần cân nhắc mô hình Small LLM / NER phân loại fact để xử lý ngôn ngữ tự nhiên mềm dẻo hơn.

---

## 4. Kiểm thử kiểm chứng (Unit Tests)

Bộ kiểm thử [src/test_agents.py](file:///d:/lab_vinuni/lab17/day17-cohort4-MemorySystems4Agent/src/test_agents.py) bao gồm 6 unit tests bao phủ toàn diện:
1. `test_user_markdown_read_write_edit`: Kiểm tra thao tác đọc/ghi/sửa file `User.md`.
2. `test_compact_trigger`: Kiểm tra cơ chế nén tự động kích hoạt khi vượt ngưỡng token.
3. `test_cross_session_recall`: Kiểm tra khả năng nhớ facts qua thread mới của Advanced và khả năng quên của Baseline.
4. `test_compact_reduces_prompt_load_on_long_thread`: Kiểm chứng compact memory giúp giảm tải prompt load trong thread dài.
5. `test_confidence_guardrail_rejects_questions_and_jokes`: **[Bonus]** Kiểm chứng câu hỏi, câu đùa và chuyến đi tạm thời bị từ chối lưu vào `User.md`.
6. `test_conflict_handling_and_audit_history`: **[Bonus]** Kiểm chứng xung đột dữ liệu được giải quyết chuẩn xác và lưu lại lịch sử audit log.

Lệnh chạy kiểm thử:
```powershell
.venv/Scripts/python.exe -m pytest src/test_agents.py -v
```
Kết quả: **6/6 passed in ~0.26s**.
