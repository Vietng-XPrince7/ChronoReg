import unittest,json
from unittest.mock import patch,MagicMock
from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
import test_mission_review_181 as fixtures
import test_advisor_tasks_172 as tasks
from test_advisor_mission_180 import Q
from test_quality_routes import Request
from advisor_mission import route
from advisor_composer import clarify
from conversation import add_conversation
from stream_chat import install_stream
from mission_intent import plan,checked

class ReviewViews(unittest.TestCase):
 setUp=tasks.Tasks.setUp
 setup_patches=fixtures.IntegratedMission.setup_patches
 def go(self,q,c=None,sid=None):return route(q,c or {},sid,None,self.roster,self.root,True)
 def test_distinct_goals_and_state(self):
  self.setup_patches();r,c=self.go(Q)
  for question,view,expected in [('Tóm tắt lại kế hoạch.','summary','25 phút/ngày'),('Kế hoạch này có khả thi không?','feasibility','chưa đủ căn cứ'),('Rủi ro của phương án này là gì?','risks','CTĐT tham khảo chưa duyệt'),('Bước tiếp theo của phương án này?','next_steps','một mục tiêu nhỏ')]:
   r,new=self.go(question,c);self.assertEqual(new,c);self.assertEqual(r['metadata']['review_views'],[view]);self.assertIn(expected,r['answer'])
  r,new=self.go('Tóm tắt và đánh giá rủi ro của phương án này.',c);self.assertEqual(r['metadata']['review_views'],['summary','risks']);self.assertEqual(new,c)
 def test_no_model_for_known_view(self):
  self.setup_patches();r,c=self.go(Q)
  with patch('mission_intent.infer') as model:
   r,new=self.go('Phương án này có phù hợp không?',c);model.assert_not_called();self.assertEqual(r['metadata']['review_planner'],'explicit_review')
 def test_model_review_and_untrusted_output(self):
  self.setup_patches();r,c=self.go(Q)
  q='Em nhận xét thế nào về phương án này?'
  with patch('mission_intent.infer',return_value=['feasibility','risks']) as model:
   r,new=self.go(q,c);model.assert_called_once_with(q);self.assertEqual(new,c);self.assertEqual(r['metadata']['review_planner'],'local_model_review');self.assertEqual(r['metadata']['review_views'],['feasibility','risks']);self.assertIn('chưa đủ căn cứ',r['answer'])
  with patch('mission_intent.infer',return_value=['send']):
   r,new=self.go(q,c);self.assertEqual(new,c);self.assertNotIn('review_views',r['metadata']);self.assertIn('muốn em',r['answer'])
  for obj in ({'views':['summary','summary']},{'views':['summary'],'student':'99000002'},{'views':['execute']},{'views':[]},None):
   with self.assertRaises(ValueError):checked(obj)
 def test_no_model_for_new_constraint_or_mutation(self):
  for q in ('Đánh giá phương án này cho sinh viên khác.','Đánh giá phương án này rồi gửi email.','Đánh giá phương án này với 12 tín chỉ.','Đánh giá phương án này, không nhắc rủi ro.','Đánh giá phương án này và sửa kế hoạch.'):
   with patch('mission_intent.infer') as model:
    self.assertEqual(plan(q,True),([],None));model.assert_not_called()
 def test_scope_check_and_fresh_source(self):
  self.setup_patches();r,c=self.go(Q)
  with patch('mission_intent.infer') as model:
   r,new=self.go('Em nhận xét thế nào về phương án này?',c,'99000002');model.assert_not_called();self.assertFalse(new)
  with patch('mission_review.load_candidate',return_value=(None,'hold')):
   r,new=self.go('Kế hoạch này có khả thi không?',c);self.assertIn('Chưa thể xác minh lại',r['answer']);self.assertNotIn('9 tín chỉ xếp được',r['answer']);self.assertEqual(new,c)
 def test_new_session(self):
  self.assertIn('phiên này chưa có',clarify('Tóm tắt lại kế hoạch.',{}));self.assertIsNone(clarify('Tóm tắt lại quy chế đào tạo.',{}))
 def test_streaming_readonly_model_review(self):
  self.setup_patches();s=SimpleNamespace(app=FastAPI(),_get_active_roster=lambda:self.roster,_router=SimpleNamespace(route_decision=lambda q:SimpleNamespace(risk_tier='GREEN')),_semantic_pilot=True)
  dispatch=MagicMock(return_value={'answer':'legacy','routing':{'risk_tier':'GREEN'},'metadata':{}});add_conversation(s,dispatch,Request,self.root);h=next(r.endpoint for r in s.app.routes if r.path=='/api/advisor/chat');install_stream(s.app,h,interval=0);client=TestClient(s.app)
  def send(q,t=None):
   a=client.post('/api/advisor/chat/stream',json={'question':q,'experience':'advisor','context_token':t});self.assertEqual(a.status_code,200);ev=[json.loads(x) for x in a.text.splitlines()];r=ev[-1]['data'];self.assertEqual(''.join(x['text'] for x in ev if x['event']=='delta'),r['answer']);return r
  with patch('semantic_product.route',return_value=None),patch('mission_intent.infer',return_value=['risks']):
   a=send(Q);b=send('Em nhận xét thế nào về phương án này?',a['context_token']);self.assertEqual(b['metadata']['review_planner'],'local_model_review');self.assertIn('Điểm cần kiểm tra',b['answer']);c=send('Tóm tắt lại kế hoạch.',b['context_token']);self.assertIn('25 phút/ngày',c['answer']);d=send('Tóm tắt lại kế hoạch.',b['context_token']+'x');self.assertIn('phiên này chưa có',d['answer']);self.assertIsNone(d['context_token'])
 def test_extension_keeps_artifacts_and_pending(self):
  self.setup_patches();r,c=self.go('Phân tích hồ sơ sinh viên 99000001 và lập lộ trình học lại tối đa 6 tín chỉ mỗi đợt.')
  r,new=self.go('Bổ sung kế hoạch tự học một tuần, mỗi ngày 20 phút.',c);self.assertEqual(r['metadata']['mission_planner'],'explicit_extension');self.assertEqual(new['states']['retake'],c['states']['retake']);self.assertEqual(new['states']['study']['minutes'],20)
  r,ext=self.go('Bổ sung soạn email mời trao đổi học tập.',new);self.assertEqual(ext['states']['study'],new['states']['study']);self.assertEqual(ext['states']['draft']['student'],'99000001')
  r,again=self.go('Bổ sung kế hoạch tự học một tuần, mỗi ngày 25 phút.',ext);self.assertEqual(again,ext);self.assertIn('đã có',r['answer'])
  r,wrong=self.go('Bổ sung kế hoạch tự học một tuần, mỗi ngày 20 phút.',c,'99000002');self.assertFalse(wrong)
 def test_extension_without_minutes_pending(self):
  self.setup_patches();r,c=self.go('Phân tích hồ sơ sinh viên 99000001 và lập lộ trình học lại tối đa 6 tín chỉ mỗi đợt.')
  r,new=self.go('Bổ sung kế hoạch tự học.',c);self.assertEqual(r['metadata']['mission_completed'],[]);self.assertIn('study',new['pending']);self.assertEqual(new['states'],c['states'])
  r,new=self.go('Điều chỉnh kế hoạch tự học còn 20 phút mỗi ngày.',new);self.assertEqual(new['states']['study']['minutes'],20);self.assertNotIn('study',new['pending']);self.assertEqual(new['states']['retake'],c['states']['retake'])
