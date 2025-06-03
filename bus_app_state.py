
from enum import Enum
from zoneinfo import ZoneInfo
from datetime import datetime, timedelta


class AppState(Enum):
    DEFAULT = 0
    STOP_SELECTED = 1
    BUS_SELECTED = 2

class BusAppStateManager:
    def __init__(self, static_data, live_feed_state):
        self.state = AppState.DEFAULT
        self.selected_stop = None
        self.selected_bus = None
        self.highlighted_stop = None
        self.static_data = static_data
        self.live_feed_state = live_feed_state
        self.cyprus_tz = ZoneInfo("Asia/Nicosia")

    def on_select_stop(self, stop_id):
        self.selected_stop = stop_id
        self.selected_bus = None
        self.highlighted_stop = None
        self.state = AppState.STOP_SELECTED
        return self.update_stop_table(stop_id)

    def on_select_bus(self, vehicle_id):
        self.selected_bus = vehicle_id
        self.selected_stop = None
        self.highlighted_stop = None
        self.state = AppState.BUS_SELECTED
        return self.update_future_stops(vehicle_id)

    def on_select_stop_from_route(self, stop_id):
        self.highlighted_stop = stop_id
        return f"Stop {stop_id} highlighted on map"

    def on_deselect(self):
        self.selected_stop = None
        self.selected_bus = None
        self.highlighted_stop = None
        self.state = AppState.DEFAULT
        return "Deselected all. Reset to default view."

    def update_every_5s(self, current_time):
        if self.state == AppState.BUS_SELECTED:
            return self.update_future_stops(self.selected_bus, current_time)
        elif self.state == AppState.STOP_SELECTED:
            return self.update_stop_table(self.selected_stop, current_time)
        else:
            return self.update_all_bus_locations(current_time)



    def interpolate_position(self, lat1, lon1, time1, lat2, lon2, time2, now):
        dt1 = datetime.fromtimestamp(time1, self.cyprus_tz)
        dt2 = datetime.fromtimestamp(time2, self.cyprus_tz)

        if dt2 <= dt1:
            return lat1, lon1

        """Linearly interpolate position between two timestamps"""
        f = (now - dt1) / (dt2 - dt1)
        f = max(0, min(1, f))  # Clamp between 0 and 1

        lat = lat1 + f * (lat2 - lat1)
        lon = lon1 + f * (lon2 - lon1)
        return lat, lon

    def update_stop_table(self, stop_id, current_time=None):
        if not current_time:
            current_time = datetime.now().astimezone(self.cyprus_tz)

        stop_info = []
        locations = {}
        stop_data = self.static_data["stops"].get(stop_id, {})
        stop_lat = float(stop_data.get("stop_lat", 0))
        stop_lon = float(stop_data.get("stop_lon", 0))
        for vehicle_id, data in self.live_feed_state["vehicles"].items():
            for update in data.get("stop_time_updates", []):
                if update["stop_id"] == stop_id:
                    eta_dt = datetime.fromtimestamp(int(update["arrival"]["time"]), self.cyprus_tz)
                    eta_minutes = int((eta_dt - current_time).total_seconds() // 60)
                    delay_minutes = int(update["arrival"]["delay"] // 60)

                    trip_id = data.get("trip_id")
                    route_id = self.static_data["trips"].get(trip_id, {}).get("route_id", "")
                    route_number = self.static_data["routes"].get(route_id, {}).get("route_short_name", "")

                    stop_info.append({
                        "vehicle_id": vehicle_id,
                        'trip_id': trip_id,
                        'route_id': route_id,
                        "route_number": route_number,
                        "eta": eta_dt.strftime('%H:%M:%S'),
                        "eta_in_minutes": eta_minutes,
                        "delay_in_minutes": delay_minutes
                    })
                    pos = data.get("current_position", (None, None))
                    timestamp_bus = int(data.get("timestamp"))
                    timestamp_stop = int(update["arrival"]["time"])
                    approx_lat, approx_lon = self.interpolate_position(pos[0], pos[1], timestamp_bus, stop_lat, stop_lon, timestamp_stop, datetime.now().astimezone(self.cyprus_tz))
                    if pos:
                        locations[vehicle_id] = {
                            "route_number": route_number,
                            "lat": approx_lat,
                            "lon": approx_lon,
                            "timestamp": datetime.fromtimestamp(int(data.get("timestamp")), self.cyprus_tz).strftime('%H:%M:%S'),
                            "now": current_time.strftime('%H:%M:%S'),

                        }



        return {
            "now": current_time.strftime('%H:%M:%S'),
            "stop_id": stop_id,
            "stop_name": stop_data.get("stop_name", ""),
            "stop_lat": stop_lat,
            "stop_lon": stop_lon,
            "stop_table": stop_info,
            "bus_locations": locations
        }



    def update_future_stops(self, vehicle_id, current_time=None):
        vehicle_data = self.live_feed_state["vehicles"].get(vehicle_id)
        if not vehicle_data:
            return {"error": "Vehicle not found"}

        future_stops = []
        for update in vehicle_data.get("stop_time_updates", []):
            arrival_ts = int(update["arrival"]["time"])
            eta = datetime.fromtimestamp(arrival_ts, self.cyprus_tz)
            if not current_time or arrival_ts >= int(current_time.timestamp()):
                future_stops.append({
                    "stop_id": update["stop_id"],
                    "eta": eta.strftime('%H:%M:%S'),
                    "delay": int(update["arrival"]["delay"])
                })

        # ✅ Include bus location so /vehicle_positions gets it
        locations = {}
        pos = vehicle_data.get("current_position", (None, None))
        if pos:
            locations[vehicle_id] = {
                "lat": pos[0],
                "lon": pos[1],
                "timestamp": vehicle_data.get("timestamp")
            }
            return {
                "future_stops": future_stops,
                "bus_locations": locations  # ✅ critical fix
            }

        return {
            "future_stops": future_stops
        }


    def update_all_bus_locations(self, current_time):
        locations = {}
        for vehicle_id, data in self.live_feed_state["vehicles"].items():
            pos = data.get("current_position", (None, None))
            locations[vehicle_id] = {
                "lat": pos[0],
                "lon": pos[1],
                "timestamp": data.get("timestamp")
            }
        return {"bus_locations": locations}
