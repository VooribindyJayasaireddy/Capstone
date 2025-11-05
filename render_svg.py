# render_svg.py
from xml.sax.saxutils import escape
import cairosvg
import math

def _rect_svg(x, y, w, h, stroke_width=2, stroke_color="white", fill="none"):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" stroke="{stroke_color}" stroke-width="{stroke_width}" stroke-linejoin="miter"/>'

def _text_svg(x, y, txt, font_size=12, color="white"):
    return f'<text x="{x}" y="{y}" fill="{color}" font-size="{font_size}" text-anchor="middle" dominant-baseline="middle">{escape(txt)}</text>'

def _arc_svg(cx, cy, r, start_deg, end_deg, stroke_width=3, color="white"):
    # draw arc path using SVG arc command
    start_rad = math.radians(start_deg)
    end_rad = math.radians(end_deg)
    x1 = cx + r * math.cos(start_rad)
    y1 = cy + r * math.sin(start_rad)
    x2 = cx + r * math.cos(end_rad)
    y2 = cy + r * math.sin(end_rad)
    large = 1 if abs(end_deg - start_deg) > 180 else 0
    return f'<path d="M {x1:.2f} {y1:.2f} A {r:.2f} {r:.2f} 0 {large} 1 {x2:.2f} {y2:.2f}" stroke="{color}" stroke-width="{stroke_width}" fill="none"/>'

def render_svg(coords: dict, labels: dict, doors: list = None, fixtures: list = None, out_svg="floorplan.svg", px_per_m=100):
    # coords: id -> (x,y,w,h) in meters
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
    svg.append(f'<rect width="100%" height="100%" fill="#181818"/>')

    # draw rooms with double-line wall (outer thicker stroke then inner)
    for rid, (x,y,w,h) in coords.items():
        sx, sy, sw, sh = mx(x), my(y), w*px_per_m, h*px_per_m
        # outer bold stroke
        svg.append(_rect_svg(sx, sy, sw, sh, stroke_width=6))
        # inner thinner stroke to create double-line effect
        inset = 3
        svg.append(_rect_svg(sx+inset, sy+inset, sw-2*inset, sh-2*inset, stroke_width=2))
        # label
        svg.append(_text_svg(sx + sw/2, sy + sh/2, labels.get(rid, rid), font_size=16))
        # size label bottom-center
        size_label = f"{w:.1f}×{h:.1f}m"
        svg.append(_text_svg(sx + sw/2, sy + sh - 12, size_label, font_size=10))

    # draw fixtures (filled small rectangles with black text)
    if fixtures:
        for f in fixtures:
            rx,ry,rw,rh = f["rect"]
            sx, sy = mx(rx), my(ry)
            sw, sh = rw*px_per_m, rh*px_per_m
            svg.append(_rect_svg(sx, sy, sw, sh, stroke_width=1, fill="white", stroke_color="white"))
            svg.append(f'<text x="{sx+sw/2}" y="{sy+sh/2}" fill="black" font-size="9" text-anchor="middle" dominant-baseline="middle">{escape(f["type"])}</text>')

    # draw doors: for each door, attempt to place a swing arc or gap on shared wall
    if doors:
        for d in doors:
            a = coords.get(d.get("from_room") or d.get("from"))
            b = coords.get(d.get("to_room") or d.get("to"))
            if not a or not b:
                continue
            ax,ay,aw,ah = a; bx,by,bw,bh = b
            eps = 1e-6
            # right of A touches left of B
            if abs((ax+aw) - bx) < 1e-3:
                # shared vertical wall at x = ax+aw
                xwall = mx(ax+aw)
                # midpoint y
                myid = my(max(ay,by) + min(ah,bh)/2)
                # draw small gap (erase inner stroke area) by drawing background rect
                gap_h = 20
                svg.append(f'<rect x="{xwall-3}" y="{myid-gap_h/2}" width="8" height="{gap_h}" fill="#181818" stroke="none"/>')
                # draw swing arc into B side (90deg)
                svg.append(_arc_svg(xwall+10, myid, 20, 180, 270))
            elif abs(ax - (bx + bw)) < 1e-3:
                xwall = mx(ax)
                myid = my(max(ay,by) + min(ah,bh)/2)
                svg.append(f'<rect x="{xwall-3}" y="{myid-10}" width="8" height="20" fill="#181818" stroke="none"/>')
                svg.append(_arc_svg(xwall-10, myid, 20, 0, 90))
            elif abs((ay+ah) - by) < 1e-3:
                ywall = my(ay+ah)
                mxid = mx(max(ax,bx) + min(aw,bw)/2)
                svg.append(f'<rect x="{mxid-10}" y="{ywall-3}" width="20" height="8" fill="#181818" stroke="none"/>')
                svg.append(_arc_svg(mxid, ywall+10, 20, 270, 360))
            elif abs(ay - (by + bh)) < 1e-3:
                ywall = my(ay)
                mxid = mx(max(ax,bx) + min(aw,bw)/2)
                svg.append(f'<rect x="{mxid-10}" y="{ywall-3}" width="20" height="8" fill="#181818" stroke="none"/>')
                svg.append(_arc_svg(mxid, ywall-10, 20, 90, 180))

    svg.append('</svg>')
    full = "\n".join(svg)
    with open(out_svg, "w", encoding="utf-8") as f:
        f.write(full)
    print("Saved SVG:", out_svg)
    try:
        out_png = out_svg.replace('.svg', '.png')
        cairosvg.svg2png(bytestring=full.encode('utf-8'), write_to=out_png, output_width=W, output_height=H)
        print("Saved PNG:", out_png)
    except Exception as e:
        print("PNG export failed (cairosvg). Error:", e)
