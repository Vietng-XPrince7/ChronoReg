import unittest,re,json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from conversation import add_conversation
from stream_chat import install_stream
from test_quality_routes import Request
from advisor_agent import route

class ContinuationTests(unittest.TestCase):
 def setUp(self):
  self.root=Path('.'); self.roster={'class_short':'K69-DEMO','cohort':'QH-2024 (K69)','semester':'2025.1','students':[{'student_id':'99000001','gpa_semester':1.2,'owed_credits':30,'drl':60},{'student_id':'99000002','gpa_semester':1.4,'owed_credits':22,'drl':65}],'courses':[]}
 def go(self,q,old=None,explicit=None,classified=None):return route(q,old or {},explicit,classified,self.roster,self.root)
 def test_private_draft_revision(self):
  r,c=self.go('Soạn email mời sinh viên 99000001 đến trao đổi về tình hình học tập.');self.assertEqual(c['student'],'99000001');self.assertNotIn('99000001',r['answer']);self.assertIn('Cảm ơn em',r['answer']);before=len(r['answer'])
  r,c=self.go('Viết ngắn gọn hơn, giọng thân thiện, không gây áp lực.',c);self.assertLess(len(r['answer']),before);self.assertEqual(c['student'],'99000001');self.assertEqual(c['format'],'email');self.assertIn('thời gian thuận tiện',r['answer']);self.assertEqual(c['tone'],'friendly')
  r,c=self.go('Chuyển sang tin nhắn, giọng trang trọng.',c);self.assertNotIn('Tiêu đề',r['answer']);self.assertEqual(c['tone'],'formal');self.assertEqual(c['format'],'message')
  r,c=self.go('Bây giờ viết thông báo chung cho cả lớp, không tiết lộ thông tin cá nhân.',c);self.assertEqual(c['audience'],'class');self.assertNotIn('student',c);self.assertNotIn('99000001',r['answer']);self.assertIn('Các em',r['answer'])
 def test_scope_changes(self):
  _,c=self.go('Soạn email mời sinh viên 99000001 trao đổi học tập.');r,k=self.go('Viết ngắn hơn cho 99000002',c,explicit='99000001');self.assertFalse(k);self.assertIn('không khớp',r['answer']);self.assertIsNone(self.go('Sửa điểm học phần',c));self.assertIsNone(self.go('Viết ngắn gọn quy chế học phí',c));self.roster['students'][0]['owed_credits']=31;r,k=self.go('Viết ngắn hơn',c);self.assertFalse(k);self.assertIn('hồ sơ đã thay đổi',r['answer'])
 def test_missing_fee_context_resume(self):
  r,c=self.go('Một môn 4 tín chỉ học lại hết bao nhiêu tiền?');self.assertEqual(c['topic'],'fee_pending');self.assertEqual(c['fee']['quantity'],4);self.assertIn('năm học',r['answer']);self.assertIn('Không cần mã sinh viên',r['answer']);self.assertIsNone(self.go('Phân tích CPA của sinh viên',c));
  r,c=self.go('K69',c);self.assertEqual(c['fee']['cohort'],2024);self.assertEqual(c['fee']['quantity'],4)
  def lookup(root,q):return {'answer':'• Học lại, cải thiện điểm (đồng/tín chỉ): 924.000 đồng.','path':'fixture.md','sha256':'test'}
  with patch('tuition.lookup_tuition',side_effect=lookup),patch('advisor_agent.source_table',side_effect=lambda root,v:{'answer':v['answer'],'metadata':{},'routing':{}}):
   r,c=self.go('Chương trình chuẩn năm học 2025–2026',c);self.assertEqual(c['topic'],'fee');self.assertIn('3.696.000',r['answer']);self.assertIn('fee_calculator',r['metadata']['workflow_tools'])
 def test_agenda_revision(self):
  r,c=self.go('Lập chương trình buổi tư vấn lớp 60 phút và soạn thông báo mời sinh viên.');self.assertIn('Thông báo mời tham gia',r['answer']);r,c=self.go('Rút còn 25 phút',c);self.assertEqual(sum(map(int,re.findall(r'\b(\d+) phút',r['answer']))),25);self.assertNotIn('Thông báo mời tham gia',r['answer']);self.assertNotIn('em đã rà',r['answer']);self.assertTrue(c['draft'])
 def test_signed_stream(self):
  s=SimpleNamespace(app=FastAPI(),_get_active_roster=lambda:self.roster,_router=SimpleNamespace(route_decision=lambda q:SimpleNamespace(risk_tier='GREEN')))
  def dispatch(req):return {'answer':'unrelated excerpt','routing':{'risk_tier':'GREEN'},'metadata':{'engine_mode':'KNOWLEDGE_EXCERPTS'}}
  add_conversation(s,dispatch,Request,self.root);h=next(r.endpoint for r in s.app.routes if r.path=='/api/advisor/chat');install_stream(s.app,h,interval=0);c=TestClient(s.app)
  def ask(q,token=None):
   r=c.post('/api/advisor/chat/stream',json={'question':q,'context_token':token,'experience':'advisor'});self.assertEqual(r.status_code,200);events=[json.loads(x) for x in r.text.splitlines()];d=events[-1]['data'];self.assertEqual(''.join(x['text'] for x in events if x['event']=='delta'),d['answer']);return d
  a=ask('Soạn email mời sinh viên 99000001 trao đổi học tập');b=ask('Viết ngắn gọn hơn, giọng thân thiện',a['context_token']);self.assertIn('thời gian thuận tiện',b['answer']);self.assertLess(len(b['answer']),len(a['answer']));bad=ask('Viết ngắn gọn hơn, giọng thân thiện',a['context_token']+'x');self.assertNotIn('thời gian thuận tiện',bad['answer']);self.assertIsNone(bad['context_token'])
if __name__=='__main__':unittest.main()
