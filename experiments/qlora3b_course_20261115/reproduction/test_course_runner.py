import json,hashlib,tempfile,unittest,sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent))
from course_train_runner import dataset_preflight, norm_question, metric_f1, load_benchmark, stage_valid,find_local_model

ROOT=Path(__file__).resolve().parent

class TestCourseRunner(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)
        self.data=json.loads('['+','.join(ROOT.joinpath('course_train_200.jsonl').read_text(encoding='utf-8').splitlines())+']')
        self.datafile=self.path/'dataset.jsonl'
        self.manifest=self.path/'manifest.json'
        self.write_input(self.data)
    def write_input(self, rows):
        self.datafile.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
        self.manifest.write_text(json.dumps({'training_rows':len(rows),
            'train_sha256':hashlib.sha256(self.datafile.read_bytes()).hexdigest()}),encoding='utf-8')
    def test_200_valid(self):
        data,counts=dataset_preflight(ROOT/'course_train_200.jsonl',ROOT/'manifest.json')
        self.assertEqual(len(data),200)
        self.assertEqual(counts,{2022:40,2023:37,2024:36,2025:49,2026:38})
    def test_tamper_digest_rejected(self):
        self.datafile.write_text(self.datafile.read_text(encoding='utf-8')+'\n',encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError,'does not match'):
            dataset_preflight(self.datafile,self.manifest)
    def test_reject_duplicates(self):
        self.data[1]['question']=self.data[0]['question']
        self.write_input(self.data)
        with self.assertRaisesRegex(RuntimeError,'duplicate'):
            dataset_preflight(self.datafile,self.manifest)
    def test_reject_fake_independent_review(self):
        self.data[0]['independent_review_verified']=True
        self.write_input(self.data)
        with self.assertRaisesRegex(RuntimeError,'duplicate/ambiguous'):
            dataset_preflight(self.datafile,self.manifest)
    def test_bad_year(self):
        self.data[0]['as_of_year']=2021
        self.write_input(self.data)
        with self.assertRaisesRegex(RuntimeError,'invalid year'):
            dataset_preflight(self.datafile,self.manifest)
    def test_2022_underfilled(self):
        rows=self.data[:]
        for x in rows:
            if x['as_of_year']==2022: x['as_of_year']=2023
        self.write_input(rows)
        with self.assertRaisesRegex(RuntimeError,'fewer than 30'):
            dataset_preflight(self.datafile,self.manifest)
    def test_normalization(self):
        self.assertEqual(norm_question(' Câu    hỏi ? '),norm_question('câu hỏi'))
    def test_token_f1(self):
        self.assertEqual(metric_f1('3 tín chỉ','3 tín chỉ'),1.0)
        self.assertEqual(metric_f1('abc','xyz'),0.0)
    def test_benchmark_exact_90_required(self):
        f=self.path/'benchmark.jsonl'
        f.write_text(json.dumps({'id':'x','question':'q','gold_answer':'a'})+'\n')
        with self.assertRaisesRegex(RuntimeError,'90-case'):
            load_benchmark(f)
    def test_checkpoint_integrity(self):
        cp=self.path/'year-2022';cp.mkdir()
        (cp/'adapter_model.safetensors').write_bytes(b'not-real-test-weights')
        (cp/'adapter_config.json').write_text('{}')
        m={'year':2022,'training_data_sha256':'x','model_config_sha256':'y',
           'previous_adapter_sha256':None,
           'adapter_sha256':hashlib.sha256(b'not-real-test-weights').hexdigest()}
        (cp/'course_stage.json').write_text(json.dumps(m))
        self.assertEqual(stage_valid(cp,2022,'x','y',None)['year'],2022)
        (cp/'adapter_model.safetensors').write_bytes(b'tampered')
        with self.assertRaisesRegex(RuntimeError,'invalid saved stage'):
            stage_valid(cp,2022,'x','y',None)
    def test_no_fake_benchmark_when_missing(self):
        with self.assertRaisesRegex(RuntimeError,'not found'):
            load_benchmark(self.path/'nope.jsonl')

if __name__=='__main__':unittest.main(verbosity=2)
