"""HTTP regression: helper success alone does not prove correct dispatch."""
import unittest,tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from conversation import add_conversation
from grounded_contract import grounded,plan

class ExperienceFix5(unittest.TestCase):
    def test_signed_cpa_yellow_followup(self):
        class Router:
            def route_decision(self,q):
                return SimpleNamespace(risk_tier='RED' if 'ngoại lệ' in q else 'YELLOW' if 'thay đổi' in q else 'GREEN')
        calls=[]
        def dispatch(req):
            calls.append(req.question)
            return {'answer':'legacy sentinel','routing':{'risk_tier':'RED'},'metadata':{}}
        s=SimpleNamespace(app=FastAPI(),_router=Router())
        with tempfile.TemporaryDirectory() as d, patch('advisor_decision.route',return_value=None):
            add_conversation(s,dispatch,SimpleNamespace,Path(d))
            c=TestClient(s.app)
            def ask(q,t=None,**kw):
                r=c.post('/api/advisor/chat',json={'question':q,'experience':'advisor','context_token':t,**kw});self.assertEqual(r.status_code,200);return r.json()
            r=ask('Mô phỏng CPA hiện tại 2,40; đã tích lũy 80 tín chỉ; học thêm 20 tín chỉ; GPA kỳ tới 3,40. CPA mới là bao nhiêu?')
            self.assertIn('2,60',r['answer']);t=r['context_token'];self.assertTrue(t)
            r=ask('Nếu kỳ sau đạt GPA 3,80 thì kết quả thay đổi thế nào?',t)
            self.assertIn('2,68',r['answer']);self.assertEqual(r['routing']['risk_tier'],'YELLOW');self.assertTrue(r['context_token'])
            r=ask('Thay bằng 10 tín chỉ thôi, còn các giả định khác giữ nguyên nhé.',r['context_token']);self.assertIn('2,56',r['answer'])
            t=r['context_token'];r=ask('Nếu GPA 4,50 thì sao?',t);self.assertEqual(r['metadata']['simulation']['status'],'needs_inputs')
            self.assertEqual(calls,[])
            r=ask('Nếu GPA 3,80 thì thay đổi thế nào?',None);self.assertNotEqual(r.get('metadata',{}).get('engine_mode'),'ADVISOR_SIMULATION')
            r=ask('Nếu GPA 3,80 thì thay đổi thế nào?',t+'x');self.assertNotEqual(r.get('metadata',{}).get('engine_mode'),'ADVISOR_SIMULATION')
            r=ask('Nếu GPA 3,80 thì có ngoại lệ không?',t);self.assertEqual(r['answer'],'legacy sentinel')
            r=ask('Nếu GPA 3,80 thì thay đổi thế nào?',t,force_engine='chrono_rag');self.assertEqual(r['answer'],'legacy sentinel')
    def test_new_review_phrasing(self):
        p=plan('study_plan',student='99000001',minutes=25,days=7)
        for q in ('Cuối tuần cô dựa vào đâu để biết kế hoạch đó có hiệu quả?', 'Sau đợt thử đánh giá phương án bằng tiêu chí nào?'):
            self.assertEqual(grounded({'action':'study_review'},q,p),plan('study_review',**p['args']))
        with self.assertRaises(ValueError):grounded({'action':'study_review'},'Đánh giá kế hoạch 35 phút',p)
    def test_legacy_mission_review_not_intercepted(self):
        from experience_transfer import route
        from quality_workflows import snapshot
        roster={'students':[{'student_id':'99000001'}]}; sig=snapshot(roster)
        p={'kind':'advisor_mission','student':'99000001','scope':sig,'states':{'study':{'kind':'advisor_agent','topic':'study_plan','student':'99000001','scope':sig,'minutes':25}}}
        for q in ('Em đánh giá xem phương án này có gì chưa chắc chắn, cô cần kiểm tra gì trước?', 'Cuối tuần cô dựa vào đâu để biết kế hoạch đó có hiệu quả?'):
            self.assertIsNone(route(q,p,None,None,roster,None))
if __name__=='__main__':unittest.main()
