"""Short-lived, signed browser context. No transcript or student grades stored server-side.
Only explicit referents and a single prior public-year query may be resolved.
"""
import base64, hashlib, hmac, json, re, secrets, time, os
from quality import norm
from counseling import meeting_intent, open_support
from meeting_context import CURRENT, update_topics, continuation, standalone_format
from pydantic import BaseModel, Field

class AdvisorChatRequest(BaseModel):
    question: str = Field(min_length=1,max_length=4000)
    experience: str | None = None  # advisor UI opt-in; legacy API compatibility
    force_engine: str | None = None
    mssv: str | None = None
    context_token: str | None = Field(default=None,max_length=8000)

YEAR = re.compile(r'\bnăm(?:\s+học)?\s+(20\d{2})(?:\s*[-–—/]\s*(20\d{2}))?\b',re.I)
YEAR_FOLLOW = re.compile(r'^(?:còn|thế|vậy)\s+năm(?:\s+học)?\s+(20\d{2})(?:\s*[-–—/]\s*(20\d{2}))?\s*(?:thì sao|thế nào|như thế nào)?[\s?!.]*$',re.I)
REFERENT = re.compile(r'\b(?:em nay|em do|em ay|sinh vien nay|sinh vien do|sinh vien ay|ban nay|ban do|ban ay)\b')
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
    identified=explicit or classified_id
    if identified and not (previous.get('meeting') and str(identified)==previous.get('mssv') and continuation(q)):
        return q,identified,'explicit'
    if previous.get('kind')=='student' and previous.get('meeting') and continuation(q) and not OTHER_SCOPE.search(n):
        # Follow only a scoped reference, an explicit meeting reference, or a short
        # format request. Never attach unrelated public policy to a student.
        from counseling import EXCLUDE, DRAFT_TASK, REPORT_TASK, STUDENT_TASK as WORKFLOW_STUDENT
        if not (EXCLUDE.search(n) or DRAFT_TASK.search(n) or REPORT_TASK.search(n) or WORKFLOW_STUDENT.search(n)) and (REFERENT.search(n) or standalone_format(q) or re.search(r'\b(?:buoi gap do|buoi gap nay|buoi tu van do|buoi tu van nay)\b',n)):
            return q,previous['mssv'],'student_followup'
    if identified:return q,identified,'explicit'
    if REFERENT.search(n):
        if previous.get('kind')=='student' and (STUDENT_TASK.search(n) or meeting_intent(n) or open_support(n)) and not OTHER_SCOPE.search(n):
            return q,previous['mssv'],'student_followup'
        return q,None,'clarify_student'
    # Only explicitly referenced prior meeting, not arbitrary follow-up text.
    if re.search(r'\b(?:buoi gap do|buoi gap nay|buoi tu van do|buoi tu van nay)\b',n) and meeting_intent(n):
        if previous.get('kind')=='student' and not OTHER_SCOPE.search(n):return q,previous['mssv'],'student_followup'
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

def next_context(question,result,prior=None):
    routing=result.get('routing') or {};meta=result.get('metadata') or {}
    if routing.get('risk_tier')=='RED' or routing.get('actual_engine_used') in ('safety_gate_red','meta_greeting'):return {}
    entities=meta.get('advisor_entities') or {};sid=entities.get('mssv')
    if meta.get('advisor_category')=='STUDENT_STATUS' and meta.get('advisor_intent')!='scope_clarification' and meta.get('workflow_tools')!=['scope_check'] and sid and meta.get('roadmap') and re.fullmatch(r'\d{5,12}',str(sid)):
        data={'kind':'student','mssv':str(sid)}
        if meta.get('advisor_intent')=='meeting_preparation':
            old=prior or {}; same=old.get('kind')=='student' and old.get('mssv')==str(sid) and old.get('meeting')
            data.update(meeting=True,topics=update_topics(question,old.get('topics',[]) if same else [])[0])
        return data
    # No carryover of profile queries, conflict-free public source queries only.
    if meta.get('advisor_category') not in (None,'REGULATION') or meta.get('engine_mode') not in ('SOURCE_TABLE','SOURCE_CLAUSE','LORA_KNOWLEDGE_ACCESS','KNOWLEDGE_EXCERPTS'):return {}
    from regulation import TEXT_SHA
    if meta.get('engine_mode')=='SOURCE_CLAUSE' and meta.get('sha256')==TEXT_SHA and re.search(r'\b(?:nghi hoc tam thoi|tam dung hoc|bao luu ket qua)\b',norm(question)):
        return {'kind':'policy_clause','article':36,'clause':3,'instrument':'3626'}
    if len(question)<=1500 and public_year(question):return {'kind':'public_year','question':question}
    return {}

def add_conversation(s, dispatch, request_type, root=None):
    state=Context()
    from reference_knowledge import ReferenceLibrary
    reference_library=ReferenceLibrary(root) if root is not None else None
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
        prior=state.read(req.context_token)
        product=req.experience=='advisor'
        # One parked mission, only during a verified public-source interlude.
        # It is never injected into another task or a model prompt. A new
        # conversation, another student, RED, or forced research clears it.
        parked=prior.pop('parked_mission',None)
        if not product:parked=None
        classified_id=None
        if not isinstance(parked,dict) or parked.get('kind')!='advisor_mission' or parked.get('exp',0)<state.clock():parked=None
        if product and prior.get('kind')=='advisor_mission':parked=dict(prior)
        def issue_context(data,result):
            if not data:return None
            clean=dict(data);clean.pop('parked_mission',None)
            if product and clean.get('kind')=='student' and callable(getattr(s,'_get_active_roster',None)):
                from quality_workflows import snapshot
                clean['scope']=snapshot(s._get_active_roster())
            meta=result.get('metadata') or {}
            if (product and auto and risk.risk_tier!='RED' and not req.mssv and not classified_id and parked and
                meta.get('advisor_category')=='REGULATION' and meta.get('engine_mode') in ('SOURCE_TABLE','SOURCE_CLAUSE','ADVISOR_EVIDENCE') and
                meta.get('source_path') and meta.get('sha256') and not (meta.get('advisor_entities') or {}).get('mssv') and
                not clean.get('student') and not clean.get('mssv') and clean.get('kind') in ('advisor_agent','advisor_task','semantic_task','public_year','policy_clause') and
                not re.search(r'\b(?:\d{8}|mssv|em nay|em ay|em do|sinh vien nay|sinh vien do|sinh vien khac|ca lop|toan lop)\b',norm(raw))):
                token=state.issue({**clean,'parked_mission':parked})
                if len(token)<=8000:return token
            return state.issue(clean)
        if (auto and product and root is not None and risk.risk_tier!='RED' and not req.mssv and
            re.fullmatch(r'(?:co muon )?(?:quay lai|tiep tuc|tro lai) (?:ke hoach|phuong an|nhiem vu)(?: tu van)?(?: (?:truoc|vua roi|ban dau|da lap|dang lam|truoc do))?',norm(raw))):
            from quality_routes import response
            from advisor_mission import route as mission_route
            if parked and callable(getattr(s,'_get_active_roster',None)):
                resumed=mission_route('Tóm tắt lại kế hoạch.',parked,None,None,s._get_active_roster(),root,enabled=False)
                if resumed is not None:
                    r,data=resumed;r['question']=raw;r['routing']['risk_tier']=risk.risk_tier
                    r['metadata']['advisor_experience']=True
                    r['context_resolution']={'kind':'mission_resumed' if data else 'mission_resume_unavailable','original_question':raw,'effective_question':'Tóm tắt lại kế hoạch.'}
                    r['context_token']=state.issue({k:v for k,v in data.items() if k!='parked_mission'}) if data else None
                    return JSONResponse(content=r)
            r=response('Dạ cô, phiên này chưa có nhiệm vụ tư vấn còn hiệu lực để quay lại. Cô chọn hồ sơ hoặc nêu lại yêu cầu nhé.','advisor_clarification')
            r['question']=raw;r['routing']['risk_tier']=risk.risk_tier;r['context_token']=None
            return JSONResponse(content=r)
        # A separate read-only source decision, never permission to perform an
        # exception. Research and forced modes retain the original gate.
        if auto and product and root is not None and not req.mssv:
            from advisor_decision import route as decision_route
            decision=decision_route(raw,prior,root,red=risk.risk_tier=='RED')
            if decision is not None:
                r,data=decision;r['question']=raw;r['routing']['risk_tier']='YELLOW' if risk.risk_tier=='RED' else risk.risk_tier
                r['metadata'].update(advisor_experience=True,original_risk_tier=risk.risk_tier)
                r['context_resolution']={'kind':'source_decision','original_question':raw,'effective_question':raw}
                r['context_token']=issue_context(data,r)
                return JSONResponse(content=r)
        if not auto or risk.risk_tier=='RED':
            r=call(raw,req.mssv);r['context_token']=None;return JSONResponse(content=r)
        # Check named students before injecting an inherited identifier. This is
        # a local classifier, not a call to the news scraper or any model.
        if hasattr(s,'_router') and hasattr(s._router,'classify_query') and hasattr(s,'_get_active_roster'):
            _,entities=s._router.classify_query(raw,roster=s._get_active_roster(),mssv=req.mssv)
            classified_id=(entities or {}).get('mssv')
        # Signed, scope-checked transitions and public table requests, before model fallback.
        if product and root is not None and callable(getattr(s,'_get_active_roster',None)):
            from advisor_continuity import route as continuity_route
            from admission_multiyear import route as admissions_history_route
            from advisor_public_guard import route as public_guard_route
            from advisor_pdf_reference import route as pdf_reference_route
            from advisor_course_reference import route as course_reference_route
            continued=course_reference_route(root,raw,prior) if not req.mssv and not classified_id and auto and risk.risk_tier!='RED' else None
            if continued is None and not req.mssv and not classified_id and auto and risk.risk_tier!='RED':
                from advisor_release_counsel import route as release_counsel_route
                continued=release_counsel_route(root,raw,prior)
            if continued is None:
                continued=pdf_reference_route(root,raw,prior) if not req.mssv and not classified_id and auto and risk.risk_tier!='RED' else None
            if continued is None:
                continued=public_guard_route(root,raw,prior) if not req.mssv and not classified_id and auto and risk.risk_tier!='RED' else None
            if continued is None:
                continued=admissions_history_route(raw,root) if not req.mssv and not classified_id and auto and risk.risk_tier!='RED' else None
            if continued is None:
                continued=continuity_route(raw,prior,req.mssv,classified_id,s._get_active_roster(),root)
            if continued is None and not req.mssv and not classified_id and auto and risk.risk_tier!='RED':
                from advisor_source_precision import route as public_precision_route
                continued=public_precision_route(root,raw,prior)
                if continued is None:
                    from advisor_public_fast import route as public_fast_route
                    continued=public_fast_route(root,raw,prior)
                if continued is None:
                    from advisor_public_sections import route as public_sections_route
                    continued=public_sections_route(root,raw,prior)
            if continued is not None:
                r,data=continued;r['question']=raw;r['routing']['risk_tier']=risk.risk_tier
                r['metadata']['advisor_experience']=True
                r['context_resolution']={'kind':'scoped_continuity','original_question':raw,'effective_question':raw}
                r['context_token']=issue_context(data,r)
                return JSONResponse(content=r)
        # Repair high-confidence advising intent before generic evidence retrieval.
        if product and root is not None and callable(getattr(s,'_get_active_roster',None)):
            from experience_transfer import route as transfer_route
            repaired=transfer_route(raw,prior,req.mssv,classified_id,s._get_active_roster(),root)
            if repaired is not None:
                r,data=repaired;r['question']=raw;r['routing']['risk_tier']=risk.risk_tier
                r['metadata']['advisor_experience']=True
                r['context_resolution']={'kind':'experience_transfer','original_question':raw,'effective_question':raw}
                r['context_token']=issue_context(data,r)
                return JSONResponse(content=r)
            # Exact graduation-rule questions already have a source-bound tool.
            # Prefer it to the generic semantic planner, without weakening its guards.
            from quality_routes import route as rank_route,RANK
            n=norm(raw)
            if not req.mssv and not classified_id and (RANK.search(n) and re.search(r'\b(?:bang (?:dung )?5|dung bang 5)\b',n) or (prior.get('kind')=='advisor_task' and prior.get('topic')=='rank')):
                ranked=rank_route(raw,prior,None,None,s._get_active_roster(),root)
                if ranked is not None and ranked[1].get('topic')=='rank':
                    r,data=ranked;r['question']=raw;r['routing']['risk_tier']=risk.risk_tier
                    r['metadata']['advisor_experience']=True
                    r['context_resolution']={'kind':'rank_reference','original_question':raw,'effective_question':raw}
                    r['context_token']=issue_context(data,r)
                    return JSONResponse(content=r)
        # Product-only scoped public notice and hypothetical CPA continuation.
        # No inherited identity, RED override, or research-path changes.
        if product and root is not None and not req.mssv and not classified_id:
            from experience_routes import route as experience_route
            # YELLOW is a comparison/temporal signal, not an exception. Only a
            # signed, typed hypothetical CPA context may use this narrow delta path.
            # RED and forced modes have already returned; explicit/classified IDs excluded.
            from experience_routes import cpa_route
            if risk.risk_tier=='YELLOW' and prior.get('kind')=='advisor_experience_cpa':
                experienced=cpa_route(raw,prior,delta_only=True)
                if experienced is None:experienced=experience_route(raw,prior,root,allow_calculation=False)
            else:
                experienced=experience_route(raw,prior,root,allow_calculation=risk.risk_tier=='GREEN')
            if experienced is not None:
                r,data=experienced;r['question']=raw;r['routing']['risk_tier']=risk.risk_tier
                r['metadata']['advisor_experience']=True
                r['context_resolution']={'kind':'scoped_experience','original_question':raw,'effective_question':raw}
                r['context_token']=issue_context(data,r)
                return JSONResponse(content=r)
        if root is not None and callable(getattr(s,'_get_active_roster',None)):
            if product:
                if os.environ.get('CHRONOREG_GROUNDED_PILOT')=='1':
                    from grounded_product import route as grounded_route
                    grounded=grounded_route(raw,prior,req.mssv,classified_id,s._get_active_roster(),root)
                    if grounded is not None:
                        r,data=grounded;r['question']=raw;r['routing']['risk_tier']=risk.risk_tier
                        r['metadata'].update(advisor_experience=True,grounded_pilot=True)
                        r['context_resolution']={'kind':'grounded_orchestration','original_question':raw,'effective_question':raw}
                        r['context_token']=issue_context(data,r)
                        return JSONResponse(content=r)
                from advisor_evidence import direct_article
                exact = direct_article(raw, prior, root) if not req.mssv and not classified_id else None
                if exact is not None:
                    r,data=exact;r['question']=raw;r['routing']['risk_tier']=risk.risk_tier
                    r['metadata']['advisor_experience']=True
                    r['context_resolution']={'kind':'evidence_article','original_question':raw,'effective_question':raw}
                    r['context_token']=issue_context(data,r)
                    return JSONResponse(content=r)
                from advisor_bridge import route as bridge_route, transition_study
                bridged=transition_study(raw,prior,req.mssv,classified_id,s._get_active_roster(),root)
                if bridged is None:bridged=bridge_route(raw,prior,req.mssv,classified_id,s._get_active_roster(),root)
                if bridged is not None:
                    r,data=bridged;r['question']=raw;r['routing']['risk_tier']=risk.risk_tier
                    r['metadata']['advisor_experience']=True
                    r['context_resolution']={'kind':'bounded_orchestration','original_question':raw,'effective_question':raw}
                    r['context_token']=issue_context(data,r)
                    return JSONResponse(content=r)
                from reviewed_sources import route as reviewed_route
                reviewed=reviewed_route(raw,prior,root) if not req.mssv and not classified_id else None
                if reviewed is not None:
                    r,data=reviewed;r['question']=raw;r['routing']['risk_tier']=risk.risk_tier
                    r['metadata']['advisor_experience']=True
                    r['context_resolution']={'kind':'reviewed_public_reference','original_question':raw,'effective_question':raw}
                    r['context_token']=issue_context(data,r)
                    return JSONResponse(content=r)
                from advisor_composer import clarify
                missing=clarify(raw,prior) if not req.mssv and not classified_id else None
                if missing and reference_library is not None and re.search(r'\b20\d{2}\b|\bqh[- ]?20\d{2}\b|\bk(?:6[7-9]|7[01])\b',norm(raw)):
                    ref=reference_library.route(raw,prior)
                    if ref is not None:
                        r,data=ref;r['question']=raw;r['routing']['risk_tier']=risk.risk_tier
                        r['metadata']['advisor_experience']=True
                        r['context_resolution']={'kind':'corpus_reference','original_question':raw,'effective_question':raw}
                        r['context_token']=issue_context(data,r)
                        return JSONResponse(content=r)
                if missing:
                    from quality_routes import response
                    r=response(missing,'advisor_clarification');r['question']=raw;r['routing']['risk_tier']=risk.risk_tier
                    r['metadata']['advisor_experience']=True;r['context_token']=None
                    return JSONResponse(content=r)
                from advisor_mission import route as mission_route
                mission=mission_route(raw,prior,req.mssv,classified_id,s._get_active_roster(),root,enabled=getattr(s,'_semantic_pilot',False))
                if mission is not None:
                    r,data=mission;r['question']=raw;r['routing']['risk_tier']=risk.risk_tier
                    r['metadata']['advisor_experience']=True
                    r['context_resolution']={'kind':'mission_followup' if prior.get('kind')=='advisor_mission' else 'mission_task','original_question':raw,'effective_question':raw}
                    r['context_token']=issue_context(data,r)
                    return JSONResponse(content=r)
                from advisor_agent import route as agent_route
                result=agent_route(raw,prior,req.mssv,classified_id,s._get_active_roster(),root)
                if result is not None:
                    r,data=result;r['question']=raw;r['routing']['risk_tier']=risk.risk_tier
                    r['metadata']['advisor_experience']=True
                    r['context_resolution']={'kind':'agent_followup' if prior.get('kind')=='advisor_agent' else 'agent_task','original_question':raw,'effective_question':raw}
                    r['context_token']=issue_context(data,r)
                    return JSONResponse(content=r)
            if getattr(s,'_semantic_pilot',False):
                from semantic_product import route as semantic_route
                from policy_followup import return_to_study
                result=return_to_study(raw,prior,root) if not req.mssv and not classified_id else None
                if result is None:result=semantic_route(raw,prior,req.mssv,classified_id,s._get_active_roster(),root)
                if result is not None:
                    r,data=result;r['question']=raw;r['routing']['risk_tier']=risk.risk_tier
                    if product and data.get('kind')=='semantic_task' and data.get('plan',{}).get('intent')=='retake_plan' and r.get('metadata',{}).get('engine_mode')=='ADVISOR_WORKFLOW':
                        from advisor_bridge import promote_retake
                        data=promote_retake(data,s._get_active_roster(),root) or data
                    if product and r.get('metadata',{}).get('advisor_intent')=='semantic_calendar':
                        from advisor_tasks import calendar_presentation
                        calendar_presentation(r)
                    r['context_resolution']={'kind':'semantic_followup' if prior.get('kind')=='semantic_task' else 'semantic_task','original_question':raw,'effective_question':raw}
                    r['context_token']=issue_context(data,r)
                    return JSONResponse(content=r)
            from quality_routes import route as quality_route
            repaired=quality_route(raw,prior,req.mssv,classified_id,s._get_active_roster(),root)
            if repaired is not None:
                r,data=repaired
                r['question']=raw
                r['routing']['risk_tier']=risk.risk_tier
                r['context_resolution']={'kind':'typed_followup' if prior.get('kind')=='advisor_task' else 'typed_task','original_question':raw,'effective_question':raw}
                r['context_token']=issue_context(data,r)
                return JSONResponse(content=r)
        if product and not req.mssv and not classified_id and not prior.get('kind') in ('student','advisor_task','semantic_task'):
            from advisor_evidence import retrieve, PERSONAL, SPECIAL
            evidence=retrieve(raw,getattr(s,'_advisor_evidence_index',None),enabled=getattr(s,'_semantic_pilot',False))
            if evidence is not None:
                r,data=evidence;r['question']=raw;r['routing']['risk_tier']=risk.risk_tier
                r['metadata']['advisor_experience']=True
                r['context_resolution']={'kind':'public_evidence','original_question':raw,'effective_question':raw}
                r['context_token']=issue_context(data,r)
                return JSONResponse(content=r)
            # Do not send a failed explicit-edition public lookup to a second
            # unverified generator. Research mode still has its original path.
            n=norm(raw)
            if '3626' in n and not PERSONAL.search(n) and not SPECIAL.search(n):
                from quality_routes import response
                r=response('Dạ cô, em chưa xác minh được đoạn quy chế đủ để trả lời yêu cầu này trong QĐ 3626. Nếu cô biết điều hoặc khoản liên quan, em có thể đối chiếu trực tiếp; em không tự thay bằng văn bản khác.','advisor_clarification')
                r['question']=raw;r['routing']['risk_tier']=risk.risk_tier
                r['metadata']['advisor_experience']=True;r['context_token']=None
                return JSONResponse(content=r)
        # Product-only access to raw UET reference material. Does not change publication status.
        if auto and product and risk.risk_tier!='RED' and reference_library is not None and not req.mssv and not classified_id:
            reference=reference_library.route(raw,prior)
            if reference is not None:
                r,data=reference;r['question']=raw;r['routing']['risk_tier']=risk.risk_tier
                r['metadata']['advisor_experience']=True
                r['context_resolution']={'kind':'corpus_reference','original_question':raw,'effective_question':raw}
                r['context_token']=issue_context(data,r)
                return JSONResponse(content=r)
        q,sid,kind=resolve(raw,req.mssv,prior,classified_id)
        if kind.startswith('clarify_'):
            msg='Dạ cô, cô đang nhắc đến sinh viên nào? Cô chọn hồ sơ hoặc nhập MSSV giúp em.' if kind=='clarify_student' else 'Dạ cô, cô muốn tra nội dung nào trong năm này? Cô nêu chủ đề và năm học giúp em.'
            return JSONResponse(content={'question':raw,'answer':msg,'routing':{'selected_engine':'meta_greeting','actual_engine_used':'meta_greeting','risk_tier':'GREEN','detected_signals':[],'routing_reason':'Thiếu ngữ cảnh rõ ràng'},'metadata':{'engine_mode':'CONTEXT_CLARIFICATION','source_label':'Làm rõ ngữ cảnh','inference_source':'deterministic_router','latency_ms':0},'context_token':None})
        same=bool(sid and prior.get('kind')=='student' and prior.get('mssv')==str(sid) and prior.get('meeting') and kind=='student_followup')
        inherited=prior if same else {}
        ctx=CURRENT.set({'mssv':str(sid),'meeting':True,'topics':inherited.get('topics',[]) } if same else None)
        try:r=call(q,sid)
        finally:CURRENT.reset(ctx)
        # Preserve expanded question for the research comparison button; expose
        # original question and effective query separately for audit.
        r['context_resolution']={'kind':kind,'original_question':raw,'effective_question':q,'student_context_used':kind=='student_followup'}
        if product:
            from advisor_agent import product_result
            r,accepted=product_result(r)
            r.setdefault('metadata',{})['advisor_experience']=True
            if not accepted:
                r['context_token']=None
                return JSONResponse(content=r)
        data=next_context(q,r,inherited);r['context_token']=issue_context(data,r)
        return JSONResponse(content=r)
