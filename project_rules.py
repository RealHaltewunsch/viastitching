"""Read clearance matrices not exposed by KiCad's SWIG rule-engine API.

Supports literal minimum-distance rules whose conditions compare A/B.NetClass
or A/B.NetName with &&, ||, parentheses, == and !=. Never eval project text.
Unsupported distance expressions fail before board edits instead of silently
placing vias using a guessed clearance.
"""
import re
import json
import fnmatch
from fractions import Fraction
from pathlib import Path

VIA_CONSTRAINTS={'disallow','via_diameter','annular_width','hole_size'}
DISTANCES={'clearance','physical_clearance','hole_clearance','physical_hole_clearance','hole_to_hole','edge_clearance'}

def sexpr(text):
 tokens=re.findall(r'\(|\)|"(?:\\.|[^"\\])*"|[^\s()]+',re.sub(r'(?m)#.*$','',text));stack=[[]]
 for token in tokens:
  if token=='(':
   new=[];stack[-1].append(new);stack.append(new)
  elif token==')':
   if len(stack)==1:raise ValueError('Unbalanced project rules')
   stack.pop()
  elif token.startswith('"'):
   stack[-1].append(token[1:-1].replace('\\"','"').replace('\\\\','\\'))
  else:stack[-1].append(token)
 if len(stack)!=1:raise ValueError('Unbalanced project rules')
 return stack[0]

def distance(value):
 m=re.fullmatch(r'([+-]?(?:\d+(?:\.\d*)?|\.\d+))(mm|mil|mils|in)?',value)
 if not m:raise ValueError('Distance rule must use a literal dimension: '+value)
 scale={'mm':1000000,'mil':25400,'mils':25400,'in':25400000,None:1000000}[m[2]]
 f=Fraction(m[1])*scale
 return -(-f.numerator//f.denominator)

def expression(text):
 if not text:return ('constant',True)
 token_re=re.compile(r"\s*(A\.(?:NetClass|NetName)|B\.(?:NetClass|NetName)|'(?:\\.|[^'\\])*'|==|!=|&&|\|\||[()])")
 tokens=[];pos=0
 while pos<len(text):
  if not text[pos:].strip():break
  m=token_re.match(text,pos)
  if not m:raise ValueError('Unsupported distance-rule condition: '+text)
  tokens.append(m[1]);pos=m.end()
 index=0
 def atom():
  nonlocal index
  if index<len(tokens) and tokens[index]=='(':
   index+=1;node=disjunction()
   if index>=len(tokens) or tokens[index]!=')':raise ValueError('Unbalanced rule condition')
   index+=1;return node
  if index+2>=len(tokens):raise ValueError('Incomplete rule condition')
  prop,operator,value=tokens[index:index+3];index+=3
  if prop not in ('A.NetClass','B.NetClass','A.NetName','B.NetName') or operator not in ('==','!=') or not value.startswith("'"):raise ValueError('Unsupported rule comparison')
  if any(c in value[1:-1] for c in '*?['):raise ValueError('Wildcard comparison is not supported in distance rules')
  return ('compare',prop,operator,value[1:-1])
 def conjunction():
  nonlocal index
  node=atom()
  while index<len(tokens) and tokens[index]=='&&':
   index+=1;node=('and',node,atom())
  return node
 def disjunction():
  nonlocal index
  node=conjunction()
  while index<len(tokens) and tokens[index]=='||':
   index+=1;node=('or',node,conjunction())
  return node
 node=disjunction()
 if index!=len(tokens):raise ValueError('Trailing rule condition')
 return node

def evaluate(node,a,b):
 kind=node[0]
 if kind=='constant':return node[1]
 if kind=='and':return evaluate(node[1],a,b) and evaluate(node[2],a,b)
 if kind=='or':return evaluate(node[1],a,b) or evaluate(node[2],a,b)
 _,prop,operator,value=node
 actual=(a if prop[0]=='A' else b)[prop.split('.')[1]]
 # Exact, case-sensitive literal comparison; no Python or KiCad expressions run.
 matched=value in actual if isinstance(actual,(tuple,list,set)) else actual==value
 return matched if operator=='==' else not matched

class ProjectRules:
 def __init__(self,path):
  self.rules=[];self.net_settings={};self.board_rules={}
  if path:
   project=Path(path).with_suffix('.kicad_pro')
   if project.exists():
    data=json.loads(project.read_text());self.net_settings=data.get('net_settings',{})
    self.board_rules=data.get('board',{}).get('design_settings',{}).get('rules',{})
  if not path or not Path(path).exists():return
  for form in sexpr(Path(path).read_text()):
   if not isinstance(form,list) or not form or form[0]!='rule':continue
   fields={f[0]:f[1:] for f in form[2:] if isinstance(f,list) and f}
   if fields.get('severity')==['ignore']:continue
   if any(isinstance(f,list) and len(f)>1 and f[0]=='constraint' and f[1] in VIA_CONSTRAINTS for f in form[2:]):raise ValueError('Custom via constraint is not supported: '+form[1])
   constraints=[f for f in form[2:] if isinstance(f,list) and len(f)>2 and f[0]=='constraint' and f[1] in DISTANCES]
   if not constraints:continue
   condition=expression(fields.get('condition',[''])[0])
   layer=fields.get('layer',[None])[0]
   for constraint in constraints:
    minimum=next((f[1] for f in constraint[2:] if isinstance(f,list) and len(f)==2 and f[0]=='min'),None)
    if minimum is not None:
     if constraint[1]!="clearance":raise ValueError("Custom "+constraint[1]+" rule is not supported: "+form[1])
     self.rules.append((constraint[1],condition,distance(minimum),layer,form[1]))
 def context(self,context):
  if not self.net_settings:return context
  net=context['NetName']
  assigned=(self.net_settings.get('netclass_assignments') or {}).get(net,[])
  if isinstance(assigned,str):assigned=[assigned]
  matches=set(assigned)
  native=context['NetClass']
  if isinstance(native,str) and native!='Default':matches.add(native)
  for entry in self.net_settings.get('netclass_patterns') or []:
   if fnmatch.fnmatchcase(net,entry['pattern']):matches.add(entry['netclass'])
  return {'NetName':net,'NetClass':tuple(sorted(matches or {'Default'}))}
 def inherited_clearance(self,context):
  names=context['NetClass'];names=(names,) if isinstance(names,str) else names
  values=[Fraction(str(c.get('clearance',0)))*1000000 for c in self.net_settings.get('classes',[]) if c['name'] in names]
  return max((int(v) for v in values),default=0)
 def minimum(self,kind,a,b,layer=None):
  values=[]
  for constraint,condition,value,required_layer,name in self.rules:
   if constraint!=kind:continue
   if required_layer not in (None,layer):
    if not (required_layer=='outer' and layer in ('F.Cu','B.Cu')) and not (required_layer=='inner' and layer not in ('F.Cu','B.Cu')):continue
   aa=a['NetClass'];aa=(aa,) if isinstance(aa,str) else aa
   bb=b['NetClass'];bb=(bb,) if isinstance(bb,str) else bb
   matched=False
   for aname in aa:
    for bname in bb:
     ac=dict(a,NetClass=aname);bc=dict(b,NetClass=bname)
     if evaluate(condition,ac,bc) or evaluate(condition,bc,ac):matched=True
   if matched:values.append(value)
  # A stricter minimum is safe even if a later rule relaxes an earlier rule.
  # Relaxation/precedence is intentionally conservative, documented to users.
  return max(values,default=0)
