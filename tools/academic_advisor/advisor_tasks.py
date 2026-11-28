"""Scoped task continuation for profile metrics, study plans and source clauses.
Input-only state: no grades, generated prose, or raw conversation in tokens.
Only bounded requests are handled here; all other tasks use existing routes.
"""
import re
from quality import norm
from quality_routes import response,source_response,pinned,cohort,find_student
from quality_workflows import snapshot
from workflow import scope_error,valid,debt_rows
from meeting_context import update_topics

METRICS=(('owed_credits','Tín chỉ nợ',1000,r'\b(?:tin chi|tc)(?: con)? no\b|\bno bao nhieu (?:tin chi|tc)\b'),('accumulated_credits','Tín chỉ tích lũy',1000,r'\b(?:tin chi|tc)(?: da)? tich luy\b'),('gpa_semester','GPA học kỳ',4,r'\b(?:gpa(?: hoc)? ky|gpa hoc ky truoc|diem trung binh hoc ky)\b'),('cpa','CPA',4,r'\b(?:cpa|gpa tich luy|diem trung binh(?: chung)? tich luy)\b'),('drl','Điểm rèn luyện',100,r'\b(?:diem ren luyen|drl)\b'))
REF=re.compile(r'\b(?:em nay|em ay|em do|ban nay|ban ay|ban do|sinh vien nay|sinh vien ay|sinh vien do)\b')
EXCLUDE=re.compile(r'\b(?:hoc phi|bao nhieu tien|chi phi|diem chuan|hoc bong|thong tu|nghi dinh|hutech|ulis|uit|bach khoa|thac si|tien si|lop khac|lop moi|sinh vien khac|em khac|ban khac|ca lop|toan lop|cong khai|so sanh|gui|dang len|sua diem|thay diem|cham diem)\b')
WITHDRAW=re.compile(r'\b(?:rut (?:bot )?hoc phan|rut mon hoc)\b')
PERIOD=re.compile(r'\b(?:hoc )?ky (?:phu|he|chinh)\b')
DURATION=re.compile(r'\b(\d{1,3}) phut\b')
PLAN=re.compile(r'\b(?:chia|lap|xep|lo trinh|phuong an|doi|thay doi|dieu chinh)\b')

def daily_study(n):
    # Explicit daily study constraint, not a meeting length or policy question.
    return bool(DURATION.search(n) and re.search(r'\b(?:moi ngay|hang ngay|phut ngay)\b',n) and re.search(r'\b(?:tu hoc|hoc duoc|hoc tap|hoc moi ngay|hoc toi da|danh)\b',n) and re.search(r'\b(?:nen|thu|ke hoach|phuong an|chi|gioi han|toi da|dieu chinh|giam)\b',n) and not re.search(r'\b(?:quy che|quy dinh|hoc phi|hoc bong|ky thi|lich thi|du thi|buoi gap|sinh hoat|ca lop|toan lop|dang ky|nghi dinh|thong tu|ngoai le|hoc sinh|tieng anh)\b',n))

def state(topic,**kw):return {'kind':'advisor_agent','topic':topic,**kw}
def ask(text,old=None):return response('Dạ cô, '+text,'advisor_clarification'),old or {}

def withdrawal(q,n,prior,root,explicit,classified):
    old=prior if prior.get('kind')=='advisor_agent' and prior.get('topic')=='withdrawal' else {}
    initial=bool(WITHDRAW.search(n) and re.search(r'\b(?:thoi diem|thoi han|bao lau|khi nao|cham nhat|han|den ngay|quy trinh|thu tuc|hau qua|dieu kien)\b',n))
    follow=bool(old and (re.fullmatch(r'(?:con|the|vay|neu)?\s*(?:hoc )?ky (?:phu|he|chinh)(?: thi sao| the nao)?',n) or re.search(r'\b(?:van ban do|quy dinh do|dieu khoan do|quyet dinh do)\b',n) and re.search(r'\b(?:k\d{2}|khoa|hieu luc|ap dung)\b',n)))
    if not (initial or follow) or explicit or classified:return None
    if EXCLUDE.search(n) or re.search(r'\b(?:5115|3079|quy che cu|quy che moi|lich dang ky|ngay cu the)\b',n):return None
    explicit_cohorts={1955+int(x) for x in re.findall(r'\bk(6[5-9]|7[0-9])\b',n)}|{int(x) for x in re.findall(r'\b(?:qh|khoa(?: tuyen sinh)?)\s*(20\d{2})\b',n)}
    if len(explicit_cohorts)>1:return ask('cô xác nhận khóa cần đối chiếu; em chưa so sánh hiệu lực giữa các khóa.',old)
    cy=cohort(n,old.get('cohort')); periods=set(re.findall(r'\b(?:hoc )?ky (phu|he|chinh)\b',n)); periods={'phu' if x=='he' else x for x in periods}
    if len(periods)>1:return None
    sem=next(iter(periods),old.get('semester','chinh'))
    new=state('withdrawal',cohort=cy,semester=sem)
    if (cy is not None and not 2022<=cy<=2025) or re.search(r'\b(?:chua (?:duoc )?xac nhan|chua xac minh)\b',n):return ask('chưa đủ căn cứ xác nhận QĐ 3626 áp dụng cho khóa đang hỏi. Cần đối chiếu quy chế đúng khóa và thông báo UET; không tự áp dụng thời hạn của khóa trước.',new)
    if re.search(r'\b(?:2026|202[7-9]|202[01])\b',n):return ask('cần xác minh hiệu lực văn bản ở năm đang hỏi trước khi áp dụng.',new)
    instruments=re.findall(r'\b(?:qd|quyet dinh) (\d+)\b',n)
    if any(x!='3626' for x in instruments):return None
    broad=initial and bool(re.search(r'\b(?:quy trinh|thu tuc|hau qua|dieu kien|can chu y)\b',n))
    if broad:
        from presentation import withdrawal_summary
        full=pinned(root,'Điều 23 QĐ 3626')
        if full:
            summary=withdrawal_summary(q,full['answer'])
            if summary:return source_response(summary.replace('Thầy/cô','Cô'),'withdrawal',full),new
        return ask('chưa xác minh đủ toàn bộ Điều 23 để hướng dẫn quy trình và hậu quả; cần đối chiếu văn bản gốc.',new)
    c=pinned(root,'Điều 23 khoản 2 QĐ 3626')
    if not c:return ask('chưa xác minh được điều khoản rút học phần đúng nguồn.',new)
    m=re.search(r'Việc rút bớt học phần chỉ được chấp nhận trong (\d+) tuần kể từ đầu học kỳ chính, (\d+) tuần kể từ đầu học kỳ phụ',c['answer'],re.I)
    if not m:return ask('chưa trích được thời hạn từ khoản 2 Điều 23; không suy đoán.',new)
    weeks=m[2] if sem=='phu' else m[1]; label='phụ' if sem=='phu' else 'chính'
    text=f'Dạ cô, theo khoản 2 Điều 23 QĐ 3626, việc rút bớt học phần được chấp nhận trong **{weeks} tuần kể từ đầu học kỳ {label}**. Cần đối chiếu quy chế đúng khóa và thông báo thực hiện của UET trước khi áp dụng.'
    return source_response(text,'withdrawal',c),new

def route(q,n,prior,explicit,classified,roster,root):
    r=withdrawal(q,n,prior,root,explicit,classified)
    if r is not None:return r
    if not prior and re.fullmatch(r'(?:viet lai|rut gon|tom tat|sua lai|chinh lai)(?: (?:cho|giu|giup))?(?: ngan gon hon| ngan hon| gon hon| ngan gon| giup co)?',n):
        return ask('cô muốn em chỉnh nội dung nào? Cô gửi đoạn cần sửa nhé.')
    if not prior and re.search(r'\b(?:phuong an|lo trinh) (?:vua roi|truoc do|da lap)\b',n) and re.search(r'\b(?:giam|tang|doi|dieu chinh)\b',n) and not (explicit or classified or re.search(r'\b\d{8}\b',q)):
        return ask('phiên này chưa có lộ trình. Cô chọn hồ sơ và nêu phương án cần chỉnh nhé.')
    if EXCLUDE.search(n):return None
    old=prior if prior.get('kind')=='advisor_agent' and prior.get('topic') in ('profile','study_plan','retake','retake_compare') else {}
    meeting=prior if prior.get('kind')=='advisor_task' and prior.get('topic') in ('meeting','student_priority') else {}
    sig=snapshot(roster); ids=set(re.findall(r'\b\d{8}\b',q)); selected=str(explicit or classified or '')
    metrics=[x for x in METRICS if re.search(x[3],n)]
    study=bool(daily_study(n) or (DURATION.search(n) and re.search(r'\b(?:tu hoc|moi ngay|hang ngay)\b',n) and re.search(r'\b(?:phuong an|ke hoach|lich|chia|dieu chinh|giam|chi co|danh)\b',n)) or (old.get('topic')=='study_plan' and re.search(r'\b(?:qua nang|hoi nang|nhe hon|giam bot|bot nang|qua suc)\b',n)))
    retake=bool(re.search(r'\b\d{1,2} (?:tin chi|tc)\b',n) and PLAN.search(n) and (re.search(r'\b(?:mon (?:con )?no|hoc phan (?:con )?no|hoc lai|tien quyet)\b',n) or old.get('topic') in ('retake','retake_compare') and re.search(r'\b(?:moi dot|mot dot|moi ky)\b',n)))
    profile=bool(metrics and (ids or selected or old and REF.search(n)) and re.search(r'\b(?:bao nhieu|la may|hien co|hien tai|cho co biet|tra cuu|liet ke)\b',n) and not PLAN.search(n) and not re.search(r'\b(?:quy che|dang ky|gioi han|toi da|tot nghiep|canh bao|ha hang|gia su|neu)\b',n))
    advice=bool(old.get('topic') in ('retake','retake_compare') and re.search(r'\b(?:hoc don|tra no nhanh|hoc qua nhieu|nen hoc|co nen|phu hop|danh doi|rui ro)\b',n) and re.search(r'\b(?:hoc|tra no|phuong an|lo trinh)\b',n) and not PLAN.search(n) and not DURATION.search(n) and not re.search(r'\b\d+ (?:tin chi|tc)\b',n))
    if not (study or retake or profile or advice):return None
    # Verify all explicit identifiers, roster scope and stale context before reuse.
    if len(ids)>1 or (selected and ids and selected not in ids):return ask('cô xác nhận một hồ sơ sinh viên đúng với yêu cầu.')
    if scope_error(n,roster):return ask('cô chọn đúng lớp trước khi tra hồ sơ.')
    carry=old or meeting
    if not ids and not selected and carry and carry.get('scope')!=sig:return ask('hồ sơ đã thay đổi, cô xác nhận lại sinh viên trước khi tiếp tục.')
    sid=next(iter(ids),None) or selected or (carry.get('student') or carry.get('mssv') if carry else None)
    st=find_student(roster,sid)
    if not st:return ask('cô chọn hồ sơ sinh viên cần hỗ trợ trước nhé.')
    sid=str(sid)
    if advice:
        if not carry or carry.get('student')!=sid or carry.get('scope')!=sig:return ask('cô xác nhận lại hồ sơ và phương án trước khi so sánh.')
        plan=carry.get('plan',{});cap=plan.get('budget');rounds=plan.get('rounds');debt=valid(st.get('owed_credits'),0,1000);gpa=valid(st.get('gpa_semester'),0,4)
        lead='Dạ cô, em không khuyến nghị tăng tải chỉ để trả nợ nhanh.'
        if debt is not None and gpa is not None:lead+=f' Hồ sơ đang có {debt:g} tín chỉ nợ và GPA học kỳ {gpa:g}; nên ưu tiên khả năng hoàn thành thực tế thay vì số môn đăng ký.'
        if type(cap) is int and type(rounds) is int and rounds>0:lead+=f' Phương án trước là {cap} tín chỉ/đợt, {rounds} đợt trên tập môn xếp được; đây là mô phỏng, không phải số học kỳ.'
        lead+='\n\n- Học dồn có thể giảm số đợt, nhưng tăng khối lượng tự học và rủi ro phải học lại lần nữa.\n- Giữ tải vừa sức và ưu tiên môn tiên quyết; sau khi có kết quả từng đợt mới xem xét tăng tải.\n- Cô nên xác nhận thời gian tự học, môn đang học, lịch mở lớp và giới hạn đăng ký theo quy chế đúng khóa trước khi quyết định. Em chưa đủ căn cứ để chốt tải hợp pháp hay lịch đăng ký.'
        return response(lead,'retake_tradeoff',['scope_check','student_signals','credit_scenarios','action_strategy'],category='STUDENT_STATUS',sid=sid),{k:v for k,v in carry.items() if k!='exp'}
    if profile:
        lines=[]
        for field,label,upper,_ in metrics:
            if field=='cpa':lines.append('- **CPA:** hồ sơ demo chưa xác nhận CPA độc lập; không dùng GPA học kỳ thay thế.');continue
            v=valid(st.get(field),0,upper);lines.append(f'- **{label}:** '+(f'{v:g}'.replace('.',',') if v is not None else 'chưa có dữ liệu hợp lệ')+('.' if v is not None else '.'))
        text=f'Dạ cô, hồ sơ {sid} hiện có:\n'+'\n'.join(lines)+'\n\nCăn cứ hồ sơ '+str(roster.get('class_short',''))+', '+str(roster.get('semester','kỳ chưa rõ'))+'.'
        return response(text,'student_lookup',['scope_check','student_signals'],category='STUDENT_STATUS',sid=sid),state('profile',student=sid,scope=sig)
    if retake:
        # Reuse the existing verified planner; do not duplicate prerequisite logic.
        from quality_routes import route as legacy
        caps=re.findall(r'\b(\d{1,2}) (?:tin chi|tc)\b',n)
        if len(set(caps))!=1 or re.search(r'\d[.,]\d+\s*(?:tín chỉ|tc)',q,re.I):return ask('cô xác nhận một giới hạn tín chỉ nguyên cho mỗi đợt.',carry)
        if re.search(r'\b(?:truoc|bat buoc|khong hoc|bo mon|tru mon|giu nguyen mon|uu tien mon|khong cung|cung dot|khong xep|chi xep|co dinh|tu ngay|den ngay)\b',n) or re.search(r'\b[A-Z]{3}\d{4}\b',q):return None # Preserve specialized constraint handling.
        cap=int(caps[0]); previous=old.get('plan',{}) if old.get('topic')=='retake' and old.get('student')==sid and old.get('scope')==sig else {}
        try:r,new=legacy(f'Lập lộ trình học lại mỗi đợt {cap} tín chỉ',previous,sid,None,roster,root)
        except (ValueError,RuntimeError,TypeError,KeyError):return ask('chưa xác minh được phương án có tiên quyết. Cô kiểm tra lại hồ sơ và giới hạn.')
        return r,state('retake',student=sid,scope=sig,plan=new)
    # Practical weekly study plan, not a timetable or promise of passing.
    mins=[int(x) for x in DURATION.findall(n)]; previous=old if old.get('topic')=='study_plan' and old.get('student')==sid and old.get('scope')==sig else {}
    if len(set(mins))>1:return ask('cô xác nhận thời gian tự học tối đa mỗi ngày.',carry)
    budget=mins[0] if mins else previous.get('minutes')
    if not budget or not 5<=budget<=180:return ask('cô cho em số phút tự học mỗi ngày (5–180 phút).',carry)
    if not mins:budget=max(5,(budget*2//3)//5*5)
    lighter=bool(previous and budget<previous.get('minutes',budget))
    if re.search(r'\b(?:[2-9]|\d{2}|hai|ba|bon|nam|sau|bay) tuan\b|\b(?:thang|lich thi|lich mo lop)\b',n):return None
    # Do not silently replace a specified horizon, excluded day, or another study pattern.
    if re.search(r'\b(?:[1-6]|[89]|\d{2}|hai|ba|bon|nam|sau) ngay\b|\b(?:tru ngay|nghi chu nhat|khong hoc vao|chi hoc vao|cuoi tuan|cach ngay)\b',n):return ask('em mới hỗ trợ kế hoạch thử trong 7 ngày với cùng trần thời gian mỗi ngày. Cô xác nhận số ngày hoặc ngày cần nghỉ để tránh lập lịch sai yêu cầu.',carry)
    topics,_=update_topics(q,carry.get('topics',[]) if carry else [])
    rows,_,_=debt_rows(st,roster.get('courses') or [])
    from course_planning import load_candidate,REL,SHA,candidate_source,candidate_label
    table,_=load_candidate(root,roster);pending={x[0] for x in rows if table and x[0] in table and table[x[0]][0]==x[2]}
    blockers=sorted(((c,sum(c in table[x][1] for x in pending)) for c in pending),key=lambda x:(-x[1],x[0]))
    target=blockers[0][0] if blockers and blockers[0][1]>0 else None
    intro=(f'Em đề xuất ưu tiên **{target}** vì bảng {candidate_label(table)} cho thấy môn này mở đường cho {blockers[0][1]} môn nợ; cô cần xác minh trước khi chọn.' if target else 'Em đề xuất cùng sinh viên chọn một môn nền tảng đang gặp khó khăn sau khi rà bảng điểm mới.')
    a=max(1,budget//5);b=budget-a*2
    lines=[f'Dạ cô, em đề xuất thử một tuần với tối đa **{budget} phút/ngày** ({budget*7} phút/tuần). '+('Nếu sinh viên xác nhận có lịch làm việc, nên chọn khung giờ không trùng ca và không cắt giảm giấc ngủ. ' if 'time' in topics else '')+intro,'','| Ngày | Nội dung | Thời lượng |','|---|---|---:|']
    activities=['Rà mục tiêu, chọn phần kiến thức yếu','Ôn khái niệm và tự giải ví dụ','Luyện bài tập, ghi lỗi','Ôn lại lỗi, hỏi điểm chưa hiểu','Tự giải một bài không nhìn lời giải','Luyện lại phần yếu','Tự kiểm tra ngắn, chọn mục tiêu tuần sau']
    if budget<=20:
        activities=['Chọn một dạng bài nhỏ, rà ví dụ mẫu','Ôn một khái niệm và ghi một câu hỏi','Tự thử một bước của bài tập','Xem lại một lỗi; nhờ hỗ trợ nếu mắc','Tự làm lại bài ngắn đã học','Ôn thẻ ghi nhớ; có thể nghỉ nếu mệt','Tự kiểm tra một câu, ghi mục tiêu nhỏ tuần tới']
        lines.insert(1,'Chỉ đặt một mục tiêu nhỏ trong tuần; bỏ bài dài và phần nâng cao. Ngày 6 có thể nghỉ, không cần bù giờ.')
    elif lighter:
        lines.insert(1,'Giảm mục tiêu mỗi buổi: chỉ làm một dạng bài, không học thêm chủ đề mới trước khi nắm được phần nền tảng.')
    for i,activity in enumerate(activities):lines.append(f'| {i+1} | {activity} | {budget} phút |')
    lines+=['',f'Mỗi buổi có thể chia {a} phút ôn lại, {b} phút tập trung vào nhiệm vụ chính, {a} phút ghi lại điều đã hiểu và câu hỏi còn vướng.', ('Nếu mệt hoặc lịch làm việc (nếu có) thay đổi' if 'time' in topics else 'Nếu mệt hoặc lịch sinh hoạt thay đổi')+', có thể rút ngắn buổi học; không dồn phần thiếu sang khuya. Sau một tuần, cô hỏi sinh viên phần nào làm được và điều chỉnh tiếp. Đây là kế hoạch tự học thử, không phải lịch mở lớp hay cam kết kết quả.']
    return response('\n'.join(lines),'study_plan',['scope_check','course_history','study_plan']+(['prerequisite_planning'] if target else []),[candidate_source(table)] if target else [],'STUDENT_STATUS',sid),state('study_plan',student=sid,scope=sig,minutes=budget,topics=topics)

def calendar_presentation(r):
    """Keep source qualification verbatim in evidence; simplify only a known technical sentence."""
    m=r.get('metadata',{}); lines=r['answer'].splitlines(); out=[]
    for line in lines:
        if line.startswith('Bản PDF người dùng cung cấp có số 1588/KH-ĐHCN') and 'pdfsig' in line:
            m.setdefault('source_qualification',line)
            out.append('Căn cứ kế hoạch số 1588/KH-ĐHCN ngày 01/08/2025. Chưa xác nhận các thay đổi sau công bố.')
        else:out.append(re.sub(r'(\d{2}/\d{2}/\d{4})\s*÷\s*(\d{2}/\d{2}/\d{4})',r'\1 – \2',line))
    r['answer']='\n'.join(out)
