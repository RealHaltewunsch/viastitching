"""Independent coordinate regression oracle for the upstream 0.3.x loop."""
import importlib.util
import math
from pathlib import Path
import random
import sys
import unittest

spec = importlib.util.spec_from_file_location('placement_engine', Path(__file__).parents[1]/'placement_engine.py')
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


def legacy(bounds, diameter, pitch, offset, style, rng):
    left, top, right, bottom = bounds
    sx, sy = pitch
    ox, oy = offset
    left += diameter//2; top += diameter//2
    right -= diameter//2; bottom -= diameter//2
    px = (left+ox) % sx; py = (top+oy) % sy
    xs = left if px == 0 else left+(sx-px)
    ys = top if py == 0 else top+(sy-py)
    result = []; y = ys; row = 0
    while y <= bottom:
        x = xs+(sx//2 if style == 'Stagger' and row % 2 else 0)
        while x <= right:
            if style == 'Randomize':
                xp = x+rng.uniform(-1,1)*sx/5
                yp = y+rng.uniform(-1,1)*sy/5
            else:
                xp,yp = x,y
            result.append((int(xp),int(yp)))
            x += sx
        y += sy; row += 1
    return result


class EngineTests(unittest.TestCase):
    def test_exact_upstream_coordinates(self):
        for style in ('Standard','Stagger','Randomize'):
            for bounds in ((0,0,17000,21000),(-8700,-3200,13900,15400),(0,0,20,20)):
                for offset in ((0,0),(300,-750),(1700,5200)):
                    with self.subTest(style=style,bounds=bounds,offset=offset):
                        args=(bounds,601,(1701,2301),offset,style)
                        self.assertEqual(list(m.grid_candidates(m.Grid(*args),random.Random(17))),
                                         legacy(*args,random.Random(17)))

    def test_classification_preserves_positions_and_order(self):
        points=[(0,0),(1,0),(2,0)]
        before=points[:]
        results=list(m.evaluate_candidates(points,lambda p:'edge' if p[0]==1 else None))
        self.assertEqual(points,before)
        self.assertEqual([x.position for x in results],points)
        self.assertEqual([x.accepted for x in results],[True,False,True])
        self.assertEqual(results[1].reason,'edge')

    def test_invalid_input_fails_before_iteration(self):
        for pitch in ((0,1),(-1,1),(math.nan,1),(1,math.inf)):
            with self.assertRaises(ValueError):
                list(m.grid_candidates(m.Grid((0,0,10,10),1,pitch)))

    def test_known_grid_phase(self):
        self.assertEqual(list(m.grid_candidates(m.Grid((0,0,10,10),2,(4,4)))),
                         [(4,4),(8,4),(4,8),(8,8)])
        self.assertEqual(list(m.grid_candidates(m.Grid((0,0,10,10),2,(4,4),style='Stagger'))),
                         [(4,4),(8,4),(6,8)])




class NewModeTests(unittest.TestCase):
    def test_spiral_center_order_and_spacing(self):
        points=list(m.spiral_candidates((-10000,-20000,10000,20000),(1000,2000)))
        self.assertEqual(points[0],(0,0))
        radii=[math.hypot(x/1000,y/2000) for x,y in points]
        self.assertTrue(all(b+0.002>=a for a,b in zip(radii,radii[1:])))
        index=m.SeparationIndex((1000,2000))
        # Integer rounding is corrected by the common separation validator.
        accepted=[]
        for p in points:
            if index.permits(p):index.add(p);accepted.append(p)
        self.assertGreater(len(accepted),200)
        self.assertTrue(all(math.hypot((a[0]-b[0])/1000,(a[1]-b[1])/2000)>=.999999
                            for i,a in enumerate(accepted) for b in accepted[:i]))

    def test_packing_is_repeatable_and_separated(self):
        candidates=list(m.packing_candidates((0,0,10000,10000),1000))
        self.assertEqual(candidates,list(m.packing_candidates((0,0,10000,10000),1000)))
        index=m.SeparationIndex((1000,1000));accepted=[]
        for p in candidates:
            if index.permits(p):accepted.append(p);index.add(p)
        self.assertTrue(all(math.dist(a,b)>=999.999 for i,a in enumerate(accepted) for b in accepted[:i]))

    def test_each_segment_is_centered(self):
        self.assertEqual(list(m.centered_segment(10,21,4)),[12,16,20])
        self.assertEqual(list(m.centered_segment(30,30,4)),[30])
        self.assertEqual(list(m.centered_segment(31,30,4)),[])


class BoundsTests(unittest.TestCase):
    def test_negative_large_and_duplicate_bounds(self):
        index=m.BoundsIndex(10)
        near,far,large=object(),object(),object()
        index.add((-12,-12,2,2),near)
        index.add((500,500,501,501),far)
        index.add((-1000,-1000,1000,1000),large)
        self.assertEqual(set(index.query((-1,-1,1,1))),{near,large})
        self.assertEqual(set(index.query((-2000,-2000,2000,2000))),{near,far,large})

if __name__ == '__main__': unittest.main()
