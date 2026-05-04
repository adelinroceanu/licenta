"""
Connector pentru proiectul de licență — varianta finală.

Citește metrici din Open5GS pe host (loopback) și trimite load către pod-urile
stub din Kubernetes prin port-forward.

Mapare metrici Open5GS -> load_level pe pod-urile stub:
- AMF stub primește load proporțional cu rata de cereri Initial Registration
- SMF stub primește load proporțional cu numărul de UE-uri active (gauge)
- UPF stub primește load proporțional cu numărul de sesiuni PFCP active (gauge)

Rulează ca proces continuu pe host. Polling la 5 secunde.
"""

import time
import requests
import logging
import re
from collections import deque

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger("connector")

# === Configurație ===
POLL_INTERVAL = 5  # secunde între polluri
LOAD_LEVEL_MAX = 10.0

# Endpoints Open5GS (pe host, loopback)
OPEN5GS_ENDPOINTS = {
    "amf": "http://127.0.0.5:9090/metrics",
    "smf": "http://127.0.0.4:9090/metrics",
    "upf": "http://127.0.0.7:9090/metrics",
}

# Endpoints stub-uri din K8s (prin kubectl port-forward)
STUB_ENDPOINTS = {
    "amf": "http://localhost:18080",
    "smf": "http://localhost:18081",
    "upf": "http://localhost:18082",
}

# Calibrare — mapping de la metrici Open5GS la load_level (0-10)
# Aceste valori se ajustează experimental pe baza încărcării așteptate
CALIBRATION = {
    "amf": {
        "metric": "fivegs_amffunction_rm_reginitreq",
        "max_rate_per_sec": 1.0,  # 1 reg/s = load 10 (sensibil pentru testbed)
    },
    "smf": {
        "metric": "ues_active",
        "max_value": 5,  # 5 UE active = load 10
    },
    "upf": {
        "metric": "fivegs_upffunction_upf_sessionnbr",
        "max_value": 5,  # 5 sesiuni PFCP active = load 10
    },
}


def parse_prometheus_metric(text, metric_name):
    """Extrage valoarea unui metric Prometheus din text."""
    pattern = rf"^{re.escape(metric_name)}\s+([\d.eE+-]+)\s*$"
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#") or not line:
            continue
        match = re.match(pattern, line)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass
    return None


class MetricTracker:
    """Tracker pentru calculul ratei (delta/dt) pentru counter-uri."""
    def __init__(self):
        self.history = deque(maxlen=2)

    def update(self, value, timestamp):
        self.history.append((timestamp, value))

    def rate_per_sec(self):
        if len(self.history) < 2:
            return 0.0
        (t1, v1), (t2, v2) = self.history[0], self.history[1]
        dt = t2 - t1
        if dt <= 0:
            return 0.0
        return max(0.0, (v2 - v1) / dt)


def fetch_open5gs_metric(endpoint, metric_name):
    """Citește un metric specific de la endpoint Open5GS."""
    try:
        resp = requests.get(endpoint, timeout=3)
        resp.raise_for_status()
        return parse_prometheus_metric(resp.text, metric_name)
    except requests.RequestException as e:
        logger.warning(f"Failed to fetch {endpoint}: {e}")
        return None


def push_load_to_stub(stub_url, load_level, active_sessions=0, total_requests=0):
    """Trimite POST /load către un stub în K8s."""
    try:
        resp = requests.post(
            f"{stub_url}/load",
            json={
                "load_level": load_level,
                "active_sessions": active_sessions,
                "total_requests": total_requests,
            },
            timeout=2
        )
        return resp.status_code == 200
    except requests.RequestException as e:
        logger.warning(f"Failed to push to {stub_url}: {e}")
        return False


def main():
    logger.info("Connector starting")
    logger.info(f"Open5GS endpoints: {OPEN5GS_ENDPOINTS}")
    logger.info(f"Stub endpoints: {STUB_ENDPOINTS}")

    # Trackers pentru rate calculation pe metrici de tip counter
    trackers = {
        "amf_reginit": MetricTracker(),
    }

    while True:
        try:
            now = time.monotonic()

            # === AMF: rata de Initial Registration Requests (counter -> rate) ===
            amf_reginit = fetch_open5gs_metric(
                OPEN5GS_ENDPOINTS["amf"],
                CALIBRATION["amf"]["metric"]
            )
            ues_active_amf = fetch_open5gs_metric(
                OPEN5GS_ENDPOINTS["amf"],
                "amf_session"
            ) or 0

            if amf_reginit is not None:
                trackers["amf_reginit"].update(amf_reginit, now)
                rate = trackers["amf_reginit"].rate_per_sec()
                amf_load = min(
                    LOAD_LEVEL_MAX,
                    (rate / CALIBRATION["amf"]["max_rate_per_sec"]) * LOAD_LEVEL_MAX
                )
                push_load_to_stub(
                    STUB_ENDPOINTS["amf"],
                    load_level=amf_load,
                    active_sessions=int(ues_active_amf),
                    total_requests=int(amf_reginit),
                )
                logger.info(
                    f"AMF: reginit={amf_reginit:.0f}, rate={rate:.2f}/s, "
                    f"load={amf_load:.2f}, sessions={int(ues_active_amf)}"
                )

            # === SMF: număr UE-uri active (gauge direct) ===
            ues_active_smf = fetch_open5gs_metric(
                OPEN5GS_ENDPOINTS["smf"],
                CALIBRATION["smf"]["metric"]
            ) or 0
            smf_load = min(
                LOAD_LEVEL_MAX,
                (ues_active_smf / CALIBRATION["smf"]["max_value"]) * LOAD_LEVEL_MAX
            )
            push_load_to_stub(
                STUB_ENDPOINTS["smf"],
                load_level=smf_load,
                active_sessions=int(ues_active_smf),
            )
            logger.info(f"SMF: ues_active={ues_active_smf:.0f}, load={smf_load:.2f}")

            # === UPF: număr sesiuni PFCP active (gauge direct) ===
            upf_sessions = fetch_open5gs_metric(
                OPEN5GS_ENDPOINTS["upf"],
                CALIBRATION["upf"]["metric"]
            ) or 0
            upf_load = min(
                LOAD_LEVEL_MAX,
                (upf_sessions / CALIBRATION["upf"]["max_value"]) * LOAD_LEVEL_MAX
            )
            push_load_to_stub(
                STUB_ENDPOINTS["upf"],
                load_level=upf_load,
                active_sessions=int(upf_sessions),
            )
            logger.info(f"UPF: sessions={upf_sessions:.0f}, load={upf_load:.2f}")

        except Exception as e:
            logger.exception(f"Error in main loop: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
