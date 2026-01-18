# created on 30/10/25 by gooseberry-py on a raspberry pi 5
import httpx
import pandas as pd
import json
from datetime import datetime as dt
import logging

logger = logging.getLogger(__name__)

# Async helpers for fetching line data

# load environment variables from .env file
# load_dotenv(dotenv_path="config.env")

client = httpx.AsyncClient(
    headers={"Accept": "application/json"},
    base_url="https://api.tfl.gov.uk/",
)


def format_timedelta(td):
    # Convert to total seconds and round
    total_seconds = int(td.total_seconds())
    # Calculate minutes and remaining seconds
    minutes = total_seconds // 60
    seconds = total_seconds % 60

    if total_seconds < 0:
        minutes = 0
        seconds = 0
    return f"{minutes} m {seconds} s"


async def _get_list_modes(client):
    # Gets a list of valid modes
    # https://api-portal.tfl.gov.uk/api-details#api=Line&operation=Line_MetaModes
    all_modes = await client.get("Line/Meta/Modes")
    all_modes_clean = json.loads(all_modes.text)
    all_modes_list = []
    for item in range(len(all_modes_clean)):
        all_modes_list.append(all_modes_clean[item]["modeName"])
    return all_modes_list


async def _get_tube_lines(client, modes):
    # get tube lines
    # https://api-portal.tfl.gov.uk/api-details#api=Line&operation=Line_StatusByModeByPathModesQueryDetailQuerySeverityLevel
    tube_lines = await client.get(f"Line/Mode/{modes}/Status")
    tube_lines_clean = json.loads(tube_lines.text)
    tube_lines_list = []
    for item in range(len(tube_lines_clean)):
        tube_lines_list.append(tube_lines_clean[item]["name"])
    return tube_lines_list


async def _all_valid_routes_all_lines(client, modes):
    # Get all valid routes for all lines, including the name and id of the originating and terminating stops for each route.
    # https://api-portal.tfl.gov.uk/api-details#api=Line&operation=Line_RouteByModeByPathModesQueryServiceTypes
    service_type = "Regular"  # or 'Night'
    all_lines_routes = await client.get(
        f"Line/Mode/{modes}/Route?serviceTypes={service_type}"
    )
    all_lines_routes_clean = json.loads(all_lines_routes.text)
    return all_lines_routes_clean


async def _all_valid_routes_single_line(client, line):
    # Gets all valid routes for given line id, including the sequence of stops on each route.
    # We get the name, location, and IDs of different stops on the line
    # https://api-portal.tfl.gov.uk/api-details#api=Line&operation=Line_RouteSequenceByPathIdPathDirectionQueryServiceTypesQueryExcludeCrowding
    service_type = "Regular"  # or 'Night'
    all_routes_single = await client.get(
        f"Line/{line}/Route/Sequence/all?serviceTypes={service_type}"
    )
    all_routes_single_clean = json.loads(all_routes_single.text)
    return all_routes_single_clean


async def _get_stops_on_a_line(client, lines_to_check):
    stops_dict = {}
    for transport in lines_to_check:
        stops_on_line = await client.get(f"Line/{transport}/StopPoints")
        logger.debug(
            "stops_on_line: %s",
            str(getattr(stops_on_line, "text", stops_on_line))[:500],
        )
        stops_on_line_neat = json.loads(stops_on_line.text)
        stops = [
            {"id": item["naptanId"], "name": item["commonName"]}
            for item in stops_on_line_neat
        ]
        stops_dict[transport] = stops
    return stops_dict


async def _get_tube_status_update(client):
    # https://api-portal.tfl.gov.uk/api-details#api=Line&operation=Line_StatusByModeByPathModesQueryDetailQuerySeverityLevel
    modes = "tube"  # "bus" "dlr" are valid - try 'national-rail'
    status_dict = {}
    status_raw = await client.get(f"Line/Mode/{modes}/Status")
    if status_raw.status_code == 200:
        status_neat = json.loads(status_raw.text)
        for x in range(len(status_neat)):
            id_key = status_neat[x]["name"]
            id_body = status_neat[x]["lineStatuses"][0]["statusSeverityDescription"]
            status_dict[id_key] = id_body
        tube_line_status = pd.DataFrame.from_dict(
            status_dict, orient="index", columns=pd.Index(["Status"])
        )
        tube_line_status.reset_index(inplace=True)
        tube_line_status.rename(columns={"index": "Line"}, inplace=True)
    # Consider constructing DataFrame from records for clarity
    # rand_no = random.randint(0, 2)
    # if rand_no == 0:
    #     rand_text = "Good Service"
    # elif rand_no == 1:
    #     rand_text = "Minor Delays"
    # else:
    #     rand_text = "Severe Delays"
    # nam1 = "test line " + str(rand_no)
    # tube_line_status.loc[len(tube_line_status)] = [nam1, rand_text]

    return tube_line_status


async def _next_train_or_bus(client, tube_and_bus_stops):
    # Get the list of arrival predictions for given line ids based at the given stop
    # https://api-portal.tfl.gov.uk/api-details#api=Line&operation=Line_ArrivalsWithStopPointByPathIdsPathStopPointIdQueryDirectionQueryDestina
    next_transport_dict = {}
    # Include Line and stationName (populated from the configured YAML key) so the UI shows the human-friendly name
    eta_dashboard_cols: list[str] = [
        "modeName",
        "line",
        "stationName",
        "platformName",
        "expectedArrival",
        "TimeToArrival",
    ]
    eta_dashboard_df = pd.DataFrame(columns=pd.Index(eta_dashboard_cols))
    # Support two input shapes:
    # 1) New YAML shape: { "Station Name": { "id": "940GZZ...", "lines": ["northern", "jubilee"] }, ... }
    # 2) Legacy shape: { "Station Name": ["940GZZ...", "northern"], ... }
    for station_name, details in tube_and_bus_stops.items():
        # Normalize to station_id and list of lines
        station_id = None
        lines = []
        if isinstance(details, dict):
            station_id = details.get("id") or details.get("station_id")
            lines = details.get("lines", []) or details.get("line", [])
        elif isinstance(details, (list, tuple)) and len(details) >= 2:
            station_id = details[0]
            # legacy single-line entry -> wrap into list
            if isinstance(details[1], (list, tuple)):
                lines = list(details[1])
            else:
                lines = [details[1]]
        else:
            # Unknown shape - skip
            continue

        if not station_id or not lines:
            continue

        for line in lines:
            schedule_raw = await client.get(f"Line/{line}/Arrivals/{station_id}")
            if schedule_raw.status_code == 200:
                schedule_neat = json.loads(schedule_raw.text)
                # Use the human-friendly station_name (the dict key) as the identifier in the results
                next_transport_dict[(line, station_name)] = schedule_neat
    for y in next_transport_dict.keys():
        for z in range(len(next_transport_dict[y])):
            new_row = {}
            new_row["modeName"] = next_transport_dict[y][z]["modeName"]
            # y is the key (line, configured_station_name)
            new_row["line"] = y[0]
            # Replace API stationName with the configured human-friendly station name
            new_row["stationName"] = y[1]
            mode = next_transport_dict[y][z].get("modeName")
            if mode == "tube":
                new_row["platformName"] = next_transport_dict[y][z].get(
                    "platformName", ""
                )[:10]
            elif mode == "bus":
                new_row["platformName"] = next_transport_dict[y][z].get("lineName", "")
            new_row["expectedArrival"] = next_transport_dict[y][z]["expectedArrival"]
            # if next_transport_dict[y][z]["currentLocation"]:
            #    new_row['currentLocation'] = next_transport_dict[y][z]["currentLocation"]
            eta_dashboard_df.loc[len(eta_dashboard_df)] = new_row

    # now converting the arrival time into a datetime format
    current_dateTime = dt.now()
    eta_dashboard_df["expectedArrival"] = pd.to_datetime(
        eta_dashboard_df["expectedArrival"], format="%Y-%m-%dT%H:%M:%SZ"
    )
    eta_dashboard_df["TimeToArrival"] = (
        eta_dashboard_df["expectedArrival"] - current_dateTime
    )
    eta_dashboard_df.sort_values(
        ["modeName", "stationName", "expectedArrival"],
        ascending=[False, True, True],
        inplace=True,
    )
    # eta_dashboard_df["expectedArrival"] = eta_dashboard_df["expectedArrival"].dt.time
    # Convert timedelta to minutes and seconds format
    eta_dashboard_df["TimeToArrival"] = eta_dashboard_df["TimeToArrival"].apply(
        format_timedelta
    )
    eta_dashboard_bus = eta_dashboard_df[eta_dashboard_df["modeName"] == "bus"]
    eta_dashboard_tube = eta_dashboard_df[eta_dashboard_df["modeName"] == "tube"]
    eta_dashboard_tube_mini = eta_dashboard_tube[:4]
    eta_dashboard_combo = pd.concat(
        [eta_dashboard_tube_mini, eta_dashboard_bus], axis=0
    )
    eta_dashboard_combo.drop(["modeName", "expectedArrival"], inplace=True, axis=1)
    eta_dashboard_combo.rename(columns={"expectedArrival": "expected"}, inplace=True)
    return eta_dashboard_combo


def convert_str_to_datetime(str_data):
    # https://docs.python.org/3/library/datetime.html#format-codes
    format = "%Y-%m-%dT%H:%M:%SZ"
    datetime_str = dt.strptime(str_data, format)
    return datetime_str


# if __name__ == "__main__":
# #generic tube information functions
# list_of_modes = asyncio.run(_get_list_modes(client))
# list_of_tube_lines = asyncio.run(_get_tube_lines(client, "tube"))
# routes_all_lines = asyncio.run(_all_valid_routes_all_lines(client, "tube"))
# routes_single_line = asyncio.run(_all_valid_routes_single_line(client, 'northern'))
# # in dashboard
# tube_line_status = asyncio.run(_get_tube_status_update(client))

# #more detailed checks for my needs that will get into the dashboard
# lines_to_check = ["northern", "149", "68", "165"]
# #this tells me which stops exist on different lines but will not be used in the dashboard
# stops = asyncio.run(_get_stops_on_a_line(client, lines_to_check))

# tube_and_bus_stops = json.loads((os.getenv("tube_and_bus_stops")))
# next_tube_and_bus = asyncio.run(_next_train_or_bus(client, tube_and_bus_stops))


# print("stops")
