import hashlib,json,os,tempfile,unittest,zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import httpx
from local_slm import LocalClient,download,extract_runtime,MODEL
from slm_advisor import suggest,voice,knowledge_with_source,present
from portable_runtime import fix_response
from knowledge import Index
from presentation import present as source_present

class LocalTests(unittest.TestCase):
 def test_download_integrity(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'x.bin';p.write_bytes(b'abc');h=hashlib.sha256(b'abc').hexdigest()
   with patch('urllib.request.urlopen',side_effect=AssertionError('network not needed')):self.assertEqual(download('https://invalid',p,h,100),p)
   import io
   with patch('urllib.request.urlopen',return_value=io.BytesIO(b'wrong')):
    with self.assertRaises(ValueError):download('https://invalid',p,'0'*64,100)
   self.assertEqual(p.read_bytes(),b'abc');self.assertFalse(p.with_suffix('.bin.part').exists())
 def test_zip_path_traversal(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'runtime.zip';target=Path(d)/'runtime'
   with zipfile.ZipFile(p,'w') as z:z.writestr('../evil.exe','bad')
   with self.assertRaises(ValueError):extract_runtime(p,target)
   with zipfile.ZipFile(p,'w') as z:z.writestr('bin/llama-server.exe','test')
   self.assertEqual(extract_runtime(p,target).read_text(),'test')
 def test_local_contract(self):
  def handle(req):
   self.assertEqual(req.url.host,'127.0.0.1');self.assertEqual(req.url.path,'/v1/chat/completions');data=json.loads(req.content);self.assertIn('gọi người hỏi là cô',data['messages'][0]['content']);self.assertEqual(data['response_format']['type'],'json_schema')
   return httpx.Response(200,json={'choices':[{'message':{'content':'{"priority":"A1"}'},'finish_reason':'stop'}]})
  c=LocalClient('http://127.0.0.1:5432',httpx.MockTransport(handle));r=c.post('',{'messages':[{'role':'system','content':'test'}],'format':{'type':'object'}},1).json();self.assertEqual(r['done_reason'],'stop')
  with self.assertRaises(ValueError):LocalClient('https://example.com')
 def test_advice_gate(self):
  def model(text):
   c=SimpleNamespace(post=lambda *a,**k:SimpleNamespace(json=lambda:{'message':{'content':json.dumps({'advice':text})},'done_reason':'stop'}));return SimpleNamespace(_make_client=lambda *a:(c,False),ollama_url='local',ollama_timeout=1)
  self.assertIsNotNone(suggest(model('Cô nên trao đổi riêng với sinh viên về kế hoạch học lại.'),'hỏi','nguồn',{}))
  self.assertIsNone(suggest(model('Sinh viên chắc chắn đủ điều kiện nhận học bổng.'),'hỏi','nguồn',{}))
  self.assertIsNone(suggest(model('Cô yêu cầu học thêm 15 tín chỉ.'),'hỏi','nguồn',{}))
 def test_labels(self):
  data=fix_response({'answer':'Thầy/cô cần kiểm tra','metadata':{'engine_mode':'LORA_KNOWLEDGE_ACCESS','source_label':'LoRA 7B'}},'local-slm');self.assertEqual(data['metadata']['model_name'],MODEL);self.assertEqual(data['metadata']['engine_mode'],'SLM_KNOWLEDGE_ACCESS');self.assertEqual(data['answer'],'Cô cần kiểm tra')
 def test_graduation_dispatch_and_hold(self):
  idx=Index(Path(os.environ['CHRONOREG_TEST_REPO']));q='tôi bị trượt 1 môn có bị hạ bằng k';p=knowledge_with_source(lambda *a:None,idx,None,q);self.assertEqual(p['engine_mode'],'SOURCE_CLAUSE');self.assertIn('5%',p['predicted_answer']);p=present(source_present,SimpleNamespace(),q,p,{});self.assertIn('Không nhất thiết',p['predicted_answer']);self.assertIn('5%',p['predicted_answer'])
  self.assertEqual(knowledge_with_source(lambda *a:{'engine_mode':'fallback'},idx,None,'K71 trượt môn có bị hạ bằng không?')['engine_mode'],'fallback')
 def test_real_application_mocked_model(self):
  # Use actual FastAPI endpoint installation, but mock the local model process.
  from fastapi import FastAPI
  from fastapi.testclient import TestClient
  from pydantic import BaseModel
  from portable_runtime import install
  import run_live,conversation,local_slm
  class Req(BaseModel):question:str;force_engine:str|None=None;mssv:str|None=None
  with tempfile.TemporaryDirectory() as tmp, patch.object(run_live,'answer',run_live.answer),patch.object(run_live,'present',run_live.present),patch.object(conversation,'next_context',conversation.next_context):
   root=Path(tmp);p=root/'data/raw/uet/markdown';p.mkdir(parents=True);(p/'policy.md').write_text('Quy định giấy xác nhận sinh viên: thời hạn xử lý 14 ngày.',encoding='utf8');v=root/'data/versioning';v.mkdir(parents=True)
   for name in ('publication_holds.jsonl','reviewed_documents.jsonl','rag_chunks.jsonl'):(v/name).write_text('')
   app=FastAPI();b=SimpleNamespace(lora_model='disabled',base_model='disabled',ollama_url='http://local')
   def route(q,student_context=None):return SimpleNamespace(risk_tier='RED' if 'ngoại lệ' in q else 'GREEN',selected_engine='continual_lora',actual_engine_used='continual_lora',detected_signals=[],routing_reason='original')
   s=SimpleNamespace(app=app,llm_backend=b,_router=SimpleNamespace(route_decision=route),_run_rag_engine=lambda *a,**k:{'engine_mode':'ORIGINAL'},_build_metadata=lambda *a,**k:{'original':True})
   @app.post('/api/chat')
   def chat(req:Req):
    r=s._router.route_decision(req.question)
    if r.risk_tier=='RED':return {'routing':{'risk_tier':'RED'},'metadata':{'engine_mode':'RED'},'answer':'blocked'}
    engine=req.force_engine if req.force_engine not in (None,'auto') else r.selected_engine
    if engine=='continual_lora':return s._run_web_lora(req.question)
    roster={'class_short':'K69-CNTT1','cohort':'QH-2024 (K69)','students':[{'student_id':'24000001','full_name':'Demo A','gpa_semester':1.4,'owed_credits':7,'drl':68},{'student_id':'24000002','full_name':'Demo B','gpa_semester':3.5,'owed_credits':0,'drl':90}], 'courses':[]}
    bundle={'category':'STUDENT_STATUS','student_id':req.mssv,'entities':{'mssv':req.mssv},'roster_obj':roster} if req.mssv else {'category':'REGULATION'}
    pred=s._run_rag_engine(req.question,engine,advisor_bundle=bundle)
    return {'question':req.question,'answer':pred['predicted_answer'],'metadata':s._build_metadata([],pred['latency_ms'],pred=pred)}
   s._build_chat_response=lambda q,r,e,p:{'answer':p['predicted_answer'],'metadata':s._build_metadata([],p['latency_ms'],pred=p)}
   calls=[]
   def post(*args,**kwargs):calls.append(kwargs);return SimpleNamespace(raise_for_status=lambda:None,json=lambda:{'message':{'content':json.dumps({'answer':'Cô có thể hướng dẫn sinh viên theo thời hạn 14 ngày.','refs':['P1']})},'done_reason':'stop'})
   with patch.object(local_slm.LocalClient,'post',side_effect=post):
    install(s,root,model=MODEL,slm_url='http://127.0.0.1:5432');client=TestClient(app)
    self.assertEqual(client.get('/api/knowledge/status').json()['deployment_profile'],'local-slm')
    r=client.post('/api/chat',json={'question':'Thời hạn giấy xác nhận sinh viên?'}).json();self.assertEqual(r['metadata']['engine_mode'],'SLM_KNOWLEDGE_ACCESS');self.assertIn('14 ngày',r['answer']);self.assertEqual(len(calls),1)
    self.assertEqual(client.post('/api/chat',json={'question':'Xin ngoại lệ'}).json()['routing']['risk_tier'],'RED');self.assertEqual(len(calls),1)
    self.assertEqual(client.post('/api/advisor/chat',json={'question':'Thời hạn giấy xác nhận sinh viên?','force_engine':'continual_lora'}).json()['metadata']['engine_mode'],'LORA_UNAVAILABLE');self.assertEqual(len(calls),1)
    # Actual portable wrapper and Auto endpoint, not a direct conversation-only fixture.
    def ask(q,token=None,sid=None):
     response=client.post('/api/advisor/chat',json={'question':q,'force_engine':'auto','context_token':token,'mssv':sid});self.assertEqual(response.status_code,200);return response.json()
    seed=ask('Em hãy phân tích toàn diện tình hình học tập của sinh viên 24000001.',sid='24000001');self.assertTrue(seed['context_token']);self.assertEqual(seed['metadata']['advisor_intent'],'student_review')
    a=ask('Nếu cô gặp riêng sinh viên này, cô nên nói gì?',seed['context_token']);self.assertTrue(a['context_token']);self.assertEqual(a['metadata']['advisor_intent'],'meeting_preparation')
    b=ask('Nếu em này vừa đi làm vừa học, cô nên hỗ trợ thế nào?',a['context_token']);self.assertIn('lịch ca',b['answer']);self.assertTrue(b['context_token'])
    c=ask('Chỉ cho cô 2 câu hỏi',b['context_token']);self.assertEqual(c['answer'].count('• '),2);self.assertIn('lịch ca',c['answer'])
    d=ask('Em ấy không còn đi làm nữa.',b['context_token']);self.assertIn('đính chính',d['answer']);self.assertNotIn('lịch ca',ask('Trong buổi gặp đó cô nên hỏi gì?',d['context_token'])['answer'])
    other=ask('Cô nên hỏi gì khi gặp riêng sinh viên này?',b['context_token'],sid='24000002');self.assertIn('Demo B',other['answer']);self.assertNotIn('lịch ca',other['answer']);self.assertNotIn('Demo A',other['answer'])
    self.assertEqual(ask('Trong buổi gặp đó cô nên hỏi gì?')['metadata']['engine_mode'],'CONTEXT_CLARIFICATION')
    self.assertIsNone(ask('Xin ngoại lệ',b['context_token'])['context_token'])

if __name__=='__main__':unittest.main()
