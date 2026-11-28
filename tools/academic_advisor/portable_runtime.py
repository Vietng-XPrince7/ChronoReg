"""Portable product deployment. Local CPU SLM by default; explicit offline/Gemini options.
Public-document Gemini is explicitly opt-in; student analysis stays on-device.
Pure LoRA is NOT available in this profile. No benchmark cache as inference.
"""
import argparse, json, os, re, sys
from pathlib import Path
from types import SimpleNamespace
import run_live
import conversation
from quality import norm

OFFLINE={'ollama_reachable':False,'base_model_ready':False,'lora_model_ready':False,'ready':False,'all_models_ready':False,'models':[],'remote_configured':False,'inference_source':'knowledge_excerpts','engine_label':'Advisor — local evidence & tools','error':None}

def disabled_client(*a,**k):
    raise RuntimeError('Local model disabled in portable profile')

def public_query(q):
    # Cloud requests are limited to public-policy query path, plus conservative
    # rejection of obvious profile identifiers. User opt-in still required.
    n=norm(q)
    return not (re.search(r'\b\d{8,}\b|@',q) or re.search(r'\b(?:mssv|ma sinh vien|ho so|bang diem|sinh vien nay|em nay|lop minh|lop toi|gpa|cpa|diem cua|email|so dien thoai)\b',n))

class GeminiClient:
    def __init__(self,key,model,transport=None):self.key=key;self.model=model;self.transport=transport
    def post(self,url,json,timeout):
        import httpx
        if not re.fullmatch(r'[A-Za-z0-9._-]+',self.model):raise ValueError('Invalid Gemini model')
        messages=json['messages'];system='\n'.join(m['content'] for m in messages if m['role']=='system')
        body={'systemInstruction':{'parts':[{'text':system}]},'contents':[{'role':'user','parts':[{'text':m['content']} for m in messages if m['role']!='system']}],'generationConfig':{'temperature':0.1,'maxOutputTokens':2048}}
        endpoint='https://generativelanguage.googleapis.com/v1beta/models/'+self.model+':generateContent'
        with httpx.Client(timeout=60,transport=self.transport,trust_env=False) as c:
            r=c.post(endpoint,headers={'x-goog-api-key':self.key},json=body);r.raise_for_status();d=r.json()
        candidate=d.get('candidates',[{}])[0];content=''.join(p.get('text','') for p in candidate.get('content',{}).get('parts',[]) if not p.get('thought'))
        result={'message':{'content':content},'done_reason':'stop' if candidate.get('finishReason')=='STOP' else 'incomplete'}
        return SimpleNamespace(raise_for_status=lambda:None,json=lambda:result)

def make_answer(original,key,model):
    def answer(index,backend,q):
        if not key or not public_query(q):return original(index,backend,q)
        client=GeminiClient(key,model)
        shim=SimpleNamespace(lora_model=model,ollama_url='https://generativelanguage.googleapis.com',ollama_timeout=60,_make_client=lambda *a,**k:(client,False))
        result=original(index,shim,q)
        if result.get('engine_mode')=='LORA_KNOWLEDGE_ACCESS':
            result.update(engine_mode='GEMINI_KNOWLEDGE_ACCESS',inference_source='gemini_public_knowledge',model_name=model)
        return result
    return answer

def unavailable(*a,**k):
    return {'predicted_answer':'Chế độ LoRA thuần cần trọng số đã huấn luyện. Bản portable không chứa trọng số LoRA đã huấn luyện; hãy chọn Auto để dùng trợ lý hoặc chạy bản 7B thực nghiệm trên máy đã có model.','engine_mode':'LORA_UNAVAILABLE','inference_source':'unavailable','model_name':None,'source_label':'LoRA thuần không khả dụng — portable','cited_doc_ids':[],'latency_ms':0,'is_advisor_composite':True,'quality_qualified':False}

def product_copy(data):
    m=data.get('metadata') or {}
    if m.get('engine_mode') not in ('ADVISOR_WORKFLOW','ADVISOR_PLAN'):
        return data
    # The currently bundled roster is generated sample data, not an official record.
    # Keep that provenance in metadata and the UI, not in every sentence.
    if m.get('advisor_category') in ('STUDENT_STATUS','CLASS_STATS','COURSE_TREND') or 'scope_check' in (m.get('workflow_tools') or []):
        m['roster_provenance']='sample_roster'
        m['roster_provenance_label']='Hồ sơ mẫu, chưa phải bảng điểm chính thức'
    answer=data.get('answer')
    if isinstance(answer,str):
        for old,new in (
            ('Hồ sơ demo','Hồ sơ đang mở'),('hồ sơ demo đang mở','hồ sơ đang mở'),
            ('hồ sơ demo','hồ sơ'),('dữ liệu demo','dữ liệu hiện có'),
            ('danh mục demo','danh mục học phần hiện có'),('ngành demo','ngành trong hồ sơ'),
            ('Đây là kế hoạch tự học thử, không phải lịch mở lớp hay cam kết kết quả.', 'Việc đăng ký học phần cần căn cứ lịch mở lớp và điều kiện thực tế.'),
        ):
            answer=answer.replace(old,new)
        data['answer']=answer
    if m.get('source_label')=='Hồ sơ demo + quy tắc tư vấn (không phải LoRA thuần)':
        m['source_label']='Hồ sơ đang mở và công cụ học vụ'
    return data

def fix_response(data,profile):
    if not isinstance(data,dict):return data
    for v in data.values():
        if isinstance(v,dict):fix_response(v,profile)
    r=data.get('routing') or {};m=data.get('metadata')
    if isinstance(m,dict):
        if m.get('engine_mode')=='GEMINI_KNOWLEDGE_ACCESS':
            m.update(source_label='Gemini + kho tri thức UET (không phải LoRA)',inference_source='gemini_public_knowledge')
        m['deployment_profile']=profile
        if profile=='local-slm':
            from local_slm import MODEL
            if m.get('engine_mode')=='LORA_KNOWLEDGE_ACCESS':
                m.update(engine_mode='SLM_KNOWLEDGE_ACCESS',model_name=MODEL,inference_source='local_slm_knowledge',source_label='SLM + kho tri thức UET (không phải LoRA thuần)')
            if m.get('presentation_mode') in ('SLM_ADVISOR','SLM_ADVISOR_PRIORITY'):
                priority=m['presentation_mode']=='SLM_ADVISOR_PRIORITY'
                m.update(model_name=MODEL,inference_source='local_slm_priority' if priority else 'local_slm_advisor',source_label=(m.get('source_label') or '')+(' | SLM chọn ưu tiên' if priority else ' | SLM tư vấn'))
            if isinstance(data.get('answer'),str):
                from slm_advisor import voice
                data['answer']=voice(data['answer'])
        if r.get('actual_engine_used')=='meta_greeting' and m.get('source_type')=='meta_greeting':
            data['answer']='Xin chào cô! ChronoReg Academic Advisor có thể tra cứu quy chế, phân tích hồ sơ demo, tạo lộ trình và mô phỏng GPA tích lũy. Bản portable không chạy LoRA thuần. '+('Gemini hỗ trợ diễn đạt câu hỏi tài liệu công khai; không nhập thông tin cá nhân vào câu hỏi gửi cloud.' if profile=='gemini-public' else 'Chế độ không model dùng dữ liệu và công cụ cục bộ, không sinh lời tư vấn tự do.')
        if profile=='local-slm' and r.get('risk_tier')!='RED' and 'Knowledge Access' in str(r.get('routing_reason','')): r['routing_reason']='Trợ lý SLM + nguồn và công cụ học vụ.'
        elif 'Knowledge Access' in str(r.get('routing_reason','')) or 'Chế độ sản phẩm' in str(r.get('routing_reason','')):
            r['routing_reason']='Chế độ portable: ưu tiên nguồn và công cụ tư vấn; '+('Gemini chỉ dành cho tài liệu công khai.' if profile=='gemini-public' else 'không có LLM cục bộ.')
    if profile=='local-slm' and r.get('actual_engine_used')=='meta_greeting' and isinstance(m,dict) and m.get('source_type')=='meta_greeting':data['answer']='Em chào cô! Em có thể hỗ trợ cô tra cứu quy chế, phân tích hồ sơ và lập lộ trình học tập. Cô muốn xem vấn đề nào trước?'
    return data

def install(s,root,key='',model='gemini-2.5-flash',slm_url=None):
    from fastapi.responses import JSONResponse,HTMLResponse
    profile='local-slm' if slm_url else 'gemini-public' if key else 'offline-tools'
    run_live.answer=make_answer(run_live.answer,key,model)
    # Keep year followup behavior for Gemini answers, without relabeling output.
    original_next=conversation.next_context
    def next_context(q,r,prior=None):
        if (r.get('metadata') or {}).get('engine_mode')=='GEMINI_KNOWLEDGE_ACCESS':
            r={**r,'metadata':{**r['metadata'],'engine_mode':'LORA_KNOWLEDGE_ACCESS'}}
        return original_next(q,r,prior)
    conversation.next_context=next_context
    if slm_url:
        from local_slm import shim,MODEL
        import slm_advisor
        local=shim(slm_url);old_answer=run_live.answer;old_present=run_live.present
        s._advisor_task_backend=local
        def local_answer(index,backend,q):
            r=slm_advisor.knowledge_with_source(old_answer,index,local,q)
            # Internal v12 mode retained for context/source metadata, relabeled at API boundary.
            return r
        run_live.answer=local_answer
        run_live.present=lambda backend,q,pred,bundle=None:slm_advisor.present(old_present,local,q,pred,bundle)
    s._semantic_pilot=bool(slm_url and not key and os.environ.get('CHRONOREG_SEMANTIC_PILOT')=='1')
    idx=run_live.install(s,root);b=s.llm_backend
    b._make_client=disabled_client;b.check_ollama_health=lambda **kw:{**OFFLINE,'base_model':None,'lora_model':None,'ollama_url':None,'deployment_profile':profile}
    s._run_web_lora=unavailable
    original_meta=s._build_metadata
    def metadata(*a,**kw):
        m=original_meta(*a,**kw)
        pred=kw.get('pred') or (a[4] if len(a)>4 else None) or {}
        if pred.get('knowledge_diagnostics') is not None:m['knowledge_diagnostics']=pred['knowledge_diagnostics']
        if profile=='local-slm' and pred.get('presentation_mode') in ('SLM_ADVISOR','SLM_ADVISOR_PRIORITY'):m.update(model_name=model,inference_source='local_slm_priority' if pred['presentation_mode']=='SLM_ADVISOR_PRIORITY' else 'local_slm_advisor')
        if m.get('engine_mode')=='GEMINI_KNOWLEDGE_ACCESS':m.update(source_label='Gemini + kho tri thức UET (không phải LoRA)',inference_source='gemini_public_knowledge')
        return m
    s._build_metadata=metadata
    for route in s.app.routes:
        path=getattr(route,'path','');methods=getattr(route,'methods',set());dep=getattr(route,'dependant',None)
        if dep is None:continue
        if path in ('/api/chat','/api/advisor/chat','/api/compare') and 'POST' in methods:
            old=dep.call
            def wrapped(req,_old=old):
                if getattr(req,'force_engine',None)=='continual_lora' and s._router.route_decision(req.question).risk_tier!='RED':
                    return JSONResponse(content={'question':req.question,'answer':unavailable()['predicted_answer'],'routing':{'selected_engine':'continual_lora','actual_engine_used':'continual_lora','risk_tier':'GREEN','detected_signals':[],'routing_reason':'Không có trọng số LoRA trong bản portable'},'metadata':{'engine_mode':'LORA_UNAVAILABLE','source_label':unavailable()['source_label'],'inference_source':'unavailable','model_name':None,'latency_ms':0,'deployment_profile':profile},'context_token':None})
                result=_old(req);data=json.loads(result.body) if hasattr(result,'body') else result
                data=fix_response(data,profile)
                meta=data.get('metadata') or {}
                if getattr(req,'experience',None)=='advisor' and getattr(req,'force_engine',None) in (None,'auto'):
                    product_copy(data)
                if getattr(req,'experience',None)=='advisor' and getattr(req,'force_engine',None) in (None,'auto'):
                    reviewed=[x for x in (meta.get('advisor_sources') or []) if isinstance(x,dict) and x.get('status')=='reviewed_scoped' and x.get('review_id','').startswith('cntt_')]
                    if len(reviewed)==1:
                        meta['curriculum_review_scope']=reviewed[0]['review_scope']
                        meta['curriculum_source_url']=reviewed[0]['source_url']
                return JSONResponse(content=data)
            dep.call=wrapped
        elif path=='/api/knowledge/status':
            from calendar_source import pack_status
            from reviewed_sources import status as reviewed_status
            dep.call=lambda:{**idx.stats(),'product_version':'15.0' if slm_url else '12.0','deployment_profile':profile,'model':model if key or slm_url else None,'mode':'portable_advisor','pure_lora_available':False,'intelligence_revision':'2.0.0-pilot','grounded_pilot':os.environ.get('CHRONOREG_GROUNDED_PILOT')=='1','chat_streaming':True,'semantic_pilot':s._semantic_pilot,'calendar_pack':pack_status(root),'scoped_source_review':reviewed_status(root)}
        elif path=='/api/answer-v2' and 'POST' in methods:
            dep.call=lambda req:JSONResponse(status_code=503,content={'detail':'Experimental dispatch not enabled in portable profile; use /api/advisor/chat.'})
        elif path=='/' and 'GET' in methods:
            old=dep.call
            def page(_old=old):
                html=_old().body.decode('utf-8')
                html=html.replace('LoRA 7B + Knowledge Access','Knowledge Access').replace('LoRA 7B Advisor','Academic Advisor').replace('LoRA 7B + bằng chứng','Advisor + bằng chứng').replace('Ollama LoRA 7B + nguồn','Local model + nguồn').replace('Chrono-RAG 7B','Chrono-RAG').replace('Ollama 7B','Ollama').replace('LoRA 7B thuần','LoRA thuần (cần model)').replace('Continual LoRA 7B','Continual LoRA (cần model)').replace('LoRA 7B','LoRA (cần model)')
                html=html.replace("if (src === 'ollama_local_advisor')", "if (src === 'gemini_public_knowledge') return 'Gemini + tài liệu công khai';\n      if (src === 'unavailable') return 'Không khả dụng';\n      if (src === 'ollama_local_advisor')")
                html=html.replace("m.engine_mode === 'LORA_KNOWLEDGE_ACCESS' ? 'Knowledge Access'", "m.engine_mode === 'GEMINI_KNOWLEDGE_ACCESS' ? 'Gemini + Knowledge Access' : m.engine_mode === 'LORA_KNOWLEDGE_ACCESS' ? 'Knowledge Access'")
                note='Portable — không cần Ollama/model. '+('Gemini đã bật cho tài liệu công khai; không nhập dữ liệu cá nhân vào câu hỏi cloud.' if key else 'Không LLM: tra cứu, tư vấn theo quy tắc, roadmap, mô phỏng và hội thoại giới hạn.')+' LoRA thuần không khả dụng.'
                if slm_url:
                    note='ChronoReg Academic Advisor — Hỗ trợ học tập và tra cứu quy chế. Xử lý cục bộ. Nguồn hồ sơ: dữ liệu mẫu.'
                    html=html.replace("m.engine_mode === 'GEMINI_KNOWLEDGE_ACCESS' ?", "m.presentation_mode === 'SLM_ADVISOR_PRIORITY' ? 'SLM chọn ưu tiên' : m.presentation_mode === 'SLM_ADVISOR' ? 'Academic Advisor (SLM)' : m.engine_mode === 'SLM_KNOWLEDGE_ACCESS' ? 'SLM + Knowledge Access' : m.engine_mode === 'GEMINI_KNOWLEDGE_ACCESS' ?")
                    html=html.replace("if (src === 'gemini_public_knowledge')", "if (src === 'local_slm_advisor' || src === 'local_slm_knowledge' || src === 'local_slm_priority') return 'SLM cục bộ';\n      if (src === 'gemini_public_knowledge')")
                    html=html.replace('Thầy/cô','Cô').replace('thầy/cô','cô')
                html=html.replace('6 tình huống cố vấn mẫu','Gợi ý tư vấn').replace('Đang tải kịch bản mẫu...','Đang tải gợi ý...').replace('Kịch bản mẫu','Gợi ý').replace('chọn một tình huống mẫu ở cột phải','chọn một gợi ý ở cột phải')
                html=html.replace('id="btnRegenerateRoster"', 'id="btnRegenerateRoster" style="display:none"').replace('Tạo lại điểm ngẫu nhiên','Tạo lại hồ sơ mẫu')
                html=html.replace('<body>','<body><div style="padding:8px 14px;background:#eee;color:#222;font-size:12px">'+note+' &nbsp; <a href="/advisor/workspace" style="color:#214b76;font-weight:600">Công việc cố vấn →</a></div>',1)
                from stream_chat import patch_page
                from advisor_view import patch_advisor_view
                html=patch_advisor_view(patch_page(html))
                html=html.replace('currentEngineMode = mode;', "currentEngineMode = mode; const regen = document.getElementById('btnRegenerateRoster'); if (regen) regen.style.display = mode === 'auto' ? 'none' : '';",1)
                return HTMLResponse(html)
            dep.call=page
    from stream_chat import install_stream
    advisor_route=next(r for r in s.app.routes if getattr(r,'path',None)=='/api/advisor/chat' and 'POST' in getattr(r,'methods',set()))
    install_stream(s.app, advisor_route.dependant.call)
    if callable(getattr(s,'_get_active_roster',None)):
        from advisor_workspace import install_workspace
        install_workspace(s.app,s._get_active_roster,root)
    return idx

def main():
    p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--port',type=int,default=8765);p.add_argument('--gemini',action='store_true');p.add_argument('--slm-url');a=p.parse_args();root=a.repo.resolve()
    if not (root/'src/api/studenthub_server.py').is_file():raise SystemExit('Wrong repository')
    os.chdir(root);sys.path.insert(0,str(root));os.environ.update(PYTHONUTF8='1',RAG_AUTO_LLM='0',OLLAMA_BASE_URL='http://127.0.0.1:11434',OLLAMA_BASE_MODEL='portable-disabled',OLLAMA_LORA_MODEL='portable-disabled')
    key='';model='gemini-2.5-flash'
    if a.gemini:
        from dotenv import load_dotenv
        load_dotenv(root/'.env',override=False);key=os.environ.get('GEMINI_API_KEY','').strip();model=os.environ.get('GEMINI_MODEL',model)
        if not key or key=='your_gemini_api_key_here':raise SystemExit('Set GEMINI_API_KEY locally in .env or environment (never commit).')
    # Original RAG cloud auto-upgrade remains disabled even when Gemini public path is enabled.
    os.environ['RAG_AUTO_LLM']='0'
    import uvicorn
    from src.api import studenthub_server as s
    if a.slm_url:
        from local_slm import MODEL
        model=MODEL
    idx=install(s,root,key,model,a.slm_url)
    print('PORTABLE_ADVISOR_READY',json.dumps(idx.stats(),ensure_ascii=False), 'local-slm' if a.slm_url else 'gemini-public' if key else 'offline-tools',flush=True)
    uvicorn.run(s.app,host='127.0.0.1',port=a.port,lifespan='off')
if __name__=='__main__':main()
