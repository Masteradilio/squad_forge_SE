# ForgeOS benchmark Kubernetes profile

This directory contains the PA-002 profile generator for an isolated full-
coverage run. It creates a namespace, least-privilege runner identity,
runtime-only secret references, bounded resources, a durable state PVC, an
ephemeral worktree volume, and a restricted NetworkPolicy.

Generate a profile without putting credentials in Git:

```powershell
python scripts/generate_benchmark_k8s_profile.py `
  --run-id mission-control-001 `
  --output-dir .localforge/benchmark-profile/mission-control-001 `
  --check
```

For the local Docker Desktop Kubernetes path, use the repository bootstrap after
installing Helm and enabling the `docker-desktop` Kubernetes context:

```powershell
.\scripts\start_forgeos.ps1 -Mode helm
```

The Helm path requires the runtime Secret to already exist. The script validates
the context, runs `helm lint`, and installs/upgrades the complete chart with
`--wait`; the chart starts Redis, PostgreSQL, OmniRoute, backend and frontend in
the same namespace. Compose and Helm are alternative orchestration modes and
must not be started simultaneously for the same local environment.

For Compose, set `OMNIROUTE_HOST_PORT` to an unused host port when another
OmniRoute is already running. The default is `20128`; the backend always uses
the internal service address and does not depend on this host mapping.

Before applying the generated manifest, create the runtime secret in the
generated namespace using the local secret store or an external secret
manager. The generator only emits `secretKeyRef` entries; it never accepts or
writes secret values:

```powershell
kubectl create namespace forgeos-benchmark-mission-control-001
kubectl -n forgeos-benchmark-mission-control-001 create secret generic forgeos-runtime-secrets `
  --from-literal=CONTEXT7_API_KEY="<local-value>" `
  --from-literal=OMNIROUTE_API_KEY="<local-value>"
kubectl apply -f .localforge/benchmark-profile/mission-control-001/manifest.yaml
```

The runner has no `hostPath`, privileged mode, host networking, host PID, or
host IPC. It runs as a non-root UID with a read-only root filesystem, dropped
Linux capabilities, bounded CPU/memory/ephemeral storage, a 90-minute Job
deadline, and a least-privilege namespaced Role. Worktrees are ephemeral;
state and evidence use the bounded PVC.

Cleanup must target the generated namespace exactly and is intentionally a
separate human-controlled action:

```powershell
kubectl delete namespace forgeos-benchmark-mission-control-001 --wait=true
```

The current Job command is the non-destructive `localforge doctor` smoke
entrypoint. PA-014 will replace it with the full benchmark runner only after
Redis, Helm, frontend, security, and recovery gates are implemented.
