import os,tempfile,unittest
from pathlib import Path
from scholarship import parse_rates,lookup_rates,SOURCES
ROOT=Path(os.environ['CHRONOREG_TEST_REPO'])
class ScholarshipTests(unittest.TestCase):
 def test_full_tables(self):
  self.assertEqual([(len(r),sum(len(x['values']) for x in r)) for y in (2023,2025) for r,*_ in [parse_rates(ROOT,y)]],[(9,23),(8,24)])
 def check(self,q,value):
  r=lookup_rates(ROOT,q);self.assertIsNotNone(r,q);self.assertIn(value+' đồng/tháng',r['answer']);self.assertEqual(len(r['sha256']),64)
 def test_regression(self):
  self.check('Mức học bổng khuyến khích học tập loại xuất sắc của nhóm Đối với lớp chất lượng cao thuộc ngành Công nghệ thông tin; Các khóa từ QH-2021 trở về trước tại UET năm học 2023-2024 là bao nhiêu?','2.070.000')
 def test_scope_separation(self):
  for group,cohort,grade,year,value in [('chương trình chuẩn','QH-2021','xuất sắc',2023,'1.590.000'),('CLC CNTT','QH-2023','giỏi',2023,'3.800.000'),('chương trình chuẩn ngành CNNN','QH-2022','khá',2023,'1.740.000'),('chương trình chuẩn ngành CNKTXD','QH-2022','xuất sắc',2025,'2.700.000'),('CLC theo TT23','QH-2021','giỏi',2025,'3.600.000'),('ĐMKTKT','QH-2024','khá',2025,'4.000.000'),('chương trình chuẩn','QH-2025','xuất sắc',2025,'3.600.000')]:
   with self.subTest(group=group,cohort=cohort):self.check(f'Mức học bổng loại {grade} {group}, khóa {cohort}, năm học {year}-{year+1}?',value)
 def test_not_extrapolated(self):
  for q in ['Mức học bổng loại khá CLC CNTT QH-2021 năm học 2023-2024?', 'Mức học bổng loại xuất sắc chương trình chuẩn QH-2022 năm học 2023-2024?', 'Mức học bổng loại giỏi CLC CNTT QH-2022 năm học 2026-2027?', 'Mức học bổng loại giỏi QH-2022 năm học 2025-2026?', 'Mức học bổng xuất sắc CLC CNTT QH-2023 năm 2023 và 2025?', 'Mức học bổng giỏi chương trình chuẩn QH-2023 năm học 2025-2026 tại HUTECH?','Điều kiện xét cấp học bổng giỏi CLC CNTT QH-2022 năm học 2025-2026?']:
   with self.subTest(q=q):self.assertIsNone(lookup_rates(ROOT,q))
 def test_changed_source(self):
  with tempfile.TemporaryDirectory() as d:
   rel=Path('data/raw/uet/markdown/2023')/SOURCES[2023][0];p=Path(d)/rel;p.parent.mkdir(parents=True);p.write_bytes((ROOT/rel).read_bytes()+b'changed');self.assertRaises(ValueError,parse_rates,d,2023)
if __name__=='__main__':unittest.main()
