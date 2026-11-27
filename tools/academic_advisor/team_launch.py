import argparse,json,os,subprocess,sys,time,urllib.request,webbrowser,socket
from pathlib import Path
from contextlib import nullcontext
from local_slm import server
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
def main():
 p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8765);g=p.add_mutually_exclusive_group();g.add_argument('--gemini',action='store_true');g.add_argument('--offline',action='store_true');p.add_argument('--no-browser',action='store_true');a=p.parse_args()
 if sys.version_info<(3,11):raise SystemExit('Python 3.11+ required')
 if not (ROOT/'src/api/studenthub_server.py').is_file():raise SystemExit('Wrong repository layout')
 with socket.socket() as s:
  try:s.bind(('127.0.0.1',a.port))
  except OSError:raise SystemExit('Port is in use. Stop the old server or choose another port.')
 venv=ROOT/'.venv-chronoreg-advisor';py=venv/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
 if not py.is_file():subprocess.run([sys.executable,'-m','venv',str(venv)],check=True)
 subprocess.run([str(py),'-m','pip','install','-r',str(HERE/'team_requirements.txt')],check=True)
 subprocess.run([str(py),'-m','pip','check'],check=True)
 with (nullcontext(None) if a.offline or a.gemini else server(venv/'slm-cache')) as url:
  cmd=[str(py),str(HERE/'portable_runtime.py'),'--repo',str(ROOT),'--port',str(a.port)]+(['--gemini'] if a.gemini else ['--slm-url',url] if url else [])
  proc=subprocess.Popen(cmd,cwd=ROOT,env={**os.environ,'PYTHONUTF8':'1','RAG_AUTO_LLM':'0'})
  try:
   if not a.no_browser:
    for _ in range(90):
     if proc.poll() is not None:break
     try:
      with urllib.request.urlopen(f'http://127.0.0.1:{a.port}/api/knowledge/status',timeout=2) as r:
       if json.load(r).get('mode')=='portable_advisor':webbrowser.open(f'http://127.0.0.1:{a.port}');break
     except (OSError,ValueError):time.sleep(1)
   return proc.wait()
  finally:
   if proc.poll() is None:
    proc.terminate()
    try:proc.wait(timeout=10)
    except subprocess.TimeoutExpired:proc.kill();proc.wait()
if __name__=='__main__':raise SystemExit(main())
