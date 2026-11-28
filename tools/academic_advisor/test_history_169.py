import unittest, tempfile, json, os, shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from calendar_source import inspect_uploaded_calendar,pack_status,REVIEW_2022
from semantic_product import route
from tuition_history import adjusted_standard, REL, PIN, DOC

@unittest.skipUnless(os.getenv('CHRONOREG_HISTORY_PACK_TEST'),'original pack absent')
class History169(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup); self.root=Path(self.tmp.name)
        shutil.copytree(Path(os.environ['CHRONOREG_HISTORY_PACK_TEST'])/'data',self.root/'data')
        self.ledger=self.root/'data/versioning/publication_holds.jsonl';self.ledger.parent.mkdir(parents=True)
        self.rows=[REVIEW_2022['hold'].copy(),{'doc_id':'uet-2022-dinh-muc-hoc-phi-dao-tao-dai-hoc-2022-aafa0d8e79','reason':'historical_hold: Original undergraduate tuition rates subsequently adjusted for 2022-2023','content_sha256':'4ad16473b3a33ba90b63deeb54dbdc9c235a675736f1228d6fdc37d25a002443'}];self.write(self.rows)
    def write(self,rows):self.ledger.write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf8')
    def test_three_intervals(self):
        for k,interval in REVIEW_2022['intervals'].items():
            r=inspect_uploaded_calendar(self.root,'2022-2023',k);self.assertEqual(r['status'],'READY');self.assertEqual(r['hits'][0]['date'],interval[0]);self.assertEqual(r['retained_quality_hold_ids'],[REVIEW_2022['hold']['doc_id']]);self.assertIn('bảng tuần chưa được duyệt',r['hits'][0]['qualification'])
        self.assertEqual(len(pack_status(self.root)),9)
    def test_changed_hold_and_pdf(self):
        h=self.rows[0].copy();h['reason']='historical_hold: changed';self.write([h]);self.assertEqual(inspect_uploaded_calendar(self.root,'2022-2023','main_1')['status'],'POSSIBLE_RELATED_PUBLICATION_HOLD');self.write(self.rows)
        p=self.root/'data/advisor_sources/calendar_2022/Ke_hoach_hoc_tap_2022.pdf';p.write_bytes(p.read_bytes()+b'x');self.assertEqual(inspect_uploaded_calendar(self.root,'2022-2023','main_1')['status'],'PDF_HASH_MISMATCH')
    def test_adjustment_source(self):
        q='Định mức học phí CTĐT chuẩn khóa QH-2022 năm học 2022–2023 là bao nhiêu?';r=adjusted_standard(self.root,2022,q);self.assertIn('315.000',r['answer']);self.assertIn('11.700.000',r['answer']);self.assertNotIn('715.000',r['answer']);self.assertEqual(r['sha256'],PIN)
        for suffix in (' trước điều chỉnh',' trước tháng 3',' sinh viên nước ngoài',' chương trình TT 23',' học phí học bổng',' học phí nộp khi nào'):
            self.assertIsNone(adjusted_standard(self.root,2022,q+suffix),suffix)
        self.assertIsNone(adjusted_standard(self.root,2023,q))
    def test_adjustment_gate(self):
        q='Học phí CTĐT chuẩn QH-2022 năm học 2022–2023';self.write(self.rows+[{'doc_id':DOC}]);self.assertIsNone(adjusted_standard(self.root,2022,q));self.write(self.rows);p=self.root/REL;p.write_bytes(p.read_bytes()+b' ');self.assertIsNone(adjusted_standard(self.root,2022,q))
    def test_route(self):
        with patch('semantic_product.infer',side_effect=AssertionError('no model expected')),patch('calendar_source.Index',return_value=SimpleNamespace(errors=[],chunks=[])):
            q='Theo kế hoạch học tập UET năm học 2022–2023, học kỳ II bắt đầu ngày nào?';r,st=route(q,{},None,None,{},self.root);self.assertIn('30/01/2023',r['answer']);self.assertEqual(r['metadata']['engine_mode'],'SOURCE_TABLE')
            q='Định mức học phí CTĐT chuẩn khóa QH-2022 năm học 2022–2023 là bao nhiêu?';r,st=route(q,{},None,None,{},self.root);self.assertIn('315.000',r['answer']);self.assertEqual(r['metadata']['engine_mode'],'SOURCE_TABLE')
            r,st=route('Sang năm học 2023–2024 thì sao, vẫn khóa và CTĐT đó?',st,None,None,{},self.root);self.assertIn('279/QĐ-ĐHCN',r['answer']);self.assertNotIn('851.000',r['answer'])
    def test_actual_ledger(self):
        path=os.environ.get('CHRONOREG_ACTUAL_COVERAGE_TEST')
        if not path:self.skipTest('coverage report not supplied')
        records=json.loads(Path(path).read_text(encoding='utf8'))['hold_records'];self.write([{k:v for k,v in r.items() if v is not None} for r in records]);self.assertEqual(inspect_uploaded_calendar(self.root,'2022-2023','main_2')['status'],'READY');self.assertIsNotNone(adjusted_standard(self.root,2022,'Học phí CTĐT chuẩn khóa QH-2022 năm học 2022–2023'))
