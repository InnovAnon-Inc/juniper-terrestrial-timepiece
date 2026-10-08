import asyncio
import json
import math
import threading
import time
import requests
import websockets
from flask import Flask, render_template_string, jsonify, request

from .polygons import (
        polygon_engine,
        generate_rhythm_library,
        analyze_pattern,
        note_to_freq_432
    )

app = Flask(__name__)

# ==============================================================================
# WEBSOCKET BROADCAST & FLASK API
# ==============================================================================

@app.route('/api/polygon_state', methods=['GET'])
def get_polygon_state():
    with polygon_engine.lock:
        return jsonify(polygon_engine.current_state)

@app.route('/api/library', methods=['GET'])
def get_library():
    n_steps = int(request.args.get('n', 12))
    lib = generate_rhythm_library(n_steps)
    return jsonify({"n": n_steps, "library": lib})

@app.route('/api/chimes_synesthesia', methods=['GET'])
def get_chimes_synesthesia():
    try:
        res = requests.get('http://127.0.0.1:5001/chimes_state', timeout=1.0)
        if res.status_code == 200 and res.json():
            data = res.json()
            for hand in ['inner_hand', 'outer_hand', 'left_hand', 'right_hand']:
                if hand in data and 'notes' in data[hand]:
                    for idx, note_str in enumerate(data[hand]['notes']):
                        freq = note_to_freq_432(note_str)
                        if idx < len(data[hand]['colors']):
                            data[hand]['colors'][idx]['exact_freq_hz'] = freq
            return jsonify(data)
    except Exception:
        pass

    fallback_data = {
        "inner_hand": {
            "chord_name": "Cmaj7 (Lower Hand / Octave 2-3)",
            "notes": ["C2", "G2", "B2", "E3"],
            "colors": [
                {"r": 255, "g": 87,  "b": 34,  "exact_freq_hz": note_to_freq_432("C2")},
                {"r": 76,  "g": 175, "b": 80,  "exact_freq_hz": note_to_freq_432("G2")},
                {"r": 33,  "g": 150, "b": 243, "exact_freq_hz": note_to_freq_432("B2")},
                {"r": 255, "g": 193, "b": 7,   "exact_freq_hz": note_to_freq_432("E3")}
            ]
        },
        "outer_hand": {
            "chord_name": "Am9 (Upper Hand / Octave 4-5)",
            "notes": ["C4", "E4", "G4", "B4"],
            "colors": [
                {"r": 255, "g": 87,  "b": 34,  "exact_freq_hz": note_to_freq_432("C4")},
                {"r": 255, "g": 193, "b": 7,   "exact_freq_hz": note_to_freq_432("E4")},
                {"r": 76,  "g": 175, "b": 80,  "exact_freq_hz": note_to_freq_432("G4")},
                {"r": 33,  "g": 150, "b": 243, "exact_freq_hz": note_to_freq_432("B4")}
            ]
        }
    }
    return jsonify(fallback_data)

@app.route('/api/evaluate_voice_bitwise', methods=['POST'])
def evaluate_voice_bitwise():
    data = request.json
    polygons = data.get('polygons', [])
    N = data.get('N', 12)
    
    voices = {}
    for poly in polygons:
        tone_id = poly.get('tone_id')
        pat = poly.get('pattern', [0] * N)
        is_pos = poly.get('type') == 'positive'
        
        if tone_id not in voices:
            voices[tone_id] = {'pos': [0] * N, 'neg': [0] * N, 'tone_name': poly.get('tone_name')}
        
        for i in range(len(pat)):
            idx = i % N
            if pat[i]:
                if is_pos:
                    voices[tone_id]['pos'][idx] = 1
                else:
                    voices[tone_id]['neg'][idx] = 1

    global_combined_pattern = [0] * N
    voice_results = {}
    
    for tone_id, vdata in voices.items():
        res_pat = [1 if (pos and not neg) else 0 for pos, neg in zip(vdata['pos'], vdata['neg'])]
        voice_results[tone_id] = {
            "tone_name": vdata['tone_name'],
            "pattern": res_pat,
            "analysis": analyze_pattern(res_pat, N)
        }
        for i in range(N):
            if res_pat[i]:
                global_combined_pattern[i] = 1

    global_analysis = analyze_pattern(global_combined_pattern, N)

    return jsonify({
        "voices": voice_results,
        "global_analysis": global_analysis
    })

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

# ==============================================================================
# FRONTEND INTERFACE
# ==============================================================================

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Harmonic Polygon Server - Live Nested Loop</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: #121214;
            color: #e0e0e0;
            margin: 0;
            padding: 20px;
            display: flex;
            flex-direction: column;
            align-items: center;
        }
        h1 { margin-bottom: 5px; color: #4db6ac; }
        p.subtitle { color: #888; margin-top: 0; margin-bottom: 20px; text-align: center; }
        
        .top-bar {
            background: #1e1e24;
            padding: 15px 25px;
            border-radius: 8px;
            display: flex;
            gap: 20px;
            align-items: center;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
            margin-bottom: 20px;
            flex-wrap: wrap;
        }
        label { font-weight: bold; font-size: 14px; }
        
        .workspace {
            display: flex;
            gap: 25px;
            flex-wrap: wrap;
            justify-content: center;
            max-width: 1450px;
            width: 100%;
        }
        
        .canvas-card {
            background: #1e1e24;
            padding: 20px;
            border-radius: 8px;
            display: flex;
            flex-direction: column;
            align-items: center;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        }
        canvas { background: #18181c; border-radius: 50%; border: 1px solid #333; }
        
        .panel {
            background: #1e1e24;
            padding: 15px;
            border-radius: 8px;
            width: 540px;
            display: flex;
            flex-direction: column;
            gap: 12px;
        }

        .status-box {
            background: #25252e;
            padding: 12px;
            border-radius: 6px;
            font-size: 14px;
            border-left: 4px solid #00e676;
            line-height: 1.6;
        }
        
        .badge { font-size: 11px; padding: 3px 8px; border-radius: 4px; font-weight: bold; }
        .badge-pos { background: #00897b; color: #fff; }
        .badge-neg { background: #d32f2f; color: #fff; }
        .badge-sub { background: #7b1fa2; color: #fff; }
    </style>
</head>
<body>

    <h1>Harmonic Polygon Progression Server</h1>
    <p class="subtitle">Live Bitwise Subtraction Broadcast & Dual-Hand Chimes Sync Engine</p>

    <div class="top-bar">
        <span id="n-display" style="font-size: 16px; font-weight: bold; color: #00e676;">N = --</span>
        <span id="combo-display" style="font-size: 14px; color: #bbb;">Combo: -- / --</span>
        <span id="repeat-display" style="font-size: 14px; color: #ffeb3b;">Repeat: -- / 7</span>
        <span id="step-display" style="font-size: 14px; color: #4db6ac;">Step: --</span>
    </div>

    <div class="workspace">
        <div class="canvas-card">
            <canvas id="polyCanvas" width="500" height="500"></canvas>
        </div>

        <div class="panel">
            <h3>Live Nested Loop Status</h3>
            <div class="status-box" id="loop-status">
                Connecting to Polygon Engine WebSocket...
            </div>
        </div>
    </div>

    <script>
        let ws = null;

        function connectWS() {
            ws = new WebSocket(`ws://${window.location.hostname}:65403`);

            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                updateUI(data);
            };

            ws.onclose = () => {
                setTimeout(connectWS, 1000);
            };
        }

        function updateUI(data) {
            if (!data || !data.pos_polygon) return;

            document.getElementById('n-display').innerText = `N = ${data.N}`;
            document.getElementById('combo-display').innerText = `Combo: ${data.combo_index} / ${data.total_combos}`;
            document.getElementById('repeat-display').innerText = `Repeat: ${data.repeat_count} / ${data.total_repeats}`;
            document.getElementById('step-display').innerText = `Step: ${data.step_index + 1} / ${data.N}`;

            const posLabel = data.pos_polygon.label || 'Positive Polygon';
            const negLabel = data.neg_polygon.label || 'Negative Polygon';

            document.getElementById('loop-status').innerHTML = `
                <div><span class="badge badge-pos">POSITIVE (Left Hand 7ths)</span><br>
                <strong>${posLabel}</strong>: [${data.pos_polygon.pattern.join('')}]</div><br>
                
                <div><span class="badge badge-neg">NEGATIVE (Bitwise Subtracted)</span><br>
                <strong>${negLabel}</strong>: [${data.neg_polygon.pattern.join('')}]</div><br>
                
                <div><span class="badge badge-sub">RESULT (Right Hand 7ths)</span><br>
                <strong>Pattern</strong>: [${data.sub_pattern.join('')}]</div>
            `;

            drawCanvas(data);
        }

        function drawCanvas(data) {
            const canvas = document.getElementById('polyCanvas');
            const ctx = canvas.getContext('2d');
            const N = data.N;

            ctx.clearRect(0, 0, canvas.width, canvas.height);
            const centerX = canvas.width / 2;
            const centerY = canvas.height / 2;
            const radius = 180;

            // Draw radial grid
            for (let i = 0; i < N; i++) {
                const angle = (2 * Math.PI * i / N) - (Math.PI / 2);
                const x1 = centerX + (radius + 10) * Math.cos(angle);
                const y1 = centerY + (radius + 10) * Math.sin(angle);
                
                ctx.beginPath();
                ctx.moveTo(centerX, centerY);
                ctx.lineTo(x1, y1);
                ctx.strokeStyle = (i === data.step_index) ? '#ffeb3b' : '#333';
                ctx.lineWidth = (i === data.step_index) ? 2.5 : 0.8;
                ctx.stroke();
            }

            // Draw Positive Polygon (Left Hand)
            drawPolygonShape(ctx, centerX, centerY, radius, data.pos_polygon.pattern, '#00e676', false, 2.5);
            // Draw Negative Polygon
            drawPolygonShape(ctx, centerX, centerY, radius - 15, data.neg_polygon.pattern, '#ff5252', true, 1.5);
            // Draw Subtracted Result Polygon (Right Hand)
            drawPolygonShape(ctx, centerX, centerY, radius - 30, data.sub_pattern, '#ab47bc', false, 2.5);
        }

        function drawPolygonShape(ctx, centerX, centerY, radius, pattern, color, isDashed, lineWidth) {
            const N = pattern.length;
            const vertices = [];

            for (let i = 0; i < N; i++) {
                if (pattern[i]) {
                    const angle = (2 * Math.PI * (i / N)) - (Math.PI / 2);
                    vertices.push({
                        x: centerX + radius * Math.cos(angle),
                        y: centerY + radius * Math.sin(angle)
                    });
                }
            }

            if (vertices.length > 1) {
                ctx.beginPath();
                ctx.moveTo(vertices[0].x, vertices[0].y);
                vertices.forEach(v => ctx.lineTo(v.x, v.y));
                ctx.closePath();

                ctx.strokeStyle = color;
                ctx.setLineDash(isDashed ? [5, 5] : []);
                ctx.lineWidth = lineWidth;
                ctx.stroke();
                ctx.setLineDash([]);
            }

            vertices.forEach(v => {
                ctx.beginPath();
                ctx.arc(v.x, v.y, 4, 0, 2 * Math.PI);
                ctx.fillStyle = color;
                ctx.fill();
            });
        }

        connectWS();
    </script>
</body>
</html>
"""

# ==============================================================================
# MAIN ENTRY POINT
# ==============================================================================

def start_ws_broadcast():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def ws_handler(websocket):
        polygon_engine.connected_clients.add(websocket)
        try:
            await websocket.wait_closed()
        finally:
            polygon_engine.connected_clients.remove(websocket)

    async def broadcast_loop():
        while True:
            state = polygon_engine.tick()
            if polygon_engine.connected_clients and state:
                payload = json.dumps(state)
                await asyncio.gather(
                    *[client.send(payload) for client in polygon_engine.connected_clients],
                    return_exceptions=True
                )
            now = time.time()
            next_tick = math.floor(now) + (60.0 / polygon_engine.bpm)
            await asyncio.sleep(max(0.01, next_tick - time.time()))

    async def main_ws():
        async with websockets.serve(ws_handler, "0.0.0.0", 65403):
            print("[POLYGON WS] Broadcasting polygon engine on ws://0.0.0.0:65403")
            await broadcast_loop()

    loop.run_until_complete(main_ws())

#if __name__ == '__main__':
#    threading.Thread(target=start_ws_broadcast, daemon=True).start()
#    print("Running Harmonic Polygon Server on http://0.0.0.0:5007")
#    app.run(host='0.0.0.0', port=5007, debug=True)

import os

if __name__ == '__main__':
    # Only start the WebSocket server in the child reloader process (or if debug is off)
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not app.debug:
        threading.Thread(target=start_ws_broadcast, daemon=True).start()

    print("Running Harmonic Polygon Server on http://0.0.0.0:5007")
    app.run(host='0.0.0.0', port=5007, debug=True, use_reloader=False)
