"""Home copy check: every paragraph of the approved copy must appear verbatim (whitespace-normalised,
straight/curly quotes equal), in order; report any sentence on the page (>= 6 words) that is not from
the copy, the brief, or the sketch figures."""
import re, sys, json, pathlib
from html.parser import HTMLParser
COPY = pathlib.Path('/Users/erik/Custom-Coding/palingenesis/docs/design-canon/briefs/home-copy-2026-09-18.md').read_text()
BRIEF = json.load(open('/Users/erik/Custom-Coding/palingenesis/docs/design-canon/briefs/home-brief.json'))
def norm(s):
    s = s.replace('’',"'").replace('‘',"'").replace('“','"').replace('”','"').replace(' ',' ')
    return re.sub(r'\s+',' ',s).strip()
paras = [norm(p) for p in COPY.split('\n\n') if p.strip() and not p.strip().startswith('Sign in')]
allowed = set()
def walk(o):
    if isinstance(o,str): allowed.add(norm(o))
    elif isinstance(o,dict): [walk(v) for v in o.values()]
    elif isinstance(o,list): [walk(v) for v in o]
walk(BRIEF)
class P(HTMLParser):
    def __init__(s): super().__init__(); s.skip=0; s.t=[]
    def handle_starttag(s,t,a):
        if t in ('style','script','title'): s.skip+=1
    def handle_endtag(s,t):
        if t in ('style','script','title'): s.skip-=1
    def handle_data(s,d):
        if not s.skip and d.strip(): s.t.append(norm(d))
for f in sys.argv[1:]:
    p=P(); p.feed(pathlib.Path(f).read_text()); page=' '.join(p.t); page=norm(page)
    missing=[i+1 for i,q in enumerate(paras) if q not in page]
    pos=[page.find(q) for q in paras if q in page]; ordered = pos==sorted(pos)
    stray=[t for t in p.t if len(t.split())>=6 and t not in allowed and not any(t in q for q in paras)]
    motto = 'Every claim sourced' in page
    print(f"{pathlib.Path(f).name}: paragraphs {len(paras)-len(missing)}/{len(paras)} present, missing {missing}, in order {ordered}, motto {motto}, stray sentences {len(stray)}")
    for s in stray[:12]: print('   ✗', s[:150])
