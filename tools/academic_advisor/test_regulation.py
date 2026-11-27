import os, json, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from regulation import selection, lookup_regulation, read_articles, TEXT, PDF, PDF_SHA
from runtime_v5 import install
from test_runtime import Backend
ROOT=Path(os.environ['CHRONOREG_TEST_REPO'])
CASES=[
 ('Quy trình rút bớt học phần?',23,['2 tuần','1 tuần','Phòng Đào tạo']),
 ('Xin bảo lưu kết quả học tập như thế nào?',36,['2,0','01 học kỳ','2 tuần']),
 ('Tiêu chí cảnh báo học vụ UET?',44,['1,20','1,40','1,60','1,80','24 tín chỉ','50%','17/02/2023','nhắc nhở']),
 ('Điều kiện học vượt 24 tín chỉ?',21,['2/3','3/2','18 tín chỉ','không thể kết luận']),
 ('Điều kiện tốt nghiệp?',46,['2,00','2,50']),
 ('Điều kiện chuyển ngành?',28,['năm học thứ nhất','2,50']),
 ('Xếp loại học lực?',45,['3,60','3,20','2,50','2,00']),
 ('Quy trình xin bảo lưu kết quả học tập hoặc rút bớt học phần?',23,['Điều 23','Điều 36','2 tuần']),
]
class RegulationTests(unittest.TestCase):
 def test_source(self):
  articles,sha=read_articles(ROOT);self.assertEqual(len(articles),51);self.assertEqual(len(sha),64)
 def test_clauses(self):
  for q,n,need in CASES:
   with self.subTest(q=q):
    r=lookup_regulation(ROOT,q);self.assertIsNotNone(r);self.assertIn(n,[a['article'] for a in r['articles']]);self.assertEqual(r['pdf_sha256'],PDF_SHA);self.assertLessEqual(len(r['answer']),2700)
    for x in need:self.assertIn(x,r['answer'])
 def test_scope(self):
  for q in ['Cảnh báo học vụ K66?', 'Cảnh báo học vụ năm 2021?', 'So sánh quy định rút học phần 5115 và 3626?', 'Xin ngoại lệ học vượt?', 'Trong lớp tôi sinh viên nào cảnh báo học vụ?', 'Học phí khi rút học phần?', 'Điều 44 của Thông tư 08?', 'Phòng học vụ mở cửa lúc mấy giờ?']:
   self.assertEqual(selection(q),[],q)
 def test_old_semester(self):
  self.assertIsNone(lookup_regulation(ROOT,'Tiêu chí cảnh báo học vụ HKI năm học 2022-2023?'))
 def test_pins(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);p=root/TEXT;p.parent.mkdir(parents=True);p.write_text('changed',encoding='utf8');(root/PDF).write_bytes((ROOT/PDF).read_bytes())
   with self.assertRaises(ValueError):read_articles(root)
 def test_hold(self):
  with patch.object(Path,'read_text',return_value=json.dumps({'doc_id':'qd-3626-2022'})):
   with self.assertRaises(ValueError):lookup_regulation(ROOT,'Tiêu chí cảnh báo học vụ?')
 def test_runtime(self):
  def route(q,student_context=None):
   tier='RED' if 'ngoại lệ' in q else 'YELLOW' if 'so sánh' in q else 'GREEN'
   e='safety_gate_red' if tier=='RED' else 'continual_lora'
   return SimpleNamespace(risk_tier=tier,selected_engine=e,actual_engine_used=e,detected_signals=[],routing_reason='old')
  s=SimpleNamespace(llm_backend=Backend(),_router=SimpleNamespace(route_decision=route),_run_rag_engine=lambda *a,**k:{'old':True},_build_metadata=lambda *a,**k:{})
  install(s,ROOT)
  q='Quy trình rút bớt học phần?'
  self.assertEqual(s._router.route_decision(q).selected_engine,'chrono_rag')
  self.assertEqual(s._router.route_decision(q+' ngoại lệ').selected_engine,'safety_gate_red')
  self.assertEqual(s._router.route_decision(q+' so sánh').risk_tier,'YELLOW')
  self.assertEqual(s._router.route_decision(q,{'mssv':'1'}).selected_engine,'continual_lora')
  p=s._run_rag_engine(q,'chrono_rag');self.assertEqual(p['inference_source'],'deterministic_source_clause');m=s._build_metadata([],1,pred=p);self.assertEqual(m['engine_mode'],'SOURCE_CLAUSE');self.assertEqual(m['pdf_sha256'],PDF_SHA);self.assertIsNone(m['model_name'])
  self.assertTrue(s._run_rag_engine(q,'naive_rag')['old']);self.assertTrue(s._run_rag_engine(q,'chrono_rag',{'roster_context':'student'})['old'])
  with patch.object(Path,'read_text',return_value=json.dumps({'doc_id':'qd-3626-2022'})):
   self.assertEqual(s._run_rag_engine(q,'chrono_rag')['inference_source'],'source_clause_unavailable')
if __name__=='__main__':unittest.main()
