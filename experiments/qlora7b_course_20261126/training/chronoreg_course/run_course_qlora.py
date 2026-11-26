"""ChronoReg UET-VNU snapshot course experiment; NOT the canonical release runner."""
from __future__ import annotations
import argparse, collections, gc, hashlib, json, math, os, re, sys, unicodedata
from pathlib import Path

YEARS=list(range(2022,2027))
MODEL='Qwen/Qwen2.5-7B-Instruct'
REVISION='a09a35458c702b33eeacc393d103063234e8bc28'
SYSTEM='Bạn là trợ lý hỏi đáp quy định UET. Trả lời theo năm học được hỏi. Nếu thiếu bằng chứng, nói rõ không đủ thông tin. Không bịa nguồn hoặc số liệu.'
CONFIG=dict(model=MODEL,revision=REVISION,quantization='nf4_double_quant',dtype='float32',optimizer='adamw_torch',seed=42,epochs=2,max_seq_length=512,max_new_tokens=160,batch_size=1,gradient_accumulation_steps=8,learning_rate=0.0001,lora_r=8,lora_alpha=16,lora_dropout=.05,target_modules=['q_proj','k_proj','v_proj','o_proj'],strategy='sequential_no_replay',single_gpu=True,year_convention='academic_year_start_snapshot_proxy',official_training_authorized=False)

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def norm(s): return re.sub(r'\s+',' ',unicodedata.normalize('NFC',s)).strip()
def qkey(s): return norm(s).casefold().strip(' .?!')
def readj(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def rows(p): return [json.loads(s) for s in p.read_text(encoding='utf-8-sig').splitlines() if s.strip()]
def savej(p,obj):
    p.parent.mkdir(parents=True,exist_ok=True); tmp=p.with_name(p.name+'.tmp'); tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8'); tmp.replace(p)
def jsonl(p,items):
    p.parent.mkdir(parents=True,exist_ok=True); tmp=p.with_name(p.name+'.tmp'); tmp.write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in items),encoding='utf-8'); tmp.replace(p)
def must(ok,msg):
    if not ok: raise RuntimeError(msg)
def safe(root,rel):
    p=(root/rel).resolve(); must(p.is_relative_to(root.resolve()),'path escape: '+str(rel)); return p

def verify(bundle):
    m=readj(bundle/'bundle_manifest.json'); must(m['schema']=='chronoreg-course-kaggle-7b-v1','bad manifest')
    must(m['config']==CONFIG,'config mismatch')
    for rel,h in m['files'].items():
        p=safe(bundle,rel); must(p.is_file() and sha(p)==h,'bundle SHA mismatch: '+rel)
    d=bundle/'dataset'; dm=readj(d/'manifest.json'); must(dm['official_training_authorized'] is False,'unexpected dataset release state')
    groups={s:set() for s in ['train','validation']}; ids=set(); questions=set(); data={}; cache={}; count=collections.Counter(); bases=collections.Counter(); exactmiss=0
    for y in YEARS:
        data[y]={}
        for s in groups:
            rr=rows(d/s/f'{y}.jsonl'); must(len(rr)==dm['by_stage'][str(y)][s] and len(rr)>0,f'{y} {s} count')
            for r in rr:
                rid=r['id']; must(rid not in ids,'duplicate ID: '+rid); ids.add(rid)
                must(r['as_of_year']==y and r['review_status']=='snapshot_technical_review_pass','bad stage/review '+rid)
                must(all(isinstance(r.get(k),str) and r[k].strip() for k in ['question','answer','source_file','source_sha256','evidence_quote','group_id']),'missing field '+rid)
                q=(y,qkey(r['question'])); must(q not in questions,'duplicate stage question '+rid); questions.add(q);groups[s].add(r['group_id'])
                src=r['source_file']; p=safe(d/'sources',src)
                if src not in cache: cache[src]=(sha(p),p.read_text(encoding='utf-8-sig'),norm(p.read_text(encoding='utf-8-sig')))
                h,t,nt=cache[src]; must(h==r['source_sha256'],'source hash '+rid); must(norm(r['evidence_quote']) in nt,'evidence mismatch '+rid)
                exactmiss+=int(r['evidence_quote'] not in t);count[s]+=1;bases[r['stage_basis']]+=1
            data[y][s]=rr
    must(not groups['train']&groups['validation'],'fact overlap');must(count['train']==1774 and count['validation']==197,'unexpected total')
    report={'status':'SNAPSHOT_CPU_PREFLIGHT_PASS','canonical_release':False,'counts':dict(count),'unique_sources':len(cache),'normalized_evidence_only':exactmiss,'stage_basis':dict(bases),'bundle_manifest_sha256':sha(bundle/'bundle_manifest.json'),'source_commit':dm['base_commit'],'training_config':CONFIG}
    return data,report

def messages(q,y): return [{'role':'system','content':SYSTEM},{'role':'user','content':f'Năm học: {y}-{y+1}\nCâu hỏi: {q}'}]
def encode(tok,r):
    p=tok.apply_chat_template(messages(r['question'],r['as_of_year']),tokenize=False,add_generation_prompt=True)
    a=tok(p,add_special_tokens=False)['input_ids']; b=tok(r['answer'],add_special_tokens=False)['input_ids']; must(tok.eos_token_id is not None and bool(b),'empty response'); ids=a+b+[tok.eos_token_id]
    must(len(ids)<=CONFIG['max_seq_length'],'OVER_LENGTH '+r['id']+': '+str(len(ids)))
    return dict(input_ids=ids,attention_mask=[1]*len(ids),labels=[-100]*len(a)+b+[tok.eos_token_id])
class Dataset:
    def __init__(self,data): self.data=data
    def __len__(self): return len(self.data)
    def __getitem__(self,i): return self.data[i]
def pad(batch,pad_id):
    import torch
    n=max(len(x['input_ids']) for x in batch)
    return {k:torch.tensor([x[k]+[v]*(n-len(x[k])) for x in batch],dtype=torch.long) for k,v in [('input_ids',pad_id),('attention_mask',0),('labels',-100)]}

def gpu_setup(data):
    import torch
    from transformers import AutoTokenizer
    must(torch.cuda.is_available(),'CUDA unavailable: select GPU accelerator'); must(torch.cuda.device_count()==1,'Exactly one visible CUDA device required; set CUDA_VISIBLE_DEVICES=0 before starting Python'); g=torch.cuda.get_device_properties(0); must(g.total_memory/2**30>=12,'GPU requires >=12 GiB VRAM')
    tok=AutoTokenizer.from_pretrained(MODEL,revision=REVISION,trust_remote_code=False)
    if tok.pad_token_id is None: tok.pad_token=tok.eos_token
    enc={y:{s:[encode(tok,r) for r in data[y][s]] for s in data[y]} for y in YEARS}
    gpu={'gpu':g.name,'vram_gib':round(g.total_memory/2**30,2),'torch':torch.__version__,'max_tokens':max(len(x['input_ids']) for y in YEARS for s in enc[y] for x in enc[y][s])}
    from importlib.metadata import version
    gpu['packages']={p:version(p) for p in ['transformers','peft','accelerate','bitsandbytes','safetensors']}
    gpu['cuda']=torch.version.cuda; gpu['device_count']=torch.cuda.device_count()
    must(gpu['packages']['bitsandbytes']=='0.49.0','Expected bitsandbytes 0.49.0; see requirements')
    return torch,tok,enc,gpu

def model_load(torch,previous,training):
    from transformers import AutoModelForCausalLM,BitsAndBytesConfig
    from peft import LoraConfig,PeftModel,get_peft_model,prepare_model_for_kbit_training
    q=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',bnb_4bit_use_double_quant=True,bnb_4bit_compute_dtype=torch.float32)
    model=AutoModelForCausalLM.from_pretrained(MODEL,revision=REVISION,quantization_config=q,torch_dtype=torch.float32,device_map={'':0},trust_remote_code=False,use_safetensors=True,attn_implementation='eager')
    if training:
        model.config.use_cache=False
        model=prepare_model_for_kbit_training(model,use_gradient_checkpointing=True,gradient_checkpointing_kwargs={'use_reentrant':False})
        if previous is not None: model=PeftModel.from_pretrained(model,str(previous),is_trainable=True)
        else: model=get_peft_model(model,LoraConfig(task_type='CAUSAL_LM',r=8,lora_alpha=16,lora_dropout=.05,target_modules=CONFIG['target_modules'],bias='none'))
    else:
        must(previous is not None,'inference needs checkpoint');model=PeftModel.from_pretrained(model,str(previous),is_trainable=False);model.eval()
    return model

def chain(out,signature):
    done=[]; previous=None
    for y in YEARS:
        p=out/'checkpoints'/f'year-{y}'
        if not p.exists(): continue
        must(y==YEARS[len(done)],'checkpoint chain gap'); m=readj(p/'stage.json'); must(m['signature']==signature and m['year']==y and m['previous_adapter_sha256']==previous and m['model']==MODEL and m['revision']==REVISION and m['status']=='TRAINED_COURSE_SNAPSHOT_NOT_RELEASED','checkpoint provenance mismatch'); must({'adapter_model.safetensors','adapter_config.json'}<=set(m['files']),'missing checkpoint files')
        for name,h in m['files'].items(): must(sha(p/name)==h,'checkpoint file mismatch '+name)
        previous=m['files']['adapter_model.safetensors'];done.append(y)
    return done

def trainer_args(out, y, smoke=False):
    from transformers import TrainingArguments
    return TrainingArguments(output_dir=str(out),per_device_train_batch_size=1,per_device_eval_batch_size=1,gradient_accumulation_steps=CONFIG['gradient_accumulation_steps'],num_train_epochs=CONFIG['epochs'],max_steps=1 if smoke else -1,learning_rate=CONFIG['learning_rate'],seed=CONFIG['seed']+y,report_to='none',save_strategy='no',eval_strategy='no',logging_steps=1,remove_unused_columns=False,label_names=['labels'],dataloader_num_workers=0,fp16=False,bf16=False,gradient_checkpointing=True,gradient_checkpointing_kwargs={'use_reentrant':False},optim='adamw_torch',max_grad_norm=.3,logging_nan_inf_filter=False)

def fit(torch,model,tok,encoded,out,y,smoke=False):
    from transformers import Trainer
    before={n:v.detach().float().cpu().clone() for n,v in model.named_parameters() if v.requires_grad and 'lora_' in n}
    must(bool(before),'no trainable LoRA');must(all(bool(torch.isfinite(v).all()) for v in before.values()),'invalid initial adapter')
    trainer=Trainer(model=model,args=trainer_args(out,y,smoke),train_dataset=Dataset(encoded),data_collator=lambda b:pad(b,tok.pad_token_id),processing_class=tok)
    result=trainer.train(); logs=trainer.state.log_history;must(result.global_step>0 and math.isfinite(result.training_loss),'nonfinite loss / no steps')
    grads=[float(x['grad_norm']) for x in logs if 'grad_norm' in x];must(bool(grads) and all(math.isfinite(g) for g in grads) and any(g>0 for g in grads),'invalid gradients')
    after={n:v.detach().float().cpu() for n,v in model.named_parameters() if v.requires_grad and 'lora_' in n};must(set(after)==set(before),'adapter parameter set changed');must(all(bool(torch.isfinite(v).all()) for v in after.values()),'nonfinite adapter')
    delta=max(float((after[n]-before[n]).abs().max()) for n in before);must(delta>0 and math.isfinite(delta),'no adapter update')
    evidence={'optimizer_steps':result.global_step,'train_loss':result.training_loss,'max_adapter_delta':delta,'logged_grad_norm_min':min(grads),'logged_grad_norm_max':max(grads)}
    del trainer,before,after;gc.collect();torch.cuda.empty_cache()
    return evidence,logs

def validate_loss(torch,model,tok,encoded):
    # Explicit single-device validation; no DataParallel, no accumulating logits.
    model.eval(); total=0.; tokens=0
    with torch.inference_mode():
        for item in encoded:
            batch={k:v.to('cuda:0') for k,v in pad([item],tok.pad_token_id).items()}
            n=int((batch['labels'][:,1:]!=-100).sum().item());must(n>0,'empty validation labels')
            result=model(**batch,use_cache=False)
            loss=float(result.loss.item());must(math.isfinite(loss),'nonfinite validation loss')
            total+=loss*n;tokens+=n;del result,batch
    must(tokens>0,'no validation tokens');torch.cuda.synchronize()
    return {'loss':total/tokens,'rows':len(encoded),'answer_tokens':tokens,'aggregation':'answer_token_weighted'}

def smoke_test(out,data,report):
    from transformers import set_seed
    torch,tok,enc,gpu=gpu_setup(data);out.mkdir(parents=True,exist_ok=True)
    marker=out/'gpu_smoke.json'
    if marker.exists(): marker.unlink()
    torch.cuda.reset_peak_memory_stats();set_seed(CONFIG['seed']+2022)
    model=model_load(torch,None,True)
    # Longest actual samples, enough for one full accumulation step.
    selected=sorted([x for y in YEARS for x in enc[y]['train']],key=lambda x:len(x['input_ids']),reverse=True)[:CONFIG['gradient_accumulation_steps']]
    val=sorted([x for y in YEARS for x in enc[y]['validation']],key=lambda x:len(x['input_ids']),reverse=True)[:3]
    evidence,_=fit(torch,model,tok,selected,out/'smoke_scratch',2022,True)
    validation=validate_loss(torch,model,tok,val)
    result=dict(status='7B_GPU_TRAIN_VALIDATION_SMOKE_PASS',signature=report['bundle_manifest_sha256'],model=MODEL,revision=REVISION,gpu=gpu,training=evidence,validation=validation,peak_allocated_gib=round(torch.cuda.max_memory_allocated()/2**30,3),peak_reserved_gib=round(torch.cuda.max_memory_reserved()/2**30,3),smoke_adapter_saved=False)
    savej(marker,result);print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)
    del model;gc.collect();torch.cuda.empty_cache()

def train(bundle,out,data,report,through):
    from transformers import set_seed
    torch,tok,enc,gpu=gpu_setup(data);print(json.dumps(gpu,ensure_ascii=False),flush=True)
    signature=report['bundle_manifest_sha256'];out.mkdir(parents=True,exist_ok=True);done=chain(out,signature)
    smoke=readj(out/'gpu_smoke.json');must(smoke['status']=='7B_GPU_TRAIN_VALIDATION_SMOKE_PASS' and smoke['signature']==signature and smoke['gpu']==gpu,'Run GPU smoke first in the current environment')
    savej(out/'run_provenance.json',dict(report,gpu=gpu,mode='COURSE_SNAPSHOT_ONLY_NOT_CANONICAL_RELEASE'))
    for y in YEARS:
        if y>through or y in done: continue
        p=out/'checkpoints'/f'year-{y}'; partial=p.with_name('.'+p.name+'.partial');pending=p.with_name('.'+p.name+'.pending')
        must(not partial.exists(),'partial checkpoint retained: inspect before moving it')
        prev=p.parent/f'year-{y-1}' if y>2022 else None
        prior_hash=sha(prev/'adapter_model.safetensors') if prev else None
        set_seed(CONFIG['seed']+y);torch.cuda.reset_peak_memory_stats()
        if pending.exists():
            m=readj(pending/'stage.json');must(m['signature']==signature and m['model']==MODEL and m['revision']==REVISION and m['year']==y and m['previous_adapter_sha256']==prior_hash and m['status']=='TRAINED_PENDING_VALIDATION','pending provenance mismatch')
            must({'adapter_config.json','adapter_model.safetensors'}<=set(m['files']),'missing pending files')
            for name,h in m['files'].items():must(sha(pending/name)==h,'pending file mismatch '+name)
            model=model_load(torch,pending,True);print(f'Recovering trained stage {y}; validation only',flush=True)
        else:
            model=model_load(torch,prev,True)
            evidence,logs=fit(torch,model,tok,enc[y]['train'],out/'scratch'/str(y),y)
            partial.mkdir(parents=True);model.save_pretrained(str(partial),safe_serialization=True);tok.save_pretrained(str(partial));must((partial/'adapter_model.safetensors').is_file(),'adapter missing')
            savej(partial/'training_log.json',logs)
            files={x.name:sha(x) for x in partial.iterdir() if x.is_file()}
            m=dict(evidence,year=y,model=MODEL,revision=REVISION,signature=signature,previous_adapter_sha256=prior_hash,files=files,train_rows=len(enc[y]['train']),status='TRAINED_PENDING_VALIDATION')
            savej(partial/'stage.json',m);partial.rename(pending);print(f'Saved recoverable trained adapter {y}; validation pending',flush=True)
        losses={}
        for old in YEARS:
            if old>y:break
            losses[str(old)]=validate_loss(torch,model,tok,enc[old]['validation']);print('Validation',y,old,losses[str(old)],flush=True)
        m.update(validation=losses,status='TRAINED_COURSE_SNAPSHOT_NOT_RELEASED',peak_allocated_gib=round(torch.cuda.max_memory_allocated()/2**30,3),peak_reserved_gib=round(torch.cuda.max_memory_reserved()/2**30,3))
        # Rename only after successful validation; a pending stage is never used as predecessor.
        savej(pending/'stage.json',m);pending.rename(p);print(json.dumps(m,ensure_ascii=False),flush=True)
        del model;gc.collect();torch.cuda.empty_cache()
    done=chain(out,signature);savej(out/'completion.json',{'status':'ALL_FIVE_STAGES_COMPLETE' if done==YEARS else 'PARTIAL_CHAIN','years':done,'model':MODEL,'revision':REVISION,'canonical_release':False,'bundle_manifest_sha256':signature});print('Completed stages:',done,flush=True)

def predict(model,tok,torch,question,year):
    p=tok.apply_chat_template(messages(question,year),tokenize=False,add_generation_prompt=True); x=tok(p,add_special_tokens=False,return_tensors='pt').to('cuda:0')
    with torch.inference_mode(): a=model.generate(**x,do_sample=False,max_new_tokens=CONFIG['max_new_tokens'],pad_token_id=tok.pad_token_id)
    return tok.decode(a[0][x['input_ids'].shape[1]:],skip_special_tokens=True).strip()
def token_f1(a,b):
    a=collections.Counter(qkey(a).split());b=collections.Counter(qkey(b).split());n=sum((a&b).values());return 2*n/(sum(a.values())+sum(b.values())) if a and b else 0.

def evaluate(bundle,out,data,report):
    torch,tok,_,gpu=gpu_setup(data); must(chain(out,report['bundle_manifest_sha256'])==YEARS,'all stages required')
    results=[]; best={}; summary={}
    for y in YEARS:
        model=model_load(torch,out/'checkpoints'/f'year-{y}',False);stage=[]
        for old in YEARS:
            if old>y:break
            for r in data[old]['validation']:
                p=predict(model,tok,torch,r['question'],old);f=token_f1(p,r['answer']);em=int(qkey(p)==qkey(r['answer']));drop=max(0,best[r['id']]-f) if r['id'] in best else None;best[r['id']]=max(best.get(r['id'],0),f)
                stage.append(dict(id=r['id'],checkpoint_year=y,as_of_year=old,topic=r['topic'],question=r['question'],gold_answer=r['answer'],prediction=p,token_f1=f,exact_match=em,forgetting_drop=drop))
        results.extend(stage);jsonl(out/'evaluation'/f'validation_{y}.jsonl',stage);summary[str(y)]={str(old):{'n':len(rr),'token_f1':sum(x['token_f1'] for x in rr)/len(rr),'exact_match':sum(x['exact_match'] for x in rr)/len(rr)} for old in YEARS if (rr:=[x for x in stage if x['as_of_year']==old])}
        del model;gc.collect();torch.cuda.empty_cache()
    jsonl(out/'evaluation'/'validation_predictions.jsonl',results);savej(out/'evaluation'/'summary.json',{'status':'SNAPSHOT_VALIDATION_DIAGNOSTICS_NOT_VERSION_ACCURACY','by_stage_year':summary,'predictions':len(results),'note':'Not independent benchmark; lexical scores only; source/temporal overlap limitations remain.'})

def main():
    p=argparse.ArgumentParser();p.add_argument('--bundle',type=Path,default=Path(__file__).resolve().parent);p.add_argument('--out',type=Path,default=Path('/kaggle/working/chronoreg_7b_v1'));p.add_argument('command',choices=['preflight','gpu-preflight','gpu-smoke','train','evaluate']);p.add_argument('--through',type=int,choices=YEARS,default=2026);a=p.parse_args();data,r=verify(a.bundle);print(json.dumps(r,ensure_ascii=False,indent=2),flush=True)
    if a.command=='gpu-preflight': _,_,_,g=gpu_setup(data);print(json.dumps(g,ensure_ascii=False,indent=2))
    elif a.command=='gpu-smoke':smoke_test(a.out,data,r)
    elif a.command=='train':train(a.bundle,a.out,data,r,a.through)
    elif a.command=='evaluate':evaluate(a.bundle,a.out,data,r)
if __name__=='__main__':main()
