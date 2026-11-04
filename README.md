# SpeedMonitor

Home network monitoring on a Raspberry Pi. It answers two questions: *was the connection down, and where?* and *what throughput am I actually getting?*

| Component | Role |
|---|---|
| [blackbox_exporter](https://github.com/prometheus/blackbox_exporter) | ICMP, DNS and HTTPS probes every 15 s |
| `speedtest` (this repo) | Runs one [Ookla CLI](https://www.speedtest.net/apps/cli) test per Prometheus scrape |
| Prometheus | Scrapes, stores (10 years / 6 GB cap), evaluates recording rules |
| Grafana | LAN-only dashboard at `http://<pi>:3000`, anonymous read-only |

## Reading the dashboard

Every probe has a `tier` label, and **Reachability by tier** shows one row per tier. The lowest tier that goes red is where the problem is:

| Tier | Targets | If it alone goes red |
|---|---|---|
| `lan` | home router (ICMP, DNS) | Router, cabling or the Pi |
| `isp` | Ting's first two hops | Ting |
| `internet` | 1.1.1.1, 8.8.8.8, 9.9.9.9, Google/Cloudflare HTTPS | Beyond Ting: peering or upstream |

A tier counts as up if *any* of its probes succeeded (`tier:probe_success:max` in [prometheus/rules.yml](prometheus/rules.yml)), so one flaky target doesn't register as an outage. **Probe failures by target** shows per-target noise.

Prometheus is also exposed on `:9090` for ad-hoc PromQL.

## Configuration

- **Probe targets**: [prometheus/prometheus.yml](prometheus/prometheus.yml). The ISP hops came from `traceroute -n 1.1.1.1` on the Pi. Re-check them if Ting re-routes.
- **Speedtests**: there are two pinned servers, one nearby and one in Ashburn, so results are comparable over time. Each is scraped every 4 h, which comes to about one test every 2 h. At current line rates each test moves about 1 GB. Find server IDs at `https://www.speedtest.net/api/js/servers?engine=js` (add `&search=<name>` to filter).
- **Grafana**: copy `.env.example` to `.env` and set `GRAFANA_ADMIN_PASSWORD`. You only need the admin login to edit. Dashboards are provisioned read-only from [grafana/dashboards](grafana/dashboards). To change one, edit it in the UI, export the JSON, and commit it.

The speedtest container runs the Ookla CLI with `--accept-license --accept-gdpr`, which accepts [Ookla's EULA](https://www.speedtest.net/about/eula). That license covers personal, non-commercial use on one computer you control, and forbids redistributing the binary or making it available to more than one device on a network. To stay within it:
- Never push the speedtest image to a registry. The Dockerfile downloads the binary at build time, so it is never committed or redistributed.
- Keep the exporter's port unpublished in `compose.yaml`. Only Prometheus should reach it, over Docker's internal network.

## Deploying to the Pi

The Pi needs Raspberry Pi OS **64-bit** (Lite is enough). This requires two quick physical visits: one to pull the SD card and one to put it back. You don't need a keyboard or monitor.

The Pi's only SD card is reflashed in place, so expect roughly 15–30 minutes of downtime.

**Prep (no downtime).** Install Imager with `brew install --cask raspberry-pi-imager`, and download the current Raspberry Pi OS Lite (64-bit) `.img.xz` into `data/`.

**Flash day.**

1. Save the final legacy database and power the Pi off:
   ```bash
   deploy/reflash.sh before
   ```
2. Pull the card, put it in the Mac, and flash it with Imager: choose *Use custom* and pick the image in `data/`. Imager skips *OS customisation* for custom images and ejects the card when it's done.
3. Re-insert the card so `bootfs` mounts, then write the first-boot config. It's a cloud-init `user-data` file that creates your user with `~/.ssh/current.ed25519.pub` (override with `SSH_PUBKEY=`), turns off password SSH, and starts SSH:
   ```bash
   deploy/reflash.sh card
   ```
4. Put the card back in the Pi and power it on. It keeps the same MAC, so DHCP should give it the same address. The first boot takes a minute or two longer while cloud-init runs.
5. Trust the new host key, copy the history over, and run [deploy/bootstrap.sh](deploy/bootstrap.sh):
   ```bash
   deploy/reflash.sh after
   ```
   The bootstrap installs Docker, clones the repo, backfills the history once, and starts the stack. To deploy a branch other than `main`, prefix the command with `BRANCH=<name>`.

To update later, re-run the bootstrap on its own:
```bash
ssh pi.internal.accapehart.com 'bash -s' < deploy/bootstrap.sh
```

## Legacy history

The previous collector (2022–2026, a cron job running `speedtest-cli` into SQLite) is backfilled by [src/speedmonitor/backfill.py](src/speedmonitor/backfill.py) as `instance="legacy"` with the test server as the `server` label. The backfill corrects three problems in the old data:

- download was stored in the `upMb` column and upload in `downMb`
- values were divided by 1024², not 10⁶
- unreachable servers recorded a 1,800,000 ms ping

Rows with that placeholder ping, or with zero throughput, become `speedtest_success 0`. The legacy collector chose a random server for each test, so its numbers are much noisier than the pinned tests.

## Development

```bash
uv run pytest
```

```bash
cp .env.example .env && docker compose up -d --build
```

Running the stack locally on a Mac works for everything except the LAN-tier semantics, since probes originate from Docker's VM.
