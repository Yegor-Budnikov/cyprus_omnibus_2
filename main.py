
from flask import Flask, jsonify
from flask import render_template
import requests
from datetime import datetime
from google.transit import gtfs_realtime_pb2
from bus_app_state import BusAppStateManager
import json
import csv
from collections import defaultdict

import threading
import time
from zoneinfo import ZoneInfo
cyprus_tz = ZoneInfo("Asia/Nicosia")


# Load your GTFS static data from earlier (mocked here)
GTFS_REALTIME_URL = "http://20.19.98.194:8328/Api/api/gtfs-realtime"

import csv
import os
from collections import defaultdict

# GTFS static paths
STATIC_DATA_FOLDERS = [
    "static_data/2_google_transit/",
    "static_data/4_google_transit/",
    "static_data/5_google_transit/",
    "static_data/6_google_transit/",
    "static_data/9_google_transit/",
    "static_data/10_google_transit/",
    "static_data/11_google_transit/"
]

ROUTES_FILE = "routes.txt"
STOPS_FILE = "stops.txt"
STOP_TIMES_FILE = "stop_times.txt"
TRIPS_FILE = "trips.txt"

# Data holders
routes_dict = {}
stops_data = []
trips_dict = {}
stop_times = defaultdict(list)

# === Load GTFS CSV (TXT) files ===

import os
import csv
from collections import defaultdict

# Constants
STATIC_DATA_FOLDERS = [
    "static_data/2_google_transit/",
    "static_data/4_google_transit/",
    "static_data/5_google_transit/",
    "static_data/6_google_transit/",
    "static_data/9_google_transit/",
    "static_data/10_google_transit/",
    "static_data/11_google_transit/"
]

ROUTES_FILE = "routes.txt"
STOPS_FILE = "stops.txt"
TRIPS_FILE = "trips.txt"
STOP_TIMES_FILE = "stop_times.txt"

# Data holders
routes_dict = {}
stops_data = []
trips_dict = {}
stop_times = defaultdict(list)

# === Load GTFS CSV (TXT) files ===
for folder in STATIC_DATA_FOLDERS:
    # --- Load Routes ---
    path = os.path.join(folder, ROUTES_FILE)
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None or "route_id" not in reader.fieldnames:
                print(f"⚠️ Skipping {path}: Missing or invalid header. Found: {reader.fieldnames}")
                continue
            for row in reader:
                routes_dict[row["route_id"]] = row
    except FileNotFoundError:
        print(f"⚠️ {ROUTES_FILE} not found in {folder}, skipping.")
    except Exception as e:
        print(f"❌ Error loading {path}: {e}")

    # --- Load Stops ---
    path = os.path.join(folder, STOPS_FILE)
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None or "stop_id" not in reader.fieldnames:
                print(f"⚠️ Skipping {path}: Missing or invalid header. Found: {reader.fieldnames}")
                continue
            for row in reader:
                stops_data.append(row)
    except FileNotFoundError:
        print(f"⚠️ {STOPS_FILE} not found in {folder}, skipping.")
    except Exception as e:
        print(f"❌ Error loading {path}: {e}")

    # --- Load Trips ---
    path = os.path.join(folder, TRIPS_FILE)
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None or "trip_id" not in reader.fieldnames:
                print(f"⚠️ Skipping {path}: Missing or invalid header. Found: {reader.fieldnames}")
                continue
            for row in reader:
                trips_dict[row["trip_id"]] = row
    except FileNotFoundError:
        print(f"⚠️ {TRIPS_FILE} not found in {folder}, skipping.")
    except Exception as e:
        print(f"❌ Error loading {path}: {e}")

    # --- Load Stop Times ---
    path = os.path.join(folder, STOP_TIMES_FILE)
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None or "trip_id" not in reader.fieldnames:
                print(f"⚠️ Skipping {path}: Missing or invalid header. Found: {reader.fieldnames}")
                continue
            for row in reader:
                try:
                    stop_times[row["trip_id"]].append({
                        "stop_id": row["stop_id"],
                        "arrival_time": row["arrival_time"],
                        "departure_time": row["departure_time"],
                        "stop_sequence": int(row["stop_sequence"])
                    })
                except KeyError as ke:
                    print(f"⚠️ Missing key in {path}: {ke}")
                except ValueError:
                    print(f"⚠️ Invalid stop_sequence in {path}: {row.get('stop_sequence')}")
    except FileNotFoundError:
        print(f"⚠️ {STOP_TIMES_FILE} not found in {folder}, skipping.")
    except Exception as e:
        print(f"❌ Error loading {path}: {e}")

# Attach sorted stop_times to each trip in trips_dict
for trip_id, times in stop_times.items():
    if trip_id in trips_dict:
        trips_dict[trip_id]["stop_times"] = sorted(times, key=lambda x: x["stop_sequence"])


app = Flask(__name__)

# Prepare static and dynamic data
static_data = {
    "routes": routes_dict,
    "stops": {stop["stop_id"]: stop for stop in stops_data},
    "trips": trips_dict,
}
live_feed_state = {"vehicles": {}}

# Initialize global state manager
state_manager = BusAppStateManager(static_data, live_feed_state)

# background job function
def schedule_feed_updates(interval=60):
    def update_loop():
        while True:
            try:
                with app.app_context():
                    print("⏰ Updating GTFS-RT feed in background...")
                    update_feed()
            except Exception as e:
                print("Feed update failed:", e)
            time.sleep(interval)

    thread = threading.Thread(target=update_loop, daemon=True)
    thread.start()


@app.route("/bus_state/update")
def update_feed():
    feed = gtfs_realtime_pb2.FeedMessage()
    response = requests.get(GTFS_REALTIME_URL)
    feed.ParseFromString(response.content)
    print(f"Feed entity count: {len(feed.entity)}")


    vehicles = {}
    for entity in feed.entity:
        vehicle_id = None
        v_info = {}

        if entity.HasField("vehicle"):
            v = entity.vehicle
            vehicle_id = v.vehicle.id
            v_info["trip_id"] = v.trip.trip_id
            v_info["timestamp"] = int(v.timestamp)
            if v.HasField("position"):
                v_info["current_position"] = (v.position.latitude, v.position.longitude)
            else:
                v_info["current_position"] = (None, None)

        if entity.HasField("trip_update"):
            trip = entity.trip_update
            vehicle_id = trip.vehicle.id if trip.HasField("vehicle") else vehicle_id or "unknown"
            v_info["trip_id"] = trip.trip.trip_id
            v_info["timestamp"] = int(trip.timestamp)
            v_info["stop_time_updates"] = [
                {
                    "stop_id": u.stop_id,
                    "arrival": {"time": u.arrival.time, "delay": u.arrival.delay},
                    "departure": {"time": u.departure.time, "delay": u.departure.delay}
                } for u in trip.stop_time_update if u.HasField("arrival") and u.HasField("departure")
            ]

        if vehicle_id:
            # Merge with any existing data
            existing = vehicles.get(vehicle_id, {})
            existing.update(v_info)
            vehicles[vehicle_id] = existing



    state_manager.live_feed_state["vehicles"] = vehicles
    return jsonify({"status": "Live feed updated", "vehicles_count": len(vehicles)})

@app.route("/bus_state/view")
def view_state():
    return jsonify(state_manager.update_every_5s(datetime.now().astimezone(cyprus_tz)))

@app.route("/bus_state/select_stop/<stop_id>")
def select_stop(stop_id):
    return jsonify(state_manager.on_select_stop(stop_id))

@app.route("/bus_state/select_bus/<vehicle_id>")
def select_bus(vehicle_id):
    return jsonify(state_manager.on_select_bus(vehicle_id))

@app.route("/bus_state/deselect")
def deselect():
    return jsonify({"message": state_manager.on_deselect()})

@app.route("/bus_stops")
def bus_stops():
    # Optional: augment with upcoming buses if available
    return jsonify({"stops": stops_data})

@app.route("/vehicle_positions")
def vehicle_positions():
    now = datetime.now().astimezone(cyprus_tz)
    snapshot = state_manager.update_every_5s(now)

    vehicles = []
    if "bus_locations" in snapshot:
        for vehicle_id, info in snapshot["bus_locations"].items():
            v = state_manager.live_feed_state["vehicles"].get(vehicle_id, {})
            updates = v.get("stop_time_updates", [])
            next_stop_id = updates[0]["stop_id"] if updates else ""
            #eta = updates[0]["stop_id"] if updates else ""

            vehicles.append({
                "vehicle_id": vehicle_id,
                "latitude": info["lat"],
                "longitude": info["lon"],
                "timestamp": info["timestamp"],
                "trip_id": v.get("trip_id"),
                "next_stop_id": next_stop_id
                #"next_stop_eta": eta
            })
    return jsonify({"vehicles": vehicles})


@app.route("/")
def home():
    return render_template("map.html")

@app.route("/admin")
def admin():
    return render_template("admin_debug.html")


if __name__ == "__main__":
    schedule_feed_updates(interval=60)
    app.run(debug=True)



