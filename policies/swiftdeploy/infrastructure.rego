package swiftdeploy.infrastructure

import future.keywords.if
import future.keywords.in

deny contains msg if {
    input.disk_free_gb < data.swiftdeploy.thresholds.infrastructure.min_disk_gb
    msg := sprintf("Insufficient disk space: %.2fGB free, minimum %.2fGB required", [input.disk_free_gb, data.swiftdeploy.thresholds.infrastructure.min_disk_gb])
}

deny contains msg if {
    input.cpu_load > data.swiftdeploy.thresholds.infrastructure.max_cpu_load
    msg := sprintf("High CPU load: %.2f, maximum %.2f allowed", [input.cpu_load, data.swiftdeploy.thresholds.infrastructure.max_cpu_load])
}

allow := count(deny) == 0

decision := {
    "allowed": allow,
    "domain": "infrastructure",
    "reasons": [msg | msg = deny[_]],
    "checked_at": input.timestamp
}
