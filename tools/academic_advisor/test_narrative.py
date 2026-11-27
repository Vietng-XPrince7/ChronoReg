import json,unittest
from test_knowledge import Backend
from narrative import present,validate

class NarrativeTests(unittest.TestCase):
    def setUp(self):
        self.backend=Backend()
        self.source='Tham chiếu Quyết định 3626/QĐ-ĐHQGHN, cần đối chiếu phạm vi.\nViệc rút bớt học phần chỉ được chấp nhận trong 2 tuần kể từ đầu học kỳ chính, 1 tuần kể từ đầu học kỳ phụ và được trả lại học phí.'
        self.pred={'engine_mode':'SOURCE_CLAUSE','predicted_answer':self.source,'model_name':None,'latency_ms':0}
        self.payload={'claims':[{'text':'Sinh viên cần xin rút học phần trong 2 tuần đầu kỳ chính hoặc 1 tuần đầu kỳ phụ.','quote':self.source.split('\n')[1]}],'advice':['Giảng viên nên hướng dẫn sinh viên liên hệ Phòng Đào tạo để kiểm tra thủ tục.']}
    def run_answer(self,**kw):
        self.backend.text=json.dumps(self.payload,ensure_ascii=False);return present(self.backend,'Rút học phần như thế nào?',self.pred,**kw)
    def test_valid(self):
        r=self.run_answer();self.assertEqual(r['presentation_mode'],'LORA_ADVISOR_NARRATIVE');self.assertEqual(r['model_name'],'chronoreg-lora:7b');self.assertEqual(r['advisor_evidence'],self.source);self.assertIn('Đề xuất cho cố vấn',r['predicted_answer']);self.assertIn('2 tuần',r['predicted_answer']);self.assertEqual(self.backend.calls[0]['format'],'json')
    def test_quote_scope(self):
        self.payload['claims'][0]['text']='Rút học phần trong 3626 tuần.';r=self.run_answer();self.assertEqual(r['predicted_answer'],self.source);self.assertEqual(r['presentation_mode'],'SOURCE_FALLBACK');self.assertIsNone(r['model_name'])
    def test_fake_quote(self):
        self.payload['claims'][0]['quote']='Đoạn trích không có trong nguồn.';self.assertEqual(self.run_answer()['predicted_answer'],self.source)
    def test_numeric_advice(self):
        self.payload['advice']=['Đăng ký 25 tín chỉ.'];self.assertEqual(self.run_answer()['predicted_answer'],self.source)
    def test_truncated(self):
        self.backend.reason='length';self.assertEqual(self.run_answer()['presentation_mode'],'SOURCE_FALLBACK')
    def test_personal_guard(self):
        self.pred={'engine_mode':'ADVISOR_PLAN','predicted_answer':'Sinh viên A — 24020001. GPA học kỳ: 1.5. CPA độc lập chưa xác nhận.\nLộ trình đề xuất (không phải lịch học chính thức):\n1. Trao đổi với cố vấn.','roadmap':[{'title':'Trao đổi','detail':'Rà hồ sơ'}]}
        bundle={'student_id':'24020001','roster_obj':{'students':[{'full_name':'Sinh viên A','student_id':'24020001'}]}}
        self.payload={'claims':[{'text':'GPA học kỳ 1,5 cần được rà soát.','quote':'GPA học kỳ: 1.5. CPA độc lập chưa xác nhận.'}],'advice':['Trao đổi với sinh viên về khó khăn khi học.']}
        r=self.run_answer(bundle=bundle);self.assertEqual(r['presentation_mode'],'LORA_ADVISOR_NARRATIVE');self.assertIn('CPA độc lập chưa xác nhận',r['predicted_answer']);self.assertNotIn('24020001',self.backend.calls[0]['messages'][1]['content']);self.assertEqual(r['roadmap'],self.pred['roadmap'])
        self.payload['advice']=['Sinh viên đủ điều kiện học vượt.'];self.assertEqual(self.run_answer(bundle=bundle)['presentation_mode'],'SOURCE_FALLBACK')
    def test_conflict(self):
        p={'engine_mode':'KNOWLEDGE_EXCERPTS','predicted_answer':'Nguồn có mốc chưa thống nhất; cần hỏi đơn vị ban hành.\n**Chú ý về hai mốc khác nhau trong nguồn:** Bảng ghi 25/02/2026; hướng dẫn ghi 15/02/2026.'};r=present(self.backend,'Hạn đăng ký?',p);self.assertIn('25/02/2026',r['predicted_answer']);self.assertIn('15/02/2026',r['predicted_answer']);self.assertFalse(self.backend.calls);self.assertEqual(r['advisor_evidence'],p['predicted_answer'])
    def test_unchanged_nonproduct(self):
        p={'engine_mode':'SOURCE_TABLE','predicted_answer':'20 ngành'};self.assertIs(p,present(self.backend,'Điểm chuẩn?',p));self.assertFalse(self.backend.calls)

class ReferenceTests(unittest.TestCase):
    setUp=NarrativeTests.setUp
    run_answer=NarrativeTests.run_answer
    def test_reference_without_copy(self):
        self.payload['claims'][0].pop('quote');self.payload['claims'][0]['refs']=['E02']
        r=self.run_answer();self.assertEqual(r['presentation_mode'],'LORA_ADVISOR_NARRATIVE');self.assertEqual(r['advisor_quote_checks'],[self.source.split('\n')[1]]);self.assertIn('[E02]',self.backend.calls[0]['messages'][1]['content'])
    def test_unknown_reference(self):
        self.payload['claims'][0].pop('quote');self.payload['claims'][0]['refs']=['E99']
        r=self.run_answer();self.assertEqual(r['presentation_mode'],'SOURCE_FALLBACK');self.assertEqual(r['narrative_diagnostics'],['unknown evidence reference']*2);self.assertEqual(r['narrative_attempts'],2)
    def test_reference_numeric_scope(self):
        self.payload['claims'][0]={'text':'Thời hạn rút là 3626 tuần.','refs':['E02']}
        r=self.run_answer();self.assertEqual(r['presentation_mode'],'SOURCE_FALLBACK');self.assertIn('number unsupported by cited passage',r['narrative_diagnostics'])
    def test_repair(self):
        self.payload['claims'][0].pop('quote');self.payload['claims'][0]['refs']=['E02']
        valid=json.dumps(self.payload,ensure_ascii=False);responses=iter(['not json',valid]);self.backend.json=lambda:{'message':{'content':next(responses)},'done_reason':'stop'}
        r=self.run_answer();self.assertEqual(r['presentation_mode'],'LORA_ADVISOR_NARRATIVE');self.assertEqual(r['narrative_attempts'],2);self.assertEqual(r['narrative_diagnostics'],['invalid_json'])
