# SwiftDeploy

Build the Tool That Builds the Stack.

SwiftDeploy is a declarative infrastructure CLI that generates Docker Compose and Nginx configurations from a single `manifest.yaml`, manages container lifecycles, and supports stable/canary promotions.

## Project Structure

```
.
├── manifest.yaml              # Single source of truth (only file you edit)
├── swiftdeploy                # CLI tool (Python 3)
├── Dockerfile                 # API service image
├── app/
│   ├── main.py                # Python Flask API
│   └── requirements.txt       # Python dependencies
├── templates/
│   ├── nginx.conf.j2          # Nginx config template
│   └── docker-compose.yml.j2  # Compose file template
├── nginx.conf                 # Generated (root folder)
├── docker-compose.yml         # Generated (root folder)
└── README.md                  # This file
```

## Prerequisites

- Docker Engine & Docker Compose (v2+)
- Python 3.9+ with PyYAML:
  ```bash
  pip install pyyaml
  ```

> **Windows Users**: If using PowerShell instead of WSL/Git Bash, run `python swiftdeploy <command>` instead of `./swiftdeploy <command>`.

## Quick Start

### 1. Build the API image

```bash
docker build -t swiftdeploy-keeds-api:v1.0.0 .
```

### 2. Initialize configs

```bash
./swiftdeploy init
```

This parses `manifest.yaml` and generates `nginx.conf` + `docker-compose.yml` in the **root folder**.

### 3. Validate the stack

```bash
./swiftdeploy validate
```

Performs 5 pre-flight checks:
1. `manifest.yaml` exists and is valid YAML
2. All required fields are present and non-empty
3. The Docker image exists locally
4. The Nginx host port is available
5. The generated `nginx.conf` is syntactically valid

### 4. Deploy the stack

```bash
./swiftdeploy deploy
```

Runs `init`, brings up the stack with `docker compose up -d`, and blocks until `/healthz` returns HTTP 200 (or 60s timeout).

### 5. Test the endpoints

```bash
# Welcome message (includes mode, version, timestamp)
curl http://localhost:8080/

# Health check
 curl http://localhost:8080/healthz

# Chaos (only works in canary mode)
curl -X POST http://localhost:8080/chaos \
  -H "Content-Type: application/json" \
  -d '{"mode":"slow","duration":2}'
```

### 6. Promote to canary

```bash
./swiftdeploy promote canary
```

- Updates `mode` in `manifest.yaml` in-place
- Regenerates `docker-compose.yml` with `MODE=canary`
- Restarts the API service container only
- Confirms the switch by polling `/healthz` for the `X-Mode: canary` header

### 7. Promote back to stable

```bash
./swiftdeploy promote stable
```

Reverses all canary changes.

### 8. Tear down

```bash
./swiftdeploy teardown
```

Removes all containers, networks, and volumes.

To also delete generated configs:

```bash
./swiftdeploy teardown --clean
```

## Manifest Reference

```yaml
services:
  image: swiftdeploy-keeds-api:v1.0.0   # Unique image name
  port: 5000                            # API port (unexposed directly)
  name: api-service
  version: "1.0.0"
  mode: stable                          # "stable" or "canary"

nginx:
  image: nginx:alpine
  port: 8080                            # Host & container port
  proxy_timeout: "30s"
  error_contact: "devops@swiftdeploy.local"

network:
  name: swiftdeploy-net
  driver_type: bridge

volumes:
  logs: swiftdeploy-logs

restart_policy: unless-stopped
```

## Design Decisions

- **Root-folder generation**: All generated files (`nginx.conf`, `docker-compose.yml`) are placed in the project root so the automatic grader can find them without knowing custom subfolder names.
- **Unique image name**: `swiftdeploy-keeds-api:v1.0.0` avoids collisions with other submissions.
- **Non-root containers**: The API Dockerfile creates an `appuser` (UID 1000) and drops all Linux capabilities in Compose. Nginx runs as the `nginx` user on an unprivileged port.
- **Lightweight image**: Multi-stage Alpine-based build keeps the final image well under 300 MB.
- **No direct service exposure**: The API port is never published to the host; all traffic routes through Nginx.

## Canary Behavior

- Every response includes `X-Mode: canary` header.
- `POST /chaos` is active and accepts:
  - `{ "mode": "slow", "duration": N }`
  - `{ "mode": "error", "rate": 0.5 }`
  - `{ "mode": "recover" }`

## License

HNG Internship — DevOps Track Stage 4A
