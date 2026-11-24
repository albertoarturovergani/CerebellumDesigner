"""Start the real source or frozen app, exercise its API, and shut it down cleanly."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser();p.add_argument('--exe');args=p.parse_args()
    data=ROOT/'test-output'/('frozen space é' if args.exe else 'source space é');data.mkdir(parents=True,exist_ok=True)
    command=[str(Path(args.exe).resolve())] if args.exe else [sys.executable,str(ROOT/'desktop.py')]
    subprocess.run(command+['--self-test','--data-dir',str(data)],check=True,timeout=150)
    result=json.loads((data/'self-test.json').read_text(encoding='utf-8'))
    assert result['passed'] and (not args.exe or result['frozen'])
    process=subprocess.Popen(command+['--no-browser','--port','0','--data-dir',str(data)])
    try:
        state=data/f'server-{process.pid}.json'
        deadline=time.monotonic()+40
        while not state.exists():
            assert process.poll() is None, 'Server exited before startup'
            if time.monotonic()>deadline:raise TimeoutError('Server did not start')
            time.sleep(.2)
        url=json.loads(state.read_text(encoding='utf-8'))['url'].rstrip('/')
        def request(path,body=None,origin=None):
            headers={} if body is None else {'Content-Type':'application/json'}
            if origin:headers['Origin']=origin
            req=urllib.request.Request(url+path,data=None if body is None else json.dumps(body).encode(),headers=headers)
            with urllib.request.urlopen(req,timeout=60) as response:
                raw=response.read()
                return json.loads(raw) if response.headers.get_content_type()=='application/json' else raw
        catalog=request('/api/catalog');assert catalog['native_editor']
        assert b'Windows' in request('/') and b'Close app' in request('/')
        assert len(request('/api/network-reference')['populations'])==7
        sz=next(x['recipe'] for x in catalog['presets'] if x['id']=='sz')
        assert request('/api/preview',{'recipe':sz,'population':'purkinje_cell'})['valid']
        saved=request('/api/save-profile',{'recipe':sz})
        assert request('/api/profile?id='+saved['id'])['recipe']['name']==sz['name']
        assert request('/api/profiles')['profiles']
        for path,body in [('/api/catalog',None),('/api/quit',{})]:
            try:request(path,body,origin='https://example.org')
            except urllib.error.HTTPError as e:assert e.code==403
            else:raise AssertionError('Cross-origin request accepted')
        try:request('/api/network',{'recipe':sz})
        except urllib.error.HTTPError as e:assert e.code==400
        else:raise AssertionError('Unexpected BSB placement available')
        # Export through the actual frozen HTTP endpoint and download its PDF.
        package=request('/api/export',{'recipe':sz})
        assert request(package['pdf']).startswith(b'%PDF')
        assert request('/api/quit',{})['closed']
        assert process.wait(timeout=15)==0
        result['http_checks']=['catalog','static assets','reference','SZ preview','save/load profile','foreign-origin rejection','placement unavailable','export PDF','graceful quit']
        (data/'validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(f"PASS {result['count']} core/export checks + {len(result['http_checks'])} HTTP checks; frozen={result['frozen']}")
    finally:
        if process.poll() is None:
            process.terminate();process.wait(timeout=15)

if __name__=='__main__':main()
