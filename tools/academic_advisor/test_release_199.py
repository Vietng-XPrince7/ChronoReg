"""Cross-path acceptance regressions; synthetic roster and mocked source/model boundary."""
import json,unittest
from unittest.mock import patch
from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
from conversation import add_conversation,Context
from stream_chat import install_stream
from test_quality_routes import Request
import test_release_196 as fixture
import test_reviewed_sources_192 as source_fixture
from advisor_evidence import direct_article
from quality_workflows import snapshot
import advisor_bridge as bridge

class Release199(unittest.TestCase):
 def setUp(self):
  self.f=fixture.Continuity();self.f.setUp();self.addCleanup(self.f.doCleanups);self.roster=self.f.roster;self.root=self.f.root
 def test_finance_estimation(self):
  def lookup(root,q):return {'answer':'• Học lại, cải thiện điểm (đồng/tín chỉ): '+('924.000' if '2025-2026' in q else '869.000')+' đồng.'}
  with patch('tuition.lookup_tuition',side_effect=lookup),patch('advisor_agent.source_table',side_effect=lambda root,v:{'answer':v['answer'],'metadata':{'engine_mode':'SOURCE_TABLE'},'routing':{}}):
   r=self.f.ask('Cô cần ước tính khoản tiền để một sinh viên K69 chương trình chuẩn học lại 5 tín chỉ trong năm học 2025–2026.');self.assertIn('4.620.000',r['answer']);t=r['context_token'];self.assertTrue(t)
   r=self.f.ask('Nếu chuyển sang năm học 2024–2025, vẫn 5 tín chỉ ấy thì chênh bao nhiêu?',t);self.assertIn('4.345.000',r['answer']);self.assertIn('giảm 275.000',r['answer'])
   r=self.f.ask('Nếu chuyển sang năm học 2024–2025, vẫn 7 tín chỉ ấy thì chênh bao nhiêu?',t);self.assertNotIn('4.345.000',r['answer'])
 def test_topic_cancellation(self):
  f=source_fixture.Review192();f.setUp();self.addCleanup(f.doCleanups)
  import reviewed_sources as rs
  q='Cô không hỏi học lại nữa, mức học bổng KKHT loại Giỏi của K69 chuẩn năm học 2026–2027 là bao nhiêu?'
  r,p=rs.route(q,{},f.root);self.assertIn('3.700.000',r['answer']);self.assertEqual(p['topic'],'reviewed_rate')
  self.assertIsNone(rs.route(q+' cho sinh viên 99000001',{},f.root))
  self.assertIsNone(rs.route(q.replace('không hỏi học lại nữa','không hỏi học lại nữa nhưng tính học phí'),{},f.root))
 def test_legacy_review_scoped_continuation(self):
  ctx=Context(key=b'z'*32,clock=lambda:1000)
  s=SimpleNamespace(app=FastAPI(),_get_active_roster=lambda:self.roster,_router=SimpleNamespace(route_decision=lambda q:SimpleNamespace(risk_tier='GREEN')),_semantic_pilot=False)
  def dispatch(req):
   return {'answer':'Đánh giá hồ sơ.','routing':{'risk_tier':'GREEN','actual_engine_used':'chrono_rag'},'metadata':{'advisor_category':'STUDENT_STATUS','advisor_intent':'student_review','engine_mode':'ADVISOR_WORKFLOW','workflow_tools':['scope_check','course_history'],'roadmap':['review'],'advisor_entities':{'mssv':'99000001'}}}
  with patch('conversation.Context',return_value=ctx):add_conversation(s,dispatch,Request,self.root)
  h=next(r.endpoint for r in s.app.routes if r.path=='/api/advisor/chat');install_stream(s.app,h,interval=0);cl=TestClient(s.app)
  def ask(q,t=None,**kw):return json.loads(cl.post('/api/advisor/chat/stream',json={'question':q,'experience':'advisor','context_token':t,**kw}).text.splitlines()[-1])['data']
  r=ask('Xem hồ sơ sinh viên 99000001, ưu tiên trao đổi điều gì?',mssv='99000001');t=r['context_token'];self.assertEqual(ctx.read(t)['scope'],snapshot(self.roster))
  q='Giả sử em ấy dành được 16 phút tự học mỗi ngày thì nên làm gì?';r=ask(q,t);self.assertIn('16 phút/ngày',r['answer']);self.assertEqual(ctx.read(r['context_token'])['student'],'99000001')
  self.assertIsNone(bridge.transition_study(q,{'kind':'student','mssv':'99000001','scope':snapshot(self.roster)},'99000002',None,self.roster,self.root))
  self.roster['students'][0]['owed_credits']=12;r=ask(q,t);self.assertIn('đã thay đổi',r['answer']);self.assertFalse(r['context_token'])
 def test_article_reference_and_hold(self):
  import tempfile
  from pathlib import Path
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);p=root/'data/versioning/publication_holds.jsonl';p.parent.mkdir(parents=True);p.write_text('')
   articles={32:('Điểm thưởng', '1. Đây là khoản một của văn bản thử.\n2. Đây là khoản hai của văn bản thử.\n3. Sinh viên chỉ được hưởng một mức điểm thưởng cao nhất.')}
   old={'kind':'advisor_agent','topic':'evidence_article','article':32}
   with patch('advisor_evidence.read_articles',return_value=(articles,'fixture')):
    for q in ('Khoản 3 của điều đó quy định gì?','Xem khoản 3 trong điều này.'):
     r,c=direct_article(q,old,root);self.assertIn('mức điểm thưởng cao nhất',r['answer']);self.assertEqual(c['article'],32)
     self.assertIsNone(direct_article(q,{},root))
    self.assertIsNone(direct_article('Khoản 3 của điều đó áp dụng K71?',old,root))
    p.write_text('{"doc_id":"qd3626","content_sha256":"fixture"}');r,c=direct_article('Khoản 3 của điều đó quy định gì?',old,root);self.assertFalse(c);self.assertNotIn('mức điểm thưởng cao nhất',r['answer'])
 def test_public_draft_only(self):
  r=self.f.ask('Cô muốn gửi thông báo chung mời cả lớp trao đổi về việc học, không nêu tên hoặc điểm của bất kỳ ai.');self.assertIn('Bản nháp thông báo chung (chưa gửi)',r['answer']);self.assertIn('Các em thân mến',r['answer']);self.assertNotIn('99000001',r['answer']);self.assertEqual(self.f.ctx.read(r['context_token'])['audience'],'class')
  r=self.f.ask('Tóm tắt kế hoạch học lại của em ấy vừa rồi.',r['context_token']);self.assertNotIn('99000001',r['answer'])
if __name__=='__main__':unittest.main()
