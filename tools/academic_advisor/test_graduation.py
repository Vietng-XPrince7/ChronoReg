import unittest,os,tempfile
from pathlib import Path
from types import SimpleNamespace
from regulation import selection,lookup_regulation,TEXT
from knowledge import Index
from presentation import present
ROOT=Path(os.environ['CHRONOREG_TEST_REPO'])
class GraduationTests(unittest.TestCase):
 def test_colloquial(self):
  for q in ['tôi bị trượt 1 môn có bị hạ bằng k','Rớt môn có bị hạ loại bằng không?','Học lại có bị giảm hạng tốt nghiệp không?','K69 bị trượt một môn có bị hạ bằng không?']:
   self.assertEqual(selection(q),[(47,7)])
   result=lookup_regulation(ROOT,q);self.assertIn('vượt quá 5%',result['answer'])
   p=present(SimpleNamespace(lora_model='disabled'),q,{'engine_mode':'SOURCE_CLAUSE','predicted_answer':result['answer']})
   self.assertIn('vượt quá 5%',p['predicted_answer']);self.assertIn('Giỏi hoặc Xuất sắc',p['predicted_answer']);self.assertIn('Điều 47',p['predicted_answer'])
 def test_ranking_scope(self):
  self.assertEqual(selection('Xếp loại tốt nghiệp như thế nào?'),[(47,5)])
  self.assertIn('3,60',lookup_regulation(ROOT,'Xếp loại tốt nghiệp như thế nào?')['answer'])
  for q in ['K71 học lại có bị hạ bằng không?','QH-2026 trượt môn có hạ bằng?','Thông tư 56/2026 hạ hạng tốt nghiệp?','K66 trượt môn có hạ bằng?']:
   self.assertEqual(selection(q),[],q)
 def test_clean_index(self):
  idx=Index(ROOT);hits=idx.search('tôi bị trượt 1 môn có bị hạ bằng k')
  self.assertTrue(any(c.path==TEXT and '5%' in c.text for c in hits),[(c.path,c.heading) for c in hits])
  self.assertTrue(any(c.path==TEXT for c in idx.chunks))
 def test_distractors(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'data/raw/uet/markdown';p.mkdir(parents=True);(p/'admission.md').write_text('Trượt một môn học. Hạ bằng. Điểm chuẩn tuyển sinh.',encoding='utf8')
   self.assertEqual(Index(t).search('tôi bị trượt 1 môn có bị hạ bằng k'),[])
