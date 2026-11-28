"""Source versions, cross-scope comparisons and class advice; synthetic fixture."""
import unittest,re
import test_reviewed_sources_192 as fx
import test_advisor_agent as af
import reviewed_sources as rs
import advisor_bridge as bridge
import advisor_agent as agent
from pathlib import Path
class Release195(unittest.TestCase):
 def setUp(self):
  self.f=fx.Review192();self.f.setUp();self.addCleanup(self.f.doCleanups);self.root=self.f.root
 def ask(self,q,p=None):return rs.route(q,p or {},self.root)
 def b(self,q,p=None):return bridge.route(q,p or {},None,None,{},self.root)
 def test_new_rates(self):
  for label,y,expected in [('chuẩn ngành CNNN',2022,'2.250.000'),('chuẩn ngành CN XDGT',2022,'2.800.000'),('chuẩn các ngành còn lại',2022,'3.300.000'),('chuẩn',2026,'3.700.000'),('CLC TT23 ngành MMT&TTDL',2022,'3.600.000'),('ĐMKTKT',2024,'4.500.000')]:
   r,p=self.ask(f'Mức học bổng KKHT CTĐT {label} QH-{y} năm học 2026–2027 loại Giỏi?');self.assertIn(expected,r['answer'],label);self.assertEqual(p['year'],2026);self.assertEqual(r['metadata']['review_id'],'scholarship_rates_2026')
 def test_year_grade_and_hypothesis(self):
  r,p=self.ask('Định mức KKHT chuẩn K70 năm học 2025–2026 loại Xuất sắc?');self.assertIn('3.600.000',r['answer']);r,p=self.ask('Còn năm học 2026–2027?',p);self.assertIn('3.800.000',r['answer']);r,p=self.ask('Còn loại Khá?',p);self.assertIn('3.600.000',r['answer']);r,p=self.b('Giả định được nhận 3 tháng, tổng tiền bao nhiêu?',p);self.assertIn('10.800.000',r['answer']);self.assertEqual(r['metadata']['review_id'],'scholarship_rates_2026');self.assertIsNone(self.b('Giả định nhận 3 tháng loại Giỏi, tổng tiền bao nhiêu?',p))
 def test_narrower_scope_and_hold(self):
  for label in ('CLC TT23','CLC CNTT','chuẩn ngành CNKTXD'):
   r,p=self.ask(f'Mức học bổng KKHT CTĐT {label} QH-2022 năm học 2026–2027 loại Giỏi?');self.assertEqual(r['metadata']['engine_mode'],'CONTEXT_CLARIFICATION',label)
  r,p=self.ask('Mức học bổng KKHT chuẩn K70 năm học 2027–2028 loại Giỏi?');self.assertIn('2027–2028',r['answer']);self.assertEqual(p,{})
  import json
  self.f.ledger.write_text(json.dumps({'doc_id':'scholarship_rates_2026','content_sha256':'x'}));r,p=self.ask('Mức học bổng KKHT chuẩn K70 năm học 2026–2027 loại Giỏi?');self.assertEqual(p,{})
  r,p=self.ask('Mức học bổng KKHT chuẩn K70 năm học 2025–2026 loại Giỏi?');self.assertIn('3.500.000',r['answer'])
 def test_compare_years(self):
  r,p=self.b('So sánh mức học bổng KKHT chuẩn K69 loại Giỏi năm học 2025–2026 và 2026–2027.');self.assertIn('200.000 đồng/tháng',r['answer']);self.assertEqual(len(r['metadata']['advisor_sources']),2)
 def test_compare_different_pairs(self):
  r,p=self.b('Đối chiếu tổng tín chỉ CNTT K67 với KTMT K70.');self.assertEqual(p['items'],[['cntt',2022],['ktmt',2025]]);self.assertIn('150',r['answer']);self.assertIn('136',r['answer']);r,p=self.b('So sánh tổng tín chỉ KHMT và HTTT và KTMT K70.');self.assertEqual(len(p['items']),3);self.assertEqual(len(r['metadata']['advisor_sources']),3)
  self.assertIsNone(self.b('So sánh tổng tín chỉ đăng ký của KHMT K70 và KTMT K70.'))
 def test_class_meeting(self):
  f=af.AgentTests();f.setUp();r,p=agent.route('Cô có buổi sinh hoạt với lớp demo K69-DEMO, ưu tiên hỗ trợ nhóm có nguy cơ. Lập kế hoạch 24 phút và theo dõi sau buổi gặp.',{},None,None,f.roster,self.root);self.assertIn('5 hồ sơ',r['answer']);self.assertIn('không phải cảnh báo học vụ chính thức',r['answer']);self.assertIn('mốc kiểm tra lại',r['answer']);self.assertEqual(sum(map(int,re.findall(r'(\d+) phút',r['answer']))),24);self.assertNotIn('99000001',r['answer']);self.assertEqual(p['minutes'],24)
  r,p=agent.route('Sinh hoạt với lớp demo K70-DEMO, lập kế hoạch 24 phút.',{},None,None,f.roster,self.root);self.assertEqual(p,{})
if __name__=='__main__':unittest.main()
