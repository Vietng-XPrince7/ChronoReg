import hashlib,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import course_planning as cp
from workflow import run_workflow

TEXT='''|**18**|**INT1008**|**Nhập môn lập trình**|**3**|**20**|**25**|||\n|**20**|**INT2210**|**Giải thuật**|**4**|**45**|**15**||**INT1008**|\n|**25**|**INT2211**|**Cơ sở dữ liệu**|**4**|**45**|**15**|||\n|**28**|**INT2204**|**Lập trình hướng đối tượng**|**3**|**30**|**15**||**INT1008**|\n|**42**|**INT3306**|**Web**|**3**|**30**|**15**||**INT2204, INT2211**|\n'''
class PlanningTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
  self.digest=hashlib.sha256(TEXT.encode()).hexdigest();self.p=self.root/cp.REL;self.p.parent.mkdir(parents=True);self.p.write_bytes(TEXT.encode())
  catalog=self.root/'data/raw/uet/curricula/catalog.json';catalog.write_text(json.dumps({'records':[{'content_path':cp.REL,'doc_id':cp.DOC,'program_identifier':'cntt','content_sha256':self.digest}]}))
  self.hold=self.root/'data/versioning/publication_holds.jsonl';self.hold.parent.mkdir(parents=True);self.hold.write_text('')
  self.roster={'major':'Công nghệ Thông tin','cohort':'QH-2024 (K69)','class_short':'K69-CNTT1','semester':'2025-2026'}
  self.table=cp.parse_rows(TEXT);self.rows=[(k,k,v[0]) for k,v in self.table.items()]
 def test_rows(self):
  self.assertEqual(len(self.table),5);self.assertEqual(self.table['INT3306'],(3,('INT2204','INT2211')))
 def test_bad_or_conflicting_rows(self):
  self.assertNotIn('INT1008',cp.parse_rows(TEXT+'|18|INT1008|X|4|20|25|||\n'))
  self.assertFalse(cp.parse_rows('|1|INT1008|X|3|20|25||INT2210 or INT2211|'))
 def test_scope_and_hash(self):
  with patch.object(cp,'SHA',self.digest):
   self.assertEqual(cp.load_candidate(self.root,self.roster)[0],self.table)
   self.assertIsNone(cp.load_candidate(self.root,{**self.roster,'cohort':'QH-2025'})[0])
   self.assertIsNone(cp.load_candidate(self.root,{**self.roster,'major':'Khoa học máy tính'})[0])
   self.p.write_bytes(TEXT.encode()+b'changed');self.assertIsNone(cp.load_candidate(self.root,self.roster)[0])
 def test_hold(self):
  with patch.object(cp,'SHA',self.digest):
   for hold in [{'doc_id':cp.DOC},{'content_sha256':self.digest},{'content_path':cp.REL}]:
    self.hold.write_text(json.dumps(hold)+'\n');self.assertIsNone(cp.load_candidate(self.root,self.roster)[0])
   self.hold.unlink();self.assertIsNone(cp.load_candidate(self.root,self.roster)[0])
 def test_order_and_budget(self):
  for cap in (4,6,12):
   stages,excluded=cp.make_plan(self.rows,self.table,[],cap);self.assertFalse(excluded);done=set()
   for stage in stages:
    self.assertLessEqual(sum(r[2] for r in stage),cap)
    for code,_,_ in stage:self.assertTrue(set(self.table[code][1])<=done)
    done.update(r[0] for r in stage)
   self.assertEqual(done,set(self.table))
 def test_unknown_or_mixed_prerequisite(self):
  rows=[('INT2210','X',4)]
  for hist in ([],[{'ma_mon':'INT1008','dat':True},{'ma_mon':'INT1008','dat':False}]):
   stage,exc=cp.make_plan(rows,self.table,hist,12);self.assertFalse(stage);self.assertIn('INT1008',exc['INT2210'])
  self.assertTrue(cp.make_plan(rows,self.table,[{'ma_mon':'INT1008','dat':True}],12)[0])
 def test_credit_mismatch_and_unknown_code(self):
  stage,exc=cp.make_plan([('INT1008','X',4),('LAW1050','X',2)],self.table,[],12);self.assertFalse(stage);self.assertEqual(set(exc),{'INT1008','LAW1050'})
 def test_cycle(self):
  stage,exc=cp.make_plan([('INT1008','X',3),('INT2210','Y',4)],{'INT1008':(3,('INT2210',)),'INT2210':(4,('INT1008',))},[],12);self.assertFalse(stage);self.assertEqual(len(exc),2)
 def test_workflow(self):
  roster={**self.roster,'students':[{'student_id':'24000001','full_name':'Demo A','gpa_semester':1.5,'owed_credits':7,'drl':65,'bang_diem':[{'ma_mon':'INT1008','dat':False},{'ma_mon':'INT2210','dat':False}]}],'courses':[{'ma_mon':'INT1008','ten_mon':'X','so_tin_chi':3},{'ma_mon':'INT2210','ten_mon':'Y','so_tin_chi':4}]}
  with patch.object(cp,'SHA',self.digest):
   p=run_workflow('Lập phương án học lại tối đa 12 tín chỉ môn nợ',{'category':'STUDENT_STATUS','student_id':'24000001','roster_obj':roster},self.root)
   self.assertIn('prerequisite_planning',p['workflow_tools']);self.assertIn('Đợt 1: INT1008',p['predicted_answer']);self.assertIn('Đợt 2: INT2210',p['predicted_answer']);self.assertIn('bảng chưa duyệt',p['predicted_answer']);self.assertEqual(p['advisor_sources'][0]['source_path'],cp.REL)
 def test_real_pinned_table(self):
  root=Path(os.environ.get('CHRONOREG_TEST_REPO','.' ));path=root/cp.REL
  if not path.is_file():self.skipTest('pinned source absent in fixture')
  table,reason=cp.load_candidate(root,self.roster);self.assertIsNotNone(table,reason);self.assertEqual(table['INT2210'],(4,('INT1008',)));self.assertEqual(table['INT3306'],(3,('INT2204','INT2211')));self.assertNotIn('LAW1050',table)
