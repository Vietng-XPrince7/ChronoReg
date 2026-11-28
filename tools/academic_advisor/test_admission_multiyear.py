import os,re,unittest
from pathlib import Path
from unittest.mock import patch
from admission_multiyear import load,route,parse_2022_methods

class HistoricalAdmissionTests(unittest.TestCase):
    def setUp(self):self.root=Path(os.environ.get('CHRONOREG_TEST_REPO',Path(__file__).resolve().parents[2]))
    def test_five_sources(self):
        from advisor_evidence import fresh_ledger
        holds=fresh_ledger(self.root)
        for year,count in [(2022,17),(2023,17),(2024,17),(2025,20),(2026,20)]:
            rows,s=load(self.root,year,holds);self.assertEqual(len(rows),count);self.assertEqual(s['year'],year)
    def test_methods(self):
        r,_=route('Điểm chuẩn CN1 theo SAT năm 2022',self.root)
        self.assertIn('28,5',r['answer']);self.assertNotIn('29,15',r['answer'])
        r,_=route('Điểm chuẩn tất cả các ngành năm 2022',self.root);self.assertIn('29,15',r['answer']);self.assertEqual(re.findall(r'^\| (CN\d+) \|',r['answer'],re.M),[f'CN{i}' for i in range(1,18)])
    def test_comparison(self):
        r,_=route('So sánh điểm chuẩn CN8 từ 2022–2026',self.root)
        for marker in ('27,25','27,58','27,86','26,86'):
            self.assertIn(marker,r['answer'])
        self.assertEqual(r['answer'].count('| CN8 |'),5)
    def test_hold_and_scope(self):
        for q in ('Dự đoán điểm chuẩn CN1 năm 2026','Điểm chuẩn CN1 theo SAT năm 2024','Điểm chuẩn CN1 năm 2025 của HUTECH','Điểm chuẩn CN1 năm 2027'):
            self.assertIsNone(route(q,self.root))
        with patch('admission_multiyear.fresh_ledger',return_value=[{'doc_id':'uet-2022-diem-trung-tuyen','content_sha256':'x'}]):
            self.assertIsNone(route('Điểm chuẩn CN1 năm 2022',self.root))
    def test_bad_row(self):
        with self.assertRaises(ValueError):parse_2022_methods('|CN1|CNTT|31|20|20|20|',1)
