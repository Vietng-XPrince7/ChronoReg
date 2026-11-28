import unittest,re,copy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from conversation import add_conversation
from quality_routes import route
from quality import norm

class Req(BaseModel):
    question:str; force_engine:str|None=None; mssv:str|None=None

class WorkflowQuality(unittest.TestCase):
    def setUp(self):
        self.roster={'class_short':'K69-CNTT1','cohort':'QH-2024 (K69)','semester':'2025.1','students':[{'student_id':'24000001','full_name':'DEMO_A','gpa_semester':1.5,'owed_credits':6,'drl':65,'bang_diem':[{'ma_mon':c,'dat':False} for c in ('ABC0001','ABC0002')]},{'student_id':'24000002','full_name':'DEMO_B','gpa_semester':3.5,'owed_credits':0,'drl':90}], 'courses':[{'ma_mon':c,'so_tin_chi':3} for c in ('ABC0001','ABC0002')]}
        self.table={'ABC0001':(3,()),'ABC0002':(3,('ABC0001',))}
        for name in ('quality_workflows.load_candidate','quality_routes.load_candidate','counseling.load_candidate'):
            p=patch(name,return_value=(self.table,None));p.start();self.addCleanup(p.stop)
        self.calls=[]
        def original(req):
            self.calls.append(req.question);return {'answer':'original','routing':{'risk_tier':'RED' if 'ngoại lệ' in req.question else 'GREEN'},'metadata':{}}
        router=SimpleNamespace(route_decision=lambda q:SimpleNamespace(risk_tier='RED' if 'ngoại lệ' in q else 'GREEN'),classify_query=lambda q,**kw:('STUDENT_STATUS',{'mssv':next(iter(re.findall(r'\b2400000[12]\b',q)),None)}))
        s=SimpleNamespace(app=FastAPI(),_router=router,_get_active_roster=lambda:self.roster)
        add_conversation(s,original,Req,Path('.'));self.client=TestClient(s.app)
    def ask(self,q,previous=None,**kw):
        r=self.client.post('/api/advisor/chat',json={'question':q,'context_token':previous.get('context_token') if previous else None,**kw});self.assertEqual(r.status_code,200,r.text);return r.json()
    def test_priorities_to_plan(self):
        a=self.ask('Với sinh viên 24000001, chọn tối đa 2 hành động học tập cần ưu tiên.');self.assertEqual(a['answer'].count('\n1.'),1);self.assertEqual(a['answer'].count('\n2.'),1);self.assertNotIn('\n3.',a['answer']);self.assertIn('ABC0001',a['answer']);self.assertIn('chưa duyệt',a['answer'])
        b=self.ask('Mỗi đợt chỉ học lại 3 tín chỉ, lập kế hoạch.',a);self.assertEqual(b['metadata']['advisor_intent'],'retake_plan');self.assertIn('2 đợt',b['answer']);self.assertNotIn('DEMO_B',b['answer'])
    def test_meeting_revision(self):
        a=self.ask('Chuẩn bị gặp sinh viên 24000001, viết 3 câu hỏi mở.');self.assertEqual(a['answer'].count('• '),3);self.assertNotIn('Sau khi nghe',a['answer'])
        b=self.ask('Bạn làm thêm buổi tối, khó học nhóm. Thay câu hỏi bằng câu về thời gian tự học.',a);self.assertEqual(b['answer'].count('?'),1);self.assertIn('tự học',b['answer'])
        c=self.ask('Bạn muốn học một mình, không muốn có bạn đồng hành. Cô nên đề xuất phương án khác?',b);self.assertIn('tự học',c['answer']);self.assertIn('tôn trọng',c['answer']);self.assertNotIn('học nhóm',c['answer'])
    def test_draft_revision_public(self):
        a=self.ask('Viết tin nhắn riêng cho sinh viên 24000001, hẹn gặp, tối đa 50 từ, không nhắc GPA.');self.assertLessEqual(len(a['answer'].split()),50);self.assertNotIn('24000001',a['answer']);self.assertNotIn('GPA',a['answer'])
        for edit in ('Giọng thân thiện hơn, bỏ cụm từ gặp riêng.','Giọng thân thiện hơn và đừng dùng cụm từ gặp riêng.','Viết nhẹ nhàng hơn, không dùng chữ gặp riêng.'):
            b=self.ask(edit,a);self.assertLessEqual(len(b['answer'].split()),50);self.assertNotIn('gặp riêng',b['answer']);self.assertNotEqual(a['answer'],b['answer'])
            self.assertEqual(b['metadata']['advisor_intent'],'communication_draft');self.assertIn('communication_draft',b['metadata']['workflow_tools']);self.assertTrue(b['context_token']);self.assertIn('Chào em',b['answer']);self.assertNotIn('GPA',b['answer']);self.assertNotIn('24000001',b['answer'])
        self.assertFalse(self.calls)
        c=self.ask('Soạn thông báo chung cho lớp về đăng ký học phần.',b);self.assertIn('đăng ký học phần',c['answer']);self.assertNotIn('DEMO_A',c['answer']);self.assertNotIn('24000001',c['answer'])
    def test_public_private_split(self):
        a=self.ask('Cô cần họp lớp: tóm tắt tình hình nội bộ rồi tách thông báo công khai.');self.assertIn('Nội bộ',a['answer']);self.assertIn('Thông báo công khai',a['answer']);self.assertIn('2 hồ sơ',a['answer'])
        b=self.ask('Bỏ phần báo cáo nội bộ, chỉ giữ thông báo và thêm nhắc chuẩn bị câu hỏi.',a);self.assertNotIn('hồ sơ',b['answer']);self.assertIn('chuẩn bị câu hỏi',b['answer'])
        c=self.ask('Cô đã gửi rồi, đề xuất cách thu phản hồi.',b);self.assertIn('cô đã gửi',c['answer']);self.assertNotIn('Em đã gửi',c['answer']);self.assertIn('chưa gửi',c['answer'])
    def test_agenda(self):
        a=self.ask('Cô có 25 phút để hỗ trợ lớp, chia thời lượng ra sao?');self.assertEqual(sum(map(int,re.findall(r'\d+\. (\d+) phút:',a['answer']))),25)
        b=self.ask('Tuần sau thêm 60 phút, lập kế hoạch tiếp nối.',a);self.assertEqual(sum(map(int,re.findall(r'\d+\. (\d+) phút:',b['answer']))),60);self.assertIn('chưa xong',b['answer'])
        c=self.ask('Kế hoạch này có giúp cả lớp tốt nghiệp đúng hạn không?',b);self.assertEqual(c['metadata']['advisor_intent'],'class_strategy');self.assertIn('chưa đủ',c['answer'])
    def test_evidence(self):
        a=self.ask('Dựa trên hồ sơ, ai chắc chắn bị cảnh báo học vụ?');self.assertIn('chưa đủ căn cứ',a['answer']);self.assertNotIn('DEMO_A',a['answer'])
        b=self.ask('Nhóm không có tín hiệu chắc chắn an toàn không?',a);self.assertIn('không chứng minh',b['answer'])
        c=self.ask('Ước lượng tỷ lệ tốt nghiệp đúng hạn của lớp.',b);self.assertNotIn('%',c['answer']);self.assertIn('chưa thể tính',c['answer'])
    def test_action_status(self):
        a=self.ask('Lập danh sách việc cần làm sau buổi gặp sinh viên 24000001, có người thực hiện và hạn.');self.assertIn('Xác nhận bảng điểm',a['answer'])
        b=self.ask('Cô đã xác nhận bảng điểm mới nhưng chưa nhập dữ liệu.',a);self.assertIn('không thay đổi',b['answer']);self.assertIn('Chưa ghi',b['answer'])
        c=self.ask('Chỉ cho cô xem việc còn lại.',b);self.assertNotIn('Xác nhận bảng điểm mới nhất',c['answer']);self.assertIn('Nhập hoặc đối chiếu',c['answer'])
    def test_no_unsupported_persistence(self):
        a=self.ask('Lập danh sách việc cần làm cho sinh viên 24000001, kèm hạn.');b=self.ask('Cô chưa xác nhận bảng điểm, đừng đánh dấu xong.',a);c=self.ask('Chỉ cho cô xem việc còn lại.',b);self.assertIn('Xác nhận bảng điểm',c['answer'])
    def test_conceptual(self):
        a=self.ask('Phân biệt quy chế theo khóa tuyển sinh với thông báo theo năm học.');self.assertIn('không mặc nhiên',a['answer']);self.assertNotIn('S1',a['answer'])
    def test_scope_and_research(self):
        a=self.ask('Soạn tin nhắn riêng hẹn gặp sinh viên 24000001.');b=self.ask('Sửa giọng thân thiện hơn cho lớp K70.',a);self.assertNotIn('DEMO_A',b['answer']);self.assertNotIn('24000001',b['answer']);self.assertEqual(b['metadata']['advisor_intent'],'scope_clarification')
        self.assertEqual(self.ask('Soạn tin nhắn riêng hẹn gặp sinh viên 24000001.',force_engine='continual_lora')['answer'],'original');self.assertEqual(self.ask('Xin ngoại lệ soạn tin nhắn riêng cho sinh viên 24000001.')['routing']['risk_tier'],'RED')
        self.assertEqual(self.ask('Học phí UET năm 2024?',a)['answer'],'original')
    def test_changed_roster_and_fresh_tab(self):
        a=self.ask('Soạn tin nhắn riêng cho sinh viên 24000001.');self.roster['semester']='2026.1';b=self.ask('Viết lại thân thiện hơn.',a);self.assertEqual(b['metadata']['advisor_intent'],'scope_clarification');self.assertEqual(self.ask('Viết lại thân thiện hơn.')['answer'],'original')
    def test_existing_compound_workflow_not_hijacked(self):
        self.assertEqual(self.ask('Lớp cô có em nào cần gặp riêng? Soạn thông báo cho lớp.')['answer'],'original')
        self.assertEqual(self.ask('Cô cần lập chiến lược để cả lớp tốt nghiệp đúng hạn.')['answer'],'original')

if __name__=='__main__':unittest.main()
