"""Generate grafana/dashboards/network.json: uv run python grafana/generate.py > grafana/dashboards/network.json"""

import json, sys

DS = {"type": "prometheus", "uid": "prometheus"}
UPDOWN = [{"type": "value", "options": {"0": {"text": "Down", "color": "red"}, "1": {"text": "Up", "color": "green"}}}]
panels, y = [], 0

def row(title):
    global y
    panels.append({"type": "row", "title": title, "collapsed": False, "gridPos": {"h": 1, "w": 24, "x": 0, "y": y}, "panels": []})
    y += 1

def panel(kind, title, w, h, x, targets, unit=None, desc=None, **extra):
    p = {"type": kind, "title": title, "datasource": DS, "gridPos": {"h": h, "w": w, "x": x, "y": y},
         "targets": [{"refId": chr(65 + i), "datasource": DS, "expr": e, "legendFormat": l, **({"instant": True} if kind == "stat" else {})}
                     for i, (e, l) in enumerate(targets)],
         "fieldConfig": {"defaults": {}, "overrides": []}, "options": {}}
    if unit: p["fieldConfig"]["defaults"]["unit"] = unit
    if desc: p["description"] = desc
    for k, v in extra.items():
        if k == "defaults": p["fieldConfig"]["defaults"].update(v)
        elif k == "options": p["options"].update(v)
        else: p[k] = v
    panels.append(p)

INTERNET = 'tier:probe_success:max{tier="internet"}'

row("Now")
panel("stat", "Internet", 4, 5, 0, [(INTERNET, "")], defaults={"mappings": UPDOWN, "color": {"mode": "thresholds"},
      "thresholds": {"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "green", "value": 1}]}},
      options={"colorMode": "background", "graphMode": "none"},
      desc="Up if any internet-tier probe (ICMP, DNS or HTTPS beyond Ting) succeeded on the last scrape.")
panel("stat", "Internet downtime, last 24h", 4, 5, 4, [(f"sum_over_time((1 - {INTERNET})[24h:15s]) * 15", "")], unit="s",
      defaults={"thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "orange", "value": 60}, {"color": "red", "value": 600}]}},
      options={"colorMode": "value", "graphMode": "none"})
panel("stat", "Latency to internet", 4, 5, 8, [('tier:icmp_rtt_seconds:avg{tier="internet"}', "")], unit="s", options={"graphMode": "area"})
PLAN_BPS = 1e9  # Ting plan: 1 Gbps symmetric
panel("gauge", "Latest speedtest vs 1 Gbps plan", 12, 5, 12,
      [('last_over_time(speedtest_download_bits_per_second{instance!="legacy"}[1d])', "↓ {{server}}"),
       ('last_over_time(speedtest_upload_bits_per_second{instance!="legacy"}[1d])', "↑ {{server}}")],
      unit="bps", defaults={"min": 0, "max": PLAN_BPS, "decimals": 0,
          "thresholds": {"mode": "percentage", "steps": [{"color": "red", "value": None}, {"color": "yellow", "value": 50}, {"color": "green", "value": 80}]}},
      options={"showThresholdMarkers": True, "showThresholdLabels": False, "minVizHeight": 75},
      desc="Green at 80% of plan or better, yellow from 50%, red below. TCP overhead caps a 1 Gbps line at about 940 Mbps, so ~94% is effectively full speed.")
y += 5

row("Outages")
# Path map: each measured node is coloured by the share of its probes that succeeded over the
# dashboard's time range, and so is the line leading into it. The switch and ONT bridge traffic
# without answering probes, so they are drawn as inferred and take the colour of the next hop.
GREY, W, H = "#5f6670", 118, 40
HOPS = [  # key, label, probe instance (None = inferred), column
    ("pi", "Pi", None, 0), ("switch", "Switch (inferred)", None, 1), ("router", "Router", "192.168.1.1", 2),
    ("ont", "ONT (inferred)", None, 3), ("hop1", "Ting 64.99.112.2", "64.99.112.2", 4), ("hop2", "Ting 64.98.11.58", "64.98.11.58", 5)]
LEAVES = [("cf_dns", "1.1.1.1", "1.1.1.1"), ("google_dns", "8.8.8.8", "8.8.8.8"), ("quad9", "9.9.9.9", "9.9.9.9"),
          ("google_https", "Google HTTPS", "https://www.google.com/generate_204"),
          ("cf_https", "Cloudflare HTTPS", "https://www.cloudflare.com/cdn-cgi/trace")]
LEAF_GAP = 64
CHAIN_TOP = 24 + 2 * LEAF_GAP  # level with the middle leaf

def wire(target, field):
    return {"source": {"x": 1, "y": 0}, "target": {"x": -1, "y": 0}, "targetName": target, "path": "straight",
            "color": {"field": field, "fixed": GREY} if field else {"fixed": GREY}, "size": {"fixed": 3, "min": 1, "max": 10}}

def node(key, label, x, top, measured, wires):
    text = {"mode": "field", "field": key, "fixed": ""} if measured else {"mode": "fixed", "fixed": label}
    return [
        *([{"type": "text", "name": f"{key}_label", "config": {"text": {"mode": "fixed", "fixed": label}, "color": {"fixed": "#ccccdc"},
                                                               "size": 12, "align": "center", "valign": "bottom"},
            "constraint": {"horizontal": "left", "vertical": "top"},
            "placement": {"left": x - 16, "top": top - 20, "width": W + 32, "height": 18}}] if measured else []),
        {"type": "metric-value" if measured else "rectangle", "name": key,
         "config": {"text": text, "color": {"fixed": "#ffffff"}, "size": 14, "align": "center", "valign": "middle"},
         "background": {"color": {"field": key, "fixed": GREY} if measured else {"fixed": "transparent"}},
         "border": {"color": {"fixed": GREY}, "width": 0 if measured else 2, "radius": 6},
         "constraint": {"horizontal": "left", "vertical": "top"},
         "placement": {"left": x, "top": top, "width": W, "height": H},
         "connections": wires}]

measured = {k: inst for k, _, inst, _ in HOPS if inst} | {k: inst for k, _, inst in LEAVES}
elements = []
for i, (key, label, inst, col) in enumerate(HOPS):
    nxt = HOPS[i + 1][0] if i + 1 < len(HOPS) else None
    # A line takes the colour of the first measured node at or after its far end.
    downstream = next((k for k, _, n, _ in HOPS[i + 1:] if n), None)
    wires = [wire(nxt, downstream)] if nxt else [wire(k, k) for k, _, _ in LEAVES]
    elements += node(key, label, 16 + col * 160, CHAIN_TOP, bool(inst), wires)
for j, (key, label, _) in enumerate(LEAVES):
    elements += node(key, label, 16 + 6 * 160 + 40, 24 + j * LEAF_GAP, True, [])

panel("canvas", "Path to the internet", 24, 10, 0,
      [(f'avg(avg_over_time(probe_success{{instance="{inst}"}}[$__range]))', key) for key, inst in measured.items()],
      unit="percentunit",
      defaults={"decimals": 2, "min": 0, "max": 1, "color": {"mode": "thresholds"},
                "thresholds": {"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "yellow", "value": 0.99},
                                                             {"color": "green", "value": 0.999}]}},
      options={"inlineEditing": False, "showAdvancedTypes": True, "panZoom": False,
               "root": {"type": "frame", "name": "root", "elements": elements, "background": {"color": {"fixed": "transparent"}},
                        "border": {"color": {"fixed": "dark-green"}}, "constraint": {"horizontal": "left", "vertical": "top"}}},
      desc="Share of probes that succeeded over the selected time range, from the Pi's point of view. "
           "Read left to right: the first node that isn't green is where the path breaks. Zoom into an outage to see where it happened. "
           "The switch and ONT don't answer probes, so the lines through them take the colour of the next measured hop. Green ≥ 99.9%, yellow ≥ 99%.")
for t in panels[-1]["targets"]:
    t["instant"] = True
y += 10
panel("state-timeline", "Reachability by tier", 24, 6, 0, [("tier:probe_success:max", "{{tier}}")],
      defaults={"mappings": UPDOWN, "color": {"mode": "thresholds"},
                "thresholds": {"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "green", "value": 1}]}},
      options={"showValue": "never", "mergeValues": True, "rowHeight": 0.8},
      desc="lan = home router; isp = Ting's first hops; internet = services beyond Ting. The lowest tier that goes red is where the problem is.")
y += 6
panel("timeseries", "Ping latency by tier", 12, 8, 0, [("tier:icmp_rtt_seconds:avg", "{{tier}}")], unit="s",
      defaults={"custom": {"spanNulls": False}})
panel("timeseries", "Internet downtime per day", 12, 8, 12,
      [(f"sum_over_time((1 - {INTERNET})[1d:15s]) * 15", "downtime")], unit="s", interval="1d",
      defaults={"custom": {"drawStyle": "bars", "fillOpacity": 80}, "color": {"mode": "fixed", "fixedColor": "red"}})
y += 8
panel("timeseries", "Probe failures by target", 24, 7, 0, [("1 - probe_success", "{{job}} {{instance}}")],
      defaults={"custom": {"drawStyle": "bars", "fillOpacity": 60, "stacking": {"mode": "normal"}}, "max": 1},
      options={"legend": {"displayMode": "table", "placement": "right"}},
      desc="Spikes here without a matching tier outage are individual targets flaking, not your connection.")
y += 7

row("Throughput")
SPARSE = {"custom": {"drawStyle": "line", "showPoints": "always", "pointSize": 4, "spanNulls": 86400000}}
def band(title, metric, x, color):
    q = lambda p: f"quantile_over_time({p}, {metric}[$__interval])"
    def band_style(name, fill_to):
        return {"matcher": {"id": "byName", "options": name}, "properties": [
            {"id": "custom.lineWidth", "value": 0}, {"id": "custom.fillBelowTo", "value": fill_to},
            {"id": "custom.fillOpacity", "value": 20}, {"id": "custom.hideFrom", "value": {"legend": True, "tooltip": False, "viz": False}}]}
    def edge(name):
        return {"matcher": {"id": "byName", "options": name}, "properties": [
            {"id": "custom.lineWidth", "value": 0}, {"id": "custom.hideFrom", "value": {"legend": True, "tooltip": False, "viz": False}}]}
    panel("timeseries", title, 12, 9, x,
          [(q(0.9), "p90"), (q(0.75), "p75"), (q(0.5), "median"), (q(0.25), "p25"), (q(0.1), "p10")],
          unit="bps", interval="1d", maxDataPoints=100,
          defaults={"min": 0, "max": PLAN_BPS, "color": {"mode": "fixed", "fixedColor": color},
                    "custom": {"lineWidth": 2, "fillOpacity": 0, "showPoints": "never", "spanNulls": 3 * 86400000}},
          options={"tooltip": {"mode": "multi", "sort": "desc"}},
          desc="Median of all tests in each bucket (at least a day), with the middle 50% (p25–p75) and middle 80% (p10–p90) shaded. "
               "Data before Nov 2026 comes from the legacy collector, which picked a random server per test, so its bands are wider.")
    panels[-1]["fieldConfig"]["overrides"] = [band_style("p90", "p10"), band_style("p75", "p25"), edge("p10"), edge("p25")]

band("Download", "job:speedtest_download_bits_per_second:pooled", 0, "green")
band("Upload", "job:speedtest_upload_bits_per_second:pooled", 12, "blue")
y += 9
panel("timeseries", "Speedtest by server (live)", 16, 8, 0,
      [('avg_over_time(speedtest_download_bits_per_second{instance!="legacy"}[$__interval])', "↓ {{server}}"),
       ('avg_over_time(speedtest_upload_bits_per_second{instance!="legacy"}[$__interval])', "↑ {{server}}")],
      unit="bps", interval="4h", defaults=SPARSE)
panel("timeseries", "Speedtest failures", 8, 8, 16,
      [("sum(count_over_time(speedtest_success[$__interval]) - sum_over_time(speedtest_success[$__interval]))", "failed tests")],
      interval="4h", defaults={"custom": {"drawStyle": "bars", "fillOpacity": 80}, "color": {"mode": "fixed", "fixedColor": "orange"}})
y += 8

json.dump({"uid": "speedmonitor-network", "title": "Network health", "tags": ["speedmonitor"], "editable": False,
           "schemaVersion": 41, "time": {"from": "now-7d", "to": "now"}, "refresh": "1m",
           "timepicker": {}, "templating": {"list": []}, "annotations": {"list": []}, "panels": panels},
          sys.stdout, indent=2, ensure_ascii=False)
print()
