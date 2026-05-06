from flask import Flask, request, jsonify, Response
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

# Prometheus metrics storage
metrics_lock = threading.Lock()
http_requests_total = {}  # {(method, path, status): count}
http_request_duration_seconds = {}  # {le: count} for histogram buckets
HISTOGRAM_BUCKETS = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]


def get_uptime():
    return round(time.time() - START_TIME, 2)


def record_request(method, path, status_code, duration):
    with metrics_lock:
        key = (method, path, status_code)
        http_requests_total[key] = http_requests_total.get(key, 0) + 1
        
        for bucket in HISTOGRAM_BUCKETS:
            bkey = (method, path, bucket)
            if duration <= bucket:
                http_request_duration_seconds[bkey] = http_request_duration_seconds.get(bkey, 0) + 1


@app.after_request
def add_headers(response):
    if MODE == "canary":
        response.headers["X-Mode"] = "canary"
    return response


@app.before_request
def start_timer():
    request.start_time = time.time()


@app.after_request
def track_metrics(response):
    duration = time.time() - getattr(request, 'start_time', time.time())
    record_request(request.method, request.path, response.status_code, duration)
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


@app.route("/metrics", methods=["GET"])
def metrics():
    lines = []
    
    # http_requests_total
    lines.append("# HELP http_requests_total Total HTTP requests")
    lines.append("# TYPE http_requests_total counter")
    with metrics_lock:
        for (method, path, status), count in http_requests_total.items():
            lines.append(f'http_requests_total{{method="{method}",path="{path}",status_code="{status}"}} {count}')
    
    # http_request_duration_seconds histogram
    lines.append("# HELP http_request_duration_seconds HTTP request duration")
    lines.append("# TYPE http_request_duration_seconds histogram")
    with metrics_lock:
        for (method, path, bucket), count in http_request_duration_seconds.items():
            lines.append(f'http_request_duration_seconds_bucket{{method="{method}",path="{path}",le="{bucket}"}} {count}')
    
    # app_uptime_seconds
    lines.append("# HELP app_uptime_seconds Application uptime in seconds")
    lines.append("# TYPE app_uptime_seconds gauge")
    lines.append(f"app_uptime_seconds {get_uptime()}")
    
    # app_mode (0=stable, 1=canary)
    mode_val = 1 if MODE == "canary" else 0
    lines.append("# HELP app_mode Application mode (0=stable, 1=canary)")
    lines.append("# TYPE app_mode gauge")
    lines.append(f"app_mode {mode_val}")
    
    # chaos_active (0=none, 1=slow, 2=error)
    with chaos_lock:
        if not chaos_state["active"]:
            chaos_val = 0
        elif chaos_state["mode"] == "slow":
            chaos_val = 1
        elif chaos_state["mode"] == "error":
            chaos_val = 2
        else:
            chaos_val = 0
    lines.append("# HELP chaos_active Active chaos mode (0=none, 1=slow, 2=error)")
    lines.append("# TYPE chaos_active gauge")
    lines.append(f"chaos_active {chaos_val}")
    
    return Response("\n".join(lines) + "\n", mimetype="text/plain")


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
    if request.path == "/chaos":
        return

    if not chaos_state["active"]:
        return

    with chaos_lock:
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
    app.run(host="0.0.0.0", port=int(APP_PORT))
