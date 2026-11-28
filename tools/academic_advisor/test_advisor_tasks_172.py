import unittest,re,json
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
from conversation import add_conversation
from stream_chat import install_stream
from test_quality_routes import Request
from advisor_agent import route
from quality_workflows import snapshot

SOURCE={'path':'fixture.md','sha256':'fixture','source_url':'https://example.invalid','answer':'2. Việc rút bớt học phần chỉ được chấp nhận trong 2 tuần kể từ đầu học kỳ chính, 1 tuần kể từ đầu học kỳ phụ và được trả lại học phí.'}
class Tasks(unittest.TestCase):
 def setUp(self):
  self.root=Path('.');self.roster={'class_short':'K69-DEMO','cohort':'QH-2024 (K69)','semester':'2025.1','students':[{'student_id':'99000001','gpa_semester':1.4,'owed_credits':9,'accumulated_credits':57,'drl':68,'bang_diem':[{'ma_mon':c,'dat':False} for c in ['ABC0001','ABC0002','ABC0003']]},{'student_id':'99000002','owed_credits':15}], 'courses':[{'ma_mon':c,'so_tin_chi':3} for c in ['ABC0001','ABC0002','ABC0003']]}
  self.table={'ABC0001':(3,()),'ABC0002':(3,('ABC0001',)),'ABC0003':(3,())}
 def go(self,q,p=None,explicit=None,classified=None):return route(q,p or {},explicit,classified,self.roster,self.root)
 def test_profile_multi_and_plan(self):
  r,c=self.go('Sinh viên demo 99000001 còn bao nhiêu tín chỉ nợ và CPA hiện có là bao nhiêu?');self.assertIn('**Tín chỉ nợ:** 9',r['answer']);self.assertIn('chưa xác nhận CPA',r['answer']);self.assertNotIn('1.4',r['answer']);self.assertEqual(c['student'],'99000001');self.assertNotIn('owed_credits',json.dumps(c))
  with patch('quality_routes.load_candidate',return_value=(self.table,None)):
   r,c=self.go('Với em này, chia các môn còn nợ thành các đợt không quá 6 tín chỉ, theo tiên quyết.',c);self.assertEqual(c['plan']['rounds'],2);self.assertIn('9 tín chỉ',r['answer'])
   r,c=self.go('Nếu chỉ có thể học thêm 3 tín chỉ mỗi đợt thì thay đổi thế nào?',c);self.assertIn('2 → 3',r['answer']);self.assertEqual(c['plan']['rounds'],3)
   self.roster['students'][0]['owed_credits']=6;r,c=self.go('Đổi thành 6 tín chỉ mỗi đợt',c);self.assertIn('đã thay đổi',r['answer']);self.assertFalse(c)
 def test_profile_scope_and_transfer(self):
  r,c=self.go('Sinh viên 99000001 có bao nhiêu tín chỉ tích lũy và GPA học kỳ?');self.assertIn('57',r['answer']);self.assertIn('1,4',r['answer'])
  r,c=self.go('Em ấy có bao nhiêu điểm rèn luyện?',c);self.assertIn('68',r['answer']);self.assertEqual(c['student'],'99000001')
  r,c=self.go('Sinh viên 99000002 còn bao nhiêu tín chỉ nợ?',c,explicit='99000001');self.assertFalse(c);self.assertNotIn('15',r['answer'])
  self.assertIsNone(self.go('So sánh tín chỉ nợ của 99000001 và 99000002'))
 def test_withdrawal_context(self):
  with patch('advisor_tasks.pinned',return_value=SOURCE):
   r,c=self.go('Sinh viên có thể xin rút học phần trong học kỳ chính đến thời điểm nào theo QĐ 3626?');self.assertIn('2 tuần',r['answer']);self.assertEqual(c['topic'],'withdrawal')
   r,c=self.go('Còn học kỳ phụ?',c);self.assertIn('1 tuần',r['answer']);self.assertNotIn('2 tuần',r['answer']);self.assertTrue(r['metadata']['source_url'])
   r,c=self.go('Nếu văn bản đó chưa được xác nhận cho khóa K71 thì sao?',c);self.assertIn('chưa đủ căn cứ',r['answer']);self.assertNotIn('1 tuần',r['answer']);self.assertEqual(c['cohort'],2026)
  self.assertIsNone(self.go('Còn học kỳ phụ?'))
  with patch('advisor_tasks.pinned',return_value=None):
   r,c=self.go('Thời hạn rút học phần học kỳ phụ?');self.assertNotIn('1 tuần',r['answer'])
 def test_study_week_and_revision(self):
  old={'kind':'advisor_task','topic':'meeting','scope':snapshot(self.roster),'mssv':'99000001','topics':['time']}
  with patch('course_planning.load_candidate',return_value=(self.table,None)):
   r,c=self.go('Nếu em chỉ có 45 phút tự học mỗi ngày, đề xuất phương án trong một tuần.',old);self.assertEqual(c['minutes'],45);self.assertEqual(r['answer'].count('| 45 phút |'),7);self.assertIn('315 phút/tuần',r['answer']);self.assertIn('ca',r['answer']);self.assertIn('ABC0001',r['answer'])
   r,c=self.go('Cô thấy kế hoạch này vẫn hơi nặng, em điều chỉnh lại giúp cô.',c);self.assertEqual(c['minutes'],30);self.assertEqual(r['answer'].count('| 30 phút |'),7)
   r,c=self.go('Chỉ còn 15 phút tự học mỗi ngày, điều chỉnh kế hoạch.',c);self.assertEqual(c['minutes'],15);self.assertEqual(r['answer'].count('| 15 phút |'),7)
  r,c=self.go('Viết lại cho ngắn gọn hơn.');self.assertIn('nội dung nào',r['answer']);self.assertFalse(c)
 def test_horizon_and_calendar_presentation(self):
  from advisor_tasks import calendar_presentation
  old={'kind':'advisor_task','topic':'meeting','scope':snapshot(self.roster),'mssv':'99000001','topics':['time']}
  r,c=self.go('Lập kế hoạch tự học 30 phút mỗi ngày trong 3 ngày.',old);self.assertNotIn('| Ngày |',r['answer']);self.assertIn('7 ngày',r['answer'])
  r={'answer':'Mốc kế hoạch.\nBản PDF người dùng cung cấp có số 1588/KH-ĐHCN ngày 01/08/2025; chữ ký hợp lệ theo pdfsig, chứng thư hết hạn.','metadata':{}}
  calendar_presentation(r);self.assertNotIn('pdfsig',r['answer']);self.assertNotIn('hết hạn',r['answer']);self.assertIn('hết hạn',r['metadata']['source_qualification']);self.assertIn('pdfsig',r['metadata']['source_qualification'])
 def test_stream_inheritance(self):
  s=SimpleNamespace(app=FastAPI(),_get_active_roster=lambda:self.roster,_router=SimpleNamespace(route_decision=lambda q:SimpleNamespace(risk_tier='GREEN')))
  def dispatch(req):return {'answer':'irrelevant source','routing':{'risk_tier':'GREEN'},'metadata':{'engine_mode':'KNOWLEDGE_EXCERPTS'}}
  add_conversation(s,dispatch,Request,self.root);h=next(r.endpoint for r in s.app.routes if r.path=='/api/advisor/chat');install_stream(s.app,h,interval=0);client=TestClient(s.app)
  def ask(q,t=None):
   r=client.post('/api/advisor/chat/stream',json={'question':q,'experience':'advisor','context_token':t});self.assertEqual(r.status_code,200);events=[json.loads(x) for x in r.text.splitlines()];d=events[-1]['data'];self.assertEqual(''.join(x['text'] for x in events if x['event']=='delta'),d['answer']);return d
  with patch('advisor_tasks.pinned',return_value=SOURCE):
   a=ask('Hạn rút học phần học kỳ chính khi nào?');b=ask('Còn học kỳ phụ?',a['context_token']);self.assertIn('1 tuần',b['answer']);self.assertNotIn('1 tuần',ask('Còn học kỳ phụ?',a['context_token']+'x')['answer'])
  a=ask('Sinh viên 99000001 còn bao nhiêu tín chỉ nợ và CPA?');self.assertTrue(a['context_token']);b=ask('Em ấy có bao nhiêu điểm rèn luyện?',a['context_token']);self.assertIn('68',b['answer']);self.assertNotIn('68',ask('Em ấy có bao nhiêu điểm rèn luyện?')['answer'])
if __name__=='__main__':unittest.main()
