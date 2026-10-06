import importlib
import sys
import types
from pathlib import Path
import unittest
import math

pkg=types.ModuleType('density_geometry_tests')
pkg.__path__=[str(Path(__file__).resolve().parents[1])]
sys.modules[pkg.__name__]=pkg
m=importlib.import_module(pkg.__name__+'.density_field')
a=importlib.import_module(pkg.__name__+'.adaptive_fill')


def rect(x0,y0,x1,y1):
    return ([(x0,y0),(x1,y0),(x1,y1),(x0,y1)],[])


class DensityTests(unittest.TestCase):
    def test_distance_contour_and_ramp(self):
        f=m.DensityField([rect(0,0,100,100)],(100,100))
        for p,d,s in [((50,50),0,1),((200,50),1,1),((300,50),2,2),((400,50),3,3),((900,50),3,3)]:
            self.assertAlmostEqual(f.distance(p),d)
            self.assertAlmostEqual(f.factor(p),s)

    def test_anisotropic_holes(self):
        outer,holes=rect(0,0,1000,1000)
        f=m.DensityField([(outer,[rect(200,200,800,800)[0]])],(200,100))
        self.assertAlmostEqual(f.distance((500,500)),1.5)
        self.assertAlmostEqual(f.distance((1200,500)),1)
        self.assertAlmostEqual(f.distance((500,1100)),1)

    def test_invalid_density_settings(self):
        m.validate_density(1,3,3)
        for v in [(0,3,3),(.999,3,3),(math.nan,3,3),(-1,3,3),(1,1,3),(2,1,3),(1,3,0),(1,3,1.5),(1,math.inf,3)]:
            with self.assertRaises(ValueError):m.validate_density(*v)

    def test_empty_board_coarse_phase_and_stability(self):
        f=m.DensityField([],(100,100))
        c=[(r,col,(col*100+20,r*100+30)) for r in range(10) for col in range(10)]
        got=m.ordered_candidates(c,f)
        self.assertEqual([p for _,p in got],[(x*100+20,y*100+30) for y in (0,3,6,9) for x in (0,3,6,9)])
        self.assertEqual(got,m.ordered_candidates(c,f))

    def test_near_candidates_preserved_and_transition_sorted(self):
        f=m.DensityField([rect(0,-100,100,1000)],(100,100))
        c=[(r,col,(col*100,r*100)) for r in range(6) for col in range(8)]
        got=m.ordered_candidates(c,f)
        self.assertEqual([p for near,p in got if near],[p for _,_,p in c if f.factor(p)==1])
        transition=[f.factor(p) for near,p in got if not near and f.factor(p)<3]
        self.assertEqual(transition,sorted(transition))

    def test_symmetric_local_exclusion_including_existing_vias(self):
        f=m.DensityField([rect(-100,-100,0,100)],(100,100))
        ix=m.DensityViaIndex(f);ix.add((300,0),[])
        self.assertEqual(list(ix.nearby((100,0),1)),[(2/3,frozenset())])
        self.assertEqual(list(ix.nearby((700,0),1)),[])

    def test_refill_does_not_repopulate_coarse_grid(self):
        f=m.DensityField([],(1000,1000));ix=m.DensityViaIndex(f)
        for x in range(0,9001,3000):
            for y in range(0,9001,3000):ix.add((x,y),[])
        region=a.Region(0,rect(-50,-50,9050,9050)[0],[])
        added=[]
        r=a.refill([region],ix,(0,0),(1000,1000),100,.8,1.5,
                   lambda p: added.append(p) or True,density=f)
        self.assertEqual(added,[])
        self.assertFalse(r.limited)

    def test_new_refill_pairs_use_larger_factor(self):
        f=m.DensityField([rect(-100,-100,0,5000)],(1000,1000));ix=m.DensityViaIndex(f)
        original=[(0,0),(5000,5000)]
        for p in original:ix.add(p,[])
        added=[]
        r=a.refill([a.Region(0,rect(-50,-50,6050,6050)[0],[])],ix,(0,0),(1000,1000),100,.8,1.5,
                   lambda p:added.append(p) or True,density=f)
        self.assertGreater(r.added,0)
        checked=original[:]
        for p in added:
            for q in checked:
                self.assertGreaterEqual(math.hypot((p[0]-q[0])/1000,(p[1]-q[1])/1000)+1e-12,
                                        .8*max(f.factor(p),f.factor(q)))
            checked.append(p)
