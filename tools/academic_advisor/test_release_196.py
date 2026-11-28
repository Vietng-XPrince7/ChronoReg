"""Cross-router continuity and source-predicate regression; mocked API/model, no live model."""
import json,unittest
from unittest.mock import patch
from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
from conversation import add_conversation,Context
from stream_chat import install_stream
from test_quality_routes import Request
import test_advisor_tasks_172 as ft
import advisor_bridge as bridge
from quality_workflows import snapshot
from adaptive_counsel import validated

class Continuity(unittest.TestCase):
 def setUp(self):
  f=ft.Tasks();f.setUp();self.roster=f.roster;self.root=f.root;self.table=f.table
  self.ctx=Context(key=b'x'*32,clock=lambda:1000)
  s=SimpleNamespace(app=FastAPI(),_get_active_roster=lambda:self.roster,_router=SimpleNamespace(route_decision=lambda q:SimpleNamespace(risk_tier='RED' if 'ngoại lệ' in q else 'GREEN')),_semantic_pilot=False)
  def dispatch(req):
   if req.mssv=='99000001' and 'trao đổi' in req.question:
    return {'answer':'Chuẩn bị buổi gặp với sinh viên.','routing':{'risk_tier':'GREEN','actual_engine_used':'chrono_rag'},'metadata':{'advisor_category':'STUDENT_STATUS','advisor_intent':'meeting_preparation','engine_mode':'ADVISOR_WORKFLOW','workflow_tools':['scope_check','meeting_preparation'],'roadmap':['meeting'],'advisor_entities':{'mssv':'99000001'}}}
   return {'answer':'fallback','routing':{'risk_tier':'GREEN'},'metadata':{'engine_mode':'KNOWLEDGE_EXCERPTS'}}
  with patch('conversation.Context',return_value=self.ctx):add_conversation(s,dispatch,Request,self.root)
  h=next(r.endpoint for r in s.app.routes if r.path=='/api/advisor/chat');install_stream(s.app,h,interval=0);self.client=TestClient(s.app)
  for name in ('course_planning.load_candidate','mission_review.load_candidate'):
   p=patch(name,return_value=(self.table,None));p.start();self.addCleanup(p.stop)
 def ask(self,q,t=None,**kwargs):
  r=self.client.post('/api/advisor/chat/stream',json={'question':q,'experience':'advisor','context_token':t,**kwargs});self.assertEqual(r.status_code,200);return json.loads(r.text.splitlines()[-1])['data']
 def legacy(self):
  # Explicit selection reproduces legacy model-backed meeting dispatch.
  r=self.ask('Chuẩn bị cách trao đổi phù hợp.',mssv='99000001');c=self.ctx.read(r['context_token']);self.assertEqual(c['kind'],'student');self.assertEqual(c['scope'],snapshot(self.roster));return r['context_token']
 def test_stream_transition_and_review(self):
  t=self.legacy();r=self.ask('Nếu chỉ học được 15 phút mỗi ngày thì nên thử việc gì?',t);self.assertIn('15 phút/ngày',r['answer']);p=self.ctx.read(r['context_token']);self.assertEqual(p['student'],'99000001');self.assertEqual(set(p['states']),{'meeting','study'});self.assertEqual(p['states']['study']['minutes'],15)
  r=self.ask('Em đánh giá xem phương án này có gì chưa chắc chắn, cô cần kiểm tra gì trước?',r['context_token']);self.assertIn('15 phút/ngày',r['answer']);self.assertIn('CPA',r['answer']);self.assertEqual(r['metadata']['review_views'],['risks'])
 def test_scope_expiry_tamper(self):
  t=self.legacy();q='Nếu chỉ học được 15 phút mỗi ngày thì nên thử việc gì?'
  for x in (None,t+'x'):
   r=self.ask(q,x);self.assertNotIn('15 phút/ngày',r['answer']);self.assertNotIn('99000001',r['answer'])
  self.roster['students'][0]['owed_credits']=12;r=self.ask(q,t);self.assertIn('đã thay đổi',r['answer']);self.assertIsNone(r['context_token'])
 def test_multiple_state_types_and_constraints(self):
  sig=snapshot(self.roster)
  for p in ({'kind':'advisor_task','topic':'meeting','mssv':'99000001','scope':sig},{'kind':'advisor_agent','topic':'profile','student':'99000001','scope':sig},{'kind':'advisor_mission','student':'99000001','scope':sig,'states':{'profile':{'kind':'advisor_agent','topic':'profile','student':'99000001','scope':sig}},'pending':[]}):
   r,c=bridge.transition_study('Em ấy chỉ học được 18 phút mỗi ngày, nên thử cách nào?',p,None,None,self.roster,self.root);self.assertIn('18 phút/ngày',r['answer']);self.assertEqual(c['states']['study']['minutes'],18)
   self.assertIsNone(bridge.transition_study('Học phí học lại, tự học 18 phút mỗi ngày?',p,None,None,self.roster,self.root))
   self.assertIsNone(bridge.transition_study('Sinh viên 99000002 chỉ học được 18 phút mỗi ngày, nên thử cách nào?',p,None,None,self.roster,self.root))
   r,c=bridge.transition_study('Chỉ học được 18 phút mỗi ngày trong 3 ngày, nên thử gì?',p,None,None,self.roster,self.root);self.assertNotIn('| Ngày |',r['answer']);self.assertEqual(c,p)
 def test_same_document_and_numeric_threshold(self):
  c={'answer':'Điểm trung bình chung đạt từ 2,5 trở lên và đáp ứng ngưỡng bảo đảm chất lượng đầu vào hoặc từ 2,0 trở lên và đáp ứng điều kiện trúng tuyển; sinh viên có đơn xin học thêm và trả học phí.','path':'fixture','sha256':'fixture','source_url':'https://example.invalid','articles':[{'article':26,'clause':1}]}
  with patch('advisor_decision.source',return_value=c):
   r,p=bridge.route('Theo QĐ 3626, GPA chung tất cả học phần chỉ 1,9 có đủ ngưỡng học chương trình thứ hai không?',{},None,None,self.roster,self.root);self.assertIn('chưa đạt ngưỡng điểm của cả hai nhánh',r['answer'])
  c['answer']='Điểm thưởng dùng xét học bổng, không dùng để xếp loại học lực hoặc xác định hạng tốt nghiệp.';c['articles']=[{'article':32,'clause':1}]
  with patch('advisor_decision.source',return_value=c) as src:
   r,p=bridge.route('Theo cùng quyết định, điểm thưởng NCKH có được tính vào xếp loại học lực không?',p,None,None,self.roster,self.root);self.assertIn('không dùng điểm thưởng',r['answer']);src.assert_called_with(self.root,32,1)
  self.assertIsNone(bridge.route('Theo cùng quyết định, điểm thưởng NCKH có được tính vào xếp loại học lực không?',{},None,None,self.roster,self.root))
 def test_model_echo(self):
  q='Em hãy giúp cô chuẩn bị cách trao đổi phù hợp, ưu tiên việc có thể làm trong tuần này.'
  obj={'questions':['Em có thể giúp cô chuẩn bị cách trao đổi phù hợp, ưu tiên việc có thể làm trong tuần này?'],'action':'private'}
  self.assertIsNone(validated(obj,'baseline',{},request=q))
if __name__=='__main__':unittest.main()
