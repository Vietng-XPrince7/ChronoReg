import argparse,json
from pathlib import Path
from reference_knowledge import ReferenceLibrary
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();r=ReferenceLibrary(a.repo).report();a.out.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print(json.dumps({k:v for k,v in r.items() if k!='files'},ensure_ascii=False));print('REFERENCE_COVERAGE_COMPLETE',a.out)
