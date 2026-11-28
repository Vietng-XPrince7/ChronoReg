import unittest,json,tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import httpx
from portable_runtime import GeminiClient,public_query,make_answer,fix_response,disabled_client,unavailable,install
import run_live,conversation

class PortableTests(unittest.TestCase):
 def test_public_scope(self):
  self.assertTrue(public_query('Điều kiện tốt nghiệp UET năm 2025?'))
  for q in ['MSSV 24020027 cần tư vấn','Hồ sơ sinh viên','GPA của em này','abc@example.org']:
   self.assertFalse(public_query(q))
 def test_gemini_contract(self):
  def handle(req):
   self.assertEqual(req.headers['x-goog-api-key'],'secret-test')
   self.assertEqual(req.url.host,'generativelanguage.googleapis.com')
   self.assertNotIn('secret-test',str(req.url));body=json.loads(req.content)
   self.assertEqual(body['systemInstruction']['parts'][0]['text'],'system')
   return httpx.Response(200,json={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'Nguồn [S1]'}]}}]})
  c=GeminiClient('secret-test','gemini-test',httpx.MockTransport(handle))
  r=c.post('',{'messages':[{'role':'system','content':'system'},{'role':'user','content':'public query'}]},30).json()
  self.assertEqual(r['done_reason'],'stop');self.assertEqual(r['message']['content'],'Nguồn [S1]')
 def test_generation_label(self):
  offline=object()
  def original(index,backend,q):
   if backend is offline:return {'engine_mode':'KNOWLEDGE_EXCERPTS'}
   return {'engine_mode':'LORA_KNOWLEDGE_ACCESS','model_name':backend.lora_model}
  f=make_answer(original,'secret-test','gemini-test')
  self.assertEqual(f(None,offline,'Hồ sơ sinh viên')['engine_mode'],'KNOWLEDGE_EXCERPTS')
  result=f(None,offline,'Quy chế UET?');self.assertEqual(result['engine_mode'],'GEMINI_KNOWLEDGE_ACCESS')
  self.assertEqual(result['model_name'],'gemini-test');self.assertEqual(result['inference_source'],'gemini_public_knowledge')
  self.assertEqual(make_answer(original,'','gemini-test')(None,offline,'Quy chế?')['engine_mode'],'KNOWLEDGE_EXCERPTS')
 def test_no_fake_model(self):
  self.assertIsNone(unavailable()['model_name'])
  self.assertEqual(unavailable()['engine_mode'],'LORA_UNAVAILABLE')
  with self.assertRaises(RuntimeError):disabled_client()
 def test_reply_labels(self):
  r=fix_response({'metadata':{'engine_mode':'GEMINI_KNOWLEDGE_ACCESS','source_label':'LoRA 7B'}},'gemini-public')
  self.assertIn('Gemini',r['metadata']['source_label']);self.assertNotIn('LoRA 7B',r['metadata']['source_label'])
 def test_product_presentation(self):
  from portable_runtime import product_copy
  data={'answer':'Hồ sơ demo: 27 tín chỉ nợ. Đây là kế hoạch tự học thử, không phải lịch mở lớp hay cam kết kết quả.', 'metadata':{'engine_mode':'ADVISOR_WORKFLOW','advisor_category':'STUDENT_STATUS','workflow_tools':['scope_check'],'source_label':'Hồ sơ demo + quy tắc tư vấn (không phải LoRA thuần)'},'context_token':'opaque'}
  r=product_copy(data);self.assertNotIn('demo',r['answer']);self.assertIn('27 tín chỉ nợ',r['answer']);self.assertEqual(r['metadata']['roster_provenance'],'sample_roster');self.assertEqual(r['context_token'],'opaque')
  quote={'answer':'Hồ sơ demo: trích dẫn nguyên văn', 'metadata':{'engine_mode':'SOURCE_CLAUSE'}}
  self.assertEqual(product_copy(quote)['answer'],'Hồ sơ demo: trích dẫn nguyên văn')
 def test_http_portable(self):
  from fastapi import FastAPI
  from fastapi.testclient import TestClient
  from pydantic import BaseModel
  class Request(BaseModel):question:str;force_engine:str|None=None;mssv:str|None=None
  with tempfile.TemporaryDirectory() as t,patch.object(run_live,'answer',run_live.answer),patch.object(conversation,'next_context',conversation.next_context):
   root=Path(t);p=root/'data/raw/uet/markdown';p.mkdir(parents=True);(p/'policy.md').write_text('Quy định giấy xác nhận sinh viên: thời hạn xử lý 14 ngày.',encoding='utf8');v=root/'data/versioning';v.mkdir(parents=True)
   for name in ('publication_holds.jsonl','reviewed_documents.jsonl','rag_chunks.jsonl'):(v/name).write_text('')
   (root/'studenthub_ui').mkdir();(root/'studenthub_ui/index.html').write_bytes((Path(__file__).resolve().parents[2]/'studenthub_ui/index.html').read_bytes())
   app=FastAPI()
   @app.get('/')
   def homepage():return {}
   b=SimpleNamespace(lora_model='disabled',base_model='disabled',ollama_url='http://local')
   def route(q,student_context=None):return SimpleNamespace(risk_tier='RED' if 'ngoại lệ' in q else 'GREEN',selected_engine='continual_lora',actual_engine_used='continual_lora',detected_signals=[],routing_reason='original')
   s=SimpleNamespace(app=app,llm_backend=b,_router=SimpleNamespace(route_decision=route),_run_rag_engine=lambda *a,**k:{'engine_mode':'ORIGINAL'},_build_metadata=lambda *a,**k:{'original':True})
   @app.post('/api/chat')
   def chat(req:Request):
    r=s._router.route_decision(req.question)
    if r.risk_tier=='RED':return {'routing':{'risk_tier':'RED'},'metadata':{'engine_mode':'RED'},'answer':'blocked'}
    engine=req.force_engine if req.force_engine not in (None,'auto') else r.selected_engine
    if engine=='continual_lora':return s._run_web_lora(req.question)
    pred=s._run_rag_engine(req.question,engine,advisor_bundle={'category':'REGULATION'})
    return {'question':req.question,'answer':pred['predicted_answer'],'metadata':s._build_metadata([],pred['latency_ms'],pred=pred)}
   s._build_chat_response=lambda q,r,e,p:{'answer':p['predicted_answer'],'metadata':s._build_metadata([],p['latency_ms'],pred=p)}
   s._get_active_roster=lambda:{'class_short':'K69-DEMO','semester':'demo','students':[{'student_id':'24000001','gpa_semester':1.4,'owed_credits':7,'drl':68}]}
   with patch('advisor_workspace.storage_path',return_value=root/'workspace-test.sqlite3'):
    install(s,root)
   client=TestClient(app,base_url='http://127.0.0.1:8765')
   import re
   page=client.get('/').text;self.assertIn('/advisor/workspace',page);self.assertIn('readAdvisorStream',page)
   streamed=client.post('/api/advisor/chat/stream',json={'question':'Thời hạn giấy xác nhận sinh viên?'});self.assertEqual(streamed.status_code,200)
   events=[json.loads(x) for x in streamed.text.splitlines()];self.assertEqual(events[0]['event'],'processing');self.assertEqual(events[-1]['event'],'done');self.assertEqual(''.join(e['text'] for e in events if e['event']=='delta'),events[-1]['data']['answer']);self.assertIn('14 ngày',events[-1]['data']['answer'])
   red=client.post('/api/advisor/chat/stream',json={'question':'Xin ngoại lệ','force_engine':'auto'});self.assertEqual(json.loads(red.text.splitlines()[-1])['data']['routing']['risk_tier'],'RED')
   workspace=client.get('/advisor/workspace');self.assertEqual(workspace.status_code,200)
   headers={'X-Advisor-Workspace':re.search(r"const token='([^']+)'",workspace.text)[1]}
   state=client.get('/api/advisor/workspace',headers=headers);self.assertEqual(state.status_code,200);self.assertEqual(state.json()['plans'],[])
   self.assertEqual(client.get('/api/knowledge/status').json()['intelligence_revision'],'2.0.0-pilot')
   self.assertFalse(client.get('/api/knowledge/status').json()['pure_lora_available'])
   reply=client.post('/api/chat',json={'question':'Thời hạn giấy xác nhận sinh viên?' }).json()
   self.assertEqual(reply['metadata']['engine_mode'],'KNOWLEDGE_EXCERPTS');self.assertIsNone(reply['metadata']['model_name']);self.assertIn('14 ngày',reply['answer'])
   reply=client.post('/api/advisor/chat',json={'question':'Thời hạn giấy xác nhận sinh viên?','force_engine':'continual_lora'}).json();self.assertEqual(reply['metadata']['engine_mode'],'LORA_UNAVAILABLE')
   self.assertEqual(client.post('/api/chat',json={'question':'Xin ngoại lệ','force_engine':'continual_lora'}).json()['routing']['risk_tier'],'RED')
if __name__=='__main__':unittest.main()
