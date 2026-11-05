"""Speedtest metric names shared by the live exporter and the legacy-history backfill."""

SUCCESS = "speedtest_success"
DURATION = "speedtest_duration_seconds"
DOWNLOAD = "speedtest_download_bits_per_second"
UPLOAD = "speedtest_upload_bits_per_second"
LATENCY = "speedtest_ping_latency_seconds"
JITTER = "speedtest_ping_jitter_seconds"
PACKET_LOSS = "speedtest_packet_loss_ratio"

# One sample per test with the server dropped, so percentiles pool every test in a window.
# Live values come from prometheus/rules.yml; legacy values are written by the backfill.
POOLED = {
    DOWNLOAD: "job:speedtest_download_bits_per_second:pooled",
    UPLOAD: "job:speedtest_upload_bits_per_second:pooled",
}
