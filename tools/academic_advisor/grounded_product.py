"""Opt-in bounded product pilot. Existing tools remain authoritative.
No model call in this path; existing semantic planner remains available outside it.
All prior context originates in conversation.Context (signed, expiring).
"""
import re
from grounded_contract import grounded,fold,plan,canonical,cohorts
from quality import norm
from quality_routes import response,find_student,source_response
from quality_workflows import snapshot
from workflow import scope_error

# Never canonicalize mixed, external, exceptional or write/action requests.
BLOCK=r'\b(?:hutech|ulis|uit|bach khoa|thac si|tien si|ngoai le|dac cach|tam khoa|chua duyet|5115|3079|thong tu|nghi dinh|gui ngay|sua diem|cong khai|lop khac|sinh vien khac|bo qua|ignore|system prompt)\b'

def ask(text,old=None):return response('Dạ cô, '+text,'grounded_clarification'),old or {}

def prior_plan(p):
    try:
        if p.get('kind')=='advisor_agent' and p.get('topic')=='fee':
            f=p['fee'];return canonical(plan('fee_total',cohort=f['cohort'],program_type=f['scope'],academic_year=f['year'],credits=f.get('credits') or [f['quantity']]))
        if p.get('kind')=='policy_clause' and p.get('instrument')=='3626' and (p.get('article'),p.get('clause'))==(36,3):
            return plan('policy_lookup',instrument='3626',article=36,clause=3,question_type='leave_conditions')
        if p.get('kind')=='advisor_agent' and p.get('topic')=='evidence_article' and (p.get('article'),p.get('clause'))==(36,3):
            return plan('policy_lookup',instrument='3626',article=36,clause=3,question_type='leave_conditions')
        if p.get('kind')=='advisor_mission':
            st=p.get('states',{}).get('study',{})
            if st.get('topic')=='study_plan' and st.get('student')==p.get('student') and st.get('scope')==p.get('scope'):
                return canonical(plan('study_plan',student=p['student'],minutes=st['minutes'],days=7))
        if p.get('kind') in ('student','advisor_task','advisor_agent','advisor_mission'):
            sid=p.get('student') or p.get('mssv')
            if re.fullmatch(r'\d{8}',str(sid)):return {'kind':'student_context','student':sid}
    except (KeyError,TypeError,ValueError):pass
    return {}

def fee_execute(a,p,roster,root):
    from advisor_agent import fee
    from advisor_bridge import fmt
    qty=sum(a['credits']);c=a['cohort'];year=a['academic_year']
    # Existing fee tool is verified only for standard programs and 1–30 credits.
    if a['program_type']!='standard' or not 1<=qty<=30:return ask('phạm vi tính phí này chưa được xác minh; cần bảng định mức đúng chương trình và số tín chỉ.',p)
    def run(y):
        q=f'Học phí học lại {qty} tín chỉ CTĐT chuẩn QH-{c} năm học {y} hết bao nhiêu tiền?'
        result=fee(q,norm(q),{},roster,root)
        if not result:return None
        r,ctx=result;meta=r.get('metadata',{});f=ctx.get('fee',{})
        if meta.get('engine_mode')!='SOURCE_TABLE' or f.get('quantity')!=qty or f.get('year')!=y or f.get('cohort')!=c:return None
        m=re.search(r'= \*\*([\d.]+) đồng\*\*',r['answer'])
        return (r,ctx,int(m[1].replace('.',''))) if m else None
    cur=run(year)
    if not cur:return ask('chưa xác minh được định mức học lại đúng khóa và năm học.',p)
    r,ctx,total=cur;ctx['fee']['credits']=list(a['credits'])
    if len(a['credits'])>1:r['answer']+='\n\nTổng tín chỉ: '+' + '.join(map(str,a['credits']))+f' = {qty} tín chỉ.'
    if 'previous_year' in a:
        base=run(a['previous_year'])
        if not base:return ask('chưa xác minh được cả hai bảng học phí; em chưa tính chênh lệch.',p)
        rr,_,old_total=base;d=total-old_total
        r['answer']+=f'\n\nSo với {a["previous_year"]} ({fmt(old_total)} đồng), tổng tiền '+(f'cao hơn {fmt(d)} đồng.' if d>0 else f'thấp hơn {fmt(-d)} đồng.' if d<0 else 'không đổi.')
        r['metadata']['advisor_sources']=rr['metadata'].get('advisor_sources',[])+r['metadata'].get('advisor_sources',[])
    return r,ctx

def route(q,p,explicit,classified,roster,root):
    n=fold(q);old=prior_plan(p);ids={str(x) for x in (explicit,classified) if x}|set(re.findall(r'(?<!\d)\d{8}(?!\d)',q))
    if re.search(r'\b(?:phien|cua so|cuoc tro chuyen|doan chat)\b',n) and re.search(r'\b(?:khac|hom qua|truoc do|cu)\b',n) and re.search(r'\b(?:ho so|sinh vien|mssv)\b',n):
        return ask('em không lấy hồ sơ từ phiên khác. Cô mở hồ sơ hợp lệ hoặc nhập MSSV trong phiên này nhé.')
    if re.search(BLOCK,n):return None
    action=None
    # Public money request must not become a personal retake plan.
    money=bool(re.search(r'\b(?:kinh phi|chi phi|hoc phi|khoan tien|khoan thu|tinh tien|du tru|du phong|uoc tinh|du kien bao nhieu)\b',n))
    if not ids and not re.search(r'\b(?:hoc bong|mien|hoc lan dau|thi lai|hoc ky|ca ky|toan ky|lo trinh|tu hoc|soan|thong bao|gui|lich hoc|lich thi|diem chuan|quy che|hoc vuot|cai thien|nganh|tien no|thanh toan|tra gop)\b',n):
        if (money and re.search(r'\bhoc lai\b',n)) or (old.get('action')=='fee_total' and re.search(r'\b(?:so voi|doi chieu voi|chenh lech|chenh ra|tang them|giam di|chi hoc lai|bo mon)\b',n) and re.search(r'\b(?:20\d{2}|tin chi|tc)\b',n)):
            # A single scalar query keeps the already stable fast route unless
            # a multi-credit or comparison request needs the structured path.
            if re.search(r'\b(?:hai|ba|bon|[2-9]) (?:mon|hoc phan)\b|\b\d+\s*(?:,|va)\s*\d+\s*(?:tin chi|tc)\b',n) or p.get('fee',{}).get('credits') or re.search(r'\b(?:so voi|doi chieu voi)\b',n):action='fee_total'
    if action is None and not ids and not re.search(r'\b(?:hoc phi|hoc bong|nckh|tien quyet|hoc lai|mssv|lich hoc|nam hoc|tuong duong|chuyen doi|dang ky|gioi han|soan|gui|khong tinh|clc|dmktkt|tt\s*23)\b',n):
        if p.get('topic')=='curriculum_comparison' and any(y not in range(2022,2027) for y in cohorts(n)) and re.search(r'\b(?:cntt|khmt|httt|ktmt|cong nghe thong tin|khoa hoc may tinh|he thong thong tin|ky thuat may tinh)\b',n):
            return ask('chưa có CTĐT đã đối chiếu đúng khóa này; không lấy bảng của khóa khác thay thế.')
        if len(cohorts(n))>=2 and re.search(r'\b(?:doi chieu|so sanh|khac nhau|chenh lech|dat .+ canh nhau|hon kem|so khoi luong)\b',n) and re.search(r'\b(?:tong|toan khoa|tin chi tot nghiep|khoa luan)\b',n):action='curriculum_compare'
    if action is None and not ids and old.get('action')=='policy_lookup' and re.search(r'\b(?:tro lai hoc|hoc tro lai|hoc tiep)\b',n) and re.search(r'\b(?:han|moc|truoc|khi nao)\b',n):action='policy_lookup'
    if action is None and old and not re.search(r'\b(?:hoc lai|hoc phi|hoc bong|soan|viet|email|tin nhan|ca lop|tin chi|tc|nghi chu nhat|cach ngay|khong tu hoc|khong lap|khong can lap|dung lap|tru ngay|chi hoc vao|lich thi|lich mo lop)\b',n) and not re.search(r'\b[A-Z]{3}\d{4}\b',q):
        if re.search(r'\b(?:tu hoc|tu on|on tap|lich on)\b',n) and re.search(r'\b\d{1,3}\s*phut\b',n) and re.search(r'\b(?:mot tuan|bay ngay|7 ngay)\b',n):action='study_plan'
        elif old.get('action')=='study_plan' and re.search(r'\b(?:can cu|dau hieu|ket qua|danh gia|theo doi|giam do kho|quyet dinh tiep)\b',n) and re.search(r'\b(?:ke hoach|phuong an|dot thu|cuoi tuan|tuan sau)\b',n) and not re.search(r'\b(?:doi thanh|dieu chinh|tang len|giam con|lap lai|so sanh)\b',n):action='study_review'
    if not action:return None
    try:
        a=grounded({'action':action},q,old);act=a['action'];args=a['args']
        if act in ('fee_total','fee_compare'):return fee_execute(args,p,roster,root)
        if act=='curriculum_compare':
            from advisor_bridge import execute_curricula
            items=[[x['program'],x['cohort']] for x in args['items']]
            if len(items)>4:return ask('em mới hỗ trợ tối đa bốn CTĐT trong một lần đối chiếu.',p)
            return execute_curricula(items,root,p if p.get('topic')=='curriculum_comparison' else {},args['metric'])
        if act=='unsupported_scope':return ask('chưa có nguồn đã đối chiếu đúng khóa; không áp dụng bảng khóa khác.')
        if act=='policy_lookup':
            if (args['instrument'],args['article'],args['clause'],args['question_type'])!=('3626',36,3,'return_deadline'):return None
            from advisor_decision import source
            c=source(root,36,3);m=re.search(r'Sinh viên nghỉ học tạm thời nếu muốn học tiếp phải có đơn[^.]+\.',c['answer'],re.I)
            if not m:return ask('chưa xác minh được câu quy định về thời hạn nộp đơn.',p)
            return source_response('Dạ cô, theo khoản 3 Điều 36 QĐ 3626: '+m[0]+' Cần đối chiếu phạm vi áp dụng và thủ tục của UET.','return_to_study',c),{'kind':'policy_clause','article':36,'clause':3,'instrument':'3626'}
        if act=='clarify_student':return ask('cô mở hồ sơ hợp lệ trong phiên này hoặc nhập MSSV nhé.')
        if act in ('study_plan','study_review'):
            sid=args['student'];sig=snapshot(roster)
            if ids and ids!={sid} or p.get('scope')!=sig or not find_student(roster,sid) or scope_error(norm(q),roster):return ask('hồ sơ đã thay đổi hoặc không khớp; cô xác nhận lại sinh viên.')
            prior_sid=p.get('student') or p.get('mssv')
            if sid!=prior_sid:return ask('cô mở đúng hồ sơ sinh viên trước khi đổi đối tượng.')
            if args['days']!=7 or not 5<=args['minutes']<=180:return ask('em mới hỗ trợ kế hoạch thử bảy ngày, 5–180 phút/ngày.',p)
            if act=='study_plan':
                from advisor_bridge import transition_study
                # Keep the original wording; no discarded constraints.
                r=transition_study(q,p,explicit,classified,roster,root)
                if r is None:
                    # Only use canonical phrasing for the fully specified simple daily plan.
                    if re.search(r'\b(?:khong|tru|nghi|chi hoc|doi mon|tap trung|mon |hoc phan|gio |buoi sang|buoi toi)\b',n):return ask('cô xác nhận thêm ràng buộc của kế hoạch tự học.',p)
                    r=transition_study(f'Lập kế hoạch tự học một tuần mỗi ngày {args["minutes"]} phút.',p,explicit,classified,roster,root)
                return r or ask('chưa lập được kế hoạch trong phạm vi hồ sơ.',p)
            from advisor_mission import review
            if p.get('kind')!='advisor_mission':return ask('chưa có kế hoạch tự học để đánh giá.',p)
            # Respect existing explicit review selection; use combined review for
            # implicit end-of-week evaluation only when no explicit view was chosen.
            from mission_intent import explicit_views
            views=explicit_views(norm(q)) or ['risks','next_steps']
            text,tools,sources=review(find_student(roster,sid),roster,root,p['states'],p.get('pending',[]),views)
            r=response('Dạ cô, '+text,'mission_review',tools,sources,'STUDENT_STATUS',sid);r['metadata'].update(mission_step='review',review_views=views,review_planner='grounded_review');return r,p
    except (ValueError,KeyError,TypeError,OSError):return ask('em chưa xác định chắc các tham số hoặc nguồn của yêu cầu này; cô xác nhận lại phạm vi nhé.',p)
    return None
