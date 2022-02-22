import configparser
import copy
from datetime import datetime, timedelta
import os
import sqlite3
import statistics
import time

from flask import Flask, render_template, jsonify
from dateutil.relativedelta import relativedelta

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

def make_point(lst, x_val):
    try:
        point_mean = statistics.mean(lst)
    except statistics.StatisticsError:
        point_mean = 0
    try:
        point_variance = statistics.stdev(lst)
    except statistics.StatisticsError:
        point_variance = 0
    try:
        point_low = min(lst)
    except ValueError:
        point_low = 0
    try:
        point_high = max(lst)
    except ValueError:
        point_high = 0
    point = {
        'x': x_val,
        'y': [min(point_mean - point_variance, point_low), max(point_mean + point_variance, point_high)],
        'subvalue': {
            'range': [point_low, point_high]
        }
    }
    return point
    # return point_mean


def make_point_from_events(item_list, point_time):
    point = {}
    pings = []
    upMb_arr = []
    downMb_arr = []
    for item in item_list:
        pings.append(item['ping'])
        upMb_arr.append(item['upMb'])
        downMb_arr.append(item['downMb'])
    point['ping'] = make_point(pings, point_time)
    point['upMb'] = make_point(upMb_arr, point_time)
    point['downMb'] = make_point(downMb_arr, point_time)
    point['test_time'] = point_time
    return point

@app.route('/all/')
def return_all_points():
    items = [dict(item) for item in get_events_in_range(0,time.time())]
    convert_timestamps(items)
    return jsonify(items)

@app.route('/year/')
def return_last_year():
    points = []
    months_back = 12
    now = datetime.now()
    for i in range(months_back):
        last_month = now + relativedelta(months=-(i+1))
        last_month_start = last_month.replace(day=1,hour=0,minute=0,second=0,microsecond=0)
        last_month_end = last_month + relativedelta(day=31)
        last_month_end = last_month_end.replace(hour=23, minute=59, second=59)
        items = [dict(item) for item in get_events_in_range(
            time.mktime(last_month_start.timetuple()),
            time.mktime(last_month_end.timetuple())
        )]
        points.append(make_point_from_events(items, last_month_start))
    return jsonify(points)


@app.route('/month/')
def return_last_30():
    num_days = 31
    points = []
    now = datetime.now()
    for day_count in range(num_days):
        this_day = now - timedelta(days=day_count)
        day_events = get_events_for_day(this_day)
        items = [dict(item) for item in day_events]
        item_time = datetime.fromtimestamp(items[0]['test_time']).replace(hour=0, minute=0, second=0, microsecond=0)
        points.append(make_point_from_events(items, item_time))
    return jsonify(points)


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
