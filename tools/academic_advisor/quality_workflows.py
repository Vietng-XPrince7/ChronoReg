"""Bounded advisor task continuation, using existing scoped read-only tools.
No database writes, no raw transcript in tokens, no external actions.
"""
import re, hashlib, json
from quality import norm
from workflow import scope_error, screening, debt_rows, valid, DRAFT_TASK, REPORT_TASK, CLASS_TASK
from course_planning import load_candidate, REL, SHA,candidate_source,candidate_label
from meeting_context import CURRENT, update_topics, question_count
from counseling import prepare

EDIT = re.compile(r'\b(?:sua|viet lai|chinh|doi|thay|bo|them|rut gon|giu|giong|than thien|trang trong|ngan hon|nhe nhang|gan gui)\b')
PUBLIC = re.compile(r'\b(?:thong bao chung|thong bao cong khai|ca lop|toan lop|cho lop|nhom lop)\b')
PRIVATE = re.compile(r'\b(?:tin nhan rieng|hen gap|cho ban|cho sinh vien)\b')
QUESTIONS = re.compile(r'\b(?:cau hoi|nen hoi|hoi gi)\b')
MINUTES = re.compile(r'\b(\d{1,3}) phut\b')
SCOPE_REF = re.compile(r'\b(?:sinh vien khac|ban khac|em khac|mssv|ma sinh vien|\d{8}|k\d{2}|qh 20\d{2})\b')

def snapshot(roster):
    # No grades or note text in the signed token, only a fingerprint.
    return hashlib.sha256(json.dumps(roster,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()

def route_workflow(question,prior,explicit,classified,roster,root):
    from quality_routes import response,task,find_student
    n=norm(question); old=prior if prior.get('kind')=='advisor_task' else {}; topic=old.get('topic'); sid=explicit or classified
    sig=snapshot(roster) if old or sid or re.search(r'\b(?:lop|ho so|sinh vien|tin nhan|thong bao)\b',n) else None
    same=old.get('scope')==sig if sig else False
    if not sid and not SCOPE_REF.search(n) and not PUBLIC.search(n):
        if same and topic in ('meeting','student_priority','draft_private','actions'):sid=old.get('mssv')
        elif prior.get('kind')=='student':sid=prior.get('mssv')
    def out(a,goal,tools=(),category='REGULATION',state=None,sources=(),person=None):
        return response(a,goal,tools,sources,category,person),state or {}
    def ctx(t,**kw):return task(t,scope=sig,**kw)
    def reject():return out('Dạ cô, hồ sơ hoặc đối tượng chưa khớp. Cô chọn đúng lớp/sinh viên trước khi tiếp tục.','scope_clarification',['scope_check'])
    st=find_student(roster,sid) if sid else None
    scope_bad=scope_error(n,roster)
    if old.get('scope') and topic in ('meeting','student_priority','draft_private','draft_public','actions','agenda','evidence') and not same and not (explicit or classified) and (EDIT.search(n) or QUESTIONS.search(n) or MINUTES.search(n) or re.search(r'\b(?:con lai|ke hoach nay|da xac nhan|da gui)\b',n)):
        return reject()
    # A conceptual distinction, not an assertion about any named current regulation.
    if 'quy che' in n and 'khoa tuyen sinh' in n and 'thong bao' in n and 'nam hoc' in n and re.search(r'\b(?:khac nhau|phan biet|giai thich)\b',n) and not re.search(r'\b(?:20\d{2}|\d{4}|so hieu \d)\b',n):
        return out('Dạ cô, quy chế theo khóa tuyển sinh xác định khung quy định áp dụng cho nhóm sinh viên thuộc khóa đó, có thể tiếp tục áp dụng qua nhiều năm. Thông báo theo năm học hoặc học kỳ hướng dẫn việc thực hiện trong một thời điểm cụ thể, như lịch đăng ký. Khi tư vấn cần đối chiếu cả khóa, kỳ và phạm vi văn bản; thông báo mới không mặc nhiên thay thế toàn bộ quy chế.','scope_explanation')
    # A request for limited priorities must actually honor the output size.
    m=re.search(r'\b(?:toi da|chi|chọn|chon|neu) (\d|mot|hai|ba) (?:viec|hanh dong)\b',n)
    if m and sid and re.search(r'\b(?:uu tien|lam truoc|hoc tap)\b',n) and not re.search(r'\b(?:quy che|hoc bong|hoc phi|dang ky bao nhieu)\b',n):
        if scope_bad or not st:return reject()
        count={'mot':1,'hai':2,'ba':3}.get(m[1],int(m[1]) if m[1].isdigit() else 2); count=max(1,min(count,3))
        rows,amb,unknown=debt_rows(st,roster.get('courses') or []); table,_=load_candidate(root,roster); pending={c for c,_,k in rows if table and c in table and table[c][0]==k}
        blockers=sorted(((c, sorted(x for x in pending if c in table[x][1])) for c in pending),key=lambda x:(-len(x[1]),x[0])); blockers=[x for x in blockers if x[1]]
        actions=[]; sources=[]; tools=['scope_check','student_signals','course_history']
        if blockers:
            c,children=blockers[0];actions.append(f'Rà và ưu tiên {c}: bảng {candidate_label(table)} cho thấy môn này mở đường cho {", ".join(children)}. Xác minh tiên quyết và lịch mở lớp trước khi đăng ký.'); sources=[candidate_source(table)];tools.append('prerequisite_planning')
        elif rows:actions.append('Đối chiếu các môn chưa thấy lần đạt với bảng điểm mới và chương trình đúng khóa; chọn môn nền tảng cần xử lý trước.')
        g=valid(st.get('gpa_semester'),0,4)
        if g is not None and g<2:actions.append(f'Tìm nguyên nhân GPA học kỳ {g:g} và thống nhất tải học vừa sức, sau khi xác minh tình trạng học vụ và lịch học.')
        if not actions:actions.append('Xác minh bảng điểm mới nhất và các học phần còn thiếu trước khi chọn mục tiêu học tập.')
        if len(actions)<count:actions.append('Thống nhất một mục tiêu học tập và mốc đánh giá lại với sinh viên.')
        return out('Dạ cô, em ưu tiên các việc sau từ hồ sơ demo:\n'+'\n'.join(f'{i}. {a}' for i,a in enumerate(actions[:count],1)),'student_priority',tools,'STUDENT_STATUS',ctx('student_priority',mssv=str(sid)),sources, str(sid))
    # Explicit meeting task / editing follow-up. Reuse the same scoped counseling tool.
    meeting_start=bool(st and (explicit or classified) and QUESTIONS.search(n) and re.search(r'\b(?:gap|tu van|trao doi|kho khan)\b',n))
    meeting_old=topic=='meeting' and same and st and old.get('mssv')==str(sid)
    if meeting_start or (meeting_old and (QUESTIONS.search(n) or re.search(r'\b(?:lam them|di lam|hoc nhom|hoc mot minh|ban dong hanh|phuong an|ho tro|tu hoc)\b',n)) and not re.search(r'\b(?:quy che|hoc bong|hoc phi|bao cao|tin nhan|thong bao|tien quyet|tin chi)\b',n)):
        if scope_bad or not st:return reject()
        topics,_=update_topics(question,old.get('topics',[]) if meeting_old else [])
        solo=bool(old.get('solo')) if meeting_old else False
        if re.search(r'\b(?:khong muon (?:co )?ban dong hanh|hoc mot minh|khong muon hoc nhom|kho hoc nhom)\b',n):solo=True
        elif re.search(r'\b(?:muon hoc nhom|muon co ban dong hanh)\b',n):solo=False
        new=ctx('meeting',mssv=str(sid),topics=topics,solo=solo)
        if EDIT.search(n) and QUESTIONS.search(n) and re.search(r'\b(?:lich|tu hoc|thoi gian)\b',n):
            return out('Em có thể dành những khoảng thời gian nào để tự học đều đặn trong tuần, phù hợp với lịch hiện tại của em?','meeting_preparation',['scope_check','meeting_preparation'],'STUDENT_STATUS',new,person=str(sid))
        if solo and re.search(r'\b(?:phuong an|ho tro|de xuat)\b',n) and not QUESTIONS.search(n):
            return out('Dạ cô, mình nên tôn trọng mong muốn tự học của sinh viên. Cô có thể cùng em ấy chọn một môn cần ưu tiên, chia nội dung thành các phần nhỏ, thống nhất lịch tự học và một bài tự kiểm tra mỗi tuần. Nếu gặp vướng mắc, em ấy có thể chủ động hỏi giảng viên bộ môn nếu có kênh phù hợp. Hẹn một lần kiểm tra tiến độ ngắn sau khi hai bên thống nhất thời gian.','meeting_preparation',['scope_check','meeting_preparation'],'STUDENT_STATUS',new,person=str(sid))
        token=CURRENT.set({'mssv':str(sid),'meeting':True,'topics':topics})
        try:
            # Explicit count is a format constraint, not an invitation to add extra content.
            q=question
            if QUESTIONS.search(n) and re.search(r'\b(?:\d|mot|hai|ba|bon|nam) cau hoi\b',n):q=f'Chỉ viết {question_count(question)} câu hỏi.'
            a,tools,_,sources=prepare(q,{'roster_obj':roster,'student_id':str(sid)},root,None)
        finally:CURRENT.reset(token)
        return out(a,'meeting_preparation',tools,'STUDENT_STATUS',new,sources,str(sid))
    # Drafting: only safe, scoped academic messages; revisions retain a structured
    # audience, tone and word budget, not raw draft text or names.
    initial=bool(DRAFT_TASK.search(n) or (PUBLIC.search(n) and 'thong bao' in n and re.search(r'\b(?:can|tao|tach|viet|soan)\b',n)))
    draft_old=topic in ('draft_private','draft_public') and same
    edit=bool(draft_old and EDIT.search(n) and not re.search(r'\b(?:hoc phi|quy che|hoc bong|diem chuan)\b',n))
    follow_feedback=bool(draft_old and re.search(r'\b(?:gui roi|da gui)\b',n) and re.search(r'\b(?:phan hoi|thu y kien)\b',n))
    if follow_feedback and not scope_bad:
        return out('Dạ cô, theo thông tin cô vừa xác nhận là cô đã gửi thông báo, em đề xuất thu phản hồi qua một kênh chung cho câu hỏi chung và kênh riêng cho khó khăn cá nhân. Cô có thể tổng hợp theo nhóm vấn đề, trả lời các câu trùng nhau, rồi hẹn trao đổi riêng với trường hợp cần hỗ trợ. Em chưa gửi biểu mẫu hay ghi nhận phản hồi nào.','communication_followup',['communication_draft'],'CLASS_STATS',old)
    # Preserve established multi-tool workflows when they explicitly request a report,
    # a retake scenario or screening plus a message (except explicit public split).
    combined=PUBLIC.search(n) and re.search(r'\b(?:noi bo|bao cao|tom tat tinh hinh)\b',n) and re.search(r'\b(?:roi|tach|va)\b',n) and not re.search(r'\b(?:bo phan|chi giu)\b',n)
    # A phrase the advisor asks to REMOVE is not a new class-screening task.
    # Only mask the specific phrase in an existing draft edit; leave positive
    # requests for screening/reporting and all scope checks intact.
    task_text=n
    if edit:
        task_text=re.sub(r'\b(?:dung|khong|tranh) (?:dung|nhac|viet)(?: cum tu| tu| chu)? gap rieng\b|\b(?:bo|xoa|loai bo) (?:cum tu |tu |chu )?gap rieng\b',' ',task_text)
    if (initial or edit) and (combined or not CLASS_TASK.search(task_text)) and (combined or not re.search(r'\b(?:tien quyet|kich ban|phuong an hoc lai|sang loc|phan nhom|phieu tu van|bao cao tu van)\b',task_text)):
        public=bool(PUBLIC.search(n)) or (edit and topic=='draft_public') or bool(re.search(r'\b(?:thong bao|cong khai)\b',n) and not PRIVATE.search(n))
        if not public and not (st and (PRIVATE.search(n) or edit)):return None
        if scope_bad or not roster.get('students') or (not public and not st):return reject()
        if edit and (explicit or classified) and str(sid)!=old.get('mssv') and not public:carry_reset=True
        else:carry_reset=False
        # Public messages never include personal identifiers or any derived grades.
        carry=old if edit and not carry_reset and topic==('draft_public' if public else 'draft_private') else {}
        budget=re.search(r'\b(?:toi da|khong qua|duoi) (\d{1,3}) tu\b',n); limit=int(budget[1]) if budget else carry.get('limit',60 if not public else 100)
        friendly=bool(re.search(r'\b(?:than thien|gan gui|nhe nhang)\b',n)) or bool(carry.get('friendly'))
        remind=bool(re.search(r'\b(?:chuan bi cau hoi|cau hoi cho buoi)\b',n)) or bool(carry.get('remind'))
        registration=bool(re.search(r'\b(?:dang ky|hoc phan)\b',n)) or bool(carry.get('registration'))
        if public:
            body='Các em thân mến, '+('hãy rà kế hoạch học tập và thông tin đăng ký học phần trên cổng đào tạo. ' if registration else 'hãy rà tình hình học tập và những vấn đề cần hỗ trợ. ')+('Các em chuẩn bị câu hỏi cho buổi tư vấn nhé. ' if remind else 'Nếu có câu hỏi, các em có thể trao đổi với cô. ')+'Thông tin cá nhân vui lòng trao đổi qua kênh riêng.'
        else:
            body=('Chào em! Cô muốn cùng em trao đổi về việc học và kế hoạch kỳ tới. Khi nào thuận tiện, em nhắn cô để mình cùng trò chuyện nhé.' if friendly else 'Chào em, cô muốn trao đổi về tình hình học tập và kế hoạch kỳ tới. Em cho cô biết thời gian thuận tiện để mình cùng trao đổi nhé.')
        if len(body.split())>limit:
            body='Các em chuẩn bị câu hỏi cho buổi tư vấn nhé.' if public and remind else 'Các em rà thông tin học tập trên cổng đào tạo nhé.' if public else 'Chào em, khi nào em thuận tiện trao đổi với cô nhé?'
        if len(body.split())>limit:return out('Dạ cô, giới hạn từ quá ngắn để soạn nội dung đầy đủ. Cô cho em tăng giới hạn hoặc chọn một ý chính nhé.','communication_draft')
        new=ctx('draft_public' if public else 'draft_private',limit=limit,friendly=friendly,remind=remind,registration=registration,**({} if public else {'mssv':str(sid)}))
        tools=['scope_check','communication_draft']; a=body
        if combined:
            groups,dup=screening(roster['students']); a='**Nội bộ — không đăng nhóm lớp**\n'+f"Hồ sơ demo {roster.get('class_short','')}, {roster.get('semester','kỳ chưa rõ')}: {sum(map(len,groups.values()))} hồ sơ hợp lệ, {len(groups[1])} ưu tiên, {len(groups[2])} cần trao đổi thêm, {len(groups[3])} thiếu dữ liệu, {len(groups[4])} chưa thấy tín hiệu. {dup} bản ghi trùng/thiếu mã. Đây không phải kết luận học vụ.\n\n**Thông báo công khai — bản nháp**\n"+body;tools.insert(1,'screening')
        return out(a,'communication_draft',tools,'CLASS_STATS' if public else 'STUDENT_STATUS',new,person=None if public else str(sid))
    # Time-constrained agenda for the advisor, no appointment or completion claim.
    mins=MINUTES.search(n); agenda_old=topic=='agenda' and same
    if mins and not sid and (agenda_old or re.search(r'\b(?:lop|co van)\b',n) and re.search(r'\b(?:ho tro|uu tien|ke hoach|thoi luong)\b',n)):
        if scope_bad or not roster.get('students'):return reject()
        total=int(mins[1]);
        if not 3<=total<=480:return out('Dạ cô, cô cho em một khoảng từ 3 đến 480 phút để chia thời lượng khả thi.','class_priorities')
        groups,dup=screening(roster['students']); a=max(1,total//3); b=max(1,total//2); c=total-a-b
        if agenda_old:
            tasks=['Kiểm tra việc tuần trước đã thực hiện và cập nhật kết quả; chỉ làm lại mục chưa xong.','Dựa trên kết quả, trao đổi sâu với các trường hợp ưu tiên còn mở và thống nhất bước hỗ trợ.','Ghi nhận việc tiếp theo, mốc kiểm tra và dữ liệu còn thiếu.']
        else:tasks=['Rà bảng điểm kỳ hiện tại và xác minh hồ sơ cũ trước khi chọn trường hợp hỗ trợ.',f'Liên hệ hoặc chuẩn bị trao đổi với nhóm {len(groups[1])} sinh viên ưu tiên theo thời gian thực tế; chưa giả định gặp được tất cả.','Ghi lại việc còn mở và hẹn mốc tiếp theo nếu hai bên thống nhất.']
        text=f'Dạ cô, em chia {total} phút như sau:\n'+'\n'.join(f'{i}. {t} phút: {x}' for i,(t,x) in enumerate(zip((a,b,c),tasks),1))+'\nĐây là lịch đề xuất, chưa đặt lịch hay xác nhận hoàn thành. Căn cứ hồ sơ demo '+str(roster.get('semester','kỳ chưa rõ'))+'.'
        return out(text,'class_priorities',['scope_check','screening','action_strategy'],'CLASS_STATS',ctx('agenda',minutes=total))
    if agenda_old and not scope_bad and re.search(r'\b(?:tot nghiep dung han|ke hoach nay)\b',n):
        return out('Dạ cô, kế hoạch giúp phát hiện sớm môn nợ và giảm trở ngại, nhưng chưa đủ để dự báo cả lớp tốt nghiệp đúng hạn. Cần rà tín chỉ còn thiếu, CPA độc lập, tiên quyết, lịch mở lớp và chuẩn đầu ra đúng khóa. Theo dõi số hồ sơ đã rà, số sinh viên có phương án và tín chỉ nợ đã xử lý; chỉ đánh giá kết quả khi có hồ sơ mới.','class_strategy',['scope_check','graduation_checklist'],'CLASS_STATS',old)
    # Explicit requests for official classifications or forecasts from stale records.
    if not sid and re.search(r'\b(?:ho so|lop|ai|nhom)\b',n) and re.search(r'\b(?:chac chan|ty le|uoc luong|du bao|an toan)\b',n) and re.search(r'\b(?:canh bao hoc vu|tot nghiep|tin hieu)\b',n):
        if scope_bad or not roster.get('students'):return reject()
        groups,dup=screening(roster['students'])
        if 'tot nghiep' in n: a='Dạ cô, chưa thể tính tỷ lệ tốt nghiệp đúng hạn từ hồ sơ demo. Cần CPA độc lập, tín chỉ bắt buộc còn thiếu, ngoại ngữ, học phần điều kiện, lịch mở lớp và thời gian đào tạo từng sinh viên. Không coi số người chưa thấy tín hiệu là số sẽ tốt nghiệp.'
        elif 'tin hieu' in n:a='Dạ cô, không. Chưa thấy tín hiệu chỉ nghĩa là các chỉ số sàng lọc hiện có chưa báo vấn đề; không chứng minh sinh viên an toàn. Cần xác minh CPA, cảnh báo trước đây, hồ sơ mới và quy chế đúng kỳ.'
        else:a=f'Dạ cô, chưa đủ căn cứ xác định ai chắc chắn bị cảnh báo học vụ. Hồ sơ demo có {len(groups[1])} sinh viên ưu tiên hỗ trợ, nhưng cần CPA độc lập, năm thứ, lịch sử cảnh báo và thông báo xử lý học vụ đúng kỳ để kết luận chính thức.'
        return out(a,'evidence_boundary',['scope_check','screening'],'CLASS_STATS',ctx('evidence'))
    # Read-only conversational tracking of existing report actions. No implicit DB write.
    action_start=bool(st and REPORT_TASK.search(n) and re.search(r'\b(?:viec|han|nguoi thuc hien)\b',n) and not re.search(r'\b(?:tin nhan|tien quyet|kich ban)\b',n))
    action_old=topic=='actions' and same and st and old.get('mssv')==str(sid)
    if action_start or (action_old and re.search(r'\b(?:xac nhan|danh dau|con lai|hoan thanh|xong)\b',n)):
        if scope_bad or not st:return reject()
        # Separate verifying a record from actually importing it, so marking the
        # former done does not imply new grades or completed counseling.
        tasks=[('Cô và sinh viên','Xác nhận bảng điểm mới nhất','Trước khi chốt kế hoạch'),('Cô','Nhập hoặc đối chiếu dữ liệu mới; xác minh CPA và lịch sử cảnh báo','Trước khi tư vấn chính thức'),('Cô và sinh viên','Rà môn nợ, tiên quyết và lịch mở lớp','Trước khi đăng ký'),('Cô và sinh viên','Thống nhất mục tiêu và mốc gặp lại','Sau khi rà hồ sơ')]
        done=bool(old.get('verified')) if action_old else False
        if action_old and 'bang diem' in n and not re.search(r'\b(?:chua xac nhan|chua kiem tra|khong xac nhan)\b',n) and re.search(r'\b(?:da xac nhan|da kiem tra|danh dau.*xong)\b',n):
            done=True; a='Dạ cô, em ghi nhận trong ngữ cảnh hội thoại rằng cô đã xác nhận bảng điểm. Việc nhập dữ liệu mới vẫn chưa hoàn thành; số liệu hồ sơ không thay đổi. Chưa ghi vào Workspace hoặc bộ nhớ lâu dài.'
        elif action_old and re.search(r'\b(?:danh dau|hoan thanh|xong)\b',n) and 'con lai' not in n:
            a='Dạ cô, em chưa xác định được việc nào đã hoàn thành. Cô nêu rõ việc cần đánh dấu; em chưa thay đổi dữ liệu hay Workspace.'
        else:
            a='Dạ cô, các việc '+('còn lại' if action_old else 'đề xuất')+' (mốc dự kiến):\n'+'\n'.join(f'• {owner}: {what} — {when}.' for i,(owner,what,when) in enumerate(tasks) if not (i==0 and done))+'\nChỉ theo dõi trong hội thoại này; chưa lưu hoặc đặt lịch.'
        return out(a,'advisor_report',['scope_check','advisor_report'],'STUDENT_STATUS',ctx('actions',mssv=str(sid),verified=done),person=str(sid))
    return None
