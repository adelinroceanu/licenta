"""
NF Stub - simulează un Network Function 5G (AMF/SMF/UPF).
- HTTP server pe port 8080
- POST /load primește load de la conector
- GET /metrics expune metrici Prometheus
- Worker thread consumă CPU proporțional cu load
"""
import os
import time
import math
import threading
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger("nf-stub")

# === Configurație din env vars ===
NF_TYPE = os.environ.get("NF_TYPE", "amf").lower()
PORT = int(os.environ.get("PORT", "8080"))

# === State global - protejat de lock ===
state_lock = threading.Lock()
state = {
    "load_level": 0.0,        # 0.0 - 10.0, controlat extern
    "active_sessions": 0,     # numărul de sesiuni active simulate
    "total_requests": 0,      # counter cumulativ
    "total_failures": 0,      # counter cumulativ
}

# === Worker thread - consumă CPU proporțional cu load ===
        
def cpu_worker():
    """Loop care consumă CPU calculând operații matematice (busy work).
    
    Folosește un model 'duty cycle': consumă CPU intens pentru o perioadă,
    apoi doarme. Raportul este controlat de load_level (0=idle, 10=full burn).
    """
    cycle_ms = 100  # un ciclu = 100ms (busy + idle împreună)
    
    while True:
        with state_lock:
            load = state["load_level"]
        
        # load=0 -> 0% duty cycle (doar idle)
        # load=10 -> 100% duty cycle (toată CPU)
        # load=5 -> 50% duty cycle
        duty = max(0.0, min(1.0, load / 10.0))
        
        if duty < 0.01:
            time.sleep(cycle_ms / 1000.0)
            continue
        
        busy_seconds = (cycle_ms * duty) / 1000.0
        idle_seconds = (cycle_ms * (1.0 - duty)) / 1000.0
        
        # Busy phase: consumă CPU pentru busy_seconds
        end_busy = time.monotonic() + busy_seconds
        x = 1
        while time.monotonic() < end_busy:
            # Operații matematice care nu pot fi optimizate
            for _ in range(1000):
                x = (x * 1103515245 + 12345) & 0x7FFFFFFF
                x = (x * x + 1) % 1000000007
        
        # Idle phase
        if idle_seconds > 0:
            time.sleep(idle_seconds)        

# === HTTP handlers ===
class StubHandler(BaseHTTPRequestHandler):
    
    def log_message(self, format, *args):
        pass  # silence default logging
    
    def do_GET(self):
        if self.path == "/healthz":
            self._send_json(200, {"status": "ok", "nf_type": NF_TYPE})
        elif self.path == "/metrics":
            self._send_metrics()
        elif self.path == "/state":
            with state_lock:
                self._send_json(200, dict(state))
        else:
            self._send_json(404, {"error": "not found"})
    
    def do_POST(self):
        if self.path == "/load":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            try:
                data = json.loads(body)
                with state_lock:
                    if "load_level" in data:
                        state["load_level"] = float(data["load_level"])
                    if "active_sessions" in data:
                        state["active_sessions"] = int(data["active_sessions"])
                    if "total_requests" in data:
                        state["total_requests"] = int(data["total_requests"])
                    if "total_failures" in data:
                        state["total_failures"] = int(data["total_failures"])
                logger.info(f"Updated state: {data}")
                self._send_json(200, {"status": "updated"})
            except (json.JSONDecodeError, ValueError) as e:
                self._send_json(400, {"error": str(e)})
        else:
            self._send_json(404, {"error": "not found"})
    
    def _send_json(self, code, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    
    def _send_metrics(self):
        """Expune metrici în format Prometheus."""
        with state_lock:
            load = state["load_level"]
            sessions = state["active_sessions"]
            total_req = state["total_requests"]
            total_fail = state["total_failures"]
        
        # Construiește output în funcție de NF_TYPE
        # Imită numele metricilor Open5GS reale
        metrics = []
        
        if NF_TYPE == "amf":
            metrics.append("# HELP nfstub_amf_load_level Current load level (0-10)")
            metrics.append("# TYPE nfstub_amf_load_level gauge")
            metrics.append(f"nfstub_amf_load_level {load}")
            metrics.append("# HELP fivegs_amffunction_rm_reginitreq Initial registration requests")
            metrics.append("# TYPE fivegs_amffunction_rm_reginitreq counter")
            metrics.append(f"fivegs_amffunction_rm_reginitreq {total_req}")
            metrics.append("# HELP fivegs_amffunction_rm_reginitsucc Successful initial registrations")
            metrics.append("# TYPE fivegs_amffunction_rm_reginitsucc counter")
            metrics.append(f"fivegs_amffunction_rm_reginitsucc {total_req - total_fail}")
            metrics.append("# HELP amf_session Active AMF sessions")
            metrics.append("# TYPE amf_session gauge")
            metrics.append(f"amf_session {sessions}")
        
        elif NF_TYPE == "smf":
            metrics.append("# HELP nfstub_smf_load_level Current load level")
            metrics.append("# TYPE nfstub_smf_load_level gauge")
            metrics.append(f"nfstub_smf_load_level {load}")
            metrics.append("# HELP ues_active Active UEs")
            metrics.append("# TYPE ues_active gauge")
            metrics.append(f"ues_active {sessions}")
            metrics.append("# HELP pfcp_sessions_active Active PFCP sessions")
            metrics.append("# TYPE pfcp_sessions_active gauge")
            metrics.append(f"pfcp_sessions_active {sessions}")
        
        elif NF_TYPE == "upf":
            metrics.append("# HELP nfstub_upf_load_level Current load level")
            metrics.append("# TYPE nfstub_upf_load_level gauge")
            metrics.append(f"nfstub_upf_load_level {load}")
            metrics.append("# HELP fivegs_upffunction_upf_sessionnbr Active UPF sessions")
            metrics.append("# TYPE fivegs_upffunction_upf_sessionnbr gauge")
            metrics.append(f"fivegs_upffunction_upf_sessionnbr {sessions}")
            metrics.append("# HELP fivegs_ep_n3_gtp_indatapktn3upf Incoming GTP packets N3")
            metrics.append("# TYPE fivegs_ep_n3_gtp_indatapktn3upf counter")
            metrics.append(f"fivegs_ep_n3_gtp_indatapktn3upf {total_req}")
        
        body = "\n".join(metrics).encode("utf-8") + b"\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    logger.info(f"Starting NF stub: type={NF_TYPE}, port={PORT}")
    
    # Pornește worker CPU în background
    worker = threading.Thread(target=cpu_worker, daemon=True)
    worker.start()
    
    # Pornește HTTP server (blocant)
    server = HTTPServer(("0.0.0.0", PORT), StubHandler)
    logger.info(f"HTTP server listening on 0.0.0.0:{PORT}")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down")


if __name__ == "__main__":
    main()
