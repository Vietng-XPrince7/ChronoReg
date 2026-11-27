"""Stage one cumulative release in a clean clone, without changing existing files or committing."""
import argparse, hashlib,json, shutil, subprocess,tempfile
from pathlib import Path

def git(repo,*args):return subprocess.check_output(['git','-C',str(repo),*args],text=True,encoding='utf8',errors='replace').strip()

def stage(repo,source):
 repo=Path(repo).resolve();source=Path(source).resolve()
 if Path(git(repo,'rev-parse','--show-toplevel')).resolve()!=repo:raise ValueError('Expected repository root')
 if not (repo/'src/api/studenthub_server.py').is_file():raise ValueError('Wrong repository')
 if git(repo,'status','--porcelain'):raise ValueError('Working tree is not clean; use a clean clone/branch')
 dest=repo/'tools'/'academic_advisor'
 if dest.exists():raise ValueError('Release directory already exists; refusing to overwrite')
 if (repo/'tools').exists() and (repo/'tools').is_symlink():raise ValueError('Unsafe tools path')
 manifest=json.loads((source/'release_manifest.json').read_text(encoding='utf8'))
 paths=manifest['files']
 for name,digest in paths.items():
  if Path(name).name!=name or not name.endswith(('.py','.md')):raise ValueError('Invalid manifest path')
  if hashlib.sha256((source/name).read_bytes()).hexdigest()!=digest:raise ValueError('Changed release file: '+name)
 dest.parent.mkdir(exist_ok=True)
 with tempfile.TemporaryDirectory(prefix='.advisor-stage-',dir=dest.parent) as tmp:
  folder=Path(tmp)/'release';folder.mkdir()
  for name in paths:shutil.copyfile(source/name,folder/name)
  shutil.copyfile(source/'release_manifest.json',folder/'release_manifest.json')
  folder.rename(dest)
 return dest

def main():
 p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);a=p.parse_args()
 print('RELEASE_STAGED',stage(a.repo,Path(__file__).resolve().parent))
 print('Review git status. No commit or push was performed.')
if __name__=='__main__':main()
