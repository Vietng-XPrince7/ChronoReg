import unittest
from unittest.mock import patch
import experience_routes as e
from experience_transfer import route
from quality_workflows import snapshot

class ExperienceTransferTests(unittest.TestCase):
    def test_cpa_variants(self):
        _,p=e.cpa_route('Mô phỏng CPA hiện tại 2,40; đã tích lũy 80 tín chỉ; học thêm 20 tín chỉ; GPA kỳ tới 3,40. CPA mới là bao nhiêu?',{})
        a,p=e.cpa_route('Nếu kỳ sau đạt GPA 3,80 thì kết quả thay đổi thế nào?',p)
        self.assertIn('2,68',a['answer'])
        a,p=e.cpa_route('Thay bằng 10 tín chỉ thôi, còn các giả định khác giữ nguyên nhé.',p)
        self.assertIn('2,56',a['answer'])
        a,_=e.cpa_route('Nếu GPA 4,50 thì sao?',p)
        self.assertEqual(a['metadata']['simulation']['status'],'needs_inputs')
        self.assertIsNone(e.cpa_route('Thay bằng 10 tín chỉ, có đủ điều kiện học bổng không?',p))
        self.assertIsNone(e.cpa_route('Thay bằng 10 tín chỉ thôi, còn các giả định khác giữ nguyên nhé.',{}))
    def test_hypothesis_correction(self):
        from meeting_context import update_topics
        self.assertEqual(update_topics('Thực ra em ấy chưa nói là mất tự tin.', ['confidence'])[0],[])
    def test_review_scope(self):
        roster={'students':[{'student_id':'99000001'}]}
        p={'kind':'advisor_agent','topic':'study_plan','student':'99000001','scope':snapshot(roster),'minutes':25}
        q='Cuối tuần cô dựa vào đâu để biết kế hoạch đó có hiệu quả?'
        r,c=route(q,p,None,None,roster,None);self.assertIn('25 phút',r['answer']);self.assertIn('chưa có kết quả',r['answer']);self.assertEqual(c,p)
        r,c=route(q,p,'99000002',None,roster,None);self.assertEqual(c,{})
        self.assertIsNone(route(q,{},None,None,roster,None))
    def test_priority_dispatch(self):
        roster={'students':[{'student_id':'99000001'}]}
        with patch('advisor_agent.class_flow',return_value=({'answer':'fixture'},{})) as f:
            self.assertIsNotNone(route('Cô chỉ có thời gian gặp một vài bạn trong tuần này. Em giúp cô xác định nên ưu tiên ai và vì sao?',{},None,None,roster,None));f.assert_called_once()
            self.assertIsNone(route('Cô muốn công khai những bạn cần ưu tiên gặp',{},None,None,roster,None))
if __name__=='__main__':unittest.main()
