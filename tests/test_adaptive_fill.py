import math
import unittest

from adaptive_fill import Region, ViaIndex, local_candidates, refill, validate_settings


def rectangle(x0, y0, x1, y1, layer=0, holes=None):
    return Region(layer, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], holes or [])


class AdaptiveFillTests(unittest.TestCase):
    def run_fill(self, regions, existing=(), pitch=(1000, 1000), origin=(0, 0),
                 blocked=lambda p: False, **kwargs):
        index = ViaIndex(pitch)
        for point, ids in existing:
            index.add(point, ids)
        added = []
        def place(point):
            if blocked(point):
                return False
            added.append(point)
            return True
        result = refill(regions, index, origin, pitch, 100, .8, 1.5, place, **kwargs)
        return result, added

    def test_regular_grid_does_not_get_denser(self):
        region = rectangle(-100, -100, 2100, 2100)
        existing = [((x, y), [0]) for x in (0, 1000, 2000) for y in (0, 1000, 2000)]
        result, added = self.run_fill([region], existing)
        self.assertEqual(added, [])
        self.assertEqual(result.unserved, 0)

    def test_small_island_without_grid_point(self):
        region = rectangle(200, 200, 450, 450)
        result, added = self.run_fill([region])
        self.assertEqual(result.added, 1)
        self.assertTrue(region.fits(added[0], 50))
        self.assertEqual(result.unserved, 0)

    def test_neighboring_island_does_not_count_as_connected(self):
        regions = [rectangle(-100,-100,100,100), rectangle(850,100,1150,400)]
        result, added = self.run_fill(regions, [((0,0), [0])])
        self.assertEqual(result.added, 1)
        self.assertEqual(result.unserved, 0)
        self.assertTrue(regions[1].fits(added[0], 50))

    def test_obstructed_grid_point_gets_offset_candidate(self):
        region = rectangle(-100, -400, 2100, 400)
        blocked = lambda p: 900 < p[0] < 1100 and -100 < p[1] < 100
        result, added = self.run_fill([region], [((0,0),[0]), ((2000,0),[0])], blocked=blocked)
        self.assertEqual(result.added, 1)
        self.assertNotEqual(added[0], (1000,0))
        self.assertFalse(blocked(added[0]))
        self.assertLess(abs(added[0][0]-1000), 500)

    def test_hole_and_narrow_impossible_island(self):
        hole = [(200,200),(800,200),(800,800),(200,800)]
        region = rectangle(-100,-100,1100,1100, holes=[hole])
        _, added = self.run_fill([region])
        self.assertTrue(all(region.fits(p,50) for p in added))
        result, added = self.run_fill([rectangle(200,200,240,500)])
        self.assertEqual(result.unserved, 1)
        self.assertFalse(added)

    def test_rectangular_metric_and_new_via_spacing(self):
        pitch = (2000,500)
        result, added = self.run_fill([rectangle(0,0,6000,2000)], pitch=pitch)
        self.assertGreater(result.added, 5)
        for i, a in enumerate(added):
            for b in added[:i]:
                self.assertGreaterEqual(math.hypot((a[0]-b[0])/2000, (a[1]-b[1])/500), .8)

    def test_layer_islands_tracked_separately(self):
        regions = [rectangle(-100,-100,100,100,0), rectangle(850,100,1150,400,2)]
        result, added = self.run_fill(regions, [((0,0),[0])])
        self.assertEqual(result.unserved,0)
        self.assertTrue(any(regions[1].fits(p,50) for p in added))

    def test_first_island_via_does_not_need_nearby_neighbor(self):
        result, _ = self.run_fill([rectangle(10000,10000,10300,10300)], [((0,0),[])])
        self.assertEqual(result.added,1)

    def test_full_obstruction_and_cancellation(self):
        result, added = self.run_fill([rectangle(0,0,1000,1000)], blocked=lambda p: True)
        self.assertEqual(result.unserved,1)
        self.assertFalse(added)
        result, _ = self.run_fill([rectangle(0,0,1000,1000)], progress=lambda count, examined: False)
        self.assertTrue(result.cancelled)

    def test_stagger_and_offset_are_deterministic(self):
        args = ([rectangle(0,0,4000,4000)],)
        a = self.run_fill(*args, origin=(200,100), stagger=True)
        b = self.run_fill(*args, origin=(200,100), stagger=True)
        self.assertEqual(a,b)
        self.assertIn((200,100), a[1])
        self.assertIn((700,1100), a[1])

    def test_candidate_search_is_bounded_and_reaches_fine_resolution(self):
        points = list(local_candidates((0,0),(-500,-500,500,500),(1000,1000),100, limit=20000))
        self.assertEqual(points[0],(0,0))
        self.assertEqual(len(points),len(set(points)))
        self.assertLessEqual(len(points),20000)
        self.assertIn((10,10),points)

    def test_large_distance_limit_does_not_enumerate_empty_buckets(self):
        index = ViaIndex((1000,1000))
        index.add((0,0),[0])
        self.assertEqual(list(index.nearby((1000,0),1e100)),[(1.0,frozenset([0]))])

    def test_frontier_revisits_cells_before_initial_seed(self):
        region = rectangle(-100,-100,5100,100)
        result, added = self.run_fill([region],[((5000,0),[0])])
        self.assertEqual(result.added,5)
        self.assertIn((0,0),added)

    def test_blocked_path_does_not_prevent_seeding_a_gap_on_same_plane(self):
        region = rectangle(-100, -100, 8100, 2100)
        result, added = self.run_fill([region], [((0, 0), [0])],
                                     blocked=lambda p: p[0] < 5000)
        self.assertGreater(result.added, 0)
        self.assertTrue(any(p[0] >= 5000 for p in added))

    def test_blocked_cells_do_not_exhaust_budget_before_later_offsets(self):
        region = rectangle(-100, -100, 10100, 1100)
        result, added = self.run_fill([region], candidate_limit=1000,
            blocked=lambda p: not (9750 <= p[0] <= 10200 and 200 <= p[1] <= 400))
        self.assertGreater(result.added, 0)

    def test_nearby_via_does_not_discard_entire_offset_cell(self):
        region = rectangle(-1000, -500, 500, 500)
        result, added = self.run_fill([region], [((-700, 0), [0])],
                                     blocked=lambda p: p[0] < 200)
        self.assertGreater(result.added, 0)
        self.assertTrue(any(p[0] >= 200 for p in added))

    def test_geometry_hint_still_obeys_spacing_and_physical_checks(self):
        region = rectangle(-100, -100, 5100, 1100)
        hints = lambda target: [(target[0] + 123, target[1])]
        result, added = self.run_fill([region], [((0, 0), [0])],
            candidate_hints=hints, blocked=lambda p: p[0] != 3123)
        self.assertGreater(result.added, 0)
        self.assertTrue(all(p[0] == 3123 for p in added))

    def test_spacing_preference_breaks_equal_grid_distance_ties(self):
        candidates = list(local_candidates((0,0),(-500,-500,500,500),(1000,1000),100,
                                           spacing_error=lambda p: 0 if p[0] > 0 else 1))
        self.assertLess(candidates.index((250,0)),candidates.index((-250,0)))

    def test_default_cell_and_total_search_budgets(self):
        self.assertLessEqual(len(list(local_candidates((0,0),(-500,-500,500,500),(1000,1000),100))),512)
        result, _ = self.run_fill([rectangle(0,0,100000,100000)],
                                  blocked=lambda p: True, candidate_limit=100)
        self.assertTrue(result.limited)
        self.assertEqual(result.examined,100)

    def test_time_limit_keeps_partial_result(self):
        ticks = iter([0,0,0,0,0,0,0,100])
        result, added = self.run_fill([rectangle(-100,-100,10000,10000)],
                                      clock=lambda: next(ticks,100))
        self.assertTrue(result.limited)
        self.assertEqual(result.added,len(added))

    def test_indexed_geometry_matches_full_edge_scan(self):
        from adaptive_fill import point_in_ring, segment_distance
        import random
        count = 4000
        ring = [(int(10000*math.cos(i*2*math.pi/count)),int(10000*math.sin(i*2*math.pi/count)))
                for i in range(count)]
        holes = [[(-500,-500),(500,-500),(500,500),(-500,500)]]
        region = Region(0,ring,holes)
        rng = random.Random(123)
        for _ in range(150):
            p = (rng.randrange(-11000,11000),rng.randrange(-11000,11000))
            radius = rng.randrange(1,500)
            expected = point_in_ring(p,ring) and not point_in_ring(p,holes[0]) and all(
                segment_distance(p,a,b)>=radius for r in [ring]+holes
                for a,b in zip(r,r[1:]+r[:1]))
            self.assertEqual(region.fits(p,radius),expected)

    def test_interior_disk_does_not_scan_all_polygon_edges(self):
        from unittest.mock import patch
        from adaptive_fill import segment_distance
        ring = [(int(10000*math.cos(i*2*math.pi/10000)),int(10000*math.sin(i*2*math.pi/10000)))
                for i in range(10000)]
        region = Region(0,ring,[])
        with patch('adaptive_fill.segment_distance',wraps=segment_distance) as distance:
            self.assertTrue(region.fits((0,0),100))
            self.assertLess(distance.call_count,10)

    def test_invalid_settings(self):
        for pitch, size, low, high in [((0,1000),100,.8,1.5), ((1000,1000),100,1.1,1.5),
                                       ((1000,1000),100,.8,.9), ((1000,1000),100,0,1.5),
                                       ((math.inf,1000),100,.8,1.5)]:
            with self.assertRaises(ValueError):
                validate_settings(pitch,size,low,high)


if __name__ == '__main__':
    unittest.main()
