"""Targeted transfer checks; the full repository suite must still run."""
import unittest
from whatif import simulate
from stream_chat import install_stream
from advisor_draft import route
from quality import norm

Q='Giả sử GPA tích lũy 2,50 với 60 tín chỉ, kỳ tới học 15 tín chỉ đạt GPA 3,50. CPA mới là bao nhiêu?'
class ExperienceFixTests(unittest.TestCase):
    def test_natural_gpa(self):
        for q in (Q,Q.replace('với','trên').replace('kỳ tới','học kỳ sau'),Q.replace('GPA tích lũy','CPA').replace('đạt GPA','có GPA')):
            self.assertEqual(simulate(q)['projected_cpa'],'2.70')
    def test_invalid_natural(self):
        for q in (Q.replace('3,50','4,50'),Q.replace('60 tín chỉ','0 tín chỉ'),Q+'; đã tích lũy 30 tín chỉ',Q.replace('kỳ tới','kỳ trước')):
            self.assertEqual(simulate(q)['status'],'needs_inputs')
        self.assertIsNone(simulate(Q+' học lại môn cũ'))
    def test_public_revision(self):
        roster={'students':[],'courses':[]}
        q='Viết giúp cô một thông báo ngắn mời cả lớp trao đổi về việc học, không nêu tên hay điểm của ai.'
        a,p=route(q,norm(q),{},None,None,roster)
        q='Rút gọn thông báo vừa rồi, giữ giọng lịch sự.'
        b,p2=route(q,norm(q),p,None,None,roster)
        self.assertLess(len(b['answer'].split()),len(a['answer'].split()))
        self.assertIn('việc riêng',b['answer'])
        self.assertEqual(p2['audience'],'class')
        self.assertNotIn('student',p2)
if __name__=='__main__': unittest.main()
