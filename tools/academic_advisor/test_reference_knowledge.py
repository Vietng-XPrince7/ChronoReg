import tempfile,unittest,json,hashlib
from pathlib import Path
from reference_knowledge import ReferenceLibrary,safe_public
from knowledge import Index
class ReferenceCoverage(unittest.TestCase):
 def test_pending_is_reference_only(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);p=root/'data/raw/uet/markdown/2025/notice.md';p.parent.mkdir(parents=True)
   p.write_text('---\nretrieval_eligible: false\n---\n# Học bổng nghiên cứu\nHọc bổng nghiên cứu hỗ trợ sinh viên thực hiện đề tài khoa học. Mức hỗ trợ trong thông báo là 1000000 đồng.\n',encoding='utf8')
   v=root/'data/versioning';v.mkdir(parents=True);h=v/'publication_holds.jsonl';h.write_text('',encoding='utf8')
   strict=Index(root);self.assertFalse(strict.chunks)
   lib=ReferenceLibrary(root);audit=lib.report();self.assertGreater(audit['pending_reference_chunks'],0);self.assertFalse(audit['official_review_changed'])
   r,c=lib.route('Học bổng nghiên cứu hỗ trợ đề tài khoa học năm 2025?');self.assertTrue(r['metadata']['reference_only']);self.assertIn('1000000',r['answer']);self.assertEqual(c,{})
   h.write_text(json.dumps({'doc_id':'test','content_sha256':hashlib.sha256(p.read_bytes()).hexdigest()})+'\n',encoding='utf8');self.assertIsNone(lib.route('Học bổng nghiên cứu hỗ trợ đề tài khoa học năm 2025?'))
   h.write_text('',encoding='utf8');p.write_text('changed',encoding='utf8');self.assertIsNone(lib.route('Học bổng nghiên cứu hỗ trợ đề tài khoa học năm 2025?'))
 def test_public_boundary(self):
  for q in ('Cô muốn soạn lời mời gặp riêng cho bạn ấy','Xin ngoại lệ quy chế UET','Hồ sơ của sinh viên 24020001','Quy chế hiện nay có áp dụng cho K71 không?'):
   self.assertFalse(safe_public(q))
  self.assertTrue(safe_public('Thông báo học bổng nghiên cứu khoa học năm 2025'))
if __name__=='__main__':unittest.main()
