# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a bachelor's thesis project: a 5G network testbed with ML-based EDoS (Economic Denial of Sustainability) attack detection. The main code lives in `~/licenta/`.

**Stack**: Open5GS (5G core, systemd) + UERANSIM (RAN simulator, C++) + Kubernetes (kind) + Python (connector, NF stubs, ML training) + Prometheus/Grafana (monitoring).

## Starting the Testbed

The full startup script (after reboot) is:
```bash
~/licenta/scripts/start-testbed.sh
```

This script: verifies Open5GS systemd services, restores NAT/iptables rules (lost on reboot), starts kubectl port-forwards for stubs (18080–18082), and launches the connector.

Then in separate terminals:
```bash
# Terminal 1 — gNB
cd ~/UERANSIM && ./build/nr-gnb -c config-licenta/gnb.yaml

# Terminal 2 — UE
cd ~/UERANSIM && sudo ./build/nr-ue -c config-licenta/ue.yaml
```

## Architecture

```
[UERANSIM gNB/UE] ──NGAP/GTP──> [Open5GS AMF/SMF/UPF on host]
                                         │ Prometheus metrics
                                         ▼
                               [connector.py (host process)]
                                         │ POST /load
                                         ▼
                         [nf-stubs namespace in K8s (kind)]
                          amf-stub:18080  smf-stub:18081  upf-stub:18082
                                         │ /metrics
                                         ▼
                              [Prometheus + Grafana in K8s]
```

### Key Components

- **`licenta/connector/connector.py`** — Runs on host, polls Open5GS Prometheus endpoints every 5s, maps real metrics to load levels (0–10), pushes via `POST /load` to K8s stub pods through port-forwards.
- **`licenta/stubs/nf-stub/app.py`** — Single Python file deployed to all three stub pods (AMF/SMF/UPF, selected by `NF_TYPE` env var). Runs an HTTP server on port 8080 with a CPU worker thread that burns CPU proportional to `load_level`. Exposes `/metrics`, `/load`, `/healthz`, `/state`.
- **`licenta/k8s/`** — Kubernetes manifests: `nf-stubs.yaml` (stub deployments + services), `open5gs-values.yaml` (Helm values for open5gs), `monitoring/` (Prometheus/Grafana stack).
- **`licenta/training/`** — ML scripts; data generators first, then trainers.
- **`UERANSIM/`** — Upstream C++ gNB/UE simulator, built with CMake.

### Network Addresses

| Service | Address |
|---------|---------|
| Open5GS AMF metrics | `http://127.0.0.5:9090/metrics` |
| Open5GS SMF metrics | `http://127.0.0.4:9090/metrics` |
| Open5GS UPF metrics | `http://127.0.0.7:9090/metrics` |
| AMF stub (port-forward) | `http://localhost:18080` |
| SMF stub (port-forward) | `http://localhost:18081` |
| UPF stub (port-forward) | `http://localhost:18082` |
| Grafana | `http://localhost:30030` (admin/admin123) |
| Prometheus | requires `kubectl port-forward` on 19090 |
| 5G UE subnet | `10.45.0.0/16` via `ogstun` |

## ML Training Scripts

Run from `~/licenta/` with the venv active (`source licenta/venv/bin/activate`):

```bash
# 1. Generate synthetic 5G traffic data
python training/generate_synthetic_data.py   # → training/data/synthetic_traffic.csv

# 2. Generate EDoS attack/legit labeled features
python training/generate_edos_data.py        # → training/data/edos_features.csv

# 3. Train GRU forecaster (TensorFlow/Keras, predicts 5-min horizon)
python training/train_gru.py                 # → training/models/gru_forecaster.h5

# 4. Train Random Forest EDoS detector (scikit-learn)
python training/train_rf.py                  # → training/models/rf_detector.pkl

# 5. Visualize predictions
python training/visualize_predictions.py
```

**GRU features**: `ue_rate`, `pdu_active`, `throughput_mbps`, `cpu_percent`, `memory_percent`. Input window 30 steps (15 min), output horizon 10 steps (5 min).

**RF features**: `req_rate`, `unique_sources`, `ip_entropy`, `reg_ratio`, `pdu_setup_ratio`, `pdu_release_ratio`, `mean_session_duration`. Binary label: 0=legit, 1=attack.

## Building UERANSIM

```bash
cd ~/UERANSIM
make          # uses cmake Release build → binaries in build/
make clean    # removes build/ and cmake-build-release/
```

Requires: cmake, g++, libsctp-dev, libssl-dev, libnl-3-dev, libnl-genl-3-dev.

## Kubernetes Operations

```bash
# Check stub pods
kubectl get pods -n nf-stubs

# Rebuild and redeploy stub image
cd ~/licenta/stubs/nf-stub
docker build -t nf-stub:v1 .
kind load docker-image nf-stub:v1 --name <cluster-name>
kubectl rollout restart deployment -n nf-stubs

# Apply K8s manifests
kubectl apply -f ~/licenta/k8s/nf-stubs.yaml
kubectl apply -f ~/licenta/k8s/monitoring/

# View connector logs
tail -f /tmp/connector.log

# View port-forward logs
tail -f /tmp/pf-amf.log /tmp/pf-smf.log /tmp/pf-upf.log
```

## Connector Calibration

In `licenta/connector/connector.py`, the `CALIBRATION` dict maps Open5GS metrics to load level 10:
- AMF: 1 Initial Registration req/s → load 10
- SMF: 5 active UEs → load 10
- UPF: 5 active PFCP sessions → load 10

Adjust these `max_rate_per_sec` / `max_value` constants to re-calibrate for observed traffic levels.

## Open5GS Services

Open5GS runs as systemd services. The relevant ones:
```bash
sudo systemctl status open5gs-amfd open5gs-smfd open5gs-upfd
sudo systemctl restart open5gs-amfd   # etc.
```

Configuration files are in `/etc/open5gs/`. Host-side YAML references in `licenta/host-setup/`.
