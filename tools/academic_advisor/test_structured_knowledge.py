import json,unittest
from types import SimpleNamespace
from knowledge import Chunk,structured_synthesis
from slm_advisor import present
from presentation import present as source_present
from test_slm_quality import model, Q, ROOT
from regulation import lookup_regulation

def chunk(text,year=2024):return Chunk('public.md','abc',text,'Tuyển sinh thạc sĩ','unreviewed',(year,))
class StructuredTests(unittest.TestCase):
 def test_reference_assembled_without_inline_citation(self):
  b,c=model({'answer':'Dạ cô, thí sinh cần tiếng Anh từ Bậc 3 trở lên.','refs':['P1']});a,s,e=structured_synthesis(b,'Thí sinh cần năng lực tiếng Anh tối thiểu nào?',[chunk('Thí sinh cần năng lực tiếng Anh từ Bậc 3 trở lên.')],{2024});self.assertIn('Bậc 3',a);self.assertEqual(e,[]);self.assertEqual(len(s),1);self.assertEqual(c[0]['json']['format']['properties']['refs']['items']['enum'],['P1'])
 def test_bad_number_from_other_passage(self):
  b,_=model({'answer':'Cần tiếng Anh Bậc 5.','refs':['P1']});a,s,e=structured_synthesis(b,'Cần tiếng Anh Bậc nào?',[chunk('Cần năng lực tiếng Anh từ Bậc 3 trở lên.'),chunk('Số đợt tuyển sinh là 5.')],{2024});self.assertIsNone(a);self.assertIn('unsupported_number_in_selected_passages',e)
 def test_bad_id(self):
  b,_=model({'answer':'Cần Bậc 3.','refs':['P9']});a,s,e=structured_synthesis(b,'Tiếng Anh Bậc nào?',[chunk('Cần năng lực tiếng Anh từ Bậc 3 trở lên.')],{2024});self.assertIsNone(a);self.assertEqual(e,['invalid_passage_reference'])
 def test_compare_requires_both_years(self):
  b,_=model({'answer':'Cần tiếng Anh Bậc 3.','refs':['P1']});a,s,e=structured_synthesis(b,'Tiếng Anh Bậc nào năm 2024 và 2025?',[chunk('Cần năng lực tiếng Anh từ Bậc 3 trở lên.'),chunk('Cần năng lực tiếng Anh từ Bậc 4 trở lên.',2025)],{2024,2025});self.assertIsNone(a);self.assertEqual(e,['missing_year_evidence'])
 def test_duplicate_advice(self):
  b,_=model({'advice':'Cô nên đối chiếu tổng tín chỉ phải học lại với tổng tín chỉ chương trình và quy chế áp dụng cho khóa tuyển sinh.'});r=present(source_present,b,Q,{'engine_mode':'SOURCE_CLAUSE','predicted_answer':lookup_regulation(ROOT,Q)['answer'],'latency_ms':0},{});self.assertEqual(r['narrative_diagnostics'],['duplicate_advice']);self.assertNotEqual(r['presentation_mode'],'SLM_ADVISOR')
if __name__=='__main__':unittest.main()
