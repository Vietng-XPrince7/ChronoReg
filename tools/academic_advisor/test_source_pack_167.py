import unittest, tempfile, shutil, json, os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from calendar_source import INTERVAL_REVIEW, inspect_uploaded_calendar, pack_status
from semantic_product import route
from knowledge import Index

@unittest.skipUnless(os.getenv('CHRONOREG_CALENDAR_PACK_TEST'), 'original pack absent')
class ScopedReview(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.dest=self.root/'data/advisor_sources/calendar';self.hold=self.root/'data/versioning/publication_holds.jsonl';self.hold.parent.mkdir(parents=True)
        shutil.copytree(Path(os.environ['CHRONOREG_CALENDAR_PACK_TEST']),self.dest)
        self.rows=[x['hold'].copy() for x in INTERVAL_REVIEW.values()]
        self.rows.append({'doc_id':'uet-2022-ke-hoach-hoc-tap-2022-7f683bf6cb','content_sha256':'ab398b7e6b150da001d8d97b683658ce8127598676004dd0594a9101cdf103f8','reason':'quality_hold: Calendar PDF verified, multi-column extraction requires table QA'})
        self.write(self.rows)
    def write(self,rows):self.hold.write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf8')
    def check(self,period='2024-2025',sem='main_2'):return inspect_uploaded_calendar(self.root,period,sem)
    def test_exact_known_holds_remain_and_six_intervals(self):
        before=self.hold.read_bytes()
        self.assertEqual([r['status'] for r in pack_status(self.root)],['READY']*6)
        for v in INTERVAL_REVIEW.values():
            for sem,interval in v['intervals'].items():
                r=self.check(v['period'],sem);self.assertEqual(r['hits'][0]['date'],interval[0]);self.assertEqual(r['review_scope'],'semester_interval_only');self.assertEqual(r['retained_quality_hold_ids'],[v['hold']['doc_id']])
        self.assertEqual(self.hold.read_bytes(),before)
        # Original research/index holds remain unchanged; separate pack is not indexed.
        idx=Index(self.root);self.assertEqual(idx.hold_ids,{r['doc_id'] for r in self.rows});self.assertEqual(idx.chunks,[])
    def test_changed_hold_is_not_released(self):
        for field,value in [('reason','historical_hold: schedule superseded'),('content_sha256','0'*64),('evidence_reference','https://example.org'),('source_path','data/raw/other.md')]:
            rows=[x.copy() for x in self.rows];rows[0][field]=value;self.write(rows);self.assertEqual(self.check()['status'],'POSSIBLE_RELATED_PUBLICATION_HOLD')
    def test_new_exact_or_related_hold_blocks(self):
        for r,expected in [({'doc_id':'uet-advisor-calendar-2024-2025'},'EXACT_PUBLICATION_HOLD'),({'doc_id':'uet-2024-ke-hoach-hoc-tap-amendment'},'POSSIBLE_RELATED_PUBLICATION_HOLD'),({'content_sha256':json.loads((self.dest/'manifest.json').read_text())['sources'][0]['pdf_sha256']},'EXACT_PUBLICATION_HOLD')]:
            self.write(self.rows+[r]);self.assertEqual(self.check()['status'],expected)
    def test_api_route_with_actual_known_holds(self):
        with patch('calendar_source.Index',return_value=SimpleNamespace(errors=[],chunks=[])),patch('semantic_product.infer',side_effect=AssertionError('unexpected model')):
            r,st=route('Theo kế hoạch học tập UET năm học 2024–2025, học kỳ II bắt đầu ngày nào?',{},None,None,{},self.root)
            self.assertIn('03/02/2025',r['answer']);self.assertIn('không có chữ ký số',r['answer']);self.assertEqual(r['metadata']['cited_doc_ids'],['uet-advisor-calendar-2024-2025'])
            r,st=route('Theo kế hoạch học tập UET năm học 2025–2026, học kỳ II bắt đầu ngày nào?',st,None,None,{},self.root)
            self.assertIn('23/02/2026',r['answer']);self.assertNotIn('03/02/2025',r['answer'])
    def test_pdf_hash_mismatch(self):
        p=self.dest/'Ke_hoach_hoc_tap_2025.pdf';p.write_bytes(p.read_bytes()+b'x');self.assertEqual(self.check('2025-2026')['status'],'PDF_HASH_MISMATCH')
if __name__=='__main__':unittest.main()
