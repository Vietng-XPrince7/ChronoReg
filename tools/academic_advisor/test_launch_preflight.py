import io, json, os, tempfile, unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
import launch_preflight as lp
import team_launch as tl

class LaunchTests(unittest.TestCase):
    def test_existing_model_no_pull(self):
        opener=MagicMock(); opener.open.return_value.__enter__.return_value=io.StringIO('{"message":{"content":"OK"}}')
        with patch.object(lp,'loopback_json',return_value={'models':[{'name':lp.MODEL}]}), patch.object(lp.subprocess,'run') as run, patch.object(lp.urllib.request,'build_opener',return_value=opener):
            lp.ensure_planner('ollama',{})
            run.assert_not_called()
            payload=json.loads(opener.open.call_args.args[0].data)
            self.assertEqual(payload['options']['num_gpu'],0)
            self.assertEqual(payload['model'],lp.MODEL)
    def test_missing_model_pull(self):
        opener=MagicMock();opener.open.return_value.__enter__.return_value=io.StringIO('{"message":{"content":"OK"}}')
        with patch.object(lp,'loopback_json',side_effect=[{'models':[]},{'models':[{'name':lp.MODEL}]}]), patch.object(lp.subprocess,'run') as run, patch.object(lp.urllib.request,'build_opener',return_value=opener):
            lp.ensure_planner('ollama',{'OLLAMA_HOST':'127.0.0.1:11434'})
            self.assertEqual(run.call_args.args[0],['ollama','pull',lp.MODEL])
    def test_missing_after_pull_fails(self):
        with patch.object(lp,'loopback_json',return_value={'models':[]}),patch.object(lp.subprocess,'run'):
            with self.assertRaisesRegex(RuntimeError,'not present'):lp.ensure_planner('ollama',{})
    def test_reuse_existing_service(self):
        with tempfile.TemporaryDirectory() as d,patch.object(lp,'find_ollama',return_value='ollama'),patch.object(lp,'ollama_ready',return_value=True),patch.object(lp,'ensure_planner') as ensure,patch.object(lp.subprocess,'Popen') as popen:
            with lp.planner_runtime(d):pass
            popen.assert_not_called();self.assertEqual(ensure.call_args.args[1]['OLLAMA_HOST'],'127.0.0.1:11434')
    def test_owned_service_cleanup_after_error(self):
        proc=Mock();proc.poll.return_value=None
        with tempfile.TemporaryDirectory() as d,patch.object(lp,'find_ollama',return_value='ollama'),patch.object(lp,'ollama_ready',side_effect=[False,True]),patch.object(lp,'ensure_planner',side_effect=RuntimeError('probe')),patch.object(lp.subprocess,'Popen',return_value=proc):
            with self.assertRaisesRegex(RuntimeError,'probe'):
                with lp.planner_runtime(d):self.fail('must not yield')
            proc.terminate.assert_called_once()
    def test_full_launch_enables_flags_and_checks_health(self):
        self._launch(False)
    def test_limited_launch_skips_models(self):
        self._launch(True)
    def _launch(self,limited):
        @contextmanager
        def runtime(_):yield 'http://127.0.0.1:11434/ollama'
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'src/api').mkdir(parents=True);(root/'src/api/studenthub_server.py').touch()
            opener=MagicMock();opener.open.return_value.__enter__.return_value=io.StringIO(json.dumps({'mode':'portable_advisor','grounded_pilot':not limited,'semantic_pilot':not limited}))
            proc=Mock();proc.poll.return_value=None;proc.wait.return_value=0
            with patch.object(tl,'ROOT',root),patch.object(tl.sys,'argv',['team_launch.py','--no-browser']+(['--offline'] if limited else [])),patch.object(tl.socket,'socket'),patch.object(tl.subprocess,'run'),patch.object(tl.subprocess,'Popen',return_value=proc) as popen,patch.object(tl,'planner_runtime',side_effect=runtime) as planner,patch.object(tl,'server',side_effect=runtime) as server,patch.object(tl.urllib.request,'build_opener',return_value=opener):
                self.assertEqual(tl.main(),0)
                env=popen.call_args.kwargs['env'];self.assertEqual(env['CHRONOREG_GROUNDED_PILOT'],'0' if limited else '1');self.assertEqual(env['CHRONOREG_SEMANTIC_PILOT'],'0' if limited else '1')
                self.assertEqual(planner.call_count,int(not limited));self.assertEqual(server.call_count,int(not limited));opener.open.assert_called_once()
