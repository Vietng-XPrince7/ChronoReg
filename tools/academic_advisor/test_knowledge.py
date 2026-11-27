import json, tempfile, hashlib, unittest, os
from pathlib import Path
from types import SimpleNamespace
from knowledge import Index,answer
from run_live import install,AUTO

class Backend:
    def __init__(self):self.ollama_timeout=300;self.lora_model='chronoreg-lora:7b';self.base_model='base';self.ollama_url='http://local';self.calls=[];self.text='Theo văn bản, thời hạn là 14 ngày [S1].';self.reason='stop'
    def _make_client(self,*a,**k):return self,False
    def post(self,url,json,timeout):self.calls.append(json);return self
    def raise_for_status(self):pass
    def json(self):return {'message':{'content':self.text},'done_reason':self.reason}
class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);d=self.root/'data/raw/uet/markdown/2025';d.mkdir(parents=True);v=self.root/'data/versioning';v.mkdir(parents=True)
        self.body='## Thủ tục cấp giấy xác nhận\nThời hạn xử lý giấy xác nhận sinh viên là 14 ngày kể từ khi hồ sơ hợp lệ.'
        p=d/'giay_xac_nhan.md';p.write_text(self.body,encoding='utf8');sha=hashlib.sha256(p.read_bytes()).hexdigest()
        held=d/'held.md';held.write_text('Giấy xác nhận sinh viên thời hạn 999 ngày.',encoding='utf8')
        (v/'publication_holds.jsonl').write_text(json.dumps({'doc_id':'hold','content_sha256':hashlib.sha256(held.read_bytes()).hexdigest()}),encoding='utf8')
        (v/'reviewed_documents.jsonl').write_text(json.dumps({'doc_id':'g','content_sha256':sha,'review_status':'verified_against_source','academic_year':'2025-2026'}),encoding='utf8')
        (v/'rag_chunks.jsonl').write_text(json.dumps({'doc_id':'g','content_sha256':sha,'policy_qa_ready':True,'eligible_for_policy_qa':True,'academic_year_verified':'2025-2026','text':self.body}),encoding='utf8')
        b=self.root/'data/qa_benchmark';b.mkdir();(b/'answers.md').write_text('Giấy xác nhận 888 ngày',encoding='utf8')
        self.index=Index(self.root);self.backend=Backend();self.q='Thời hạn xử lý giấy xác nhận sinh viên năm học 2025-2026?'
    def tearDown(self):self.tmp.cleanup()
    def test_inventory(self):
        self.assertEqual(self.index.stats()['files'],2);self.assertEqual(self.index.stats()['held'],1);self.assertEqual(self.index.stats()['reviewed_chunks'],1);self.assertFalse(any('999' in c.text or '888' in c.text for c in self.index.chunks))
    def test_lora_with_evidence(self):
        r=answer(self.index,self.backend,self.q);self.assertEqual(r['model_name'],'chronoreg-lora:7b');self.assertEqual(r['engine_mode'],'LORA_KNOWLEDGE_ACCESS');self.assertIn('14 ngày',r['predicted_answer']);self.assertIn('14 ngày',self.backend.calls[0]['messages'][1]['content'])
    def test_wrong_number(self):
        self.backend.text='Thời hạn là 99 ngày [S1].';r=answer(self.index,self.backend,self.q);self.assertEqual(r['engine_mode'],'KNOWLEDGE_EXCERPTS');self.assertNotIn('99 ngày',r['predicted_answer'])
    def test_unverified_year(self):
        r=answer(self.index,self.backend,'Thời hạn giấy xác nhận sinh viên năm 2022?');self.assertEqual(r['engine_mode'],'KNOWLEDGE_EXCERPTS');self.assertFalse(self.backend.calls)
    def test_no_year_caution(self):
        r=answer(self.index,self.backend,'Thời hạn xử lý giấy xác nhận sinh viên?');self.assertIn('chưa xác nhận',r['predicted_answer'])
    def test_bad_reference(self):
        self.backend.text='14 ngày [S99]';self.assertIsNone(answer(self.index,self.backend,self.q)['model_name'])
    def test_dispatch(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from pydantic import BaseModel
        class Request(BaseModel):question:str;force_engine:str|None=None;mssv:str|None=None
        app=FastAPI();backend=self.backend
        def route(q,student_context=None):return SimpleNamespace(risk_tier='RED' if q=='blocked' or 'RED_TEST' in q else 'GREEN',selected_engine='continual_lora',actual_engine_used='continual_lora',detected_signals=[],routing_reason='original')
        s=SimpleNamespace(app=app,llm_backend=backend,_router=SimpleNamespace(route_decision=route),_run_rag_engine=lambda *a,**k:{'engine_mode':'ORIGINAL'},_build_metadata=lambda *a,**k:{'original':True})
        @app.post('/api/chat')
        def chat(req:Request):
            r=s._router.route_decision(req.question)
            if r.risk_tier=='RED':return {'engine_mode':'RED'}
            engine=req.force_engine if req.force_engine not in (None,'auto') else r.selected_engine
            if engine=='continual_lora':return {'engine_mode':'PURE'}
            return s._run_rag_engine(req.question,engine,advisor_bundle={'category':'REGULATION'})
        @app.post('/api/compare')
        def compare(req:Request):return s._run_rag_engine(req.question,'chrono_rag',advisor_bundle={'category':'REGULATION'})
        s._build_chat_response=lambda q,r,e,p: {'answer':p['predicted_answer'],'metadata':s._build_metadata([],p['latency_ms'],pred=p)}
        install(s,self.root);client=TestClient(app)
        self.assertEqual(client.post('/api/chat',json={'question':self.q}).json()['engine_mode'],'LORA_KNOWLEDGE_ACCESS')
        self.assertEqual(client.post('/api/chat',json={'question':self.q,'force_engine':'continual_lora'}).json()['engine_mode'],'PURE')
        self.assertEqual(client.post('/api/chat',json={'question':self.q,'force_engine':'chrono_rag'}).json()['engine_mode'],'ORIGINAL')
        self.assertEqual(client.post('/api/compare',json={'question':self.q}).json()['engine_mode'],'ORIGINAL')
        self.assertEqual(client.post('/api/chat',json={'question':'blocked'}).json()['engine_mode'],'RED')
        from whatif import EXAMPLE
        result=client.post('/api/chat',json={'question':EXAMPLE}).json()
        self.assertEqual(result['metadata']['simulation']['projected_cpa'],'2.70')
        self.assertEqual(result['metadata']['engine_mode'],'ADVISOR_SIMULATION')
        self.assertEqual(client.post('/api/chat',json={'question':EXAMPLE,'force_engine':'continual_lora'}).json()['engine_mode'],'PURE')
        self.assertEqual(client.post('/api/chat',json={'question':EXAMPLE+' RED_TEST'}).json()['engine_mode'],'RED')
        self.assertNotEqual(client.post('/api/chat',json={'question':EXAMPLE,'mssv':'123'}).json().get('metadata',{}).get('engine_mode'),'ADVISOR_SIMULATION')
        self.assertFalse(AUTO.get())
