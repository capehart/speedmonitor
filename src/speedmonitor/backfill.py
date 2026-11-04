"""Convert the legacy speedmonitor SQLite history into OpenMetrics for `promtool tsdb create-blocks-from openmetrics`.

The legacy collector stored download in the `upMb` column and upload in `downMb`, both
divided by 1024**2, so values are corrected here. Rows with speedtest-cli's 1,800,000 ms
"unreachable" ping, or a zero/missing throughput, are recorded as failed tests.
"""

import argparse
import sqlite3
import sys
from collections import defaultdict
from typing import IO

from speedmonitor import DOWNLOAD, LATENCY, SUCCESS, UPLOAD

UNREACHABLE_PING_MS = 1_800_000
MIBIT = 1024**2


def samples(row: sqlite3.Row) -> dict[str, float]:
    ping, download, upload = row["ping"], row["upMb"], row["downMb"]
    if not ping or ping >= UNREACHABLE_PING_MS or not download or not upload:
        return {SUCCESS: 0}
    return {SUCCESS: 1, DOWNLOAD: download * MIBIT, UPLOAD: upload * MIBIT, LATENCY: ping / 1000}


def escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def convert(db_path: str, out: IO[str]) -> int:
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    families = defaultdict(list)
    rows = connection.execute("SELECT test_time, ping, upMb, downMb, host FROM bandwidth ORDER BY test_time")
    count = 0
    for count, row in enumerate(rows, 1):
        labels = f'job="speedtest",instance="legacy",server="{escape(row["host"] or "unknown")}"'
        for name, value in samples(row).items():
            families[name].append(f"{name}{{{labels}}} {value} {row['test_time']}\n")
    connection.close()
    for name, lines in families.items():
        out.write(f"# TYPE {name} gauge\n")
        out.writelines(lines)
    out.write("# EOF\n")
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("db", help="path to the legacy speedmonitor.db")
    parser.add_argument("output", help="OpenMetrics file to write")
    args = parser.parse_args()
    with open(args.output, "w") as out:
        count = convert(args.db, out)
    print(f"converted {count} legacy tests to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
