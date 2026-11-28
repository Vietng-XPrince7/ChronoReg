import hashlib, tempfile, unittest, json
from pathlib import Path
from unittest.mock import patch
import experience_routes as e

class ExperienceRoutesTests(unittest.TestCase):
    def test_cpa_followup(self):
        a,p=e.cpa_route('Giả sử GPA tích lũy 2,50 với 60 tín chỉ, kỳ tới học 15 tín chỉ đạt GPA 3,50. CPA mới là bao nhiêu?',{})
        self.assertEqual(a['metadata']['simulation']['projected_cpa'],'2.70')
        b,p=e.cpa_route('Nếu kỳ tới chỉ đạt GPA 3,00 thì sao?',p)
        self.assertEqual(b['metadata']['simulation']['projected_cpa'],'2.60')
        c,p=e.cpa_route('Còn nếu học 20 tín chỉ thì sao?',p)
        self.assertEqual(c['metadata']['simulation']['projected_cpa'],'2.625')
        self.assertIsNone(e.cpa_route('Nếu kỳ tới chỉ đạt GPA 3,00 thì sao?',{}))
        self.assertIsNone(e.cpa_route('Nếu GPA 3,0 thì có học bổng không?',p))
        bad,p2=e.cpa_route('Nếu GPA 5,00 thì sao?',p);self.assertEqual(bad['metadata']['simulation']['status'],'needs_inputs');self.assertEqual(p2,{})
    def test_notice_scope(self):
        q='Thí sinh dự tuyển thạc sĩ UET đợt 1 năm 2024 cần tiếng Anh tối thiểu bậc mấy?'
        with patch.object(e,'_notice',return_value=(3,2,'fake')):
            r,p=e.notice_route(q,{},None);self.assertIn('bậc 3',r['answer'])
            r,p=e.notice_route('Chứng chỉ có thời hạn bao lâu?',p,None);self.assertIn('2 năm',r['answer'])
            r,p=e.notice_route('Chứng chỉ thi online có được không?',p,None);self.assertIn('không chấp nhận',r['answer'])
            for wrong in (q.replace('2024','2025'),q.replace('đợt 1','đợt 2'),q.replace('thạc sĩ','tiến sĩ'),q+' IELTS?',q+' và học phí bao nhiêu?',q.replace('UET','ULIS')):
                self.assertIsNone(e.notice_route(wrong,p,None))
            self.assertIsNone(e.notice_route('Chứng chỉ có thời hạn bao lâu?',{},None))
    def test_byte_pin_and_hold(self):
        data=('***1.2. Yêu cầu về ngoại ngữ***\nThí sinh có năng lực Tiếng Anh từ Bậc 3 trở lên theo Khung năng lực ngoại ngữ 6 bậc dùng cho Việt Nam\ntrong thời hạn 2 năm kể từ ngày thi chứng chỉ/chứng nhận đến ngày đăng ký dự tuyển\nkhông chấp nhận sử dụng chứng chỉ ngoại ngữ thi theo hình thức trực tuyến\n***1.3. Yêu cầu khác***\n').encode()
        pin=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
        with tempfile.TemporaryDirectory() as t,patch.object(e,'NOTICE_BLOB',pin):
            root=Path(t);p=root/e.NOTICE_PATH;p.parent.mkdir(parents=True);p.write_bytes(data);h=root/'data/versioning/publication_holds.jsonl';h.parent.mkdir(parents=True);h.write_text('')
            self.assertEqual(e._notice(root)[:2],(3,2))
            h.write_text(json.dumps({'doc_id':'test','content_sha256':hashlib.sha256(data).hexdigest()}));self.assertRaises(ValueError,e._notice,root)
            h.write_text('');p.write_bytes(data+b'x');self.assertRaises(ValueError,e._notice,root)
if __name__=='__main__':unittest.main()
