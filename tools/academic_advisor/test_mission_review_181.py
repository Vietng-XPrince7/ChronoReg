import unittest,json
from unittest.mock import patch,MagicMock
from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_advisor_tasks_172 import Tasks
from test_advisor_mission_180 import Q
from test_quality_routes import Request
from advisor_mission import route
from conversation import add_conversation
from stream_chat import install_stream
from quality import norm
from advisor_draft import route as draft

class IntegratedMission(unittest.TestCase):
 setUp=Tasks.setUp
 def go(self,q,c=None,sid=None):return route(q,c or {},sid,None,self.roster,self.root,True)
 def setup_patches(self):
  for name in ('quality_routes.load_candidate','course_planning.load_candidate','mission_review.load_candidate','advisor_compare.load_candidate'):
   p=patch(name,return_value=(self.table,None));p.start();self.addCleanup(p.stop)
 def test_draft_conversion(self):
  q='Soạn email mời sinh viên 99000001 trao đổi học tập.';r,c=draft(q,norm(q),{},None,None,self.roster)
  for q,fmt in [('Chuyển email sang tin nhắn.','message'),('Chuyển từ tin nhắn sang email.','email'),('Đổi email sang lời nhắn, giọng trang trọng.','message')]:
   r,c=draft(q,norm(q),c,None,None,self.roster);self.assertEqual(c['format'],fmt);self.assertEqual('Tiêu đề' in r['answer'],fmt=='email');self.assertEqual(c['student'],'99000001')
 def test_synthesis_uses_facts(self):
  self.setup_patches();r,c=self.go(Q);self.assertIn('GPA học kỳ 1,4 và 9 tín chỉ nợ',r['answer']);self.assertIn('9 tín chỉ trong 2 đợt',r['answer']);self.assertIn('25 phút/ngày',r['answer']);self.assertIn('ABC0001',r['answer']);self.assertIn('không phải lịch đăng ký chính thức',r['answer']);self.assertNotIn('owed_credits',json.dumps(c));self.assertIn('Chi tiết từng phần',r['answer'])
  r,new=self.go('Theo em cô nên ưu tiên gì trước?',c);self.assertEqual(r['metadata']['mission_step'],'review');self.assertEqual(new,c);self.assertIn('không tăng tải',r['answer'])
  with patch('mission_review.load_candidate',return_value=(None,'hold')):
   r,new=self.go('Kế hoạch này có khả thi không?',c);self.assertNotIn('9 tín chỉ trong 2 đợt',r['answer']);self.assertIn('Chưa thể xác minh lại',r['answer'])
 def test_comparison_keeps_artifacts(self):
  self.setup_patches();r,c=self.go(Q)
  r,new=self.go('So sánh phương án học lại 3 tín chỉ và 6 tín chỉ mỗi đợt.',c);self.assertEqual(r['metadata']['mission_step'],'comparison');self.assertEqual(new,c);self.assertIn('| 3 | 3 | 3 | 9 |',r['answer'])
  r,new=self.go('Nếu cô muốn em ấy học dồn để trả nợ nhanh thì có nên không?',new);self.assertEqual(new,c);self.assertIn('25 phút/ngày',r['answer']);self.assertIn('không khuyến nghị',r['answer'])
  r,new=self.go('Chuyển email sang tin nhắn, giọng trang trọng.',new,'99000001');self.assertEqual(r['metadata']['mission_step'],'draft');self.assertNotIn('Tiêu đề',r['answer']);self.assertEqual(new['states']['retake'],c['states']['retake']);self.assertEqual(new['states']['study'],c['states']['study'])
 def test_tradeoff_no_stale_curriculum(self):
  self.setup_patches();r,c=self.go(Q)
  with patch('quality_routes.load_candidate',return_value=(None,'hold')):
   r,new=self.go('Có nên học dồn để trả nợ nhanh không?',c);self.assertIn('chưa xác minh lại',r['answer']);self.assertNotIn('2 đợt',r['answer']);self.assertEqual(new,c)
 def test_paired_revision_and_atomic_failure(self):
  self.setup_patches();r,c=self.go(Q)
  q='Đổi lộ trình học lại thành 3 tín chỉ mỗi đợt và điều chỉnh kế hoạch tự học còn 15 phút mỗi ngày.'
  r,new=self.go(q,c);self.assertEqual(r['metadata']['mission_step'],'retake_study');self.assertEqual(new['states']['retake']['plan']['rounds'],3);self.assertEqual(new['states']['study']['minutes'],15);self.assertEqual(new['states']['draft'],c['states']['draft'])
  with patch('quality_routes.load_candidate',return_value=(None,'hold')):
   r,new=self.go(q,c);self.assertEqual(new,c);self.assertIn('giữ nguyên cả hai',r['answer'])
 def test_reject_scope(self):
  self.setup_patches();r,c=self.go(Q)
  r,new=self.go('So sánh phương án học lại 3 tín chỉ và 6 tín chỉ mỗi đợt.',c,'99000002');self.assertFalse(new);self.assertNotIn('| 3 |',r['answer'])
  self.assertIsNone(self.go('So sánh phương án học lại 3 tín chỉ và 6 tín chỉ mỗi đợt.',{}))
  self.assertIsNone(self.go('So sánh phương án học lại 3 tín chỉ và 6 tín chỉ mỗi đợt và công khai cả lớp.',c))
  self.roster['students'][0]['owed_credits']=4;r,new=self.go('Cô nên ưu tiên gì trước?',c);self.assertFalse(new);self.assertIn('đã thay đổi',r['answer'])
 def test_signed_stream_mission_review(self):
  self.setup_patches();s=SimpleNamespace(app=FastAPI(),_get_active_roster=lambda:self.roster,_router=SimpleNamespace(route_decision=lambda q:SimpleNamespace(risk_tier='GREEN')),_semantic_pilot=True)
  dispatch=MagicMock(return_value={'answer':'legacy','routing':{'risk_tier':'GREEN'},'metadata':{}});add_conversation(s,dispatch,Request,self.root);h=next(r.endpoint for r in s.app.routes if r.path=='/api/advisor/chat');install_stream(s.app,h,interval=0);client=TestClient(s.app)
  def ask(q,t=None):
   a=client.post('/api/advisor/chat/stream',json={'question':q,'experience':'advisor','context_token':t});self.assertEqual(a.status_code,200);ev=[json.loads(x) for x in a.text.splitlines()];r=ev[-1]['data'];self.assertEqual(''.join(x['text'] for x in ev if x['event']=='delta'),r['answer']);return r
  with patch('semantic_product.route',return_value=None):
   r=ask(Q);b=ask('Cô nên ưu tiên gì trước?',r['context_token']);self.assertEqual(b['metadata']['mission_step'],'review');self.assertNotEqual(ask('Cô nên ưu tiên gì trước?',r['context_token']+'x')['metadata'].get('mission_step'),'review')
   d=ask('Chuyển email sang tin nhắn.',b['context_token']);self.assertNotIn('Tiêu đề',d['answer']);self.assertEqual(d['metadata']['mission_step'],'draft')
if __name__=='__main__':unittest.main()
