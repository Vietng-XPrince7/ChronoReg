import hashlib,json,tempfile,unittest
from pathlib import Path
from knowledge import Index

class RetrievalGate(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name); self.v=self.root/'data/versioning';self.v.mkdir(parents=True)
        self.put('data/raw/uet/markdown/2025/ordinary.md','## Quy chế học tập\nSinh viên đăng ký học phần theo kế hoạch đào tạo năm 2025.')
    def put(self,rel,body):
        p=self.root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(body,encoding='utf8');return hashlib.sha256(p.read_bytes()).hexdigest()
    def ledger(self,name,rows):
        (self.v/name).write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf8')
    def test_archive_raw_and_wrapper_excluded(self):
        a='data/raw/uet/curricula/tuan_2022_2026/original/x.md'; b='data/raw/uet/markdown/curricula/tuan_2022_2026/x.md'
        self.put(a,'Chương trình đào tạo yêu cầu 987 tín chỉ.');self.put(b,'---\nretrieval_eligible: false\n---\nChương trình đào tạo yêu cầu 987 tín chỉ.')
        idx=Index(self.root);self.assertEqual(idx.stats()['review_pending'],2);self.assertEqual(idx.stats()['files'],3);self.assertFalse(any(c.path in (a,b) for c in idx.chunks));self.assertTrue(idx.search('Sinh viên đăng ký học phần'))
    def test_explicit_optout_and_no_fake_review(self):
        a='data/raw/uet/markdown/2025/blocked.md';sha=self.put(a,'---\nretrieval_eligible: "false" # blocked\n---\nNội dung học phí sai lệch 999 triệu đồng.')
        self.ledger('reviewed_documents.jsonl',[{'doc_id':'x','content_sha256':sha,'review_status':'verified_against_source'}]);self.ledger('rag_chunks.jsonl',[{'doc_id':'x','content_sha256':sha,'policy_qa_ready':True,'eligible_for_policy_qa':True,'text':'Nội dung 999 triệu đồng.'}]);idx=Index(self.root);self.assertEqual(idx.stats()['reviewed_chunks'],0);self.assertEqual(idx.stats()['review_pending'],1);self.assertFalse(any(c.path==a for c in idx.chunks))
    def test_hold_precedence(self):
        a='data/raw/uet/curricula/tuan_2022_2026/original/x.md';sha=self.put(a,'Một tài liệu cần kiểm tra và đang được giữ lại.');self.ledger('publication_holds.jsonl',[{'doc_id':'x','content_sha256':sha}]);idx=Index(self.root);self.assertEqual(idx.stats()['held'],1);self.assertEqual(idx.stats()['review_pending'],0)
    def test_flag_in_body_not_metadata(self):
        a='data/raw/uet/markdown/2025/example.md';self.put(a,'## Hướng dẫn\nVí dụ: retrieval_eligible: false là thông tin minh họa.');idx=Index(self.root);self.assertEqual(idx.stats()['review_pending'],0);self.assertTrue(any(c.path==a for c in idx.chunks))
    def test_exact_alias_cannot_bypass_pending(self):
        raw='Chương trình đào tạo yêu cầu 987 tín chỉ.'
        a='data/raw/uet/curricula/tuan_2022_2026/original/x.md';b='data/raw/uet/markdown/2025/alias.md'
        self.put(a,raw);self.put(b,raw);idx=Index(self.root);self.assertEqual(idx.stats()['review_pending'],2);self.assertFalse(any(c.path in (a,b) for c in idx.chunks))
    def test_catalog_optout(self):
        a='data/raw/uet/markdown/2025/catalogued.md';self.put(a,'Nội dung đã được ghi nhận nhưng chưa được duyệt.')
        c=self.root/'data/raw/uet/curricula/catalog.json';c.parent.mkdir(parents=True,exist_ok=True);c.write_text(json.dumps({'records':[{'content_path':a,'retrieval_eligible':False}]}));idx=Index(self.root);self.assertEqual(idx.stats()['review_pending'],1);self.assertFalse(any(c.path==a for c in idx.chunks))
    def test_true_flag_not_release_archive(self):
        a='data/raw/uet/markdown/curricula/tuan_2022_2026/x.md';self.put(a,'---\nretrieval_eligible: true\n---\nTự sửa cờ không thay thế việc thẩm định tài liệu.');self.assertEqual(Index(self.root).stats()['review_pending'],1)
if __name__=='__main__':unittest.main()
