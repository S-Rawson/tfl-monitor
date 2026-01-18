# created on 30/10/25 by gooseberry-py on a raspberry pi 5
import requests
import pandas as pd
import json
import logging

logger = logging.getLogger(__name__)

# load environment variables from .env file
# load_dotenv(dotenv_path="config.env")


async def get_all_boris_bike_info():
    # this works even without an API key
    # Gets all bike point locations. The Place object has an addtionalProperties array which contains the nbBikes, nbDocks and nbSpaces numbers which give the status of the BikePoint. A mismatch in these numbers i.e. nbDocks - (nbBikes + nbSpaces) != 0 indicates broken docks.
    # https://api-portal.tfl.gov.uk/api-details#api=BikePoint&operation=BikePoint_GetAll
    bb_info = requests.get("https://api.tfl.gov.uk/BikePoint/")
    bikepoint_json = json.loads(bb_info.text)
    list_of_bikepoint_dict = {}
    for x in range(len(bikepoint_json)):
        list_of_bikepoint_dict[bikepoint_json[x]["id"]] = bikepoint_json[x][
            "commonName"
        ]
    # finding a specific bikepoint based on a string
    for key, body in list_of_bikepoint_dict.items():
        if "Queen Victoria" in body:
            logger.info("Found bikepoint %s: %s", key, body)
    return list_of_bikepoint_dict


async def get_specific_boris_bike_info(bikepoints):
    # Gets the bike point with the given id.
    # https://api-portal.tfl.gov.uk/api-details#api=BikePoint&operation=BikePoint_Get
    cols: list[str] = [
        "commonName",
        "NbBikes",
        "NbEmpty",
    ]
    bike_info_df = pd.DataFrame(columns=pd.Index(cols))

    for id in bikepoints.keys():
        bikepoint_info_raw = requests.get(f"https://api.tfl.gov.uk/BikePoint/{id}")
        bikepoint_info = json.loads(bikepoint_info_raw.text)
        # info from the bikepoint
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
        bike_info_df.loc[len(bike_info_df)] = new_row

    return bike_info_df


# if __name__ == "__main__":
#     # bikepoints = {
#     # "BikePoints_753":"Clapham South, Clapham South",
#     # "BikePoints_866":"Limburg Road, Clapham Junction",
#     # "BikePoints_532":"Jubilee Plaza, Canary Wharf",
#     # "BikePoints_551":"Import Dock, Canary Wharf",
#     # "BikePoints_136":"Queen Victoria Street, St. Paul's",
#     # }

#     bike_info = asyncio.run(get_specific_boris_bike_info(bikepoints))
#     test = asyncio.run(get_all_boris_bike_info())
#     rich.print(bike_info)
