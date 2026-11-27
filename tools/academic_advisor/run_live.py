"""Deadline-safe opt-in hybrid product mode. Pure comparison modes remain separate."""
import argparse, os, sys, json
from contextvars import ContextVar
from pathlib import Path
from runtime_v5 import install as install_v5
from knowledge import Index, answer
from advisor import plan
from workflow import run_workflow
from presentation import present
from whatif import simulate
from conversation import add_conversation
AUTO=ContextVar('chronoreg_product_auto', default=False)

def install(s,root):
    if getattr(s, "_chronoreg_product_installed", False):
        raise RuntimeError("Do not stack ChronoReg overlays; start a fresh process")
    index=Index(root)
    original=s._run_rag_engine
    # Insert broad knowledge search behind existing source-table and clause handlers.
    def fallback(question,mode,advisor_bundle=None):
        ab=advisor_bundle or {}
        if AUTO.get() and mode=='chrono_rag':
            advisory=run_workflow(question,ab,root) or plan(question,ab,root)
            if advisory is not None:return advisory
        if AUTO.get() and mode=='chrono_rag' and ab.get('category') in (None,'REGULATION') and not any(ab.get(k) for k in ('roster_context','news_context','course_trend_text','single_student_mode')):
            pred=answer(index,s.llm_backend,question)
            pred.update(advisor_category=ab.get('category'),advisor_entities=ab.get('entities'))
            return pred
        return original(question,mode,advisor_bundle=advisor_bundle)
    s._run_rag_engine=fallback
    install_v5(s,root)
    source_rag=s._run_rag_engine
    def composed(question,mode,advisor_bundle=None):
        pred=source_rag(question,mode,advisor_bundle=advisor_bundle)
        if AUTO.get() and mode=='chrono_rag':
            return present(s.llm_backend,question,pred,advisor_bundle)
        return pred
    s._run_rag_engine=composed
    route=s._router.route_decision
    def routed(question,student_context=None):
        r=route(question,student_context)
        if AUTO.get() and r.risk_tier!='RED' and r.selected_engine=='continual_lora':
            r.selected_engine=r.actual_engine_used='chrono_rag'
            r.detected_signals=list(r.detected_signals)+['Knowledge Access']
            r.routing_reason='Chế độ sản phẩm: ưu tiên nguồn; LoRA 7B có thể tổng hợp tri thức truy xuất. Nhánh LoRA thuần giữ riêng.'
        return r
    s._router.route_decision=routed
    original_meta=s._build_metadata
    def meta(cited_doc_ids,latency_ms,engine_note=None,actual_engine='chrono_rag',pred=None):
        p=pred or {}
        if p.get('engine_mode')=='ADVISOR_SIMULATION':
            return {'engine_mode':'ADVISOR_SIMULATION','inference_source':'deterministic_calculator','source_type':'hypothetical_calculation','source_label':'Tính toán từ giả định do người dùng nhập (không phải LoRA thuần)','model_name':None,'latency_ms':round(latency_ms,2),'engine_note':'Không dùng GPA học kỳ thay CPA; không xác nhận điều kiện học vụ.','quality_qualified':False,'simulation':p['simulation']}
        if p.get('engine_mode') in ('ADVISOR_PLAN','ADVISOR_WORKFLOW'):
            sources=p.get('advisor_sources',[]);first=sources[0] if sources else {}
            return {'doc_id':None,'doc_title':Path(first['source_path']).name if first else None,'effective_year':None,'sha256_short':first.get('sha256','')[:8] or None,'source_type':'advisor_plan','source_label':'Hồ sơ demo + quy tắc tư vấn (không phải LoRA thuần)','inference_source':p.get('inference_source','deterministic_advisor_plan'),'engine_mode':p['engine_mode'],'workflow_tools':p.get('workflow_tools',[]),'advisor_report':p.get('advisor_report'),'model_name':None,'latency_ms':round(latency_ms,2),'engine_note':'Đề xuất từ hồ sơ đang chọn, không xác nhận điều kiện chính thức.','quality_qualified':False,'roadmap':p.get('roadmap',[]),'advisor_sources':sources,'advisor_category':p.get('advisor_category'),'advisor_entities':p.get('advisor_entities')}
        if 'knowledge_sources' in p:
            sources=p['knowledge_sources'];model=p.get('model_name')
            return {'doc_id':sources[0]['doc_id'] or None if sources else None,'doc_title':Path(sources[0]['path']).name if sources else None,'effective_year':None,'sha256_short':sources[0]['sha256'][:8] if sources else None,'source_type':'knowledge_access','source_label':'LoRA 7B + Knowledge Access' if model else 'Knowledge Access — trích nguồn','inference_source':p['inference_source'],'engine_mode':p['engine_mode'],'model_name':model,'latency_ms':round(latency_ms,2),'engine_note':'Không phải LoRA thuần; kiểm tra số liệu không chứng nhận sự đúng đắn hay hiệu lực.','quality_qualified':False,'knowledge_sources':sources,'advisor_category':p.get('advisor_category'),'advisor_entities':p.get('advisor_entities')}
        return original_meta(cited_doc_ids,latency_ms,engine_note,actual_engine=actual_engine,pred=pred)
    def presentation_meta(cited_doc_ids,latency_ms,engine_note=None,actual_engine='chrono_rag',pred=None):
        p=pred or {}
        m=meta(cited_doc_ids,latency_ms,engine_note,actual_engine=actual_engine,pred=p)
        if p.get('presentation_mode'):
            m['presentation_mode']=p['presentation_mode']
            m['advisor_evidence']=p.get('advisor_evidence','')
            m['advisor_quote_checks']=p.get('advisor_quote_checks',[])
            m['narrative_diagnostics']=p.get('narrative_diagnostics',[])
            m['narrative_attempts']=p.get('narrative_attempts',0)
            m['advisor_priority']=p.get('advisor_priority')
            if p['presentation_mode'] in ('LORA_ADVISOR_NARRATIVE','LORA_ADVISOR_PRIORITY'):
                m.update(model_name=p['model_name'],inference_source=p['inference_source'],source_label=m.get('source_label','')+' | LoRA 7B chọn ưu tiên tư vấn',quality_qualified=False)
        return m
    s._build_metadata=presentation_meta
    if hasattr(s,'_answer_text_from_pred'):
        original_text=s._answer_text_from_pred
        def answer_text(pred,question):
            # Preserve complete source excerpts and roadmaps rather than truncating mid-condition.
            if pred.get('presentation_mode') or pred.get('engine_mode') in ('ADVISOR_PLAN','ADVISOR_WORKFLOW','LORA_KNOWLEDGE_ACCESS','KNOWLEDGE_EXCERPTS','ADVISOR_SIMULATION'):
                return pred.get('predicted_answer','')
            return original_text(pred,question)
        s._answer_text_from_pred=answer_text
    # FastAPI endpoint closure reads dependant.call. Preserve request validation and routes.
    found=False
    for r in s.app.routes:
        if getattr(r,'path',None)=='/api/chat' and 'POST' in getattr(r,'methods',set()):
            old=r.dependant.call
            def wrapped(req,_old=old):
                token=AUTO.set(not req.force_engine or req.force_engine=='auto')
                try:
                    if AUTO.get() and not getattr(req,'mssv',None):
                        result=simulate(req.question.strip())
                        if result is not None:
                            route_result=s._router.route_decision(req.question.strip())
                            if route_result.risk_tier=='GREEN':
                                from fastapi.responses import JSONResponse
                                route_result.routing_reason='Công cụ mô phỏng CPA từ giả định rõ ràng; không phải kết luận quy chế.'
                                route_result.detected_signals=list(route_result.detected_signals)+['What-if calculation']
                                pred={'predicted_answer':result['answer'],'engine_mode':'ADVISOR_SIMULATION','simulation':result,'latency_ms':0.5,'cited_doc_ids':[],'is_advisor_composite':True}
                                return JSONResponse(content=s._build_chat_response(req.question,route_result,'chrono_rag',pred))
                    return _old(req)
                finally:AUTO.reset(token)
            r.dependant.call=wrapped;found=True
            request_type=r.dependant.body_params[0].type_
            break
    if not found:raise RuntimeError('No /api/chat route')
    add_conversation(s,wrapped,request_type)
    # UI overlay only: accurately label actual engines without editing Viet's tracked UI.
    ui=Path(root)/'studenthub_ui/index.html'
    if ui.is_file():
        from fastapi.responses import HTMLResponse
        html=ui.read_text(encoding='utf-8').replace('LoRA 3B','LoRA 7B').replace('Chrono-RAG 3B','Chrono-RAG 7B').replace('Ollama 3B','Ollama 7B').replace('mô hình 3B','mô hình 7B')
        html=html.replace('escapeHtml(engineLabel(actualEngine, riskTier))', "escapeHtml((m.presentation_mode === 'LORA_ADVISOR_NARRATIVE' || m.presentation_mode === 'LORA_ADVISOR_PRIORITY') ? 'LoRA 7B Advisor' : m.engine_mode === 'LORA_KNOWLEDGE_ACCESS' ? 'LoRA 7B + Knowledge Access' : m.engine_mode === 'ADVISOR_SIMULATION' ? 'Advisor — mô phỏng CPA' : m.engine_mode === 'ADVISOR_WORKFLOW' ? 'Advisor — công cụ cố vấn' : m.engine_mode === 'ADVISOR_PLAN' ? 'Advisor — hồ sơ và lộ trình' : m.engine_mode === 'KNOWLEDGE_EXCERPTS' ? 'Knowledge Access (trích nguồn)' : engineLabel(actualEngine, riskTier))")
        html=html.replace("if (src === 'ollama_local')", "if (src === 'ollama_local_advisor') return 'LoRA 7B + bằng chứng';\n      if (src === 'ollama_local_knowledge') return 'Ollama LoRA 7B + nguồn';\n      if (src === 'deterministic_calculator') return 'Công cụ tính CPA';\n      if (src === 'deterministic_advisor_plan') return 'Phân tích hồ sơ';\n      if (src === 'knowledge_excerpts') return 'Trích nguồn';\n      if (src === 'ollama_local')")
        html=html.replace("      document.getElementById('chatList').appendChild(card);", """      if (Array.isArray(m.roadmap) && m.roadmap.length) {
        const roadmap = document.createElement('section');
        roadmap.setAttribute('aria-label', 'Lộ trình tư vấn');
        roadmap.style.cssText = 'margin:12px 16px;padding:12px 14px;border-left:2px solid #58766c;display:grid;gap:12px';
        const heading = document.createElement('strong'); heading.textContent = 'Lộ trình đề xuất'; roadmap.appendChild(heading);
        m.roadmap.forEach((step, i) => {
          const item = document.createElement('div');
          const title = document.createElement('strong'); title.textContent = (i+1) + '. ' + step.title;
          const body = document.createElement('div'); body.textContent = step.detail; body.style.fontSize = '12px';
          item.append(title, body); roadmap.appendChild(item);
        });
        card.querySelector('.ai-tier2').after(roadmap);
      }
      if (m.advisor_report && m.advisor_report.draft && typeof m.advisor_report.text === 'string') {
        const reportPanel = document.createElement('section');
        reportPanel.style.cssText = 'margin:12px 16px;padding:12px;border:1px solid #b8c4bf;border-radius:6px;display:grid;gap:8px';
        const label = document.createElement('strong'); label.textContent = m.advisor_report.title;
        const note = document.createElement('div'); note.textContent = m.advisor_report.scope === 'individual_private' ? 'Bản nháp chứa thông tin cá nhân. Chỉ lưu hoặc chia sẻ qua kênh được phép.' : 'Bản nháp tổng hợp, không gồm tên/mã sinh viên.';
        const download = document.createElement('button'); download.type = 'button'; download.textContent = 'Lưu bản nháp (.txt)';
        download.addEventListener('click', () => {
          const url = URL.createObjectURL(new Blob([m.advisor_report.text], {type:'text/plain;charset=utf-8'}));
          const link = document.createElement('a'); link.href = url; link.download = 'chronoreg-advisor-draft.txt'; link.click();
          setTimeout(() => URL.revokeObjectURL(url), 1000);
        });
        reportPanel.append(label,note,download); card.querySelector('.ai-tier2').after(reportPanel);
      }
      if (m.advisor_evidence) {
        const proof = document.createElement('details');
        proof.style.cssText = 'margin:12px 16px; font-size:12px;';
        const head = document.createElement('summary'); head.textContent = 'Dữ kiện và điều khoản đối chiếu';
        const body = document.createElement('pre'); body.style.cssText = 'white-space:pre-wrap;overflow-wrap:anywhere;font:inherit;'; body.textContent = m.advisor_evidence;
        proof.append(head,body); card.querySelector('.ai-tier2').after(proof);
      }
      document.getElementById('chatList').appendChild(card);""")
        html=html.replace("if (actualEngine === 'continual_lora') {", "if (m.engine_mode === 'ADVISOR_SIMULATION' || m.engine_mode === 'ADVISOR_PLAN' || m.engine_mode === 'LORA_KNOWLEDGE_ACCESS' || m.engine_mode === 'KNOWLEDGE_EXCERPTS') { provenanceHtml = `<span>${escapeHtml(m.source_label || '')}</span>`; } else if (actualEngine === 'continual_lora') {")
        html=html.replace('Continual LoRA 7B (2026)', 'Continual LoRA 7B thuần (2026)').replace('>LoRA 7B</button>', '>LoRA 7B thuần</button>')
        # Never advertise factual guarantees from demo badges.
        html=html.replace('Khóa năm học 2021–2026 qua SHA-256 Registry hoặc tư vấn quy trình từ LoRA 7B.', 'Auto: LoRA 7B + kho tri thức, hồ sơ demo và kiểm tra nguồn. So sánh: LoRA thuần và RAG.')
        # Context is held only in the current browser tab. New requests consume
        # the token; concurrent responses cannot overwrite a newer turn.
        html=html.replace('async function handleSend(overrideMssv = null) {', "let advisorContextToken = null, advisorTurnSequence = 0;\n    async function handleSend(overrideMssv = null) {")
        html=html.replace("const payload = { question, force_engine: currentEngineMode };", "const seq = ++advisorTurnSequence;\n        const autoMode = !currentEngineMode || currentEngineMode === 'auto';\n        const payload = { question, force_engine: currentEngineMode };\n        if (autoMode && advisorContextToken && !overrideMssv) payload.context_token = advisorContextToken;\n        advisorContextToken = null;")
        html=html.replace("const res = await fetch('/api/chat', {", "const res = await fetch(autoMode ? '/api/advisor/chat' : '/api/chat', {")
        html=html.replace("const data = await res.json();\n        removeTypingSkeleton();", "const data = await res.json();\n        if (seq === advisorTurnSequence && autoMode) advisorContextToken = data.context_token || null;\n        removeTypingSkeleton();")
        # Do not expose the signed token or silently mislabel an expanded query.
        html=html.replace("      document.getElementById('chatList').appendChild(card);", """      if (data.context_resolution && ['student_followup','year_followup'].includes(data.context_resolution.kind)) {
        const note = document.createElement('div');
        note.style.cssText = 'font-size:12px;margin:8px 16px;color:var(--ink-muted)';
        note.textContent = data.context_resolution.kind === 'student_followup' ? 'Tiếp tục hồ sơ sinh viên vừa được chọn.' : 'Câu hỏi được hiểu là: ' + data.context_resolution.effective_question;
        card.querySelector('.ai-tier2').before(note);
      }
      document.getElementById('chatList').appendChild(card);""")
        html=html.replace('function setEngineMode(mode) {', 'function setEngineMode(mode) {\n      advisorContextToken = null; advisorTurnSequence++;')
        html=html.replace("runComparison(data.question || '', compareId, this);", "runComparison(data.question || '', compareId, this, m.advisor_entities?.mssv || null);")
        html=html.replace('async function runComparison(question, targetId, btn) {','async function runComparison(question, targetId, btn, mssv = null) {')
        html=html.replace('body: JSON.stringify({ question }),', 'body: JSON.stringify(mssv ? { question, mssv } : { question }),')
        for r in s.app.routes:
            if getattr(r,'path',None)=='/'  and 'GET' in getattr(r,'methods',set()):
                def page():return HTMLResponse(html)
                r.dependant.call=page;break
    @s.app.get('/api/knowledge/status')
    def knowledge_status():return {**index.stats(),'product_version':'12.0','model':'chronoreg-lora:7b','mode':'hybrid_advisor'}
    s._chronoreg_product_installed=True
    return index

def main():
    p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--port',type=int,default=8765);a=p.parse_args();root=a.repo.resolve()
    if not (root/'src/api/studenthub_server.py').is_file():raise SystemExit('Wrong repo root')
    os.chdir(root);sys.path.insert(0,str(root));os.environ.update(OLLAMA_BASE_URL='http://127.0.0.1:11434',OLLAMA_BASE_MODEL='chronoreg-base:7b',OLLAMA_LORA_MODEL='chronoreg-lora:7b',PYTHONUTF8='1')
    import uvicorn
    from src.api import studenthub_server as s
    idx=install(s,root)
    h=s.llm_backend.check_ollama_health(force=True)
    if not h.get('all_models_ready'):raise SystemExit('Ollama 7B models not ready: '+str(h))
    print('KNOWLEDGE_INDEX:',json.dumps(idx.stats(),ensure_ascii=False),flush=True)
    print('CHRONOREG_ADVISOR_V12_READY',flush=True)
    uvicorn.run(s.app,host='127.0.0.1',port=a.port,lifespan='off')
if __name__=='__main__':main()
