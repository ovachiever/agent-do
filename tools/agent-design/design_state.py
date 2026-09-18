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
            elif not self.create:raise DesignError('round has no completed brief manifest')
            return self
        except BaseException:
            self.__exit__(None,None,None);raise

    def __exit__(self,*_):
        if self.lock:
            fcntl.flock(self.lock,fcntl.LOCK_UN);self.lock.close();self.lock=None

    def initialize(self,copy,facts,source='facts.json'):
        if self.state is not None:raise DesignError('round already initialized; use a new round for changed inputs')
        if any(p.name!='.lock' for p in self.path.iterdir()):raise DesignError('round directory contains unfinished or unrelated files; preserve it and use a new round')
        contract=compile_contract(copy,facts,source)
        self.state={'schema':1,'id':self.path.name,'created_at':now(),'stage':'briefed','inputs':{},'images':[],'measurements':{},'pages':[],'ballots':{},'usage':[]}
        for name,data in [('copy.md',copy),('facts.json',facts),('contract.json',contract)]:
            receipt=write_new(self.path/'inputs'/name,data);receipt['path']=str(Path(receipt['path']).relative_to(self.path));self.state['inputs'][name]=receipt
        self.state['prompts']={}
        for level,text in prompts(copy,contract).items():
            receipt=write_new(self.path/'prompts'/(level+'.txt'),text);receipt['path']=str(Path(receipt['path']).relative_to(self.path));self.state['prompts'][level]=receipt
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
        self.state=snapshot

    def require(self,*stages):
        if self.state['stage'] not in stages:raise DesignError('stage '+self.state['stage']+' cannot run this operation; requires '+', '.join(stages))

    def transition(self,stage):
        old=self.state['stage']
        if stage not in STAGES or STAGES.index(stage)!=STAGES.index(old)+1:raise DesignError('illegal stage transition: '+old+' -> '+stage)
        self.state['stage']=stage;self.save('stage '+stage)

    def attempt(self,kind):
        path=self.path/kind/uuid.uuid4().hex;path.mkdir(parents=True)
        return path
