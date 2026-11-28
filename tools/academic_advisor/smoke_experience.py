"""Local demo-only conversation and response latency probe (not a research benchmark)."""
import argparse, json, re, sys, time, urllib.request
from pathlib import Path

FLOWS = [
    ('policy', [('Một bạn trượt đúng một môn thì có bị hạ loại bằng tốt nghiệp không?', ('5%',)),
                ('Nếu vậy thì chỉ cần trượt là bị hạ bằng à?', ())]),
    ('gpa', [('Giả sử GPA tích lũy 2,50 với 60 tín chỉ, kỳ tới học 15 tín chỉ đạt GPA 3,50. CPA mới là bao nhiêu?', ('2,70','2.70')),
             ('Nếu kỳ tới chỉ đạt GPA 3,00 thì sao?', ('2,60','2.60')),
             ('Còn nếu học 20 tín chỉ thì sao?', ('2,63','2.63'))]),
    ('scope', [('Lớp K65 của cô có những bạn nào cần gặp riêng?', ())]),
    ('public_draft', [('Viết giúp cô một thông báo ngắn mời cả lớp trao đổi về việc học, không nêu tên hay điểm của ai.', ()),
                      ('Rút gọn thông báo vừa rồi, giữ giọng lịch sự.', ())]),
    ('knowledge', [('Thí sinh dự tuyển thạc sĩ UET đợt 1 năm 2024 cần tiếng Anh tối thiểu bậc mấy?', ('bậc 3',)),
                   ('Chứng chỉ có thời hạn bao lâu?', ('2 năm',)),
                   ('Chứng chỉ thi online có được không?', ('không chấp nhận',))]),
    ('fresh_context', [('Trong buổi gặp đó cô nên hỏi gì?', ())]),
]

def probe(opener, url, question, context=None, timeout=450):
    payload={'question':question,'force_engine':'auto','experience':'advisor','context_token':context}
    req=urllib.request.Request(url+'/api/advisor/chat/stream',data=json.dumps(payload,ensure_ascii=False).encode(),headers={'Content-Type':'application/json','Accept':'application/x-ndjson'})
    start=time.perf_counter(); first_event=first_text=None; pieces=[]; final=None; heartbeats=0
    with opener.open(req,timeout=timeout) as res:
        if 'application/x-ndjson' not in res.headers.get('content-type',''):
            raise ValueError('unexpected content type')
        for raw in res:
            e=json.loads(raw); now=time.perf_counter()-start
            if first_event is None: first_event=now
            if final is not None: raise ValueError('event after done')
            kind=e.get('event')
            if kind=='processing': heartbeats+=1
            elif kind=='delta':
                if first_text is None: first_text=now
                pieces.append(e['text'])
            elif kind=='done': final=e['data']
            elif kind=='error': raise ValueError('server reported error')
            else: raise ValueError('unexpected event')
    elapsed=time.perf_counter()-start
    if not final or first_text is None or ''.join(pieces)!=final.get('answer'):
        raise ValueError('incomplete or inconsistent stream')
    meta=final.get('metadata') or {}
    return final, {'first_event_s':round(first_event,3),'first_text_s':round(first_text,3),'total_s':round(elapsed,3),'delivery_tail_s':round(elapsed-first_text,3),'heartbeats':heartbeats,'engine_mode':meta.get('engine_mode'),'inference_source':meta.get('inference_source'),'context_returned':bool(final.get('context_token'))}

def main():
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8765);p.add_argument('--output',type=Path,required=True);p.add_argument('--demo-only',action='store_true',required=True);p.add_argument('--show-demo',action='store_true');a=p.parse_args()
    if not 1<=a.port<=65535:p.error('invalid port')
    url=f'http://127.0.0.1:{a.port}';opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url+'/api/knowledge/status',timeout=15) as res: status=json.load(res)
    if status.get('deployment_profile')!='local-slm' or not status.get('grounded_pilot') or not status.get('semantic_pilot'):raise SystemExit('Expected full local advisor')
    rows=[]
    for name,turns in FLOWS:
        token=None; previous_answer=None
        for i,(q,expected) in enumerate(turns,1):
            try:
                final,row=probe(opener,url,q,token);token=final.get('context_token')
                answer=re.sub(r'</?mark>','',final['answer'])
                row['content_check']='MANUAL_REVIEW' if not expected else ('PASS' if any(s.casefold() in answer.casefold() for s in expected) else 'REVIEW')
                if name in ('public_draft','scope','fresh_context') and re.search(r'(?<!\d)\d{8}(?!\d)',answer):row['content_check']='REVIEW'
                if name=='policy' and i==2 and (not previous_answer or answer==previous_answer or '5%' not in answer):row['content_check']='REVIEW'
                if name=='public_draft' and i==2 and (not previous_answer or len(answer.split())>=len(previous_answer.split())):row['content_check']='REVIEW'
                if name=='policy' and i==2 and row['content_check']=='MANUAL_REVIEW' and '5%' in answer and previous_answer and answer!=previous_answer:row['content_check']='PASS'
                if name=='public_draft' and i==2 and row['content_check']=='MANUAL_REVIEW' and previous_answer and len(answer.split())<len(previous_answer.split()):row['content_check']='PASS'
                if name=='scope' and i==1 and 'không khớp' in answer and row['content_check']=='MANUAL_REVIEW':row['content_check']='PASS'
                if name=='fresh_context' and row['engine_mode']=='CONTEXT_CLARIFICATION' and not row['context_returned'] and row['content_check']=='MANUAL_REVIEW':row['content_check']='PASS'
                previous_answer=answer
                if i<len(turns) and not token:row['context_warning']='missing token before follow-up'
                if a.show_demo:print(q+'\n'+answer,flush=True)
            except Exception as exc:
                row={'error_type':type(exc).__name__,'content_check':'TRANSPORT_FAILURE'};token=None
            row.update(flow=name,turn=i);rows.append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
            a.output.parent.mkdir(parents=True,exist_ok=True)
            a.output.write_text(json.dumps({'qualification':'DEMO_TRANSFER_PROBE_NOT_BENCHMARK','revision':status.get('intelligence_revision'),'results':rows},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('EXPERIENCE_PROBE_COMPLETE',a.output)
    return int(any(r['content_check'] in ('TRANSPORT_FAILURE','REVIEW') or 'context_warning' in r for r in rows))
if __name__=='__main__':sys.exit(main())
