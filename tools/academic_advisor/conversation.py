"""Short-lived, signed browser context. No transcript or student grades stored server-side.
Only explicit referents and a single prior public-year query may be resolved.
"""
import base64, hashlib, hmac, json, re, secrets, time
from quality import norm
from pydantic import BaseModel, Field

class AdvisorChatRequest(BaseModel):
    question: str = Field(min_length=1,max_length=4000)
    force_engine: str | None = None
    mssv: str | None = None
    context_token: str | None = Field(default=None,max_length=8000)

YEAR = re.compile(r'\bnăm(?:\s+học)?\s+(20\d{2})(?:\s*[-–—/]\s*(20\d{2}))?\b',re.I)
YEAR_FOLLOW = re.compile(r'^(?:còn|thế|vậy)\s+năm(?:\s+học)?\s+(20\d{2})(?:\s*[-–—/]\s*(20\d{2}))?\s*(?:thì sao|thế nào|như thế nào)?[\s?!.]*$',re.I)
REFERENT = re.compile(r'\b(?:em nay|em do|sinh vien nay|sinh vien do|ban nay|ban do)\b')
OTHER_SCOPE = re.compile(r'\b(?:k6[5-9]|k7[01]|qh[- ]?20\d{2}|ca lop|toan lop|lop minh|lop toi|mssv|ma sinh vien|sinh vien khac|em khac|so sanh|nhung em|cac em|hai em|[0-9]{8})\b')
STUDENT_TASK = re.compile(r'\b(?:tu van|roadmap|lo trinh|ke hoach|gpa|cpa|diem|tin chi|hoc vuot|hoc bong|canh bao|bao luu|tot nghiep|chuyen nganh|rut hoc phan|mon no|hoc lai)\b')

def public_year(q):
    matches=list(YEAR.finditer(q))
    if len(matches)!=1:return None
    m=matches[0]; years=re.findall(r'\b20\d{2}\b',q)
    # Reject cohort, other years, personal and mixed comparison topics.
    if len(years)!=(2 if m.group(2) else 1) or (m.group(2) and int(m.group(2))!=int(m.group(1))+1):return None
    if re.search(r'\b(?:so sanh|so voi|thay doi|truoc day|qh|k6[5-9]|k7[01]|mssv|lop minh|sinh vien nay)\b',norm(q)):return None
    return m

class Context:
    def __init__(self, key=None, ttl=1800, clock=time.time):self.key=key or secrets.token_bytes(32);self.ttl=ttl;self.clock=clock
    def issue(self, data):
        raw=json.dumps({'exp':int(self.clock())+self.ttl,**data},ensure_ascii=False,separators=(',',':')).encode()
        payload=base64.urlsafe_b64encode(raw).decode().rstrip('=')
        sig=hmac.new(self.key,payload.encode(),hashlib.sha256).hexdigest()
        return payload+'.'+sig
    def read(self, token):
        if not token or len(token)>8000:return {}
        try:
            payload,sig=token.split('.',1)
            if not hmac.compare_digest(hmac.new(self.key,payload.encode(),hashlib.sha256).hexdigest(),sig):return {}
            data=json.loads(base64.urlsafe_b64decode(payload+'='*(-len(payload)%4)))
            if data['exp']<self.clock():return {}
            return data
        except (ValueError,TypeError,KeyError,UnicodeError):return {}

def resolve(question, explicit, previous, classified_id=None):
    """Returns effective query, student id, resolution kind. Never infer from broad 'it'."""
    q=question.strip(); n=norm(q)
    if explicit or classified_id:return q,explicit or classified_id,'explicit'
    if REFERENT.search(n):
        if previous.get('kind')=='student' and STUDENT_TASK.search(n) and not OTHER_SCOPE.search(n):
            return q,previous['mssv'],'student_followup'
        return q,None,'clarify_student'
    f=YEAR_FOLLOW.fullmatch(q)
    if f:
        old=previous.get('question','') if previous.get('kind')=='public_year' else ''
        m=public_year(old)
        if m and (not f.group(2) or int(f.group(2))==int(f.group(1))+1) and (bool(f.group(2))==bool(m.group(2))):
            new=f'năm học {f.group(1)}-{f.group(2)}' if f.group(2) else f'năm {f.group(1)}'
            return old[:m.start()]+new+old[m.end():],None,'year_followup'
        return q,None,'clarify_year'
    return q,None,'new'

def next_context(question,result):
    routing=result.get('routing') or {};meta=result.get('metadata') or {}
    if routing.get('risk_tier')=='RED' or routing.get('actual_engine_used') in ('safety_gate_red','meta_greeting'):return {}
    entities=meta.get('advisor_entities') or {};sid=entities.get('mssv')
    if meta.get('advisor_category')=='STUDENT_STATUS' and sid and meta.get('roadmap') and re.fullmatch(r'\d{5,12}',str(sid)):
        return {'kind':'student','mssv':str(sid)}
    # No carryover of profile queries, conflict-free public source queries only.
    if meta.get('advisor_category') not in (None,'REGULATION') or meta.get('engine_mode') not in ('SOURCE_TABLE','SOURCE_CLAUSE','LORA_KNOWLEDGE_ACCESS','KNOWLEDGE_EXCERPTS'):return {}
    if len(question)<=1500 and public_year(question):return {'kind':'public_year','question':question}
    return {}

def add_conversation(s, dispatch, request_type):
    state=Context()
    from fastapi.responses import JSONResponse
    def unpack(response):
        return json.loads(response.body) if hasattr(response,'body') else dict(response)
    @s.app.post('/api/advisor/chat')
    def conversation(req:AdvisorChatRequest):
        auto=req.force_engine in (None,'auto')
        raw=req.question.strip()
        def call(q,sid):return unpack(dispatch(request_type(question=q,force_engine=req.force_engine,mssv=sid)))
        # Never reinterpret explicit experiment modes or RED queries.
        risk=s._router.route_decision(raw)
        if not auto or risk.risk_tier=='RED':
            r=call(raw,req.mssv);r['context_token']=None;return JSONResponse(content=r)
        prior=state.read(req.context_token)
        classified_id=None
        # Check named students before injecting an inherited identifier. This is
        # a local classifier, not a call to the news scraper or any model.
        if hasattr(s,'_router') and hasattr(s._router,'classify_query') and hasattr(s,'_get_active_roster'):
            _,entities=s._router.classify_query(raw,roster=s._get_active_roster(),mssv=req.mssv)
            classified_id=(entities or {}).get('mssv')
        q,sid,kind=resolve(raw,req.mssv,prior,classified_id)
        if kind.startswith('clarify_'):
            msg='Thầy/cô đang nhắc đến sinh viên nào? Hãy chọn hồ sơ hoặc nhập MSSV.' if kind=='clarify_student' else 'Thầy/cô muốn tra nội dung nào trong năm này? Hãy nêu lại chủ đề và năm học cần tra cứu.'
            return JSONResponse(content={'question':raw,'answer':msg,'routing':{'selected_engine':'meta_greeting','actual_engine_used':'meta_greeting','risk_tier':'GREEN','detected_signals':[],'routing_reason':'Thiếu ngữ cảnh rõ ràng'},'metadata':{'engine_mode':'CONTEXT_CLARIFICATION','source_label':'Làm rõ ngữ cảnh','inference_source':'deterministic_router','latency_ms':0},'context_token':None})
        r=call(q,sid)
        # Preserve expanded question for the research comparison button; expose
        # original question and effective query separately for audit.
        r['context_resolution']={'kind':kind,'original_question':raw,'effective_question':q,'student_context_used':kind=='student_followup'}
        data=next_context(q,r);r['context_token']=state.issue(data) if data else None
        return JSONResponse(content=r)
