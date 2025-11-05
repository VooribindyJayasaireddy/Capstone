# render_svg_v2.py
from xml.sax.saxutils import escape
import cairosvg
import math

def _rect_svg(x, y, w, h, stroke_width=2, stroke_color="white", fill="none"):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" stroke="{stroke_color}" stroke-width="{stroke_width}" stroke-linejoin="miter"/>'

def _text_svg(x, y, txt, font_size=12, color="white"):
    return f'<text x="{x}" y="{y}" fill="{color}" font-size="{font_size}" text-anchor="middle" dominant-baseline="middle">{escape(txt)}</text>'

def _line_svg(x1,y1,x2,y2, stroke_width=1, color="white"):
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{stroke_width}" stroke-linecap="butt"/>'

def _arc_svg(cx, cy, r, start_deg, end_deg, stroke_width=2, color="white"):
    start_rad = math.radians(start_deg)
    end_rad = math.radians(end_deg)
    x1 = cx + r * math.cos(start_rad)
    y1 = cy + r * math.sin(start_rad)
    x2 = cx + r * math.cos(end_rad)
    y2 = cy + r * math.sin(end_rad)
    large = 1 if abs(end_deg - start_deg) > 180 else 0
    return f'<path d="M {x1:.2f} {y1:.2f} A {r:.2f} {r:.2f} 0 {large} 1 {x2:.2f} {y2:.2f}" stroke="{color}" stroke-width="{stroke_width}" fill="none" stroke-linecap="round"/>'

def render_plan(coords, labels, doors=None, fixtures=None, furniture=None, out_svg="floorplan_v2.svg", px_per_m=120):
    """
    Render a floorplan to SVG (and PNG if cairosvg available).

    coords: dict mapping room_id -> (x, y, w, h) in meters
    labels: dict mapping room_id -> display name
    doors: list of dicts like {"from_room": "a", "to_room": "b"}
    fixtures: list of {"room": id, "type": "...", "rect": (x,y,w,h)}
    furniture: list of {"type": "sofa"/"table", "rect": (x,y,w,h)}
    """
    minx = min(x for x,y,w,h in coords.values())
    miny = min(y for x,y,w,h in coords.values())
    maxx = max(x+w for x,y,w,h in coords.values())
    maxy = max(y+h for x,y,w,h in coords.values())
    margin = 0.5
    Wm = (maxx - minx) + 2*margin
    Hm = (maxy - miny) + 2*margin
    W = int(Wm * px_per_m)
    H = int(Hm * px_per_m)

    def mx(x): return (x - minx + margin) * px_per_m
    def my(y): return (y - miny + margin) * px_per_m

    svg = []
    svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">')
    svg.append(f'<rect width="100%" height="100%" fill="#1c1c1c"/>')
    
    # floor pattern definition
    svg.append('<defs><pattern id="floor_pattern" width="8" height="8" patternUnits="userSpaceOnUse"><path d="M0,0 L8,8 M8,0 L0,8" stroke="#202020" stroke-width="0.5"/></pattern></defs>')

    # furniture icons based on room type (relative coordinates in meters)
    furniture_icons = {
        "Living Room": [{"type":"sofa","rect":(0.5,1.0,1.8,0.8)}, {"type":"table","rect":(2.6,1.2,1.2,0.6)}],
        "Kitchen": [{"type":"stove","rect":(0.3,0.3,0.8,0.5)}, {"type":"sink","rect":(1.3,0.3,0.8,0.5)}],
        "Bathroom": [{"type":"toilet","rect":(0.3,0.3,0.7,0.6)}, {"type":"shower","rect":(1.2,0.3,0.7,0.7)}],
    }
    
    # rooms - walls with thickness (outer + inner)
    wall_thickness = 0.12  # meters
    for rid, (x,y,w,h) in coords.items():
        sx, sy = mx(x), my(y)
        sw, sh = w*px_per_m, h*px_per_m
        # outer wall
        svg.append(_rect_svg(sx, sy, sw, sh, stroke_width=8, stroke_color="#f8f8f8", fill="#141414"))
        # inner wall
        svg.append(_rect_svg(sx + wall_thickness*px_per_m,
                             sy + wall_thickness*px_per_m,
                             sw - 2*wall_thickness*px_per_m,
                             sh - 2*wall_thickness*px_per_m,
                             stroke_width=2, stroke_color="#1c1c1c", fill="#1c1c1c"))
        svg.append(_text_svg(sx + sw/2, sy + sh/2 - 6, labels.get(rid, rid), font_size=14, color="#cfcfcf"))
        svg.append(_text_svg(sx + sw/2, sy + sh - 12, f"{w:.1f}×{h:.1f}m", font_size=11, color="#bfbfbf"))
        
        # render furniture icons if room type matches
        if labels.get(rid) in furniture_icons:
            for item in furniture_icons[labels[rid]]:
                rx,ry,rw,rh = item["rect"]
                sx_item, sy_item = mx(x+rx), my(y+ry)
                sw_item, sh_item = rw*px_per_m, rh*px_per_m
                svg.append(_rect_svg(sx_item, sy_item, sw_item, sh_item, stroke_width=1, stroke_color="#bfbfbf", fill="#2b2b2b"))

    # fixtures (white boxes)
    if fixtures:
        for f in fixtures:
            rx,ry,rw,rh = f["rect"]
            sx, sy = mx(rx), my(ry)
            sw, sh = rw*px_per_m, rh*px_per_m
            svg.append(_rect_svg(sx, sy, sw, sh, stroke_width=1, stroke_color="white", fill="white"))
            svg.append(_text_svg(sx + sw/2, sy + sh/2, f["type"], font_size=9, color="black"))

    # furniture simple shapes
    if furniture:
        for item in furniture:
            typ = item.get("type")
            rx,ry,rw,rh = item["rect"]
            sx, sy = mx(rx), my(ry)
            sw, sh = rw*px_per_m, rh*px_per_m
            if typ == "sofa":
                svg.append(f'<rect x="{sx}" y="{sy}" rx="6" ry="6" width="{sw}" height="{sh}" fill="#3a3a3a" stroke="#bfbfbf" stroke-width="1"/>')
            elif typ == "table":
                svg.append(_rect_svg(sx, sy, sw, sh, stroke_width=1, stroke_color="#bfbfbf", fill="#2b2b2b"))
            else:
                svg.append(_rect_svg(sx, sy, sw, sh, stroke_width=1, stroke_color="#bfbfbf", fill="#2b2b2b"))

    # doors: draw gap + swing arc on shared walls
    if doors:
        for d in doors:
            a = coords.get(d.get("from_room") or d.get("from"))
            b = coords.get(d.get("to_room") or d.get("to"))
            if not a or not b:
                continue
            ax,ay,aw,ah = a; bx,by,bw,bh = b
            
            # find shared edge with improved tolerance
            if abs((ax+aw) - bx) < 0.1:  # right of A touches left of B
                door_y = my(ay + 0.2*ah)  # offset door 20% from top
                xwall = mx(ax+aw)
                svg.append(_line_svg(xwall, door_y-12, xwall, door_y+12, stroke_width=6, color="#1c1c1c"))
                svg.append(_arc_svg(xwall+10, door_y, 22, 180, 270, stroke_width=3))
            elif abs(ax - (bx + bw)) < 0.1:  # left of A touches right of B
                door_y = my(ay + 0.2*ah)
                xwall = mx(ax)
                svg.append(_line_svg(xwall, door_y-12, xwall, door_y+12, stroke_width=6, color="#1c1c1c"))
                svg.append(_arc_svg(xwall-10, door_y, 22, 0, 90, stroke_width=3))
            elif abs((ay+ah) - by) < 0.1:  # bottom of A touches top of B
                door_x = mx(ax + 0.2*aw)
                ywall = my(ay+ah)
                svg.append(_line_svg(door_x-12, ywall, door_x+12, ywall, stroke_width=6, color="#1c1c1c"))
                svg.append(_arc_svg(door_x, ywall+10, 22, 270, 360, stroke_width=3))
            elif abs(ay - (by + bh)) < 0.1:  # top of A touches bottom of B
                door_x = mx(ax + 0.2*aw)
                ywall = my(ay)
                svg.append(_line_svg(door_x-12, ywall, door_x+12, ywall, stroke_width=6, color="#1c1c1c"))
                svg.append(_arc_svg(door_x, ywall-10, 22, 90, 180, stroke_width=3))

    # exterior dimension ticks (top and left)
    minx_m = min(x for x,y,w,h in coords.values())
    miny_m = min(y for x,y,w,h in coords.values())
    maxx_m = max(x+w for x,y,w,h in coords.values())
    maxy_m = max(y+h for x,y,w,h in coords.values())

    top_x1 = mx(minx_m)
    top_x2 = mx(maxx_m)
    top_y = my(miny_m) - 20
    svg.append(_line_svg(top_x1, top_y, top_x2, top_y, stroke_width=1, color="#909090"))
    svg.append(_line_svg(top_x1, top_y-6, top_x1, top_y+6, stroke_width=1, color="#909090"))
    svg.append(_line_svg(top_x2, top_y-6, top_x2, top_y+6, stroke_width=1, color="#909090"))
    svg.append(_text_svg((top_x1+top_x2)/2, top_y-10, f"{(maxx_m-minx_m):.2f} m", font_size=12, color="#bfbfbf"))

    left_x = mx(minx_m) - 30
    left_y1 = my(miny_m)
    left_y2 = my(maxy_m)
    svg.append(_line_svg(left_x, left_y1, left_x, left_y2, stroke_width=1, color="#909090"))
    svg.append(_line_svg(left_x-6, left_y1, left_x+6, left_y1, stroke_width=1, color="#909090"))
    svg.append(_line_svg(left_x-6, left_y2, left_x+6, left_y2, stroke_width=1, color="#909090"))
    svg.append(_text_svg(left_x-12, (left_y1+left_y2)/2, f"{(maxy_m-miny_m):.2f} m", font_size=12, color="#bfbfbf"))

    svg.append('</svg>')
    out = "\n".join(svg)
    with open(out_svg, "w", encoding="utf-8") as f:
        f.write(out)
    print("Saved:", out_svg)
    # optionally export PNG
    try:
        out_png = out_svg.replace(".svg", ".png")
        cairosvg.svg2png(bytestring=out.encode("utf-8"), write_to=out_png, output_width=W, output_height=H)
        print("Saved PNG:", out_png)
    except Exception as e:
        print("PNG export failed (cairosvg). Error:", e)

# optional quick test when running this file directly
if __name__ == "__main__":
    # tiny test plan
    coords = {
        "living": (0.2,0.2,5.0,4.0),
        "kitchen": (5.4,0.2,3.0,3.0),
        "master": (0.2,4.6,4.0,4.0)
    }
    labels = {"living":"Living Room","kitchen":"Kitchen","master":"Master Bedroom"}
    render_plan(coords, labels, doors=[{"from_room":"living","to_room":"kitchen"}], furniture=[{"type":"sofa","rect":(1.8,1.6,1.6,0.8)}], out_svg="test_render_v2.svg")
