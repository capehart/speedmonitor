"""Prometheus exporter that runs one Ookla speedtest per scrape of /probe?server_id=N.

Scrape-triggered, like blackbox_exporter: Prometheus owns the schedule, and each test
yields exactly one sample per metric. Tests are serialized so overlapping scrapes never
compete for the link.
"""

import json
import logging
import os
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from speedmonitor import DOWNLOAD, DURATION, JITTER, LATENCY, PACKET_LOSS, SUCCESS, UPLOAD

log = logging.getLogger("speedtest_exporter")

SPEEDTEST_BIN = os.getenv("SPEEDTEST_BIN", "speedtest")
TEST_TIMEOUT = float(os.getenv("SPEEDTEST_TIMEOUT", "110"))
_test_lock = threading.Lock()


def parse_result(result: dict) -> dict[str, float]:
    """Map Ookla CLI JSON (bandwidth in bytes/s, latency in ms, loss in %) to base units."""
    metrics = {
        DOWNLOAD: result["download"]["bandwidth"] * 8,
        UPLOAD: result["upload"]["bandwidth"] * 8,
        LATENCY: result["ping"]["latency"] / 1000,
        JITTER: result["ping"]["jitter"] / 1000,
    }
    if "packetLoss" in result:
        metrics[PACKET_LOSS] = result["packetLoss"] / 100
    return metrics


def run_speedtest(server_id: str) -> dict:
    cmd = [SPEEDTEST_BIN, "--format=json", "--accept-license", "--accept-gdpr", f"--server-id={server_id}"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=TEST_TIMEOUT, check=True)
    return json.loads(proc.stdout)


def probe(server_id: str) -> dict[str, float]:
    with _test_lock:
        start = time.monotonic()
        try:
            metrics = parse_result(run_speedtest(server_id))
            metrics[SUCCESS] = 1
        except subprocess.CalledProcessError as e:
            log.warning("speedtest against %s exited %s: %s", server_id, e.returncode, e.stderr.strip())
            metrics = {SUCCESS: 0}
        except (subprocess.TimeoutExpired, json.JSONDecodeError, KeyError, TypeError) as e:
            log.warning("speedtest against %s failed: %r", server_id, e)
            metrics = {SUCCESS: 0}
        metrics[DURATION] = time.monotonic() - start
    return metrics


def render(metrics: dict[str, float]) -> str:
    return "".join(f"# TYPE {name} gauge\n{name} {value}\n" for name, value in sorted(metrics.items()))


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlparse(self.path)
        server_id = parse_qs(url.query).get("server_id", [""])[0]
        if url.path != "/probe" or not server_id.isdigit():
            self.send_error(400, "usage: /probe?server_id=<numeric Ookla server id>")
            return
        body = render(probe(server_id)).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        log.info("%s %s", self.address_string(), fmt % args)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    port = int(os.getenv("PORT", "9798"))
    log.info("listening on :%d", port)
    ThreadingHTTPServer(("", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
