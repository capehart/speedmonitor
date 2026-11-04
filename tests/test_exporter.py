import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from speedmonitor import DOWNLOAD, JITTER, LATENCY, PACKET_LOSS, SUCCESS, UPLOAD, exporter

OOKLA_RESULT = {
    "type": "result",
    "ping": {"jitter": 0.5, "latency": 3.25, "low": 3.0, "high": 4.0},
    "download": {"bandwidth": 75_000_000, "bytes": 900_000_000, "elapsed": 12000},
    "upload": {"bandwidth": 40_000_000, "bytes": 450_000_000, "elapsed": 11000},
    "packetLoss": 1.5,
    "isp": "Ting",
    "server": {"id": 70055, "host": "chvl-speedtest-02.brightspeed.com", "port": 8080},
}


@pytest.fixture
def fake_speedtest(tmp_path, monkeypatch):
    """Point the exporter at a stand-in `speedtest` script with the given body."""

    def install(script_body: str):
        path = tmp_path / "speedtest"
        path.write_text(f"#!/bin/sh\n{script_body}\n")
        path.chmod(0o755)
        monkeypatch.setattr(exporter, "SPEEDTEST_BIN", str(path))

    return install


def test_parse_result_converts_to_base_units():
    assert exporter.parse_result(OOKLA_RESULT) == {
        DOWNLOAD: 600_000_000,
        UPLOAD: 320_000_000,
        LATENCY: 0.00325,
        JITTER: 0.0005,
        PACKET_LOSS: 0.015,
    }


def test_parse_result_omits_packet_loss_when_unavailable():
    result = {k: v for k, v in OOKLA_RESULT.items() if k != "packetLoss"}
    assert PACKET_LOSS not in exporter.parse_result(result)


def test_probe_success(fake_speedtest):
    fake_speedtest(f"echo '{json.dumps(OOKLA_RESULT)}'")
    metrics = exporter.probe("70055")
    assert metrics[SUCCESS] == 1
    assert metrics[DOWNLOAD] == 600_000_000


@pytest.mark.parametrize("body", ["echo 'no servers' >&2; exit 2", "echo 'not json'", "echo '{}'"])
def test_probe_failure_reports_success_zero(fake_speedtest, body):
    fake_speedtest(body)
    metrics = exporter.probe("70055")
    assert metrics[SUCCESS] == 0
    assert DOWNLOAD not in metrics


def test_probe_timeout(fake_speedtest, monkeypatch):
    fake_speedtest("sleep 5")
    monkeypatch.setattr(exporter, "TEST_TIMEOUT", 0.2)
    assert exporter.probe("70055")[SUCCESS] == 0


def test_render_is_prometheus_text():
    assert exporter.render({SUCCESS: 1}) == f"# TYPE {SUCCESS} gauge\n{SUCCESS} 1\n"


@pytest.fixture
def server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), exporter.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


def test_http_probe(server, fake_speedtest):
    fake_speedtest(f"echo '{json.dumps(OOKLA_RESULT)}'")
    body = urllib.request.urlopen(f"{server}/probe?server_id=70055").read().decode()
    assert f"{SUCCESS} 1\n" in body


@pytest.mark.parametrize("path", ["/probe", "/probe?server_id=abc", "/metrics"])
def test_http_rejects_bad_requests(server, path):
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(server + path)
    assert e.value.code == 400
