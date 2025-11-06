
import sys
import json
import traceback

# try imports
try:
    from gemini_extract import extract_structured_plan
except Exception:
    extract_structured_plan = None

try:
    from ai_placement import suggest_placements
except Exception:
    suggest_placements = None

from layout_gen import compact_snapping_layout
from layout_optimize import optimize_layout
from render_svg_v2 import render_plan

OUT_SVG = "out_floorplan_ai.svg"
OUT_PNG = "out_floorplan_ai.png"

# A simple lightweight Room class used for the hard-coded fallback plan
class SimpleRoom:
    def __init__(self, id, type, min_width_m=None, min_height_m=None, size_m=None, preferred_adjacent=None, fixtures=None):
        self.id = id
        self.type = type
        self.min_width_m = min_width_m
        self.min_height_m = min_height_m
        self.size_m = size_m  # can be a SimpleSize or None
        self.preferred_adjacent = preferred_adjacent or []
        self.fixtures = fixtures or []

class SimpleSize:
    def __init__(self, width_m=None, height_m=None):
        self.width_m = width_m
        self.height_m = height_m

class SimplePlan:
    def __init__(self, rooms, doors=None, notes=None):
        self.rooms = rooms
        self.doors = doors or []
        self.notes = notes

def hardcoded_plan():
    """Return a SimplePlan useful to test layout + renderer without Gemini."""
    rooms = [
        SimpleRoom(id="living", type="Living Room", size_m=SimpleSize(5.0,4.0), preferred_adjacent=["kitchen","master","guest","balcony"]),
        SimpleRoom(id="kitchen", type="Kitchen", size_m=SimpleSize(3.0,3.0), preferred_adjacent=["living"], fixtures=["stove","sink"]),
        SimpleRoom(id="master", type="Master Bedroom", size_m=SimpleSize(4.0,4.0), preferred_adjacent=["living"], fixtures=[]),
        SimpleRoom(id="guest", type="Guest Room", size_m=SimpleSize(3.5,3.0), preferred_adjacent=["living","kids"]),
        SimpleRoom(id="kids", type="Kids Room", size_m=SimpleSize(3.5,3.0), preferred_adjacent=["guest"]),
        SimpleRoom(id="bath1", type="Bathroom", size_m=SimpleSize(2.8,3.0), preferred_adjacent=["master"], fixtures=["toilet","sink","shower"]),
        SimpleRoom(id="balcony", type="Balcony", size_m=SimpleSize(2.0,1.5), preferred_adjacent=["living"])
    ]
    # doors: list of dicts matching earlier format
    doors = [
        {"from_room":"living","to_room":"kitchen"},
        {"from_room":"living","to_room":"master"},
        {"from_room":"living","to_room":"guest"},
        {"from_room":"guest","to_room":"kids"},
        {"from_room":"master","to_room":"bath1"},
        {"from_room":"living","to_room":"balcony"}
    ]
    return SimplePlan(rooms=rooms, doors=doors, notes="Hard-coded fallback plan for testing")

def safe_pretty_print(plan):
    """Print Pydantic model or our SimplePlan cleanly."""
    try:
        # Pydantic v2
        if hasattr(plan, "model_dump_json"):
            print(plan.model_dump_json(indent=2))
            return
        # Pydantic v1 or models: fallback to model_dump
        if hasattr(plan, "model_dump"):
            dd = plan.model_dump()
            print(json.dumps(dd, indent=2))
            return
    except Exception:
        pass

    # If our SimplePlan
    if isinstance(plan, SimplePlan):
        out = {
            "rooms": [
                {
                    "id": r.id, "type": r.type,
                    "size_m": {"width_m": getattr(r.size_m, "width_m", None), "height_m": getattr(r.size_m, "height_m", None)} if r.size_m else None,
                    "preferred_adjacent": r.preferred_adjacent,
                    "fixtures": r.fixtures
                } for r in plan.rooms
            ],
            "doors": plan.doors,
            "notes": plan.notes
        }
        print(json.dumps(out, indent=2))
        return

    # final fallback
    try:
        print(json.dumps(plan, indent=2))
    except Exception:
        print(repr(plan))

def build_adjacency_pairs(plan):
    pairs = []
    # handle Pydantic model or SimplePlan
    rooms = plan.rooms
    for r in rooms:
        prefs = getattr(r, "preferred_adjacent", []) or []
        for adj in prefs:
            # match by substring on type or id
            for rr in rooms:
                if adj is None: continue
                if adj.lower() in getattr(rr, "type", "").lower() or adj.lower() in getattr(rr, "id", "").lower():
                    pairs.append((r.id, rr.id))
    # also add doors
    for d in getattr(plan, "doors", []) or []:
        if isinstance(d, dict):
            a = d.get("from_room") or d.get("from")
            b = d.get("to_room") or d.get("to")
        else:
            # Pydantic object or similar
            a = getattr(d, "from_room", None) or (d.get("from") if hasattr(d, "get") else None)
            b = getattr(d, "to_room", None) or (d.get("to") if hasattr(d, "get") else None)
        if a and b:
            pairs.append((a, b))
    # dedupe
    pairs = list(dict.fromkeys(pairs))
    return pairs

def main(prompt=None, use_gemini=True):
    # Decide prompt
    if prompt is None:
        prompt = (
            "Design a 3BHK layout: Living room 5x4m, kitchen 3x3m to the right of living room with stove and sink, "
            "master bedroom 4x4m below the living room with attached bathroom 2.8x3.0m, guest room 3.5x3.0m left of the living room, "
            "kids room 3.5x3.0m adjacent to guest room, plus a small balcony 2.0x1.5m attached to living room."
        )

    print("PROMPT:\n", prompt, "\n")

    plan = None
    if use_gemini and extract_structured_plan:
        print("1) Attempting to extract structured plan from Gemini...")
        try:
            plan = extract_structured_plan(prompt)
            print("-> Gemini extraction succeeded. Extracted plan:")
            safe_pretty_print(plan)
        except Exception as e:
            print("Gemini extraction failed (falling back). Error:")
            traceback.print_exc()
            plan = None
    else:
        if not extract_structured_plan:
            print("Gemini extractor not available in this environment; using fallback plan.")
        else:
            print("Skipping Gemini extraction (using fallback).")

    if plan is None:
        plan = hardcoded_plan()
        print("Using hard-coded fallback plan:")
        safe_pretty_print(plan)

    # 2) compact snapping layout
    print("\n2) Generating initial compact snapping layout...")
    coords_initial = compact_snapping_layout(plan)
    print("Initial coords (meters):")
    for k,(x,y,w,h) in coords_initial.items():
        print(f"  {k}: x={x:.2f}, y={y:.2f}, w={w:.2f}, h={h:.2f}")

    # 3) optimize
    print("\n3) Running layout optimizer (this may take a few seconds)...")
    adjacency_pairs = build_adjacency_pairs(plan)
    coords_opt = optimize_layout(coords_initial, plan, adjacency_pairs=adjacency_pairs, iterations=2500, seed=123)
    print("Optimized coords:")
    for k,(x,y,w,h) in coords_opt.items():
        print(f"  {k}: x={x:.2f}, y={y:.2f}, w={w:.2f}, h={h:.2f}")

    # 4) prepare doors list
    doors = []
    for d in getattr(plan, "doors", []) or []:
        if isinstance(d, dict):
            doors.append(d)
        else:
            # pydantic object or similar
            a = getattr(d, "from_room", None) or d.get("from") if hasattr(d, "get") else None
            b = getattr(d, "to_room", None) or d.get("to") if hasattr(d, "get") else None
            if a and b:
                doors.append({"from_room": a, "to_room": b})

    # 5) AI furniture and window placement suggestions
    furniture = []
    windows = []
    if suggest_placements:
        print("\n5) Getting AI furniture and window placement suggestions...")
        try:
            # Create a wrapper plan with coordinates (without modifying Pydantic objects)
            class RoomWithCoords:
                """Wrapper that adds coords to a room without modifying the original object."""
                def __init__(self, room, coords_tuple):
                    self._room = room
                    self.coords = coords_tuple
                def __getattr__(self, name):
                    return getattr(self._room, name)
            
            class PlanWithCoords:
                """Wrapper plan that includes rooms with coordinates."""
                def __init__(self, plan, coords_dict):
                    self.rooms = [RoomWithCoords(r, coords_dict.get(r.id)) for r in plan.rooms]
                    # Convert doors to JSON-serializable format
                    doors_raw = getattr(plan, "doors", []) or []
                    self.doors = []
                    for d in doors_raw:
                        if isinstance(d, dict):
                            self.doors.append(d)
                        else:
                            # Pydantic object - convert to dict
                            a = getattr(d, "from_room", None) or (d.get("from") if hasattr(d, "get") else None)
                            b = getattr(d, "to_room", None) or (d.get("to") if hasattr(d, "get") else None)
                            if a and b:
                                door_dict = {"from_room": a, "to_room": b}
                                if hasattr(d, "count"):
                                    door_dict["count"] = getattr(d, "count", 1)
                                self.doors.append(door_dict)
                    self.notes = getattr(plan, "notes", None)
            
            plan_with_coords = PlanWithCoords(plan, coords_opt)
            placements = suggest_placements(plan_with_coords)
            ai_furniture = placements.get("furniture", [])
            windows = placements.get("windows", [])
            
            # Convert furniture from room-relative to absolute coordinates
            # AI returns rect as [x,y,w,h] where x,y are relative to room origin
            for item in ai_furniture:
                room_id = item.get("room_id")
                if room_id and room_id in coords_opt:
                    rx, ry, rw, rh = coords_opt[room_id]
                    rel_x, rel_y, rel_w, rel_h = item.get("rect", [0,0,0,0])
                    # Convert to absolute coordinates by adding room position
                    abs_x = rx + rel_x
                    abs_y = ry + rel_y
                    furniture.append({
                        "type": item.get("type", "furniture"),
                        "rect": (abs_x, abs_y, rel_w, rel_h)
                    })
            print(f"  -> AI placed {len(furniture)} furniture items and {len(windows)} windows")
        except Exception as e:
            print(f"  -> AI placement failed, using fallback: {e}")
            traceback.print_exc()
            # Fallback to simple placement
            furniture = []
            for r in plan.rooms:
                if "living" in getattr(r, "type", "").lower() and r.id in coords_opt:
                    lx,ly,lw,lh = coords_opt[r.id]
                    furniture.append({"type":"sofa", "rect": (lx + (lw-1.6)/2, ly + (lh-0.8)/2, 1.6, 0.8)})
                    furniture.append({"type":"table", "rect": (lx + (lw-0.9)/2, ly + (lh-0.6)/2 + 0.2, 0.9, 0.6)})
                    break
    else:
        print("\n5) AI placement not available, using simple fallback...")
        # Simple fallback
        for r in plan.rooms:
            if "living" in getattr(r, "type", "").lower() and r.id in coords_opt:
                lx,ly,lw,lh = coords_opt[r.id]
                furniture.append({"type":"sofa", "rect": (lx + (lw-1.6)/2, ly + (lh-0.8)/2, 1.6, 0.8)})
                furniture.append({"type":"table", "rect": (lx + (lw-0.9)/2, ly + (lh-0.6)/2 + 0.2, 0.9, 0.6)})
                break

    # 6) render using render_svg_v2.render_plan
    print("\n6) Rendering final plan to SVG/PNG...")
    labels = {r.id: r.type for r in plan.rooms}
    try:
        render_plan(coords_opt, labels, doors=doors, fixtures=None, furniture=furniture, windows=windows, out_svg=OUT_SVG, px_per_m=130)
        print(f"\nSaved: {OUT_SVG} (PNG: {OUT_PNG} if cairosvg installed)")
    except Exception as e:
        print("Rendering failed. Error:")
        traceback.print_exc()

if __name__ == "__main__":
    # allow passing prompt via command line
    if len(sys.argv) > 1:
        p = " ".join(sys.argv[1:])
        main(prompt=p, use_gemini=True)
    else:
        main(use_gemini=True)
