import configparser
import copy
from datetime import datetime, timedelta
import os
import sqlite3
import statistics
import time

from flask import Flask, render_template, jsonify

import pprint

app = Flask(__name__)

# Set PROJECT_HOME to the contents of the environment variable if set, or this directory if not
PROJECT_HOME = os.getenv('PROJECT_HOME', os.path.dirname(os.path.abspath(__file__)))

# Read the config file based on the PROJECT_HOME
config = configparser.ConfigParser()
path = os.path.join(PROJECT_HOME, 'speedmonitor.ini')
config.read(path)

db_path = os.path.join(PROJECT_HOME, config.get('Storage','DBPath'))

def get_events_in_range(start_time: time, end_time: time):
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()
    sql = "SELECT * FROM `bandwidth` WHERE `test_time` >= ? AND `test_time` <= ?"
    cursor.execute(sql,[start_time,end_time])
    results = cursor.fetchall()
    connection.close()
    return results

def get_events_for_day(day: datetime):
    my_day = copy.copy(day)  # preserve actual 'day' just in case
    start = my_day.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(hours=24)
    return get_events_in_range(
        time.mktime(start.timetuple()),
        time.mktime(end.timetuple())
    )

def create_point_from_item(item):
    when =

def make_points_from_events(events_list):
    items = [dict(item) for item in events_list]


@app.route('/all/')
def return_all_points():
    items = [dict(item) for item in get_events_in_range(0,time.time())]
    convert_timestamps(items)
    return jsonify(items)

@app.route('/month/')
def return_last_30():
    num_days = 31
    days = []
    now = datetime.now()
    for day_count in range(num_days):
        this_day = now - timedelta(days=day_count)
        day_events = get_events_for_day(this_day)
        days.append(make_points_from_events(day_events))


@app.route('/week/')
def return_last_week():
    now = datetime.now()
    start_dt = now - timedelta(days=7)
    items = [dict(item) for item in get_events_in_range(
        time.mktime(start_dt.timetuple()),
        time.mktime(now.timetuple())
    )]
    convert_timestamps(items)
    return jsonify(items)

@app.route('/month/')
def return_last_month():
    pass

@app.route('/year/')
def return_last_year():
    pass

def convert_timestamps(datapoint_array):
    for item in datapoint_array:
        item['test_time'] = datetime.fromtimestamp(item['test_time'])

@app.route('/')
def hello_world():  # put application's code here
    end_time = time.time()
    start_time = end_time - 60 * 60 * 24 * 7  #days

    events = get_events_in_range(start_time=start_time, end_time=end_time)
    return render_template('bandwidth.html',test_instances=events, name='ac')

if __name__ == '__main__':
    app.run(host="0.0.0.0")
