import unittest,tempfile,json,hashlib,subprocess
from pathlib import Path
from stage_release import stage
class StageTests(unittest.TestCase):
 def test_copy_no_overwrite(self):
  with tempfile.TemporaryDirectory() as t:
   base=Path(t);repo=base/'repo';repo.mkdir();src=base/'release';src.mkdir()
   subprocess.run(['git','init','-q',str(repo)],check=True)
   p=repo/'src/api/studenthub_server.py';p.parent.mkdir(parents=True);p.write_text('# original')
   def git(*args):subprocess.run(['git','-C',str(repo),*args],check=True,stdout=subprocess.DEVNULL)
   git('add','.');git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','initial')
   f=src/'run_live.py';f.write_text('# release');(src/'release_manifest.json').write_text(json.dumps({'files':{f.name:hashlib.sha256(f.read_bytes()).hexdigest()}}))
   p.write_text('# dirty');
   with self.assertRaisesRegex(ValueError,'not clean'):stage(repo,src)
   p.write_text('# original');dest=stage(repo,src);self.assertEqual((dest/f.name).read_text(),'# release');self.assertEqual(p.read_text(),'# original')
   with self.assertRaises(ValueError):stage(repo,src)
if __name__=='__main__':unittest.main()
