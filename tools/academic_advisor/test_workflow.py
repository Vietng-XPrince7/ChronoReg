import unittest,tempfile
from pathlib import Path
from workflow import run_workflow,pack,debt_rows,screening,caps

class WorkflowTests(unittest.TestCase):
 def setUp(self):
  self.roster={'class_short':'K69-CNTT1','cohort':'QH-2024','semester':'2025-2026','courses':[{'ma_mon':'INT1008','ten_mon':'Lập trình','so_tin_chi':3},{'ma_mon':'INT2210','ten_mon':'Giải thuật','so_tin_chi':4},{'ma_mon':'MAT1042','ten_mon':'Giải tích','so_tin_chi':4}],'students':[{'student_id':'24000001','full_name':'Sinh viên A','gpa_semester':1.5,'drl':65,'owed_credits':11,'bang_diem':[{'ma_mon':'INT1008','dat':False},{'ma_mon':'INT2210','dat':False},{'ma_mon':'MAT1042','dat':False},{'ma_mon':'MAT1042','dat':True}]},{'student_id':'24000002','full_name':'Sinh viên B','gpa_semester':3.5,'drl':90,'owed_credits':0},{'student_id':'24000003','full_name':'Sinh viên C','gpa_semester':None,'drl':90,'owed_credits':0}]}
 def ask(self,q,personal=False,sid='24000001'):
  return run_workflow(q,{'category':'STUDENT_STATUS' if personal else 'CLASS_STATS','roster_obj':self.roster,'student_id':sid if personal else None,'entities':{'mssv':sid} if personal else {}},Path('.'))
 def test_multi_tool_class(self):
  r=self.ask('Lớp cô có em nào cần gặp riêng? Soạn thông báo cho lớp.');a=r['predicted_answer'];self.assertEqual(r['workflow_tools'],['scope_check','screening','communication_draft']);self.assertIn('Sinh viên A',a);self.assertNotIn('Sinh viên B',a);self.assertIn('Cần bổ sung dữ liệu — 1',a);self.assertNotIn('24000001',a.split('Dự thảo thông báo chung')[1]);self.assertIsNone(r['model_name'])
 def test_plan_and_draft(self):
  r=self.ask('So sánh phương án học lại và soạn tin nhắn riêng cho em này',True);a=r['predicted_answer'];self.assertIn('credit_scenarios',r['workflow_tools']);self.assertIn('tối đa 6 tín chỉ',a);self.assertIn('tối đa 12 tín chỉ',a);self.assertIn('7 tín chỉ',a);self.assertIn('MAT1042',a);self.assertIn('Có cả lần đạt và không đạt',a);self.assertNotIn('Sinh viên B',a);self.assertIn('không tự gửi',a)
 def test_budget(self):
  r=self.ask('Lập phương án học lại tối đa 4 tín chỉ môn nợ',True);self.assertIn('tối đa 4 tín chỉ',r['predicted_answer']);self.assertNotIn('tối đa 12 tín chỉ',r['predicted_answer'])
 def test_scope(self):
  for q in ['Lớp K68 cần gặp riêng ai?','Lớp K69-CNTT2 cần gặp riêng ai?','Lớp QH-2023 cần gặp riêng ai?','Năm học 2023-2024 lớp cô cần gặp riêng ai?']:
   r=self.ask(q);self.assertNotIn('Sinh viên A',r['predicted_answer']);self.assertEqual(r['workflow_tools'],['scope_check'])
 def test_no_student(self):
  r=self.ask('Lập phương án học lại',True,'missing');self.assertNotIn('Sinh viên A',r['predicted_answer']);self.assertFalse(r['roadmap'])
 def test_no_override(self):
  self.assertIsNone(self.ask('GPA trung bình lớp?'));self.assertIsNone(self.ask('Sinh viên này có được phép học vượt?',True));self.assertIsNone(run_workflow('Soạn thông báo',{'category':'REGULATION'},Path('.')))
 def test_duplicate_history_and_oversize(self):
  st=self.roster['students'][0];st['bang_diem'].append({'ma_mon':'INT1008','dat':False});rows,amb,missing=debt_rows(st,self.roster['courses']);self.assertEqual(sum(x[2] for x in rows),7);self.assertEqual(amb,['MAT1042']);bins,over=pack(rows,3);self.assertEqual(len(bins),1);self.assertEqual(over[0][0],'INT2210')
 def test_invalid_budgets(self):
  self.assertEqual(caps('toi da 0 tin chi mon no'),[]);self.assertEqual(caps('toi da 6 tin chi mon no toi da 12 tin chi hoc lai'),[])
 def test_duplicate_students_excluded(self):
  groups,dup=screening([self.roster['students'][0],self.roster['students'][0]]);self.assertEqual(dup,2);self.assertFalse(groups)
 def test_all_missing(self):
  groups,_=screening([{'student_id':'x'}]);self.assertEqual(len(groups[3]),1);self.assertFalse(groups[4])

 def test_http_dispatch(self):
  from fastapi import FastAPI
  from fastapi.testclient import TestClient
  from pydantic import BaseModel
  from types import SimpleNamespace
  from unittest.mock import patch
  import run_live,conversation
  from portable_runtime import install
  class Request(BaseModel):
   question:str;force_engine:str|None=None;mssv:str|None=None
  with tempfile.TemporaryDirectory() as t,patch.object(run_live,'answer',run_live.answer),patch.object(conversation,'next_context',conversation.next_context):
   root=Path(t);v=root/'data/versioning';v.mkdir(parents=True)
   for f in ('publication_holds.jsonl','reviewed_documents.jsonl','rag_chunks.jsonl'):(v/f).write_text('')
   app=FastAPI();b=SimpleNamespace(lora_model='disabled',base_model='disabled',ollama_url='http://local')
   def route(q,student_context=None):return SimpleNamespace(risk_tier='RED' if 'ngoại lệ' in q else 'GREEN',selected_engine='continual_lora',actual_engine_used='continual_lora',detected_signals=[],routing_reason='original')
   def original(*a,**kw):return {'predicted_answer':'original','engine_mode':'ORIGINAL','latency_ms':0}
   server=SimpleNamespace(app=app,llm_backend=b,_router=SimpleNamespace(route_decision=route),_run_rag_engine=original,_build_metadata=lambda *a,**k:{'original':True})
   @app.post('/api/chat')
   def chat(req:Request):
    r=server._router.route_decision(req.question)
    if r.risk_tier=='RED':return {'routing':{'risk_tier':'RED'},'answer':'blocked'}
    mode=req.force_engine if req.force_engine not in (None,'auto') else r.selected_engine
    if mode=='continual_lora':return server._run_web_lora(req.question)
    bundle={'category':'STUDENT_STATUS' if req.mssv else 'CLASS_STATS','roster_obj':self.roster,'student_id':req.mssv,'entities':{'mssv':req.mssv},'roster_context':'demo'}
    pred=server._run_rag_engine(req.question,mode,advisor_bundle=bundle)
    return {'question':req.question,'answer':pred['predicted_answer'],'metadata':server._build_metadata([],pred['latency_ms'],pred=pred)}
   install(server,root);client=TestClient(app)
   q='Lớp cô có em nào cần gặp riêng? Soạn thông báo cho lớp.'
   r=client.post('/api/chat',json={'question':q,'force_engine':'auto'}).json();self.assertEqual(r['metadata']['engine_mode'],'ADVISOR_WORKFLOW');self.assertIn('communication_draft',r['metadata']['workflow_tools'])
   r=client.post('/api/chat',json={'question':q,'force_engine':'chrono_rag'}).json();self.assertEqual(r['answer'],'original')
   r=client.post('/api/chat',json={'question':q+' xin ngoại lệ','force_engine':'auto'}).json();self.assertEqual(r['routing']['risk_tier'],'RED')

if __name__=='__main__':unittest.main()
