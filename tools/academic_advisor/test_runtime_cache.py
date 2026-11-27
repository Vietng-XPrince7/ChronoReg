import tempfile, unittest, zipfile
from pathlib import Path
from contextlib import contextmanager
from unittest.mock import patch
import local_slm as m

class RuntimeCacheTests(unittest.TestCase):
 def test_reuse_verified_cache_no_move_or_delete(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);archive=root/'runtime.zip';target=root/'runtime'
   with zipfile.ZipFile(archive,'w') as z:
    z.writestr('llama-server.exe',b'exe');z.writestr('ggml-cpu.dll',b'dll')
   with patch.object(m.shutil,'move',side_effect=AssertionError('must not move')),patch.object(m.shutil,'rmtree',side_effect=AssertionError('must not delete')):
    first=m.extract_runtime(archive,target)
    with patch.object(zipfile.ZipFile,'extractall',side_effect=AssertionError('must reuse')):
     self.assertEqual(first,m.extract_runtime(archive,target))
    first.with_name('ggml-cpu.dll').write_bytes(b'bad')
    second=m.extract_runtime(archive,target)
    self.assertNotEqual(first,second);self.assertTrue(first.exists());self.assertEqual(second.with_name('ggml-cpu.dll').read_bytes(),b'dll')
 def test_prefer_existing_ollama(self):
  @contextmanager
  def available(cache,model):yield 'http://127.0.0.1:11434/ollama'
  with tempfile.TemporaryDirectory() as d,patch.object(m,'find_ollama',return_value='ollama'),patch.object(m,'download',return_value=Path(d)/m.MODEL_FILE),patch.object(m,'ollama_server',available),patch.object(m,'llama_server') as llama:
   with m.server(Path(d)) as url:self.assertTrue(url.endswith('/ollama'))
   llama.assert_not_called()
 def test_permission_error_falls_back(self):
  @contextmanager
  def locked(cache):raise PermissionError('DLL locked');yield
  @contextmanager
  def available(cache,model):yield 'http://127.0.0.1:11434/ollama'
  with tempfile.TemporaryDirectory() as d,patch.object(m,'find_ollama',return_value=None),patch.object(m,'llama_server',locked),patch.object(m,'ollama_server',available),patch.object(m,'download',return_value=Path(d)/m.MODEL_FILE):
   with m.server(Path(d)) as url:self.assertTrue(url.endswith('/ollama'))
 def test_ollama_failure_uses_llama(self):
  @contextmanager
  def bad(cache,model):raise RuntimeError('startup failed');yield
  @contextmanager
  def good(cache):yield 'http://127.0.0.1:12345'
  with tempfile.TemporaryDirectory() as d,patch.object(m,'find_ollama',return_value='ollama'),patch.object(m,'download',return_value=Path(d)/m.MODEL_FILE),patch.object(m,'ollama_server',bad),patch.object(m,'llama_server',good):
   with m.server(Path(d)) as url:self.assertEqual(url,'http://127.0.0.1:12345')
 def test_integrity_error_not_hidden(self):
  with tempfile.TemporaryDirectory() as d,patch.object(m,'find_ollama',return_value='ollama'),patch.object(m,'download',side_effect=ValueError('SHA mismatch')),patch.object(m,'llama_server') as llama:
   with self.assertRaisesRegex(ValueError,'SHA mismatch'):
    with m.server(Path(d)):pass
   llama.assert_not_called()
