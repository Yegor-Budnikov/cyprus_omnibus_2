
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


    def update_stop_table(self, stop_id, current_time=None):
        if not current_time:
            current_time = datetime.now().astimezone(self.cyprus_tz)

        stop_info = []
        locations = {}

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
                    if pos:
                        locations[vehicle_id] = {
                            "lat": pos[0],
                            "lon": pos[1],
                            "timestamp": data.get("timestamp")
                        }

        return {
            "now": current_time.strftime('%H:%M:%S'),
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
