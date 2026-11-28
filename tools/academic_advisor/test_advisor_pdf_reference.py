import unittest,tempfile,hashlib
from pathlib import Path
from unittest.mock import patch
import advisor_pdf_reference as a

class PdfReferenceTests(unittest.TestCase):
    def test_fee_scope_and_units(self):
        with patch.object(a,'source',return_value={'source_path':'pdf','sha256':'a'*64}):
            x=a.route(Path('.'),'Học phí thạc sĩ khóa QH-2024 năm học 2025-2026 bao nhiêu?',{})[0]['answer']
            self.assertIn('1.144.000',x);self.assertIn('3.500.000',x);self.assertNotIn('1.282.000',x)
            x=a.route(Path('.'),'Học phí tiến sĩ khóa QH-2025 năm học 2025-2026?',{})[0]['answer']
            self.assertIn('QĐ 248',x);self.assertIn('1.282.000',x);self.assertNotIn('4.200.000',x)
            for q in ('Học phí tiến sĩ năm học 2026-2027?', 'Học phí thạc sĩ QH-2024 năm học 2025-2026 của tôi?', 'Học phí tiến sĩ năm học 2025-2026 miễn giảm?', 'Học phí thạc sĩ năm học 2025-2026 QH-2027?'):
                self.assertIsNone(a.route(Path('.'),q,{}))
            self.assertIsNone(a.route(Path('.'),'Học phí thạc sĩ năm học 2025-2026?',{'kind':'student'}))
    def test_research_conflict(self):
        with tempfile.TemporaryDirectory() as t, patch.object(a,'source',return_value={'source_path':'pdf','sha256':'a'*64}):
            root=Path(t); f=root/a.SOURCES['r2025']['raw_alias'][0];f.parent.mkdir(parents=True);f.write_bytes(b'fixture')
            x=a.route(root,'Hạn đăng ký NCKH Viện TTNT năm học 2025-2026?',{})[0]['answer']
            self.assertIn('25/02/2026',x);self.assertIn('15/02/2026',x);self.assertIn('Mâu thuẫn',x)
            self.assertIsNone(a.route(root,'Lịch NCKH cấp Trường Viện TTNT năm học 2025-2026?',{}))
    def test_source_hold(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);(p/'a.pdf').write_bytes(b'pdf');(p/'a.md').write_bytes(b'md');h=lambda s:hashlib.sha256(s).hexdigest()
            with patch.dict(a.SOURCES,{'test':{'pdf':'a.pdf','sha':h(b'pdf'),'md':'a.md','md_sha':h(b'md'),'alias':'x-test','raw_alias':None}}):
                with patch('advisor_evidence.fresh_ledger',return_value=[]):self.assertEqual(a.source(p,'test')['source_path'],'a.pdf')
                with patch('advisor_evidence.fresh_ledger',return_value=[{'doc_id':'x-test','content_sha256':'z'}]):
                    with self.assertRaises(ValueError):a.source(p,'test')
                (p/'a.pdf').write_bytes(b'changed')
                with self.assertRaises(ValueError):a.source(p,'test')
