# layout_gen.py
from typing import Dict, Tuple, Any
from shapely.geometry import box
import networkx as nx
import math

DEFAULT_SIZES = {
    "Living Room": (5.0, 4.0),
    "Kitchen": (3.0, 3.0),
    "Master Bedroom": (4.0, 4.0),
    "Kids Room": (3.5, 3.0),
    "Guest Room": (3.5, 3.0),
    "Bathroom": (1.8, 2.4),
    "Balcony": (2.0, 1.5)
}

def _size_for(room):
    # prefer explicit size_m then min_ then default
    if getattr(room, "size_m", None):
        sm = room.size_m
        if (sm.width_m or sm.height_m):
            w = sm.width_m or DEFAULT_SIZES.get(room.type, (3.5,3.0))[0]
            h = sm.height_m or DEFAULT_SIZES.get(room.type, (3.5,3.0))[1]
            return (w,h)
    if getattr(room, "min_width_m", None) and getattr(room, "min_height_m", None):
        return (room.min_width_m, room.min_height_m)
    return DEFAULT_SIZES.get(room.type, (3.5,3.0))

def _bbox_area(coords):
    xs = [x for (x,y,w,h) in coords.values()] + [x+w for (x,y,w,h) in coords.values()]
    ys = [y for (x,y,w,h) in coords.values()] + [y+h for (x,y,w,h) in coords.values()]
    return (max(xs)-min(xs)) * (max(ys)-min(ys))

def compact_snapping_layout(plan) -> Dict[str, Tuple[float,float,float,float]]:
    """
    Returns: room_id -> (x, y, w, h)
    Places rooms so they share walls where adjacency exists.
    """
    # build adjacency
    G = nx.Graph()
    for r in plan.rooms:
        G.add_node(r.id, room=r)
    for r in plan.rooms:
        for adj in (r.preferred_adjacent or []):
            # match by type substring or id substring
            for rr in plan.rooms:
                if adj.lower() in rr.type.lower() or adj.lower() in rr.id.lower():
                    G.add_edge(r.id, rr.id)
    if plan.doors:
        for d in plan.doors:
            a = d.from_room if hasattr(d, "from_room") else d.get("from")
            b = d.to_room if hasattr(d, "to_room") else d.get("to")
            if a and b:
                if a in G.nodes and b in G.nodes:
                    G.add_edge(a, b)

    # choose root (living) or largest area
    root = None
    for r in plan.rooms:
        if "living" in r.type.lower():
            root = r.id; break
    if root is None:
        # choose largest default area
        root = max(plan.rooms, key=lambda r: _size_for(r)[0]*_size_for(r)[1]).id

    coords = {}  # id -> (x,y,w,h)
    placed_shapes = {}  # id -> shapely box

    def place_initial(rid):
        room = next(r for r in plan.rooms if r.id==rid)
        w,h = _size_for(room)
        coords[rid] = (0.0, 0.0, w, h)
        placed_shapes[rid] = box(0.0, 0.0, w, h)

    place_initial(root)

    # helper to check overlap excluding touching boundaries
    def overlaps(candidate_box):
        for s in placed_shapes.values():
            # allow touching but not intersecting with positive area
            if candidate_box.intersects(s) and candidate_box.intersection(s).area > 1e-6:
                return True
        return False

    # searches placements on 4 sides of anchor and optionally slides along edge
    def find_best_placement_for(node, anchor_id):
        room = next(r for r in plan.rooms if r.id==node)
        w,h = _size_for(room)
        ax,ay,aw,ah = coords[anchor_id]
        candidates = []

        # candidate positions: right, left, top, bottom (touching)
        cand_positions = [
            ("right", ax+aw+0.0, ay, w, h),
            ("left", ax - w - 0.0, ay, w, h),
            ("top", ax, ay - h - 0.0, w, h),
            ("bottom", ax, ay+ah+0.0, w, h)
        ]

        for side, x0, y0, cw, ch in cand_positions:
            # try several slide offsets along the shared edge (to find a non-overlapping fit)
            slide_steps = max(1, int((aw if side in ("right","left") else ah) / 0.5))
            for s in range(slide_steps):
                if side in ("right","left"):
                    # slide vertically along anchor edge
                    if slide_steps == 1:
                        y = y0
                    else:
                        # try offsets centered then +/- increments
                        center = ay + (ah-ch)/2
                        offset = (s - slide_steps//2) * 0.5
                        y = center + offset
                    x = x0
                else:
                    # top/bottom: slide horizontally
                    if slide_steps == 1:
                        x = x0
                    else:
                        center = ax + (aw-cw)/2
                        offset = (s - slide_steps//2) * 0.5
                        x = center + offset
                    y = y0

                candidate = box(x, y, x + cw, y + ch)
                if not overlaps(candidate):
                    # compute bounding box area if placed, to prefer compact fits
                    tmp_coords = dict(coords)
                    tmp_coords[node] = (x, y, cw, ch)
                    area = _bbox_area(tmp_coords)
                    candidates.append((area, (x, y, cw, ch)))
        if not candidates:
            return None
        # choose minimal bounding area
        candidates.sort(key=lambda t: t[0])
        return candidates[0][1]

    # BFS order placement: try to place neighbors close to an already-placed node
    bfs_nodes = list(nx.bfs_tree(G, root))
    for node in bfs_nodes:
        if node in coords:
            continue
        # find placed neighbors to anchor to
        anchors = [n for n in G.neighbors(node) if n in coords]
        placed = False
        # prefer anchors with bigger shared adjacency (degree)
        anchors.sort(key=lambda a: -G.degree[a])
        for a in anchors:
            place = find_best_placement_for(node, a)
            if place:
                x,y,w,h = place
                coords[node] = (x,y,w,h)
                placed_shapes[node] = box(x,y,x+w,y+h)
                placed = True
                break
        if not placed:
            # fallback: place near the overall bounding box to the right
            xs = [c[0]+c[2] for c in coords.values()]
            maxx = max(xs)
            w,h = _size_for(next(r for r in plan.rooms if r.id==node))
            x = maxx + 0.5
            y = 0.0
            coords[node] = (x,y,w,h)
            placed_shapes[node] = box(x,y,x+w,y+h)

    # final small packing pass: try to shift rooms closer to top-left to reduce whitespace
    def bounding():
        xs = [x for x,y,w,h in coords.values()] + [x+w for x,y,w,h in coords.values()]
        ys = [y for x,y,w,h in coords.values()] + [y+h for x,y,w,h in coords.values()]
        return min(xs), min(ys), max(xs), max(ys)

    # shift everything so min is at 0,0
    minx, miny, _, _ = bounding()
    for k,v in list(coords.items()):
        x,y,w,h = v
        coords[k] = (x - minx + 0.2, y - miny + 0.2, w, h)

    return coords
