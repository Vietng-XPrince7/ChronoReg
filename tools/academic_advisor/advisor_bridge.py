"""Bounded orchestration of verified public lookups and scoped tasks.
Only product AUTO non-RED. No model-supplied data, no arbitrary rewritten queries.
"""
import re
from quality import norm
from quality_routes import response,find_student,source_response
from quality_workflows import snapshot
from workflow import scope_error
from semantic_product import fee_year
import reviewed_sources as rs

PROGRAMS={'cntt':r'\b(?:cntt|cong nghe thong tin)\b',**rs.SUMMARY_PROGRAMS}
NAMES={'cntt':'CNTT','khmt':'Khoa học máy tính','httt':'Hệ thống thông tin','ktmt':'Kỹ thuật máy tính'}
EXCLUDE=r'\b(?:hutech|ulis|uit|bach khoa|thac si|tien si|ngoai le|dac cach|tam khoa|chua duyet|5115|3079|thong tu|nghi dinh|gui ngay|sua diem|cong khai|sinh vien khac|lop khac)\b'
SPECIAL=r'\b(?:clc|chat luong cao|nhat ban|tt 23|chuan quoc te|dmktkt|tri tue nhan tao|mang may tinh|khoa hoc du lieu)\b'
def ask(t,p=None):return response('Dạ cô, '+t,'advisor_clarification'),p or {}
def state(topic,**kw):return {'kind':'advisor_agent','topic':topic,**kw}
def fmt(x):return f'{x:,}'.replace(',','.')

def compare_curricula(q,n,p,root):
    old=p if p.get('topic')=='curriculum_comparison' else {}
    majors=[k for k,v in PROGRAMS.items() if re.search(v,n)]; years=rs.cohort_values(n)
    if re.search(EXCLUDE,n) or re.search(SPECIAL,n) or re.search(r'\b(?:hoc phi|hoc bong|nckh|diem chuan|mssv|\d{8}|nam hoc|tien quyet|hoc lai)\b',n):return None
    if old and re.search(r'\b(?:tuong duong|dang ky thay|thay the hoc phan|quy doi ma)\b',n):
        return ask('không thể xác nhận tương đương học phần chỉ từ mã hoặc số tín chỉ. Cần bảng chuyển đổi hoặc quyết định công nhận đúng ngành và khóa của từng sinh viên.',old)
    items=None
    request=bool(re.search(r'\b(?:so sanh|khac nhau|doi chieu|chenh lech)\b',n) and re.search(r'\b(?:tong|toan khoa|khoa luan|tong so tin chi)\b',n) and not re.search(r'\b(?:dang ky|gioi han|hoc phan|bao luu|tuong duong|chuyen doi|mon)\b',n) and not rs.CODE.search(q))
    if request and len(majors)==1 and 2<=len(years)<=4:
        items=[[majors[0],y] for y in sorted(years)]
    elif request and len(years)==1 and 2<=len(majors)<=4:
        items=[[k,next(iter(years))] for k in majors]
    elif request and len(majors)>=2 and len(years)>=2:
        parts=re.split(r'\b(?:voi|so voi|va|con)\b',n)
        pairs=[]
        for part in parts:
            ms=[k for k,v in PROGRAMS.items() if re.search(v,part)];ys=rs.cohort_values(part)
            if not ms and not ys:continue
            if len(ms)!=1 or len(ys)!=1:return ask('cần ghép rõ từng ngành với từng khóa để so sánh.',old)
            pairs.append([ms[0],next(iter(ys))])
        if not 2<=len(pairs)<=4 or len({tuple(x) for x in pairs})!=len(pairs):return ask('cần xác định từng ngành và khóa để so sánh.',old)
        items=pairs
    elif old and re.search(r'\b(?:thay|doi)\b',n) and re.search(r'\b(?:giu|giu nguyen)\b',n):
        # Split explicit replacement vs retained target; never switch both.
        parts=re.split(r'\bgiu(?: nguyen)?\b',n,maxsplit=1)
        if len(parts)!=2:return None
        selections=[]
        for part in parts:
            ys=rs.cohort_values(part);ms=[k for k,v in PROGRAMS.items() if re.search(v,part)]
            if len(ys)!=1 or len(ms)!=1:return ask('cần xác nhận ngành và khóa cho từng đối tượng so sánh.',old)
            selections.append([ms[0],next(iter(ys))])
        prev=old.get('items',[])
        if selections[1] not in prev or selections[0][1]==selections[1][1] or sum(x[1]==selections[0][1] for x in prev)!=1:return ask('chưa xác định được đối tượng cần thay đổi.',old)
        items=[selections[0] if x[1]==selections[0][1] else x for x in prev]
    if not items:return None
    return execute_curricula(items,root,old)

def execute_curricula(items,root,old=None,metric=None):
    old=old or {}
    if any(y not in range(2022,2027) for _,y in items):return ask('chưa có nguồn đúng khóa để so sánh.')
    records=[]
    try:
        for k,y in items:
            r=rs.load(root,k+('_2022_2024' if y<=2024 else '_2025_2026'))
            if y not in r['cohorts']:raise ValueError('scope')
            records.append(r)
    except (OSError,ValueError,KeyError,TypeError):return ask('chưa xác minh được đầy đủ nguồn của các CTĐT.',old)
    lines=['Dạ cô, em đối chiếu các chương trình theo đúng khóa tuyển sinh:','','| Ngành và khóa | Tổng tín chỉ | Khóa luận/đồ án |','|---|---:|---:|']
    sources=[]
    for (k,y),r in zip(items,records):
        lines.append(f'| {NAMES[k]} QH-{y} | {r["total"]} | {r["thesis"] if r.get("thesis") is not None else "Chưa xác minh"} |')
        sources.append({'source_path':rs.PACK,'sha256':rs.PIN,'source_url':r['source_url'],'review_id':r['id']})
    if metric and len(records)==2:
        field='thesis' if metric=='thesis_credits' else 'total'
        x,y=(r.get(field) for r in records)
        if type(x) is int and type(y) is int:
            lines.append(f'\nChênh lệch {abs(x-y)} tín chỉ ({"khóa luận/đồ án" if field=="thesis" else "tổng tín chỉ"}).')
    lines+=['','Nguồn từng khóa:']+[f'- {NAMES[k]} QH-{y}: {r["source_url"]}' for (k,y),r in zip(items,records)]+['Không tự coi mã học phần giữa hai CTĐT là tương đương; cần đối chiếu quyết định công nhận nếu chuyển đổi.']
    result=response('\n'.join(lines),'curriculum_comparison',['policy_reference','compare_sources'],sources);result['metadata']['cited_doc_ids']=[r['id'] for r in records]
    return result,state('curriculum_comparison',items=items)

def finance(q,n,p,roster,root):
    from advisor_agent import fee
    from scholarship import group_of
    old=p if p.get('topic')=='fee' else {}; f=old.get('fee',{})
    if re.search(EXCLUDE,n) or re.search(r'\b(?:\d{8}|mssv|mien|tra gop|tien no|ca ky|toan ky|clc|chat luong cao|dmktkt|dinh muc kinh te ky thuat|tt 23|nhat ban)\b',n):return None
    if re.search(r'\b(?:hoc bong|kkht)\b',n) and re.search(r'\b(?:so sanh|chenh lech|tang bao nhieu|giam bao nhieu)\b',n) and not re.search(r'\b(?:dieu kien|thuc nhan|du dieu kien|hoc phi|mien|nhan duoc|tong tien|ca nam|so thang)\b',n):
        years=re.findall(r'\b(20\d{2}) (20\d{2})\b',re.sub(rs.COHORT_RE,' ',n));cy=rs.cohort_values(n);grades=[g for g in rs.GRADES if re.search(r'\b'+g+r'\b',n)]
        if set(years)=={('2025','2026'),('2026','2027')} and len(years)==2 and len(cy)==1 and group_of(n)=='standard' and len(grades)==1 and next(iter(cy)) in (2023,2024,2025):
            cohort=next(iter(cy));grade=grades[0]
            try:a,x=rs.rate_value(root,2025,'standard',cohort,None,grade);b,y=rs.rate_value(root,2026,'standard',cohort,None,grade)
            except (OSError,ValueError,KeyError,TypeError,IndexError):return ask('chưa xác minh được cả hai bảng định mức học bổng.')
            text=f'Dạ cô, CTĐT chuẩn QH-{cohort}, loại {rs.GRADES[grade][1]}: năm 2025–2026 là {fmt(x)} đồng/tháng; năm 2026–2027 là {fmt(y)} đồng/tháng; chênh lệch năm mới so với năm cũ: {fmt(y-x)} đồng/tháng. Đây là định mức, không xác nhận thực nhận.\n\nNguồn: {a["source_url"]} và {b["source_url"]}'
            result=response(text,'scholarship_comparison',['policy_reference','compare_sources','fee_calculator'],[{'source_path':rs.PACK,'sha256':rs.PIN,'source_url':r['source_url'],'review_id':r['id']} for r in (a,b)]);result['metadata']['cited_doc_ids']=[a['id'],b['id']]
            return result,state('reviewed_rate',year=2026,group='standard',cohort=cohort,subgroup=None,grade=grade)
    # Count equal-credit courses only when the wording explicitly says each.
    m=re.search(r'\b(\d{1,2}|mot|hai|ba|bon|nam|sau) mon moi mon (\d{1,2}) (?:tin chi|tc)\b',n)
    if m and re.search(r'\bhoc lai\b',n) and re.search(r'\b(?:du tru|bao nhieu|chi phi|tong tien|hoc phi)\b',n) and not re.search(r'\b(?:hoc bong|so sanh|khong hoc lai|hoc lan dau|giam|tru mon|ngoai|them|khong tinh)\b',n) and len(re.findall(r'\b\d{1,2} (?:tin chi|tc)\b',n))==1 and not re.search(r'\d[.,]\d+\s*(?:tín chỉ|tc)',q,re.I):
        words={'mot':1,'hai':2,'ba':3,'bon':4,'nam':5,'sau':6}; count=words.get(m[1],int(m[1]) if m[1].isdigit() else 0);qty=count*int(m[2]);cy=rs.cohort_values(n);year=fee_year(q)
        if len(cy)!=1 or not year or group_of(n)!='standard' or not 1<=qty<=30:return ask('cần đúng một khóa, chương trình chuẩn, năm học và tổng tín chỉ học lại hợp lệ.')
        c=next(iter(cy));query=f'Học phí học lại {qty} tín chỉ CTĐT chuẩn QH-{c} năm học {year} hết bao nhiêu tiền?'
        return fee(query,norm(query),{},roster,root)
    if f and f.get('quantity') and fee_year(q) and re.search(r'\b(?:chuyen|doi|sang)\b',n) and re.search(r'\b(?:tang (?:them )?bao nhieu|giam (?:di )?bao nhieu|chenh lech|chenh bao nhieu)\b',n) and not re.search(r'\b(?:hoc bong|ctdt|chuong trinh|khoa|k\d{2}|qh)\b',n):
        qty=f['quantity'];cy=f['cohort'];year=fee_year(q)
        stated=re.findall(r'\b(\d{1,2}) (?:tin chi|tc)\b',n)
        if stated and (len(stated)!=1 or int(stated[0])!=qty or not re.search(r'\b(?:van|giu nguyen|do|ay)\b',n)):return ask('cô xác nhận số tín chỉ muốn giữ khi so sánh.',old)
        if re.search(r'\b(?:them|bot|doi so|giam so|tang so|khong hoc lai)\b',re.sub(r'\btang them bao nhieu\b','tang bao nhieu',n)) or re.search(r'\d[.,]\d+\s*(?:tín chỉ|tc)',q,re.I):return None
        if f.get('scope')!='standard':return None
        def get(y):
            query=f'Học phí học lại {qty} tín chỉ CTĐT chuẩn QH-{cy} năm học {y} hết bao nhiêu tiền?';return fee(query,norm(query),{},roster,root)
        a,b=get(f['year']),get(year)
        if not a or not b:return ask('chưa xác minh được cả hai bảng học phí.',old)
        def total(r):
            x=re.search(r'= \*\*([\d.]+) đồng\*\*',r[0]['answer']);return int(x[1].replace('.','')) if x else None
        x,y=total(a),total(b)
        if x is None or y is None:return ask('chưa xác minh được cả hai tổng tiền.',old)
        r,c=b;d=y-x;r['answer']+=f'\n\nSo với {f["year"]} ({fmt(x)} đồng), tổng tiền '+(f'tăng {fmt(d)} đồng.' if d>0 else f'giảm {fmt(-d)} đồng.' if d<0 else 'không đổi.');r['metadata']['advisor_sources']=a[0]['metadata'].get('advisor_sources',[])+r['metadata'].get('advisor_sources',[]);return r,c
    if f and re.search(r'\b(?:hoc bong|kkht)\b',n) and re.search(r'\b(?:dinh muc|muc|muc nao|bao nhieu)\b',n) and re.search(r'\b(?:em nay|em ay|sinh vien nay)\b',n) and not rs.cohort_values(n) and not re.search(SPECIAL,n):
        grades=[g for g in rs.GRADES if re.search(r'\b'+g+r'\b',n)];year=fee_year(q)
        if len(grades)!=1 or not year or f.get('scope')!='standard':return ask('cần xác định loại học bổng và năm học.',old)
        query=f'Mức học bổng KKHT CTĐT chuẩn QH-{f["cohort"]} năm học {year} loại {rs.GRADES[grades[0]][1]}'
        return rs.rate_route(norm(query),{},root) or ask('chưa có định mức học bổng đã đối chiếu cho năm học này.')
    if p.get('topic')=='reviewed_rate' and re.search(r'\b(?:gia dinh|neu duoc nhan)\b',n) and re.search(r'\b(?:tong tien|tong cong|bao nhieu)\b',n):
        months=re.findall(r'\b(\d{1,2}) thang\b',n)
        if len(months)!=1 or not 1<=int(months[0])<=12 or fee_year(q) or rs.cohort_values(n) or group_of(n) or any(re.search(r'\b'+g+r'\b',n) for g in rs.GRADES) or re.search(r'\b(?:hoc phi|tru|giam|mien|khong nhan|thay vi)\b',n):return None
        try:
            rec,v=rs.rate_value(root,p.get('year',2025),p['group'],p['cohort'],p.get('subgroup'),p['grade'])
        except (OSError,ValueError,KeyError,TypeError,IndexError):return ask('chưa xác minh lại được định mức.',p)
        k=int(months[0]);return rs.reply(rec,f'Dạ cô, theo giả định {k} tháng: {k} × {fmt(v)} = **{fmt(k*v)} đồng**. Đây chỉ là phép tính theo định mức, không xác nhận số tháng được cấp hay số tiền thực nhận.',p.get('year',2025)),p
    return None

def policy(q,n,p,root):
    if re.search(EXCLUDE,n) or re.search(r'\b(?:\d{8}|mssv|k\d{2}|qh|hieu luc|ap dung|soan|gui)\b',n):return None
    if any(x!='3626' for x in re.findall(r'\b(?:qd|quyet dinh) (\d+)\b',n)) or re.search(r'\b(?:khong phai|thay vi|quy che khac|van ban khac|dieu 21|dieu 23|dieu 47)\b',n):return None
    explicit=bool(re.search(r'\b(?:qd|quyet dinh) 3626\b',n));old=p.get('topic')=='dual_degree'
    follow=old and re.search(r'\b(?:gpa|diem trung binh)\b',n) and re.search(r'\b(?:tang|giam|du dieu kien|tu dong)\b',n)
    dual=bool(re.search(r'\b(?:hai (?:ctdt|chuong trinh)|chuong trinh thu hai|nganh thu hai|hoc cung luc hai|hoc dong thoi hai)\b',n))
    bonus=bool(re.search(r'\b(?:nckh|nghien cuu khoa hoc)\b',n) and re.search(r'\b(?:hang tot nghiep|xep hang tot nghiep|xep loai hoc luc|phan loai hoc luc)\b',n) and re.search(r'\b(?:diem thuong|cong diem|phan thuong|thuong diem)\b',n))
    same_document=bool((old or p.get('topic')=='evidence_article' and p.get('article')==32) and re.search(r'\b(?:quyet dinh do|cung quyet dinh|van ban do|cung van ban|quy che do)\b',n))
    if not ((explicit and dual) or follow or (bonus and (explicit or same_document))):return None
    if dual and bonus:return None
    from advisor_decision import source
    try:c=source(root,32 if bonus else 26,1)
    except (OSError,ValueError,KeyError,TypeError):return ask('chưa xác minh được điều khoản đúng văn bản.')
    s=norm(c['answer'])
    if bonus:
        if not re.search(r'khong.{0,100}(?:xep hang|xep loai|xac dinh hang).{0,80}tot nghiep',s):return ask('chưa xác minh được điều kiện điểm thưởng trong nguồn.')
        if 'khong dung de xep loai hoc luc' not in s or 'xac dinh hang tot nghiep' not in s:return ask('chưa xác minh được phạm vi sử dụng điểm thưởng trong nguồn.')
        text='Dạ cô, không dùng điểm thưởng nghiên cứu khoa học để xếp loại học lực hoặc xác định hạng tốt nghiệp. Căn cứ khoản 1 Điều 32 QĐ 3626:\n\n'+c['answer']
        new=state('evidence_article',article=32,decision=None)
    else:
        if not all(x in s for x in ('2 5','2 0','dieu kien trung tuyen','nguong bao dam chat luong dau vao','don xin hoc them','tra hoc phi')):return ask('chưa xác minh được đầy đủ các nhánh điều kiện trong nguồn.')
        from advisor_decision import ascii_text
        vals=re.findall(r'\b(?:gpa|diem trung binh)(?: chung)?(?: (?:tat ca )?cac hoc phan| tat ca hoc phan| hoc phan)?(?: tang len| tang| giam con| giam| dat| bang| la| chi| chi dat| chi con)?\s+([0-4](?:[.,]\d{1,2})?)(?![.,]\d|\d)\b',ascii_text(q))
        g=float(vals[0].replace(',','.')) if len(vals)==1 else None
        lead='Dạ cô, không thể kết luận chỉ từ GPA; còn phải đối chiếu đầy đủ các điều kiện.'
        if g is not None and 0<=g<=4:
            if g<2:lead='Dạ cô, mức GPA nêu ra chưa đạt ngưỡng điểm của cả hai nhánh.'
            elif g<2.5:lead='Dạ cô, mức GPA nêu ra chỉ đạt ngưỡng điểm của nhánh từ 2,0, chưa đủ để kết luận; còn phải đáp ứng điều kiện trúng tuyển và các yêu cầu khác.'
            else:lead='Dạ cô, mức GPA nêu ra đạt ngưỡng điểm của cả hai nhánh, nhưng chưa đủ để tự động kết luận; còn phải xác minh ngưỡng đầu vào hoặc điều kiện trúng tuyển và các yêu cầu khác.'
        text=lead+'\n\nCăn cứ khoản 1 Điều 26 QĐ 3626:\n\n'+c['answer'];new=state('dual_degree')
    r=source_response(text+'\n\nĐây là đối chiếu văn bản, chưa xác nhận hiệu lực cho khóa cụ thể.','bounded_policy',c);return r,new

def notice(q,n,p,roster,root):
    if p.get('topic')!='reviewed_notice' or p.get('academic_year')!='2025-2026' or re.search(EXCLUDE,n) or re.search(r'\b(?:\d{8}|mssv|k\d{2}|qh|hoc bong|hoc phi|202[0-9])\b',n):return None
    if p.get('notice')=='research' and re.search(r'\bcap truong\b',n) and re.search(r'\b(?:moc|han|ngay nao|thoi gian)\b',n):return rs.route('Hạn NCKH cấp Trường năm học 2025–2026?',{},root)
    if re.search(r'\b(?:cung nam hoc|nam hoc do|nam hoc nay)\b',n) and re.search(r'\bket thuc\b',n):
        from calendar_source import SEM
        from semantic_product import execute
        terms=[k for k,pat in SEM.items() if re.search(pat,n)]
        if len(terms)==1:
            slots={'academic_year':p['academic_year'],'semester':terms[0]};r=execute({'intent':'calendar','slots':slots},roster,root,q)
            from advisor_tasks import calendar_presentation
            calendar_presentation(r);return r,{'kind':'semantic_task','plan':{'intent':'calendar','slots':slots},'scope':snapshot(roster)} if r['metadata'].get('engine_mode')=='SOURCE_TABLE' else p
    return None

def route(q,p,explicit,classified,roster,root):
    if explicit or classified:return None
    n=norm(q)
    for f,args in ((compare_curricula,(q,n,p,root)),(policy,(q,n,p,root)),(finance,(q,n,p,roster,root)),(notice,(q,n,p,roster,root))):
        r=f(*args)
        if r is not None:return r
    return None


def transition_study(q,prior,explicit,classified,roster,root):
    from advisor_tasks import daily_study,route as task_route
    from advisor_mission import successful,safe_norm,BLOCK
    n=safe_norm(q)
    if not daily_study(n) or BLOCK.search(n) or re.search(r'\b(?:soan|viet|email|tin nhan|loi nhan|hoc lai|lo trinh|tin chi|tc|khong lap|khong can lap|khong muon lap|dung lap|bo ke hoach|khong tu hoc)\b',n) or re.search(r'\b[A-Z]{3}\d{4}\b',q) or re.search(r'\d[.,]\d+\s*phút',q,re.I):return None
    kind=prior.get('kind');topic=prior.get('topic');sig=snapshot(roster)
    if kind=='student' and prior.get('meeting'):
        sid=prior.get('mssv');meeting={'kind':'advisor_task','topic':'meeting','scope':prior.get('scope'),'mssv':sid,'topics':prior.get('topics',[])};states={'meeting':meeting};pending=[]
    elif kind=='student':
        sid=prior.get('mssv');states={'profile':{'kind':'advisor_agent','topic':'profile','student':sid,'scope':prior.get('scope')}};pending=[]
    elif kind=='advisor_task' and topic in ('meeting','student_priority'):
        sid=prior.get('mssv');states={'meeting' if topic=='meeting' else 'priorities':prior};pending=[]
    elif kind=='advisor_agent' and topic in ('profile','study_plan','retake'):
        sid=prior.get('student');states={{'profile':'profile','study_plan':'study','retake':'retake'}[topic]:prior};pending=[]
    elif kind=='advisor_mission':
        sid=prior.get('student');states=dict(prior.get('states',{}));pending=list(prior.get('pending',[]))
    else:return None
    ids=set(re.findall(r'\b\d{8}\b',q))|{str(x) for x in (explicit,classified) if x}
    if ids and ids!={sid}:return None
    if scope_error(n,roster) or prior.get('scope')!=sig or not find_student(roster,sid):return ask('hồ sơ đã thay đổi hoặc không khớp; cô xác nhận lại sinh viên trước khi tiếp tục.')
    carry=states.get('study') or states.get('meeting') or states.get('priorities') or {'kind':'advisor_agent','topic':'profile','student':sid,'scope':sig}
    result=task_route(q,n,carry,None,None,roster,root)
    if result is None:return None
    r,c=result
    if not successful('study',r,c) or c.get('student')!=sid or c.get('scope')!=sig:return r,prior
    # Preserve already completed subtasks; re-evaluate facts on every review.
    states['study']=c
    new={'kind':'advisor_mission','student':sid,'scope':sig,'states':states,'pending':[x for x in pending if x!='study']}
    r['metadata'].update(mission_step='study',mission_planner='scoped_transition')
    return r,new


def promote_retake(prior,roster,root):
    # Re-execute the validated simple plan to obtain the native typed state.
    # Preserve specialized semantic plans with course constraints as-is.
    slots=prior.get('plan',{}).get('slots',{});sid=slots.get('student');cap=slots.get('budget');sig=snapshot(roster)
    if set(slots)-{'student','budget'} or not re.fullmatch(r'\d{8}',str(sid)) or type(cap) is not int or not 1<=cap<=30 or prior.get('scope')!=sig or not find_student(roster,sid):return None
    from advisor_agent import route as agent
    from advisor_mission import successful
    try:result=agent(f'Lập lộ trình học lại mỗi đợt {cap} tín chỉ cho sinh viên {sid}.',{},sid,None,roster,root)
    except (OSError,ValueError,TypeError,RuntimeError,KeyError):return None
    if not result or not successful('retake',*result):return None
    return {'kind':'advisor_mission','student':sid,'scope':sig,'states':{'retake':result[1]},'pending':[]}
