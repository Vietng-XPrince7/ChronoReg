"""Synthetic source fixtures. Exercise product endpoint, hold checks and task transfer."""
import json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from conversation import add_conversation
from stream_chat import install_stream
from test_quality_routes import Request
import test_advisor_tasks_172 as fixtures
from advisor_decision import route as decision
from advisor_agent import route

ARTICLES={38:('Thi kết thúc học phần','1. Sinh viên chỉ được dự thi kết thúc học phần nếu có điểm đánh giá bộ phận lớn hơn 0, trả học phí đầy đủ và đáp ứng các điều kiện kết thúc học phần do thủ trưởng đơn vị phụ trách học phần quy định.'),25:('Đào tạo văn bằng thứ hai','1. Nội dung khác.\n2. Người học được bảo lưu kết quả học tập đối với những học phần có từ 80% trở lên nội dung tương đương và điểm học phần đạt từ điểm D trở lên; những học phần có nội dung tương đương từ 50% đến dưới 80% thì người học không được bảo lưu kết quả học tập nhưng có thể tự học và dự thi để lấy điểm; những học phần chưa học hoặc có nội dung tương đương dưới 50% thì người học phải dự học mới được dự thi theo quy định chung.')}
EXAM='Theo QĐ 3626, một sinh viên có điểm đánh giá bộ phận bằng 0 nhưng đã đóng đủ học phí có đủ điều kiện dự thi kết thúc học phần không?'
DEGREE='Theo QĐ 3626, sinh viên có thể bảo lưu kết quả học tập khi học văn bằng thứ hai trong trường hợp nội dung tương đương 80% không?'
class Decisions(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);p=self.root/'data/versioning';p.mkdir(parents=True);self.hold=p/'publication_holds.jsonl';self.hold.write_text('');self.mock=patch('advisor_decision.read_articles',return_value=(ARTICLES,'fixture'));self.mock.start()
 def tearDown(self):self.mock.stop();self.tmp.cleanup()
 def test_exam(self):
  r,c=decision(EXAM,{},self.root);self.assertIn('không đủ điều kiện',r['answer']);self.assertIn('kể cả đã đóng đủ',r['answer']);self.assertEqual(c['article'],38);self.assertIn('condition_evaluation',r['metadata']['workflow_tools'])
  r,_=decision(EXAM.replace('bằng 0','bằng 5'),{},self.root);self.assertIn('chưa đủ để kết luận',r['answer']);self.assertNotIn('được dự thi chắc chắn',r['answer'])
  r,_=decision(EXAM.replace('bằng 0','bằng 5').replace('đã đóng đủ','chưa đóng đủ'),{},self.root);self.assertIn('chưa đủ điều kiện',r['answer'])
  self.assertIsNone(decision(EXAM+' Áp dụng K71?',{},self.root));self.assertIsNone(decision(EXAM+' xin ngoại lệ',{},self.root));self.assertIsNone(decision(EXAM+' Theo QĐ 9999',{},self.root))
 def test_equivalency(self):
  r,c=decision(DEGREE,{},self.root,red=True);self.assertIn('từ D trở lên',r['answer']);self.assertEqual(c['article'],25)
  r,_=decision(DEGREE.replace('80%','70%'),{},self.root,red=True);self.assertIn('không được bảo lưu',r['answer'])
  r,_=decision(DEGREE.replace('80%','45%'),{},self.root,red=True);self.assertIn('phải dự học',r['answer'])
  r,_=decision(DEGREE.replace('80%','80% và điểm học phần F'),{},self.root,red=True);self.assertIn('không đáp ứng điều kiện',r['answer'])
  self.assertIsNone(decision(DEGREE+' xin ngoại lệ',{},self.root,red=True));self.assertIsNone(decision(DEGREE+' áp dụng K71',{},self.root,red=True));self.assertIsNone(decision(DEGREE+' giúp cô phê duyệt',{},self.root,red=True))
 def test_hypothetical_continuation(self):
  r,c=decision(EXAM,{},self.root);r,c=decision('Thế nếu điểm bộ phận là 5?',c,self.root);self.assertIn('điều kiện điểm bộ phận và học phí',r['answer']);self.assertIn('chưa đủ để kết luận',r['answer'])
  self.assertIsNone(decision('Thế nếu điểm bộ phận là 5?',{},self.root))
  r,c=decision(DEGREE,{},self.root);r,c=decision('Nếu điểm học phần F thì sao?',c,self.root);self.assertIn('không đáp ứng',r['answer'])
  r,c=decision('Còn tương đương 70%?',c,self.root);self.assertIn('không được bảo lưu',r['answer'])
  self.assertIsNone(decision('Thế nếu điểm bộ phận là 5 cho K71?',c,self.root))
  self.assertIsNone(decision(EXAM.replace('bằng 0','bằng -1'),{},self.root))
 def test_holds(self):
  self.hold.write_text(json.dumps({'doc_id':'qd3626','content_sha256':'fake'}));self.assertIsNone(decision(DEGREE,{},self.root,red=True));self.assertIsNone(decision(EXAM,{},self.root));self.hold.unlink();self.assertIsNone(decision(DEGREE,{},self.root,red=True))
 def test_changed_clauses(self):
  with patch('advisor_decision.read_articles',return_value=({38:('Thi','1. Điểm phải lớn hơn 5.')},'other')):self.assertIsNone(decision(EXAM,{},self.root))
 def test_http_read_only_and_red_research(self):
  s=SimpleNamespace(app=FastAPI(),_get_active_roster=lambda:{},_router=SimpleNamespace(route_decision=lambda q:SimpleNamespace(risk_tier='RED' if 'bảo lưu' in q else 'GREEN')),_semantic_pilot=True)
  dispatch=MagicMock(return_value={'answer':'blocked/legacy','routing':{'risk_tier':'RED'},'metadata':{}})
  add_conversation(s,dispatch,Request,self.root);h=next(r.endpoint for r in s.app.routes if r.path=='/api/advisor/chat');install_stream(s.app,h,interval=0);client=TestClient(s.app)
  def get(q,mode='advisor',token=None,force=None):
   r=client.post('/api/advisor/chat/stream',json={'question':q,'experience':mode,'context_token':token,'force_engine':force});self.assertEqual(r.status_code,200);events=[json.loads(x) for x in r.text.splitlines()];d=events[-1]['data'];self.assertEqual(''.join(x['text'] for x in events if x['event']=='delta'),d['answer']);return d
  a=get(DEGREE);self.assertEqual(a['metadata']['original_risk_tier'],'RED');self.assertEqual(a['routing']['risk_tier'],'YELLOW');self.assertTrue(a['context_token']);dispatch.assert_not_called()
  a=get(EXAM);self.assertIn('không đủ điều kiện',a['answer']);dispatch.assert_not_called()
  self.assertEqual(get(DEGREE,mode=None)['answer'],'blocked/legacy');self.assertEqual(get(DEGREE,force='continual_lora')['answer'],'blocked/legacy');self.assertEqual(get(DEGREE+' xin ngoại lệ')['answer'],'blocked/legacy')
  self.hold.write_text(json.dumps({'doc_id':'qd3626','content_sha256':'fake'}));self.assertEqual(get(DEGREE)['answer'],'blocked/legacy')

class Transfers(unittest.TestCase):
 setUp=fixtures.Tasks.setUp
 go=fixtures.Tasks.go
 def test_retake_advice_and_compare(self):
  with patch('quality_routes.load_candidate',return_value=(self.table,None)),patch('advisor_compare.load_candidate',return_value=(self.table,None)):
   _,c=self.go('Sinh viên 99000001 còn bao nhiêu tín chỉ nợ và GPA học kỳ?');_,c=self.go('Với em này, lập phương án học lại mỗi đợt tối đa 6 tín chỉ theo tiên quyết.',c)
   r,c=self.go('Nếu cô muốn em ấy học dồn để trả nợ nhanh thì có nên không?',c);self.assertIn('không khuyến nghị',r['answer']);self.assertIn('6 tín chỉ/đợt',r['answer']);self.assertEqual(c['student'],'99000001')
   r,c=self.go('So sánh phương án học lại 3 tín chỉ và 6 tín chỉ mỗi đợt.',c);self.assertIn('| 3 | 3 | 3 | 9 |',r['answer']);self.assertIn('| 6 | 2 | 3 | 9 |',r['answer']);self.assertIn('chưa duyệt',r['answer']);self.assertEqual(c['caps'],[3,6]);self.assertNotIn('owed_credits',json.dumps(c))
   r,c=self.go('Đổi thành 6 tín chỉ mỗi đợt',c);self.assertEqual(c['topic'],'retake');self.assertEqual(c['student'],'99000001')
   self.roster['students'][0]['owed_credits']=5;r,c=self.go('Có nên học dồn để trả nợ nhanh không?',c);self.assertIn('đã thay đổi',r['answer']);self.assertFalse(c)
 def test_compare_different_coverage(self):
  with patch('advisor_compare.load_candidate',return_value=(self.table,None)):
   r,c=self.go('So sánh học lại 2 tín chỉ và 6 tín chỉ mỗi đợt của sinh viên 99000001.');self.assertIn('không xếp được cùng tập',r['answer']);self.assertIn('chưa xếp',r['answer'])
 def test_fee_carry_quantity(self):
  def lookup(root,q):return {'answer':'• Học lại, cải thiện điểm (đồng/tín chỉ): '+('924.000' if '2025-2026' in q else '869.000')+' đồng.'}
  with patch('tuition.lookup_tuition',side_effect=lookup),patch('advisor_agent.source_table',side_effect=lambda root,v:{'answer':v['answer'],'metadata':{'engine_mode':'SOURCE_TABLE'},'routing':{}}):
   r,c=self.go('Sinh viên K69 CTĐT chuẩn, học lại học phần 3 tín chỉ trong năm học 2025–2026 mất bao nhiêu tiền?');self.assertEqual(c['fee']['quantity'],3);self.assertIn('2.772.000',r['answer'])
   r,c=self.go('Còn năm học 2024–2025?',c);self.assertIn('2.607.000',r['answer']);self.assertEqual(c['fee']['quantity'],3)
   r,c=self.go('Nếu học lại một môn 5 tín chỉ hết bao nhiêu tiền?',c);self.assertIn('4.345.000',r['answer']);self.assertEqual(c['fee']['quantity'],5)
if __name__=='__main__':unittest.main()
