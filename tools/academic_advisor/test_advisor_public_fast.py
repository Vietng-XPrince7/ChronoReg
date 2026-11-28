import unittest, tempfile, json, hashlib, os
from pathlib import Path
from unittest.mock import patch
from advisor_public_fast import fee,team_outcomes,route

class PublicFastTests(unittest.TestCase):
    def test_fee_ambiguous_group(self):
        def lookup(root,q):
            return {'path':'fee.md','sha256':'a'*64,'year':2025,'answer':('CTĐT chuẩn: 3.400.000 đồng/tháng.' if 'chuẩn' in q else 'ĐMKTKT: 4.000.000 đồng/tháng.')}
        with patch('tuition.lookup_tuition',side_effect=lookup),patch('semantic_product.source_table',side_effect=lambda root,v:v):
            result=fee(Path('.'),'Học phí ngành Kỹ thuật máy tính khóa QH-2024 năm học 2025-2026?')
            self.assertIn('3.400.000',result[0]['answer']);self.assertIn('4.000.000',result[0]['answer']);self.assertIn('Chưa xác định',result[0]['answer'])
            self.assertIsNone(fee(Path('.'),'Học phí CTĐT chuẩn ngành Kỹ thuật máy tính QH-2024 năm học 2025-2026?'))
            self.assertIsNone(fee(Path('.'),'Học phí ngành CNTT QH-2024 năm học 2025-2026 miễn giảm thế nào?'))
    def test_team_outcomes(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);rel='data/raw/uet/curricula/robot.md';p=root/rel;p.parent.mkdir(parents=True);data='- **PLO1: Kiến thức.**\n- **PLO2: Kỹ năng.**\n- **PLO3: Trách nhiệm.**\n**4. Vị trí việc làm**\n';p.write_bytes(data.encode());sha=hashlib.sha256(data.encode()).hexdigest()
            (p.parent/'catalog.json').write_text(json.dumps({'records':[{'program_identifier':'ktrb','collection':'team_original_uploads','content_kind':'learning_outcomes','cohort_hint_unverified':'QH-2022 to QH-2024 (filename hint only)','doc_id':'robot','content_path':rel,'content_sha256':sha}]}),encoding='utf8')
            hold=root/'data/versioning/publication_holds.jsonl';hold.parent.mkdir(parents=True);hold.write_text('')
            q='Chuẩn đầu ra ngành Kỹ thuật Robot QH-2024 là gì?'
            result=team_outcomes(root,q);self.assertIn('PLO3',result[0]['answer']);self.assertTrue(result[0]['metadata']['reference_only']);self.assertIn('chưa xác minh',result[0]['answer'])
            self.assertIsNone(team_outcomes(root,'Chuẩn đầu ra ngành Kỹ thuật Robot QH-2026 là gì?'))
            hold.write_text(json.dumps({'doc_id':'robot','content_sha256':sha}));self.assertIsNone(team_outcomes(root,q))
            hold.write_text('');p.write_bytes(b'changed');self.assertIsNone(team_outcomes(root,q))
    def test_context_preserved(self):
        self.assertIsNone(route(Path('.'),'Học phí ngành CNTT QH-2024 năm học 2025-2026?',{'kind':'advisor_mission'}))
        self.assertIsNone(route(Path('.'),'Soạn lời mời gặp riêng cho bạn ấy',{}))
