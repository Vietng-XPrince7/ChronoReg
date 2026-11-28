"""Start the accepted advisor profile; no automatic edits to source or research modes."""
import argparse,json,os,subprocess,sys,time,urllib.request,webbrowser,socket
from pathlib import Path
from contextlib import ExitStack
from local_slm import server
from launch_preflight import planner_runtime
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
 subprocess.run([str(py),'-m','pip','--disable-pip-version-check','install','-r',str(HERE/'team_requirements.txt')],check=True)
 subprocess.run([str(py),'-m','pip','check'],check=True)
 with ExitStack() as stack:
  full=not (a.offline or a.gemini)
  url=None
  if full:
   stack.enter_context(planner_runtime(venv/'slm-cache'))
   url=stack.enter_context(server(venv/'slm-cache'))
  env={**os.environ,'PYTHONUTF8':'1','RAG_AUTO_LLM':'0',
       'CHRONOREG_SEMANTIC_PILOT':'1' if full else '0',
       'CHRONOREG_GROUNDED_PILOT':'1' if full else '0'}
  cmd=[str(py),str(HERE/'portable_runtime.py'),'--repo',str(ROOT),'--port',str(a.port)]+(['--gemini'] if a.gemini else ['--slm-url',url] if url else [])
  proc=subprocess.Popen(cmd,cwd=ROOT,env=env)
  try:
   opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
   for _ in range(180):
    if proc.poll() is not None:raise RuntimeError(f'Advisor exited during startup: {proc.returncode}')
    try:
     with opener.open(f'http://127.0.0.1:{a.port}/api/knowledge/status',timeout=2) as r:
      status=json.load(r)
      if status.get('mode')=='portable_advisor':
       if full and not (status.get('grounded_pilot') is True and status.get('semantic_pilot') is True):
        raise RuntimeError('Advisor started without the required orchestration flags')
       break
    except (OSError,ValueError):pass
    time.sleep(1)
   else:raise RuntimeError('Advisor health check timed out')
   print(f'ADVISOR_READY http://127.0.0.1:{a.port}'+(' (full local advisor)' if full else ' (limited profile)'),flush=True)
   if not a.no_browser:
    try:webbrowser.open(f'http://127.0.0.1:{a.port}')
    except webbrowser.Error:pass
   return proc.wait()
  finally:
   if proc.poll() is None:
    proc.terminate()
    try:proc.wait(timeout=10)
    except subprocess.TimeoutExpired:proc.kill();proc.wait()
if __name__=='__main__':
 try:raise SystemExit(main())
 except KeyboardInterrupt:raise SystemExit(130)
