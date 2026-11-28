"""Read-only live workspace probe; no plan confirmation or student notes printed."""
import argparse,json,re,urllib.request,urllib.error

def main():
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8765);a=p.parse_args();base=f'http://127.0.0.1:{a.port}';op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def call(path,body=None,token=None,extra=None):
        headers={'Content-Type':'application/json'}
        if token:headers['X-Advisor-Workspace']=token
        headers.update(extra or {})
        req=urllib.request.Request(base+path,data=None if body is None else json.dumps(body).encode(),headers=headers)
        with op.open(req,timeout=30) as response:return response.read().decode('utf-8')
    checks=[]
    def check(name,ok):checks.append(bool(ok));print('PASS' if ok else 'FAIL',name,flush=True)
    status=json.loads(call('/api/knowledge/status'));check('revision',status.get('intelligence_revision')=='2.0.0-pilot')
    check('home_link','/advisor/workspace' in call('/'))
    page=call('/advisor/workspace');match=re.search(r"const token='([^']+)'",page);check('workspace_page',bool(match));token=match[1]
    nav={'Sec-Fetch-Site':'cross-site','Sec-Fetch-Mode':'navigate','Sec-Fetch-Dest':'document','Sec-Fetch-User':'?1'}
    check('external_navigation',bool(re.search(r"const token='([^']+)'",call('/advisor/workspace',extra=nav))))
    def denied(path,headers,token=None):
        try:call(path,token=token,extra=headers)
        except urllib.error.HTTPError as e:return e.code==403
        return False
    check('external_iframe_blocked',denied('/advisor/workspace',{**nav,'Sec-Fetch-Dest':'iframe'}))
    check('external_api_blocked',denied('/api/advisor/workspace',nav,token))
    route='/api/advisor/workspace';state=json.loads(call(route,token=token));scope=state['scope'];check('workspace_state',bool(scope) and isinstance(state['plans'],list))
    for goal in ('graduation','improvement','daily'):
        result=json.loads(call(route+'/preview',{'scope':scope,'goal':goal,'days':14},token));check('preview_'+goal,result['draft'] and result['scope']==scope and bool(result['tasks']) and bool(result['preview_hash']))
    after=json.loads(call(route,token=token));check('preview_no_plan_write',after==state)
    print(f'WORKSPACE_PROBE: {sum(checks)}/{len(checks)}; no plans created; manual browser review required')
    return int(not all(checks))
if __name__=='__main__':raise SystemExit(main())
