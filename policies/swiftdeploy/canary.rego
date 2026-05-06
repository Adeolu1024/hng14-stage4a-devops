package swiftdeploy.canary

import future.keywords.if
import future.keywords.in

deny contains msg if {
    input.error_rate > data.swiftdeploy.canary.max_error_rate
    msg := sprintf("High error rate: %.4f, maximum %.4f allowed", [input.error_rate, data.swiftdeploy.canary.max_error_rate])
}

deny contains msg if {
    input.p99_latency_ms > data.swiftdeploy.canary.max_p99_latency_ms
    msg := sprintf("High P99 latency: %dms, maximum %dms allowed", [input.p99_latency_ms, data.swiftdeploy.canary.max_p99_latency_ms])
}

allow := count(deny) == 0

decision := {
    "allowed": allow,
    "domain": "canary_safety",
    "reasons": [msg | msg = deny[_]],
    "metrics": {
        "error_rate": input.error_rate,
        "p99_latency_ms": input.p99_latency_ms,
        "window_seconds": input.window_seconds
    },
    "checked_at": input.timestamp
}
