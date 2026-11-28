"""Read-only transitions from ranked class list to scoped student tasks, plus a
verified public notice table. No model calls, no changes to research routes."""
import hashlib,re
from quality import norm
from quality_routes import response,find_student
from quality_workflows import snapshot
from workflow import scope_error,screening,valid

ORD=re.compile(r'\b(?:ban|em|sinh vien|ho so) (?:thu )?(dau tien|nhat|hai|ba|bon|nam|[1-9]|10)\b')
ORDINAL={'dau tien':1,'nhat':1,'hai':2,'ba':3,'bon':4,'nam':5}
REF=re.compile(r'\b(?:ban|em|sinh vien) (?:ay|nay|do)\b')
BLOCK=re.compile(r'\b(?:cong khai|ca lop|toan lop|nhom lop|lop khac|sinh vien khac|ban khac|em khac|so sanh|hoc phi|hoc bong|diem chuan|quy che|ngoai le|dac cach|hutech|ulis|uit|bach khoa|gui ngay|gui di|sua diem|cham diem|bo qua|ignore|system prompt)\b')
SOURCE='data/raw/uet/markdown/2026/thong_bao_diem_trung_tuyen_2026.md'
BLOB='c4f7eae101ad61e6feb8973ff7f63b8447fc96db'
URL='https://uet.vnu.edu.vn/truong-dai-hoc-cong-nghe-dhqghn-cong-bo-diem-chuan-dai-hoc-chinh-quy-nam-2026/'

# The 20 rows in this exact repository blob were compared to UET's 09/08/2026 notice.
def parse_table(text):
    out=[]
    for line in text.splitlines():
        if not line.startswith('|'):continue
        cells=line.strip()[1:-1].split('|')
        if len(cells)!=6:continue
        _,codes,names,refs,points,criteria=cells
        cs=re.split(r'<br\s*/?>',codes.strip(),flags=re.I)
        if not all(re.fullmatch(r'[0-9A-Z]{7}',c) for c in cs):continue
        parts=lambda x:re.split(r'<br\s*/?>',x.strip(),flags=re.I)
        rr=parts(refs);pp=parts(points)
        ns=parts(names) if len(cs)>1 else [re.sub(r'<br\s*/?>',' ',names.strip(),flags=re.I)]
        tt=parts(criteria) if len(cs)>1 else [re.sub(r'<br\s*/?>',' ',criteria.strip(),flags=re.I)]
        if not len(cs)==len(rr)==len(pp)==len(ns)==len(tt):raise ValueError('ambiguous merged row')
        for c,name,ref,point,t in zip(cs,ns,rr,pp,tt):
            if not re.fullmatch(r'CN\d{1,2}',ref) or not re.fullmatch(r'\d{1,2}(?:,\d{1,2})?',point) or not 0<=float(point.replace(',','.'))<=30 or not name:raise ValueError('invalid row')
            out.append((c,name,ref,point,t or '—'))
    if len(out)!=20 or len({r[0] for r in out})!=20 or len({r[2] for r in out})!=20:raise ValueError('incomplete table')
    return out

def admissions(q,root):
    n=norm(q)
    if not re.fullmatch(r'(?:(?:cho co |cho em |cho biet |tra cuu |liet ke |bang )?)(?:diem chuan|diem trung tuyen)(?: (?:tat ca|toan bo|cac) nganh(?: dao tao)?| (?:dai hoc )?chinh quy)?(?: (?:cua )?uet)?(?: nam)? 2026(?: (?:cua )?uet)?',n):return None
    try:
        from advisor_evidence import fresh_ledger
        raw=(root/SOURCE).read_bytes(); canonical=raw.replace(b'\r\n',b'\n')
        sha=hashlib.sha256(raw).hexdigest();canonsha=hashlib.sha256(canonical).hexdigest()
        blobs={hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest() for b in (raw,canonical)}
        if BLOB not in blobs:raise ValueError('source changed')
        if any(h['content_sha256'] in (sha,canonsha) or ('2026' in h['doc_id'] and re.search(r'diem-(?:trung-tuyen|chuan)',h['doc_id'])) for h in fresh_ledger(root)):raise ValueError('source held')
        rows=parse_table(canonical.decode('utf8'))
    except (OSError,ValueError,KeyError,TypeError,UnicodeError):
        return response('Dạ cô, em chưa xác minh được bảng điểm chuẩn 2026 trong kho hiện tại. Cô có thể đối chiếu thông báo chính thức tại '+URL,'admissions_unavailable'),{}
    lines=['Dạ cô, đây là điểm trúng tuyển đại học chính quy UET năm 2026 (20 ngành, thang 30):','','| Mã XT | Ngành | Điểm | Tiêu chí phụ |','|---|---|---:|---|']
    for _,name,ref,point,t in rows:lines.append(f'| {ref} | {name} | {point} | {t.replace("<", "≤").replace("≤=", "≤")} |')
    lines+=['','Tiêu chí phụ áp dụng khi cùng điểm xét ở cuối danh sách: ưu tiên điểm cộng (ĐC) thấp hơn, sau đó thứ tự nguyện vọng (NV) cao hơn. Điểm xét tuyển theo thang 30, không phải điểm dự báo.','Nguồn: thông báo UET ngày 09/08/2026 — '+URL]
    r=response('\n'.join(lines),'admissions_all',['policy_reference'],[{'source_path':SOURCE,'source_url':URL,'sha256':sha}]);r['metadata'].update(engine_mode='SOURCE_TABLE',source_path=SOURCE,source_url=URL,sha256=sha,doc_title='Điểm trúng tuyển đại học chính quy UET 2026',source_label='Thông báo UET 09/08/2026',quality_qualified=False)
    return r,{'kind':'advisor_agent','topic':'admissions_all','year':2026}

def route(q,p,explicit,classified,roster,root):
    n=norm(q);sig=snapshot(roster);ids={str(x) for x in (explicit,classified) if x}|set(re.findall(r'\b\d{8}\b',q))
    # Public lookup has explicit year and is not a student's academic record.
    result=admissions(q,root)
    if result is not None:return result
    if BLOCK.search(n):return None
    def ask(t,carry=None):return response('Dạ cô, '+t,'advisor_clarification'),carry or {}
    oldclass=p.get('kind')=='advisor_agent' and p.get('topic')=='class'
    matches=ORD.findall(n)
    wants_plan=bool(re.search(r'\b(?:lap|de xuat|len) (?:phuong an|ke hoach)\b',n) and re.search(r'\b(?:ho tro|tu van|hoc tap)\b',n) and re.search(r'\b(?:mot tuan|bay ngay|7 ngay|1 tuan)\b',n))
    if matches and wants_plan and oldclass and not ids:
        if len(matches)!=1 or p.get('scope')!=sig or scope_error(n,roster):return ask('cô xác nhận lại danh sách ưu tiên trước khi chọn hồ sơ.')
        index=ORDINAL.get(matches[0],int(matches[0]) if matches[0].isdigit() else 0)
        count=p.get('count')
        if p.get('ranked_list') is not True or (count is not None and (type(count) is not int or not 1<=count<=10)):return ask('cô yêu cầu hiển thị lại danh sách ưu tiên trước khi chọn hồ sơ.')
        groups,_=screening(roster.get('students',[]));actual=(groups[1]+groups[2])[:count] if count is not None else groups[1]
        if not 1<=index<=len(actual):return ask('cô chọn một bạn trong danh sách đã hiển thị hoặc nhập mã sinh viên.',p)
        sid=str(actual[index-1][0]);st=find_student(roster,sid)
        if not st:return ask('hồ sơ đã thay đổi, cô chọn lại sinh viên.')
        name=str(st.get('full_name') or st.get('ho_ten') or sid)
        flags=actual[index-1][2];g=valid(st.get('gpa_semester'),0,4);debt=valid(st.get('owed_credits'),0,1000)
        text=f'Dạ cô, em đang hỗ trợ bạn thứ {index}: **{name} ({sid})**. Dữ kiện sàng lọc: '+('; '.join(flags) if flags else 'cần rà thêm hồ sơ')+'.\n\n'
        text+='**Phương án hỗ trợ trong 7 ngày**\n\n1. Ngày 1: hẹn trao đổi riêng, hỏi điều đang cản trở việc học và xác nhận bảng điểm mới, CPA, lịch học.\n2. Ngày 2: '
        text+=('đối chiếu các học phần chưa đạt và chọn một môn nền tảng cần hỗ trợ trước; không yêu cầu học dồn.' if debt is not None and debt>0 else 'thống nhất một mục tiêu học tập hoặc phát triển năng lực phù hợp với mong muốn của sinh viên.')
        text+='\n3. Ngày 3–6: thử một nhiệm vụ nhỏ mỗi ngày, ghi lại lỗi và câu hỏi cần giải đáp. Thống nhất thời lượng với sinh viên, chưa tự đặt số phút.\n4. Ngày 7: so sánh một bài tự làm đầu và cuối tuần, số buổi thực hiện và mức vừa sức; cùng điều chỉnh mục tiêu.\n\nĐây là kế hoạch hỗ trợ đề xuất, không phải quyết định học vụ. Cô cho em biết bạn có thể tự học bao nhiêu phút mỗi ngày để em chia kế hoạch cụ thể.'
        return response(text,'weekly_support',['scope_check','student_signals','action_strategy'],category='STUDENT_STATUS',sid=sid),{'kind':'advisor_agent','topic':'profile','student':sid,'scope':sig,'support_horizon':7}
    # A one-week plan with no minutes was just proposed; a daily constraint fills it.
    if p.get('kind')=='advisor_agent' and p.get('topic')=='profile' and p.get('support_horizon')==7 and REF.search(n) and re.fullmatch(r'(?:neu |con neu |vay neu )?(?:ban|em|sinh vien) (?:ay|nay|do) (?:chi )?co (\d{1,3}) phut(?: (?:tu hoc|moi ngay|hang ngay)){2}(?: thi sao)?',n):
        sid=p.get('student')
        if (ids and ids!={sid}) or p.get('scope')!=sig or scope_error(n,roster) or not find_student(roster,sid):return ask('cô xác nhận lại hồ sơ trước khi điều chỉnh kế hoạch.')
        mins=int(re.search(r'\b(\d{1,3}) phut\b',n)[1])
        from advisor_bridge import transition_study
        result=transition_study(f'Lập kế hoạch tự học một tuần, mỗi ngày chỉ có {mins} phút.',p,None,None,roster,root)
        return result or ask('cô xác nhận số phút tự học mỗi ngày.',p)
    # A direct invitation is a writing task, not a meeting counseling task.
    if re.search(r'\b(?:soan|viet|tao)\b',n) and re.search(r'\bloi moi\b',n) and re.search(r'\b(?:gap rieng|trao doi rieng)\b',n) and REF.search(n):
        sid=p.get('student') or p.get('mssv')
        if not sid or p.get('scope')!=sig or (ids and ids!={sid}) or not find_student(roster,sid) or scope_error(n,roster):return ask('cô chọn đúng sinh viên cần mời trước khi em soạn lời nhắn.')
        from advisor_draft import route as draft
        # Map a synonymous format into the existing validated drafting tool.
        n2=re.sub(r'\bloi moi\b','loi nhan moi',n)
        result=draft(q,n2,p,sid,None,roster)
        if result is None:return None
        r,data=result
        if data and p.get('kind')=='advisor_mission' and data.get('student')==sid:
            new={k:v for k,v in p.items() if k!='exp'};new['states']={**p.get('states',{}),'draft':data};new['pending']=[x for x in p.get('pending',[]) if x!='draft'];r['metadata']['mission_step']='draft';return r,new
        return r,data
    return None
