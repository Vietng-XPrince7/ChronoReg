"""Self-contained *classroom exploratory* QLoRA 3B; NEVER bypasses ChronoReg's official release gate.

Inputs are owner-authorized machine-excerpt-checked QA, not certified effective-year policies.
Model weights must be mounted locally in Kaggle Input, or cached by the user.
"""
from __future__ import annotations

import argparse
import collections
import csv
import gc
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile

YEARS = (2022, 2023, 2024, 2025, 2026)
MAX_LEN = 512
MODEL_ID = 'Qwen/Qwen2.5-3B-Instruct'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, obj: dict):
    path.write_text(json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + '\n', encoding='utf-8')


def norm_question(x: str) -> str:
    return re.sub(r'\s+', ' ', x.casefold().strip()).strip(' .?!')


def dataset_preflight(data_file: Path, manifest: Path) -> tuple[list[dict], dict]:
    data = [json.loads(x) for x in data_file.read_text(encoding='utf-8').splitlines() if x.strip()]
    m = json.loads(manifest.read_text(encoding='utf-8'))
    if len(data) != 200 or m.get('training_rows') != 200 or m.get('train_sha256') != sha(data_file):
        raise RuntimeError('DATA_BLOCKED: 200-row train file does not match its immutable manifest')
    ids, qs = set(), set()
    counts = collections.Counter()
    for row in data:
        ident = row.get('id'); question = row.get('question'); answer = row.get('answer')
        year = row.get('as_of_year')
        if not isinstance(year,int) or year not in YEARS or not ident or not question or not answer:
            raise RuntimeError('DATA_BLOCKED: invalid year/ID/question/answer')
        if (ident in ids or norm_question(question) in qs or not row.get('evidence_quote')
                or row.get('review_status') != 'course_experiment_not_official_release'
                or row.get('independent_review_verified') is not False
                or row.get('effective_year_verified') is not False):
            raise RuntimeError(f'DATA_BLOCKED: duplicate/ambiguous status {ident}')
        ids.add(ident); qs.add(norm_question(question)); counts[year] += 1
    if any(counts[y] < 30 for y in YEARS):
        raise RuntimeError('DATA_BLOCKED: fewer than 30 proposed-year candidates in a year')
    return data, dict(sorted(counts.items()))


def find_local_model() -> Path:
    override = os.getenv('CHRONOREG_MODEL_PATH', '').strip()
    if override:
        candidates = [Path(override)]
    else:
        roots = [Path('/kaggle/input'), Path('/kaggle/working/model')]
        candidates = []
        for root in roots:
            if root.is_dir():
                candidates.extend(p.parent for p in root.rglob('config.json'))
    good = []
    for p in candidates:
        if not (p / 'config.json').is_file():
            continue
        try:
            config = json.loads((p / 'config.json').read_text(encoding='utf-8'))
        except (ValueError,OSError):
            continue
        typ = (config.get('model_type') or '').lower()
        if typ != 'qwen2':
            continue
        if not any(p.glob('*.safetensors')) and not (p / 'model.safetensors.index.json').exists():
            continue
        if not ((p / 'tokenizer.json').exists() or (p / 'vocab.json').exists()):
            continue
        good.append(p.resolve())
    good = list(dict.fromkeys(good))
    if len(good) != 1:
        raise RuntimeError('MODEL_BLOCKED: expected one local Hugging Face Qwen2.5-3B model folder. '
                           f'Found {len(good)}: {[str(x) for x in good]}. '
                           'Use Kaggle Add Model and/or set CHRONOREG_MODEL_PATH.')
    cfg = json.loads((good[0]/'config.json').read_text(encoding='utf-8'))
    if cfg.get('hidden_size') != 2048 or cfg.get('num_hidden_layers') != 36:
        raise RuntimeError('MODEL_BLOCKED: found Qwen2 architecture but not expected 3B configuration')
    return good[0]


def runtime_preflight():
    try:
        import torch, transformers, peft, bitsandbytes, accelerate
    except ImportError as ex:
        raise RuntimeError('DEPENDENCIES_BLOCKED: required transformers/peft/accelerate/bitsandbytes/torch. '
                           'For offline Kaggle use Dependency Manager wheels or enable Internet.') from ex
    if not torch.cuda.is_available():
        raise RuntimeError('GPU_BLOCKED: activate one Kaggle T4 GPU (>=12 GiB); CPU is not supported')
    dev = torch.cuda.get_device_properties(0)
    vram = dev.total_memory / 1024**3
    if vram < 12:
        raise RuntimeError(f'GPU_BLOCKED: GPU 0 has {vram:.1f} GiB; >=12 GiB required')
    return {'gpu':dev.name,'gpu_gib':round(vram,2),
            'torch':torch.__version__,'transformers':transformers.__version__,
            'peft':peft.__version__,'accelerate':accelerate.__version__}


def load_base(model_folder: Path, previous_adapter: Path|None, training:bool=True):
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
    from peft import LoraConfig, PeftModel, get_peft_model, prepare_model_for_kbit_training
    tok = AutoTokenizer.from_pretrained(str(model_folder), local_files_only=True, trust_remote_code=False)
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token
    quant=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',
                             bnb_4bit_use_double_quant=True,bnb_4bit_compute_dtype=torch.float16)
    base=AutoModelForCausalLM.from_pretrained(
        str(model_folder),local_files_only=True,trust_remote_code=False,
        quantization_config=quant,torch_dtype=torch.float16,device_map={'':0},
        low_cpu_mem_usage=True)
    if training:
        base.config.use_cache=False
        base=prepare_model_for_kbit_training(base,use_gradient_checkpointing=True,
                                            gradient_checkpointing_kwargs={'use_reentrant':False})
    if previous_adapter is not None:
        model=PeftModel.from_pretrained(base,str(previous_adapter),is_trainable=training,
                                       local_files_only=True)
    elif training:
        lc=LoraConfig(task_type='CAUSAL_LM',r=8,lora_alpha=16,lora_dropout=0.05,
                      target_modules=['q_proj','k_proj','v_proj','o_proj'],bias='none')
        model=get_peft_model(base,lc)
    else:
        raise RuntimeError('Inference requires a verified adapter')
    if training and not any('lora_' in k and p.requires_grad for k,p in model.named_parameters()):
        raise RuntimeError('MODEL_BLOCKED: no trainable adapter parameters')
    return model,tok


def user_prompt(q: str, year: int):
    return [
        {'role':'system','content':'Bạn là trợ lý học vụ UET. Trả lời ngắn, đúng phạm vi câu hỏi; không bịa quy định hay năm hiệu lực.'},
        {'role':'user','content':f'Năm học được hỏi: {year}-{year+1}.\n{q}'},
    ]


def encode_example(tok, item: dict):
    pre=tok.apply_chat_template(user_prompt(item['question'],item['as_of_year']),
                                tokenize=False,add_generation_prompt=True)
    prefix=tok(pre,add_special_tokens=False)['input_ids']
    tail=tok(item['answer'],add_special_tokens=False)['input_ids']
    if tok.eos_token_id is not None:
        tail.append(tok.eos_token_id)
    if len(tail) >= MAX_LEN:
        tail=tail[:MAX_LEN-1]+[tok.eos_token_id]
    prefix=prefix[-(MAX_LEN-len(tail)):]
    ids=prefix+tail
    mask=[-100]*len(prefix)+tail
    if not tail or len(ids)>MAX_LEN or not any(x!=-100 for x in mask):
        raise RuntimeError('TOKENIZATION_BLOCKED: invalid supervised example')
    return {'input_ids':ids,'attention_mask':[1]*len(ids),'labels':mask}


class Dataset:
    def __init__(self,rows):self.rows=rows
    def __len__(self):return len(self.rows)
    def __getitem__(self,i):return self.rows[i]


def collator(pad_id):
    import torch
    def collate(batch):
        width=max(len(x['input_ids']) for x in batch)
        return {
            'input_ids':torch.tensor([x['input_ids']+[pad_id]*(width-len(x['input_ids'])) for x in batch]),
            'attention_mask':torch.tensor([x['attention_mask']+[0]*(width-len(x['attention_mask'])) for x in batch]),
            'labels':torch.tensor([x['labels']+[-100]*(width-len(x['labels'])) for x in batch])
        }
    return collate


def stage_valid(folder: Path, year:int, datahash:str, model_confhash:str, prior_hash: str|None):
    meta=folder/'course_stage.json';weights=folder/'adapter_model.safetensors'
    if not meta.is_file() or not weights.is_file() or not (folder/'adapter_config.json').is_file():
        raise RuntimeError(f'CHECKPOINT_BLOCKED: incomplete stage {folder}')
    m=json.loads(meta.read_text(encoding='utf-8'))
    if (m.get('year')!=year or m.get('training_data_sha256')!=datahash or
        m.get('model_config_sha256')!=model_confhash or m.get('previous_adapter_sha256')!=prior_hash or
        m.get('adapter_sha256')!=sha(weights)):
        raise RuntimeError(f'CHECKPOINT_BLOCKED: invalid saved stage {folder}')
    return m


def train(data_file: Path, manifest: Path, output: Path):
    import torch
    from transformers import TrainingArguments, Trainer
    data, counts=dataset_preflight(data_file,manifest)
    machine=runtime_preflight()
    folder=find_local_model()
    modelhash=sha(folder/'config.json'); datahash=sha(data_file)
    (output/'checkpoints').mkdir(parents=True,exist_ok=True)
    write_json(output/'course_run_provenance.json',{
        'status':'COURSE_EXPERIMENT_NOT_INDEPENDENTLY_RELEASED',
        'training_data_sha256':datahash,'train_counts':counts,
        'model_folder':str(folder),'model_config_sha256':modelhash,
        'runtime':machine,'model_id_claimed':MODEL_ID,'epochs_per_year':2,
        'note':'No claim of independent review / verified effective-year answers; exploratory results only'
    })
    prior=None;last_sha=None
    for year in YEARS:
        destination=output/'checkpoints'/f'year-{year}'
        if destination.exists():
            stage_valid(destination,year,datahash,modelhash,last_sha)
            print('VERIFIED RESUME:',year,flush=True)
        else:
            working=output/'checkpoints'/f'.year-{year}.partial'
            if working.exists():
                raise RuntimeError(f'Interrupted partial stage exists: {working}. Keep it for diagnosis; do not overwrite')
            print('TRAINING:',year,'rows',counts[year],flush=True)
            model,tok=load_base(folder,prior,training=True)
            encoded=[encode_example(tok,r) for r in data if r['as_of_year']==year]
            arguments=TrainingArguments(
                output_dir=str(output/f'trainer-{year}'),per_device_train_batch_size=1,
                gradient_accumulation_steps=8,num_train_epochs=2,
                learning_rate=1e-4,logging_steps=10,save_strategy='no',
                report_to='none',remove_unused_columns=False,
                dataloader_num_workers=0,fp16=True,bf16=False,
                optim='paged_adamw_8bit',gradient_checkpointing=True,
                gradient_checkpointing_kwargs={'use_reentrant':False},
                max_grad_norm=0.3,seed=42
            )
            trainer=Trainer(model=model,args=arguments,train_dataset=Dataset(encoded),
                            data_collator=collator(tok.pad_token_id),processing_class=tok)
            result=trainer.train()
            if not result.training_loss or not float('-inf')<float(result.training_loss)<float('inf'):
                raise RuntimeError('TRAINING_BLOCKED: non-finite loss')
            working.mkdir(parents=False,exist_ok=False)
            model.save_pretrained(str(working),safe_serialization=True)
            tok.save_pretrained(str(working))
            write_json(working/'course_stage.json',{
                'year':year,'training_data_sha256':datahash,'model_config_sha256':modelhash,
                'previous_adapter_sha256':last_sha,'rows':counts[year],
                'loss':float(result.training_loss),
                'adapter_sha256':sha(working/'adapter_model.safetensors'),
                'label':'COURSE_EXPERIMENT_NOT_OFFICIAL_RELEASE'
            })
            working.rename(destination)
            del trainer,model,tok
            gc.collect();torch.cuda.empty_cache()
            stage_valid(destination,year,datahash,modelhash,last_sha)
        prior=destination
        last_sha=sha(destination/'adapter_model.safetensors')
    write_json(output/'five_stage_completion.json',{
        'status':'FIVE_COURSE_ADAPTERS_VERIFIED_NOT_OFFICIAL_RELEASE',
        'stages':list(YEARS),'training_data_sha256':datahash,
        'last_adapter_sha256':last_sha})
    print('SUCCESS: 5 course-mode checkpoints verified',flush=True)


def load_benchmark(path:Path):
    if not path.is_file():
        raise RuntimeError('EVAL_BLOCKED: canonical 90-case benchmark file not found. Add benchmark.jsonl as Kaggle Input.')
    rows=[json.loads(x) for x in path.read_text(encoding='utf-8-sig').splitlines() if x.strip()]
    if len(rows)!=90 or len({x['id'] for x in rows})!=90 or any(not x.get('gold_answer') or not x.get('question') for x in rows):
        raise RuntimeError('EVAL_BLOCKED: expected complete canonical 90-case benchmark')
    return rows


def metric_f1(gold: str, pred: str):
    g=re.findall(r'\w+',gold.lower());p=re.findall(r'\w+',pred.lower())
    if not g or not p:return 0.0
    common=sum((collections.Counter(g)&collections.Counter(p)).values())
    return round(2*common/(len(g)+len(p)),4)


def evaluate(data_file:Path,manifest:Path,output:Path,benchmark_path:Path):
    import torch
    dataset_preflight(data_file,manifest)
    runtime_preflight()
    bench=load_benchmark(benchmark_path)
    model_dir=find_local_model()
    for year in YEARS:
        stage_valid(output/'checkpoints'/f'year-{year}',year,sha(data_file),sha(model_dir/'config.json'),
                    sha(output/'checkpoints'/f'year-{year-1}'/'adapter_model.safetensors') if year>2022 else None)
    ev=output/'evaluation'
    ev.mkdir(parents=True,exist_ok=True)
    results=ev/'predictions.jsonl'; done=set()
    if results.exists():
        for line in results.read_text(encoding='utf-8').splitlines():
            if line.strip():
                x=json.loads(line);done.add((x['checkpoint_year'],x['id']))
    for year in YEARS:
        outstanding=[r for r in bench if (year,r['id']) not in done]
        if not outstanding:continue
        model,tok=load_base(model_dir,output/'checkpoints'/f'year-{year}',training=False)
        model.eval()
        for r in outstanding:
            pro=tok.apply_chat_template(user_prompt(r['question'],int(r['as_of_year'])),
                                        tokenize=False,add_generation_prompt=True)
            inputs=tok(pro,return_tensors='pt',add_special_tokens=False)
            inputs={k:v.to('cuda:0') for k,v in inputs.items()}
            with torch.inference_mode():
                output_ids=model.generate(**inputs,do_sample=False,max_new_tokens=128,
                                          pad_token_id=tok.pad_token_id)
            answer=tok.decode(output_ids[0][inputs['input_ids'].shape[1]:],skip_special_tokens=True).strip()
            row={'id':r['id'],'checkpoint_year':year,'as_of_year':int(r['as_of_year']),
                 'question':r['question'],'gold_answer':r['gold_answer'],'prediction':answer,
                 'type':r['type'],'token_f1_proxy':metric_f1(r['gold_answer'],answer)}
            with results.open('a',encoding='utf-8') as f:
                f.write(json.dumps(row,ensure_ascii=False)+'\n')
        del model,tok;gc.collect();torch.cuda.empty_cache()
    predictions=[json.loads(x) for x in results.read_text(encoding='utf-8').splitlines() if x.strip()]
    if len(predictions)!=450 or len({(x['checkpoint_year'],x['id']) for x in predictions})!=450:
        raise RuntimeError('EVAL_PARTIAL: remaining cases must finish before summary')
    stats={}
    for y in YEARS:
        subset=[x for x in predictions if x['checkpoint_year']==y]
        stats[str(y)]={'n':len(subset),'token_f1_mean_proxy':round(sum(x['token_f1_proxy'] for x in subset)/len(subset),4),
                        'past_cases':sum(x['as_of_year']<=y for x in subset)}
    write_json(ev/'forgetting_summary.json',{
        'status':'EXPLORATORY_LEXICAL_PROXY_NOT_SEMANTIC_VERSION_ACCURACY',
        'benchmark_sha256':sha(benchmark_path),'scores_by_checkpoint':stats,
        'n_predictions':len(predictions)})
    write_json(ev/'provenance.json',{'data_sha256':sha(data_file),
        'benchmark_sha256':sha(benchmark_path), 'model_config_sha256':sha(model_dir/'config.json'),
        'stage_sha256':{str(y):sha(output/'checkpoints'/f'year-{y}'/'adapter_model.safetensors') for y in YEARS},
        'evaluation_warning':'Token F1 is not true factual or temporal version accuracy; manual analysis required'})
    print('Evaluation completed: 450 predictions + summaries',flush=True)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('command',choices=['preflight','train','evaluate'])
    p.add_argument('--data',type=Path,required=True)
    p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--output',type=Path,default=Path('/kaggle/working/chronoreg_course_3b'))
    p.add_argument('--benchmark',type=Path)
    a=p.parse_args()
    try:
        dataset,counts=dataset_preflight(a.data,a.manifest)
        print('COURSE INPUT READY:',len(dataset),'per proposed year',counts,flush=True)
        if a.command=='preflight':
            print('WARNING: auto-checked excerpts, not an independent version/effectivity certification')
            # Show model and runtime readiness separately; first cell can run on CPU.
            try: print('Local model:',find_local_model())
            except RuntimeError as e: print(e)
        elif a.command=='train':train(a.data,a.manifest,a.output)
        else:
            if not a.benchmark:raise RuntimeError('EVAL_BLOCKED: --benchmark required')
            evaluate(a.data,a.manifest,a.output,a.benchmark)
    except Exception as e:
        print('STOP:',e,file=sys.stderr)
        raise

if __name__=='__main__':main()
