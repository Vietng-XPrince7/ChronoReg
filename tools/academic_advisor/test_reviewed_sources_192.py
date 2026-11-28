import tempfile,unittest,shutil,json,hashlib
from pathlib import Path
from unittest.mock import patch
import reviewed_sources as rs
import course_planning as cp

class Review192(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  pack=Path(__file__).resolve().parents[2]/rs.PACK
  self.pack=json.loads(pack.read_text(encoding='utf-8'));self.original_pack=pack
  self.ledger=self.root/rs.HOLD;self.ledger.parent.mkdir(parents=True);self.ledger.write_text('')
  # Synthetic archive bytes; do not claim they are the original UET files.
  catalog=[]
  for r in self.pack['records']:
   if r.get('source_path'):
    p=self.root/r['source_path'];p.parent.mkdir(parents=True,exist_ok=True);b=('fixture '+r['id']).encode();p.write_bytes(b);r['source_sha']=hashlib.sha256(b).hexdigest()
    if r['kind']=='curriculum':catalog.append({'content_path':r['source_path'],'content_sha256':r['source_sha'],'doc_id':cp.DOC if r['id']=='cntt_2022_2024' else 'fixture-cntt-2025','program_identifier':'cntt'})
  p=self.root/'data/raw/uet/curricula/catalog.json';p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps({'records':catalog}))
  p=self.root/rs.PACK;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(self.pack,ensure_ascii=False),encoding='utf-8');self.pin=rs.digest(p.read_bytes());pt=patch.object(rs,'PIN',self.pin);pt.start();self.addCleanup(pt.stop)
 def ask(self,q,prior=None):return rs.route(q,prior or {},self.root)
 def test_pack_integrity_and_counts(self):
  self.assertEqual(rs.digest(self.original_pack.read_bytes()),'467481ea8cdd853e8b40bc205cf265497aa675adf5c9384f21056889fa955bb6')
  self.assertEqual(len(rs.curriculum_table(self.root,2024)[1]),71);self.assertEqual(len(rs.curriculum_table(self.root,2025)[1]),60)
  for y in (2024,2025):
   rec,t=rs.curriculum_table(self.root,y);self.assertEqual(sum(rec['blocks'].values()),rec['total']);self.assertTrue(all(p in t for _,pre in t.values() for p in pre))
 def test_cohort_totals_and_thesis(self):
  r,st=self.ask('CTĐT ngành CNTT K69 tổng số tín chỉ là bao nhiêu?');self.assertIn('136',r['answer']);self.assertEqual(r['metadata']['review_id'],'cntt_2022_2024')
  r,_=self.ask('Còn K70?',st);self.assertIn('135',r['answer']);self.assertNotIn('136',r['answer'])
  r,st=self.ask('Khóa luận tốt nghiệp ngành CNTT K69 bao nhiêu tín chỉ?');self.assertIn('**7 tín chỉ**',r['answer']);r,_=self.ask('Còn K70?',st);self.assertIn('**10 tín chỉ**',r['answer'])
 def test_course_rows_and_edition(self):
  r,st=self.ask('INT3306 có bao nhiêu tín chỉ và môn tiên quyết gì trong CTĐT CNTT K69?');self.assertIn('3 tín chỉ',r['answer']);self.assertIn('INT2204, INT2211',r['answer']);r,_=self.ask('Còn K70?',st);self.assertIn('chưa có dòng khớp',r['answer'])
  r,_=self.ask('UET.CS1058 tiên quyết gì trong CTĐT CNTT K70?');self.assertIn('UET.COM1050',r['answer']);self.assertIn('3 tín chỉ',r['answer'])
  r,_=self.ask('UET.IS3278 tiên quyết gì trong CTĐT CNTT K70?');self.assertIn('UET.IS2099, UET.MAT1052',r['answer'])
 def test_unknown_and_mixed_scope(self):
  for q in ('CTĐT CNTT năm học 2025-2026 tổng bao nhiêu tín chỉ?','CTĐT CNTT K72 tổng bao nhiêu tín chỉ?','CTĐT CNTT K69 K70 tổng bao nhiêu tín chỉ?'):
   r,_=self.ask(q);self.assertEqual(r['metadata']['engine_mode'],'CONTEXT_CLARIFICATION')
  for q in ('CTĐT CNTT K69 đăng ký tối đa bao nhiêu tín chỉ?','Học bổng CNTT K69 cần bao nhiêu tín chỉ?','CTĐT CNTT K69 học lại INT3306 bao nhiêu tín chỉ?'):
   self.assertIsNone(self.ask(q),q)
 def test_archive_hold_and_changed_pack(self):
  rec=self.pack['records'][0];q='CTĐT CNTT K69 tổng bao nhiêu tín chỉ?';p=self.root/rec['source_path'];b=p.read_bytes();p.write_bytes(b+b'changed');r,_=self.ask(q);self.assertEqual(r['metadata']['engine_mode'],'CONTEXT_CLARIFICATION');p.write_bytes(b)
  for hold in ({'doc_id':cp.DOC,'content_sha256':'x'},{'doc_id':'x','content_sha256':rec['source_sha']},{'doc_id':'x','content_sha256':'x','source_url':rec['source_url']}):
   self.ledger.write_text(json.dumps(hold));r,_=self.ask(q);self.assertEqual(r['metadata']['engine_mode'],'CONTEXT_CLARIFICATION')
  self.ledger.write_text('');p=self.root/rs.PACK;p.write_bytes(p.read_bytes()+b' ');r,_=self.ask(q);self.assertEqual(r['metadata']['engine_mode'],'CONTEXT_CLARIFICATION')
 def test_research_scopes(self):
  r,_=self.ask('Hạn đăng ký NCKH cấp Trường UET năm học 2025–2026?');self.assertIn('31/03/2026',r['answer']);self.assertIn('không phải hạn đăng ký ban đầu',r['answer']);self.assertIn('22/04/2026',r['answer'])
  r,_=self.ask('Hạn đăng ký NCKH Viện Trí tuệ nhân tạo năm học 2025–2026?');self.assertIn('15/02/2026',r['answer']);self.assertIn('25/02/2026',r['answer']);self.assertIn('Hai mốc',r['answer'])
  self.assertIsNone(self.ask('Hạn đăng ký NCKH UET năm học 2025–2026?'));self.assertIsNone(self.ask('Hạn đăng ký NCKH cấp Trường năm học 2026–2027?'))
 def test_scholarship_period(self):
  r,_=self.ask('Điều kiện cấp học bổng KKHT HKI năm học 2025–2026 là gì?');self.assertIn('15 tín chỉ',r['answer']);self.assertIn('8%',r['answer']);self.assertIn('HKII và kỳ phụ 2024–2025',r['answer']);self.assertIsNone(self.ask('Điều kiện cấp học bổng KKHT HKII năm học 2025–2026 là gì?'))
 def test_use_reviewed_table_in_planner(self):
  r=self.pack['records'][0];roster={'major':'Công nghệ thông tin','cohort':'QH-2024'}
  with patch.object(cp,'SHA',r['source_sha']):
   table,why=cp.load_candidate(self.root,roster);self.assertIsNotNone(table,why);self.assertEqual(table['INT3306'],(3,('INT2204','INT2211')));self.assertEqual(table['INT3132'],(3,('INT2215',)))
   self.assertIsNone(cp.load_candidate(self.root,{'major':'Công nghệ thông tin','cohort':'QH-2025'})[0])
if __name__=='__main__':unittest.main()
