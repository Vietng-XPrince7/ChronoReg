"""Bounded read-only multi-tool planner for individual advising.
The model selects and orders registered tools, never executes code or supplies
student IDs, numeric facts, source citations, or free-form advice. Explicit
requested tasks and constraints are checked independently. No research changes.
"""
import json,re,urllib.request
from quality import norm
from quality_routes import response,find_student
from quality_workflows import snapshot,route_workflow
from workflow import scope_error
from semantic_planner import MODEL

TOOLS={
 'profile': 'Tổng quan hồ sơ: nợ, tích lũy, GPA kỳ, CPA và rèn luyện',
 'meeting': 'Câu hỏi tìm hiểu khó khăn và chuẩn bị gặp riêng',
 'priorities': 'Ba việc hỗ trợ ưu tiên theo hồ sơ',
 'retake': 'Lộ trình học lại theo tiên quyết và trần tín chỉ mỗi đợt',
 'study': 'Kế hoạch tự học một tuần, giới hạn phút/ngày',
 'draft': 'Bản nháp lời mời trao đổi riêng, không gửi',
}
LABELS={'profile':'Tình hình học tập','meeting':'Chuẩn bị buổi gặp','priorities':'Việc nên ưu tiên','retake':'Lộ trình học lại','study':'Kế hoạch tự học','draft':'Bản nháp lời mời riêng'}
ORDER=tuple(TOOLS)
BLOCK=re.compile(r'\b(?:ca lop|toan lop|so sanh|cong khai|nhom lop|lop khac|sinh vien khac|em khac|hai sinh vien|gui|dang len|phe duyet|cham diem|sua diem|hoc phi|hoc bong|diem chuan|quy che|ngoai le|tam khoa|hoc ky|moi ky|lich mo lop|tru mon|bo mon|khong hoc|khong cung|cung dot|uu tien mon|truoc mon|thay vi|khong phai|ngoai tru|hutech|ulis|uit|bach khoa)\b')
# "GPA học kỳ" is a metric, not a request for a semester schedule.
def safe_norm(q):return re.sub(r'\b(?:gpa|diem trung binh) hoc ky\b','gpa',norm(q))
PATTERNS={
 'profile':r'\b(?:phan tich|ra soat|tom tat|tong quan|danh gia|xem)\b.{0,80}\b(?:ho so|tinh hinh hoc tap|ket qua hoc tap|sinh vien)\b|\b(?:bao nhieu|cho co biet|tra cuu)\b.{0,60}\b(?:tin chi no|gpa|cpa|tin chi tich luy)\b',
 'meeting':r'\b(?:nen hoi|cau hoi|hoi gi|chuan bi buoi gap|chuan bi buoi trao doi|chuan bi gap rieng|tim hieu kho khan)\b',
 'priorities':r'\b(?:viec (?:can |nen )?uu tien|hanh dong uu tien|nen lam gi|de xuat ho tro|bien phap ho tro|ho tro the nao)\b',
 'retake':r'\b(?:lo trinh|phuong an|ke hoach|xep|chia)\b.{0,60}\b(?:hoc lai|mon no|tra no)\b',
 'study':r'\b(?:ke hoach|lich|phuong an)\b.{0,30}\btu hoc\b',
 'draft':r'\b(?:soan|viet|tao|chuyen thanh)\b.{0,35}\b(?:email|tin nhan|loi nhan|thu moi)\b.{0,100}\b(?:moi|hen|trao doi|tu van)\b',
}

def infer(question,allowed,required):
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):return None
    schema={'type':'object','properties':{'steps':{'type':'array','items':{'type':'string','enum':allowed},'minItems':2,'maxItems':6}},'required':['steps'],'additionalProperties':False}
    prompt='Lập kế hoạch công cụ cho cố vấn học tập. Không trả lời, không tạo dữ kiện. Chỉ chọn bước phù hợp, giữ đủ bước bắt buộc, profile trước các bước tư vấn, draft cuối. Không tự thêm lời mời nếu không được yêu cầu. Danh mục: '+json.dumps({k:TOOLS[k] for k in allowed},ensure_ascii=False)+'. Bắt buộc: '+', '.join(required)
    body={'model':MODEL,'messages':[{'role':'system','content':prompt},{'role':'user','content':re.sub(r'\b\d{8}\b','[MSSV]',question)}],'format':schema,'stream':False,'think':False,'options':{'temperature':0,'num_predict':80,'num_ctx':2048,'num_gpu':0}}
    req=urllib.request.Request('http://127.0.0.1:11434/api/chat',data=json.dumps(body,ensure_ascii=False).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect()).open(req,timeout=45) as r:d=json.load(r)
    if d.get('done_reason')=='length':raise ValueError('truncated plan')
    return json.loads(d['message']['content'])

def checked_plan(obj,allowed,required):
    if not isinstance(obj,dict) or set(obj)!={'steps'} or not isinstance(obj['steps'],list):raise ValueError('plan schema')
    steps=obj['steps']
    if not 2<=len(steps)<=6 or any(type(x) is not str or x not in allowed for x in steps) or len(set(steps))!=len(steps) or not set(required)<=set(steps):raise ValueError('plan scope')
    if 'profile' in steps and steps[0]!='profile' or 'draft' in steps and steps[-1]!='draft':raise ValueError('plan dependency')
    return steps

def ask(text,prior=None):return response('Dạ cô, '+text,'mission_clarification'),prior or {}
def clean(text):
    t=re.sub(r'^Dạ cô,\s*','',text.strip(),count=1)
    return t[:1].upper()+t[1:]

def review(st,roster,root,states,pending,views=None):
    from mission_review import synthesize
    return synthesize(st,roster,root,states,pending,views)

def mission_review_request(n):
    return bool(re.fullmatch(r'(?:theo em )?(?:co |em )?(?:(?:nen |can )?uu tien (?:viec |dieu |gi |cai )?(?:gi |nao )?(?:truoc|nhat)|(?:tom tat|tong hop|ra soat) (?:lai )?(?:ke hoach|phuong an|nhiem vu)(?: (?:nay|tren|vua roi|cho co))?|(?:ke hoach|phuong an) (?:nay |tren )?co (?:phu hop|kha thi) khong)(?: (?:giup co|cho em|cho co|a|khong|khong a))?',n))

def mission_advice(q,n,old,ids,roster,root,enabled=False):
    # Comparison and review of a mission are read-only; never switch student or
    # silently treat a new alternative as the accepted retake plan.
    compare=bool(re.search(r'\b(?:so sanh|doi chieu)\b',n) and re.search(r'\b(?:hoc lai|mon no|tra no|moi dot)\b',n))
    trade=bool(re.search(r'\b(?:hoc don|tra no nhanh|hoc qua nhieu)\b',n) and re.search(r'\b(?:co nen|nen|rui ro|danh doi|phu hop)\b',n) and not re.search(r'\b\d+ (?:tin chi|tc|phut)\b',n))
    summary=mission_review_request(n)
    from mission_intent import plan,eligible
    views=[];mode=None
    if summary:
        views=['feasibility'] if re.search(r'\b(?:kha thi|phu hop)\b',n) else ['summary'] if re.search(r'\b(?:tom tat|tong hop)\b',n) else ['priority']
        mode='explicit_review'
    if not (compare or trade or summary or (old and eligible(n))):return None
    if (compare or trade) and re.search(r'\b(?:soan|viet|email|tin nhan|tu hoc|dieu chinh|doi thanh|lap ke hoach|lap lo trinh)\b',n):return None
    # Strip comparison only for this narrow read-only route; other blocks remain.
    if BLOCK.search(re.sub(r'\bso sanh\b','',n)) or re.search(r'\b[A-Z]{3}\d{4}\b',q):return None
    if not old:return None
    if len(ids)>1 or ids and ids!={old.get('student')} or scope_error(n,roster):return ask('cô xác nhận đúng sinh viên của nhiệm vụ trước khi tiếp tục.')
    if old.get('scope')!=snapshot(roster):return ask('hồ sơ đã thay đổi; cô xác nhận lại sinh viên trước khi tiếp tục.')
    sid=old.get('student');st=find_student(roster,sid)
    if not st:return ask('hồ sơ sinh viên không còn trong phạm vi.')
    states=old.get('states',{});sub=states.get('retake') or states.get('profile')
    if compare or trade:
        if not sub:return ask('cô cần có hồ sơ hoặc lộ trình của sinh viên trước khi so sánh.',old)
        from advisor_agent import route as agent
        if trade and sub.get('topic')=='retake':
            cap=sub.get('plan',{}).get('budget')
            if type(cap) is int:
                fresh=agent(f'Lập lộ trình học lại mỗi đợt {cap} tín chỉ theo tiên quyết.',sub,None,None,roster,root)
                if not fresh or not successful('retake',*fresh):return ask('chưa xác minh lại được lộ trình hiện tại; không nên quyết định tăng tải trước khi kiểm tra bảng tiên quyết.',old)
                sub=fresh[1]
        result=agent(q,sub,None,None,roster,root)
        if result is None:return ask('cô xác nhận các mức tín chỉ muốn so sánh hoặc nội dung cần phản biện.',old)
        r,c=result;intent=r.get('metadata',{}).get('advisor_intent')
        if intent not in ('retake_compare','retake_tradeoff'):return ask('em chưa xác minh được phương án; cô kiểm tra lại yêu cầu.',old)
        if c.get('student')!=sid or c.get('scope')!=old.get('scope'):return ask('cô xác nhận đúng hồ sơ trước khi tiếp tục.')
        r['metadata']['mission_step']='comparison' if compare else 'review'
        if trade and 'study' in states:
            minutes=states['study'].get('minutes')
            if type(minutes) is int:r['answer']+=f'\n\nKế hoạch tự học hiện đặt {minutes} phút/ngày. Chưa có căn cứ để quy đổi thời lượng đó thành tải học phần; nên thử và đánh giá trước khi tăng tải.'
        return r,old
    if not views:views,mode=plan(q,enabled)
    if not views:return ask('cô muốn em tóm tắt, đánh giá tính khả thi, chỉ ra rủi ro hay đề xuất bước tiếp theo của phương án?',old)
    text,tools,sources=review(st,roster,root,states,old.get('pending',[]),views)
    r=response('Dạ cô, '+text,'mission_review',tools,sources,'STUDENT_STATUS',sid)
    r['metadata'].update(mission_step='review',review_views=views,review_planner=mode)
    if mode=='local_model_review':r['metadata'].update(model_name=MODEL,inference_source=mode)
    return r,old
def successful(k,r,c):
    if not c or not r.get('metadata',{}).get('workflow_tools'):return False
    if k=='retake':return type(c.get('plan',{}).get('rounds')) is int and c['plan']['rounds']>0
    return c.get('topic')=={'profile':'profile','study':'study_plan','draft':'draft','meeting':'meeting','priorities':'student_priority'}[k]


def route(question,prior,explicit,classified,roster,root,enabled=False):
    from advisor_agent import route as agent
    n=safe_norm(question); old=prior if prior.get('kind')=='advisor_mission' else {}; sig=snapshot(roster)
    ids=set(re.findall(r'\b\d{8}\b',question)); selected={str(x) for x in (explicit,classified) if x}; explicit_ids=ids|selected
    proposed=re.findall(r'\b(?:nang|tang) tai (?:len|thanh) (\d{1,2}) (?:tin chi|tc)\b',n)
    if old and len(proposed)==1 and re.search(r'\b(?:dong y|nen|rui ro|kha thi)\b',n) and not re.search(r'\b(?:sinh vien khac|lop khac|hoc phi|hoc bong|ngoai le|gui|cong khai)\b',n):
        cap=old.get('states',{}).get('retake',{}).get('plan',{}).get('budget');newcap=int(proposed[0]);sid=old.get('student')
        if type(cap) is int and 1<=newcap<=30 and cap!=newcap and (not explicit_ids or explicit_ids=={sid}) and old.get('scope')==sig and not scope_error(n,roster):
            cmp=agent(f'So sánh phương án học lại {cap} tín chỉ và {newcap} tín chỉ mỗi đợt.',old['states']['retake'],None,None,roster,root)
            if cmp and cmp[0].get('metadata',{}).get('advisor_intent')=='retake_compare':
                rr=cmp[0];rr['answer']+='\n\nEm chưa khuyến nghị tăng tải ngay. Cần kiểm tra CPA, lịch mở lớp, lịch học hiện tại và khả năng hoàn thành từng môn.'
                minutes=old.get('states',{}).get('study',{}).get('minutes')
                if type(minutes) is int:rr['answer']+=f' Thời gian tự học đã nêu là {minutes} phút/ngày; nên thử một tuần rồi đánh giá lại.'
                rr['metadata']['mission_step']='comparison';return rr,old
    advice=mission_advice(question,n,old,explicit_ids,roster,root,enabled)
    if advice is not None:return advice
    # A request to explain foundational priority is not a constraint on a named course.
    blocked_n=re.sub(r'\b(?:vi sao|tai sao) nen uu tien mon nen tang(?: truoc)?\b','',n)
    if BLOCK.search(blocked_n) or re.search(r'\b[A-Z]{3}\d{4}\b',question) or re.search(r'\b\d+[.,]\d+\s*(?:tín chỉ|phút)',question,re.I):return None
    # Two named numeric revisions can be applied together. Only accept the
    # complete grammar; an extra constraint never disappears in canonicalization.
    if old and (not explicit_ids or explicit_ids=={old.get('student')}):
        pair=re.fullmatch(r'(?:co )?(?:doi|dieu chinh|giam|tang) (?:lo trinh hoc lai|lo trinh) (?:thanh|con|toi da) (\d{1,2}) (?:tin chi|tc) moi dot (?:va )?(?:doi|dieu chinh|giam|tang) (?:ke hoach tu hoc|tu hoc) (?:thanh|con|toi da) (\d{1,3}) phut moi ngay',n)
        if pair:
            if scope_error(n,roster) or old.get('scope')!=sig:return ask('hồ sơ đã thay đổi hoặc không khớp phạm vi; cô xác nhận lại trước khi chỉnh sửa.')
            if not (1<=int(pair[1])<=30 and 5<=int(pair[2])<=180):return ask('cô xác nhận trần từ 1–30 tín chỉ/đợt và 5–180 phút/ngày.',old)
            first=route(f'Đổi lộ trình học lại thành {pair[1]} tín chỉ mỗi đợt.',old,None,None,roster,root,enabled=False)
            if not first or first[0]['metadata'].get('mission_step')!='retake':return ask('chưa sửa được lộ trình; em giữ nguyên cả hai phần để cô kiểm tra lại.',old)
            second=route(f'Điều chỉnh kế hoạch tự học còn {pair[2]} phút mỗi ngày.',first[1],None,None,roster,root,enabled=False)
            if not second or second[0]['metadata'].get('mission_step')!='study':return ask('chưa sửa được kế hoạch tự học; em giữ nguyên cả hai phần để cô kiểm tra lại.',old)
            rr,ss=first[0],second[0];meta=[rr['metadata'],ss['metadata']]
            tools=list(dict.fromkeys(t for m in meta for t in m.get('workflow_tools',[])))
            sources=[]
            for m in meta:
                for source in m.get('advisor_sources',[]):
                    if source not in sources:sources.append(source)
            r=response('Dạ cô, em đã điều chỉnh cả hai phần; giữ nguyên các nội dung khác.\n\n**Lộ trình học lại**\n'+clean(rr['answer'])+'\n\n**Kế hoạch tự học**\n'+clean(ss['answer']),'mission_revision',tools,sources,'STUDENT_STATUS',old['student']);r['metadata']['mission_step']='retake_study';return r,second[1]
    detected=[k for k in ORDER if re.search(PATTERNS[k],n)]
    if old and re.search(r'\bbo sung ke hoach\b',n) and re.search(r'\btu hoc\b',n) and 'study' not in detected:detected.append('study')
    # Extend an existing scoped task without replacing unrelated artifacts.
    # Only explicitly requested additional registered steps; all normal numeric,
    # topic, scope and privacy checks below still apply.
    extending=bool(old and len(detected)==1 and (re.match(r'^(?:co )?(?:bo sung|them|tiep theo)(?: cho em| cho co)? ',n) or (detected[0] in ('study','draft') and re.search(r'\b(?:bo sung|soan|viet|chuyen thanh)\b',n) and re.search(r'\b(?:em ay|em nay|em do|giu nguyen lo trinh)\b',n))))
    if extending:
        if explicit_ids and explicit_ids!={old.get('student')} or scope_error(n,roster) or old.get('scope')!=sig:
            return ask('cô xác nhận đúng hồ sơ của nhiệm vụ trước khi bổ sung.')
        if detected[0] in old.get('states',{}):return ask('phần này đã có trong nhiệm vụ. Cô nêu nội dung muốn chỉnh sửa nhé.',old)
    # Follow a named artifact of a prior mission, not an arbitrary pronoun.
    follow=[]
    if old and (not explicit_ids or explicit_ids=={old.get('student')}) and re.search(r'\b(?:doi|dieu chinh|rut gon|giam|viet lai|chuyen sang|chuyen|con|neu|the|chi con|nhe hon|hoi nang|trang trong|than thien)\b',n):
        if re.search(r'\b(?:tin chi|tc|hoc lai|lo trinh|hoc don)\b',n):follow.append('retake')
        if re.search(r'\b(?:phut|tu hoc|ke hoach tu hoc)\b',n):follow.append('study')
        if re.search(r'\b(?:email|tin nhan|thu moi|tieu de|giong van|ban nhap)\b',n):follow.append('draft')
        if not follow and re.search(r'\b(?:ke hoach|hoi nang|nhe hon)\b',n) and 'study' in old.get('states',{}):follow=['study']
    if not extending and len(follow)==1 and len(detected)<=1:
        if scope_error(n,roster):return ask('cô xác nhận đúng lớp và khóa của hồ sơ đang mở.')
        if old.get('scope')!=sig:return ask('hồ sơ đã thay đổi. Cô xác nhận lại sinh viên trước khi tiếp tục.')
        k=follow[0]; sub=old.get('states',{}).get(k)
        if not sub:
            if k not in old.get('pending',[]):return ask('nhiệm vụ trước chưa có phần này. Cô nêu rõ yêu cầu mới giúp em.',old)
            # Fill only explicitly pending tasks, using the original scoped ID.
            if k=='retake' and re.search(r'\b\d{1,2} (?:tin chi|tc)\b',n):sub={'kind':'advisor_agent','topic':'retake','student':old['student'],'scope':sig}
            elif k=='study' and re.search(r'\b\d{1,3} phut\b',n):sub={'kind':'advisor_agent','topic':'study_plan','student':old['student'],'scope':sig}
            else:return ask('cô xác nhận giới hạn còn thiếu cho phần này.',old)
        if not find_student(roster,old.get('student')):return ask('hồ sơ sinh viên không còn trong phạm vi.')
        result=agent(question,sub,None,None,roster,root)
        if result is None:return ask('em chưa thể áp dụng thay đổi này cho phần '+LABELS[k].lower()+'. Cô nêu rõ nội dung cần đổi nhé.',old)
        r,c=result
        if not successful(k,r,c):return r,old
        if c.get('student') not in (None,old['student']):return ask('cô xác nhận lại đối tượng.',old)
        new={k0:v for k0,v in old.items() if k0!='exp'};new['states']={**old['states'],k:c};new['pending']=[x for x in old.get('pending',[]) if x!=k]
        r['metadata']['mission_step']=k;return r,new
    broad=bool(re.search(r'\b(?:chuan bi (?:toan dien|day du|ky luong)|tu van (?:toan dien|tong the)|(?:ke hoach|phuong an) ho tro (?:toan dien|tong the))\b',n) and re.search(r'\b(?:sinh vien|ho so|gap rieng)\b',n))
    if len(detected)<2 and not broad and not extending:return None
    if not explicit_ids and not extending and not (old and re.search(r'\b(?:em ay|em nay|sinh vien nay|sinh vien do)\b',n)):return None
    if len(explicit_ids)>1 or scope_error(n,roster):return ask('cô xác nhận một sinh viên thuộc đúng hồ sơ đang mở để thực hiện các việc này.')
    if not explicit_ids and old.get('scope')!=sig:return ask('hồ sơ đã thay đổi; cô xác nhận lại sinh viên.')
    sid=next(iter(explicit_ids),old.get('student'));st=find_student(roster,sid)
    if not st:return ask('cô chọn hồ sơ sinh viên hợp lệ trước khi thực hiện.')
    # Refuse unhandled additional numeric/temporal constraints; no model guessing.
    caps=list(dict.fromkeys(re.findall(r'\b(?:toi da|khong qua|tran|gioi han|moi dot) (\d{1,2}) (?:tin chi|tc)\b',n)+re.findall(r'\b(\d{1,2}) (?:tin chi|tc) moi dot\b',n)))
    mins=list(dict.fromkeys(re.findall(r'\b(?:moi ngay|hang ngay)(?: chi co| toi da| chi)? (\d{1,3}) phut\b',n)+re.findall(r'\b(\d{1,3}) phut (?:tu hoc )?(?:moi ngay|hang ngay)\b',n)))
    if len(set(caps))>1 or len(set(mins))>1:return ask('cô xác nhận một trần tín chỉ và một thời lượng tự học để lập phương án.')
    if re.search(r'\b(?:ngay \d|luc \d|\d+ gio|phong \d|dia diem|tieu de|\d+ tu|\d+ ngay|\d+ tuan|\d+ thang|\d+ mon|\d+ viec|\d+ cau hoi|chi hoc vao|nghi chu nhat|cach ngay|cuoi tuan|hoc nhom|hoc mot minh)\b',re.sub(r'\b\d{8}\b','[mssv]',n)):return ask('em chưa hỗ trợ đầy đủ ràng buộc bổ sung trong yêu cầu tổng hợp này. Cô tách phần cần ràng buộc riêng để em không lập phương án sai.')
    if re.search(r'\b(?:khong|dung|bo|loai)\s+(?:soan|viet|phan tich|lap|ke hoach|hoi|tinh|dua|neu|de xuat)\b',n):return ask('cô xác nhận phần cần bỏ khỏi yêu cầu tổng hợp để em không thực hiện nhầm.')
    # Only explicitly requested retake/study/draft. Broad preparation may include
    # profile, priorities and meeting, but never fabricate a cap or schedule.
    required=list(detected)
    if broad:
        required=list(dict.fromkeys(['profile','meeting']+required));allowed=list(dict.fromkeys(required+['priorities']))
    else:allowed=required[:]
    if len(required)<2 and not extending:return None
    plan=[k for k in ORDER if k in required];mode='explicit_plan' if not broad else 'bounded_fallback'
    if enabled and broad:
        try:plan=checked_plan(infer(question,allowed,required),allowed,required);mode='local_model_plan'
        except (OSError,ValueError,TypeError,KeyError,TimeoutError):pass
    if broad and mode=='bounded_fallback' and 'priorities' not in plan:plan=[k for k in ORDER if k in required or k=='priorities']
    from meeting_context import update_topics
    topics,_=update_topics(question)
    states=dict(old.get('states',{})) if extending else {};sections=[];tools=[];sources=[];completed=[];pending=[x for x in old.get('pending',[]) if x not in plan] if extending else []
    for k in plan:
        result=None
        if k=='profile':result=agent(f'Sinh viên {sid} có bao nhiêu tín chỉ nợ, tín chỉ tích lũy, GPA học kỳ, CPA và điểm rèn luyện?',{},sid,None,roster,root)
        elif k=='meeting':result=route_workflow(question+' Cô chuẩn bị gặp riêng, nên hỏi gì để tìm hiểu khó khăn học tập?',{},sid,None,roster,root)
        elif k=='priorities':result=route_workflow(f'Nêu 3 việc ưu tiên học tập cho sinh viên {sid}',{},sid,None,roster,root)
        elif k=='retake' and caps and 1<=int(caps[0])<=30:result=agent(f'Lập lộ trình học lại sinh viên {sid}, mỗi đợt tối đa {caps[0]} tín chỉ theo tiên quyết.',{},sid,None,roster,root)
        elif k=='study' and mins and 5<=int(mins[0])<=180:result=agent(f'Lập kế hoạch tự học một tuần cho sinh viên {sid}, mỗi ngày chỉ có {mins[0]} phút.',{'kind':'advisor_task','topic':'meeting','mssv':str(sid),'scope':sig,'topics':topics},sid,None,roster,root)
        elif k=='draft':
            if re.search(r'\b\d+ cau\b',n) and not re.search(r'\b3 cau\b',n):
                pending.append(k);sections.append('**'+LABELS[k]+'**\nChưa hỗ trợ số câu được yêu cầu.');continue
            fmt='tin nhắn' if 'tin nhan' in n or 'loi nhan' in n else 'email';tone='trang trọng' if 'trang trong' in n else 'thân thiện';brief=' ngắn gọn' if re.search(r'\b(?:ngan gon|rut gon)\b',n) else ''
            result=agent(f'Soạn {fmt} mời sinh viên {sid} trao đổi về học tập, giọng {tone}{brief}.',{},sid,None,roster,root)
            if result and fmt=='tin nhắn' and re.search(r'\b3 cau\b',n) and successful('draft',*result):
                result[0]['answer']='Chào em, cô muốn hẹn em trao đổi về việc học. Cô mong được lắng nghe và cùng em tìm cách hỗ trợ phù hợp. Em cho cô biết thời gian thuận tiện nhé.'
        if result is None:
            pending.append(k);sections.append('**'+LABELS[k]+'**\n'+('Cần xác nhận trần tín chỉ mỗi đợt.' if k=='retake' else 'Cần xác nhận số phút tự học mỗi ngày.' if k=='study' else 'Chưa có đủ căn cứ để thực hiện bước này.'));continue
        r,c=result;m=r.get('metadata',{});t=m.get('workflow_tools',[])
        if not successful(k,r,c):pending.append(k)
        else:states[k]=c;completed.append(k)
        for name in t:
            if name not in tools:tools.append(name)
        for src in m.get('advisor_sources',[]):
            if src not in sources:sources.append(src)
        sections.append('**'+LABELS[k]+'**\n'+clean(r['answer']))
    # Only signed scoped subtask metadata, no raw answers or grades.
    new={'kind':'advisor_mission','student':str(sid),'scope':sig,'states':states,'pending':pending}
    if extending:
        r=response(('Dạ cô, em đã bổ sung phần dưới đây; giữ nguyên những phần khác.' if completed else 'Dạ cô, phần bổ sung chưa hoàn thành; các phần đã thực hiện vẫn được giữ nguyên.')+'\n\n'+'\n\n'.join(sections),'mission_extension',tools,sources,'STUDENT_STATUS',str(sid))
        r['metadata'].update(mission_plan=plan,mission_completed=completed,mission_pending=pending,mission_planner='explicit_extension',mission_step=plan[0])
        return r,new
    summary,review_tools,review_sources=review(st,roster,root,states,pending)
    for tool in review_tools:
        if tool not in tools:tools.append(tool)
    for src in review_sources:
        if src not in sources:sources.append(src)
    r=response('Dạ cô, '+(summary[:1].lower()+summary[1:])+'\n\n**Chi tiết từng phần**\n\n'+'\n\n'.join(sections),'individual_mission',tools,sources,'STUDENT_STATUS',str(sid))
    r['metadata'].update(mission_plan=plan,mission_completed=completed,mission_pending=pending,mission_planner=mode,model_name=MODEL if mode=='local_model_plan' else None,inference_source=mode)
    return r,new
