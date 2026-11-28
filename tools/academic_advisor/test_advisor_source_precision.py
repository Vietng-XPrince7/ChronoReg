import unittest
from types import SimpleNamespace
from advisor_source_precision import family,eligible,programs,academic_year
class SourcePrecision(unittest.TestCase):
 def test_calendar_not_admissions(self):
  q='Kế hoạch năm học UET 2026-2027 có mốc đăng ký học nào?'
  self.assertEqual(family(q),'calendar');self.assertFalse(eligible(SimpleNamespace(path='data/raw/uet/markdown/2026/thong_tin_tuyen_sinh_2026.md'),q,{}));self.assertTrue(eligible(SimpleNamespace(path='data/raw/uet/markdown/2026/Ke_hoach_hoc_tap_2026.md'),q,{}))
 def test_program_and_section(self):
  q='Chuẩn đầu ra ngành Kỹ thuật Robot QH-2024 là gì?';self.assertEqual(programs(q),{'ktrb'});good=SimpleNamespace(path='robot.md',heading='Chuẩn đầu ra',text='PLO1');bad=SimpleNamespace(path='mechanics.md',heading='Chuẩn đầu ra',text='PLO1');self.assertTrue(eligible(good,q,{'robot.md':'ktrb'}));self.assertFalse(eligible(bad,q,{'mechanics.md':'engineering-mechanics'}));self.assertFalse(eligible(SimpleNamespace(path='intro.md',heading='Giới thiệu',text='Mục tiêu'),q,{'intro.md':'ktrb'}))
 def test_postgraduate(self):
  q='Thông báo tuyển sinh sau đại học năm 2022';self.assertFalse(eligible(SimpleNamespace(path='QD3626_text.md'),q,{}));self.assertTrue(eligible(SimpleNamespace(path='Chương_trình_đào_tạo_sau_đại_học_2022.md'),q,{}))
 def test_year(self):
  self.assertEqual(academic_year('Khóa QH-2024 năm học 2025-2026'),2025);self.assertIsNone(academic_year('năm 2022 và 2025'));self.assertEqual(academic_year('năm 2023'),2023)
 def test_career(self):
  q='Sinh viên tìm cơ hội việc làm của UET ở trang nào?';self.assertEqual(family(q),'career');self.assertFalse(eligible(SimpleNamespace(path='curriculum.md'),q,{}))
 def test_program_alias(self):
  self.assertEqual(programs('CTĐT CNTT và Kỹ thuật máy tính'),{'cntt','ktmt'})
