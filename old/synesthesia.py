import asyncio
import json
import math
import re
import threading
import time
import webcolors
import websockets

# ==========================================
# CONSTANTS & PHYSICAL LOGIC
# ==========================================
HTTP_PORT = 5001
UPSTREAM_CHIMES_WS = "ws://127.0.0.1:65432"
DOWNSTREAM_WS_PORT = 65401

A4_FREQ = 432.0         # Reference tuning standard
SPEED_OF_LIGHT = 3e8    # m/s
LAMBDA_MIN = 380.0      # Visible violet limit (nm)
LAMBDA_MAX = 780.0      # Visible red limit (nm)

QUARTER_NOTE_NAMES = [
    "A", "A‡", "A#", "B♭‡", "B", "C", "C‡", "C#", "D♭‡", "D", "D‡", "D#",
    "E♭‡", "E", "F", "F‡", "F#", "G♭‡", "G", "G‡", "G#", "A♭‡", "A‡ (High)", "A# (High)"
]

# 24-EDO Quartertone lookup table fallback
NOTE_TO_QUARTERTONE = {
    'A': 0, 'A𝄳': 1, 'A‡': 1, 'A#': 2, 'Bb': 2, 'A♭': 2,
    'B𝄲': 3, 'B♭‡': 3, 'B': 4, 'C': 5, 'C𝄳': 6, 'C‡': 6,
    'C#': 7, 'Db': 7, 'D𝄲': 8, 'D♭‡': 8, 'D': 9, 'D𝄳': 10,
    'D‡': 10, 'D#': 11, 'Eb': 11, 'E𝄲': 12, 'E♭‡': 12, 'E': 13,
    'F': 14, 'F𝄳': 15, 'F‡': 15, 'F#': 16, 'Gb': 16, 'G𝄲': 17,
    'G♭‡': 17, 'G': 18, 'G𝄳': 19, 'G‡': 19, 'G#': 20, 'Ab': 20,
    'A𝄲': 21, 'A♭‡': 21, 'B𝄳': 22, 'C♭': 22, 'B#': 5
}

latest_chimes_data = {}
connected_downstream_clients = set()


# ==========================================
# PARAMETERIZED EDO ENGINE & PITCH HELPERS
# ==========================================
class EDOEngine:
    """Helper engine for arbitrary N-EDO pitch-to-frequency and note naming conversions."""

    def __init__(self, edo_steps: int = 24, a4_freq: float = A4_FREQ):
        self.edo_steps = max(1, edo_steps)
        self.a4_freq = a4_freq

        # Circle of 5ths step size in N-EDO
        self.fifth_step = round(self.edo_steps * math.log2(1.5))

        # Diatonic scale degree pitch classes (C=0, D, E, F, G, A, B)
        self.deg_pcs = [
            0,                                       # C (degree 0)
            (2 * self.fifth_step) % self.edo_steps, # D (degree 1)
            (4 * self.fifth_step) % self.edo_steps, # E (degree 2)
            (-self.fifth_step) % self.edo_steps,    # F (degree 3)
            self.fifth_step % self.edo_steps,       # G (degree 4)
            (3 * self.fifth_step) % self.edo_steps, # A (degree 5)
            (5 * self.fifth_step) % self.edo_steps  # B (degree 6)
        ]

    def edo_to_freq(self, step_val: int) -> float:
        a4_step = (4 * self.edo_steps) + self.deg_pcs[5]
        return self.a4_freq * math.pow(2.0, (step_val - a4_step) / float(self.edo_steps))

    def get_note_name(self, step_val: int) -> str:
        pc = step_val % self.edo_steps
        octave = (step_val // self.edo_steps) - 1

        if self.edo_steps == 12:
            names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
            return f"{names[pc]}{octave}"
        elif self.edo_steps == 24:
            names = ['C', 'C𝄳', 'Db', 'D𝄲', 'D', 'D𝄳', 'Eb', 'E𝄲', 'E', 'E𝄳', 'F', 'F𝄳',
                     'F#', 'G𝄲', 'G', 'G𝄳', 'Ab', 'A𝄲', 'A', 'A𝄳', 'Bb', 'B𝄲', 'B', 'B𝄳']
            return f"{names[pc]}{octave}"
        else:
            deg_names = ['C', 'D', 'E', 'F', 'G', 'A', 'B']
            closest_deg = min(
                range(7),
                key=lambda i: min((pc - self.deg_pcs[i]) % self.edo_steps, (self.deg_pcs[i] - pc) % self.edo_steps)
            )
            diff = (pc - self.deg_pcs[closest_deg]) % self.edo_steps
            if diff > self.edo_steps // 2:
                diff -= self.edo_steps
            acc = f"+{diff}" if diff > 0 else (f"{diff}" if diff < 0 else "")
            return f"{deg_names[closest_deg]}{acc}_{octave}"


#def parse_note_to_step(note_str: str, edo_steps: int = 24) -> int:
#    """Parses standard, quartertone, or N-EDO offset note strings (e.g. 'C+1_4', 'A‡', 'D#3') into pitch class steps."""
#    clean_str = str(note_str).strip()
#
#    # Match general N-EDO format: Deg[+offset or -offset]_[octave] (e.g., "C+1_4", "D-2_3", "E_4")
#    m = re.match(r'^([A-Ga-g])([+-]\d+)?(?:_(-?\d+))?$', clean_str)
#    if m and edo_steps not in (12, 24):
#        deg_char = m.group(1).upper()
#        offset = int(m.group(2)) if m.group(2) else 0
#        deg_names = ['C', 'D', 'E', 'F', 'G', 'A', 'B']
#        if deg_char in deg_names:
#            engine = EDOEngine(edo_steps)
#            base_pc = engine.deg_pcs[deg_names.index(deg_char)]
#            return (base_pc + offset) % edo_steps
#
#    # 24-EDO table lookup
#    clean_note = ''.join([c for c in clean_str if not c.isdigit() and c not in ('-', '_')])
#    if clean_note in NOTE_TO_QUARTERTONE:
#        return NOTE_TO_QUARTERTONE[clean_note] % edo_steps
#
#    # 12-EDO fallback table
#    chromatic_12 = {'C': 0, 'C#': 1, 'DB': 1, 'D': 2, 'D#': 3, 'EB': 3, 'E': 4,
#                    'F': 5, 'F#': 6, 'GB': 6, 'G': 7, 'G#': 8, 'AB': 8, 'A': 9,
#                    'A#': 10, 'BB': 10, 'B': 11}
#    upper_note = clean_note.upper()
#    if upper_note in chromatic_12:
#        return int(round((chromatic_12[upper_note] / 12.0) * edo_steps)) % edo_steps
#
#    return 0
def parse_note_to_step(note_str: str, edo_steps: int = 24) -> int:
    """Parses standard, quartertone, or N-EDO offset note strings into pitch class steps."""
    clean_str = str(note_str).strip()

    # Match general N-EDO format for any EDO system
    m = re.match(r'^([A-Ga-g])([+-]\d+)?(?:_(-?\d+))?$', clean_str)
    if m:
        deg_char = m.group(1).upper()
        offset = int(m.group(2)) if m.group(2) else 0
        deg_names = ['C', 'D', 'E', 'F', 'G', 'A', 'B']
        if deg_char in deg_names:
            engine = EDOEngine(edo_steps)
            base_pc = engine.deg_pcs[deg_names.index(deg_char)]
            return (base_pc + offset) % edo_steps

    # 24-EDO table lookup fallback
    clean_note = ''.join([c for c in clean_str if not c.isdigit() and c not in ('-', '_', '+')])
    if clean_note in NOTE_TO_QUARTERTONE:
        return NOTE_TO_QUARTERTONE[clean_note] % edo_steps

    # 12-EDO fallback table
    chromatic_12 = {'C': 0, 'C#': 1, 'DB': 1, 'D': 2, 'D#': 3, 'EB': 3, 'E': 4,
                    'F': 5, 'F#': 6, 'GB': 6, 'G': 7, 'G#': 8, 'AB': 8, 'A': 9,
                    'A#': 10, 'BB': 10, 'B': 11}
    upper_note = clean_note.upper()
    if upper_note in chromatic_12:
        return int(round((chromatic_12[upper_note] / 12.0) * edo_steps)) % edo_steps

    return 0

# ==========================================
# COLOR & HARMONIC MATH
# ==========================================
def get_latest_chimes_data():
    return latest_chimes_data


def get_color_name(requested_rgb):
    try:
        if hasattr(webcolors, 'rgb_to_name'):
            return webcolors.rgb_to_name(requested_rgb)
    except (ValueError, AttributeError):
        pass

    rgb_map = {}
    if hasattr(webcolors, 'CSS3_HEX_TO_NAMES'):
        for hex_code, name in webcolors.CSS3_HEX_TO_NAMES.items():
            h = hex_code.lstrip('#')
            rgb = tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
            rgb_map[rgb] = name
    elif hasattr(webcolors, 'names'):
        for name in webcolors.names("css3"):
            try:
                rgb = webcolors.name_to_rgb(name)
                rgb_map[rgb] = name
            except Exception:
                continue

    if not rgb_map:
        return "Unknown"

    min_distance = float("inf")
    closest_name = "Unknown"

    for rgb, name in rgb_map.items():
        d = math.sqrt((rgb[0] - requested_rgb[0])**2 + (rgb[1] - requested_rgb[1])**2 + (rgb[2] - requested_rgb[2])**2)
        if d < min_distance:
            min_distance = d
            closest_name = name

    return closest_name.title() if min_distance == 0 else f"{closest_name.title()} (approx)"


def rgb_to_hsv(r, g, b):
    r_norm, g_norm, b_norm = r / 255.0, g / 255.0, b / 255.0
    mx = max(r_norm, g_norm, b_norm)
    mn = min(r_norm, g_norm, b_norm)
    df = mx - mn

    if mx == mn:
        h = 0
    elif mx == r_norm:
        h = (60 * ((g_norm - b_norm) / df) + 360) % 360
    elif mx == g_norm:
        h = (60 * ((b_norm - r_norm) / df) + 120) % 360
    elif mx == b_norm:
        h = (60 * ((r_norm - g_norm) / df) + 240) % 360

    return round(h, 2)


def hsv_to_rgb(h, s=1.0, v=1.0):
    c = v * s
    x = c * (1 - abs((h / 60.0) % 2 - 1))
    m = v - c

    if 0 <= h < 60:
        r_p, g_p, b_p = c, x, 0
    elif 60 <= h < 120:
        r_p, g_p, b_p = x, c, 0
    elif 120 <= h < 180:
        r_p, g_p, b_p = 0, c, x
    elif 180 <= h < 240:
        r_p, g_p, b_p = 0, x, c
    elif 240 <= h < 300:
        r_p, g_p, b_p = x, 0, c
    else:
        r_p, g_p, b_p = c, 0, x

    return int(round((r_p + m) * 255)), int(round((g_p + m) * 255)), int(round((b_p + m) * 255))


def calculate_single_voice(r: int, g: int, b: int, edo_steps: int = 24):
    color_name = get_color_name((r, g, b))
    hue = rgb_to_hsv(r, g, b)

    step_index = int(round((hue / 360.0) * edo_steps)) % edo_steps
    engine = EDOEngine(edo_steps)
    note_name = engine.get_note_name(step_index + (4 * edo_steps))  # Octave 4 default

    wavelength_nm = LAMBDA_MIN + (hue / 360.0) * (LAMBDA_MAX - LAMBDA_MIN)
    light_freq_hz = SPEED_OF_LIGHT / (wavelength_nm * 1e-9)

    audible_freq = engine.edo_to_freq((4 * edo_steps) + step_index)

    n_semitones = 12 * math.log2(audible_freq / A4_FREQ) if audible_freq > 0 else 0
    semitone_ratio = 2 ** ((n_semitones % 12) / 12)
    chromatic_names = ["A", "A#", "B", "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#"]
    closest_12_note = chromatic_names[int(round(n_semitones % 12)) % 12]

    return {
        "color_name": color_name,
        "hsv_hue": hue,
        "wavelength_nm": round(wavelength_nm, 2),
        "light_freq_thz": round(light_freq_hz / 1e12, 2),
        "audible_freq_hz": round(audible_freq, 2),
        "closest_note": f"{closest_12_note} ({round(semitone_ratio, 3)}:1 ratio)",
        "note_name": note_name,
        "quartertone_note": note_name,      # Backward compatibility alias
        "step_index": step_index,
        "quartertone_index": step_index,    # Backward compatibility alias
        "edo_steps": edo_steps,
        "r": r, "g": g, "b": b
    }


def calculate_note_to_color(step_index: int, edo_steps: int = 24, note_name: str = None):
    step_index = step_index % edo_steps
    hue = (step_index / float(edo_steps)) * 360.0
    r, g, b = hsv_to_rgb(hue)
    res = calculate_single_voice(r, g, b, edo_steps=edo_steps)
    res["step_index"] = step_index
    res["quartertone_index"] = step_index
    if note_name:
        res["note_name"] = note_name
        res["quartertone_note"] = note_name
    return res


def convert_note_list_to_colors(note_list: list, step_list: list = None, edo_steps: int = 24):
    colors = []
    engine = EDOEngine(edo_steps)
    for idx, note in enumerate(note_list):
        if step_list and idx < len(step_list):
            s_val = step_list[idx]
            q_idx = s_val % edo_steps
            note_str = str(note)
        else:
            note_str = str(note)
            q_idx = parse_note_to_step(note_str, edo_steps=edo_steps)

        colors.append(calculate_note_to_color(q_idx, edo_steps=edo_steps, note_name=note_str))
    return colors


# ==========================================
# CHIMES WEBSOCKET LISTENER & BROADCASTER
# ==========================================
async def listen_and_broadcast_chimes():
    global latest_chimes_data
    print(f"[SYNESTHESIA V2] Listening upstream to chimes-v2 on {UPSTREAM_CHIMES_WS}...")

    while True:
        try:
            async with websockets.connect(UPSTREAM_CHIMES_WS) as websocket:
                print("[SYNESTHESIA V2] Connected to chimes-v2 stream.")
                while True:
                    msg = await websocket.recv()
                    data = json.loads(msg)

                    # Extract EDO tuning parameter from upstream message (default to 24 if unspecified)
                    edo_steps = (
                        data.get("edo_steps") or
                        data.get("edo") or
                        data.get("meta", {}).get("edo_steps") or
                        data.get("meta", {}).get("edo") or
                        data.get("left_hand", {}).get("edo_steps") or
                        24
                    )

                    left_hand = data.get("left_hand", {})
                    right_hand = data.get("right_hand", {})

                    lh_notes = left_hand.get("notes", [])
                    lh_steps = left_hand.get("steps", [])
                    rh_notes = right_hand.get("notes", [])
                    rh_steps = right_hand.get("steps", [])

                    lh_colors = convert_note_list_to_colors(lh_notes, step_list=lh_steps, edo_steps=edo_steps)
                    rh_colors = convert_note_list_to_colors(rh_notes, step_list=rh_steps, edo_steps=edo_steps)

                    combined_palette = lh_colors + rh_colors

                    augmented_state = {
                        "server_time": time.time(),
                        "edo_steps": edo_steps,
                        "tick": data.get("tick"),
                        "minute_tick": data.get("minute_tick"),
                        "metronome": data.get("metronome"),
                        "permissible_triggers": data.get("permissible_triggers"),
                        "polygon_sync": data.get("polygon_sync"),

                        "left_hand": {
                            **left_hand,
                            "colors": lh_colors
                        },
                        "right_hand": {
                            **right_hand,
                            "colors": rh_colors
                        },
                        "palette_8_color": combined_palette
                    }

                    latest_chimes_data = augmented_state

                    if connected_downstream_clients:
                        payload = json.dumps(augmented_state)
                        await asyncio.gather(
                            *[client.send(payload) for client in connected_downstream_clients],
                            return_exceptions=True
                        )

        except (websockets.exceptions.ConnectionClosedError, OSError) as e:
            print(f"[SYNESTHESIA V2] Upstream chimes connection lost: {e}. Reconnecting in 2s...")
            await asyncio.sleep(2)


async def downstream_ws_handler(websocket):
    connected_downstream_clients.add(websocket)
    try:
        if latest_chimes_data:
            await websocket.send(json.dumps(latest_chimes_data))
        await websocket.wait_closed()
    finally:
        connected_downstream_clients.remove(websocket)


def start_asyncio_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def main_ws():
        async with websockets.serve(downstream_ws_handler, "0.0.0.0", DOWNSTREAM_WS_PORT):
            print(f"[SYNESTHESIA WS] Broadcasting color-augmented state on ws://0.0.0.0:{DOWNSTREAM_WS_PORT}")
            await listen_and_broadcast_chimes()

    loop.run_until_complete(main_ws())
