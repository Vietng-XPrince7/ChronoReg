import unittest
from whatif import simulate,EXAMPLE,GOAL_EXAMPLE
class WhatIfTests(unittest.TestCase):
 def test_projection(self):
  r=simulate(EXAMPLE);self.assertEqual(r['projected_cpa'],'2.70');self.assertIn('2,70',r['answer']);self.assertIn('không phải xác nhận học vụ',r['answer'])
 def test_goal(self):self.assertEqual(simulate(GOAL_EXAMPLE)['required_gpa'],'4.00')
 def test_unreachable(self):
  r=simulate(GOAL_EXAMPLE.replace('2,80','3,20'));self.assertIn('vượt thang 4',r['answer'])
 def test_missing_cpa(self):self.assertEqual(simulate('Mô phỏng CPA nếu GPA hiện tại 2,5 và học thêm 15 tín chỉ')['status'],'needs_inputs')
 def test_invalid_scale(self):self.assertEqual(simulate(EXAMPLE.replace('3,50','4,50'))['status'],'needs_inputs')
 def test_duplicate(self):self.assertEqual(simulate(EXAMPLE+' CPA 3,00')['status'],'needs_inputs')
 def test_invalid_credits(self):self.assertEqual(simulate(EXAMPLE.replace('15 tín chỉ','0 tín chỉ'))['status'],'needs_inputs')
 def test_mixed_input(self):self.assertEqual(simulate(EXAMPLE+' CPA mục tiêu 3,2')['status'],'needs_inputs')
 def test_retake(self):self.assertIsNone(simulate(EXAMPLE+' học lại môn cũ'))
 def test_eligibility(self):self.assertIsNone(simulate(EXAMPLE+' có đủ điều kiện học bổng không?'))
 def test_negative(self):self.assertEqual(simulate(EXAMPLE.replace('3,50','-3,50'))['status'],'needs_inputs')
 def test_current_gpa_not_future(self):self.assertEqual(simulate(EXAMPLE.replace('GPA kỳ tới','GPA hiện tại'))['status'],'needs_inputs')
 def test_unrelated(self):self.assertIsNone(simulate('Quy trình rút học phần?'))
 def test_goal_missing(self):self.assertEqual(simulate('Mô phỏng CPA hiện tại 2,5; CPA mục tiêu 3,0')['status'],'needs_inputs')
if __name__=='__main__':unittest.main()
