import unittest
from pathlib import Path
from workflow import run_workflow
from advisor_report import build_report

class ReportTests(unittest.TestCase):
 def setUp(self):
  self.roster={'class_short':'K69-CNTT1','cohort':'QH-2024','semester':'2025-2026','students':[{'student_id':'24000001','full_name':'Demo A','gpa_semester':1.5,'owed_credits':3,'drl':65,'bang_diem':[{'ma_mon':'INT1008','dat':False}]},{'student_id':'24000002','full_name':'Demo B','gpa_semester':3.5,'owed_credits':0,'drl':90},{'student_id':'24000003','full_name':'Demo C','gpa_semester':None,'owed_credits':0,'drl':90}],'courses':[{'ma_mon':'INT1008','ten_mon':'Lập trình','so_tin_chi':3}]}
 def ask(self,q,sid=None):return run_workflow(q,{'category':'STUDENT_STATUS' if sid else 'CLASS_STATS','student_id':sid,'roster_obj':self.roster},Path('.'))
 def test_class_aggregate(self):
  p=self.ask('Lập báo cáo tư vấn cho lớp cô và kế hoạch hành động');r=p['advisor_report'];self.assertEqual(r['scope'],'class_aggregate');self.assertTrue(r['draft']);self.assertIn('Ưu tiên gặp riêng: 1',r['text']);self.assertIn('Cần bổ sung dữ liệu: 1',r['text']);self.assertIn('Chưa thấy tín hiệu: 1',r['text']);self.assertTrue(all(s['student_id'] not in r['text'] and s['full_name'] not in r['text'] for s in self.roster['students']));self.assertTrue(all(a['owner'] and a['checkpoint'] and a['completion_check'] for a in r['actions']))
 def test_student_report(self):
  r=self.ask('Lập phiếu tư vấn cho em này và kế hoạch hành động','24000001')['advisor_report'];self.assertEqual(r['scope'],'individual_private');self.assertIn('24000001',r['text']);self.assertIn('INT1008',r['text']);self.assertNotIn('24000002',r['text']);self.assertIn('GPA tích lũy',r['text']);self.assertIn('chưa gửi',r['text'])
 def test_reject_scope(self):
  for p in [self.ask('Lớp K68 lập báo cáo tư vấn'),self.ask('Lập phiếu tư vấn','unknown')]:self.assertIsNone(p['advisor_report']);self.assertEqual(p['workflow_tools'],['scope_check'])
 def test_empty_groups(self):
  r=build_report(self.roster,groups={},duplicate_records=3);self.assertIn('chưa phân nhóm: 3',r['text']);self.assertNotIn('Mời riêng nhóm ưu tiên',r['text']);self.assertIn('Rà hồ sơ thiếu',r['text'])
 def test_no_override(self):
  self.assertIsNone(self.ask('GPA trung bình lớp?'));self.assertIsNone(self.ask('Sinh viên có được phép học vượt và lập phiếu tư vấn','24000001'))
 def test_combined(self):
  p=self.ask('So sánh phương án học lại và lập phiếu tư vấn, soạn tin nhắn riêng cho em này','24000001');self.assertTrue({'credit_scenarios','advisor_report','communication_draft'}<=set(p['workflow_tools']));self.assertTrue(p['advisor_report']['draft']);self.assertIn('không tự gửi',p['predicted_answer'])
 def test_api(self):
  # Reuse the existing portable mock-server integration and check metadata wiring.
  from fastapi import FastAPI
  from fastapi.testclient import TestClient
  from pydantic import BaseModel
  from types import SimpleNamespace
  from unittest.mock import patch
  import tempfile,run_live,conversation
  from portable_runtime import install
  class Request(BaseModel):
   question:str;force_engine:str|None=None;mssv:str|None=None
  with tempfile.TemporaryDirectory() as t,patch.object(run_live,'answer',run_live.answer),patch.object(conversation,'next_context',conversation.next_context):
   root=Path(t);v=root/'data/versioning';v.mkdir(parents=True)
   for f in ('publication_holds.jsonl','reviewed_documents.jsonl','rag_chunks.jsonl'):(v/f).write_text('')
   ui=root/'studenthub_ui';ui.mkdir();(ui/'index.html').write_text("<body><script>document.getElementById('chatList').appendChild(card);\n      document.getElementById('chatList').appendChild(card);</script></body>")
   app=FastAPI();backend=SimpleNamespace(lora_model='disabled',base_model='disabled',ollama_url='http://local')
   def route(q,student_context=None):return SimpleNamespace(risk_tier='RED' if 'ngoại lệ' in q else 'GREEN',selected_engine='continual_lora',actual_engine_used='continual_lora',detected_signals=[],routing_reason='original')
   s=SimpleNamespace(app=app,llm_backend=backend,_router=SimpleNamespace(route_decision=route),_run_rag_engine=lambda *a,**k:{'predicted_answer':'original','engine_mode':'ORIGINAL','latency_ms':0},_build_metadata=lambda *a,**k:{})
   @app.get('/')
   def page():return 'original'
   @app.post('/api/chat')
   def chat(req:Request):
    r=s._router.route_decision(req.question)
    if r.risk_tier=='RED':return {'routing':{'risk_tier':'RED'},'answer':'blocked'}
    mode=req.force_engine if req.force_engine not in (None,'auto') else r.selected_engine
    if mode=='continual_lora':return s._run_web_lora(req.question)
    p=s._run_rag_engine(req.question,mode,advisor_bundle={'category':'STUDENT_STATUS' if req.mssv else 'CLASS_STATS','student_id':req.mssv,'roster_obj':self.roster,'roster_context':'demo'})
    return {'question':req.question,'answer':p['predicted_answer'],'metadata':s._build_metadata([],p['latency_ms'],pred=p)}
   install(s,root);client=TestClient(app)
   q='Lập báo cáo tư vấn cho lớp cô';body={'question':q,'force_engine':'auto'}
   r=client.post('/api/chat',json=body).json();self.assertEqual(r['metadata']['advisor_report']['scope'],'class_aggregate')
   self.assertEqual(client.post('/api/chat',json={**body,'force_engine':'chrono_rag'}).json()['answer'],'original')
   self.assertEqual(client.post('/api/chat',json={**body,'question':q+' xin ngoại lệ'}).json()['routing']['risk_tier'],'RED')
   self.assertIn('Lưu bản nháp (.txt)',client.get('/').text)

if __name__=='__main__':unittest.main()
