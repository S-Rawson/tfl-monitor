# created on 30/10/25 by gooseberry-py on a raspberry pi 5
import asyncio
import os
import httpx
import pandas as pd
import json
import rich
import requests
from datetime import datetime as dt
from dotenv import load_dotenv

# Detian comment: again consider adding the typing to output and inputs for each function, like commented in queries_to_line_api.py

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
    #https://api-portal.tfl.gov.uk/api-details#api=Line&operation=Line_MetaModes
    all_modes = await client.get(f"Line/Meta/Modes")
    all_modes_clean = json.loads(all_modes.text)
    all_modes_list = []
    for item in range(len(all_modes_clean)):
        all_modes_list.append(all_modes_clean[item]["modeName"])
    return all_modes_list

async def _get_tube_lines(client, modes):
    # get tube lines
    #https://api-portal.tfl.gov.uk/api-details#api=Line&operation=Line_StatusByModeByPathModesQueryDetailQuerySeverityLevel
    tube_lines = await client.get(f"Line/Mode/{modes}/Status")
    tube_lines_clean = json.loads(tube_lines.text)
    tube_lines_list = []
    for item in range(len(tube_lines_clean)):
        tube_lines_list.append(tube_lines_clean[item]["name"])
    return tube_lines_list

async def _all_valid_routes_all_lines(client, modes):
    #Get all valid routes for all lines, including the name and id of the originating and terminating stops for each route.
    #https://api-portal.tfl.gov.uk/api-details#api=Line&operation=Line_RouteByModeByPathModesQueryServiceTypes
    service_type = 'Regular' # or 'Night'
    all_lines_routes = await client.get(f"Line/Mode/{modes}/Route?serviceTypes={service_type}")
    all_lines_routes_clean = json.loads(all_lines_routes.text)
    return all_lines_routes_clean

async def _all_valid_routes_single_line(client, line):
    #Gets all valid routes for given line id, including the sequence of stops on each route.
    #We get the name, location, and IDs of different stops on the line
    #https://api-portal.tfl.gov.uk/api-details#api=Line&operation=Line_RouteSequenceByPathIdPathDirectionQueryServiceTypesQueryExcludeCrowding
    service_type = 'Regular' # or 'Night'
    all_routes_single = await client.get(f"Line/{line}/Route/Sequence/all?serviceTypes={service_type}")
    all_routes_single_clean = json.loads(all_routes_single.text)   
    return all_routes_single_clean

async def _get_stops_on_a_line(client, lines_to_check):
    stops_dict = {}
    for transport in lines_to_check:
        stops_on_line = await client.get(f"Line/{transport}/StopPoints")
        rich.print(stops_on_line)
        stops_on_line_neat = json.loads(stops_on_line.text)
        stops = [{"id": item["naptanId"], "name":item["commonName"]} for item in stops_on_line_neat]
        stops_dict[transport] = stops
    return stops_dict

async def _get_tube_status_update(client):
    #https://api-portal.tfl.gov.uk/api-details#api=Line&operation=Line_StatusByModeByPathModesQueryDetailQuerySeverityLevel
    modes = "tube" #"bus" "dlr" are valid - try 'national-rail'
    status_dict = {}
    status_raw = await client.get(f"Line/Mode/{modes}/Status")
    if status_raw.status_code == 200:
        status_neat = json.loads(status_raw.text)
        for x in range(len(status_neat)):
            id_key  = status_neat[x]["name"]
            id_body = status_neat[x]["lineStatuses"][0]["statusSeverityDescription"]
            status_dict[id_key] = id_body
        tube_line_status = pd.DataFrame.from_dict(status_dict, orient='index', columns=['Status'])
        tube_line_status.reset_index(inplace=True)
        tube_line_status.rename(columns={'index':'Line'}, inplace=True)
        # Detian comment: same comments here as the comment for rows 79-85 of query_to_line_api.py, considering using list/record dictionary orientation

    return tube_line_status

async def _next_train_or_bus(client, dict_of_useful_tube_and_bus_stops):
    #Get the list of arrival predictions for given line ids based at the given stop
    #https://api-portal.tfl.gov.uk/api-details#api=Line&operation=Line_ArrivalsWithStopPointByPathIdsPathStopPointIdQueryDirectionQueryDestina
    next_transport_dict = {}
    eta_dashboard_cols = ['modeName', 'stationName', 'platformName', 'expectedArrival', "TimeToArrival"]
    eta_dashboard_df = pd.DataFrame(columns=eta_dashboard_cols)
    for station, line in dict_of_useful_tube_and_bus_stops.values():
        schedule_raw = await client.get(f"Line/{line}/Arrivals/{station}")
        if schedule_raw.status_code == 200:
            schedule_neat = json.loads(schedule_raw.text)
            station_and_direction = f'{schedule_neat[0]["stationName"]} {schedule_neat[0]["platformName"]}'
            next_transport_dict[(line, station_and_direction)] = schedule_neat
    for y in next_transport_dict.keys():
        for z in range(len(next_transport_dict[y])):
            new_row = {}
            new_row['modeName'] = next_transport_dict[y][z]["modeName"]
            if next_transport_dict[y][z]["modeName"] == "tube":
                new_row['platformName'] = next_transport_dict[y][z]["platformName"][:10]
                #shortening the name
                #short_name = next_transport_dict[y][z]["stationName"][:14].replace("Common Underground Station", "C")
                new_row['stationName'] = next_transport_dict[y][z]["stationName"][:14]
            elif next_transport_dict[y][z]["modeName"] == "bus":
                new_row['platformName'] = next_transport_dict[y][z]["lineName"]
                #shortening the name
                short_name = y[1].replace("Common Station", "C")
                new_row['stationName'] = short_name
            new_row['expectedArrival'] = next_transport_dict[y][z]["expectedArrival"]
            #if next_transport_dict[y][z]["currentLocation"]:
            #    new_row['currentLocation'] = next_transport_dict[y][z]["currentLocation"]
            eta_dashboard_df.loc[len(eta_dashboard_df)] = new_row#platformName will also be lineName # Detian comment : check indexing of the df.loc
    
    #now converting the arrival time into a datetime format
    current_dateTime = dt.now()
    eta_dashboard_df["expectedArrival"] = pd.to_datetime(eta_dashboard_df["expectedArrival"], format='%Y-%m-%dT%H:%M:%SZ')
    eta_dashboard_df["TimeToArrival"] = eta_dashboard_df["expectedArrival"] - current_dateTime
    eta_dashboard_df.sort_values(['modeName', "stationName", 'expectedArrival'], ascending=[False, True, True], inplace=True)
    #eta_dashboard_df["expectedArrival"] = eta_dashboard_df["expectedArrival"].dt.time
    # Convert timedelta to minutes and seconds format    
    eta_dashboard_df["TimeToArrival"] = eta_dashboard_df["TimeToArrival"].apply(format_timedelta)
    eta_dashboard_bus = eta_dashboard_df[eta_dashboard_df["modeName"] == "bus"]
    eta_dashboard_tube = eta_dashboard_df[eta_dashboard_df["modeName"] == "tube"]
    eta_dashboard_tube_mini = eta_dashboard_tube[:4]
    eta_dashboard_combo = pd.concat([eta_dashboard_tube_mini, eta_dashboard_bus], axis=0)
    eta_dashboard_combo.drop(["modeName", "expectedArrival"], inplace=True, axis=1)
    eta_dashboard_combo.rename(columns={"expectedArrival":"expected"}, inplace=True)
    return eta_dashboard_combo

def convert_str_to_datetime(str_data):
    #https://docs.python.org/3/library/datetime.html#format-codes
    format = '%Y-%m-%dT%H:%M:%SZ'
    datetime_str = dt.strptime(str_data, format)
    return datetime_str

#if __name__ == "__main__":
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

    # dict_of_useful_tube_and_bus_stops = json.loads((os.getenv("dict_of_useful_tube_and_bus_stops")))
    # next_tube_and_bus = asyncio.run(_next_train_or_bus(client, dict_of_useful_tube_and_bus_stops))


    #print("stops")
