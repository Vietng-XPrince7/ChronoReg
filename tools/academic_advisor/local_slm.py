"""Pinned CPU model, with optional existing trusted local Ollama runtime. No security-policy changes."""
import hashlib,json,os,platform,shutil,socket,stat,subprocess,tempfile,time,urllib.request,zipfile
from pathlib import Path
from types import SimpleNamespace
from contextlib import contextmanager
MODEL='Qwen2.5-1.5B-Instruct-Q4_K_M'
MODEL_FILE='qwen2.5-1.5b-instruct-q4_k_m.gguf'
MODEL_URL='https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/dd26da4/'+MODEL_FILE
MODEL_SHA='6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e'
BUILD='b12644'
RUNTIME_FILE=f'llama-{BUILD}-bin-win-cpu-x64.zip'
RUNTIME_URL=f'https://github.com/ggml-org/llama.cpp/releases/download/{BUILD}/{RUNTIME_FILE}'
OLLAMA_TAG="chronoreg-advisor:1.5b-q4km-6a1a2eb6"
OLLAMA_BASE="http://127.0.0.1:11434"
RUNTIME_SHA='245c62729788171ee29259cc7c6a69ed2af79701dc537983d677c841d9076029'

def digest(p):
 with open(p,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def download(url,path,sha,limit):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 if path.is_file() and digest(path)==sha:return path
 tmp=path.with_suffix(path.suffix+'.part')
 print('Downloading',path.name,flush=True)
 try:
  req=urllib.request.Request(url,headers={'User-Agent':'ChronoReg-Advisor/13'})
  with urllib.request.urlopen(req,timeout=90) as r,tmp.open('wb') as f:
   h=hashlib.sha256();n=0;last=0
   while b:=r.read(1024*1024):
    n+=len(b)
    if n>limit:raise ValueError('Download exceeds expected limit')
    h.update(b);f.write(b)
    if n-last>=100*1024*1024:print('Downloaded',n//(1024*1024),'MiB',flush=True);last=n
  if h.hexdigest()!=sha:raise ValueError('SHA-256 mismatch: '+path.name)
  os.replace(tmp,path);return path
 finally:tmp.unlink(missing_ok=True)

def extract_runtime(archive,target):
 # The caller has verified the archive SHA-256. Reuse only byte-identical trees.
 # Never delete/rename a runtime: Windows may still have a DLL mapped.
 target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
 with zipfile.ZipFile(archive) as z:
  if sum(i.file_size for i in z.infolist())>800*1024*1024:raise ValueError('Oversized runtime')
  members={};seen=set()
  for i in z.infolist():
   p=Path(i.filename.replace('\\','/'))
   if p.is_absolute() or '..' in p.parts or ':' in str(p) or stat.S_ISLNK(i.external_attr>>16):raise ValueError('Unsafe ZIP entry')
   key=str(p).casefold()
   if key in seen:raise ValueError('Duplicate ZIP entry')
   seen.add(key)
   if not i.is_dir():members[p]=i
  exes=[p for p in members if p.name.lower()=='llama-server.exe']
  if len(exes)!=1:raise ValueError('Missing or ambiguous llama-server.exe')
  rel=exes[0]
  def verified(tree):
   try:
    if not tree.is_dir() or tree.is_symlink():return False
    items=list(tree.rglob('*'))
    if any(p.is_symlink() or (hasattr(p,'is_junction') and p.is_junction()) for p in items):return False
    if {p.relative_to(tree) for p in items if p.is_file()}!=set(members):return False
    for path,info in members.items():
     f=tree/path
     if f.stat().st_size!=info.file_size:return False
     with z.open(info) as expected:
      if digest(f)!=hashlib.file_digest(expected,'sha256').hexdigest():return False
    return True
   except OSError:return False
  candidates=[target,*sorted(target.parent.glob(target.name+'-verified-*'))]
  for tree in candidates:
   if verified(tree):return tree/rel
  # Extract directly into a unique directory; leave old or interrupted trees alone.
  dest=Path(tempfile.mkdtemp(prefix=target.name+'-verified-',dir=target.parent))
  z.extractall(dest)
  if not verified(dest):raise RuntimeError('Extracted runtime verification failed: '+str(dest))
  return dest/rel

def loopback_port():
 with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]

class RuntimeBlocked(RuntimeError):pass

def check_exit(code,log):
 if code & 0xffffffff == 0xc0e90002:
  raise RuntimeBlocked('Windows Code Integrity blocked llama-server (0xC0E90002). No security settings changed.')
 raise RuntimeError(f'llama-server exited ({code}, 0x{code & 0xffffffff:08X}). See {log}')

def loopback_json(url,timeout=2):
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 with opener.open(url,timeout=timeout) as r:return json.load(r)

def ollama_ready():
 try:return bool(loopback_json(OLLAMA_BASE+'/api/version').get('version'))
 except (OSError,ValueError,AttributeError):return False

def find_ollama():
 path=shutil.which('ollama')
 if path:return path
 base=os.environ.get('LOCALAPPDATA')
 if base:
  p=Path(base)/'Programs/Ollama/ollama.exe'
  if p.is_file():return str(p)
 return None

@contextmanager
def ollama_server(cache,model):
 # Only use an existing independently installed runtime. Never alter Windows policy,
 # unblock binaries, install unsigned components, or send prompts to the cloud.
 exe=find_ollama();proc=None;log=None
 env={**os.environ,'OLLAMA_HOST':'127.0.0.1:11434','OLLAMA_NO_CLOUD':'1'}
 try:
  if not exe:raise RuntimeError('Ollama is not installed. Use an approved local runtime, -Gemini (opt-in), or -Offline (limited).')
  if not ollama_ready():
   log=(cache/'ollama-runtime.log').open('w',encoding='utf8')
   proc=subprocess.Popen([exe,'serve'],env=env,stdout=log,stderr=subprocess.STDOUT)
   for _ in range(45):
    if proc.poll() is not None:raise RuntimeError('Ollama startup failed; see ollama-runtime.log')
    if ollama_ready():break
    time.sleep(1)
   else:raise RuntimeError('Ollama health check timed out')
  # Import exactly the previously verified GGUF, no model pulled from a registry.
  # The distinct tag is not the trained 7B experiment. Ollama reuses its content blobs.
  with tempfile.NamedTemporaryFile(mode='w',encoding='utf8',prefix='Modelfile-',dir=cache,delete=False) as f:
   mf=Path(f.name);f.write('FROM ./'+model.name+'\nPARAMETER num_ctx 8192\nPARAMETER temperature 0\n')
  try:
   print('Importing verified 1.5B GGUF into existing Ollama (cached blobs reused)',flush=True)
   subprocess.run([exe,'create',OLLAMA_TAG,'-f',str(mf)],cwd=cache,env=env,check=True,timeout=600)
  finally:mf.unlink(missing_ok=True)
  url=OLLAMA_BASE+'/ollama'
  # Confirm generation, not just a reachable service or an imported tag.
  req=urllib.request.Request(OLLAMA_BASE+'/api/chat',data=json.dumps({'model':OLLAMA_TAG,'messages':[{'role':'user','content':'Respond with OK.'}],'stream':False,'options':{'num_gpu':0,'num_predict':16}}).encode(),headers={'Content-Type':'application/json'})
  with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=180) as response:probe=json.load(response)
  if not probe.get('message',{}).get('content','').strip():raise RuntimeError('Ollama model inference probe returned no text')
  print('SLM_RUNTIME_READY ollama-local '+OLLAMA_TAG,flush=True)
  yield url
 finally:
  if proc is not None and proc.poll() is None:
   proc.terminate()
   try:proc.wait(timeout=10)
   except subprocess.TimeoutExpired:proc.kill();proc.wait()
  if log is not None:log.close()

@contextmanager
def server(cache):
 from contextlib import ExitStack
 cache=Path(cache).resolve();cache.mkdir(parents=True,exist_ok=True)
 # Prefer an existing approved local runtime; avoid touching the DLL cache at all.
 # Model hash failures are not recoverable by switching runtimes.
 with ExitStack() as stack:
  prior_error=None
  if find_ollama():
   model=download(MODEL_URL,cache/MODEL_FILE,MODEL_SHA,2*1024**3)
   try:url=stack.enter_context(ollama_server(cache,model))
   except (OSError,RuntimeError,subprocess.SubprocessError) as exc:
    prior_error=exc
    print('Existing Ollama startup failed; trying verified llama.cpp: '+str(exc),flush=True)
   else:
    yield url
    return
  try:url=stack.enter_context(llama_server(cache))
  except (RuntimeBlocked,PermissionError) as exc:
   print('Local runtime unavailable: '+str(exc),flush=True)
   if prior_error is not None:
    raise RuntimeError(f'Both local runtimes failed. Ollama: {prior_error}; llama.cpp: {exc}') from exc
   print('Trying existing approved Ollama runtime instead (same verified model).',flush=True)
   model=download(MODEL_URL,cache/MODEL_FILE,MODEL_SHA,2*1024**3)
   url=stack.enter_context(ollama_server(cache,model))
  yield url

@contextmanager
def llama_server(cache):
 if platform.system()!='Windows' or platform.machine().lower() not in ('amd64','x86_64'):
  raise RuntimeError('Automatic local SLM currently supports Windows x64. Use --offline or --gemini on other platforms.')
 cache=Path(cache);cache.mkdir(parents=True,exist_ok=True)
 model=download(MODEL_URL,cache/MODEL_FILE,MODEL_SHA,2*1024**3)
 archive=download(RUNTIME_URL,cache/RUNTIME_FILE,RUNTIME_SHA,200*1024**2)
 exe=extract_runtime(archive,cache/'runtime');port=loopback_port();url=f'http://127.0.0.1:{port}'
 cmd=[str(exe),'-m',str(model),'--host','127.0.0.1','--port',str(port),'-c','8192','-ngl','0','-np','1','-t',str(max(1,min(6,(os.cpu_count() or 2)-1)))]
 print('Starting CPU language model:',MODEL,flush=True)
 with (cache/'runtime.log').open('w',encoding='utf8') as log:
  try:proc=subprocess.Popen(cmd,cwd=exe.parent,stdout=log,stderr=subprocess.STDOUT)
  except OSError as exc:
   if getattr(exc,'winerror',None) in (4551,1260):raise RuntimeBlocked('Windows application control refused to launch llama-server. No security settings changed.') from exc
   raise
  try:
   for _ in range(180):
    if proc.poll() is not None:check_exit(proc.returncode,cache/'runtime.log')
    try:
     with urllib.request.urlopen(url+'/health',timeout=2) as r:
      if r.status==200:break
    except OSError:pass
    time.sleep(1)
   else:raise RuntimeError('SLM startup timed out. See runtime.log')
   yield url
  finally:
   if proc.poll() is None:
    proc.terminate()
    try:proc.wait(timeout=10)
    except subprocess.TimeoutExpired:proc.kill();proc.wait()

class LocalClient:
 def __init__(self,url,transport=None):
  if not __import__('re').fullmatch(r'http://127\.0\.0\.1:\d+(?:/ollama)?',url):raise ValueError('Local loopback only')
  self.ollama=url.endswith('/ollama');self.url=url.removesuffix('/ollama');self.transport=transport
 def post(self,url,json,timeout):
  import httpx
  messages=[dict(m) for m in json['messages']]
  if messages and messages[0]['role']=='system':
   messages[0]['content']+=(' Giữ đúng định dạng JSON được yêu cầu, không thêm lời ngoài JSON. Trong lời tư vấn, gọi người hỏi là cô, xưng em.' if json.get('format') else ' Luôn gọi người hỏi là cô, xưng em. Cô là giảng viên/cố vấn học tập. Nêu kết luận trước, tiếp theo giải thích và việc cô nên làm. Không chỉ chép lại văn bản.')
  body={'messages':messages,'temperature':0,'max_tokens':min(768,json.get('options',{}).get('num_predict',512)),'stream':False}
  fmt=json.get('format')
  if isinstance(fmt,dict):body['response_format']={'type':'json_schema','json_schema':{'name':'advisor_response','schema':fmt,'strict':True}}
  elif fmt=='json':body['response_format']={'type':'json_object'}
  with httpx.Client(timeout=timeout,trust_env=False,transport=self.transport) as c:
   if self.ollama:
    payload={'model':OLLAMA_TAG,'messages':messages,'stream':False,'options':{'temperature':0,'num_ctx':8192,'num_gpu':0,'num_predict':body['max_tokens']}}
    if fmt is not None:payload['format']=fmt
    r=c.post(self.url+'/api/chat',json=payload);r.raise_for_status();data=r.json()
    if not data.get('done'):raise RuntimeError('Incomplete local Ollama response')
    return SimpleNamespace(raise_for_status=lambda:None,json=lambda:data)
   r=c.post(self.url+'/v1/chat/completions',json=body);r.raise_for_status();choice=r.json()['choices'][0]
  return SimpleNamespace(raise_for_status=lambda:None,json=lambda:{'message':{'content':choice['message']['content']},'done_reason':choice['finish_reason']})

def shim(url):
 client=LocalClient(url)
 return SimpleNamespace(lora_model=MODEL,ollama_url=url,ollama_timeout=180,structured_knowledge=True,_make_client=lambda *a,**k:(client,False))
