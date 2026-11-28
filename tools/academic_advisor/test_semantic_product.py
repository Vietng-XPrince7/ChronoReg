import unittest,tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from conversation import add_conversation
from semantic_product import route,guard,execute,candidate
from semantic_planner import checked_plan
from schedule_optimizer import optimize_rounds,validate
from test_quality_routes import RANK_SOURCE,LOAD_SOURCE

class Request(BaseModel):
    question:str;force_engine:str|None=None;mssv:str|None=None

def raw(intent,reuse=False,**slots):return {'intent':intent,'reuse':reuse,'slots':slots}
class SemanticProductTests(unittest.TestCase):
    def setUp(self):
        self.roster={'class_short':'K69-DEMO','cohort':'QH-2024 (K69)','semester':'2025.1','students':[{'student_id':'99000001','owed_credits':19,'accumulated_credits':38,'gpa_semester':1.8},{'student_id':'99000002','owed_credits':32,'accumulated_credits':50,'gpa_semester':1.2}], 'courses':[]}
        self.root=Path('.')
    def test_negation_and_correction(self):
        q='Khóa 2024 dự kiến bằng Giỏi; học lại 9 trên tổng 150 tín chỉ, không bị kỷ luật.'
        with patch('semantic_product.infer',return_value=raw('rank_check',cohort=2024,rank='good',total_credits=150,repeat_credits=9,discipline=True)),patch('semantic_product.pinned',return_value=RANK_SOURCE):
            r,st=route(q,{},None,None,self.roster,self.root);self.assertFalse(st['plan']['slots']['discipline']);self.assertIn('6.00%',r['answer'])
        with patch('semantic_product.infer',return_value=raw('rank_check',True,repeat_credits=5,discipline=True)),patch('semantic_product.pinned',return_value=RANK_SOURCE):
            r,st=route('Số phải học lại thực ra là 5 tín chỉ, giữ nguyên điều kiện.',st,None,None,self.roster,self.root);self.assertFalse(st['plan']['slots']['discipline']);self.assertIn('3.33%',r['answer']);self.assertIn('chưa thỏa',r['answer'])
    def test_guard_conflicting_number(self):
        p={'intent':'rank_check','slots':{'cohort':2024,'total_credits':140,'repeat_credits':12}}
        with self.assertRaises(ValueError):guard(p,'Khóa 2024, học lại 8 trên tổng 140 tín chỉ.',None)
    def test_cap_math(self):
        q='K69: GPA kỳ trước là 1,7. Kế hoạch chuẩn trung bình 10 tín chỉ mỗi kỳ chính, không thuộc diện buộc thôi học, mọi môn đều tính tải. Xét trần.'
        model=raw('credit_cap',cohort=2024,gpa=1.7,gpa_kind='semester',standard_credits=10,semester='main',not_dismissed=True,all_counted=True)
        with patch('semantic_product.infer',return_value=model),patch('semantic_product.pinned',return_value=LOAD_SOURCE):
            r,st=route(q,{},None,None,self.roster,self.root);self.assertIn('min(15, 18) = 15',r['answer'])
        with patch('semantic_product.infer',return_value=raw('credit_cap',True,standard_credits=14)),patch('semantic_product.pinned',return_value=LOAD_SOURCE):
            r,st=route('Cô sửa lại, trung bình là 14 tín chỉ. Những điều kiện khác giữ nguyên.',st,None,None,self.roster,self.root);self.assertIn('min(21, 18) = 18',r['answer'])
    def test_metric_confusion_compare(self):
        with patch('semantic_product.infer',return_value=raw('student_lookup',student='99000001',metric='cumulative_gpa')) as call:
            r,st=route('Tra tín chỉ đã tích lũy của 99000001.',{},None,None,self.roster,self.root);self.assertIn('38 tín chỉ tích lũy',r['answer']);self.assertEqual(call.call_args.args[1],None)
        with patch('semantic_product.infer',return_value=raw('student_compare',True,other_student='99000002',metric='cumulative_gpa')):
            r,st=route('So với 99000002 thì sao?',st,None,None,self.roster,self.root);self.assertIn('50 tín chỉ tích lũy',r['answer']);self.assertIn('cao hơn 12',r['answer'])
    def test_scope_and_no_cross_class(self):
        with patch('semantic_product.infer',return_value=raw('student_lookup',student='99000001',metric='debt')):
            r,st=route('Tín chỉ nợ của 99000001?',{},None,None,self.roster,self.root);self.assertIn('19 tín chỉ nợ',r['answer'])
        with patch('semantic_product.infer') as m:
            r,data=route('Cô chuyển sang lớp K70 chưa nhập. Có so sánh tiếp được không?',st,None,None,self.roster,self.root);self.assertNotIn('19',r['answer']);self.assertEqual(data,{});m.assert_not_called()
            r,data=route('So với 99000002?',st,None,None,{**self.roster,'semester':'new'},self.root);self.assertEqual(data,{});m.assert_not_called()
    def test_admission_method_guard(self):
        with patch('semantic_product.lookup') as m:
            r=execute({'intent':'admissions','slots':{'year':2025,'program':'CNTT','method':'THPT'}},self.roster,self.root);self.assertIn('chưa có bảng nguồn',r['answer']);m.assert_not_called()
    def test_held_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'data/versioning';p.mkdir(parents=True);(p/'publication_holds.jsonl').write_text('{"content_sha256":"abc"}\n')
            with patch('semantic_product.lookup',return_value={'sha256':'abc','path':'x.md','year':2024,'answer':'secret','row_count':1}),patch('semantic_product.infer',return_value=raw('admissions',year=2024,program='CNTT')):
                r,st=route('Điểm chuẩn CNTT năm 2024?',{},None,None,self.roster,Path(tmp));self.assertNotIn('secret',r['answer']);self.assertEqual(st,{})
    def test_unverified_cohort(self):
        with patch('semantic_product.pinned') as m:
            r=execute({'intent':'rank_check','slots':{'cohort':2026}},self.roster,self.root);m.assert_not_called();self.assertIn('đúng khóa',r['answer'])
    def test_model_error_no_fallback(self):
        with patch('semantic_product.infer',side_effect=OSError('local unavailable')):
            r,st=route('Điểm chuẩn CNTT năm 2024?',{},None,None,self.roster,self.root);self.assertEqual(st,{});self.assertIn('chưa xác minh',r['answer'])
    def test_first_course_solver(self):
        credits={'ABC1001':3,'ABC1002':4,'ABC1003':3};deps={'ABC1001':[],'ABC1002':[],'ABC1003':['ABC1001']}
        r=optimize_rounds(credits,deps,7,first_course='ABC1001');self.assertIn('ABC1001',r['rounds'][0]);self.assertTrue(validate(r,credits,deps,7));self.assertEqual(r['round_count'],2)
        with self.assertRaises(ValueError):optimize_rounds(credits,deps,7,first_course='ABC1003')
    def test_actual_conversation_route_and_isolation(self):
        calls=[]
        def legacy(req):calls.append(req.question);return {'answer':'legacy','metadata':{},'routing':{'risk_tier':'RED' if 'ngoại lệ' in req.question else 'GREEN'}}
        s=SimpleNamespace(app=FastAPI(),_semantic_pilot=True,_router=SimpleNamespace(route_decision=lambda q:SimpleNamespace(risk_tier='RED' if 'ngoại lệ' in q else 'GREEN')),_get_active_roster=lambda:self.roster)
        add_conversation(s,legacy,Request,self.root);c=TestClient(s.app)
        def ask(q,**kw):return c.post('/api/advisor/chat',json={'question':q,**kw}).json()
        with patch('semantic_product.infer',side_effect=[raw('student_lookup',student='99000001',metric='debt'),raw('student_compare',True,other_student='99000002'),raw('student_lookup',metric='debt')]) as m:
            a=ask('Tín chỉ nợ của 99000001?');self.assertTrue(a['context_token']);self.assertIn('19 tín chỉ nợ',a['answer']);self.assertTrue(a['metadata']['semantic_pilot'])
            b=ask('So với 99000002?',context_token=a['context_token']);self.assertIn('cao hơn 13',b['answer']);self.assertEqual(m.call_count,1);self.assertIsNone(b['metadata']['semantic_planner_model'])
            z=ask('Bạn đó còn nợ bao nhiêu tín chỉ?',context_token=a['context_token']+'x');self.assertNotIn('19',z['answer']);self.assertFalse(z.get('context_token'))
            self.assertEqual(ask('Tín chỉ nợ của 99000001?',force_engine='continual_lora')['answer'],'legacy');self.assertEqual(ask('ngoại lệ điểm chuẩn 2024')['routing']['risk_tier'],'RED')
            self.assertEqual(m.call_count,1)
    def test_legacy_mode_off(self):
        s=SimpleNamespace(app=FastAPI(),_semantic_pilot=False,_router=SimpleNamespace(route_decision=lambda q:SimpleNamespace(risk_tier='GREEN')),_get_active_roster=lambda:self.roster)
        add_conversation(s,lambda req:{'answer':'legacy','metadata':{},'routing':{'risk_tier':'GREEN'}},Request,self.root)
        with patch('semantic_product.infer') as m:
            a=TestClient(s.app).post('/api/advisor/chat',json={'question':'Điểm chuẩn CNTT năm 2024?'}).json();self.assertEqual(a['answer'],'legacy');m.assert_not_called()
if __name__=='__main__':unittest.main()
