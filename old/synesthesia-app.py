#! /usr/bin/env python3
import threading
from flask import Flask, render_template, render_template_string, request, jsonify

from juniper_synesthesia.synesthesia import (
    HTTP_PORT,
    calculate_single_voice,
    calculate_note_to_color,
    convert_note_list_to_colors,
    get_latest_chimes_data,
    start_asyncio_loop,
)

app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Synesthesia Engine</title>
    <style>
        body { background: #111; color: #eee; font-family: sans-serif; padding: 20px; }
        h1 { color: #00e676; }
        .palette { display: flex; gap: 10px; margin-top: 20px; flex-wrap: wrap; }
        .color-card {
            width: 130px; padding: 12px; border-radius: 8px; text-align: center;
            color: #000; font-weight: bold; font-size: 12px; box-shadow: 0 4px 10px rgba(0,0,0,0.5);
        }
        .section-title { margin-top: 25px; border-bottom: 1px solid #333; padding-bottom: 5px; }
        pre { background: #1a1a1a; padding: 12px; border-radius: 6px; overflow-x: auto; color: #4db6ac; }
    </style>
</head>
<body>
    <h1>Synesthesia Color & Harmonic Visualizer</h1>
    <p>Connected to <code>chimes-v2</code> upstream. Broadcasting on port <code>65401</code>.</p>
    
    <div id="status">Connecting to Synesthesia WebSocket...</div>

    <h2 class="section-title">Active 8-Color Palette</h2>
    <div class="palette" id="palette-container"></div>

    <h2 class="section-title">Live State JSON</h2>
    <pre id="json-debug">Waiting for tick data...</pre>

    <script>
        const ws = new WebSocket(`ws://${window.location.hostname}:65401`);
        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            document.getElementById('status').innerText = `Tick: ${data.tick} | Minute Tick: ${data.minute_tick}s / 60s`;
            document.getElementById('json-debug').innerText = JSON.stringify(data, null, 2);

            const container = document.getElementById('palette-container');
            container.innerHTML = '';

            if (data.palette_8_color) {
                data.palette_8_color.forEach((item, idx) => {
                    const card = document.createElement('div');
                    card.className = 'color-card';
                    card.style.backgroundColor = `rgb(${item.r}, ${item.g}, ${item.b})`;
                    const luminance = (0.299 * item.r + 0.587 * item.g + 0.114 * item.b);
                    card.style.color = luminance > 128 ? '#000' : '#fff';
                    card.innerHTML = `
                        <div>#${idx + 1} ${item.quartertone_note}</div>
                        <div>${item.color_name}</div>
                        <div>${item.light_freq_thz} THz</div>
                        <div>${item.wavelength_nm} nm</div>
                    `;
                    container.appendChild(card);
                });
            }
        };
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    try:
        return render_template('index.html')
    except Exception:
        return render_template_string(HTML_TEMPLATE)

@app.route('/calculate', methods=['POST'])
def calculate():
    req = request.json or {}
    r, g, b = int(req.get('r', 0)), int(req.get('g', 0)), int(req.get('b', 0))
    return jsonify(calculate_single_voice(r, g, b))

@app.route('/calculate_note', methods=['POST'])
def calculate_note():
    req = request.json or {}
    note_index = int(req.get('note_index', 0))
    return jsonify(calculate_note_to_color(note_index))

@app.route('/sync_chimes', methods=['POST'])
def sync_chimes():
    data = request.json or {}
    left_colors = convert_note_list_to_colors(data.get("left_hand", []))
    right_colors = convert_note_list_to_colors(data.get("right_hand", []))
    return jsonify({
        "left_colors": left_colors,
        "right_colors": right_colors,
        "palette_8_color": left_colors + right_colors
    })

@app.route('/chimes_state', methods=['GET'])
def chimes_state():
    return jsonify(get_latest_chimes_data())

def main():
    threading.Thread(target=start_asyncio_loop, daemon=True).start()
    print(f"Running Synesthesia Server on http://0.0.0.0:{HTTP_PORT}")
    app.run(host='0.0.0.0', port=HTTP_PORT)

if __name__ == '__main__':
    main()
