"""Regression probe for real HTTP server; not an independent benchmark."""
import argparse,json,urllib.request
from pathlib import Path

def request(url,payload=None):
    b=None if payload is None else json.dumps(payload,ensure_ascii=False).encode('utf-8')
    with urllib.request.urlopen(urllib.request.Request(url,data=b,headers={'Content-Type':'application/json; charset=utf-8'}),timeout=360) as r: return json.loads(r.read().decode('utf-8'))
def main():
    p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--url',default='http://127.0.0.1:8765');a=p.parse_args()
    h=request(a.url+'/api/health');assert h['all_models_ready'] and h['base_model']=='chronoreg-base:7b' and h['lora_model']=='chronoreg-lora:7b' and not h['peft_v3']['ready'],h
    val=a.repo/'experiments/qlora7b_course_20261126/training/chronoreg_course/dataset/validation'
    ids={'admissions-2023-cn3-thpt','review-c631e74ddcdf70eaab3c','uet-v3-020','uet-v6-039'}
    rows=[json.loads(l) for f in sorted(val.glob('*.jsonl')) for l in f.read_text(encoding='utf-8-sig').splitlines() if l.strip()]; chosen={r['id']:r for r in rows if r['id'] in ids};assert set(chosen)==ids
    cases=[dict(id='manual-2024',question='Điểm chuẩn ngành Khoa học máy tính của UET năm 2024 là bao nhiêu?',answer='27,58 điểm'),dict(id='manual-2026',question='điểm chuẩn các ngành 2026',answer='Đủ 20 ngành theo bảng nguồn năm 2026'),*chosen.values()]
    cases += [dict(id='scholarship-standard-2023',question='Mức học bổng xuất sắc chương trình chuẩn khóa QH-2021 năm học 2023-2024?',answer='1.590.000 đồng/tháng'),dict(id='scholarship-clc-2023',question='Mức học bổng giỏi CLC CNTT khóa QH-2023 năm học 2023-2024?',answer='3.800.000 đồng/tháng'),dict(id='scholarship-standard-2025',question='Mức học bổng xuất sắc chương trình chuẩn khóa QH-2021 năm học 2025-2026?',answer='2.050.000 đồng/tháng')]
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('w',encoding='utf-8') as f:
        for c in cases:
            try:
                r=request(a.url+'/api/chat',{'question':c['question'],'force_engine':'chrono_rag'})
                rec={'id':c['id'],'expected':c['answer'],'evidence':c.get('evidence_quote'),'response':r}
                m=r.get('metadata',{}); print('\n',c['id'],m.get('inference_source'),m.get('model_name'), '\nExpected:',c['answer'],'\nActual:',r.get('answer'),flush=True)
            except Exception as exc:
                rec={'id':c['id'],'error':str(exc)};print(rec,flush=True)
            f.write(json.dumps(rec,ensure_ascii=False)+'\n');f.flush()
    print('PROBE_COMPLETE',a.output,flush=True)
if __name__=='__main__':main()
