import unittest
from types import SimpleNamespace
from conversation import Context,resolve,next_context,add_conversation,public_year
from whatif import simulate,EXAMPLE,GOAL_EXAMPLE

class ContextTests(unittest.TestCase):
 def test_token_expiry_and_tamper(self):
  now=[10];s=Context(key=b'x'*32,ttl=5,clock=lambda:now[0]);token=s.issue({'kind':'student','mssv':'24020027'})
  self.assertEqual(s.read(token)['mssv'],'24020027');self.assertEqual(s.read(token+'x'),{});self.assertEqual(Context(key=b'y'*32).read(token),{})
  now[0]=16;self.assertEqual(s.read(token),{})
 def test_student_reference(self):
  p={'kind':'student','mssv':'24020027'}
  self.assertEqual(resolve('Em này cần lộ trình gì?',None,p)[1:],('24020027','student_followup'))
  self.assertEqual(resolve('Sinh viên này cần tư vấn?', '24020028',p)[1:],('24020028','explicit'))
  self.assertEqual(resolve('Em này cần tư vấn?',None,p,'24020029')[1:],('24020029','explicit'))
  self.assertEqual(resolve('Em này và em khác cần tư vấn?',None,p)[2],'clarify_student')
  self.assertEqual(resolve('Em này ở K68 có cần tư vấn?',None,p)[2],'clarify_student')
  self.assertEqual(resolve('Điểm chuẩn năm 2024?',None,p)[1:],(None,'new'))
 def test_no_student_context(self):self.assertEqual(resolve('Tư vấn sinh viên này',None,{})[2],'clarify_student')
 def test_year_followup(self):
  p={'kind':'public_year','question':'Điểm chuẩn ngành Khoa học máy tính UET năm 2024?'}
  self.assertEqual(resolve('Còn năm 2025 thì sao?',None,p),('Điểm chuẩn ngành Khoa học máy tính UET năm 2025?',None,'year_followup'))
  self.assertEqual(resolve('Còn năm học 2025-2026?',None,p)[2],'clarify_year')
  p['question']='Học phí QH-2022 năm học 2024-2025?';self.assertEqual(resolve('Còn năm học 2025-2026?',None,p)[2],'clarify_year')
 def test_annual_followup(self):
  p={'kind':'public_year','question':'NCKH Viện TTNT năm học 2024-2025 có gì?'}
  self.assertEqual(resolve('Còn năm học 2025-2026?',None,p)[0],'NCKH Viện TTNT năm học 2025-2026 có gì?')
 def test_clear_context(self):
  self.assertFalse(next_context('Điểm chuẩn năm 2024?',{'routing':{'risk_tier':'RED'},'metadata':{'engine_mode':'SOURCE_TABLE'}}))
  self.assertFalse(next_context('Điểm chuẩn năm 2024?',{'metadata':{'engine_mode':'SOURCE_TABLE','advisor_category':'CLASS_STATS'}}))
  self.assertFalse(next_context('GPA',{'metadata':{'engine_mode':'ADVISOR_PLAN','advisor_category':'STUDENT_STATUS','advisor_entities':{'mssv':'24020027'},'roadmap':[]}}))
 def test_alias(self):
  self.assertEqual(simulate(EXAMPLE.replace('CPA hiện tại','GPA tích lũy hiện tại').replace('Tính CPA mới','Tính GPA tích lũy mới'))['projected_cpa'],'2.70')
  self.assertEqual(simulate(GOAL_EXAMPLE.replace('CPA hiện tại','GPA tích lũy hiện tại').replace('CPA mục tiêu','GPA tích lũy mục tiêu'))['required_gpa'],'4.00')
 def test_http_round_trip(self):
  from fastapi import FastAPI
  from fastapi.testclient import TestClient
  from pydantic import BaseModel
  class Request(BaseModel):question:str;force_engine:str|None=None;mssv:str|None=None
  def dispatch(req):
   mode='PURE' if req.force_engine=='continual_lora' else 'ADVISOR_PLAN' if req.mssv else 'SOURCE_TABLE'
   risk='RED' if 'ngoại lệ' in req.question else 'GREEN'
   return {'question':req.question,'answer':req.mssv or req.question,'routing':{'risk_tier':risk},'metadata':{'engine_mode':mode,'advisor_category':'STUDENT_STATUS' if req.mssv else 'REGULATION','advisor_entities':{'mssv':req.mssv},'roadmap':[{'title':'demo'}] if req.mssv else []}}
  app=FastAPI();s=SimpleNamespace(app=app,_router=SimpleNamespace(route_decision=lambda q:SimpleNamespace(risk_tier='RED' if 'ngoại lệ' in q else 'GREEN')));add_conversation(s,dispatch,Request)
  c=TestClient(app)
  def ask(question,**kw):return c.post('/api/advisor/chat',json={'question':question,**kw}).json()
  r=ask('Điểm chuẩn năm 2024?');t=r['context_token'];self.assertTrue(t)
  r=ask('Còn năm 2025?',context_token=t);self.assertEqual(r['question'],'Điểm chuẩn năm 2025?');self.assertEqual(r['context_resolution']['kind'],'year_followup')
  r=ask('Tư vấn',mssv='24020027');t=r['context_token'];self.assertTrue(t)
  self.assertEqual(ask('Em này cần lộ trình gì?',context_token=t)['answer'],'24020027')
  self.assertEqual(ask('Em này cần lộ trình gì?')['metadata']['engine_mode'],'CONTEXT_CLARIFICATION')
  self.assertEqual(ask('Em này cần tư vấn ngoại lệ?',context_token=t)['routing']['risk_tier'],'RED')
  pure=ask('Em này cần tư vấn?',context_token=t,force_engine='continual_lora');self.assertEqual(pure['metadata']['engine_mode'],'PURE');self.assertIsNone(pure['context_token'])
if __name__=='__main__':unittest.main()
