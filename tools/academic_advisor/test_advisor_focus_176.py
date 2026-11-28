"""Tests for independent focus relevance and lossless source presentation.
Fixtures are synthetic except the explicitly identified report replay."""
import unittest
from advisor_evidence import Passage, source_segments, passage_spans, sentence_spans, retrieve
from advisor_composer import assess_focus, compose_evidence
from test_advisor_evidence_173 import EvidenceTests
from unittest.mock import patch

class FocusTests(unittest.TestCase):
    def test_preserve_paragraph_boundary_and_reject_wrong_focus(self):
        # Source-shaped fixture: unpunctuated award list, separate body paragraph.
        raw='2. Mức điểm thưởng:\n\nGiải nhất: 0,20 điểm\nGiải nhì: 0,15 điểm\n\nNếu công trình nghiên cứu khoa học do nhiều sinh viên cùng thực hiện thì điểm thưởng được chia đều cho số sinh viên cùng tham gia.\n\nĐối với sinh viên có công bố quốc tế, mức thưởng không quá 0,2 điểm.'
        spans=source_segments(raw); self.assertEqual(len(spans),4)
        p=Passage(' '.join(raw.split()),'Điều thử nghiệm','p','h','','',32,2,spans)
        q='Nếu nhiều sinh viên cùng thực hiện một công trình nghiên cứu khoa học thì điểm thưởng chia như thế nào?'
        d=assess_focus(q,passage_spans(p),spans[-1]);self.assertEqual(d,('selector_disagrees',spans[-2]))
        answer=compose_evidence(p,spans,d)
        self.assertIn('**'+spans[-2]+'**',answer);self.assertNotIn('**'+spans[-1]+'**',answer)
        self.assertFalse(answer.startswith('Dạ cô, Đối với'));self.assertIn(spans[-1],answer)
        self.assertTrue(all(x in answer for x in spans))
    def test_agreement_no_duplicate_and_all_conditions(self):
        s=['1. Người học phải nộp hồ sơ hợp lệ.', 'Thời hạn xử lý giấy xác nhận là 7 ngày làm việc kể từ ngày nhận hồ sơ.', 'Trường hợp thiếu tài liệu, thời hạn tính lại từ khi hồ sơ hợp lệ.']
        p=Passage(' '.join(s),'Điều thử nghiệm','p','h','','',segments=tuple(s))
        d=assess_focus('Thời hạn xử lý giấy xác nhận bao lâu?',s,s[1]);self.assertEqual(d,('agreed_focus',s[1]))
        a=compose_evidence(p,s,d);self.assertEqual(a.count(s[1]),1);self.assertIn(s[0],a);self.assertIn(s[2],a)
    def test_multiple_conditions_whole_clause(self):
        s=['1. Sinh viên phải hoàn thành hồ sơ.', 'Sinh viên phải đáp ứng điều kiện đầu vào.', 'Sinh viên phải nộp học phí.']
        p=Passage(' '.join(s),'Điều thử nghiệm','p','h','','')
        d=assess_focus('Sinh viên phải đáp ứng những điều kiện gì?',s,s[1]);self.assertEqual(d,('whole_clause',None));a=compose_evidence(p,s,d);self.assertTrue(all(x in a for x in s))
    def test_ambiguous_and_missing_focus(self):
        s=['Thời hạn đăng ký là 7 ngày.', 'Thời hạn đăng ký là 10 ngày.']
        self.assertEqual(assess_focus('Thời hạn đăng ký bao lâu?',s,s[1]),('ambiguous_focus',None))
        self.assertEqual(assess_focus('?',s,s[0]),('no_focus',None))
    def test_source_layout_integrity(self):
        p=Passage('Nội dung nguồn đầy đủ.','Điều thử nghiệm','p','h','','',segments=('Tự bịa.',))
        self.assertEqual(passage_spans(p),[p.text]);self.assertNotIn('Tự bịa',compose_evidence(p,['Tự bịa.'],('agreed_focus','Tự bịa.')))
    def test_enumeration_readability(self):
        p=Passage('1. Điều kiện: a) Đúng đối tượng; b) Đủ hồ sơ; c) Nộp đúng hạn.','Điều thử nghiệm','p','h','','')
        a=compose_evidence(p,[p.text],('whole_clause',None));self.assertIn('\na) Đúng đối tượng;\nb) Đủ hồ sơ;\nc) Nộp đúng hạn.',a)

class EvidenceFocusIntegration(EvidenceTests):
    def test_retrieval_refuses_irrelevant_lead(self):
        raw='1. Sinh viên phải nộp hồ sơ đầy đủ.\n\nKết quả điểm bộ phận phải được thông báo chậm nhất 7 ngày làm việc sau ngày kiểm tra.\n\nGiảng viên bố trí phòng thi theo quy định.'
        a={38:('Kiểm tra đánh giá',raw)}
        q='Theo QĐ 3626, thông báo kết quả điểm bộ phận sau ngày kiểm tra trong bao lâu?'
        with patch('advisor_evidence.read_articles',return_value=(a,'fixture')):
            r,c=retrieve(q,self.index,True,lambda q,ps:(ps[0],ps[0].segments[-1]))
            self.assertEqual(r['metadata']['focus_review'],'selector_disagrees');self.assertIn('**Kết quả điểm bộ phận',r['answer']);self.assertFalse(r['answer'].startswith('Dạ cô, Giảng viên bố trí'));self.assertEqual(r['metadata']['advisor_evidence'],' '.join(raw.split()));self.assertEqual(c['article'],38)

if __name__=='__main__':unittest.main()
