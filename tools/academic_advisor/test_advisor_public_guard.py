import unittest
from unittest.mock import patch
from pathlib import Path
import advisor_public_guard as g

class PublicGuardTests(unittest.TestCase):
    def test_country_phrase(self):
        q='Yêu cầu ngoại ngữ khi dự tuyển tiến sĩ UET năm 2026 ở bậc mấy với công dân Việt Nam dùng chứng chỉ?'
        self.assertEqual(g.guard_kind(q),'pg')
        self.assertIsNone(g.guard_kind(q+' hồ sơ của tôi'))
        self.assertIsNone(g.guard_kind(q+' MSSV 99000001'))
        self.assertIsNone(g.guard_kind(q+' viết thư'))
        with patch('advisor_public_sections.postgraduate_language',return_value=({'answer':'Bậc 4'},{})) as f:
            self.assertEqual(g.route(Path('.'),q,{})[0]['answer'],'Bậc 4');f.assert_called_once()
            self.assertIsNone(g.route(Path('.'),q,{'kind':'student'}))
    def test_cpa_scope(self):
        q='Theo QĐ 3626, sinh viên nghỉ học tạm thời vì lý do cá nhân cần CPA tối thiểu bao nhiêu?'
        self.assertEqual(g.guard_kind(q),'cpa')
        for x in (' CPA của em',' QH-2024',' giả sử',' hiệu lực hiện nay'):
            self.assertIsNone(g.guard_kind(q+x))
        t='3. Sinh viên được xin nghỉ học tạm thời.\n\nd) Vì lý do cá nhân khác nhưng phải học tối thiểu 01 học kỳ và phải đạt điểm trung\nbình chung tích lũy tổi thiểu 2,0.\n\nThời gian nghỉ.'
        with patch('advisor_evidence.fresh_ledger',return_value=[]),patch('advisor_evidence.blocked_qd',return_value=False),patch('regulation.read_articles',return_value=({36:('Quyền lợi',t)},'a'*64)),patch('regulation.clause',return_value=t),patch('quality_routes.source_response',side_effect=lambda a,b,c:{'answer':a}):
            self.assertIn('**2,0**',g.route(Path('.'),q,{})[0]['answer'])
            with patch('advisor_evidence.blocked_qd',return_value=True):self.assertIsNone(g.route(Path('.'),q,{}))
    def test_future(self):
        q='Cho biết điểm chuẩn chính thức CN8 UET năm 2035. Hỏi số đã công bố, không dự báo.'
        self.assertEqual(g.guard_kind(q),'outside')
        self.assertIsNone(g.guard_kind('Dự báo điểm chuẩn chính thức UET năm 2035'))
        self.assertIsNone(g.guard_kind(q.replace('2035','2025')))
        self.assertIsNone(g.guard_kind(q+' và 2024'))
        with patch('quality_routes.response',side_effect=lambda a,b,c,d:{'answer':a,'metadata':{}}):
            self.assertEqual(g.route(Path('.'),q,{})[0]['metadata']['engine_mode'],'CONTEXT_CLARIFICATION')
