"""Opt-in local runtime overlay; does not modify tracked files in ChronoReg."""
import argparse, json, os, sys, time
from pathlib import Path
from quality import lookup, messages_for, unsupported_numbers
from scholarship import lookup_rates
from scope import classify_with_scope
from tuition import lookup_tuition
from regulation import lookup_regulation, selection


def install(s, root):
    backend=s.llm_backend
    if backend is None: raise RuntimeError('Main LLM backend failed to initialize')
    backend.ollama_timeout=300
    backend.remote_url=''
    # Evaluation cache is not live inference. Keep existing extractive fallback available.
    backend._eval_cache={'chrono_rag': {}, 'naive_rag': {}}
    original_rag=s._run_rag_engine
    original_meta=s._build_metadata
    original_classify=getattr(s, "classify_query", None)
    if original_classify is not None:
        def classify(question, *, roster=None, mssv=None):
            return classify_with_scope(original_classify, question, roster=roster, mssv=mssv)
        s.classify_query=classify

    # Public, supported legal topics use evidence in Auto, not parameter memory.
    # Explicit force_engine in main /api/chat still wins except RED, and /api/compare
    # keeps the original pure LoRA branch. Do not override RED/YELLOW or greetings.
    router=getattr(s,'_router',None)
    if router is not None:
        original_route=router.route_decision
        def route(question,student_context=None):
            r=original_route(question,student_context)
            if (not student_context and r.risk_tier=='GREEN' and r.selected_engine=='continual_lora' and selection(question)):
                r.selected_engine=r.actual_engine_used='chrono_rag'
                r.detected_signals=list(r.detected_signals)+['Điều khoản 3626: ưu tiên căn cứ']
                r.routing_reason='Câu hỏi quy chế/thủ tục có điều khoản nguồn cụ thể; ưu tiên Chrono-RAG và kiểm tra phạm vi áp dụng.'
            return r
        router.route_decision=route

    def call_ollama(model,prompt):
        is_lora=model==backend.lora_model
        payload={'model':model,'messages':messages_for(model,prompt,backend.lora_model),
                 'stream':False,'options':{'temperature':0,'num_ctx':4096,'num_predict':256 if is_lora else 768}}
        client,close=backend._make_client(backend.ollama_timeout,trust_env=False)
        try:
            resp=client.post(backend.ollama_url+'/api/chat',json=payload,timeout=backend.ollama_timeout)
            resp.raise_for_status(); data=resp.json(); answer=data.get('message',{}).get('content','').strip()
            if not answer: raise RuntimeError('Empty Ollama response')
            if not is_lora:
                # The main backend builds this exact template. Never use question as factual evidence.
                marker='\n\nCâu hỏi của sinh viên:'
                if marker in prompt:
                    ctx=prompt.split(marker,1)[0].split('\n\n',1)[-1]
                    bad=unsupported_numbers(answer,ctx)
                    if bad: raise RuntimeError('RAG answer rejected: unsupported numeric atoms '+str(sorted(bad)))
                if data.get('done_reason')=='length': raise RuntimeError('RAG generation truncated; use existing extractive fallback')
            return answer
        finally:
            if close: client.close()

    def rag(question, mode, advisor_bundle=None):
        ab=advisor_bundle or {}; t=time.monotonic()
        if mode=='chrono_rag' and not any(ab.get(k) for k in ('roster_context','news_context','course_trend_text','single_student_mode')):
            # Clause path is deliberately separate from table path and from pure LoRA.
            if selection(question):
                try:
                    c=lookup_regulation(root,question)
                except (OSError,ValueError) as exc:
                    print('SOURCE_CLAUSE_NOT_USED:',exc,flush=True)
                    return {'predicted_answer':'Chưa đủ căn cứ đã kiểm tra để trả lời điều khoản này. Vui lòng đối chiếu văn bản gốc hoặc liên hệ Phòng Đào tạo.', 'mode':mode,'latency_ms':(time.monotonic()-t)*1000,'cited_doc_ids':[],'inference_source':'source_clause_unavailable','engine_mode':'SOURCE_CLAUSE_UNAVAILABLE','is_advisor_composite':True}
                if c:
                    return {'predicted_answer':c['answer'],'answer':c['answer'],'mode':mode,'latency_ms':(time.monotonic()-t)*1000,'cited_doc_ids':[],'inference_source':'deterministic_source_clause','engine_mode':'SOURCE_CLAUSE','model_name':None,'is_advisor_composite':True,'source_clause':c,'advisor_category':ab.get('category'),'advisor_entities':ab.get('entities')}
            try:
                v=lookup(root,question) or lookup_rates(root,question) or lookup_tuition(root,question)
                if v:
                    # Respect current hold ledger even if the router does not identify it.
                    hold=Path(root)/'data/versioning/publication_holds.jsonl'
                    if not hold.is_file(): raise ValueError('Publication hold ledger unavailable')
                    held=[json.loads(x) for x in hold.read_text(encoding='utf-8-sig').splitlines() if x.strip()]
                    if any(h.get('content_sha256') in (v['sha256'], v.get('normalized_sha256') or v['sha256']) or (str(v['year']) in h.get('doc_id','') and (('diem-trung-tuyen' in h.get('doc_id','') and v.get('table_kind') is None) or ('dinh-muc-hoc-bong' in h.get('doc_id','') and v.get('table_kind')=='scholarship_rate') or (v.get('table_kind')=='tuition_rate' and Path(v['path']).stem.lower().replace('_','-') in h.get('doc_id','')))) for h in held):
                        raise ValueError('Source on publication hold')
                    return {'predicted_answer':v['answer'],'answer':v['answer'],'mode':mode,
                            'latency_ms':(time.monotonic()-t)*1000,'cited_doc_ids':[],
                            'inference_source':'deterministic_source_table','engine_mode':'SOURCE_TABLE',
                            'model_name':None,'is_advisor_composite':True,'source_table':v,
                            'advisor_category':ab.get('category'),'advisor_entities':ab.get('entities')}
            except (OSError,ValueError) as exc:
                print('SOURCE_TABLE_NOT_USED:',exc,flush=True)
        return original_rag(question,mode,advisor_bundle=advisor_bundle)

    def meta(cited_doc_ids,latency_ms,engine_note=None,actual_engine='chrono_rag',pred=None):
        c=(pred or {}).get('source_clause')
        if c:
            return {'doc_id':None,'doc_title':'Quyết định 3626/QĐ-ĐHQGHN','effective_year':2022,'sha256_short':c['sha256'][:8],'sha256':c['sha256'],'pdf_sha256':c['pdf_sha256'],'source_path':c['path'],'source_url':c['source_url'],'scope_url':c['scope_url'],'notice_url':c['notice_url'],'articles':c['articles'],'superseded_warning':None,'source_type':'source_clause','source_label':'QĐ 3626/QĐ-ĐHQGHN | SHA-256: '+c['sha256'][:8],'inference_source':'deterministic_source_clause','engine_mode':'SOURCE_CLAUSE','model_name':None,'latency_ms':round(latency_ms,2),'engine_note':'Trích điều khoản từ bản PDF/text lưu trong handoff; SHA của tệp cục bộ, không chứng nhận hiệu lực hiện tại.','quality_qualified':False}
        v=(pred or {}).get('source_table')
        if v:
            return {'doc_id':None,'doc_title':Path(v['path']).name,'effective_year':v['year'],
                    'sha256_short':v['sha256'][:8],'sha256':v['sha256'],'source_path':v['path'],
                    'superseded_warning':None,'source_type':'source_table','source_label':'Trích xuất bảng nguồn trực tiếp: '+v['path']+' | SHA-256: '+v['sha256'][:8],
                    'inference_source':'deterministic_source_table','engine_mode':'SOURCE_TABLE','model_name':None,
                    'latency_ms':round(latency_ms,2),'engine_note':'Đọc bảng gốc, không sinh số liệu bằng LLM; SHA của Markdown cục bộ, không phải chứng nhận pháp lý.',
                    'row_count':v['row_count'],'quality_qualified':False}
        return original_meta(cited_doc_ids,latency_ms,engine_note,actual_engine=actual_engine,pred=pred)
    backend._call_ollama=call_ollama
    s._run_rag_engine=rag
    s._build_metadata=meta


def main():
    p=argparse.ArgumentParser(); p.add_argument('--repo',type=Path,required=True); p.add_argument('--port',type=int,default=8765); a=p.parse_args(); root=a.repo.resolve()
    if not (root/'src/api/studenthub_server.py').is_file(): raise SystemExit('Wrong repo root')
    os.chdir(root);sys.path.insert(0,str(root)); os.environ.update(OLLAMA_BASE_URL='http://127.0.0.1:11434',OLLAMA_BASE_MODEL='chronoreg-base:7b',OLLAMA_LORA_MODEL='chronoreg-lora:7b',PYTHONUTF8='1')
    import uvicorn
    from src.api import studenthub_server as s
    install(s,root)
    health=s.llm_backend.check_ollama_health(force=True)
    if not health.get('all_models_ready'): raise SystemExit('Ollama 7B models not ready: '+str(health))
    print('CHRONOREG_7B_SOURCE_GUARD_V5_READY',flush=True)
    uvicorn.run(s.app,host='127.0.0.1',port=a.port,lifespan='off')
if __name__=='__main__':main()
