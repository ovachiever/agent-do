"""Persistent loopback-only review host. Serves public ballots, never round files."""
import fcntl
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
import webbrowser

from design_browser import DesignError, TOOL
from design_contract import digest
from design_state import Round, now, write_new


def atomic_json(path,value):
    temp=path.with_name('.'+path.name+'.'+uuid.uuid4().hex)
    write_new(temp,value);os.replace(temp,path)


def launch(round_path,kind,open_browser=True):
    root=Path(round_path).resolve();state=root/('.preview-'+kind+'.json')
    def existing():
        try:
            info=json.loads(state.read_text())
            url=info['url']
            if not re.fullmatch(r'http://127\.0\.0\.1:\d+/[a-f0-9]{32}/',url):return None
            with urllib.request.urlopen(url+'health',timeout=1) as reply:
                live=json.load(reply)
                if (live.get('instance')==info['instance'] and live.get('round')==str(root)
                        and live.get('kind')==kind):return info
        except (OSError,ValueError,KeyError):pass
    info=existing()
    if info is None:
        with (root/('.preview-'+kind+'.log')).open('ab') as log:
            child=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),str(root),kind],
                                   stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            info=existing()
            if info:break
            if child.poll() is not None:raise DesignError('local preview failed to start; see '+str(log.name))
            time.sleep(.05)
        if info is None:raise DesignError('local preview did not become ready; see '+str(log.name))
    if open_browser and not webbrowser.open(info['url']):
        raise DesignError('preview is running at '+info['url']+' but the default browser could not be opened')
    return {'status':'local review ready','url':info['url'],'browser_open_requested':open_browser,
            'stop_url':info['url'],'state':str(state)}


def make_server(root,kind):
    root=Path(root).resolve()
    with Round(root) as record:
        ballot=record.state['ballots'][kind]
        folder=record.resolve(ballot['path'])
        parts=ballot.get('parts',[ballot])
    token=uuid.uuid4().hex
    def original(index):
        source=(folder/parts[index]['file']).read_text()
        if digest(source)!=parts[index]['sha256']:raise DesignError('prepared ballot changed')
        return source
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def send(self,value,status=200,mime='application/json'):
            body=(json.dumps(value) if mime=='application/json' else value).encode()
            self.send_response(status);self.send_header('Content-Type',mime+'; charset=utf-8')
            self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store')
            self.send_header('Referrer-Policy','no-referrer');self.send_header('X-Content-Type-Options','nosniff')
            self.end_headers();self.wfile.write(body)
        def route(self):
            if self.headers.get('Host')!=self.server.address or not self.path.startswith('/'+token+'/'):return None
            return self.path[len(token)+2:]
        def do_GET(self):
            route=self.route()
            try:
                if route=='health':return self.send(self.server.info)
                if route=='':
                    links=' '.join(f'<a href="part/{i}" target="review">Part {i+1}</a>' for i in range(len(parts)))
                    return self.send('<!doctype html><title>Design review</title><style>body{margin:0;background:#171717;color:#eee;font:16px system-ui}nav{padding:16px}a{color:#9cf;margin-right:20px}iframe{width:100%;height:calc(100vh - 95px);border:0}</style><nav>Design review: '+links+'<button onclick="fetch(\'stop\',{method:\'POST\'}).then(()=>document.body.textContent=\'Preview stopped. Your saved reviews remain on disk.\')">Stop preview</button><p>Choose candidates explicitly, or save notes without approving. Review every part.</p></nav><iframe name="review" src="part/0"></iframe>',mime='text/html')
                match=re.fullmatch(r'part/(\d+)',route or '')
                if match and int(match[1])<len(parts):
                    i=int(match[1]);source=original(i)
                    latest=folder/'local-reviews'/str(i)/'latest.json'
                    config={'endpoint':'../review/'+str(i),'labels':parts[i].get('labels',[]),
                            'saved':json.loads(latest.read_text()) if latest.exists() else None}
                    script='window.designLocal='+json.dumps(config).replace('<','\\u003c')+';\n'+(TOOL/'preview-runtime.js').read_text()
                    # Local hosting supplies its own runtime. Canonical ballot bytes
                    # stay immutable; saved submissions are derived from those bytes.
                    source,count=re.subn(r'<script>([\s\S]*)</script></body>',lambda _: '<script>'+script+'</script></body>',source,count=1)
                    if count!=1:raise DesignError('prepared ballot has no supported review runtime')
                    return self.send(source,mime='text/html')
                return self.send({'error':'not found'},404)
            except (OSError,ValueError,DesignError) as error:self.send({'error':str(error)},409)
        def do_POST(self):
            route=self.route()
            if route is None or self.headers.get('Origin')!='http://'+self.server.address:
                return self.send({'error':'local review origin required'},403)
            if route=='stop':
                self.send({'stopped':True});threading.Thread(target=self.server.shutdown,daemon=True).start();return
            match=re.fullmatch(r'review/(\d+)',route or '')
            if not match or int(match[1])>=len(parts):return self.send({'error':'not found'},404)
            try:
                length=int(self.headers.get('Content-Length','0'))
                if length<=0 or length>1048576:raise DesignError('review request must be between 1 byte and 1 MiB')
                body=json.loads(self.rfile.read(length));i=int(match[1]);part=parts[i]
                feedback=body.get('feedback');selected=body.get('selected_labels');complete=body.get('complete')
                if not isinstance(feedback,dict) or set(feedback)-set(part['keys']) or any(not isinstance(v,str) for v in feedback.values()):raise DesignError('invalid feedback keys or values')
                if type(complete)!=bool or not isinstance(selected,list) or any(not isinstance(x,str) for x in selected) or len(selected)!=len(set(selected)) or set(selected)-set(part.get('labels',[])):raise DesignError('invalid explicit selections')
                if not complete and selected:raise DesignError('confirm selection before submitting choices')
                if not feedback and not complete:raise DesignError('write a note or confirm a selection')
                saved={'feedback':feedback,'submitted_at':now(),'selected_labels':selected,'complete':complete}
                from design_ballot import STATE, import_ruling
                with Round(root) as record:
                    pending='image_ballot_pending' if kind=='images' else 'page_ballot_pending'
                    record.require(pending)
                    source=STATE.sub(lambda _: '<script type="application/json" id="fb-state">'+json.dumps({'feedback':feedback,'submitted_at':saved['submitted_at']}).replace('<','\\u003c')+'</script>',original(i),count=1)
                    dest=folder/'local-reviews'/str(i)/uuid.uuid4().hex
                    write_new(dest/'submitted.html',source)
                    receipt={'host':'local','review_url':'http://'+self.server.address+self.path,
                             'review_version':dest.name,'read_at':saved['submitted_at'],
                             'published_ballot_sha256':part['sha256'],'readback_sha256':digest(source),
                             'selection_status':'complete' if complete else 'needs_clarification',
                             'selected_labels':selected,'selection_method':'explicit_local_controls',
                             'owner_input':'owner-input.json'}
                    write_new(dest/'owner-input.json',saved);write_new(dest/'receipt.json',receipt)
                    result=import_ruling(record,kind,dest/'submitted.html',dest/'receipt.json')
                    atomic_json(dest.parent/'latest.json',saved)
                self.send({'saved':True,'result':result})
            except (OSError,ValueError,DesignError,KeyError,TypeError) as error:self.send({'error':str(error)},409)
    server=HTTPServer(('127.0.0.1',0),Handler)
    server.address='127.0.0.1:'+str(server.server_port)
    server.info={'url':'http://'+server.address+'/'+token+'/','instance':token,'pid':os.getpid(),'round':str(root),'kind':kind}
    return server


def serve(root,kind):
    root=Path(root).resolve()
    with (root/('.preview-'+kind+'.lock')).open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        server=make_server(root,kind)
        atomic_json(root/('.preview-'+kind+'.json'),server.info)
        try:server.serve_forever()
        finally:server.server_close()


if __name__=='__main__':serve(sys.argv[1],sys.argv[2])
