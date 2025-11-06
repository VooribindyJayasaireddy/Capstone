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

def render_plan(coords, labels, doors=None, fixtures=None, furniture=None, windows=None, out_svg="floorplan_v2.svg", px_per_m=120):
    """
    Render a floorplan to SVG (and PNG if cairosvg available).

    coords: dict mapping room_id -> (x, y, w, h) in meters (plan-global coords)
    labels: dict mapping room_id -> display name
    doors: list of dicts like {"from_room":"a", "to_room":"b"}
    fixtures: list of {"room": id, "type": "...", "rect": (x,y,w,h)}  (coords are global)
    furniture: list of {"type": "...", "rect": (x,y,w,h)} (coords are global)
    windows: list of {"room_id": id, "wall": "north|south|east|west", "offset_m": float, "width_m": float}
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

    # rooms - single line walls, with subtle filled interior
    for rid, (x,y,w,h) in coords.items():
        sx, sy = mx(x), my(y)
        sw, sh = w*px_per_m, h*px_per_m
        # outer wall
        svg.append(_rect_svg(sx, sy, sw, sh, stroke_width=5, stroke_color="white", fill="#151515"))
        # label + size
        svg.append(_text_svg(sx + sw/2, sy + sh/2 - 6, labels.get(rid, rid), font_size=14, color="#cfcfcf"))
        svg.append(_text_svg(sx + sw/2, sy + sh - 12, f"{w:.1f}×{h:.1f}m", font_size=11, color="#bfbfbf"))

    # fixtures (small white blocks)
    if fixtures:
        for f in fixtures:
            rx,ry,rw,rh = f["rect"]
            sx, sy = mx(rx), my(ry)
            sw, sh = rw*px_per_m, rh*px_per_m
            svg.append(_rect_svg(sx, sy, sw, sh, stroke_width=1, stroke_color="white", fill="white"))
            svg.append(_text_svg(sx + sw/2, sy + sh/2, f.get("type",""), font_size=9, color="black"))

    # furniture (rounded / simple shapes)
    if furniture:
        for item in furniture:
            typ = item.get("type", "")
            rx,ry,rw,rh = item["rect"]
            sx, sy = mx(rx), my(ry)
            sw, sh = rw*px_per_m, rh*px_per_m
            if typ == "sofa":
                svg.append(f'<rect x="{sx}" y="{sy}" rx="6" ry="6" width="{sw}" height="{sh}" fill="#3a3a3a" stroke="#bfbfbf" stroke-width="1"/>')
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
            # A right touches B left
            if abs((ax+aw) - bx) < 1e-3:
                xwall = mx(ax+aw)
                ymid = my(max(ay,by) + min(ah,bh)/2)
                svg.append(_line_svg(xwall, ymid-15, xwall, ymid+15, stroke_width=8, color="#1c1c1c"))
                svg.append(_arc_svg(xwall+10, ymid, 22, 180, 270, stroke_width=3))
            elif abs(ax - (bx + bw)) < 1e-3:
                xwall = mx(ax)
                ymid = my(max(ay,by) + min(ah,bh)/2)
                svg.append(_line_svg(xwall, ymid-15, xwall, ymid+15, stroke_width=8, color="#1c1c1c"))
                svg.append(_arc_svg(xwall-10, ymid, 22, 0, 90, stroke_width=3))
            elif abs((ay+ah) - by) < 1e-3:
                ywall = my(ay+ah)
                xmid = mx(max(ax,bx) + min(aw,bw)/2)
                svg.append(_line_svg(xmid-15, ywall, xmid+15, ywall, stroke_width=8, color="#1c1c1c"))
                svg.append(_arc_svg(xmid, ywall+10, 22, 270, 360, stroke_width=3))
            elif abs(ay - (by + bh)) < 1e-3:
                ywall = my(ay)
                xmid = mx(max(ax,bx) + min(aw,bw)/2)
                svg.append(_line_svg(xmid-15, ywall, xmid+15, ywall, stroke_width=8, color="#1c1c1c"))
                svg.append(_arc_svg(xmid, ywall-10, 22, 90, 180, stroke_width=3))

    # draw windows (if provided)
    # windows: list of {"room_id":id, "wall":"north|south|east|west", "offset_m":float, "width_m":float}
    if windows:
        for w in windows:
            try:
                rid = w.get("room_id")
                if rid not in coords:
                    continue
                wall = w.get("wall", "north")
                offset = float(w.get("offset_m", 0.3))
                widthm = float(w.get("width_m", 1.0))
                rx, ry, rw, rh = coords[rid]

                # Determine coordinates for window endpoints (plan-global coords)
                if wall == "north":  # top wall (y = ry)
                    x1, y1 = rx + offset, ry
                    x2, y2 = x1 + widthm, ry
                elif wall == "south":  # bottom wall (y = ry + rh)
                    x1, y1 = rx + offset, ry + rh
                    x2, y2 = x1 + widthm, ry + rh
                elif wall == "west":  # left wall (x = rx)
                    x1, y1 = rx, ry + offset
                    x2, y2 = rx, y1 + widthm
                elif wall == "east":  # right wall (x = rx + rw)
                    x1, y1 = rx + rw, ry + offset
                    x2, y2 = x1, y1 + widthm
                else:
                    continue

                # draw a pale-blue core line for glass + white highlight
                svg.append(_line_svg(mx(x1), my(y1), mx(x2), my(y2), stroke_width=5, color="#2b8fbf"))
                svg.append(_line_svg(mx(x1), my(y1), mx(x2), my(y2), stroke_width=1, color="#ffffff"))
            except Exception:
                # ignore malformed window entries
                continue

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
    # optionally export PNG using cairosvg if installed
    try:
        out_png = out_svg.replace(".svg", ".png")
        cairosvg.svg2png(bytestring=out.encode("utf-8"), write_to=out_png, output_width=W, output_height=H)
        print("Saved PNG:", out_png)
    except Exception as e:
        print("PNG export failed (cairosvg). Error:", e)
