# created on 30/10/25 by gooseberry-py on a raspberry pi 5
import asyncio
import ast
import os
import httpx
import rich
from dotenv import load_dotenv
import requests
import pandas as pd
import json

# load environment variables from .env file
# load_dotenv(dotenv_path="config.env")

client = httpx.AsyncClient(
    headers={"Accept": "application/json"},
    base_url="https://api.tfl.gov.uk/",
)

async def get_all_boris_bike_info(client):
    #this works even without an API key
    #Gets all bike point locations. The Place object has an addtionalProperties array which contains the nbBikes, nbDocks and nbSpaces numbers which give the status of the BikePoint. A mismatch in these numbers i.e. nbDocks - (nbBikes + nbSpaces) != 0 indicates broken docks.
    #https://api-portal.tfl.gov.uk/api-details#api=BikePoint&operation=BikePoint_GetAll
    bb_info = await client.get(f"BikePoint")
    # bb_info = requests.get(f"https://api.tfl.gov.uk/BikePoint/")
    bikepoint_json = json.loads(bb_info.text)
    list_of_bikepoint_dict = {}
    for x in range(len(bikepoint_json)):
        list_of_bikepoint_dict[bikepoint_json[x]["id"]] = bikepoint_json[x]["commonName"] 
    return list_of_bikepoint_dict


async def get_specific_boris_bike_info(client, dict_of_useful_bikepoints):
    #Gets the bike point with the given id.
    #https://api-portal.tfl.gov.uk/api-details#api=BikePoint&operation=BikePoint_Get
    bike_info_df = pd.DataFrame(columns=["commonName", "NbBikes", "NbEmpty", ])
    
    for id in dict_of_useful_bikepoints.keys():
        bikepoint_info_raw = await client.get(f"BikePoint/{id}")
        bikepoint_info = json.loads(bikepoint_info_raw.text)
        #info from the bikepoint
        new_row = {}
        # new_row["id"] = bikepoint_info["id"]
        new_row["commonName"] = bikepoint_info["commonName"]
        for x in range(len(bikepoint_info["additionalProperties"])):
            if bikepoint_info["additionalProperties"][x]["key"] == "NbBikes":
                new_row["NbBikes"] = bikepoint_info["additionalProperties"][x]["value"]
            if bikepoint_info["additionalProperties"][x]["key"] == "NbEmptyDocks":
                new_row["NbEmpty"] = bikepoint_info["additionalProperties"][x]["value"]
            # if bikepoint_info["additionalProperties"][x]["key"] == "NbDocks":
            #     new_row["NbDocks"] = bikepoint_info["additionalProperties"][x]["value"]
            # if bikepoint_info["additionalProperties"][x]["key"] == "NbStandardBikes":
            #     new_row["NbStandardBikes"] = bikepoint_info["additionalProperties"][x]["value"]
            # if bikepoint_info["additionalProperties"][x]["key"] == "NbEBikes":
            #     new_row["NbEBikes"] = bikepoint_info["additionalProperties"][x]["value"]       
        bike_info_df.loc[len(bike_info_df)] = new_row # Detian comment: same comment as the queries to api (not async) file on df.loc indexing last value.
    
    return bike_info_df

if __name__ == "__main__":

    dict_of_useful_bikepoints = json.loads((os.getenv("dict_of_useful_bikepoints")))
    bike_info = asyncio.run(get_specific_boris_bike_info(client, dict_of_useful_bikepoints))
    test = asyncio.run(get_all_boris_bike_info(client))
    rich.print(bike_info)
