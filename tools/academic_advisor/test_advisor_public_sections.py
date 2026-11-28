import unittest,tempfile,json,hashlib
from pathlib import Path
from unittest.mock import patch
import advisor_public_sections as a

class PublicSectionsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        p=self.root/'data/versioning/publication_holds.jsonl';p.parent.mkdir(parents=True);p.write_text('')
    def put(self,rel,t):
        p=self.root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(t.encode());return t.encode()
    def test_org_exact(self):
        b=self.put(a.ORG,'# Hội đồng Khoa học và Đào tạo\n**1\\. Chức năng, nhiệm vụ:** tư vấn cho Hiệu trưởng\n– Kế hoạch phát triển đội ngũ;\n**2\\. Tổ chức nhân sự:**\n| 1 | tên khác |\n# Khoa Công nghệ nông nghiệp\nNội dung khác\n')
        with patch.dict(a.PINS,{a.ORG:a.gitblob(b)}):
            q='Hội đồng Khoa học và Đào tạo UET có chức năng gì theo tài liệu 2026?'
            r=a.org(self.root,q)[0];self.assertIn('phát triển đội ngũ',r['answer']);self.assertNotIn('tên khác',r['answer']);self.assertNotIn('nông nghiệp',r['answer']);self.assertTrue(r['metadata']['reference_only'])
            self.assertIsNone(a.org(self.root,q.replace('2026','2025')))
            self.put('data/versioning/publication_holds.jsonl',json.dumps({'doc_id':'held','content_sha256':a.digest(b)}));self.assertIsNone(a.route(self.root,q,{}))
    def test_postgraduate_scope(self):
        txt='Năm 2026 tuyển sinh sau đại học 02 đợt vào tháng 6 và tháng 10\\. I. TUYỂN SINH BẬC THẠC SĨ Danh mục các ngành và số lượng tuyển sinh 1\\. Đối tượng và điều kiện dự tuyển 2\\. Phương thức tuyển sinh 4\\. Kế hoạch xét tuyển 6\\. Lệ phí dự tuyển 1234567890 7\\. Tổ chức đào tạo, học phí, học bổng II. TUYỂN SINH BẬC TIẾN SĨ Danh mục các ngành và số lượng tuyển sinh 1\\. Đối tượng, điều kiện tuyển sinh 2\\. Phương thức tuyển sinh 8\\. Đăng ký dự tuyển 8.2. Lệ phí 9876543210 9\\. Tổ chức đào tạo, học phí, học bổng'
        b=self.put(a.PG,txt)
        with patch.dict(a.PINS,{a.PG:a.gitblob(b)}):
            q='Thông tin tuyển sinh sau đại học UET năm 2026 gồm những nội dung nào?'
            r=a.postgraduate(self.root,q)[0];self.assertIn('**Thạc sĩ:**',r['answer']);self.assertIn('**Tiến sĩ:**',r['answer']);self.assertNotIn('1234567890',r['answer']);self.assertIsNone(a.postgraduate(self.root,'Tuyển sinh sau đại học 2026 lệ phí bao nhiêu?'))
    def test_total_scope_hash(self):
        rel='data/raw/uet/markdown/curricula/test.md';t='---\nprogram_name_vi: "Công nghệ nông nghiệp"\nreported_total_credits: 150\n---\n**tổng tín chỉ theo nguồn:** 150.\n## Giới thiệu chung\nKhác';b=self.put(rel,t)
        self.put('data/raw/uet/curricula/catalog.json',json.dumps({'records':[{'collection':'official_uet_extractions','program_identifier':'agricultural-technology','cohort_from':2025,'cohort_to':None,'doc_id':'test','content_path':rel,'content_sha256':a.digest(b),'source_url':'https://uet.edu.vn/'}]}))
        q='Công nghệ nông nghiệp QH-2025 có tổng bao nhiêu tín chỉ?'
        r=a.curriculum_total(self.root,q)[0];self.assertIn('150 tín chỉ',r['answer']);self.assertTrue(r['metadata']['reference_only']);self.assertNotIn('Khác',r['answer']);self.assertIsNone(a.curriculum_total(self.root,q.replace('2025','2024')))
        self.put(rel,t.replace('150','151'));self.assertIsNone(a.route(self.root,q,{}))
    def test_preserve_personal(self):
        self.assertIsNone(a.route(self.root,'Hội đồng Khoa học và Đào tạo UET có chức năng gì theo tài liệu 2026?',{'kind':'advisor_mission'}))
        self.assertIsNone(a.route(self.root,'Công nghệ nông nghiệp QH-2025 có tổng bao nhiêu tín chỉ?',{'kind':'student'}))
