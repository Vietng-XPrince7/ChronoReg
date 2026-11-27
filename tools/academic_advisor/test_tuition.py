import os,unittest,json,tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from tuition import lookup_tuition,dimensions,read_table
from runtime_v5 import install
from test_runtime import Backend
from test_scope import mock_classifier
ROOT=Path(os.environ['CHRONOREG_TEST_REPO'])
class TuitionTests(unittest.TestCase):
 def test_tables(self):
  for y,counts in [(2024,[1,2,3,1,2]),(2025,[9,8]),(2026,[7,5])]:
   self.assertEqual([len(r) for _,_,r in read_table(ROOT,y)[0]],counts)
 def test_rates(self):
  for question,expected in [
   ('Mức học phí CTĐT chuẩn QH-2023 năm học 2026-2027?', ['3.600.000','974.000']),
   ('Mức học phí CTĐT chuẩn QH-2021 năm học 2025-2026?', ['1.850.000','508.000']),
   ('Mức học phí CTĐT chuẩn QH-2022 ngành Công nghệ Nông nghiệp năm học 2025-2026?', ['2.000.000','545.000','816.000']),
   ('Mức học phí CTĐT chuẩn QH-2022 các ngành còn lại năm học 2026-2027?', ['3.200.000','860.000']),
   ('Mức học phí CTĐT theo ĐMKTKT QH-2024 năm học 2026-2027?', ['4.400.000','1.188.000']),
   ('Mức học phí CLC theo Thông tư 23 QH-2022 năm học 2024-2025?', ['35.000.000','800.000']),
   ('Mức học phí CTĐT chuẩn QH-2022 nhóm 2 năm học 2024-2025?', ['23.400.000','634.000','765.000']),
   ('Mức học phí CTĐT chuẩn QH-2024 năm học 2024-2025?', ['32.000.000','869.000']),
   ('Mức học phí thạc sĩ QH-2024 năm học 2026-2027?', ['3.700.000','1.221.000']),
   ('Mức học phí tiến sĩ QH-2024 năm học 2025-2026?', ['4.200.000','1.282.000']),
   ('Mức học phí thạc sĩ QH-2025 năm học 2025-2026?', ['248/QĐ-ĐHCN','1.144.000']),
   ('Mức học phí tiến sĩ QH-2021 năm học 2026-2027?', ['4.400.000','văn bản không ghi mức'])]:
   with self.subTest(question=question):
    r=lookup_tuition(ROOT,question);self.assertIsNotNone(r);self.assertEqual(len(r['sha256']),64);self.assertEqual(r['table_kind'],'tuition_rate')
    for v in expected:self.assertIn(v,r['answer'])
 def test_units(self):
  old=lookup_tuition(ROOT,'Học phí CTĐT chuẩn QH-2023 năm học 2024-2025?')['answer'];new=lookup_tuition(ROOT,'Học phí CTĐT chuẩn QH-2023 năm học 2026-2027?')['answer']
  self.assertIn('đồng/1 năm học, 10 tháng',old);self.assertNotIn('đồng/tháng',old);self.assertIn('đồng/tháng',new);self.assertIn('không phải lịch thu tiền',new)
 def test_no_extrapolation(self):
  for q in ['Học phí CTĐT chuẩn QH-2023 năm học 2023-2024?', 'Học phí QH-2023 năm học 2026-2027?', 'Học phí CTĐT chuẩn QH-2022 năm học 2026-2027?', 'Học phí CTĐT chuẩn QH-2022 các ngành còn lại năm học 2024-2025?', 'So sánh học phí CTĐT chuẩn QH-2023 năm 2025 và 2026?', 'Học phí thạc sĩ QH-2021 năm học 2026-2027?', 'Học phí CTĐT chuẩn QH-2023 năm học 2026-2027 có được miễn không?', 'Học phí CTĐT chuẩn QH-2026 năm học 2024-2025?']:
   self.assertIsNone(lookup_tuition(ROOT,q),q)
 def test_scope(self):
  from scope import classify_with_scope
  q='Mức học phí CTĐT chuẩn khóa QH-2024 năm học 2026-2027?'
  self.assertEqual(classify_with_scope(mock_classifier,q)[0],'REGULATION')
  self.assertEqual(classify_with_scope(mock_classifier,q+' Bảng điểm lớp mình')[0],'ELIGIBILITY_CHECK')
 def test_dispatch_and_hold(self):
  q='Mức học phí CTĐT chuẩn QH-2023 năm học 2026-2027?'
  server=SimpleNamespace(llm_backend=Backend(),_run_rag_engine=lambda *a,**k:{'old':True},_build_metadata=lambda *a,**k:{})
  install(server,ROOT);pred=server._run_rag_engine(q,'chrono_rag');self.assertEqual(pred['inference_source'],'deterministic_source_table');self.assertIn('974.000',pred['answer']);self.assertEqual(len(server._build_metadata([],1,pred=pred)['sha256']),64)
  v=lookup_tuition(ROOT,q);hold=ROOT/'data/versioning/publication_holds.jsonl';read=Path.read_text
  def fake(p,*a,**k):return json.dumps({'content_sha256':v['normalized_sha256']}) if p==hold else read(p,*a,**k)
  with patch.object(Path,'read_text',fake):self.assertTrue(server._run_rag_engine(q,'chrono_rag')['old'])
 def test_source_pin(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'data/raw/uet/markdown/2026/Quy_dinh_muc_thu_hoc_phi_2026.md';p.parent.mkdir(parents=True);p.write_text('changed',encoding='utf-8')
   with self.assertRaises(ValueError):lookup_tuition(d,'Học phí CTĐT chuẩn QH-2023 năm học 2026-2027?')
if __name__=='__main__':unittest.main()
