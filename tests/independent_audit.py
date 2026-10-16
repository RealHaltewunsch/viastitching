"""Independent verification using Shapely/SciPy, NOT installed in the plugin.

Subtract inscribed spacing disks. Verify the residual by polygon/rectangle
intersection and exact integer corner proofs. Never trust Engine.find or its
completion flag. Whole-board point enumeration is not used.
"""
import json,math,sys,time,subprocess,os
from fractions import Fraction
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
import shapely
from shapely.geometry import Point,Polygon,box
from shapely.affinity import scale
from shapely.ops import unary_union
ROOT=Path(sys.argv[1]);name=sys.argv[2];out=ROOT/name
data=json.loads((out/'audit-data.json').read_text());sx,sy=data['pitch'];n,d=data['minimum'];step=10000
origin=data['origin'];physical=data['physical_radius'];allp=data['all_positions']
physical_tree=cKDTree(allp)
density=data.get('density');multiple=density['multiple'] if density else 1
copper=unary_union([Polygon(p['outer'],p['holes']) for p in density['polygons']]) if density else None
boundaries=unary_union([Polygon(p['outer'],p['holes']).boundary for p in density.get('boundaries',[])]) if density else None
factor_cache={}
certificates=[];oracle=None
if '--copper-guard' in sys.argv:
 native=os.environ.get('KICAD_PYTHON','/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3')
 oracle=subprocess.Popen([native,str(Path(__file__).with_name('native_connectivity_oracle.py')),str(out)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=(out/'oracle.log').open('w'),text=True)
 ready=json.loads(oracle.stdout.readline());assert ready.get('ready'),ready

def density_distance(p):
 point=Point(p[0]/sx,p[1]/sy);dist=density['end']
 if copper is not None and not copper.is_empty:dist=min(dist,point.distance(copper))
 if boundaries is not None and not boundaries.is_empty:dist=min(dist,point.distance(boundaries))
 return dist
def factor_distance(distance):
 return 1+(multiple-1)*min(1,max(0,(distance-density['start'])/(density['end']-density['start'])))
def factor(p):
 if not density:return Fraction(1)
 key=tuple(p)
 if key not in factor_cache:factor_cache[key]=Fraction(round(factor_distance(density_distance(p))*1000000),1000000)
 return factor_cache[key]
def lower_factor(bounds):
 if not density:return Fraction(1)
 a,b,c,e=bounds;center=((a+c)/2,(b+e)/2)
 radius=math.hypot((c-a)/(2*sx),(e-b)/(2*sy))
 return Fraction(max(1000000,math.floor(factor_distance(max(0,density_distance(center)-radius))*1000000)-1),1000000)
def excluded(p,q,fixed_factor=None):
 dx=int(p[0])-int(q[0]);dy=int(p[1])-int(q[1])
 required=Fraction(n,d)*(fixed_factor if fixed_factor is not None else max(factor(p),factor(q)))
 return required.denominator**2*((dx*sy)**2+(dy*sx)**2)<required.numerator**2*sx*sx*sy*sy

def physical_excluded(p,q):return (int(p[0])-int(q[0]))**2+(int(p[1])-int(q[1]))**2<physical**2

def closest(tree,p,r):return tree.query_ball_point(p,r+1e-7) if tree is not None else []

envelope_points={};envelope_radii={}
for region in data['regions']:
 for key,radius in region.get('envelopes',[]):
  envelope_radii[key]=radius
  envelope_points.setdefault(key,[]).extend([[x+origin[0],y+origin[1]] for x,y in region['positions']])
envelope_trees={key:cKDTree(points) for key,points in envelope_points.items() if points}
def envelope_excluded(p,q,radius):return (int(p[0])-int(q[0]))**2+(int(p[1])-int(q[1]))**2<radius**2
assert len({tuple(p) for p in allp})==len(allp),'Duplicate generated via positions'
global_points=[[x-origin[0],y-origin[1]] for x,y in allp]+data.get('global_anchors',[])
global_coordinates=np.array(global_points,dtype=np.float64).reshape((-1,2))
global_normalized=global_coordinates/np.array((sx,sy))
global_tree=cKDTree(global_normalized) if len(global_points) else None
global_mask=unary_union([Point(q).buffer(n/d*float(factor(global_points[i]))-2/min(sx,sy),quad_segs=24) for i,q in enumerate(global_normalized)]) if data.get('global_spacing') else None
start=time.monotonic();nodes=probes=0
for region in data['regions']:
 points=global_points if data.get('global_spacing') else region['positions']+region['anchors']
 active=[(envelope_trees[key],envelope_points[key],radius) for key,radius in region.get('envelopes',[]) if key in envelope_trees]
 if data.get('global_spacing'):
  normalized=global_normalized;tree=global_tree
 else:
  coordinates=np.array(points,dtype=np.float64).reshape((-1,2));normalized=coordinates/np.array((sx,sy))
  tree=cKDTree(normalized) if len(points) else None
 # Independently check ALL generated pairs and ALL existing same-net anchors.
 for i,p in enumerate(region['positions']):
  for j in closest(tree,(p[0]/sx,p[1]/sy),n/d*multiple):
   if points[j]==p:continue
   assert not excluded(p,points[j]),('Density distance violated',p,points[j])
  world=[p[0]+origin[0],p[1]+origin[1]]
  for extra_tree,extra_points,extra_radius in active:
   for j in closest(extra_tree,world,extra_radius):
    if extra_points[j]==world:continue
    assert not envelope_excluded(world,extra_points[j],extra_radius),('Foreign-plane hole envelopes overlap',world,extra_points[j])
  for j in closest(physical_tree,world,physical):
   if allp[j]==world:continue
   assert not physical_excluded(world,allp[j]),('Global physical distance violated',world,allp[j])
 shape=unary_union([Polygon(p['outer'],p['holes']) for p in region['polygons']])
 norm=scale(shape,xfact=1/sx,yfact=1/sy,origin=(0,0))
 for p in region['positions']:assert shape.covers(Point(p)),('Outside allowed geometry',p)
 mask=global_mask if data.get('global_spacing') else unary_union([Point(q).buffer(n/d*float(factor(points[i]))-2/min(sx,sy),quad_segs=24) for i,q in enumerate(normalized)])
 remaining=norm.difference(mask)
 stack=[remaining]
 while stack:
  piece=stack.pop();nodes+=1
  if piece.is_empty:continue
  a,b,c,e=piece.bounds
  lo=math.ceil(a*sx/step-1e-9);hi=math.floor(c*sx/step+1e-9)
  bt=math.ceil(b*sy/step-1e-9);tp=math.floor(e*sy/step+1e-9)
  if lo>hi or bt>tp:continue
  if any(all((x*step-p[0])**2+(y*step-p[1])**2<=r*r for x,y in ((lo,bt),(lo,tp),(hi,bt),(hi,tp))) for p,r in certificates):continue
  corners=[(x*step,y*step) for x,y in ((lo,bt),(lo,tp),(hi,bt),(hi,tp))]
  center=((lo+hi)*step/(2*sx),(bt+tp)*step/(2*sy));reach=math.hypot((hi-lo)*step/(2*sx),(tp-bt)*step/(2*sy))+n/d*multiple
  lower=lower_factor((lo*step,bt*step,hi*step,tp*step))
  if any(all(excluded(p,points[j],max(lower,factor(points[j]))) for p in corners) for j in closest(tree,center,reach)):continue
  worldcorners=[(p[0]+origin[0],p[1]+origin[1]) for p in corners]
  worldcenter=((lo+hi)*step/2+origin[0],(bt+tp)*step/2+origin[1]);reach=math.hypot((hi-lo)*step/2,(tp-bt)*step/2)+physical
  if any(all(physical_excluded(p,allp[j]) for p in worldcorners) for j in closest(physical_tree,worldcenter,reach)):continue
  if any(any(all(envelope_excluded(p,extra_points[j],extra_radius) for p in worldcorners) for j in closest(extra_tree,worldcenter,math.hypot((hi-lo)*step/2,(tp-bt)*step/2)+extra_radius)) for extra_tree,extra_points,extra_radius in active):continue
  x=(lo+hi)//2*step;y=(bt+tp)//2*step;p=(x,y)
  probes+=1
  # Native exclusion edges are forbidden; GEOS covers includes them.
  # Probe the strict permitted interior, excluding numerical boundary points.
  if shape.contains(Point(p)) and not any(excluded(p,points[j]) for j in closest(tree,(x/sx,y/sy),n/d*multiple)):
   world=(x+origin[0],y+origin[1])
   blocked=any(physical_excluded(world,allp[j]) for j in closest(physical_tree,world,physical)) or any(any(envelope_excluded(world,extra_points[j],extra_radius) for j in closest(extra_tree,world,extra_radius)) for extra_tree,extra_points,extra_radius in active)
   if not blocked and oracle:
    oracle.stdin.write(json.dumps(p)+'\n');oracle.stdin.flush()
    answer=json.loads(oracle.stdout.readline());blocked=not answer['allowed'];certificates=answer['certificates']
   assert blocked,('Remaining insertable center',name,p)
  if lo==hi and bt==tp:continue
  if hi-lo>=tp-bt and hi>lo:
   mid=((lo+hi)//2+.5)*step/sx
   regions=[box(a,b,mid,e),box(mid,b,c,e)]
  else:
   mid=((bt+tp)//2+.5)*step/sy
   regions=[box(a,b,c,mid),box(a,mid,c,e)]
  stack.extend(piece.intersection(r) for r in regions)
result={'board':name,'adaptive_density':bool(density),'remaining_insertable_centers':0,'coverage_domain':'strict permitted polygon interior','spacing_pass':True,'global_same_net_spacing':bool(data.get('global_spacing')),'global_physical_spacing_pass':True,'foreign_plane_envelopes_pass':True,'nodes':nodes,'point_probes':probes,'seconds':time.monotonic()-start}
if oracle:
 oracle.stdin.close();oracle.wait();assert oracle.returncode==0
 result['foreign_connectivity_constraints']=True;result['foreign_connectivity_certificates']=len(certificates)
 (out/'audit-certificates.json').write_text(json.dumps(certificates))
(out/'audit-result.json').write_text(json.dumps(result,indent=2));print(result,flush=True)
