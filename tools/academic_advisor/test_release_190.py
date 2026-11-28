"""Release regression: integrated review, scoped pause/resume, and stream isolation.
Synthetic data/model/tuition fixtures; not a live quality benchmark.
"""
import unittest,json
from unittest.mock import patch,MagicMock
from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_mission_review_181 import IntegratedMission
from test_advisor_tasks_172 import Tasks
from test_advisor_mission_180 import Q
from test_quality_routes import Request
from mission_intent import plan,eligible
from quality import norm
from conversation import add_conversation,Context
from stream_chat import install_stream
from advisor_mission import route

class Release(unittest.TestCase):
 setUp=Tasks.setUp
 setup_patches=IntegratedMission.setup_patches
 def go(self,q,c=None):return route(q,c or {},None,None,self.roster,self.root,True)
 def test_review_many_views_once(self):
  self.setup_patches();r,c=self.go(Q)
  with patch('mission_intent.infer',return_value=['summary','priority','feasibility']):
   r,new=self.go('Em nhận xét thế nào về phương án này?',c)
  a=r['answer'];self.assertEqual(new,c);self.assertEqual(a.count('GPA học kỳ 1,4'),1);self.assertEqual(a.count('9 tín chỉ nợ'),1);self.assertEqual(a.count('25 phút/ngày'),1);self.assertIn('chưa đủ căn cứ',a);self.assertIn('Việc nên làm tiếp theo',a);self.assertIn('CTĐT tham khảo chưa duyệt',a);self.assertIn('bản nháp chưa gửi',a);self.assertLess(len(a),1800)
 def test_all_explicit_views(self):
  q='Tóm tắt, đánh giá tính khả thi, rủi ro, ưu tiên và bước tiếp theo của phương án này.'
  with patch('mission_intent.infer') as infer:
   views,mode=plan(q,True);self.assertEqual(set(views),{'summary','priority','feasibility','risks','next_steps'});infer.assert_not_called()
  self.assertTrue(eligible(norm('Em thấy thế nào về phương án này?')))
  self.assertFalse(eligible(norm('Thay phương án này.')))
  self.assertFalse(eligible(norm('Em thay phương án này bằng phương án khác.')))
 def test_missing_information_and_failed_source(self):
  self.setup_patches()
  with patch('advisor_mission.infer',return_value={'steps':['profile','meeting']}):
   r,c=self.go('Cô cần xây dựng phương án hỗ trợ tổng thể cho sinh viên 99000001.')
  r,new=self.go('Phương án này còn hạn chế gì?',c);self.assertEqual(new,c);self.assertIn('Chưa có thời gian tự học thực tế',r['answer']);self.assertIn('lịch mở lớp',r['answer']);self.assertIn('CTĐT đúng khóa',r['answer'])
  r,c=self.go(Q)
  with patch('mission_review.load_candidate',return_value=(None,'hold')):
   r,new=self.go('Tóm tắt và đánh giá rủi ro của phương án này.',c)
   self.assertIn('Chưa thể xác minh lại',r['answer']);self.assertNotIn('xếp được 9 tín chỉ',r['answer']);self.assertEqual(new,c)
 def setup_http(self):
  self.setup_patches();self.now=[1000];self.ctx=Context(key=b'z'*32,ttl=60,clock=lambda:self.now[0]);s=SimpleNamespace(app=FastAPI(),_get_active_roster=lambda:self.roster,_router=SimpleNamespace(route_decision=lambda q:SimpleNamespace(risk_tier='RED' if 'ngoại lệ' in q else 'GREEN')),_semantic_pilot=True)
  def dispatch(req):return {'answer':'legacy','metadata':{},'routing':{'risk_tier':'RED' if 'ngoại lệ' in req.question else 'GREEN'}}
  with patch('conversation.Context',return_value=self.ctx):add_conversation(s,dispatch,Request,self.root)
  h=next(r.endpoint for r in s.app.routes if r.path=='/api/advisor/chat');install_stream(s.app,h,interval=0);self.client=TestClient(s.app)
  def lookup(root,q):return {'answer':'• Học lại, cải thiện điểm (đồng/tín chỉ): '+('924.000' if '2025-2026' in q else '869.000')+' đồng.','path':'fixture.md','sha256':'fixture'}
  def source(root,v):return {'answer':v['answer'],'metadata':{'engine_mode':'SOURCE_TABLE','advisor_category':'REGULATION','source_path':'fixture.md','sha256':'fixture'},'routing':{}}
  for name,side in [('tuition.lookup_tuition',lookup),('advisor_agent.source_table',source)]:
   p=patch(name,side_effect=side);p.start();self.addCleanup(p.stop)
 def ask(self,q,token=None,**kwargs):
  r=self.client.post('/api/advisor/chat/stream',json={'question':q,'experience':'advisor','context_token':token,**kwargs});self.assertEqual(r.status_code,200);events=[json.loads(x) for x in r.text.splitlines()];d=events[-1]['data'];self.assertEqual(''.join(x['text'] for x in events if x['event']=='delta'),d['answer']);return d
 def parked(self):
  a=self.ask(Q);self.assertTrue(a['context_token']);b=self.ask('Sinh viên K69 CTĐT chuẩn, học lại học phần 3 tín chỉ trong năm học 2025–2026 mất bao nhiêu tiền?',a['context_token']);self.assertIn('2.772.000',b['answer']);self.assertNotIn('99000001',b['answer']);d=self.ctx.read(b['context_token']);self.assertEqual(d['topic'],'fee');self.assertEqual(d['parked_mission']['student'],'99000001');self.assertNotIn('owed_credits',json.dumps(d));return b
 def test_switch_public_and_resume(self):
  self.setup_http();b=self.parked();c=self.ask('Còn năm học 2024–2025?',b['context_token']);self.assertIn('2.607.000',c['answer']);self.assertNotIn('99000001',c['answer']);d=self.ask('Quay lại phương án tư vấn vừa rồi.',c['context_token']);self.assertEqual(d['context_resolution']['kind'],'mission_resumed');self.assertIn('25 phút/ngày',d['answer']);self.assertIn('9 tín chỉ',d['answer']);self.assertEqual(self.ctx.read(d['context_token'])['kind'],'advisor_mission');self.assertNotIn('parked_mission',self.ctx.read(d['context_token']))
  e=self.ask('Chuyển email sang tin nhắn.',d['context_token']);self.assertNotIn('Tiêu đề',e['answer']);self.assertEqual(e['metadata']['mission_step'],'draft')
 def test_isolation_tamper_expiry_and_changed_roster(self):
  self.setup_http();b=self.parked();q='Quay lại phương án tư vấn vừa rồi.'
  for token in (None,b['context_token']+'x'):
   r=self.ask(q,token);self.assertIsNone(r['context_token']);self.assertNotIn('9 tín chỉ',r['answer'])
  self.now[0]=1061;r=self.ask(q,b['context_token']);self.assertIsNone(r['context_token']);self.assertNotIn('9 tín chỉ',r['answer'])
  self.now[0]=1001;self.roster['students'][0]['owed_credits']=12;r=self.ask(q,b['context_token']);self.assertIn('đã thay đổi',r['answer']);self.assertIsNone(r['context_token']);self.assertNotIn('9 tín chỉ',r['answer'])
 def test_new_scope_and_forced_clear(self):
  self.setup_http();b=self.parked();r=self.ask('Sinh viên 99000002 còn bao nhiêu tín chỉ nợ?',b['context_token']);self.assertNotIn('parked_mission',self.ctx.read(r['context_token']));self.assertNotIn('9 tín chỉ',r['answer'])
  r=self.ask('Xin ngoại lệ.',b['context_token']);self.assertIsNone(r['context_token']);self.assertEqual(r['routing']['risk_tier'],'RED')
  r=self.ask('Tra quy chế.',b['context_token'],force_engine='continual_lora');self.assertIsNone(r['context_token'])
if __name__=='__main__':unittest.main()
