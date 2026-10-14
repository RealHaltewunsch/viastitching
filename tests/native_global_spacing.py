"""Cross-region minimum spacing: independent local growth and global exclusion."""
from native_geometric import *
from native_fixtures import board_fixture,point,mm
Density=importlib.import_module(pkg.__name__+'.density_field')

def verify(points, pitch, minimum=.8, factors=None):
 from fractions import Fraction
 for i,p in enumerate(points):
  for q in points[i+1:]:
   required=Fraction(str(minimum))*(max(factors(p),factors(q)) if factors else 1)
   dx,dy=p[0]-q[0],p[1]-q[1]
   assert required.denominator**2*((dx*pitch[1])**2+(dy*pitch[0])**2)>=required.numerator**2*pitch[0]**2*pitch[1]**2,(p,q)

def checks():
 pitch=(1500000,1500000);left=rect(0,0,.1,8);right=rect(.8,0,.9,8)
 solver=engine.Engine(geo.Backend(),pitch,physical_radius=554000)
 a=list(solver.run_region(left));b=list(solver.run_region(right));assert a and b
 verify(a+b,pitch)
 assert not set(y for x,y in a)&set(y for x,y in b),'Close flanks remained aligned'
 repeat=engine.Engine(geo.Backend(),pitch,physical_radius=554000)
 assert list(repeat.run_region(left))+list(repeat.run_region(right))==a+b
 # Manual anchor belongs to the area processed LAST. It must constrain the first.
 anchor=(850000,4000000);s=engine.Engine(geo.Backend(),pitch,anchors=[anchor])
 first=list(s.run_region(left));verify(first+[anchor],pitch)
 assert (50000,4000000) not in first
 second=list(s.run_region(right,[anchor]));verify(first+second+[anchor],pitch)
 # Far groups keep exactly their own local pattern and unrelated plane keys.
 standalone=list(engine.Engine(geo.Backend(),pitch).run_region(left))
 s=engine.Engine(geo.Backend(),pitch);one=list(s.run_region(left));two=list(s.run_region(geo.shift(left,8370000,0)))
 assert one==standalone and two==[(x+8370000,y) for x,y in standalone]
 shift=(13370000,77230000);s=engine.Engine(geo.Backend(shift),pitch)
 moved=list(s.run_region(left))+list(s.run_region(right))
 assert moved==[(x+shift[0],y+shift[1]) for x,y in a+b]
 # X/Y unequal; compare every pair independently.
 pitch=(2000000,1000000);s=engine.Engine(geo.Backend(),pitch)
 pts=list(s.run_region(left))+list(s.run_region(right));verify(pts,pitch)
 # Larger adaptive factor wins across regions too, with exact rational thresholds.
 pitch=(1500000,1500000);f=Density.DensityField([],pitch)
 s=engine.Engine(geo.Backend(),pitch,density=f)
 pts=list(s.run_region(left))+list(s.run_region(right));verify(pts,pitch,factors=f.factor)
 assert len(pts)<len(a+b)
 # Actual KiCad track separates the allowed-center polygons.
 board,zone=board_fixture();track=pcbnew.PCB_TRACK(board)
 track.SetStart(point(14,0));track.SetEnd(point(14,25));track.SetWidth(mm(.2));track.SetLayer(pcbnew.F_Cu);track.SetNetCode(board.GetNetcodeFromNetname('SIGNAL'));board.Add(track)
 g=geo.BoardGeometry(board,zone,zone.GetNetCode(),mm(.6),mm(.3),0)
 solver=engine.Engine(g.backend,(2000000,2000000),anchors=g.anchors,physical_radius=g.pair_radius)
 actual=[];regions=0
 for shape,anchors in g.regions():
  regions+=1;actual.extend(solver.run_region(shape,anchors))
 assert regions>=2
 verify(actual,(2000000,2000000))
 print('Actual KiCad foreign-net track splits regions; all generated pairs respect global minimum PASS',flush=True)
 print('Close track-separated flanks, pre-registered manual vias, far independence, unequal X/Y, adaptive factors and translation PASS',flush=True)

if __name__=='__main__':
 app=wx.App(False);checks()
