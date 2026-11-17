#!/usr/bin/env python3
"""Exploratory UET full-main QLoRA 3B, sequential 2022 -> 2026; CUDA only.

Every stage is cryptographically checked. Never treats experimental QA as official policy.
No data is generated at training time. All inputs must be produced by build_main_dataset.py.
"""
from __future__ import annotations
import argparse
from collections import Counter
import gc
import hashlib
import inspect
import json
import os
from pathlib import Path
import re
import sys

YEARS=(2022,2023,2024,2025,2026)
MODEL='Qwen/Qwen2.5-3B-Instruct'
MAX_LEN=512


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def jread(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def jwrite(p,obj):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')
def rows(p):
    return [json.loads(x) for x in Path(p).read_text(encoding='utf-8').splitlines() if x.strip()]


def load_dataset(folder):
    folder=Path(folder)
    man=jread(folder/'manifest.json')
    if man.get('status')!='EXPLORATORY_GROUNDED_DATA_NOT_HUMAN_CERTIFIED':
        raise RuntimeError('DATA_BLOCKED: unexpected manifest provenance')
    for name in ('train.jsonl','validation.jsonl','source_corpus.jsonl'):
        if not (folder/name).is_file() or sha(folder/name)!=man['sha256'][name]:
            raise RuntimeError(f'DATA_BLOCKED: missing or altered {name}')
    train=rows(folder/'train.jsonl');val=rows(folder/'validation.jsonl')
    if len(train)!=man['train_rows'] or len(val)!=man['validation_rows']:
        raise RuntimeError('DATA_BLOCKED: manifest row counts disagree')
    if any(not isinstance(x,dict) or not x.get('id') for x in train+val):
        raise RuntimeError('DATA_BLOCKED: missing row ID')
    trainids,val_ids={x['id'] for x in train},{x['id'] for x in val}
    if len(trainids)!=len(train) or len(val_ids)!=len(val) or trainids & val_ids:
        raise RuntimeError('DATA_BLOCKED: duplicate or overlapping IDs')
    if {x['holdout_group'] for x in train}&{x['holdout_group'] for x in val}:
        raise RuntimeError('LEAKAGE_BLOCKED: same source table row in train and validation')
    if {x['source_sha256'] for x in train}&{x['source_sha256'] for x in val}:
        raise RuntimeError('LEAKAGE_BLOCKED: same source document content in train and validation')
    if {x['source_file'] for x in train}&{x['source_file'] for x in val}:
        raise RuntimeError('LEAKAGE_BLOCKED: same source path in train and validation')
    for r in train+val:
        if r['as_of_year'] not in YEARS or not all(r.get(k) for k in ('question','answer','evidence_quote','source_file','source_sha256')):
            raise RuntimeError(f'DATA_BLOCKED: malformed entry: {r.get("id")}')
        if r['review_status']!='EXPLORATORY_SOURCE_EXCERPT_NOT_INDEPENDENTLY_APPROVED':
            raise RuntimeError('DATA_BLOCKED: unexpected review provenance')
    counts=Counter(r['as_of_year'] for r in train)
    if any(counts[y]<40 for y in YEARS):
        raise RuntimeError(f'DATA_BLOCKED: insufficient yearly train items {counts}')
    # v5: user already observed a 2024 stage with only 14 training rows.
    # Do not repeat training on such a tiny yearly sample; the builder must
    # retain at least 40 rows even when a document-level holdout is impossible.
    return man,train,val


def find_model():
    override=os.getenv('CHRONOREG_MODEL_PATH','').strip()
    paths=[Path(override)] if override else [p.parent for p in Path('/kaggle/input').rglob('config.json')]
    found=[]
    for p in paths:
        try:
            c=jread(p/'config.json')
            if (c.get('model_type')=='qwen2' and c.get('hidden_size')==2048 and
                c.get('num_hidden_layers')==36 and (p/'tokenizer.json').is_file() and
                (list(p.glob('*.safetensors')) or (p/'model.safetensors.index.json').is_file())):
                found.append(p)
        except Exception:
            pass
    found=list(dict.fromkeys(map(lambda p:p.resolve(),found)))
    if len(found)!=1:
        raise RuntimeError(f'MODEL_BLOCKED: found {len(found)} valid Qwen2.5-3B-Instruct Transformers folder(s) {found}. '
                           'Attach one model through Kaggle Add Input; or set CHRONOREG_MODEL_PATH.')
    return found[0]


def gpu_preflight():
    try:
        import torch, transformers, peft, bitsandbytes, accelerate
    except Exception as exc:
        raise RuntimeError('DEPENDENCY_BLOCKED: install torch, transformers, peft, bitsandbytes, accelerate for Kaggle T4') from exc
    if not torch.cuda.is_available():raise RuntimeError('GPU_BLOCKED: enable a Kaggle T4 >=12 GiB')
    props=torch.cuda.get_device_properties(0)
    if props.total_memory<12*1024**3:
        raise RuntimeError('GPU_BLOCKED: require >=12 GiB VRAM')
    return {'gpu':props.name,'torch':torch.__version__,'transformers':transformers.__version__,
            'peft':peft.__version__,'cuda':torch.version.cuda}


def make_prompt(q: str, year:int):
    return [
        {'role':'system','content':('Bạn là trợ lý học vụ UET trong thí nghiệm. Chỉ trả lời theo dữ liệu đã học. '
           'Không bịa số tiền, tín chỉ, thời gian áp dụng. Nếu thiếu năm, khóa, ngành, loại học '
           'hoặc chưa chắc chắn, hãy nói cần xác minh hoặc hỏi lại.')},
        {'role':'user','content':f'Mốc năm cần tra cứu: {year}-{year+1}.\nCâu hỏi: {q}'},
    ]


def encode(tok,r):
    prompt=tok.apply_chat_template(make_prompt(r['question'],r['as_of_year']),tokenize=False,add_generation_prompt=True)
    prefix=tok(prompt,add_special_tokens=False)['input_ids']
    target=tok(r['answer'],add_special_tokens=False)['input_ids']
    if tok.eos_token_id is not None:target.append(tok.eos_token_id)
    if not target:raise RuntimeError('EMPTY_LABEL_BLOCKED')
    target=target[:MAX_LEN-1]
    prefix=prefix[-(MAX_LEN-len(target)):]
    ids=prefix+target
    return {'input_ids':ids,'attention_mask':[1]*len(ids),'labels':[-100]*len(prefix)+target}


class Dataset:
    def __init__(self,x):self.x=x
    def __len__(self):return len(self.x)
    def __getitem__(self,i):return self.x[i]


def collator(pad):
    import torch
    def f(batch):
        width=max(len(x['input_ids']) for x in batch)
        out={}
        for key in ('input_ids','attention_mask','labels'):
            pad_value = -100 if key=='labels' else (0 if key=='attention_mask' else pad)
            out[key]=torch.tensor([x[key]+[pad_value]*(width-len(x[key])) for x in batch])
        return out
    return f


def load_model(folder,adapter=None,training=False):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from peft import PeftModel, LoraConfig, get_peft_model, prepare_model_for_kbit_training
    tok=AutoTokenizer.from_pretrained(str(folder),local_files_only=True,trust_remote_code=False)
    if tok.pad_token_id is None:tok.pad_token=tok.eos_token
    q=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',bnb_4bit_use_double_quant=True,
                         bnb_4bit_compute_dtype=torch.float16)
    kw=dict(local_files_only=True,trust_remote_code=False,quantization_config=q,
            device_map={'':0},low_cpu_mem_usage=True)
    if 'dtype' in inspect.signature(AutoModelForCausalLM.from_pretrained).parameters:
        kw['dtype']=torch.float16
    else:kw['torch_dtype']=torch.float16
    base=AutoModelForCausalLM.from_pretrained(str(folder),**kw)
    if training:
        base.config.use_cache=False
        base=prepare_model_for_kbit_training(base,use_gradient_checkpointing=True,
                                             gradient_checkpointing_kwargs={'use_reentrant':False})
    if adapter is not None:
        model=PeftModel.from_pretrained(base,str(adapter),is_trainable=training,local_files_only=True)
    elif training:
        model=get_peft_model(base,LoraConfig(task_type='CAUSAL_LM',r=8,lora_alpha=16,lora_dropout=.05,
                      target_modules=['q_proj','k_proj','v_proj','o_proj'],bias='none'))
    else:raise RuntimeError('A real adapter is required for inference')
    if training and not any('lora_' in name and param.requires_grad for name,param in model.named_parameters()):
        raise RuntimeError('MODEL_BLOCKED: adapter frozen, cannot train')
    return model,tok


def verify_stage(path,year,data_hash,base_hash,previous):
    path=Path(path)
    for f in ('adapter_model.safetensors','adapter_config.json','full_stage.json'):
        if not (path/f).is_file():raise RuntimeError(f'CHECKPOINT_BLOCKED: missing {path/f}')
    m=jread(path/'full_stage.json')
    if not (m.get('year')==year and m.get('data_sha256')==data_hash and
            m.get('base_config_sha256')==base_hash and m.get('previous_adapter_sha256')==previous and
            m.get('adapter_sha256')==sha(path/'adapter_model.safetensors')):
        raise RuntimeError(f'CHECKPOINT_BLOCKED: incorrect checksum or stage provenance: {path}')
    return m


def train(bundle,output,epochs=1.0):
    import torch
    from transformers import TrainingArguments, Trainer
    manifest,data,val=load_dataset(bundle)
    hw=gpu_preflight();model_dir=find_model()
    output=Path(output)
    out_ck=output/'checkpoints';out_ck.mkdir(parents=True,exist_ok=True)
    data_hash=sha(Path(bundle)/'train.jsonl')
    base_hash=sha(model_dir/'config.json')
    config=output/'run_config.json'
    expected=dict(status='COURSE_RESEARCH_NOT_OFFICIAL_RELEASE',data_sha256=data_hash,
                  git_commit=manifest['git_commit'],base_config_sha256=base_hash,epochs=epochs)
    if config.exists() and any(jread(config).get(k)!=v for k,v in expected.items()):
        raise RuntimeError('RESUME_BLOCKED: model/data/epochs changed; choose a NEW output directory')
    if not config.exists():jwrite(config,{**expected,'hardware':hw,'rows':len(data),'validation_rows':len(val)})
    previous=None;prev_hash=None
    for year in YEARS:
        dest=out_ck/f'year-{year}'
        if dest.exists():
            verify_stage(dest,year,data_hash,base_hash,prev_hash)
            print(f'VERIFIED EXISTING STAGE {year}',flush=True)
        else:
            if (out_ck/f'.year-{year}.partial').exists():
                raise RuntimeError(f'PARTIAL_STAGE_BLOCKED: review {year} partial before retry')
            selected=[v for v in data if v['as_of_year']==year]
            print(f'TRAIN REAL {year}: {len(selected)} rows, {epochs} epochs',flush=True)
            model,tok=load_model(model_dir,previous,training=True)
            encoded=[encode(tok,v) for v in selected]
            args=TrainingArguments(output_dir=str(output/f'trainer-{year}'),
                  per_device_train_batch_size=1,gradient_accumulation_steps=8,
                  num_train_epochs=epochs,learning_rate=1e-4,logging_steps=20,
                  save_strategy='no',report_to='none',remove_unused_columns=False,
                  dataloader_num_workers=0,fp16=True,bf16=False,
                  optim='paged_adamw_8bit',gradient_checkpointing=True,
                  gradient_checkpointing_kwargs={'use_reentrant':False},
                  max_grad_norm=.3,seed=42)
            trainer_kwargs={'model':model,'args':args,'train_dataset':Dataset(encoded),
                            'data_collator':collator(tok.pad_token_id)}
            if 'processing_class' in inspect.signature(Trainer.__init__).parameters:
                trainer_kwargs['processing_class']=tok
            else:trainer_kwargs['tokenizer']=tok
            trainer=Trainer(**trainer_kwargs)
            result=trainer.train()
            loss=float(result.training_loss)
            if not (0<loss<float('inf')):raise RuntimeError('TRAINING_BLOCKED: non-finite loss')
            working=out_ck/f'.year-{year}.partial';working.mkdir()
            model.save_pretrained(str(working),safe_serialization=True)
            tok.save_pretrained(str(working))
            jwrite(working/'full_stage.json',dict(year=year,rows=len(selected),loss=loss,
                  data_sha256=data_hash,base_config_sha256=base_hash,
                  previous_adapter_sha256=prev_hash,
                  adapter_sha256=sha(working/'adapter_model.safetensors'),
                  status='EXPERIMENTAL_NOT_OFFICIAL_RELEASE'))
            working.rename(dest)
            del trainer,model,tok
            gc.collect();torch.cuda.empty_cache()
            verify_stage(dest,year,data_hash,base_hash,prev_hash)
        previous=dest;prev_hash=sha(dest/'adapter_model.safetensors')
    jwrite(output/'completion.json',dict(status='FIVE_REAL_STAGES_NOT_OFFICIAL_RELEASE',
           stages=YEARS,last_adapter_sha256=prev_hash,git_commit=manifest['git_commit']))
    print('ALL FIVE STAGES TRAINED AND CHECKSUM VERIFIED',flush=True)


def preflight(bundle):
    man,train,val=load_dataset(bundle)
    counts=Counter(x['as_of_year'] for x in train)
    print(json.dumps({'status':'DATA_READY_NOT_TRAINED','commit':man['git_commit'],'sources':man['source_markdown_count'],
                      'parsed_sources':man['source_parsed_count'],'facts':man['fact_count'],
                      'training':len(train),'validation':len(val),
                      'year_counts':counts,'topics':man['facts_by_topic'],
                      'not_officially_approved':True},ensure_ascii=False,indent=2))


def live(bundle,out,year,question):
    import torch
    load_dataset(bundle)
    gpu_preflight();model_dir=find_model()
    out=Path(out)
    if not (out/'completion.json').exists():raise RuntimeError('LIVE_BLOCKED: stage training not finished')
    last=out/'checkpoints/year-2026'
    config=jread(out/'run_config.json')
    verify_stage(last,2026,sha(Path(bundle)/'train.jsonl'),sha(model_dir/'config.json'),
                 sha(out/'checkpoints/year-2025/adapter_model.safetensors'))
    model,tok=load_model(model_dir,last,training=False)
    model.eval()
    p=tok.apply_chat_template(make_prompt(question,year),tokenize=False,add_generation_prompt=True)
    inputs=tok(p,return_tensors='pt',add_special_tokens=False)
    inputs={k:v.to('cuda:0') for k,v in inputs.items()}
    with torch.inference_mode():
        result=model.generate(**inputs,max_new_tokens=180,do_sample=False,pad_token_id=tok.pad_token_id)
    print(tok.decode(result[0][inputs['input_ids'].shape[1]:],skip_special_tokens=True).strip())


def main():
    p=argparse.ArgumentParser()
    p.add_argument('command',choices=['preflight','train','ask'])
    p.add_argument('--bundle',type=Path,required=True)
    p.add_argument('--out',type=Path,default=Path('/kaggle/working/chronoreg_full_main'))
    p.add_argument('--epochs',type=float,default=1.0)
    p.add_argument('--year',type=int,default=2026)
    p.add_argument('--question',default='')
    a=p.parse_args()
    if a.command=='preflight':preflight(a.bundle)
    elif a.command=='train':train(a.bundle,a.out,a.epochs)
    else:
        if not 2022<=a.year<=2026:raise RuntimeError('YEAR_BLOCKED: only 2022 to 2026 supported')
        if not a.question.strip():raise RuntimeError('QUESTION_BLOCKED: empty')
        live(a.bundle,a.out,a.year,a.question)

if __name__=='__main__':main()
