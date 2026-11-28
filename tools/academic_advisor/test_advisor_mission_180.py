import json,unittest
from unittest.mock import patch,MagicMock
from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_advisor_tasks_172 import Tasks
from test_quality_routes import Request
from advisor_mission import route,checked_plan
from conversation import add_conversation
from stream_chat import install_stream
from advisor_composer import clarify
Q='Phân tích hồ sơ sinh viên 99000001, lập lộ trình học lại tối đa 6 tín chỉ mỗi đợt và lập kế hoạch tự học một tuần, mỗi ngày 25 phút; soạn email mời trao đổi học tập.'
STEPS=['profile','retake','study','draft']
class Mission(unittest.TestCase):
 setUp=Tasks.setUp
 def go(self,q,p=None,enabled=False):return route(q,p or {},None,None,self.roster,self.root,enabled)
 def test_plan_and_revision(self):
  with patch('quality_routes.load_candidate',return_value=(self.table,None)),patch('course_planning.load_candidate',return_value=(self.table,None)),patch('advisor_mission.infer',return_value={'steps':STEPS}) as model:
   r,c=self.go(Q,enabled=True);model.assert_not_called();self.assertEqual(r['metadata']['mission_planner'],'explicit_plan');self.assertEqual(r['metadata']['mission_completed'],STEPS);self.assertEqual(r['metadata']['mission_pending'],[]);self.assertIn('**Tín chỉ nợ:** 9',r['answer']);self.assertIn('2 đợt',r['answer']);self.assertEqual(r['answer'].count('| 25 phút |'),7);self.assertIn('Tiêu đề',r['answer']);self.assertEqual(c['states']['retake']['plan']['rounds'],2)
   self.assertNotIn('owed_credits',json.dumps(c));self.assertNotIn('Dạ cô',json.dumps(c));self.assertNotIn('answer',json.dumps(c))
   r,c=self.go('Đổi lộ trình học lại thành 3 tín chỉ mỗi đợt.',c);self.assertEqual(c['states']['retake']['plan']['rounds'],3);self.assertEqual(c['states']['study']['minutes'],25);self.assertNotIn('Tiêu đề',r['answer']);self.assertEqual(r['metadata']['mission_step'],'retake')
   r,c=self.go('Điều chỉnh kế hoạch tự học còn 15 phút mỗi ngày.',c);self.assertEqual(c['states']['study']['minutes'],15);self.assertEqual(c['states']['retake']['plan']['rounds'],3)
   r,c=self.go('Rút gọn email, giữ tiêu đề, giọng thân thiện.',c);self.assertTrue(c['states']['draft']['short']);self.assertIn('Tiêu đề',r['answer']);self.assertEqual(c['states']['study']['minutes'],15)
   self.roster['students'][0]['owed_credits']=5;r,c=self.go('Đổi lộ trình học lại thành 6 tín chỉ mỗi đợt.',c);self.assertIn('đã thay đổi',r['answer']);self.assertFalse(c)
 def test_invalid_model_and_scope(self):
  for obj in ({'steps':['retake','profile']},{'steps':['profile','retake','study','draft','send']},{'steps':['profile','retake','draft']},{'steps':['profile','profile','retake','study','draft']},{'steps':STEPS,'student':'99000002'}):
   with self.assertRaises(ValueError):checked_plan(obj,STEPS,STEPS)
  with patch('quality_routes.load_candidate',return_value=(self.table,None)),patch('course_planning.load_candidate',return_value=(self.table,None)),patch('advisor_mission.infer',return_value={'steps':['profile','draft']}):
   r,c=self.go(Q,enabled=True);self.assertEqual(r['metadata']['mission_planner'],'explicit_plan');self.assertEqual(r['metadata']['mission_completed'],STEPS)
  self.assertIsNone(self.go(Q+' Công khai điểm lên nhóm lớp.'))
  self.assertIsNone(self.go(Q+' Bỏ môn ABC0001.'))
  self.assertIsNone(self.go(Q+' So sánh với sinh viên 99000002.'))
  r,c=self.go(Q.replace('99000001','99000009'));self.assertNotIn('Tín chỉ nợ:',r['answer']);self.assertFalse(c)
  r,c=self.go(Q.replace('99000001','99000001 và 99000002'));self.assertFalse(c)
 def test_broad_optional_choice(self):
  q='Cô cần chuẩn bị toàn diện buổi gặp riêng sinh viên 99000001.'
  with patch('quality_workflows.load_candidate',return_value=(self.table,None)),patch('advisor_mission.infer',return_value={'steps':['profile','priorities','meeting']}):
   r,c=self.go(q,enabled=True);self.assertEqual(r['metadata']['mission_completed'],['profile','priorities','meeting']);self.assertIn('Việc nên ưu tiên',r['answer']);self.assertNotIn('Tiêu đề',r['answer']);self.assertEqual(r['metadata']['mission_planner'],'local_model_plan')
   with patch('advisor_mission.infer',return_value={'steps':['profile','draft']}):
    r,c=self.go(q,enabled=True);self.assertEqual(r['metadata']['mission_planner'],'bounded_fallback');self.assertEqual(set(r['metadata']['mission_completed']),{'profile','meeting','priorities'})
 def test_missing_prerequisites(self):
  with patch('quality_routes.load_candidate',return_value=(None,'chưa có CTĐT')):
   r,c=self.go('Phân tích hồ sơ sinh viên 99000001 và lập lộ trình học lại tối đa 6 tín chỉ mỗi đợt theo tiên quyết.');self.assertIn('retake',r['metadata']['mission_pending']);self.assertNotIn('retake',r['metadata']['mission_completed']);self.assertIn('chưa thể xếp lịch',r['answer'])
 def test_pending_and_isolation(self):
  with patch('quality_routes.load_candidate',return_value=(self.table,None)):
   r,c=self.go('Phân tích hồ sơ sinh viên 99000001 và lập lộ trình học lại theo tiên quyết.');self.assertEqual(c['pending'],['retake']);self.assertIn('Cần xác nhận trần tín chỉ',r['answer'])
   r,c=self.go('Đổi lộ trình học lại thành 6 tín chỉ mỗi đợt.',c);self.assertEqual(c['pending'],[]);self.assertIn('2 đợt',r['answer'])
   self.assertIsNone(self.go('Đổi lộ trình học lại thành 6 tín chỉ mỗi đợt.'))
  self.assertIn('điều kiện nào',clarify('Thế nếu điểm bộ phận là 5?',{}))
 def test_stream_and_research(self):
  s=SimpleNamespace(app=FastAPI(),_get_active_roster=lambda:self.roster,_router=SimpleNamespace(route_decision=lambda q:SimpleNamespace(risk_tier='RED' if 'ngoại lệ' in q else 'GREEN')),_semantic_pilot=True)
  dispatch=MagicMock(return_value={'answer':'legacy','routing':{'risk_tier':'GREEN'},'metadata':{}})
  add_conversation(s,dispatch,Request,self.root);h=next(r.endpoint for r in s.app.routes if r.path=='/api/advisor/chat');install_stream(s.app,h,interval=0);client=TestClient(s.app)
  def ask(q,t=None,mode='advisor',force=None):
   r=client.post('/api/advisor/chat/stream',json={'question':q,'experience':mode,'context_token':t,'force_engine':force});self.assertEqual(r.status_code,200);events=[json.loads(x) for x in r.text.splitlines()];d=events[-1]['data'];self.assertEqual(''.join(x['text'] for x in events if x['event']=='delta'),d['answer']);return d
  with patch('quality_routes.load_candidate',return_value=(self.table,None)),patch('course_planning.load_candidate',return_value=(self.table,None)),patch('advisor_mission.infer',return_value={'steps':STEPS}),patch('semantic_product.route',return_value=None):
   a=ask(Q);self.assertEqual(a['metadata']['mission_completed'],STEPS);self.assertTrue(a['context_token']);b=ask('Rút gọn email, giữ tiêu đề.',a['context_token']);self.assertEqual(b['metadata']['mission_step'],'draft');self.assertNotIn('Tiêu đề',ask('Rút gọn email, giữ tiêu đề.',a['context_token']+'x')['answer']);self.assertEqual(ask(Q,force='continual_lora')['answer'],'legacy');self.assertEqual(ask(Q+' xin ngoại lệ')['answer'],'legacy')
if __name__=='__main__':unittest.main()
