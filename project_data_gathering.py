# created on 06/11/25 by gooseberry-py on a raspberry pi 5
import asyncio
import os
import httpx
import pandas as pd
import json
import rich
import requests
import time
from dotenv import load_dotenv
from queries_to_bikepoint_api_async import get_all_boris_bike_info, get_specific_boris_bike_info
from queries_to_line_api_async import _get_list_modes, _get_tube_lines, _all_valid_routes_all_lines, _all_valid_routes_single_line, _get_tube_status_update, _get_stops_on_a_line, _next_train_or_bus

load_dotenv(dotenv_path="config_dummy.env")


async def constant_data_pull():
    client = httpx.AsyncClient(
        headers={"Accept": "application/json"},
        base_url="https://api.tfl.gov.uk/",
    )

    data_dict = {}
    tube_line_status = await _get_tube_status_update(client)
    data_dict["tube_line_status"] = tube_line_status

    dict_of_useful_tube_and_bus_stops = json.loads(os.getenv("dict_of_useful_tube_and_bus_stops"))
    next_tube_and_bus_df = await _next_train_or_bus(client, dict_of_useful_tube_and_bus_stops)
    data_dict["next_tube_and_bus_df"] = next_tube_and_bus_df

    dict_of_useful_bikepoints = json.loads((os.getenv("dict_of_useful_bikepoints")))
    boris_bike_df = await get_specific_boris_bike_info(client, dict_of_useful_bikepoints)
    data_dict["boris_bike_df"] = boris_bike_df
    return data_dict


if __name__ == "__main__":
    data_dict = asyncio.run(constant_data_pull())


