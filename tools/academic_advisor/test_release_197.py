"""Source provenance and individualized review; synthetic roster/source fixtures."""
import unittest
from unittest.mock import patch
import test_advisor_tasks_172 as tasks_fixture
import test_reviewed_sources_192 as sources_fixture
from course_planning import candidate_source,candidate_label,CandidateTable,load_candidate
import course_planning as cp
import reviewed_sources as rs
from mission_review import synthesize
from advisor_tasks import route
from quality import norm

class Evidence(unittest.TestCase):
    def test_actual_loader_provenance(self):
        f=sources_fixture.Review192();f.setUp();self.addCleanup(f.doCleanups)
        rec=f.pack['records'][0]
        roster={'major':'Công nghệ thông tin','cohort':'QH-2024'}
        with patch.object(cp,'SHA',rec['source_sha']):
            table,reason=load_candidate(f.root,roster)
            self.assertIsInstance(table,CandidateTable,reason)
            self.assertEqual(candidate_source(table)['sha256'],f.pin)
            self.assertEqual(candidate_source(table)['source_url'],rec['source_url'])
            self.assertIn('đã đối chiếu',candidate_label(table))
            self.assertIn('chưa duyệt',candidate_label(dict(table)))
            self.assertEqual(candidate_source(dict(table))['status'],'unreviewed')
            f.ledger.write_text('{"doc_id":"'+cp.DOC+'","content_sha256":"fixture"}')
            self.assertIsNone(load_candidate(f.root,roster)[0])
    def setUp(self):
        f=tasks_fixture.Tasks();f.setUp();self.root=f.root;self.roster=f.roster;self.st=f.roster['students'][0];self.table=f.table
    def test_study_risk_specific(self):
        with patch('mission_review.load_candidate',return_value=(self.table,None)):
            a,t,s=synthesize(self.st,self.roster,self.root,{'study':{'minutes':15}},[],['risks'])
            self.assertIn('ABC0001',a);self.assertIn('ABC0002',a);self.assertIn('số buổi thực hiện',a);self.assertIn('15 phút',a);self.assertIn('giảm độ khó',a)
            self.assertIn('prerequisite_planning',t);self.assertEqual(s[0]['status'],'unreviewed')
            a,t,s=synthesize(self.st,self.roster,self.root,{'study':{'minutes':15}},[],['risks','next_steps'])
            self.assertIn('ABC0002',a);self.assertIn('Việc nên làm tiếp theo',a)
    def test_source_unavailable_no_old_target(self):
        with patch('mission_review.load_candidate',return_value=(None,'hold')):
            a,t,s=synthesize(self.st,self.roster,self.root,{'study':{'minutes':15}},[],['risks'])
            self.assertNotIn('ABC0001',a);self.assertNotIn('prerequisite_planning',t);self.assertEqual(s,[])
    def test_study_source_carried_and_hypothetical(self):
        table=CandidateTable(self.table,{'source_path':'fixture.json','sha256':'fixture','source_url':'https://example.invalid','status':'reviewed_scoped','review_id':'cntt_fixture','review_scope':'fixture'})
        q='Nếu em chỉ có 15 phút tự học mỗi ngày và có thể phải đi làm, nên thử cách gì?'
        with patch('course_planning.load_candidate',return_value=(table,None)):
            r,c=route(q,norm(q),{},'99000001',None,self.roster,self.root)
            self.assertIn('đã đối chiếu',r['answer']);self.assertNotIn('Do sinh viên nói phải đi làm',r['answer']);self.assertIn('Nếu sinh viên xác nhận',r['answer']);self.assertEqual(r['metadata']['advisor_sources'],[candidate_source(table)])

if __name__=='__main__':unittest.main()
