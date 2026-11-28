import unittest,json,tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from conversation import add_conversation
from stream_chat import install_stream
from test_quality_routes import Request,LOAD_SOURCE
from advisor_agent import route,product_result

class AgentTests(unittest.TestCase):
 def setUp(self):
  self.root=Path('.');self.roster={'class_short':'K69-DEMO','cohort':'QH-2024 (K69)','semester':'2025.1','students':[{'student_id':str(99000000+i),'gpa_semester':g,'owed_credits':o,'drl':d,'bang_diem':[{'ma_mon':'ABC0001','dat':False}]} for i,g,o,d in [(1,1.1,51,67),(2,1.2,44,64),(3,1.4,27,68),(4,1.4,20,59),(5,3.2,0,80)]], 'courses':[{'ma_mon':'ABC0001','so_tin_chi':3}]}
 def go(self,q,prior=None):return route(q,prior or {},None,None,self.roster,self.root)
 def test_class_selection_and_individual(self):
  r,c=self.go('Phân tích tình hình học tập của lớp hiện tại, theo em cô nên quan tâm đến những sinh viên nào nhất?');self.assertIn('99000004',r['answer']);self.assertEqual(c['topic'],'class');self.assertNotIn('99000001',json.dumps(c));
  r,c=self.go('Chọn 3 sinh viên cần ưu tiên và giải thích lý do.',c);self.assertIn('99000003',r['answer']);self.assertNotIn('99000004',r['answer']);self.assertEqual(c['count'],3)
  r,c=self.go('Cô nên làm gì với từng sinh viên?',c);self.assertIn('ABC0001',r['answer']);self.assertNotIn('99000004',r['answer']);self.assertIn('course_history',r['metadata']['workflow_tools']);self.assertIsNone(self.go('Cô nên làm gì với từng sinh viên?'))
  self.roster['students'][0]['owed_credits']=1;r,c=self.go('Cô nên làm gì với từng sinh viên?',c);self.assertIn('đã thay đổi',r['answer']);self.assertEqual(c,{})
 def test_composite_agenda(self):
  q='Cô có một buổi tư vấn lớp kéo dài 60 phút. Hãy phân tích tình hình lớp, xác định các vấn đề ưu tiên, lập chương trình buổi tư vấn và soạn thông báo mời sinh viên tham gia.'
  r,c=self.go(q);self.assertIn('Thông báo mời tham gia',r['answer']);self.assertNotIn('99000001',r['answer']);self.assertIn('communication_draft',r['metadata']['workflow_tools']);self.assertEqual(c['minutes'],60)
  import re
  self.assertEqual(sum(map(int,re.findall(r'\b(\d+) phút',r['answer']))),60)
  r,c=self.go('Nếu cô chỉ còn 30 phút thì nên bỏ bớt nội dung nào?',c);self.assertEqual(c['minutes'],30);self.assertIn('rút ngắn',r['answer']);self.assertEqual(sum(map(int,re.findall(r'\b(\d+) phút',r['answer']))),30)
 def test_fee_scope_calculation(self):
  def lookup(root,q):
   return {'answer':'• Học lại, cải thiện điểm (đồng/tín chỉ): '+('924.000' if '2025-2026' in q else '869.000')+' đồng.','path':'fixture.md','sha256':'test'}
  with patch('tuition.lookup_tuition',side_effect=lookup),patch('advisor_agent.source_table',side_effect=lambda root,v:{'answer':v['answer'],'metadata':{'engine_mode':'SOURCE_TABLE'},'routing':{}}):
   r,c=self.go('Sinh viên K69 chương trình chuẩn phải đóng bao nhiêu tiền cho một tín chỉ học lại trong năm học 2024–2025?');self.assertIn('869.000',r['answer']);self.assertNotIn('869000',json.dumps(c))
   r,c=self.go('Nếu học lại một môn 4 tín chỉ thì hết bao nhiêu tiền?',c);self.assertIn('3.476.000',r['answer']);self.assertIn('fee_calculator',r['metadata']['workflow_tools'])
   r,c=self.go('Thế sang năm học 2025–2026 thì sao?',c);self.assertIn('924.000',r['answer'])
   r,c=self.go('Nếu học lại một môn 4 tín chỉ thì hết bao nhiêu tiền?',c);self.assertIn('3.696.000',r['answer'])
   r,c=self.go('Nếu học lại một môn 4 tín chỉ thì hết bao nhiêu tiền?');self.assertEqual(c['topic'],'fee_pending');self.assertIn('Không cần mã sinh viên',r['answer'])
   self.assertIsNone(self.go('Sinh viên K69 chương trình chuẩn học lại bao nhiêu tiền năm học 2024–2025, có miễn giảm không?'))
 def test_load(self):
  with patch('advisor_agent.pinned',return_value=LOAD_SOURCE):
   r,c=self.go('Sinh viên có GPA thấp thì bị hạn chế đăng ký học như thế nào?');self.assertIn('18 tín chỉ',r['answer'])
   r,c=self.go('Nếu CPA của em ấy trên 2 nhưng GPA kỳ trước chỉ 1,8 thì sao?',c);self.assertIn('1.8',r['answer']);self.assertIn('CPA tích lũy',r['answer']);self.assertIn('18 tín chỉ',r['answer'])
   r,c=self.go('Sinh viên K71 có GPA thấp thì bị hạn chế đăng ký học như thế nào?');self.assertNotIn('18 tín chỉ',r['answer'])
 def test_api_stream_same_product_mode(self):
  calls=[]
  def dispatch(req):calls.append(req.question);return {'answer':'NCKH unrelated raw source','routing':{'risk_tier':'RED' if 'ngoại lệ' in req.question else 'GREEN'},'metadata':{'engine_mode':'KNOWLEDGE_EXCERPTS'}}
  s=SimpleNamespace(app=FastAPI(),_get_active_roster=lambda:self.roster,_router=SimpleNamespace(route_decision=lambda q:SimpleNamespace(risk_tier='RED' if 'ngoại lệ' in q else 'GREEN')))
  add_conversation(s,dispatch,Request,self.root)
  handler=next(r.endpoint for r in s.app.routes if r.path=='/api/advisor/chat');install_stream(s.app,handler,interval=0)
  client=TestClient(s.app)
  def ask(q,token=None,stream=False,experience='advisor'):
   r=client.post('/api/advisor/chat'+('/stream' if stream else ''),json={'question':q,'context_token':token,'experience':experience});self.assertEqual(r.status_code,200);return json.loads(r.text.splitlines()[-1])['data'] if stream else r.json()
  a=ask('Phân tích tình hình học tập của lớp hiện tại',stream=True);self.assertTrue(a['context_token']);self.assertIn('99000001',a['answer'])
  b=ask('Chọn 3 sinh viên cần ưu tiên và giải thích lý do.',a['context_token'],True);self.assertIn('99000003',b['answer']);self.assertNotIn('99000004',b['answer']);self.assertNotIn('99000001',ask('Chọn 3 sinh viên cần ưu tiên và giải thích lý do.',a['context_token']+'x',True)['answer'])
  a=ask('Một câu hỏi chưa có căn cứ');self.assertNotIn('NCKH',a['answer']);self.assertIsNone(a['context_token']);self.assertTrue(a['metadata']['product_fallback_blocked']);self.assertIn('NCKH',ask('Một câu hỏi chưa có căn cứ',experience=None)['answer']);self.assertEqual(ask('Xin ngoại lệ')['routing']['risk_tier'],'RED')
 def test_public_draft_and_scope(self):
  self.assertIsNone(self.go('Viết thông báo chung cho cả lớp'))
  r,c=self.go('Phân tích tình hình lớp K70 để tư vấn');self.assertNotIn('99000001',r['answer'])
  r,c=self.go('Phân tích tình hình học tập của lớp hiện tại rồi công khai danh sách lên nhóm lớp');self.assertNotIn('99000001',r['answer'])
if __name__=='__main__':unittest.main()
