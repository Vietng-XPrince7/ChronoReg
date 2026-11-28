import unittest,json
from test_reviewed_sources_192 import Review192
import reviewed_sources as rs
# Import the fixture only, avoid rediscovering its inherited tests.
class Review193(unittest.TestCase):
 setUp=Review192.setUp
 ask=Review192.ask
 def test_rates_and_followups(self):
  r,st=self.ask('Học bổng khuyến khích học tập CTĐT chuẩn QH-2024 năm học 2025–2026 loại Giỏi là bao nhiêu?');self.assertIn('3.500.000 đồng/tháng',r['answer']);self.assertEqual(r['metadata']['review_id'],'scholarship_rates_2025')
  r,st=self.ask('Còn loại Xuất sắc?',st);self.assertIn('3.600.000 đồng/tháng',r['answer']);r,st=self.ask('Còn K70?',st);self.assertIn('QH-2025',r['answer']);self.assertIn('3.600.000 đồng/tháng',r['answer'])
  r,_=self.ask('Còn năm học 2026–2027?',st);self.assertIn('3.800.000',r['answer'])
 def test_all_rate_groups(self):
  for group,cohort,amount in [('chuẩn',2021,'1.950.000'),('chuẩn ngành CNNN',2022,'2.100.000'),('chuẩn ngành CNKTXD',2022,'2.600.000'),('chuẩn các ngành còn lại',2022,'3.100.000'),('chuẩn',2025,'3.500.000'),('CLC CNTT',2022,'4.000.000'),('CLC TT23',2022,'3.600.000'),('ĐMKTKT',2024,'4.100.000')]:
   with self.subTest(group=group):
    r,_=self.ask(f'Mức học bổng KKHT CTĐT {group} QH-{cohort} năm học 2025–2026 loại Giỏi?');self.assertIn(amount,r['answer'])
 def test_rate_conflicts(self):
  for q in ('Mức học bổng KKHT chuẩn QH-2022 năm học 2025–2026 loại Giỏi?', 'Mức học bổng KKHT chuẩn QH-2024 K70 năm học 2025–2026 loại Giỏi?', 'Mức học bổng KKHT chuẩn CLC QH-2024 năm học 2025–2026 loại Giỏi?', 'Mức học bổng KKHT chuẩn QH-2026 năm học 2025–2026 loại Giỏi?'):
   r,_=self.ask(q);self.assertEqual(r['metadata']['engine_mode'],'CONTEXT_CLARIFICATION',q)
  self.assertIsNone(self.ask('Mức học bổng của sinh viên 24020027 năm học 2025–2026 loại Giỏi?'))
 def test_other_programs(self):
  for major,old,new in [('KHMT',136,135),('HTTT',136,135),('KTMT',150,150)]:
   r,st=self.ask(f'CTĐT {major} K69 tổng số tín chỉ bao nhiêu?');self.assertIn(f'**{old} tín chỉ**',r['answer']);r,_=self.ask('Còn K70?',st);self.assertIn(f'**{new} tín chỉ**',r['answer'])
  r,_=self.ask('Khóa luận tốt nghiệp ngành HTTT K69 bao nhiêu tín chỉ?');self.assertIn('**7 tín chỉ**',r['answer'])
  r,_=self.ask('Khóa luận tốt nghiệp ngành KTMT K69 bao nhiêu tín chỉ?');self.assertEqual(r['metadata']['engine_mode'],'CONTEXT_CLARIFICATION')
  self.assertIsNone(self.ask('UET.CS1058 có bao nhiêu tín chỉ trong CTĐT KHMT K70?'))
 def test_unsupported_scope(self):
  for q in ('CTĐT CNTT CLC K69 tổng bao nhiêu tín chỉ?', 'CTĐT KHMT CLC K69 tổng bao nhiêu tín chỉ?', 'CTĐT HTTT K72 tổng bao nhiêu tín chỉ?'):
   r,_=self.ask(q);self.assertEqual(r['metadata']['engine_mode'],'CONTEXT_CLARIFICATION');self.assertNotIn('136',r['answer'])
 def test_new_source_hold(self):
  rec=next(x for x in self.pack['records'] if x['id']=='khmt_2022_2024');self.ledger.write_text(json.dumps({'doc_id':'fixture','content_sha256':'x','source_url':rec['cohort_index_url']}));r,_=self.ask('CTĐT KHMT K69 tổng bao nhiêu tín chỉ?');self.assertEqual(r['metadata']['engine_mode'],'CONTEXT_CLARIFICATION')
 def test_all_ready(self):
  out=rs.status(self.root);self.assertEqual(len(out),13);self.assertTrue(all(x['status']=='READY' for x in out))
del Review192
