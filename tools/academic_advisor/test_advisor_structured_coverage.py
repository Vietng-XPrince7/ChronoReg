import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import advisor_public_sections as a

class StructuredCoverageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.put('data/versioning/publication_holds.jsonl','')
    def put(self,rel,text):
        p=self.root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(text.encode());return a.digest(text.encode())
    def catalog(self,rows):self.put('data/raw/uet/curricula/catalog.json',json.dumps({'records':rows}))
    def total_row(self,edition,amount):
        rel=f'data/raw/uet/markdown/curricula/{edition}.md';sha=self.put(rel,f'---\nprogram_name_vi: "Công nghệ nông nghiệp"\nreported_total_credits: {amount}\n---\n**tổng tín chỉ theo nguồn:** {amount}.\n## Giới thiệu chung\nKhác')
        return dict(collection='official_uet_extractions',content_kind='curriculum',program_identifier='agricultural-technology',cohort_from=2022,cohort_to=2024,doc_id=edition,edition=edition,content_path=rel,content_sha256=sha)
    def test_total_variants(self):
        r=self.total_row('original',150);self.catalog([r]);q='Theo chương trình đào tạo ngành Công nghệ nông nghiệp, khóa QH-2022, tổng khối lượng toàn khóa là bao nhiêu tín chỉ?'
        z=a.total_v2(self.root,q)[0];self.assertIn('150 tín chỉ',z['answer']);self.assertIsNone(a.total_v2(self.root,q.replace('2022','2025')))
        self.assertIsNone(a.total_v2(self.root,q+' học kỳ 1'));self.assertIsNone(a.total_v2(self.root,q+' và QH-2024'))
        r2=self.total_row('updated',151);self.catalog([r,r2]);z=a.total_v2(self.root,q)[0];self.assertIn('150 tín chỉ',z['answer']);self.assertIn('151 tín chỉ',z['answer']);self.assertIn('Chưa đủ căn cứ',z['answer'])
        self.put('data/versioning/publication_holds.jsonl',json.dumps({'doc_id':'original','content_sha256':r['content_sha256']}));self.assertIsNone(a.route(self.root,q,{}))
    def test_hierarchical_plo(self):
        t='# 1. Chuẩn đầu ra\n**PLO1.1. Vận dụng kiến thức toán và tin học trong công việc.**\n**PLO1.2. Phân tích hệ thống phần mềm và dữ liệu.**\n# 2. Chuẩn đầu ra kỹ năng\n– PLO2.1. Giải quyết vấn đề trong lĩnh vực chuyên môn; PLO2.2. Phân tích và trình bày kết quả thực nghiệm.\n# 3. Mức tự chủ\nPLO3.1. Chịu trách nhiệm nghề nghiệp và tự học.\n# 4. Vị trí việc làm\nKhông đưa vào kết quả.'
        rows=a.parse_plo(t);self.assertEqual([k for k,v in rows],['PLO1.1','PLO1.2','PLO2.1','PLO2.2','PLO3.1']);self.assertNotIn('Không đưa',str(rows))
    def test_postgraduate_language_split(self):
        t='I. TUYỂN SINH BẬC THẠC SĨ b. Yêu cầu về ngoại ngữ Một trong các chứng chỉ tiếng Anh đạt trình độ tương đương Bậc 3 trở lên trong thời hạn 2 năm kể từ ngày thi đến ngày đăng ký dự tuyển; Lưu ý: Nhà trường không chấp nhận chứng chỉ thi online. c. Yêu cầu khác II. TUYỂN SINH BẬC TIẾN SĨ b) Người dự tuyển là công dân Việt Nam phải đạt ngoại ngữ: Một trong các chứng chỉ ngoại ngữ đạt trình độ tương đương Bậc 4 trở lên trong thời hạn 2 năm kể từ ngày thi đến ngày đăng ký dự tuyển; c) Người dự tuyển là công dân nước ngoài'
        self.put(a.PG,t)
        with patch.dict(a.PINS,{a.PG:a.gitblob(t.encode())}):
            r=a.postgraduate_language(self.root,'Yêu cầu ngoại ngữ khi dự tuyển tiến sĩ UET năm 2026 ở bậc mấy với công dân Việt Nam dùng chứng chỉ?')[0];self.assertIn('Bậc 4',r['answer']);self.assertNotIn('Bậc 3',r['answer'])
            r=a.postgraduate_language(self.root,'Tuyển sinh thạc sĩ UET năm 2026 có chấp nhận chứng chỉ ngoại ngữ thi online không?')[0];self.assertIn('không chấp nhận',r['answer'])
    def test_research_scope(self):
        rel,_,pat,label=a.RESEARCH_SOURCES[2023];t='| Hoạt động | Thời gian |\n| Hội nghị SVNCKH cấp Khoa | 12/03/2024 |\n| Đăng ký đề tài | 19/01–25/01/2024 |';self.put(rel,t)
        with patch.dict(a.RESEARCH_SOURCES,{2023:(rel,a.gitblob(t.encode()),pat,label)}):
            q='Theo kế hoạch cấp Khoa CNTT năm học 2023-2024, hội nghị sinh viên nghiên cứu khoa học diễn ra ngày nào?';r=a.research_dates(self.root,q)[0];self.assertIn('12/03/2024',r['answer']);self.assertIsNone(a.research_dates(self.root,q.replace('CNTT','Robot')))
