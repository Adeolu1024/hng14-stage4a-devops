# Building SwiftDeploy: A Declarative Infrastructure CLI with Observability and Policy Enforcement

## What Is This Project?

SwiftDeploy is a command-line tool that automatically sets up and manages web application deployments. Instead of manually configuring Docker containers, Nginx, and monitoring, you write one file (`manifest.yaml`) that describes what you want, and the tool builds everything for you.

The project was built in two parts:
- **Stage 4A**: Basic infrastructure generation and container management
- **Stage 4B**: Monitoring, policy enforcement, and audit logging

---

## The Core Idea: Declarative Configuration

In traditional DevOps, you manually write configuration files for each service. With SwiftDeploy, you write a single manifest file, and the tool generates all the configuration files automatically.

**manifest.yaml** (the only file you edit manually):
```yaml
services:
  image: swiftdeploy-keeds-api:v1.0.0
  port: 5000
  name: api-service
  mode: stable

nginx:
  image: nginx:alpine
  port: 8080
  proxy_timeout: 30s

network:
  name: swiftdeploy-net
  driver_type: bridge
```

From this one file, SwiftDeploy generates:
- `nginx.conf` (web server configuration)
- `docker-compose.yml` (container orchestration)
- All the settings for monitoring and policy checks

---

## How the Tool Works

The CLI tool (`swiftdeploy`) has several commands:

| Command | What It Does |
|---------|-------------|
| `init` | Reads manifest.yaml and generates nginx.conf + docker-compose.yml |
| `validate` | Checks if everything is ready for deployment |
| `deploy` | Starts all containers and waits for them to be healthy |
| `promote canary/stable` | Switches between stable and canary modes |
| `status` | Shows a live dashboard with metrics and policy compliance |
| `audit` | Generates a report of all events and policy violations |
| `teardown` | Stops and removes all containers |

---

## Stage 4A: The Foundation

### API Service

The API service is a Python Flask application that serves:
- `GET /` — Welcome message with current mode and version
- `GET /healthz` — Health check endpoint
- `POST /chaos` — Simulates problems for testing (only in canary mode)

### Nginx Proxy

Nginx acts as a reverse proxy, routing all traffic to the API service. It:
- Listens on port 8080 (configurable)
- Forwards requests to the API service
- Returns JSON error responses for 502, 503, 504 errors
- Logs all requests in a specific format

### Docker Compose

Docker Compose manages all containers:
- API service (your application)
- Nginx (web server/proxy)
- OPA (policy engine, added in Stage 4B)

---

## Stage 4B: Observability and Policy Enforcement

### The /metrics Endpoint

The API service now exposes a `/metrics` endpoint that reports statistics in Prometheus format:

```
http_requests_total{method="GET",path="/healthz",status_code="200"} 42
http_request_duration_seconds_bucket{le="0.1"} 35
app_uptime_seconds 847
app_mode 0
chaos_active 0
```

These metrics tell you:
- How many requests have been made
- How fast responses are
- How long the app has been running
- Whether you're in stable or canary mode
- Whether chaos testing is active

### OPA: The Policy Engine

OPA (Open Policy Agent) is a separate container that acts like a security guard. Before you can deploy or promote, the CLI asks OPA: "Is it safe?"

**Why use OPA instead of checking directly in the CLI?**
1. Policies are separate from code — easier to update
2. If OPA crashes, the CLI still works (just warns you)
3. OPA is not accessible from the internet (security)

### The Two Policies

**Infrastructure Policy** (checks before deploy):
- Is there enough disk space? (must be > 10GB)
- Is the CPU overloaded? (must be < 2.0)

**Canary Safety Policy** (checks before promoting to canary):
- Is the error rate too high? (must be < 1%)
- Is the response time too slow? (P99 must be < 500ms)

### Data-Driven Thresholds

The actual numbers (10GB, 2.0, 1%, 500ms) are stored in a separate JSON file, not in the policy code. This means you can change the limits without modifying the policy logic.

**thresholds.json:**
```json
{
  "infrastructure": {
    "min_disk_gb": 10,
    "max_cpu_load": 2.0
  },
  "canary": {
    "max_error_rate": 0.01,
    "max_p99_latency_ms": 500
  }
}
```

### The Status Dashboard

The `swiftdeploy status` command shows a live dashboard:

```
╔═══════════════════════════════════════╗
║     SwiftDeploy Status Dashboard      ║
╠═══════════════════════════════════════╣
║ Mode: canary                         ║
║ Chaos: none                          ║
║ Req/s: 0.98                          ║
║ P99 Latency: 5ms                     ║
║ Error Rate: 0.00%                    ║
║ Uptime: 133s                         ║
╠═══════════════════════════════════════╣
║ Policy Compliance                    ║
║   Infrastructure: PASS               ║
║   Canary Safety:  PASS               ║
╚═══════════════════════════════════════╝
```

Every time the dashboard refreshes, it saves the data to `history.jsonl` for the audit trail.

### The Audit Report

The `swiftdeploy audit` command reads `history.jsonl` and generates `audit_report.md` with:
- A timeline of all events (mode changes, status updates)
- A list of policy violations (when checks failed)

---

## Bugs We Fixed

### Bug 1: OPA Crashed on Startup

**Problem**: OPA wouldn't start because of "conflicting rules" error.

**Cause**: We wrote `default deny := []` in the Rego file, which conflicted with `deny contains msg if { ... }`.

**Fix**: Removed the `default deny := []` line. The `contains` keyword handles empty sets automatically.

### Bug 2: OPA Couldn't Find Threshold Values

**Problem**: OPA loaded the policy files but couldn't find the threshold numbers.

**Cause**: The JSON file was in the wrong directory. OPA loads files based on their path structure.

**Fix**: Moved `thresholds.json` into a `swiftdeploy/` subdirectory so OPA could find it at the correct data path.

### Bug 3: Status Dashboard Showed "FAIL" Incorrectly

**Problem**: The dashboard showed "Infrastructure: FAIL" and "Canary Safety: FAIL" even when everything was within limits.

**Cause**: The CLI didn't send a `timestamp` field to OPA. The policy rules need `input.timestamp` to work. Without it, the rules failed, and the CLI defaulted to "FAIL".

**Fix**: Added `timestamp` to all OPA queries.

### Bug 4: Nginx Couldn't Find the API Service

**Problem**: Nginx returned 502 errors saying it couldn't resolve the API service hostname.

**Cause**: Nginx tried to find the API service at startup, but the container wasn't running yet.

**Fix**: Added Docker's internal DNS resolver (`127.0.0.11`) and used a variable for the proxy address. This tells Nginx to look up the hostname when a request comes in, not at startup.

### Bug 5: Container Didn't Update After Promoting

**Problem**: After switching to canary mode, the container was still running in stable mode.

**Cause**: Using `docker compose restart` doesn't reload environment variables from the updated docker-compose.yml.

**Fix**: Changed to `docker compose up -d --no-deps <service>`, which recreates the container with new settings.

### Bug 6: Nginx Permission Denied

**Problem**: Nginx failed to start with "Permission denied" errors.

**Cause**: We set `user: nginx` and removed all Linux capabilities, which prevented Nginx from creating necessary directories.

**Fix**: Removed the explicit user setting. The official Nginx image handles user switching internally.

---

## Key Design Decisions

### Why a Separate OPA Container?

The task required: "The CLI must not make any allow/deny decision itself."

This means:
1. The CLI asks OPA for permission before every deploy/promote
2. OPA returns "allowed" or "denied" with a reason
3. The CLI never makes the decision itself

Benefits:
- Policies can be updated without changing the CLI
- If OPA is down, the CLI warns but continues
- All decisions are logged with reasoning

### Why Data-Driven Thresholds?

The task required: "Threshold values must not be hardcoded inside Rego files."

This means the numbers (10GB, 2.0, 1%, 500ms) are in a separate JSON file, not in the policy code. This makes it easy to change limits without touching the policy logic.

### Why Separate Policy Files?

The task required: "Organise policies by domain. Each domain owns exactly one question."

This means:
- `infrastructure.rego` only checks disk and CPU
- `canary.rego` only checks error rate and latency
- Changing one policy never requires changing another

---

## How the Pieces Fit Together

```
User runs: swiftdeploy deploy
    │
    ▼
CLI gets host stats (disk, CPU)
    │
    ▼
CLI asks OPA: "Is it safe to deploy?"
    │
    ▼
OPA checks infrastructure policy
    │
    ├── If safe → Start containers
    │
    └── If not safe → Block with reason
```

```
User runs: swiftdeploy promote canary
    │
    ▼
CLI scrapes /metrics endpoint
    │
    ▼
CLI calculates error rate and P99 latency
    │
    ▼
CLI asks OPA: "Is it safe to promote?"
    │
    ▼
OPA checks canary safety policy
    │
    ├── If safe → Switch to canary mode
    │
    └── If not safe → Block with reason
```

---

## Lessons Learned

1. **One file can drive everything**: A single manifest file can generate all the configuration files you need.

2. **Policies should be separate from code**: Using OPA makes policies easier to update and test.

3. **Always handle failures gracefully**: If OPA is down, the CLI warns but continues working.

4. **Simple templates work fine**: You don't need complex template engines for configuration files.

5. **Container recreation vs restart**: Restarting a container doesn't reload environment variables. You need to recreate it.

6. **Docker DNS is important**: Nginx needs to know how to find containers by name, which requires Docker's internal DNS resolver.

---

## Summary

SwiftDeploy is a tool that:
1. Takes a single manifest file as input
2. Generates all configuration files automatically
3. Manages container lifecycle (deploy, promote, teardown)
4. Enforces safety policies via OPA before deploy/promote
5. Provides monitoring via /metrics endpoint
6. Tracks all events in an audit log

The key innovation is that everything is driven by one file, and all safety checks happen automatically before any deployment action.

---

*This article documents the development of SwiftDeploy as part of the HNG Internship DevOps Track, Stage 4.*
