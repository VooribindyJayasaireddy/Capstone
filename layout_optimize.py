# layout_optimize.py
import random
import math
from copy import deepcopy
from shapely.geometry import box
from shapely.affinity import translate

def _bbox(coords):
    xs = [x for x,y,w,h in coords.values()] + [x+w for x,y,w,h in coords.values()]
    ys = [y for x,y,w,h in coords.values()] + [y+h for x,y,w,h in coords.values()]
    return min(xs), min(ys), max(xs), max(ys)

def bbox_area(coords):
    minx, miny, maxx, maxy = _bbox(coords)
    return max(0.0001, (maxx - minx) * (maxy - miny))

def total_overlap_area(coords):
    ids = list(coords.keys())
    total = 0.0
    for i in range(len(ids)):
        a = ids[i]
        ax,ay,aw,ah = coords[a]
        A = box(ax,ay,ax+aw,ay+ah)
        for j in range(i+1, len(ids)):
            b = ids[j]
            bx,by,bw,bh = coords[b]
            B = box(bx,by,bx+bw,by+bh)
            inter = A.intersection(B).area
            total += inter
    return total

def adjacency_distance_cost(coords, adjacency_pairs):
    # adjacency_pairs: list of (a,b) pairs that should be adjacent
    # cost = sum of center distances for pairs (encourage small)
    total = 0.0
    for a,b in adjacency_pairs:
        if a not in coords or b not in coords:
            continue
        ax,ay,aw,ah = coords[a]
        bx,by,bw,bh = coords[b]
        acx,acy = ax + aw/2.0, ay + ah/2.0
        bcx,bcy = bx + bw/2.0, by + bh/2.0
        d = math.hypot(acx-bcx, acy-bcy)
        total += d
    return total

def aspect_ratio_penalty(coords, ideal_ratio=1.5):
    # penalize rooms with extreme aspect ratio
    penalty = 0.0
    for x,y,w,h in coords.values():
        r = max(w/h if h>0 else 1e6, h/w if w>0 else 1e6)
        penalty += max(0, (r - ideal_ratio))
    return penalty

def cost_fn(coords, adjacency_pairs, weights):
    # weights: dict with overlap_w, adj_w, area_w, aspect_w
    overlap = total_overlap_area(coords)
    adj_dist = adjacency_distance_cost(coords, adjacency_pairs)
    area = bbox_area(coords)
    aspect = aspect_ratio_penalty(coords)
    return weights["overlap_w"] * overlap + weights["adj_w"] * adj_dist + weights["area_w"] * area + weights["aspect_w"] * aspect

def _random_neighbor(coords, room_ids, room_sizes, max_shift=0.6):
    # returns new coords copy with one small change:
    # - small shift of a room (dx,dy) or
    # - snap to side of adjacent room (if available)
    nc = deepcopy(coords)
    # pick random room
    rid = random.choice(room_ids)
    x,y,w,h = nc[rid]
    # random small move
    dx = random.uniform(-max_shift, max_shift)
    dy = random.uniform(-max_shift, max_shift)
    nc[rid] = (x + dx, y + dy, w, h)
    return nc

def optimize_layout(initial_coords, plan, adjacency_pairs=None, iterations=2000, seed=42):
    """
    initial_coords: dict room_id -> (x,y,w,h)
    plan: FloorPlanSpec (Pydantic) to get room ids & maybe constraints
    adjacency_pairs: list of (id1, id2) to encourage adjacency (if None, infer from plan.preferred_adjacent)
    Returns optimized coords dict.
    """
    random.seed(seed)
    current = deepcopy(initial_coords)
    room_ids = list(current.keys())
    room_sizes = {rid: (current[rid][2], current[rid][3]) for rid in room_ids}

    if adjacency_pairs is None:
        adjacency_pairs = []
        for r in plan.rooms:
            for adj in (r.preferred_adjacent or []):
                # find matching id(s)
                for rr in plan.rooms:
                    if adj.lower() in rr.type.lower() or adj.lower() in rr.id.lower():
                        adjacency_pairs.append((r.id, rr.id))

    # weights (tuneable)
    weights = {"overlap_w": 100.0, "adj_w": 0.2, "area_w": 1.0, "aspect_w": 0.5}

    current_cost = cost_fn(current, adjacency_pairs, weights)
    best = deepcopy(current)
    best_cost = current_cost

    T0 = 1.0
    for it in range(iterations):
        T = T0 * (1 - it/iterations)  # linear cooling
        candidate = _random_neighbor(current, room_ids, room_sizes, max_shift=0.8)
        cand_cost = cost_fn(candidate, adjacency_pairs, weights)
        delta = cand_cost - current_cost
        # accept if better or with small probability
        if delta < 0 or random.random() < math.exp(-delta / max(1e-6, T)):
            current = candidate
            current_cost = cand_cost
            if cand_cost < best_cost:
                best = deepcopy(candidate)
                best_cost = cand_cost
        # occasionally try a stronger move: snap a room next to a neighbor
        if it % 200 == 0:
            # try snapping small rooms to touch nearest neighbor
            for rid in room_ids:
                # find nearest placed neighbor center
                ax,ay,aw,ah = current[rid]
                acx,acy = ax + aw/2.0, ay + ah/2.0
                best_snap = None
                best_snap_cost = None
                for nid in room_ids:
                    if nid == rid: continue
                    bx,by,bw,bh = current[nid]
                    # try positions: left,right,top,bottom touching
                    test_positions = [
                        (bx - aw, by),        # left
                        (bx + bw, by),        # right
                        (bx, by - ah),        # top
                        (bx, by + bh),        # bottom
                    ]
                    for tx,ty in test_positions:
                        temp = deepcopy(current)
                        temp[rid] = (tx, ty, aw, ah)
                        c = cost_fn(temp, adjacency_pairs, weights)
                        if best_snap_cost is None or c < best_snap_cost:
                            best_snap_cost = c
                            best_snap = (tx, ty)
                if best_snap and best_snap_cost < current_cost:
                    current[rid] = (best_snap[0], best_snap[1], aw, ah)
                    current_cost = best_snap_cost
                    if current_cost < best_cost:
                        best = deepcopy(current)
                        best_cost = current_cost

    # final normalization: shift everything so min corner is at 0.2,0.2
    minx, miny, _, _ = _bbox(best)
    shiftx = -minx + 0.2
    shifty = -miny + 0.2
    for k,v in list(best.items()):
        x,y,w,h = v
        best[k] = (x + shiftx, y + shifty, w, h)

    return best
