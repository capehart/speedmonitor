#!/usr/bin/env python3

import time
import os
import sqlite3
import configparser
import speedtest

# Set PROJECT_HOME to the contents of the environment variable if set, or the parent directory if not
PROJECT_HOME = os.getenv('PROJECT_HOME', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Read the config file based on the PROJECT_HOME
config = configparser.ConfigParser()
path = os.path.join(PROJECT_HOME, 'speedmonitor.ini')
config.read(path)

# Get a speedtest server, and then get speedtest results
s = speedtest.Speedtest()
server = config.get('Testing','Server')  # So far, this has seemed moot. Drop it?
if server:
    try:
        s.get_servers([server])
    except Exception:
        s.get_best_server()
else:
    s.get_best_server()
s.download()
s.upload()

bits_to_megabits_factor = 1024**2
# Store the test results in the DB
db_path = os.path.join(PROJECT_HOME, config.get('Storage','DBPath'))
connection = sqlite3.connect(db_path)
cursor = connection.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS bandwidth(test_time INTEGER PRIMARY_KEY, ping NUMERIC, upMb NUMERIC, downMb NUMERIC, host TEXT)")
cursor.execute("INSERT INTO bandwidth (test_time,ping,upMb,downMb,host) VALUES(?,?,?,?,?)",
               [int(time.time()),
               s.results.dict().get('ping'),
               s.results.dict().get('download') / bits_to_megabits_factor ,
               s.results.dict().get('upload') / bits_to_megabits_factor,
               s.results.dict().get('server').get('host')])
connection.commit()