"""Release regressions for source scope, optional values and warm-index revocation."""
import hashlib,json,tempfile,unittest
from pathlib import Path
from reference_knowledge import ReferenceLibrary,safe_public
from advisor_course_reference import read_rows,chain_data

class FinalReferenceTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  self.put('data/versioning/publication_holds.jsonl','')
  self.q='Học bổng nghiên cứu hỗ trợ đề tài khoa học năm 2025?'
  self.rel='data/raw/uet/markdown/2025/notice.md'
  self.sha=self.put(self.rel,'# Học bổng nghiên cứu\nHọc bổng nghiên cứu hỗ trợ sinh viên thực hiện đề tài khoa học. Mức hỗ trợ trong thông báo là 1000000 đồng.\n')
 def put(self,rel,t):
  p=self.root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(t.encode());return hashlib.sha256(p.read_bytes()).hexdigest()
 def test_warm_catalog_exclusion_path(self):
  lib=ReferenceLibrary(self.root);self.assertIsNotNone(lib.route(self.q))
  self.put('data/raw/uet/curricula/catalog.json',json.dumps({'records':[],'owner_excluded_documents':[{'source_path':self.rel}]}))
  self.assertIsNone(lib.route(self.q));self.assertEqual(lib.report()['access_counts']['owner_excluded'],1)
 def test_warm_catalog_exclusion_hash(self):
  lib=ReferenceLibrary(self.root);self.assertIsNotNone(lib.route(self.q))
  self.put('data/raw/uet/curricula/catalog.json',json.dumps({'records':[],'owner_excluded_documents':[{'source_sha256':self.sha}]}))
  self.assertIsNone(lib.route(self.q))
 def test_warm_comparison_exclusion(self):
  lib=ReferenceLibrary(self.root);self.assertIsNotNone(lib.route(self.q))
  self.put('tools/academic_advisor/reference_comparison.json',json.dumps({'files':[{'path':self.rel,'sha256':self.sha,'status':'OWNER_EXCLUDED_LEGACY_COPY'}]}))
  self.assertIsNone(lib.route(self.q))
 def test_warm_path_hold(self):
  lib=ReferenceLibrary(self.root);self.assertIsNotNone(lib.route(self.q))
  self.put('data/versioning/publication_holds.jsonl',json.dumps({'source_path':self.rel,'doc_id':'other','content_sha256':'f'*64}))
  self.assertIsNone(lib.route(self.q))
 def test_literal_course_codes(self):
  self.assertTrue(safe_public('UET.AI3053'));self.assertTrue(safe_public('INT2210E'))
  self.put('data/raw/uet/markdown/2025/course.md','# Học phần\nUET.AI3053 Kỹ nghệ hệ thống AI; INT2210E Cấu trúc dữ liệu và giải thuật.\n')
  lib=ReferenceLibrary(self.root)
  self.assertIsNotNone(lib.route('UET.AI3053'))
  self.assertIsNotNone(lib.route('INT2210E'))
  self.assertIsNone(lib.route('INT2210'))
  self.assertIsNone(lib.route('AI3053'))
 def test_no_inferred_requirement(self):
  raw='|STT|Mã học phần|Tên học phần|Số tín chỉ|Mã học phần tiên quyết|\n|1|INT1000|A|3|Không có|\n|2|INT2000|B|3|INT1000|\n|3|INT3000|C|3| |\n|4|INT4000|D|3|Không áp dụng|\n|5|INT5000|E|3|-|'
  rows=read_rows(raw,False)
  self.assertEqual([r['prerequisite_status'] for r in rows],['EXPLICIT_NONE','LITERAL_CODES','BLANK_NOT_PROOF_OF_NONE','NOT_APPLICABLE','UNRESOLVED_LITERAL'])
  links,warnings,_=chain_data(rows,'INT2000');self.assertEqual(links,[('INT1000','INT2000')]);self.assertFalse(warnings)
  self.assertFalse(chain_data(rows,'INT4000')[1]);self.assertTrue(chain_data(rows,'INT3000')[1])
 def test_conflicting_none_and_codes(self):
  rows=[{'code':'INT1000','line':1,'prerequisite_status':'EXPLICIT_NONE','prerequisite_codes':[]},{'code':'INT1000','line':2,'prerequisite_status':'LITERAL_CODES','prerequisite_codes':['INT2000']}]
  links,warnings,_=chain_data(rows,'INT1000');self.assertFalse(links);self.assertTrue(warnings)
if __name__=='__main__':unittest.main()
