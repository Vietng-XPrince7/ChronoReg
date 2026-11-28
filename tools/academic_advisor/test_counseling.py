import os, unittest
from pathlib import Path
from conversation import resolve, next_context, add_conversation
from intelligence import dispatch
from counseling import meeting_intent
from quality import norm
from types import SimpleNamespace
ROOT=Path(os.environ.get('CHRONOREG_TEST_REPO','.')).resolve()

class CounselingTests(unittest.TestCase):
 def setUp(self):
  self.st={'student_id':'24000001','full_name':'Demo A','gpa_semester':1.4,'drl':68,'owed_credits':7,'bang_diem':[{'ma_mon':'INT1008','dat':False},{'ma_mon':'INT2210','dat':False}]}
  self.roster={'class_short':'K69-CNTT1','cohort':'QH-2024 (K69)','major':'Công nghệ Thông tin','semester':'2025-2026','students':[self.st,{'student_id':'24000002','full_name':'Demo B'}],'courses':[{'ma_mon':'INT1008','so_tin_chi':3},{'ma_mon':'INT2210','so_tin_chi':4}]}
  self.ab={'category':'STUDENT_STATUS','student_id':'24000001','entities':{'mssv':'24000001'},'roster_obj':self.roster}
  self.previous={'kind':'student','mssv':'24000001'}
 def answer(self,q):
  p=dispatch(q,self.ab,ROOT);self.assertEqual(p['advisor_intent'],'meeting_preparation');return p['predicted_answer']
 def test_private_meeting(self):
  a=self.answer('Nếu cô gặp riêng sinh viên này, cô nên nói gì và cần tìm hiểu thêm những thông tin nào?')
  self.assertIn('Demo A',a);self.assertNotIn('Demo B',a);self.assertIn('Những điều nên hỏi',a);self.assertIn('1.40',a);self.assertIn('7 tín chỉ nợ',a);self.assertIn('minh chứng rèn luyện',a)
 def test_context_changes_questions(self):
  q='Nếu em này vừa đi làm vừa học, cô nên hỗ trợ như thế nào?'
  a=self.answer(q);self.assertIn('lịch ca',a);self.assertIn('chưa được ghi nhận trong hồ sơ demo',a);self.assertIn('không tự hứa',a)
  b=self.answer('Nếu em này mất gốc, cô nên hỗ trợ ra sao?');self.assertIn('kiến thức nền ở phần nào',b);self.assertNotIn('lịch ca',b)
  c=self.answer('Nếu em này khó khăn tài chính và mất động lực, cô nên hỗ trợ thế nào?');self.assertIn('không hứa cấp học bổng',c);self.assertIn('mục tiêu nhỏ',c)
 def test_healthy_record(self):
  self.st.update(gpa_semester=3.6,drl=90,owed_credits=0,bang_diem=[])
  a=self.answer('Cô nên hỏi gì trong buổi gặp riêng em này?');self.assertNotIn('minh chứng rèn luyện',a);self.assertNotIn('khối lượng môn?',a);self.assertIn('không suy diễn vấn đề',a)
 def test_exclusions(self):
  for q in ('Soạn tin nhắn mời em này gặp riêng','Gặp riêng em này, cô nên hỏi quy định học bổng nào?', 'So sánh phương án học lại trước buổi gặp','Cô nên hỏi gì trong buổi gặp về giới hạn tối đa tín chỉ?'):
   self.assertFalse(meeting_intent(norm(q)),q)
 def test_no_leak_wrong_scope_and_duplicate(self):
  p=dispatch('Cô nên hỏi gì khi gặp riêng em này ở K65?',self.ab,ROOT);self.assertEqual(p['workflow_tools'],['scope_check']);self.assertNotIn('Demo A',p['predicted_answer'])
  self.roster['students'].append(dict(self.st));p=dispatch('Cô nên hỏi gì khi gặp riêng em này?',self.ab,ROOT);self.assertEqual(p['workflow_tools'],['scope_check']);self.assertNotIn('Demo A',p['predicted_answer'])
 def test_followup_and_fresh_tab(self):
  for q in ('Nếu cô gặp riêng sinh viên này, cô nên nói gì?', 'Nếu em này vừa đi làm vừa học, cô nên hỗ trợ thế nào?', 'Trong buổi gặp đó cô nên hỏi gì?'):
   self.assertEqual(resolve(q,None,self.previous)[1:],('24000001','student_followup'));self.assertEqual(resolve(q,None,{})[2],'clarify_student')
  self.assertEqual(resolve('Em này và em khác cần gặp riêng?',None,self.previous)[2],'clarify_student')
  self.assertEqual(resolve('Điểm chuẩn năm 2024?',None,self.previous)[2],'new')
 def test_reject_scope_context(self):
  meta={'advisor_category':'STUDENT_STATUS','advisor_entities':{'mssv':'24000001'},'roadmap':[{'title':'x'}],'workflow_tools':['scope_check']}
  self.assertEqual(next_context('Gặp riêng em này',{'metadata':meta}),{})
 def test_http_context_and_reset(self):
  from fastapi import FastAPI
  from fastapi.testclient import TestClient
  from pydantic import BaseModel
  class Req(BaseModel):question:str;force_engine:str|None=None;mssv:str|None=None
  def server(req):
   if req.mssv:
    p=dispatch(req.question,self.ab,ROOT)
    if not p: p={'predicted_answer':'demo','roadmap':[{'title':'x'}],'advisor_category':'STUDENT_STATUS','advisor_entities':{'mssv':req.mssv}}
    return {'answer':p['predicted_answer'],'metadata':p,'routing':{'risk_tier':'GREEN'}}
   return {'answer':'public','metadata':{},'routing':{'risk_tier':'GREEN'}}
  s=SimpleNamespace(app=FastAPI(),_router=SimpleNamespace(route_decision=lambda q:SimpleNamespace(risk_tier='GREEN')));add_conversation(s,server,Req)
  c=TestClient(s.app);send=lambda q,**kw:c.post('/api/advisor/chat',json={'question':q,**kw}).json()
  seed=send('Phân tích sinh viên',mssv='24000001');self.assertTrue(seed['context_token'])
  r=send('Nếu em này vừa đi làm vừa học, cô nên hỗ trợ như thế nào?',context_token=seed['context_token']);self.assertIn('lịch ca',r['answer']);self.assertTrue(r['context_token']);self.assertEqual(r['context_resolution']['kind'],'student_followup')
  r2=send('Trong buổi gặp đó cô nên hỏi gì?',context_token=r['context_token']);self.assertIn('Những điều nên hỏi',r2['answer']);self.assertIn('lịch ca',r2['answer']);self.assertNotIn('Hồ sơ demo:',r2['answer'])
  fresh=send('Trong buổi gặp đó cô nên hỏi gì?');self.assertEqual(fresh['metadata']['engine_mode'],'CONTEXT_CLARIFICATION');self.assertNotIn('Demo A',fresh['answer'])
