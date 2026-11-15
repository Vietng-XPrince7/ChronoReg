#!/usr/bin/env python3
"""Verify the native Git checkout of the ChronoReg 3B classroom experiment."""
import hashlib, json
from collections import Counter
from pathlib import Path

P = Path(__file__).resolve().parent
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()

def run():
    m = json.loads((P/'COURSE_MANIFEST.json').read_text(encoding='utf-8'))
    for relative, expected in m['files_sha256'].items():
        path = P/relative
        assert path.is_file(), f'Missing: {relative}'
        assert sha(path) == expected, f'SHA256 mismatch: {relative}'
    prev = None
    for year in range(2022, 2027):
        d = P/'checkpoints'/f'year-{year}'
        stage = json.loads((d/'course_stage.json').read_text(encoding='utf-8'))
        assert stage['year'] == year
        assert stage['adapter_sha256'] == sha(d/'adapter_model.safetensors'), f'Adapter mismatch {year}'
        if prev is not None:
            assert stage['previous_adapter_sha256'] == prev, f'Broken adapter chain {year}'
        prev = stage['adapter_sha256']
    completion = json.loads((P/'checkpoints'/'five_stage_completion.json').read_text(encoding='utf-8'))
    assert completion['last_adapter_sha256'] == prev
    rows = [json.loads(x) for x in (P/'training'/'course_train_200.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]
    assert len(rows) == 200, f'Expected 200 train rows, got {len(rows)}'
    predictions = [json.loads(x) for x in (P/'evaluation'/'predictions.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]
    assert len(predictions) == 450, f'Expected 450 predictions, got {len(predictions)}'
    ids = {(p['checkpoint_year'],p['id']) for p in predictions}
    assert len(ids) == 450
    years=Counter(p['checkpoint_year'] for p in predictions)
    assert years == {y:90 for y in range(2022,2027)}
    print('PASS: native Git assets; 5 chained adapters, 200 train QA, 450 unique predictions, all recorded SHA256 hashes')

if __name__=='__main__':run()
