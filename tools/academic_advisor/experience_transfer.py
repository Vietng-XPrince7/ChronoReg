"""Scoped intent repair before the expensive semantic/public fallback."""
import re
from quality import norm
from quality_routes import response,find_student
from quality_workflows import snapshot
from workflow import scope_error,screening

BLOCK=re.compile(r'\b(?:hoc phi|hoc bong|diem chuan|tuyen sinh|quy che|ngoai le|dac cach|gui ngay|cong khai|nhom lop|sua diem|lop khac|hutech|ulis|uit|bach khoa|soan|viet|email|tin nhan|thac si|tien si)\b')

def route(q,p,explicit,classified,roster,root):
    n=norm(q)
    if BLOCK.search(n):return None
    ids={str(x) for x in (explicit,classified) if x}|set(re.findall(r'\b\d{8}\b',q))
    sig=snapshot(roster)
    oldclass=p.get('kind')=='advisor_agent' and p.get('topic')=='class'
    # A limited-time private prioritization request without a named student.
    priority=bool(re.search(r'\b(?:uu tien|chuan bi gap|nen gap|can gap)\b',n) and re.search(r'\b(?:ai|mot vai ban|mot vai em|vai sinh vien|nhung ban|nhung em|sinh vien nao)\b',n) and re.search(r'\b(?:gap|ho tro|trao doi|quan tam)\b',n))
    strategy=bool(re.search(r'\b(?:ca lop|toan lop)\b',n) and re.search(r'\b(?:ho tro|tu van|trao doi)\b',n) and re.search(r'\b(?:to chuc|nhu the nao|chien luoc|phuong an|ke hoach)\b',n) and not re.search(r'\b(?:\d+ phut|tung em|tung sinh vien)\b',n))
    if not ids and p.get('kind') not in ('student','advisor_mission','semantic_task') and (not p.get('student') and not p.get('mssv')) and (priority or strategy and (oldclass or re.search(r'\b(?:gap rieng|khong the gap|chua the gap|thoi gian han che)\b',n))):
        if not roster.get('students') or scope_error(n,roster):return response('Dạ cô, cô chọn đúng lớp và hồ sơ trước khi em đề xuất hỗ trợ.','scope_clarification'),{}
        if oldclass and p.get('scope')!=sig:return response('Dạ cô, hồ sơ lớp đã thay đổi. Cô yêu cầu rà lại lớp trước khi tiếp tục nhé.','scope_clarification'),{}
        if strategy:
            groups,dup=screening(roster['students'])
            text=(f'Dạ cô, em đề xuất kết hợp hỗ trợ chung và gặp riêng. Theo dữ liệu đang mở, có {len(groups[1])} bạn ưu tiên gặp riêng, {len(groups[2])} bạn cần trao đổi thêm và {len(groups[3])} hồ sơ thiếu dữ liệu.\n\n'
                  '1. Trước buổi chung: mời cả lớp tự rà kết quả học tập, chuẩn bị câu hỏi và nhu cầu hỗ trợ.\n'
                  '2. Trong buổi chung: hướng dẫn kiểm tra học phần chưa đạt, cách lập kế hoạch học vừa sức và kênh hỏi giảng viên. Không nêu tên, điểm hoặc hoàn cảnh của từng bạn.\n'
                  '3. Sau buổi chung: ưu tiên hẹn riêng nhóm cần hỗ trợ nhất; cho các bạn còn lại đăng ký trao đổi qua kênh riêng.\n'
                  '4. Cuối tuần: rà số bạn đã liên hệ, số bạn đã thống nhất mục tiêu và các vướng mắc chưa giải quyết; điều chỉnh thứ tự hỗ trợ.\n\n'
                  'Đây là phương án hỗ trợ, không phải kết luận học vụ hay lịch đã đặt.')
            return response(text,'class_strategy',['scope_check','screening','action_strategy'],category='CLASS_STATS'),{'kind':'advisor_agent','topic':'class','scope':sig,'count':p.get('count') if oldclass else None}
        # Reuse the existing class screening tool; keep original scope and wording.
        from advisor_agent import class_flow
        return class_flow(q,n+' phan tich ca lop uu tien',p if oldclass else {},roster,explicit,classified,root)
    # Review a previously scoped study plan. No fabricated completed sessions.
    review=bool(re.search(r'\b(?:ke hoach|phuong an|dot thu|viec tu hoc|cuoi tuan|sau mot tuan)\b',n) and re.search(r'\b(?:hieu qua|danh gia|dua vao dau|do luong|tien bo|dau hieu|theo doi|tieu chi)\b',n) and not re.search(r'\b(?:doi thanh|lap lai|so sanh|tang len|giam con|\d+ phut|ca lop)\b',n))
    if not review:return None
    # Mission reviews are owned by the existing review contract, not this adapter.
    if p.get('kind')=='advisor_mission':return None
    elif p.get('kind')=='advisor_agent' and p.get('topic')=='study_plan':st=p
    else:return None
    sid=st.get('student');minutes=st.get('minutes')
    if (not sid or st.get('topic')!='study_plan' or st.get('scope')!=sig or p.get('scope')!=sig or (p.get('student')!=sid) or (ids and ids!={sid}) or not find_student(roster,sid) or scope_error(n,roster) or type(minutes) is not int or not 5<=minutes<=180):
        return response('Dạ cô, em cần xác nhận lại hồ sơ và kế hoạch tự học đang xét.','scope_clarification'),{}
    text=(f'Dạ cô, với kế hoạch thử 7 ngày, tối đa {minutes} phút/ngày, em đề xuất theo dõi bốn tiêu chí:\n\n'
          '• Mức thực hiện: số buổi đã học trên 7 buổi dự kiến, số phút thực tế; hỏi lý do nếu bỏ buổi.\n'
          '• Mức hiểu: thử lại một bài tương đương đầu tuần, không nhìn lời giải; so sánh số bước tự làm đúng.\n'
          '• Vướng mắc: số câu hỏi hoặc lỗi còn lặp lại và phần kiến thức cần giảng viên hỗ trợ.\n'
          '• Mức vừa sức: hỏi sinh viên về sự mệt mỏi, thời gian và khả năng duy trì.\n\n'
          'Nếu hiểu tốt hơn và duy trì được, giữ nhịp hoặc tăng nhẹ khi sinh viên đồng ý. Nếu chưa tiến bộ, đổi cách học hoặc giảm phạm vi nhiệm vụ; không tự tăng tải. Đây là tiêu chí đề xuất, chưa có kết quả cuối tuần thực tế.')
    return response(text,'study_review',['scope_check','study_plan','action_strategy'],category='STUDENT_STATUS',sid=sid),p
