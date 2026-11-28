import unittest, tempfile, hashlib,json
from pathlib import Path
from unittest.mock import patch
import advisor_course_reference as a

HEADER='| STT | Mã học phần | Học phần | Số tín chỉ | Số giờ | | | Mã học phần tiên quyết |'
OFF='## Nội dung chương trình đào tạo\n'+HEADER+'\n| 8 | INT1009 | Tin học cơ sở | 3 | 15 | 30 | | |\n'
class CourseReferenceTests(unittest.TestCase):
    def test_matrix_excluded(self):
        m='## Chuẩn đầu ra\n| STT | Mã học phần | Tên học phần | PLO1 | PLO2 |\n| 1 | INT1009 | Tin học cơ sở | 2 | 3 |\n'
        self.assertEqual([r['credits'] for r in a.read_rows(m+OFF,True)],[3])
        self.assertEqual(a.read_rows(m,False),[])
    def test_split_header(self):
        t='||**Mã**|**Học phần**|**Số tín**|**Số giờ tín c**|**hỉ**||**Mã số họ**|\n|---|---|---|---|---|---|---|---|\n|**STT**|**học phần**|**ghi bằng tiếng Việt và tiếng Anh**|**chỉ**|**Lý thuyết**|**Thực hành**|**Tự học**|**phần tiên**|\n|||**Tin học cơ sở**||||||\n|**9**|**INT1009**|**_Introduction to_**<br>**_Informatics_**|**3**|**15**|**30**|||'
        self.assertEqual(a.read_rows(t,False)[0]['credits'],3)
    def test_combined_and_short_header(self):
        t='|**STT**|**Mã học phần**<br>**Học phần**|**Số t**|\n|**1**|**PHI1006**<br>**Triết học Mác Lênin**|**3**|\n|**STT**|**Mã học phần**|**Học phần**|**Số t**|\n|**2**|**PEC1008**|**Kinh tế chính trị Mác Lênin**|**2**|'
        self.assertEqual([(x['code'],x['credits']) for x in a.read_rows(t,False)],[('PHI1006',3),('PEC1008',2)])
        self.assertEqual(a.read_rows('|1|INT1009|Tin học cơ sở|3|',False),[])
    def test_scope(self):
        q='Theo CTĐT ngành Kỹ thuật Robot, khóa QH-2025, học phần PEC1008 có bao nhiêu tín chỉ?'
        self.assertEqual(a.query(q),('ktrb',2025,'PEC1008'))
        self.assertIsNone(a.query(q+' và điều kiện tiên quyết?'))
        self.assertIsNone(a.query(q+' của tôi?'))
        self.assertIsNone(a.query(q+' năm 2026?'))
        self.assertIsNone(a.query(q+' và PHI1006?'))
        self.assertEqual(a.query('Theo CTĐT ngành Kỹ thuật điện tử viễn thông, khóa QH-2019, học phần INT1007 có bao nhiêu tín chỉ?'),('ktvt',2019,'INT1007'))
        self.assertEqual(a.query('Theo CTĐT ngành Mạng máy tính và truyền thông dữ liệu, khóa QH-2023, học phần INT1009 có bao nhiêu tín chỉ?'),('mmtttdl',2023,'INT1009'))
    def test_editions_and_holds(self):
        rec=lambda path,edition:dict(collection='official_uet_extractions',content_kind='curriculum',program_identifier='artificial-intelligence',cohort_from=2022,cohort_to=2024,content_path=path,edition=edition,content_sha256='a'*64,doc_id=edition)
        q='Theo CTĐT ngành Trí tuệ nhân tạo, khóa QH-2022, học phần INT1009 có bao nhiêu tín chỉ?'
        rows=[rec('a.md','old'),rec('b.md','updated')]
        with patch.object(a,'catalog',return_value={'records':rows,'owner_excluded_documents':[]}),patch.object(a,'read_source',side_effect=[(OFF,'a'*64),(OFF.replace('| 3 |','| 4 |'),'b'*64)]):
            r=a.route(Path('.'),q,{})[0];self.assertIn('3 tín chỉ',r['answer']);self.assertIn('4 tín chỉ',r['answer']);self.assertIn('không thống nhất',r['answer']);self.assertEqual(r['metadata']['source_path'],'a.md')
        with patch.object(a,'catalog',return_value={'records':rows,'owner_excluded_documents':[]}),patch.object(a,'read_source',side_effect=ValueError('held')):
            self.assertIsNone(a.route(Path('.'),q,{}))
        self.assertIsNone(a.route(Path('.'),q,{'kind':'student'}))
    def test_reset_on_unknown_header(self):
        t=HEADER+'\n| STT | Mã học phần | Tên học phần | Mức độ |\n|1|INT1009|Tin học cơ sở|2|'
        self.assertEqual(a.read_rows(t,False),[])
    def test_header_variants(self):
        # Header spellings transcribed from the six actual source formats.
        cases=[
          '| | Mã | Học phần | | Số giờ tí | n chỉ | | Mã số |\n|---|---|---|---|---|---|---|---|\n| STT | | | Số tín | | | | hần t |\n| | học phần | ghi bằng tiếng Việt và tiếng Anh | chỉ | Lý thuyết | Thực hành | Tự học | p quyết |',
          '| | | Học phần | | Số giờ t | ín chỉ | | Mã số |\n|---|---|---|---|---|---|---|---|\n| STT | Mã học | | Số tín | | | | h hầ |\n| | phần | ghi bằng tiếng Việt và tiếng Anh | chỉ | Lí thuyết | Thực hành | Tự học | ọc pn tiên quyế |',
          '| | | Học phần | | Số giờ t | ín chỉ | | Mã |\n|---|---|---|---|---|---|---|---|\n| | Mã học | | | | | | học |\n| STT | phần | ghi bằng tiếng Việt và tiếng Anh | Số tín chỉ | Lí thuyết | Thực hành | Tự học | tiên quy |',
          '| Số TT | Mã học phần | Tên học phần | Số tín<br>chỉ<br>S<br>Lý<br>th |',
          '| | | | Số | Số giờ h | ọc tập | | | Mã học phầ |\n|---|---|---|---|---|---|---|---|---|\n| STT | Mã học phần | Học phần | tín<br>chỉ | Lý thuyết | Thực hành | Bài tập | Tự học | tiên quyết |',
          '| | | Học phần | Số í | Số giờ tí | n chỉ | | Mã số h |\n|---|---|---|---|---|---|---|---|\n| STT | Mã h hầ | | tn | | | | hầ i |\n| | ọc pn | ghi bằng tiếng Việt và tiếng Anh | chỉ | Lý thuyết | Thực hành | Tự học | pn t quyết |',
        ]
        for i,h in enumerate(cases):
            with self.subTest(i=i):
                raw=h+'\n|9|INT1009|Tin học cơ sở|3|15|30|||'
                self.assertEqual([(v['code'],v['credits']) for v in a.read_rows(raw,False)],[('INT1009',3)])
    def test_new_headers_fail_closed(self):
        unknown='| STT | Mã học phần | Tên học phần | Mức độ |\n| 1 | INT1009 | Tin học cơ sở | 2 |'
        matrix='| STT | Mã học phần | Tên học phần | PLO1 | PLO2 |\n| 1 | INT1009 | Tin học cơ sở | 2 | 3 |'
        for t in (unknown,matrix,'\nMa trận\n'+matrix):
            self.assertEqual(a.read_rows(HEADER+'\n'+t,False),[])
        self.assertEqual(a.read_rows('| STT | Mã h hầ | Học phần | Số tín chỉ |\n|1|INT1009|Tin học cơ sở|3|',False),[])

    def test_new_code_formats(self):
        raw=HEADER+'\n|1.|INT2020E|Phân tích thiết kế|3|45| | | |\n|2.|UET.CE2020|Lập trình hệ thống|3|30|30| | |\n|3|AIT3005\\*|Seminar|3|45| | | |\n|4|AIT3040\\*\\*|Dự án|3|45| | | |\n| |MAT1101|Xác suất thống kê|3|30| | | |'
        self.assertEqual([(r['code'],r['credits'],r['marker']) for r in a.read_rows(raw,False)],[('INT2020E',3,''),('UET.CE2020',3,''),('AIT3005',3,'*'),('AIT3040',3,'**'),('MAT1101',3,'')])
        q='Theo CTĐT ngành Kỹ thuật Robot, khóa QH-2025, học phần UET.CE2020 có bao nhiêu tín chỉ?'
        self.assertEqual(a.query(q),('ktrb',2025,'UET.CE2020'))
        self.assertEqual(a.query(q.replace('UET.CE2020','INT2020E')),('ktrb',2025,'INT2020E'))
        self.assertIsNone(a.query(q.replace('UET.CE2020','INT2020EX')))
    def test_dotted_and_merged_headers(self):
        for raw,code in [(HEADER+'\n| Lý thuyết | Thực hành | Tự học | | | | | |\n|1.|PHI1006|Triết học|3|30|15| | |','PHI1006'),('|STT|Mã học phần<br>Học phần<br>ghi bằng tiếng Việt và tiếng Anh|Số tín<br>chỉ|Số giờ tí<br>Lý|n chỉ<br>Thực|Mã số<br>học ph<br>Tự|\n||||thuyết|hành|tiên qu học|\n|1.|PHI1006<br>Triết học Mác Lênin|3|30|15||','PHI1006')]:
            self.assertEqual([(r['code'],r['credits']) for r in a.read_rows(raw,False)],[(code,3)])
    def test_damaged_headers(self):
        cases=['|||Học phần|ố|Số giờ tí|n chỉ||Mã số h|\n|---|---|---|---|---|---|---|---|\n|STT|Mã học phần|ghi bằng tiếng Việt và tiếng Anh|S tín<br>chỉ|Lý thuyết|Thực hành|Tự học|phần ti quyết|', '||||Số|Số giờ h|ọc tập||||\n|---|---|---|---|---|---|---|---|---|\n|||||||||Mã học phầ|\n|STT|Mã học phần|Học phần|tín<br>chỉ|Lý thuyết|Thực hành|Bài tập|Tự học|tiên quyết|']
        for header in cases:
            self.assertEqual([r['credits'] for r in a.read_rows(header+'\n|20|INT2210|Cấu trúc dữ liệu|4|45|15|||',False)],[4])
        self.assertEqual(a.read_rows(HEADER+'\n|STT|Mã học phần|Tên học phần|PLO1|\n|1.|INT2020E|Tên|3|',False),[])
        self.assertEqual(a.read_rows(HEADER+'\n|1.|INT2020EX|Tên|3|',False),[])

    def test_merged_credit_hours(self):
        raw='|Số TT|Mã học phần<br>Tên học phần|Số tín<br>chỉ<br>S<br>Lý<br>th|\n|34|ELT3047E<br>Kiến trúc máy tính|**3**<br>**45**|\n|35|ELT3051<br>Kỹ thuật điều khiển|3 45|'
        self.assertEqual([(v['code'],v['credits']) for v in a.read_rows(raw,False)],[('ELT3047E',3)])
        raw='|Số TT|Mã học phần|Tên học phần|Số tín<br>chỉ<br>S<br>Lý<br>th|\n|66|ELT3094|Nhập môn xử lý tín hiệu|**3**<br>**45**|'
        self.assertEqual([v['credits'] for v in a.read_rows(raw,False)],[3])
    def test_superscript_credit(self):
        self.assertEqual([v['credits'] for v in a.read_rows(HEADER+'\n|26|UET.CE2021|Kiến trúc máy tính|<sup>**3**</sup>|45| | | |',False)],[3])
        self.assertEqual(a.read_rows(HEADER+'\n|26|UET.CE2021|Kiến trúc máy tính|<sup>**3**</sup> 4|45| | | |',False),[])
    def test_network_headers(self):
        cases=[
            '|||Hc hần||Số giờ tí|n chỉ||Mã số|\n|---|---|---|---|---|---|---|---|\n||ầ|ọ p|Số tín|||||\n|STT|Mã học phn|ghi bằng tiếng Việt và tiếng Anh|chỉ|Lý thuyết|Thực hành|Tự học|học ph tiên qu|',
            '|STT|Mã h hầ||Số tín||||h h|\n||ọc pn|ghi bằng tiếng Việt và tiếng Anh|chỉ|Lý thuyết|Thực hành|Tự học|ọc p tiên qu|',
            '|||Học phần|Số í|Số giờ tí|n chỉ||Mã số h|\n|---|---|---|---|---|---|---|---|\n|STT|Mã học phần|ghi bằng tiếng Việt và tiếng Anh|tn<br>chỉ|Lý thuyết|Thực hành|Tự học|phần ti quyết|',
            '|||Học phần|ố í|Số giờ tí|n chỉ|Mã số h|\n|---|---|---|---|---|---|---|\n|STT|Mã học phần|ghi bằng tiếng Việt và tiếng Anh|S tn<br>chỉ|Lý thuyết|Thực hành|Tự học|phần ti quyết|',
        ]
        for i,h in enumerate(cases):
            with self.subTest(i=i):
                self.assertEqual([v['credits'] for v in a.read_rows(h+'\n|10.|MAT1093|Đại số|4|30|30|| |',False)],[4])
    def test_name_excerpt_not_reconstructed(self):
        raw=HEADER+'\n|||Cấu trúc dữ liệu và giải thuật||||||\n|20|INT2210|Data Structures and Algorithms|4|45|15||INT100|'
        self.assertEqual(a.read_rows(raw,False)[0]['name_excerpt'],'Data Structures and Algorithms')

    def test_two_letter_codes_and_prerequisites(self):
        h='|STT|Mã học phần|Học phần|Số tín chỉ|Số giờ học tập||||Mã học phần tiên quyết|'
        text=h+'\n|38|UET.AI3053|Kỹ nghệ hệ thống AI|3|30|30||90|UET.AI2014, UET.CS1058|\n|39|UET.CS3136|Học máy|3|45|||105|UET.COM10|\n|40|UET.IS2099|Cơ sở dữ liệu|3|45|||105||'
        rows=a.read_rows(text,False)
        self.assertEqual([r['code'] for r in rows],['UET.AI3053','UET.CS3136','UET.IS2099'])
        self.assertEqual(rows[0]['prerequisite_codes'],['UET.AI2014','UET.CS1058'])
        self.assertEqual(rows[1]['prerequisite_status'],'UNRESOLVED_LITERAL')
        self.assertNotIn('prerequisite_codes',rows[1])
        self.assertEqual(rows[2]['prerequisite_status'],'BLANK_NOT_PROOF_OF_NONE')
        self.assertEqual(a.read_rows(h+'\n|38|UET.AI3053|Kỹ nghệ hệ thống AI|3|30|30|90|UET.AI2014|',False)[0]['prerequisite_status'],'HEADER_OR_ALIGNMENT_UNVERIFIED')

    def test_official_merged_prerequisite_header(self):
        for h,row in [('|STT|Mã học phần|Học phần|Số tín chỉ|Số giờ học tập|Mã học phần tiên quyết||||','|2|PEC1008|Kinh tế chính trị|2|30||0|70|PHI1006|'),('|STT|Mã học phần|Học phần|Số tín chỉ|Số giờ tín chỉ|Mã số học phần tiên quyết|||','|2|PEC1008|Kinh tế chính trị|2|30|15||PHI1006|')]:
            raw='## Nội dung chương trình đào tạo\n'+h+'\n'+row
            self.assertEqual(a.read_rows(raw,True)[0]['prerequisite_codes'],['PHI1006'])
            self.assertEqual(a.read_rows(raw,False)[0]['prerequisite_status'],'HEADER_OR_ALIGNMENT_UNVERIFIED')
            self.assertEqual(a.read_rows(raw.replace('|PHI1006|','|PHI10|'),True)[0]['prerequisite_status'],'UNRESOLVED_LITERAL')
        h='|STT|Mã học phần|Học phần|Số tín chỉ|Số giờ học tập|Mã học phần tiên quyết||||'
        raw='## Nội dung chương trình đào tạo\n'+h+'\n|2|PEC1008|Tên|2|30|PHI1006||70||'
        self.assertEqual(a.read_rows(raw,True)[0]['prerequisite_status'],'HEADER_OR_ALIGNMENT_UNVERIFIED')
    def test_literal_course_names(self):
        self.assertTrue(a.name_matches('Học máy Machine Learning','hoc may'))
        self.assertFalse(a.name_matches('Lý thuyết đồ thị cho Học máy Graph theory','hoc may'))
        q='Theo CTĐT ngành Trí tuệ nhân tạo, khóa QH-2025, học phần Học sâu có bao nhiêu tín chỉ?'
        self.assertEqual(a.relation_query(q),('artificial-intelligence',2025,None,'hoc sau',['credits']))
        self.assertIsNone(a.relation_query(q+' của tôi'))
        self.assertIsNone(a.relation_query(q+' năm 2026'))
    def test_prerequisite_route(self):
        q='Theo CTĐT ngành Trí tuệ nhân tạo, khóa QH-2025, học phần UET.AI3056 có môn tiên quyết nào?'
        r=dict(collection='official_uet_extractions',content_kind='curriculum',program_identifier='artificial-intelligence',cohort_from=2025,cohort_to=None,content_path='a.md',edition='2025',content_sha256='a'*64,doc_id='2025')
        raw='## Nội dung chương trình đào tạo\n|STT|Mã học phần|Học phần|Số tín chỉ|Số giờ học tập||||Mã học phần tiên quyết|\n|39|UET.CS3136|Học máy Machine Learning|3|45|||105||\n|42|UET.AI3056|Học sâu Deep Learning|3|45|||105|UET.CS3136|'
        with patch.object(a,'catalog',return_value={'records':[r],'owner_excluded_documents':[]}),patch.object(a,'read_source',return_value=(raw,'a'*64)):
            answer=a.route(Path('.'),q,{})[0]['answer'];self.assertIn('UET.CS3136',answer);self.assertIn('Học máy',answer)
            answer=a.route(Path('.'),q.replace('UET.AI3056','Học sâu'),{})[0]['answer'];self.assertIn('UET.CS3136',answer)
        with patch.object(a,'catalog',return_value={'records':[r],'owner_excluded_documents':[]}),patch.object(a,'read_source',side_effect=ValueError('held')):
            self.assertIsNone(a.route(Path('.'),q,{}))
        self.assertIsNone(a.route(Path('.'),q,{'kind':'student'}))

class CourseGraphTests(unittest.TestCase):
    def row(self,code,deps=None,line=1,status=None):
        return dict(code=code,name_excerpt=code,credits=3,line=line,prerequisite_codes=deps or [],prerequisite_status=status or ('LITERAL_CODES' if deps else 'BLANK_NOT_PROOF_OF_NONE'))
    def test_graph_chain_and_reverse(self):
        rows=[self.row('AAA1000',line=1),self.row('AAA2000',['AAA1000'],2),self.row('AAA3000',['AAA2000'],3)]
        links,warnings,cited=a.chain_data(rows,'AAA3000');self.assertEqual(links,[('AAA2000','AAA3000'),('AAA1000','AAA2000')]);self.assertEqual(cited,[1,2,3]);self.assertTrue(warnings)
        self.assertEqual(a.chain_data(rows,'AAA1000','reverse')[0],[('AAA1000','AAA2000')])
    def test_ambiguous_rows_not_merged(self):
        rows=[self.row('AAA2000',['AAA1000']),self.row('AAA2000',['AAA1001'],2),self.row('AAA3000',['AAA2000'],3),self.row('AAA4000',['AAA1000'],4),self.row('AAA4000',line=5)]
        self.assertEqual(a.chain_data(rows,'AAA3000')[0],[('AAA2000','AAA3000')]);self.assertTrue(a.chain_data(rows,'AAA3000')[1]);self.assertEqual(a.chain_data(rows,'AAA4000')[0],[])
    def test_cycle_missing_and_unresolved(self):
        rows=[self.row('AAA1000',['AAA2000']),self.row('AAA2000',['AAA1000','AAA3000'],2)]
        edges,warnings,cited=a.chain_data(rows,'AAA1000');self.assertEqual(len(edges),3);self.assertTrue(any('vòng lặp' in s for _,s in warnings));self.assertTrue(any('chưa tìm thấy' in s for _,s in warnings))
    def test_graph_scope(self):
        q='Theo CTĐT ngành Trí tuệ nhân tạo, khóa QH-2025, liệt kê chuỗi tiên quyết của học phần UET.AI3056'
        self.assertEqual(a.graph_query(q),('artificial-intelligence',2025,'UET.AI3056','uet ai3056','chain'))
        self.assertEqual(a.graph_query(q.replace('UET.AI3056','Học sâu'))[-1],'chain')
        self.assertIsNone(a.graph_query(q+' của tôi'));self.assertIsNone(a.graph_query(q+' và UET.CS3136'));self.assertIsNone(a.graph_query(q+' năm 2026'))
        self.assertIsNone(a.route(Path('.'),q,{'kind':'student'}))
    def test_graph_realistic_route(self):
        q='Theo CTĐT ngành Trí tuệ nhân tạo, khóa QH-2025, liệt kê chuỗi tiên quyết của học phần UET.AI3056'
        r=dict(collection='official_uet_extractions',content_kind='curriculum',program_identifier='artificial-intelligence',cohort_from=2025,cohort_to=None,content_path='a.md',edition='2025',content_sha256='a'*64,doc_id='2025')
        raw='## Nội dung chương trình đào tạo\n|STT|Mã học phần|Học phần|Số tín chỉ|Số giờ học tập||||Mã học phần tiên quyết|\n|1|UET.COM1050|Tư duy tính toán|5|45|||105| |\n|2|UET.CS3136|Học máy|3|45|||105|UET.COM1050|\n|3|UET.AI3056|Học sâu|3|45|||105|UET.CS3136|'
        with patch.object(a,'catalog',return_value={'records':[r],'owner_excluded_documents':[]}),patch.object(a,'read_source',return_value=(raw,'a'*64)):
            ans=a.route(Path('.'),q,{})[0]['answer'];self.assertIn('UET.COM1050',ans);self.assertIn('UET.CS3136',ans);self.assertIn('UET.AI3056',ans)
            ans=a.route(Path('.'),q.replace('liệt kê chuỗi tiên quyết của học phần UET.AI3056','học phần UET.COM1050 là tiên quyết của những môn nào'),{})[0]['answer'];self.assertIn('UET.CS3136',ans);self.assertNotIn('UET.AI3056',ans)
        with patch.object(a,'catalog',return_value={'records':[r],'owner_excluded_documents':[]}),patch.object(a,'read_source',side_effect=ValueError('held')):self.assertIsNone(a.route(Path('.'),q,{}))
