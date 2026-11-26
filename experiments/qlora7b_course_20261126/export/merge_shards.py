"""Reproduce the successful shardwise LoRA merge; CPU, no Accelerate offload."""
import json, shutil, gc, sys
from pathlib import Path
import torch
from safetensors import safe_open
from safetensors.torch import load_file, save_file

base, adapter, merged = map(Path, sys.argv[1:4])
torch.set_num_threads(2)
cfg = json.loads((adapter / 'adapter_config.json').read_text())
assert cfg['peft_type'] == 'LORA' and cfg['r'] == 8 and cfg['lora_alpha'] == 16 and cfg['bias'] == 'none'
assert not any(cfg.get(k) for k in ('fan_in_fan_out','use_rslora','use_dora','rank_pattern','alpha_pattern','modules_to_save'))
lora = load_file(str(adapter / 'adapter_model.safetensors'), device='cpu')
prefix, suffix = 'base_model.model.', '.lora_A.weight'
targets = {}
for k in lora:
    if k.endswith(suffix):
        assert k.startswith(prefix)
        stem = k[:-len(suffix)]; b = stem + '.lora_B.weight'
        assert b in lora
        targets[stem[len(prefix):] + '.weight'] = (k,b)
assert len(targets) == 112 and len(lora) == 224
assert {k for pair in targets.values() for k in pair} == set(lora)
index = json.loads((base / 'model.safetensors.index.json').read_text()); wm = index['weight_map']
assert set(targets) <= set(wm)
merged.mkdir(parents=True, exist_ok=False)
seen=set(); changed=total=0
for shard in sorted(set(wm.values())):
    tensors={}
    with safe_open(str(base/shard),framework='pt',device='cpu') as f:
        assert set(f.keys()) == {k for k,v in wm.items() if v==shard}
        for k in f.keys():
            w=f.get_tensor(k); out=w.half() if w.is_floating_point() else w.clone()
            if k in targets:
                a,b=(lora[x].float() for x in targets[k])
                assert a.shape==(8,w.shape[1]) and b.shape==(w.shape[0],8)
                out=(w.float()+2.0*(b@a)).half()
                assert torch.isfinite(out).all(),k
                changed+=int(not torch.equal(out,w.half())); seen.add(k)
            tensors[k]=out.contiguous(); total+=out.numel()*out.element_size(); del w,out
        save_file(tensors,str(merged/shard),metadata={'format':'pt'})
    del tensors; gc.collect(); print('Merged:',shard,'| LoRA targets:',len(seen),flush=True)
assert seen==set(targets) and changed==112
for p in base.iterdir():
    if p.is_file() and p.suffix in ('.json','.txt','.jinja','.model') and p.name!='model.safetensors.index.json':
        shutil.copy2(p,merged/p.name)
index.setdefault('metadata',{})['total_size']=total
(merged/'model.safetensors.index.json').write_text(json.dumps(index,indent=2))
print('MERGE_112_WEIGHTS_PASS',flush=True)
