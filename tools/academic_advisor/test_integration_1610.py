import unittest
from pathlib import Path
from unittest.mock import patch
from semantic_product import structured_input,route,execute
from quality_workflows import snapshot
from test_quality_routes import LOAD_SOURCE
from test_source_pack_166 import SOURCE
from policy_followup import return_to_study

class Integration1610(unittest.TestCase):
    root=Path('.')
    roster={'class_short':'K69-DEMO','cohort':'QH-2024 (K69)','semester':'2025.1','students':[{'student_id':'99000001','owed_credits':19}], 'courses':[]}
    def test_policy_natural_reference(self):
        state={'kind':'policy_clause','article':36,'clause':3,'instrument':'3626','exp':9999999999}
        q='Khi muốn học trở lại thì phải nộp đơn chậm nhất bao lâu trước khi hết thời hạn nghỉ?'
        with patch('policy_followup.pinned',return_value=SOURCE) as pin:
            r,_=return_to_study(q,state,self.root);self.assertIn('2 tuần',r['answer'])
            for prior,question in [({},q),(state,q+' Theo QĐ 1234.'),(state,q+' Khóa 2026.')]:
                r,_=return_to_study(question,prior,self.root);self.assertNotIn('2 tuần',r['answer'])
            pin.assert_called_once()
    def test_policy_signed_token(self):
        from conversation import add_conversation
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from types import SimpleNamespace
        from test_semantic_product import Request
        from regulation import TEXT_SHA
        server=SimpleNamespace(app=FastAPI(),_semantic_pilot=True,_get_active_roster=lambda:self.roster,_router=SimpleNamespace(route_decision=lambda q:SimpleNamespace(risk_tier='GREEN')))
        calls=[]
        def dispatch(req):
            calls.append(req.question)
            return {'answer':SOURCE['answer'],'metadata':{'engine_mode':'SOURCE_CLAUSE','sha256':TEXT_SHA},'routing':{'risk_tier':'GREEN'}}
        add_conversation(server,dispatch,Request,self.root)
        client=TestClient(server.app)
        def ask(q,token=None):
            r=client.post('/api/advisor/chat',json={'question':q,'context_token':token,'force_engine':'auto'});self.assertEqual(r.status_code,200);return r.json()
        q='Khi muốn học trở lại thì phải nộp đơn chậm nhất bao lâu trước khi hết thời hạn nghỉ?'
        with patch('policy_followup.pinned',return_value=SOURCE):
            first=ask('Theo QĐ 3626, xin nghỉ học tạm thời vì lý do cá nhân?')
            self.assertTrue(first['context_token']);self.assertIn('2 tuần',ask(q,first['context_token'])['answer']);self.assertNotIn('2 tuần',ask(q)['answer']);self.assertNotIn('2 tuần',ask(q,first['context_token']+'x')['answer']);self.assertEqual(len(calls),1)
    def test_interval_both_dates(self):
        hit={'excerpt':'Học kỳ I (22/08/2022 – 15/01/2023) (khoảng thời gian học kỳ, không phải ngày học chuyên môn từng khóa)','scope':'đại học','source_path':'fixture','source_url':'https://example.invalid','sha256':'fixture','doc_id':'fixture'}
        q='Theo kế hoạch học tập đại học UET 2022–2023, học kỳ I bắt đầu và kết thúc khi nào?'
        with patch('calendar_source.lookup_start',return_value=[hit]),patch('semantic_product.infer',side_effect=AssertionError('no model')):
            r,_=route(q,{},None,None,self.roster,self.root);self.assertIn('15/01/2023',r['answer']);self.assertIn('22/08/2022',r['answer'])
        with patch('calendar_source.lookup_start',return_value=[dict(hit,excerpt='Học kỳ I bắt đầu ngày 22/08/2022')]):
            r=execute({'intent':'calendar','slots':{'academic_year':'2022-2023','semester':'main_1'}},self.roster,self.root,q);self.assertNotIn('15/01/2023',r['answer']);self.assertEqual(r['metadata']['engine_mode'],'CONTEXT_CLARIFICATION')
    def test_fee_anchor_and_follow(self):
        q='Năm học 2024–2025, sinh viên QH-2024 CTĐT chuẩn có định mức học lại bao nhiêu đồng một tín chỉ?'
        def lookup(root,q):
            return {'answer':'869.000 đồng/tín chỉ' if '2024-2025' in q else '924.000 đồng/tín chỉ','path':'fixture','sha256':'fixture'}
        with patch('tuition.lookup_tuition',side_effect=lookup),patch('semantic_product.source_table',side_effect=lambda root,v: {'answer':v['answer'],'metadata':{'engine_mode':'SOURCE_TABLE'}}),patch('semantic_product.infer',side_effect=AssertionError('no model')):
            r,st=route(q,{},None,None,self.roster,self.root);self.assertIn('869.000',r['answer'])
            r,st=route('Chuyển sang năm học 2025–2026, giữ nguyên khóa và CTĐT.',st,None,None,self.roster,self.root);self.assertIn('924.000',r['answer']);self.assertEqual(st['plan']['slots']['cohort'],2024)
    def test_historical_comparison(self):
        state={'kind':'semantic_task','scope':snapshot(self.roster),'plan':{'intent':'tuition','slots':{'cohort':2022,'academic_year':'2022-2023','tuition_scope':'standard'}}}
        with patch('semantic_product.infer',side_effect=AssertionError('no model')):
            r,st=route('Nếu muốn biết mức ban đầu trước điều chỉnh thì có thể dùng ngay con số vừa nêu không?',state,None,None,self.roster,self.root);self.assertIn('không dùng mức điều chỉnh',r['answer']);self.assertEqual(st,state)
    def test_credit_cap(self):
        q='Sinh viên khóa K69, GPA học kỳ trước 1,8, chưa thuộc diện buộc thôi học, tải chuẩn bình quân 10 tín chỉ mỗi học kỳ chính, tất cả học phần được tính tải. Nếu hai giới hạn cùng áp dụng thì tối đa bao nhiêu?'
        with patch('semantic_product.pinned',return_value=LOAD_SOURCE),patch('semantic_product.infer',side_effect=AssertionError('no model')):
            r,st=route(q,{},None,None,self.roster,self.root);self.assertIn('min(15, 18) = 15',r['answer'])
    def test_retake_constraint(self):
        q='Lập phương án học lại giả định cho sinh viên demo 99000001, mỗi đợt không quá 12 tín chỉ, tôn trọng tiên quyết. Nêu phần chưa đủ căn cứ.'
        p=structured_input(q,None,self.root);self.assertEqual(p['slots'],{'student':'99000001','budget':12});self.assertIsNone(structured_input(q+' Ưu tiên ABC1001 vào đợt đầu.',None,self.root))
if __name__=='__main__':unittest.main()
