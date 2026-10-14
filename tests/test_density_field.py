import importlib,sys,types,unittest,math
from pathlib import Path
from fractions import Fraction
root=Path(__file__).resolve().parents[1]
pkg=types.ModuleType('density_unit');pkg.__path__=[str(root)];sys.modules[pkg.__name__]=pkg
density=importlib.import_module(pkg.__name__+'.density_field')
engine=importlib.import_module(pkg.__name__+'.geometric_engine')
Polygon=engine.Polygon
rect=lambda a,b,c,d:Polygon(((a,b),(c,b),(c,d),(a,d)))

class DensityTests(unittest.TestCase):
 def test_limits_and_transition(self):
  f=density.DensityField([rect(-10000,-10000,0,10000)],(1000000,1000000))
  for x,expected in [(0,1),(1000000,1),(2000000,2),(3000000,3),(20000000,3)]:self.assertEqual(f.factor((x,0)),expected)
  self.assertEqual(f.distance((-5000,0)),0)
  self.assertEqual(density.DensityField([],f.pitch).factor((0,0)),3)
 def test_oversized_contour_uses_bounded_index(self):
  f=density.DensityField([rect(0,0,1000000000,1000000000)],(1,1))
  self.assertEqual(len(f.buckets),0);self.assertEqual(len(f.oversized),1)
  self.assertEqual(f.distance((500000000,500000000)),0)
  self.assertEqual(f.factor((-100000,0)),3)
 def test_validation(self):
  for start,end,m in [(.99,3,3),(1,1,3),(3,2,3),(1,3,0),(1,3,1.5),(float('nan'),3,3),(1,float('inf'),3)]:
   with self.assertRaises(ValueError):density.validate_density(start,end,m)
  density.validate_density(1,3,1)
 def test_normalization_holes_and_translation(self):
  polygon=rect(-200000,-200000,200000,200000)
  f=density.DensityField([polygon],(2000000,1000000))
  self.assertAlmostEqual(f.distance((2200000,0)),1)
  self.assertAlmostEqual(f.distance((0,1200000)),1)
  ring=rect(-4000000,-4000000,4000000,4000000)
  f=density.DensityField([Polygon(ring.outer,(rect(-2000000,-2000000,2000000,2000000).outer,))],(1000000,1000000))
  self.assertEqual(f.factor((0,0)),2)
  shift=(13370000,77230000)
  moved=Polygon(tuple((x+shift[0],y+shift[1]) for x,y in polygon.outer))
  a=density.DensityField([polygon],(2000000,1000000));b=density.DensityField([moved],a.pitch)
  for p in [(0,0),(1600000,800000),(9000000,1000000)]:self.assertEqual(a.factor(p),b.factor((p[0]+shift[0],p[1]+shift[1])))
 def test_symmetric_spacing_and_existing_anchors(self):
  f=density.DensityField([rect(-10000,-100000,0,100000)],(1000000,1000000))
  index=f.spacing(.8);index.add((0,0))
  self.assertTrue(index.allows((1500000,0)))
  p,q=(1000000,0),(3000000,0)
  self.assertTrue(index.excludes(p,q));self.assertTrue(index.excludes(q,p))
  index.add(q);self.assertFalse(index.allows(p))
  # Field is unchanged by adding points to the spacing index.
  before=f.factor(p);index.add((9000000,9000000));self.assertEqual(f.factor(p),before)
 def test_far_spacing_exact_boundary_and_query(self):
  f=density.DensityField([],(2000000,1000000));index=f.spacing(.8);index.add((0,0))
  self.assertFalse(index.allows((4799999,0)));self.assertTrue(index.allows((4800000,0)))
  self.assertFalse(index.allows((0,2399999)));self.assertTrue(index.allows((0,2400000)))
  self.assertTrue(index.covers_box((0,0,100000,100000)))
  self.assertFalse(index.covers_box((0,0,5000000,100000)))
 def test_box_bound_is_conservative(self):
  f=density.DensityField([rect(-10000,-10000,0,10000)],(1000000,1000000))
  for bounds in [(500000,-500000,3500000,500000),(1800000,-10000,1900000,10000)]:
   lower=f.lower_factor(bounds)
   for x in range(bounds[0],bounds[2]+1,10000):self.assertLessEqual(lower,f.factor((x,0)))

if __name__=='__main__':unittest.main()
