import argparse,json,urllib.request,html,re
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--base',default='http://127.0.0.1:8765');a=p.parse_args()
def request(path,data=None):
    req=urllib.request.Request(a.base+path,data=json.dumps(data,ensure_ascii=False).encode() if data is not None else None,headers={'Content-Type':'application/json; charset=utf-8'})
    with urllib.request.urlopen(req,timeout=330) as r:return json.load(r)
print('INDEX:',json.dumps(request('/api/knowledge/status'),ensure_ascii=False),flush=True)
questions=['Điểm chuẩn ngành Khoa học máy tính UET năm 2024?','Quy trình rút bớt học phần?','Học phần Vật lý chất rắn EPN2062 ngành Vật lý kỹ thuật QH-2022 có bao nhiêu tín chỉ?','Thí sinh dự tuyển thạc sĩ UET đợt 1 năm 2024 cần năng lực tiếng Anh tối thiểu nào?','Thông báo hoạt động nghiên cứu khoa học cấp Viện TTNT năm học 2025-2026 có nội dung gì?','Sinh viên năm thứ hai có được chuyển ngành không?']
with a.output.open('w',encoding='utf-8') as f:
    for q in questions:
        try:r=request('/api/chat',{'question':q,'force_engine':'auto'})
        except Exception as e:r={'question':q,'error':str(e)}
        f.write(json.dumps(r,ensure_ascii=False)+'\n');f.flush();m=r.get('metadata',{});print('\n',q,'\n',m.get('engine_mode'),m.get('model_name'),'\n',html.unescape(re.sub(r'</?mark>','',r.get('answer',r.get('error','')))),flush=True)
print('PROBE_COMPLETE',a.output)
