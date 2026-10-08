#!/usr/bin/env python
import logging
from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO
from .timepiece import get_clock_data

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

thread_started = False

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/timepiece_state', methods=['GET'])
@app.route('/timepiece_state', methods=['GET'])
def timepiece_state():
    return jsonify(get_clock_data())

def background_thread():
    """Background task to push clock updates 10 times per second."""
    while True:
        try:
            data = get_clock_data()
            socketio.emit('clock_update', data, namespace='/')
        except Exception as e:
            logging.error(f"Error in clock background thread: {e}")
        socketio.sleep(0.1)

@socketio.on('connect')
def connect():
    global thread_started
    try:
        socketio.emit('clock_update', get_clock_data())
    except Exception as e:
        logging.error(f"Error emitting initial connect state: {e}")

    if not thread_started:
        socketio.start_background_task(background_thread)
        thread_started = True

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5008)
