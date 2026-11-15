#!/usr/bin/env python3
"""Minimal 4-bit Qwen2.5-3B-Instruct + ChronoReg LoRA inference. Needs CUDA GPU."""
import argparse
from pathlib import Path

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--base-model',required=True,help='HF Transformers model folder (not GGUF)')
    p.add_argument('--adapter',required=True,help='unpacked year-2026 adapter directory')
    p.add_argument('--question',required=True)
    p.add_argument('--year',type=int,default=2026)
    args=p.parse_args()
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from peft import PeftModel
    model_dir=Path(args.base_model)
    adapter=Path(args.adapter)
    assert (model_dir/'config.json').is_file(), 'Missing base model config.json'
    assert (adapter/'adapter_model.safetensors').is_file(), 'Missing adapter weights'
    if not torch.cuda.is_available():
        raise RuntimeError('Needs CUDA GPU for same NF4 load as training')
    tok=AutoTokenizer.from_pretrained(str(model_dir),local_files_only=True,trust_remote_code=False)
    if tok.pad_token_id is None:
        tok.pad_token=tok.eos_token
    q=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',bnb_4bit_use_double_quant=True,bnb_4bit_compute_dtype=torch.float16)
    base=AutoModelForCausalLM.from_pretrained(str(model_dir),local_files_only=True,trust_remote_code=False,quantization_config=q,device_map={'':0},dtype=torch.float16)
    model=PeftModel.from_pretrained(base,str(adapter),is_trainable=False,local_files_only=True)
    model.eval()
    messages=[
        {'role':'system','content':'Bạn là trợ lý học vụ UET. Trả lời ngắn, đúng phạm vi câu hỏi; không bịa quy định hay năm hiệu lực.'},
        {'role':'user','content':f'Năm học được hỏi: {args.year}-{args.year+1}.\n{args.question}'},
    ]
    prompt=tok.apply_chat_template(messages,tokenize=False,add_generation_prompt=True)
    inputs=tok(prompt,return_tensors='pt',add_special_tokens=False)
    inputs={k:v.to('cuda:0') for k,v in inputs.items()}
    with torch.inference_mode():
        gen=model.generate(**inputs,do_sample=False,max_new_tokens=128,pad_token_id=tok.pad_token_id)
    print(tok.decode(gen[0][inputs['input_ids'].shape[1]:],skip_special_tokens=True).strip())

if __name__=='__main__':main()
