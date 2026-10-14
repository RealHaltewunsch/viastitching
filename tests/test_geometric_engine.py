import sys,unittest
from pathlib import Path
from fractions import Fraction
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from geometric_engine import Polygon,Spacing,nearest,canonical_ring,ring_contains

class GeometryTests(unittest.TestCase):
 def test_ring_order_and_translation(self):
  ring=((0,0),(100,0),(100,50),(0,50))
  for k in range(4):
   moved=ring[k:]+ring[:k]
   self.assertEqual(canonical_ring(moved),canonical_ring(tuple(reversed(ring))))
   self.assertTrue(ring_contains((50,25),moved));self.assertFalse(ring_contains((120,25),moved))
 def test_hole(self):
  p=Polygon(((0,0),(100,0),(100,100),(0,100)),(((30,30),(70,30),(70,70),(30,70)),))
  self.assertTrue(p.contains((20,20)));self.assertFalse(p.contains((50,50)))
 def test_exact_spacing_and_unequal_xy(self):
  s=Spacing((2000000,1000000),'.8');s.add((0,0))
  self.assertFalse(s.allows((1599999,0)));self.assertTrue(s.allows((1600000,0)))
  self.assertFalse(s.allows((0,799999)));self.assertTrue(s.allows((0,800000)))
  self.assertTrue(s.covers_box((-10000,-10000,10000,10000)))
  self.assertFalse(s.covers_box((-1600000,-10000,1600000,10000)))
 def test_tiny_minimum_broad_query(self):
  s=Spacing((1500000,1500000),'0.000001')
  self.assertFalse(s.covers_box((0,0,300000000,100000000)))
  s.add((10000,10000))
  self.assertEqual(list(s.nearby((0,0,300000000,100000000))),[(10000,10000)])
 def test_fraction_rounding(self):
  self.assertEqual(nearest(Fraction(5000)),10000)
  self.assertEqual(nearest(Fraction(-5000)),0)
  self.assertEqual(nearest(Fraction(123456)),120000)
 def test_gap_center(self):
  p=Polygon(((0,0),(100000,0),(100000,8000000),(0,8000000)))
  self.assertEqual(next(p.centers()),(50000,4000000))
class ProjectRuleTests(unittest.TestCase):
 def test_matrix_and_units(self):
  from project_rules import expression,evaluate,distance
  a={'NetClass':'dp','NetName':'USB'};b={'NetClass':'Default','NetName':'GND'}
  node=expression("A.NetClass == 'dp' && B.NetClass == 'Default'")
  self.assertTrue(evaluate(node,a,b));self.assertFalse(evaluate(node,b,a))
  self.assertEqual(distance('0.16mm'),160000);self.assertEqual(distance('6mil'),152400)
 def test_unsupported_condition_is_not_executed(self):
  from project_rules import expression
  with self.assertRaises(ValueError):expression("A.insideArea('x')")

if __name__=='__main__':unittest.main()
