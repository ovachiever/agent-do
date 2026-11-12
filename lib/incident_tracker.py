"""Local, read-only incident evidence coordinator."""
from __future__ import annotations
import argparse, hashlib, json, os, re, shutil, subprocess, sys, tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import yaml

ROOT_NAME = ".agent-do-incident"; MAX_RESPONSE = 1_048_576
SOURCES = ("github", "kubernetes", "render")
SAFE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")
SECRET = re.compile(r"(?i)\b(token|secret|password|api[_-]?key|authorization)([=:]\s*)\S+")
SECRET_KEY = re.compile(r"(?i)(?:token|secret|password|api[_-]?key|authorization)")

class IncidentError(RuntimeError): pass
def now() -> str: return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
def redact(v: Any) -> Any:
    if isinstance(v,str): return SECRET.sub(lambda m:m.group(1)+m.group(2)+"[REDACTED]", v)
    if isinstance(v,list): return [redact(x) for x in v]
    if isinstance(v,dict): return {str(k): "[REDACTED]" if SECRET_KEY.search(str(k)) else redact(x) for k,x in v.items()}
    return v
def root(start: Path) -> Path:
    for p in (start, *start.parents):
        if (p/ROOT_NAME).is_dir(): return p/ROOT_NAME
    return start/ROOT_NAME
def load_config(start: Path) -> tuple[Path,dict[str,Any]]:
    p=root(start)/"config.yaml"
    if not p.is_file(): raise IncidentError("incident configuration not found; run `agent-do incident init`")
    text=p.read_text()
    try:
        events=list(yaml.parse(text))
        if any(isinstance(event,yaml.events.AliasEvent) or getattr(event,"anchor",None) for event in events):
            raise IncidentError("config must not use YAML aliases or anchors")
        if any(getattr(event,"tag",None) not in (None,"!", "tag:yaml.org,2002:str", "tag:yaml.org,2002:int", "tag:yaml.org,2002:null") for event in events):
            raise IncidentError("config must use plain YAML values")
        raw=yaml.safe_load(text)
    except yaml.YAMLError as e: raise IncidentError(f"invalid config: {e}") from None
    if not isinstance(raw,dict) or set(raw)-{"version","services"} or raw.get("version") != 1 or not isinstance(raw.get("services"),dict): raise IncidentError("config must contain only version: 1 and services")
    for name, service in raw["services"].items():
        if not isinstance(name,str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}",name) or not isinstance(service,dict) or set(service)-set(SOURCES) or not service: raise IncidentError(f"invalid service mapping: {name}")
        for source, keys in {"github":{"repository","workflow"},"kubernetes":{"context","namespace","deployment","container"},"render":{"service"}}.items():
            if source in service:
                block=service[source]
                if not isinstance(block,dict) or set(block)!=keys or any(not isinstance(block[k],str) or not SAFE.fullmatch(block[k]) or block[k].startswith("-") for k in keys): raise IncidentError(f"invalid {source} mapping for {name}")
        if "github" in service and not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+",service["github"]["repository"]): raise IncidentError(f"invalid github repository for {name}")
    return p.parent,raw
def dispatch(argv:list[str]) -> dict[str,Any]:
    exe=os.environ.get("AGENT_DO_INCIDENT_DISPATCHER") or str(Path(__file__).resolve().parents[1]/"agent-do")
    try: r=subprocess.run([exe,*argv],text=True,capture_output=True,timeout=45,check=False)
    except subprocess.TimeoutExpired: return {"ok":False,"error":{"code":"timeout","message":"provider command timed out"},"argv":argv}
    if len(r.stdout.encode())>MAX_RESPONSE: return {"ok":False,"error":{"code":"oversized","message":"provider response exceeded limit"},"argv":argv}
    try: data=json.loads(r.stdout)
    except json.JSONDecodeError: return {"ok":False,"error":{"code":"invalid_json","message":"provider did not return JSON"},"argv":argv}
    if r.returncode or not isinstance(data,(dict,list)): return {"ok":False,"error":{"code":"provider_failed","message":"provider command failed"},"argv":argv,"data":redact(data)}
    return {"ok":True,"argv":argv,"data":redact(data)}
def receipt(name:str, result:dict[str,Any], files:dict[str,Any]) -> dict[str,Any]:
    files[name]=result
    return {"source":name.split("-")[0],"collected_at":now(),"command":result["argv"],"status":"available" if result["ok"] else "degraded","receipt_files":[name+".json"],"error":result.get("error"),"redaction":{"applied":True}}
def duration(v:str)->timedelta:
    m=re.fullmatch(r"([1-9]\d*)([smhd])",v)
    if not m: raise IncidentError("--since must be a positive duration such as 30m")
    n,u=int(m[1]),m[2]; d=timedelta(**{ {"s":"seconds","m":"minutes","h":"hours","d":"days"}[u]:n})
    if d>timedelta(days=30): raise IncidentError("--since cannot exceed 30 days")
    return d
def parse_time(value: Any) -> datetime|None:
    if not isinstance(value,str): return None
    try: return datetime.fromisoformat(value.replace("Z","+00:00"))
    except ValueError: return None
def choose_run(data:Any, window_start:datetime)->str|None:
    runs=data if isinstance(data,list) else (data.get("runs",[]) if isinstance(data,dict) else [])
    candidates=[]
    for run in runs:
        if not isinstance(run,dict): continue
        created=parse_time(run.get("createdAt"))
        ident=run.get("databaseId") or run.get("id")
        if created and created>=window_start and ident is not None: candidates.append((created,str(ident)))
    return max(candidates,default=(None,None))[1]
def choose_pod(deployment:Any, container:str)->tuple[str,int,bool]|None:
    pods=(deployment.get("pods",[]) if isinstance(deployment,dict) else [])
    ranked=[]
    for pod in pods:
        if not isinstance(pod,dict) or not isinstance(pod.get("name"),str): continue
        states=[x for x in pod.get("containers",[]) if isinstance(x,dict) and x.get("name")==container]
        if not states: continue
        state=states[0]; restart=int(state.get("restart_count") or 0); bad=not state.get("ready") or bool(state.get("waiting_reason")) or bool(state.get("termination_reason"))
        ranked.append((not bad,-restart,pod["name"],restart,state.get("waiting_reason")=="CrashLoopBackOff"))
    if not ranked:return None
    _,_,name,restarts,crash=min(ranked); return name,restarts,crash
def add_receipt(envelope:dict[str,Any], name:str,result:dict[str,Any],files:dict[str,Any])->None:
    files[name]=result; envelope["receipt_files"].append(name+".json")
    envelope["collected_at"]=now(); envelope["command"]=result["argv"]; envelope["redaction"]={"applied":True}
    if not result["ok"]: envelope["status"]="degraded"; envelope["error"]=result["error"]
    elif envelope["status"]!="degraded": envelope["status"]="available"
def validate_service(service:dict[str,Any])->dict[str,Any]:
    checks={}
    if "github" in service:
        g=service["github"]; result=dispatch(["ci","runs",g["workflow"],"--repo",g["repository"],"--json"]); checks["github"]={"status":"available" if result["ok"] else "degraded","command":result["argv"],"error":result.get("error")}
    if "kubernetes" in service:
        k=service["kubernetes"]; result=dispatch(["k8s","deployment",k["deployment"],"--context",k["context"],"--namespace",k["namespace"],"--json"]); checks["kubernetes"]={"status":"available" if result["ok"] else "degraded","command":result["argv"],"error":result.get("error")}
    if "render" in service:
        result=dispatch(["render","show",service["render"]["service"],"--json"]); checks["render"]={"status":"available" if result["ok"] else "degraded","command":result["argv"],"error":result.get("error")}
    return checks
def summary(files:dict[str,Any], envelopes:dict[str,Any], sha:Any)->dict[str,Any]:
    ci=(files.get("ci-details",{}).get("data") or {}).get("run",{}) if isinstance(files.get("ci-details",{}).get("data"),dict) else {}
    deploy=(files.get("k8s-deployment",{}).get("data") or {}).get("deployment",{}) if isinstance(files.get("k8s-deployment",{}).get("data"),dict) else {}
    render=(files.get("render",{}).get("data") or {}) if isinstance(files.get("render",{}).get("data"),dict) else {}
    render_shas=[x.get("commit_sha") for x in render.get("deploys",[]) if isinstance(x,dict)]
    return {"workflow":{"run_id":ci.get("id"),"conclusion":ci.get("conclusion"),"sha":sha},
            "workload":{"images":deploy.get("images",[]),"replicas":deploy.get("replicas",{}),"pods":len((files.get("k8s-deployment",{}).get("data") or {}).get("pods",[]))},
            "correlations":[{"source":"render","strength":"exact" if isinstance(sha,str) and sha in render_shas else "unknown","summary":"Render deployment SHA matches workflow SHA" if isinstance(sha,str) and sha in render_shas else "No exact Render/workflow SHA match was available"}],
            "source_status":{k:v["status"] for k,v in envelopes.items()}}
def timeline(files:dict[str,Any])->list[dict[str,Any]]:
    rows=[]
    for name,result in files.items():
        data=result.get("data") if isinstance(result,dict) else None
        if name=="ci-details" and isinstance(data,dict):
            run=data.get("run") or {}; rows.append({"event_id":"ci-run","timestamp":(run.get("timestamps") or {}).get("updated_at"),"source":"github","kind":"workflow","summary":str(run.get("conclusion") or run.get("status") or "workflow run"),"strength":"exact","receipt":"ci-details.json"})
        if name=="render" and isinstance(data,dict):
            for deploy in data.get("deploys",[]):
                if isinstance(deploy,dict): rows.append({"event_id":"render-"+str(deploy.get("id")),"timestamp":deploy.get("finished_at") or deploy.get("created_at"),"source":"render","kind":"deploy","summary":str(deploy.get("status") or "deploy"),"strength":"candidate","receipt":"render.json"})
    return sorted(rows,key=lambda x:(x["timestamp"] is None,str(x["timestamp"] or ""),x["event_id"]))
def trace(base:Path, config:dict[str,Any], service:str, run_id:str|None, since:str, output:str|None)->dict[str,Any]:
    if service not in config["services"]: raise IncidentError(f"unknown service: {service}")
    mapping=config["services"][service]; start=datetime.now(timezone.utc); window=duration(since); files={}; envelopes={s:{"source":s,"configured":s in mapping,"status":"unavailable" if s not in mapping else "degraded","receipt_files":[]} for s in SOURCES}
    sha=None
    if "github" in mapping:
        g=mapping["github"]; selected=run_id
        if not selected:
            rr=dispatch(["ci","runs",g["workflow"],"--repo",g["repository"],"--json"]); add_receipt(envelopes["github"],"ci-runs",rr,files)
            selected=choose_run(rr.get("data"),start-window) if rr["ok"] else None
        if selected:
            d=dispatch(["ci","details",str(selected),"--repo",g["repository"],"--json"]); add_receipt(envelopes["github"],"ci-details",d,files)
            if d["ok"]:
                sha=((d["data"].get("run") or {}).get("head_sha")) if isinstance(d["data"],dict) else None
                conclusion=((d["data"].get("run") or {}).get("conclusion")) if isinstance(d["data"],dict) else None
                if conclusion in {"failure","timed_out","action_required","startup_failure"}: add_receipt(envelopes["github"],"ci-logs",dispatch(["ci","logs",str(selected),"--failed","--tail","200","--max-bytes","65536","--repo",g["repository"],"--json"]),files)
            if isinstance(sha,str) and re.fullmatch(r"[0-9a-fA-F]{40,64}",sha): add_receipt(envelopes["github"],"github-commit",dispatch(["gh","commit",sha,"--repo",g["repository"],"--json"]),files)
    if "kubernetes" in mapping:
        k=mapping["kubernetes"]; common=["--context",k["context"],"--namespace",k["namespace"],"--json"]
        dep=dispatch(["k8s","deployment",k["deployment"],*common]); add_receipt(envelopes["kubernetes"],"k8s-deployment",dep,files)
        add_receipt(envelopes["kubernetes"],"k8s-events",dispatch(["k8s","events","--for-deployment",k["deployment"],*common]),files)
        picked=choose_pod(dep.get("data"),k["container"]) if dep["ok"] else None
        if picked:
            pod,restarts,crash=picked; log=["k8s","logs",pod,"--container",k["container"],"--context",k["context"],"--namespace",k["namespace"],"--since",since,"--tail","200","--max-bytes","65536","--json"]
            add_receipt(envelopes["kubernetes"],"k8s-logs-current",dispatch(log),files)
            if restarts>0 or crash: add_receipt(envelopes["kubernetes"],"k8s-logs-previous",dispatch([*log[:-1],"--previous","--json"]),files)
    if "render" in mapping:
        r=mapping["render"]; add_receipt(envelopes["render"],"render",dispatch(["render","trace",r["service"],"--since",since,"--max-log-bytes","65536","--json"]),files)
    trace_id=start.strftime("%Y%m%dT%H%M%SZ")+"-"+service
    dest=Path(output).resolve() if output else base/"traces"/trace_id
    if dest.exists(): raise IncidentError("output packet already exists")
    overview=summary(files,envelopes,sha); rows=timeline(files)
    packet={"schema_version":1,"trace_id":trace_id,"service":service,"started_at":start.isoformat(),"window":since,"mapping":mapping,"sources":envelopes,"summary":overview,"receipts":{},"overall_state":"available" if all(e["status"]!="degraded" for e in envelopes.values() if e["configured"]) else "degraded","notice":"Evidence packet only; it does not determine root cause."}
    stage=Path(tempfile.mkdtemp(prefix=".incident-staging-",dir=dest.parent)); stage.chmod(0o700)
    try:
        for name,data in files.items(): (stage/(name+".json")).write_text(json.dumps(data,indent=2)+"\n")
        (stage/"timeline.jsonl").write_text("".join(json.dumps(row)+"\n" for row in rows))
        states="\n".join(f"- {name}: {item['status']}" for name,item in envelopes.items())
        (stage/"README.md").write_text(f"# Incident trace {trace_id}\n\nEvidence state: {packet['overall_state']}\n\n## Sources\n{states}\n\nWorkflow SHA: {sha or 'unknown'}\n\nThis packet is evidence, not a root-cause determination.\n")
        for f in stage.iterdir():
            if f.is_file(): packet["receipts"][f.name]={"bytes":f.stat().st_size,"sha256":hashlib.sha256(f.read_bytes()).hexdigest()}
        (stage/"trace.json").write_text(json.dumps(packet,indent=2)+"\n"); stage.replace(dest)
    except Exception:
        shutil.rmtree(stage,ignore_errors=True); raise
    return {"success":True,"trace_id":trace_id,"path":str(dest),"trace":packet}
