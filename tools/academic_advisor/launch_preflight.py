"""Shared local-runtime setup. Does not install software, modify host policy or upgrade models."""
import json
import os
import subprocess
import time
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from local_slm import OLLAMA_BASE, find_ollama, ollama_ready, loopback_json
from semantic_planner import MODEL


def ensure_planner(exe, env):
    def names():
        data = loopback_json(OLLAMA_BASE + '/api/tags', timeout=10)
        return {m.get('name') for m in data.get('models', [])}
    if MODEL not in names():
        print('Downloading semantic planner:', MODEL, flush=True)
        subprocess.run([exe, 'pull', MODEL], env=env, check=True)
    if MODEL not in names():
        raise RuntimeError('Required planner tag not present after pull: ' + MODEL)
    # A real small, public synthetic generation verifies the selected runtime and tag.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise RuntimeError('Unexpected redirect from local planner')
    payload = {'model': MODEL, 'messages': [{'role': 'user', 'content': 'Reply with OK.'}],
               'stream': False, 'think': False, 'keep_alive': 0,
               'options': {'num_gpu': 0, 'num_ctx': 4096, 'num_predict': 16, 'temperature': 0}}
    req = urllib.request.Request(OLLAMA_BASE + '/api/chat', data=json.dumps(payload).encode(),
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect()).open(req, timeout=180) as r:
        result = json.load(r)
    if not result.get('message', {}).get('content', '').strip():
        raise RuntimeError('Semantic planner returned no content; check local Ollama and available memory')
    print('SEMANTIC_PLANNER_READY', MODEL, flush=True)


@contextmanager
def planner_runtime(cache):
    exe = find_ollama()
    if not exe:
        raise RuntimeError('Ollama not installed. Use start-advisor.cmd or start-advisor.sh.')
    env = {**os.environ, 'OLLAMA_HOST': '127.0.0.1:11434', 'OLLAMA_NO_CLOUD': '1'}
    proc = None
    log = None
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    try:
        if not ollama_ready():
            log = (cache / 'planner-runtime.log').open('a', encoding='utf-8')
            proc = subprocess.Popen([exe, 'serve'], env=env, stdout=log, stderr=subprocess.STDOUT)
            for _ in range(60):
                if ollama_ready():
                    break
                if proc.poll() is not None:
                    raise RuntimeError('Ollama startup failed; see planner-runtime.log')
                time.sleep(1)
            else:
                raise RuntimeError('Ollama startup timed out; see planner-runtime.log')
        ensure_planner(exe, env)
        yield
    finally:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        if log is not None:
            log.close()
