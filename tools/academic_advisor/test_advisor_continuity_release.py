import unittest
from pathlib import Path
from unittest.mock import patch
from advisor_continuity import route,parse_table,SOURCE,admissions
from quality_workflows import snapshot

class ContinuityRelease(unittest.TestCase):
    def test_ranked_transition_and_scope(self):
        roster={'students':[{'student_id':'99000001','gpa_semester':1.0,'owed_credits':40,'drl':65},{'student_id':'99000002','gpa_semester':1.2,'owed_credits':20,'drl':66}]}
        p={'kind':'advisor_agent','topic':'class','scope':snapshot(roster),'ranked_list':True,'count':2}
        with patch('advisor_continuity.screening',return_value=({1:[('99000001','A',['GPA học kỳ thấp'],[]),('99000002','B',['tín chỉ nợ'],[])],2:[]},0)):
            q='Lập phương án hỗ trợ bạn đầu tiên trong vòng một tuần.'
            r,c=route(q,p,None,None,roster,None);self.assertEqual(c['student'],'99000001');self.assertIn('7 ngày',r['answer'])
            with patch('advisor_bridge.transition_study',return_value=({'answer':'30 phút'},c)) as f:
                self.assertIsNotNone(route('Nếu bạn ấy chỉ có 30 phút tự học mỗi ngày thì sao?',c,None,None,roster,None));self.assertEqual(f.call_args.args[1]['student'],'99000001')
            self.assertIsNone(route(q,{},None,None,roster,None))
            self.assertFalse(route(q,{**p,'scope':'stale'},None,None,roster,None)[1])
            self.assertNotIn('99000002',r['answer'])
            self.assertIsNone(route(q+' công khai cả lớp',p,None,None,roster,None))
            self.assertFalse(route(q,{**p,'ranked_list':False},None,None,roster,None)[1])
            self.assertFalse(route(q,{**p,'count':True},None,None,roster,None)[1])
            self.assertIn('danh sách',route('Lập phương án hỗ trợ bạn thứ ba trong vòng một tuần.',p,None,None,roster,None)[0]['answer'])
        with patch('advisor_continuity.screening',return_value=({1:[('99000001','A',['GPA học kỳ thấp'],[])],2:[('99000002','B',['tín chỉ nợ'],[])]},0)):
            default={**p,'count':None}
            r,c=route('Lập phương án hỗ trợ bạn thứ hai trong vòng một tuần.',default,None,None,roster,None);self.assertIn('danh sách',r['answer']);self.assertNotIn('99000002',r['answer'])
            r,c=route(q,default,None,None,roster,None);self.assertEqual(c['student'],'99000001')
    def test_invitation(self):
        roster={'students':[{'student_id':'99000001'}]};p={'kind':'student','mssv':'99000001','scope':snapshot(roster)}
        r,c=route('Soạn lời mời gặp riêng cho bạn ấy, giọng thân thiện và không gây áp lực.',p,None,None,roster,None)
        self.assertEqual(r['metadata']['advisor_intent'],'communication_draft');self.assertEqual(c['student'],'99000001');self.assertIn('Chào em',r['answer']);self.assertNotIn('GPA',r['answer'])
    def test_stream_class_to_student(self):
        import test_release_196 as fixtures
        f=fixtures.Continuity();f.setUp();self.addCleanup(f.doCleanups)
        f.roster['students'][1].update(gpa_semester=1.1,drl=65)
        r=f.ask('Cô nên ưu tiên hỗ trợ những sinh viên nào trong lớp tuần này?')
        r=f.ask('Chọn hai bạn cần gặp nhất và giải thích lý do.',r['context_token'])
        p=f.ctx.read(r['context_token']);self.assertEqual(p['count'],2);self.assertTrue(p['ranked_list']);self.assertNotIn('selected_ids',p)
        from workflow import screening
        groups,_=screening(f.roster['students']);sid=(groups[1]+groups[2])[0][0]
        self.assertNotIn(sid,str(p))
        r=f.ask('Lập phương án hỗ trợ bạn đầu tiên trong vòng một tuần.',r['context_token']);self.assertEqual(f.ctx.read(r['context_token'])['student'],sid);self.assertIn('7 ngày',r['answer'])
        r=f.ask('Nếu bạn ấy chỉ có 30 phút tự học mỗi ngày thì sao?',r['context_token']);self.assertIn('30 phút/ngày',r['answer']);self.assertEqual(f.ctx.read(r['context_token'])['student'],sid)
        r=f.ask('Soạn lời mời gặp riêng cho bạn ấy, giọng thân thiện và không gây áp lực.',r['context_token']);self.assertEqual(r['metadata']['advisor_intent'],'communication_draft');self.assertIn('Chào em',r['answer']);self.assertNotIn('GPA',r['answer'])
    def test_admission_source(self):
        import os
        root=Path(os.environ.get('CHRONOREG_TEST_REPO',Path(__file__).resolve().parents[2]))
        rows=parse_table((root/SOURCE).read_text(encoding='utf8'));self.assertEqual(len(rows),20)
        scores={x[2]:x[3] for x in rows};self.assertEqual(scores['CN8'],'26,86');self.assertEqual(scores['CN11'],'27,78');self.assertEqual(scores['CN3'],'25,41');self.assertEqual(scores['CN13'],'25,25')
        r,c=admissions('điểm chuẩn các ngành 2026',root);self.assertEqual(r['metadata']['engine_mode'],'SOURCE_TABLE');self.assertIn('20 ngành',r['answer']);self.assertEqual(c['year'],2026)
        self.assertIsNone(admissions('điểm chuẩn các ngành 2025',root));self.assertIsNone(admissions('dự đoán điểm chuẩn các ngành 2026',root))
        with patch('advisor_evidence.fresh_ledger',return_value=[{'doc_id':'uet-2026-diem-trung-tuyen-2026','content_sha256':'x'}]):self.assertEqual(admissions('điểm chuẩn các ngành 2026',root)[0]['metadata']['engine_mode'],'CONTEXT_CLARIFICATION')
if __name__=='__main__':unittest.main()
