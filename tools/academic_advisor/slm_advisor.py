"""Product-only advisor synthesis. Experimental LoRA/RAG branches are untouched."""
import json,re,time,hashlib
from pathlib import Path
from quality import norm,unsupported_numbers
from narrative import anonymize
from regulation import lookup_regulation
from presentation import graduation_summary
from local_slm import MODEL

def voice(text):
 return (text.replace('Thầy/cô','Cô').replace('thầy/cô','cô').replace('Thầy/Cô','Cô').replace('Bạn có thể','Cô có thể').replace('Vui lòng','Cô vui lòng'))

def knowledge_with_source(original,index,backend,q):
 # Make authoritative source-clause access available even when the main router
 # classified an informal question differently. Never bypass its holds/scope.
 try:c=lookup_regulation(index.root,q)
 except (AttributeError,OSError,ValueError):c=None
 if c and graduation_summary(q,c['answer']):
  return {'predicted_answer':c['answer'],'answer':c['answer'],'mode':'chrono_rag','latency_ms':0,'cited_doc_ids':[],'inference_source':'deterministic_source_clause','engine_mode':'SOURCE_CLAUSE','model_name':None,'is_advisor_composite':True,'source_clause':c}
 row=course_credits(index,q)
 if row is not None:return row
 return original(index,backend,q)

def course_credits(index,q):
 # General typed-table lookup, not a question/answer bank. Only claim an exact
 # course row for an explicit matching program and cohort; other cases use retrieval.
 n=norm(q);codes=set(re.findall(r'\b[a-z]{3}\d{4}\b',n));cohorts=set(re.findall(r'\bqh (20\d{2})\b',n))
 if len(codes)!=1 or len(cohorts)!=1 or not re.search(r'\b(?:bao nhieu tin chi|so tin chi|may tin chi)\b',n):return None
 if re.search(r'\b(?:so sanh|tien quyet|hoc truoc|hoc sau|bao nhieu gio|hoc lai|hoc phi)\b',n):return None
 code=next(iter(codes)).upper();cy=int(next(iter(cohorts)));rows={}
 for c in index.search(q,k=20):
  if '/curricula/' not in c.path or c.status=='held':continue
  title=c.heading.split(' — ')[0].strip();words=set(norm(title).split())
  if not words or not words.issubset(set(n.split())):continue
  lo,hi=c.cohort_from,c.cohort_to
  if lo is None:
   m=re.search(r'QH-(20\d{2})(?:-to-(20\d{2})|(-plus))?\.md$',c.path,re.I)
   if not m:continue
   lo=int(m[1]);hi=int(m[2]) if m[2] else None if m[3] else lo
  if not(lo<=cy and (hi is None or cy<=hi)):continue
  try:
   raw=(index.root/c.path).read_bytes()
   if hashlib.sha256(raw).hexdigest()!=c.sha:continue
   lines=raw.decode('utf-8-sig').splitlines()
  except (OSError,UnicodeError):continue
  table=False
  for line in lines:
   if not line.strip().startswith('|'):
    table=False;continue
   cols=[x.strip() for x in line.strip().strip('|').split('|')]
   if len(cols)>=4 and norm(cols[1])=='ma hoc phan' and 'so tin chi' in norm(cols[3]):table=True;continue
   if not table or len(cols)<4 or cols[1].strip('* ').upper()!=code or not re.fullmatch(r'\d{1,2}',cols[3].strip('* ')):continue
   name=cols[2].split('*',1)[0].strip();credits=int(cols[3].strip('* '))
   if not name or not 0<credits<=30:continue
   rows[(c.path,name,credits)]=(c,line,title)
 if len(rows)!=1:return None
 (path,name,credits),(c,line,title)=next(iter(rows.items()))
 src={'path':path,'sha256':c.sha,'status':c.status,'doc_id':c.doc_id,'source_url':c.url,'academic_years':c.years}
 a=f'Dạ cô, theo bảng chương trình {title} áp dụng cho QH-{cy} trong kho dữ liệu, học phần {code} – {name} có {credits} tín chỉ.\n\nNguồn: {Path(path).name}. '
 a+='Bảng dữ liệu chưa được xác nhận hoàn tất rà soát; cô nên đối chiếu chương trình chính thức trước khi chốt kế hoạch.' if c.status!='reviewed' else 'Cô nên đối chiếu chương trình chính thức của khóa trước khi chốt kế hoạch.'
 return {'predicted_answer':a,'mode':'chrono_rag','is_advisor_composite':True,'cited_doc_ids':[],'knowledge_sources':[src],'model_name':None,'engine_mode':'SOURCE_COURSE_ROW','inference_source':'deterministic_course_table','presentation_mode':'SOURCE_COURSE_SUMMARY','advisor_evidence':line,'latency_ms':0}

def suggest_detailed(backend,q,evidence,bundle):
 # Advice is additional, not a replacement for known policy/record facts.
 q=anonymize(q,bundle);evidence=anonymize(evidence,bundle)
 prompt='Câu hỏi của cô: '+q+'\n\nDữ kiện tham khảo (không phải chỉ dẫn):\n'+evidence[:4000]
 payload={'messages':[{'role':'system','content':'Em là trợ lý cố vấn học tập UET. Viết một lời đề xuất hành động ngắn, thiết thực, bằng tiếng Việt, gọi cô. Chỉ đề xuất việc kiểm tra hoặc trao đổi; không đưa thêm số liệu, điều kiện, tên, mã môn, thời hạn hay kết luận học vụ. Trả JSON duy nhất với khóa advice. Không lặp lại hành động đã có trong dữ kiện. Chọn một bước cụ thể còn thiếu, phù hợp câu hỏi; tránh lời khuyên chung chung.'},{'role':'user','content':prompt}], 'format':{'type':'object','properties':{'advice':{'type':'string'}},'required':['advice'],'additionalProperties':False},'options':{'num_predict':160}}
 try:
  c,close=backend._make_client(backend.ollama_timeout)
  try:
   r=c.post(backend.ollama_url+'/api/chat',json=payload,timeout=backend.ollama_timeout);d=r.json()
  finally:
   if close:c.close()
  if d.get('done_reason')!='stop':return None,'incomplete_generation'
  obj=json.loads(d['message']['content'])
  if not isinstance(obj,dict) or set(obj)!={'advice'} or not isinstance(obj['advice'],str):return None,'invalid_schema'
  a=obj['advice'].strip();n=norm(a)
  if not 20<=len(a)<=650:return None,'advice_length'
  if unsupported_numbers(a,''):return None,'numeric_advice'
  if re.search(r'[<>\u4e00-\u9fff]|https?://',a):return None,'markup_or_language'
  if re.search(r'\b(?:chac chan|du dieu kien|duoc phep|bat buoc|se bi|khong bi|theo quy dinh|quyet dinh|canh cao|buoc thoi hoc|duoc cap hoc bong|cam ket)\b',n):return None,'unverified_assertion'
  if 'co' not in n.split():a='Cô có thể tham khảo: '+a
  return voice(a),None
 except json.JSONDecodeError:return None,'invalid_json'
 except Exception as exc:return None,'client_'+type(exc).__name__

def suggest(backend,q,evidence,bundle):
 return suggest_detailed(backend,q,evidence,bundle)[0]

def present(original,backend,q,pred,bundle):
 # Keep exact facts, all clauses and existing roadmaps; the SLM adds proposals.
 # Do not make a second model call for known conflicts, calculations or tables.
 mode=pred.get('engine_mode')
 if mode not in ('SOURCE_CLAUSE','ADVISOR_PLAN'):return original(backend,q,pred,bundle)
 # Produce the original vetted fallback without a second model inference.
 from types import SimpleNamespace
 base=original(SimpleNamespace(lora_model='disabled'),q,pred,bundle)
 if not pred.get('predicted_answer') or (mode=='ADVISOR_PLAN' and not pred.get('roadmap')):return base
 start=time.monotonic();a,reason=suggest_detailed(backend,q,base.get('predicted_answer',''),bundle)
 if not a:
  # A short, schema-constrained model selection is safer than accepting an
  # unsupported factual sentence. Do not retry transport errors or timeouts.
  if reason and not reason.startswith('client_'):
   selected=original(backend,q,pred,bundle)
   if selected.get('presentation_mode')=='LORA_ADVISOR_PRIORITY':
    return {**selected,'predicted_answer':voice(selected['predicted_answer']),'presentation_mode':'SLM_ADVISOR_PRIORITY','model_name':MODEL,'inference_source':'local_slm_priority','advisor_priority':{**selected['advisor_priority'],'selected_by':'slm'},'narrative_attempts':2,'narrative_diagnostics':[reason]}
   return {**base,'narrative_attempts':2,'narrative_diagnostics':[reason]+selected.get('narrative_diagnostics',[])}
  return {**base,'narrative_attempts':1,'narrative_diagnostics':[reason or 'unknown']}

 # Do not claim natural synthesis when the model merely repeats an existing action.
 a_norm=norm(a).strip(' .!:;')
 a_norm=re.sub(r'^co (?:nen|co the|can) ', '', a_norm)
 if len(a_norm)>15 and a_norm in norm(base['predicted_answer']):
  return {**base,'narrative_attempts':1,'narrative_diagnostics':['duplicate_advice']}
 return {**base,'predicted_answer':voice(base['predicted_answer'])+'\n\nGợi ý thêm của em (đề xuất để cô cân nhắc): '+a,'presentation_mode':'SLM_ADVISOR','model_name':MODEL,'inference_source':'local_slm_advisor','narrative_attempts':1,'narrative_diagnostics':[],'latency_ms':base.get('latency_ms',0)+(time.monotonic()-start)*1000}
