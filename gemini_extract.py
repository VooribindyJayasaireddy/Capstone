# gemini_extract.py

import os, json, re, time

from typing import List, Optional, Dict, Any

from pydantic import BaseModel, ValidationError, Field

from google import genai

client = genai.Client()  # ensure ADC or GOOGLE_API_KEY set

class Size(BaseModel):

    width_m: Optional[float] = None

    height_m: Optional[float] = None

class RoomSpec(BaseModel):

    id: str

    type: str

    min_width_m: Optional[float] = None

    min_height_m: Optional[float] = None

    size_m: Optional[Size] = None

    preferred_adjacent: Optional[List[str]] = []

    fixtures: Optional[List[str]] = []  # e.g., ["toilet","sink","shower","stove"]

class DoorSpec(BaseModel):

    from_room: str

    to_room: str

    count: Optional[int] = 1

class FloorPlanSpec(BaseModel):

    rooms: List[RoomSpec]

    doors: Optional[List[DoorSpec]] = []

    notes: Optional[str] = None

SYSTEM_INSTR = """

You are an assistant that MUST output ONLY valid JSON following this schema:

{

  "rooms": [

    {

      "id":"living",

      "type":"Living Room",

      "min_width_m":3.5,

      "min_height_m":3.0,

      "size_m":{"width_m":5.0,"height_m":4.0},

      "preferred_adjacent":["kitchen","master"],

      "fixtures":["sofa"]

    }

  ],

  "doors": [{"from_room":"living","to_room":"kitchen","count":1}],

  "notes":"optional text"

}

Rules:

- Output strictly JSON. No commentary. Use snake_case keys.

- For sizes: if the user mentions specific sizes (e.g., '4x3m' or '4m by 3m'), provide them in size_m.

- For fixtures: list common fixtures mentioned (toilet, shower, sink, stove, balcony).

- If the user doesn't specify sizes, omit size_m and provide min_width_m/min_height_m if inference is safe.

"""

def _extract_json(text: str) -> str:

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

def extract_structured_plan(prompt: str, model: str = "gemini-2.5-flash", max_retries: int = 2) -> FloorPlanSpec:

    user_message = SYSTEM_INSTR + "\n\nUser prompt: " + prompt + "\n\nRespond with JSON now."

    last_err = None

    for attempt in range(max_retries+1):

        resp = client.models.generate_content(model=model, contents=user_message)

        raw = None

        if hasattr(resp, "text"):

            raw = resp.text

        else:

            try:

                raw = resp.output[0].content[0].text

            except Exception:

                raw = str(resp)

        try:

            json_str = _extract_json(raw)

            data = json.loads(json_str)

            plan = FloorPlanSpec.parse_obj(data)

            return plan

        except Exception as e:

            last_err = e

            time.sleep(0.5 * (attempt+1))

    raise RuntimeError(f"Failed parsing Gemini JSON after {max_retries+1} tries. Last error: {last_err}\nRaw:\n{raw}")
