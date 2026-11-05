import io
import sqlite3

import pytest

from speedmonitor import DOWNLOAD, LATENCY, POOLED, SUCCESS, UPLOAD, backfill


@pytest.fixture
def legacy_db(tmp_path):
    path = tmp_path / "speedmonitor.db"
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE bandwidth(test_time INTEGER PRIMARY_KEY, ping NUMERIC, upMb NUMERIC, downMb NUMERIC, host TEXT)"
    )
    connection.executemany(
        "INSERT INTO bandwidth VALUES (?,?,?,?,?)",
        [
            (1700000900, 1800000, 12.0, 3.0, "far.example:8080"),
            (1700000000, 20.0, 500.0, 300.0, "near.example:8080"),
        ],
    )
    connection.commit()
    connection.close()
    return str(path)


def row(ping, up_mb, down_mb):
    return {"ping": ping, "upMb": up_mb, "downMb": down_mb}


def test_samples_swaps_columns_and_converts_units():
    assert backfill.samples(row(20.0, 500.0, 300.0)) == {
        SUCCESS: 1,
        DOWNLOAD: 500 * 1024**2,
        UPLOAD: 300 * 1024**2,
        LATENCY: 0.02,
    }


@pytest.mark.parametrize("bad", [row(1800000, 10, 10), row(20, 0, 10), row(20, 10, 0), row(None, 10, 10)])
def test_samples_marks_failed_tests(bad):
    assert backfill.samples(bad) == {SUCCESS: 0}


def test_convert_writes_grouped_time_ordered_openmetrics(legacy_db):
    out = io.StringIO()
    assert backfill.convert(legacy_db, out) == 2
    lines = out.getvalue().splitlines()
    near = 'job="speedtest",instance="legacy",server="near.example:8080"'
    far = 'job="speedtest",instance="legacy",server="far.example:8080"'
    assert lines[:3] == [
        f"# TYPE {SUCCESS} gauge",
        f"{SUCCESS}{{{near}}} 1 1700000000",
        f"{SUCCESS}{{{far}}} 0 1700000900",
    ]
    assert f"{DOWNLOAD}{{{near}}} {500 * 1024**2} 1700000000" in lines
    assert not any(line.startswith(DOWNLOAD) and "far.example" in line for line in lines)
    assert f'{POOLED[DOWNLOAD]}{{job="speedtest"}} {500 * 1024**2} 1700000000' in lines
    assert f'{POOLED[UPLOAD]}{{job="speedtest"}} {300 * 1024**2} 1700000000' in lines
    assert sum(line.startswith(POOLED[DOWNLOAD]) for line in lines) == 1
    assert lines[-1] == "# EOF"


def test_escape():
    assert backfill.escape('a"b\\c') == 'a\\"b\\\\c'
