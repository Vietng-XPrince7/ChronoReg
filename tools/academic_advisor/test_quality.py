import os, unittest, tempfile, shutil
from pathlib import Path
from quality import parse,lookup,unsupported_numbers,messages_for,SYSTEM,SOURCES
ROOT=Path(os.environ['CHRONOREG_TEST_REPO'])
class Tests(unittest.TestCase):
 def test_all_tables(self):
  for y,n in [(2022,17),(2023,17),(2024,17),(2025,20),(2026,20)]:
   with self.subTest(y=y): self.assertEqual(len(parse(ROOT,y)[0]),n)
 def test_2024(self):
  r=lookup(ROOT,'Điểm chuẩn ngành Khoa học máy tính của UET năm 2024 là bao nhiêu?');self.assertIn('CN8 – Khoa học máy tính: 27,58',r['answer']);self.assertEqual(r['row_count'],1)
 def test_2023(self): self.assertIn('24,2 điểm',lookup(ROOT,'Điểm trúng tuyển ngành Vật lý kỹ thuật (CN3) của UET năm 2023 theo phương thức THPT là bao nhiêu?')['answer'])
 def test_2026_full(self):
  r=lookup(ROOT,'điểm chuẩn các ngành 2026');self.assertEqual(r['row_count'],20);self.assertIn('CN3 – Vật lý kỹ thuật: 25,41',r['answer']);self.assertIn('CN13 – Kỹ thuật năng lượng: 25,25',r['answer']);self.assertIn('CN20 – Khoa học dữ liệu: 26,85',r['answer']);self.assertIn('ĐC<=0,5',r['answer']);self.assertLess(len(r['answer']),2800)
 def test_declines(self):
  for q in ['Điểm chuẩn CN8 2024 và 2026','Điểm chuẩn HUTECH 2024','Điểm chuẩn CN3 SAT 2023','Điểm chuẩn ngành ABC năm 2026','Điểm chuẩn CN8 năm 2024 và học phí','Điểm chuẩn CN1 ngành Khoa học máy tính năm 2024','Điểm chuẩn các ngành 2027']:
   with self.subTest(q=q): self.assertIsNone(lookup(ROOT,q))
 def test_changed_source(self):
  with tempfile.TemporaryDirectory() as d:
   rel=Path('data/raw/uet/markdown/2024')/SOURCES[2024][0];p=Path(d)/rel;p.parent.mkdir(parents=True);p.write_bytes((ROOT/rel).read_bytes()+b'\nchanged');self.assertRaises(ValueError,parse,d,2024)
 def test_numbers(self):
  self.assertFalse(unsupported_numbers('27,58 điểm; 2.070.000 đồng; 24/08/2024','27.58; 2070000; 24/08/2024'));self.assertTrue(unsupported_numbers('26,85 điểm','27,58 điểm'))
 def test_prompt(self):
  m=messages_for('lora','Năm học được hỏi: 2024-2025.\nCâu hỏi?', 'lora');self.assertEqual(m[0]['content'],SYSTEM);self.assertEqual(m[1]['content'],'Năm học: 2024-2025\nCâu hỏi: Câu hỏi?')
if __name__=='__main__':unittest.main()
