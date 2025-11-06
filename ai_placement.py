# ai_placement.py
"""
Use Gemini (or other LLM) to suggest furniture and window placements for a FloorPlanSpec.
Returns a dict:
{
  "furniture": [
     {"room_id":"living","type":"sofa","rect":[x,y,width,height], "rotation_deg":0}
  ],
  "windows": [
     {"room_id":"kitchen","wall":"north","offset_m":0.5,"width_m":1.2}
  ]
}

This module uses the google genai client. It is robust to extra text and validates JSON.
"""

import json, time, re
from typing import Dict, Any, List
from google import genai

client = genai.Client()  # uses ADC or GOOGLE_API_KEY env

# Strict schema description for the model to follow
SYSTEM_INSTR = """
You receive a floorplan JSON (rooms with ids, types, sizes and coordinates in meters).
You MUST OUTPUT ONLY valid JSON that matches the schema below and nothing else.

Schema:
{
  "furniture": [
    {
      "room_id": "<room id string>",
      "type": "<sofa|table|bed|wardrobe|tv|dining_table|chair|desk|plant>",
      "rect": [x_m, y_m, width_m, height_m],   // coordinates are relative to plan origin (same coords system as rooms)
      "rotation_deg": 0                           // optional rotation in degrees
    }
  ],
  "windows": [
    {
      "room_id": "<room id string>",
      "wall": "<north|south|east|west>",
      "offset_m": 0.5,    // distance in meters from wall's start corner along that wall
      "width_m": 1.2
    }
  ],
  "notes": "optional short explanation if needed"
}

Important rules:
- Output strictly JSON only (no backticks, no commentary).
- Place furniture inside the room rectangle (rect must be fully inside the room bounds).
- Prefer realistic furniture sizes: sofa ~1.6×0.8, bed ~2.0×1.6, dining_table ~1.6×1.0, tv ~0.6×0.3, wardrobe ~1.2×0.6.
- Place windows on exterior walls, with offset and width sensible for the room size.
- Use meters and numeric values (floats allowed).
- If you cannot place anything, return empty arrays for furniture and windows.
"""

def _extract_json(text: str) -> str:
    # find the first JSON-looking substring with balanced braces
    start = text.find('{')
    if start == -1:
        raise ValueError("No JSON object found")
    depth = 0
    for i in range(start, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return text[start:i+1]
    raise ValueError("Could not extract balanced JSON")

def _plan_to_prompt(plan_obj: Any) -> str:
    """
    Converts the plan into a compact JSON text for the model. Works with Pydantic models or our SimplePlan.
    Expect rooms with fields: id, type, size_m (width_m,height_m) OR (w,h) and coords optional.
    """
    # try pydantic model_dump if available
    try:
        if hasattr(plan_obj, "model_dump"):
            plan_json = plan_obj.model_dump()
        elif hasattr(plan_obj, "model_dump_json"):
            plan_json = json.loads(plan_obj.model_dump_json())
        else:
            # try converting SimplePlan-like structure
            rooms = []
            for r in getattr(plan_obj, "rooms", []):
                size = None
                if hasattr(r, "size_m") and getattr(r, "size_m", None):
                    size = {"width_m": getattr(r.size_m, "width_m", None), "height_m": getattr(r.size_m, "height_m", None)}
                rooms.append({
                    "id": getattr(r, "id", None),
                    "type": getattr(r, "type", None),
                    "size_m": size,
                    # include coords if present
                    "coords": getattr(r, "coords", None),
                    "preferred_adjacent": getattr(r, "preferred_adjacent", None) or []
                })
            plan_json = {"rooms": rooms, "doors": getattr(plan_obj, "doors", []) or []}
    except Exception:
        plan_json = {"rooms": [], "doors": []}

    # produce compact one-line JSON string
    return json.dumps(plan_json)

def suggest_placements(plan_obj: Any, model: str = "gemini-2.5-flash", max_retries: int = 2, temperature: float = 0.0) -> Dict[str, Any]:
    """
    Calls Gemini to suggest furniture & windows. Returns dict with keys 'furniture' and 'windows'.
    Falls back to deterministic placements if Gemini fails.
    """
    prompt_body = _plan_to_prompt(plan_obj)
    user_message = SYSTEM_INSTR + "\n\nFloorPlanJSON:\n" + prompt_body + "\n\nRespond now with strictly the JSON described."

    last_err = None
    for attempt in range(max_retries+1):
        try:
            resp = client.models.generate_content(model=model, contents=user_message)
            raw = None
            if hasattr(resp, "text"):
                raw = resp.text
            else:
                try:
                    raw = resp.output[0].content[0].text
                except Exception:
                    raw = str(resp)
            json_str = _extract_json(raw)
            data = json.loads(json_str)
            # basic validation
            if "furniture" not in data:
                data.setdefault("furniture", [])
            if "windows" not in data:
                data.setdefault("windows", [])
            return data
        except Exception as e:
            last_err = e
            time.sleep(0.5 * (attempt+1))
    # if we reach here, failover to deterministic simple placement
    print("AI placement failed:", last_err)
    return _fallback_placements(plan_obj)

# fallback deterministic placer for quick testing
def _fallback_placements(plan_obj: Any) -> Dict[str, Any]:
    """
    Simple deterministic placements:
      - place sofa at center of living room
      - bed centered in bedrooms
      - windows on outer walls (north) if room width allows
    """
    rooms = getattr(plan_obj, "rooms", [])
    furniture = []
    windows = []
    for r in rooms:
        rid = getattr(r, "id", None)
        rtype = getattr(r, "type", "").lower()
        # get size: prefer size_m then min_ fields
        width = None; height = None
        if getattr(r, "size_m", None):
            width = getattr(r.size_m, "width_m", None)
            height = getattr(r.size_m, "height_m", None)
        if width is None or height is None:
            width = getattr(r, "min_width_m", None) or 3.5
            height = getattr(r, "min_height_m", None) or 3.0
        # simple placements
        if "living" in rtype:
            # sofa centered slightly toward south wall
            w_sofa, h_sofa = 1.6, 0.8
            x = 0.5*(width - w_sofa)
            y = 0.45*(height - h_sofa)
            furniture.append({"room_id": rid, "type":"sofa", "rect":[x,y,w_sofa,h_sofa], "rotation_deg":0})
            # small coffee table
            furniture.append({"room_id": rid, "type":"table", "rect":[x + w_sofa + 0.25, y + (h_sofa-0.6)/2, 0.9, 0.6], "rotation_deg":0})
            # window on north wall if wide enough
            if width >= 1.2:
                windows.append({"room_id": rid, "wall":"north", "offset_m": max(0.2, width*0.2), "width_m": min(1.6, width*0.5)})
        elif "bed" in rtype:
            # place bed at top-left corner inside room
            w_bed, h_bed = 2.0, 1.6
            x = max(0.2, (width - w_bed)/6)
            y = max(0.2, (height - h_bed)/6)
            furniture.append({"room_id": rid, "type":"bed", "rect":[x,y,w_bed,h_bed], "rotation_deg":0})
            if width >= 1.2:
                windows.append({"room_id": rid, "wall":"north", "offset_m": 0.3, "width_m": min(1.2, width*0.4)})
        elif "kitchen" in rtype:
            # place stove+sink along west edge
            stove_w, stove_h = 0.8,0.6
            furniture.append({"room_id": rid, "type":"stove", "rect":[0.2, 0.2, stove_w, stove_h], "rotation_deg":0})
            furniture.append({"room_id": rid, "type":"sink", "rect":[0.2 + stove_w + 0.15, 0.2, 0.8, 0.5], "rotation_deg":0})
            if width >= 1.2:
                windows.append({"room_id": rid, "wall":"east", "offset_m": 0.3, "width_m": min(1.0, width*0.4)})
        elif "bath" in rtype:
            # toilet + sink near a corner
            furniture.append({"room_id": rid, "type":"toilet", "rect":[0.3, 0.3, 0.7, 0.6], "rotation_deg":0})
            furniture.append({"room_id": rid, "type":"sink", "rect":[0.3, 1.1, 0.6, 0.4], "rotation_deg":0})
            # small window on north if narrow
            if height >= 1.0:
                windows.append({"room_id": rid, "wall":"north", "offset_m": 0.2, "width_m": 0.6})

    return {"furniture": furniture, "windows": windows, "notes": "fallback deterministic placements used"}

if __name__ == "__main__":
    # quick local test with a tiny sample plan
    class S: pass
    p = S()
    p.rooms = []
    r = S(); r.id="living"; r.type="Living Room"; r.size_m=type("Z",(object,),{"width_m":5.0,"height_m":4.0})(); r.preferred_adjacent=[]
    p.rooms.append(r)
    print(suggest_placements(p))
