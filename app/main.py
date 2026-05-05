from flask import Flask, request, jsonify
import os
import time
import random
import threading

app = Flask(__name__)

MODE = os.environ.get("MODE", "stable")
APP_VERSION = os.environ.get("APP_VERSION", "1.0.0")
APP_PORT = os.environ.get("APP_PORT", "5000")
START_TIME = time.time()

# Chaos state
chaos_state = {
    "active": False,
    "mode": None,
    "duration": 0,
    "error_rate": 0.0,
    "start_time": 0
}
chaos_lock = threading.Lock()


def get_uptime():
    return round(time.time() - START_TIME, 2)


@app.after_request
def add_headers(response):
    if MODE == "canary":
        response.headers["X-Mode"] = "canary"
    return response


@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "message": "Welcome to SwiftDeploy API",
        "mode": MODE,
        "version": APP_VERSION,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "port": int(APP_PORT)
    })


@app.route("/healthz", methods=["GET"])
def healthz():
    return jsonify({
        "status": "healthy",
        "uptime_seconds": get_uptime()
    })


@app.route("/chaos", methods=["POST"])
def chaos():
    if MODE != "canary":
        return jsonify({"error": "Chaos endpoint is only available in canary mode"}), 403

    data = request.get_json(force=True, silent=True) or {}
    chaos_mode = data.get("mode")

    with chaos_lock:
        if chaos_mode == "slow":
            chaos_state["active"] = True
            chaos_state["mode"] = "slow"
            chaos_state["duration"] = data.get("duration", 1)
            chaos_state["start_time"] = time.time()
            return jsonify({"status": "slow chaos activated", "duration": chaos_state["duration"]})

        elif chaos_mode == "error":
            chaos_state["active"] = True
            chaos_state["mode"] = "error"
            chaos_state["error_rate"] = data.get("rate", 0.5)
            chaos_state["start_time"] = time.time()
            return jsonify({"status": "error chaos activated", "rate": chaos_state["error_rate"]})

        elif chaos_mode == "recover":
            chaos_state["active"] = False
            chaos_state["mode"] = None
            chaos_state["start_time"] = 0
            return jsonify({"status": "recovered", "message": "Chaos cancelled"})

        else:
            return jsonify({"error": "Invalid chaos mode"}), 400


@app.before_request
def handle_chaos():
    # Don't intercept the chaos control endpoint itself
    if request.path == "/chaos":
        return

    # Fast path: avoid lock acquisition when chaos is inactive
    if not chaos_state["active"]:
        return

    with chaos_lock:
        # Double-check inside lock
        if not chaos_state["active"]:
            return

        if chaos_state["mode"] == "slow":
            elapsed = time.time() - chaos_state["start_time"]
            if elapsed < chaos_state["duration"]:
                time.sleep(chaos_state["duration"] - elapsed)
            else:
                chaos_state["active"] = False

        elif chaos_state["mode"] == "error":
            if random.random() < chaos_state["error_rate"]:
                return jsonify({"error": "Chaos error triggered"}), 500


if __name__ == "__main__":
    # NOTE: Flask's built-in server is used here for simplicity.
    # It is single-threaded by default in older Flask versions,
    # but modern Flask (1.0+) runs threaded=True by default.
    # For this task, the dev server is acceptable.
    app.run(host="0.0.0.0", port=int(APP_PORT))
