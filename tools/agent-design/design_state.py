"""Append-only stage receipts with a locked, replaceable manifest projection."""
from copy import deepcopy
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import uuid
from design_browser import DesignError
from design_contract import compile_contract, digest, prompts

STAGES=('briefed','images_ready','image_ballot_pending','images_ruled','measured','pages_ready','page_ballot_pending','ruled')


def now():return datetime.now(timezone.utc).isoformat()


def write_new(path, data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    raw=data if isinstance(data,bytes) else (data if isinstance(data,str) else json.dumps(data,ensure_ascii=False,indent=2)+'\n').encode()
    with path.open('xb') as f:
        f.write(raw);f.flush();os.fsync(f.fileno())
    return {'path':str(path),'sha256':digest(raw),'bytes':len(raw)}


def sync_directory(path):
    fd=os.open(path,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)


class Round:
    def __init__(self,path,create=False):
        self.path=Path(path).expanduser().resolve();self.create=create;self.lock=None;self.state=None

    def __enter__(self):
        if not self.path.exists():
            if not self.create:raise DesignError('round does not exist: '+str(self.path))
            self.path.mkdir(parents=True)
        self.lock=(self.path/'.lock').open('a+')
        try:fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock.close();raise DesignError('round is being mutated by another process')
        try:
            manifest=self.path/'manifest.json'
            if manifest.exists():
                self.state=json.loads(manifest.read_text());self.verify_inputs()
            elif (self.path/'initialization.json').exists():
                intent=json.loads((self.path/'initialization.json').read_text())
                self.initialize(**intent)
            elif not self.create:raise DesignError('round has no completed brief manifest')
            return self
        except BaseException:
            self.__exit__(None,None,None);raise

    def __exit__(self,*_):
        if self.lock:
            fcntl.flock(self.lock,fcntl.LOCK_UN);self.lock.close();self.lock=None

    def initialize(self,copy,facts,source='facts.json',raw_facts=None):
        if self.state is not None:raise DesignError('round already initialized; use a new round for changed inputs')
        contract=compile_contract(copy,facts,source)
        compiled=prompts(copy,contract) # Validate before writing an initialization intent.
        intent={'copy':copy,'facts':facts,'source':source,'raw_facts':raw_facts}
        marker=self.path/'initialization.json'
        if marker.exists():
            if json.loads(marker.read_text())!=intent:raise DesignError('interrupted brief inputs do not match the current inputs')
        else:
            if any(p.name!='.lock' for p in self.path.iterdir()):raise DesignError('round directory contains unrelated files; preserve it and use a new round')
            write_new(marker,intent);sync_directory(self.path)
        self.state={'schema':1,'id':self.path.name,'created_at':now(),'stage':'briefed','inputs':{},'images':[],'measurements':{},'pages':[],'ballots':{},'usage':[]}
        def preserve(path,data):
            raw=(data if isinstance(data,str) else json.dumps(data,ensure_ascii=False,indent=2)+'\n').encode()
            if path.exists():
                if path.read_bytes()!=raw:raise DesignError('interrupted brief output changed: '+str(path))
                return {'path':str(path.relative_to(self.path)),'sha256':digest(raw),'bytes':len(raw)}
            receipt=write_new(path,raw);receipt['path']=str(path.relative_to(self.path));return receipt
        for name,data in [('copy.md',copy),('facts.json',raw_facts if raw_facts is not None else facts),('contract.json',contract)]:
            self.state['inputs'][name]=preserve(self.path/'inputs'/name,data)
        self.state['prompts']={}
        for level,text in compiled.items():
            self.state['prompts'][level]=preserve(self.path/'prompts'/(level+'.txt'),text)
        self.save('approved inputs compiled into three prompts')
        return self.state

    def verify_inputs(self):
        for rec in [*self.state.get('inputs',{}).values(),*self.state.get('prompts',{}).values()]:
            path=self.resolve(rec['path'])
            if digest(path.read_bytes())!=rec['sha256']:raise DesignError('frozen input changed: '+rec['path'])

    def resolve(self,relative):
        path=(self.path/relative).resolve()
        if not path.is_relative_to(self.path):raise DesignError('round path escapes its directory')
        return path

    def contract(self):return json.loads(self.resolve('inputs/contract.json').read_text())

    def save(self,reason):
        if self.state is None:raise DesignError('round is not initialized')
        snapshot=deepcopy(self.state);snapshot['updated_at']=now();snapshot['reason']=reason
        name=uuid.uuid4().hex
        write_new(self.path/'history'/(name+'.json'),snapshot)
        staging=self.path/('.manifest-'+name)
        write_new(staging,snapshot);os.replace(staging,self.path/'manifest.json')
        sync_directory(self.path)
        # Keep live references to nested builder/attempt state attached across checkpoints.
        self.state.update(updated_at=snapshot['updated_at'],reason=reason)

    def require(self,*stages):
        if self.state['stage'] not in stages:raise DesignError('stage '+self.state['stage']+' cannot run this operation; requires '+', '.join(stages))

    def transition(self,stage):
        old=self.state['stage']
        if stage not in STAGES or STAGES.index(stage)!=STAGES.index(old)+1:raise DesignError('illegal stage transition: '+old+' -> '+stage)
        self.state['stage']=stage;self.save('stage '+stage)

    def attempt(self,kind):
        path=self.path/kind/uuid.uuid4().hex;path.mkdir(parents=True)
        return path

    def record_usage(self,path,receipt,stage):
        relative=str(Path(path).relative_to(self.path))
        if not any(row.get('receipt')==relative for row in self.state['usage']):
            usage=receipt.get('usage')
            self.state['usage'].append({'stage':stage,'receipt':relative,'usage':usage if usage is not None else 'usage not returned'})
            self.save('provider receipt retained: '+relative)
