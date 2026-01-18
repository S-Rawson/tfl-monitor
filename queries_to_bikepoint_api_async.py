# created on 30/10/25 by gooseberry-py on a raspberry pi 5
import httpx
import pandas as pd
import json

# load environment variables from .env file
# load_dotenv(dotenv_path="config.env")

client = httpx.AsyncClient(
    headers={"Accept": "application/json"},
    base_url="https://api.tfl.gov.uk/",
)


async def get_all_boris_bike_info(client):
    # this works even without an API key
    # Gets all bike point locations. The Place object has an addtionalProperties array which contains the nbBikes, nbDocks and nbSpaces numbers which give the status of the BikePoint. A mismatch in these numbers i.e. nbDocks - (nbBikes + nbSpaces) != 0 indicates broken docks.
    # https://api-portal.tfl.gov.uk/api-details#api=BikePoint&operation=BikePoint_GetAll
    bb_info = await client.get("BikePoint")
    # bb_info = requests.get(f"https://api.tfl.gov.uk/BikePoint/")
    bikepoint_json = json.loads(bb_info.text)
    list_of_bikepoint_dict = {}
    for x in range(len(bikepoint_json)):
        list_of_bikepoint_dict[bikepoint_json[x]["id"]] = bikepoint_json[x]["commonName"]
    return list_of_bikepoint_dict


async def get_specific_boris_bike_info(client, bikepoints):
    # Gets the bike point with the given id.
    # https://api-portal.tfl.gov.uk/api-details#api=BikePoint&operation=BikePoint_Get
    # Add a 'location' column containing the part after the comma from commonName (e.g. "Waterloo")
    cols: list[str] = ["commonName", "location", "NbBikes", "NbEmpty"]
    bike_info_df = pd.DataFrame(columns=pd.Index(cols))

    for id in bikepoints.keys():
        bikepoint_info_raw = await client.get(f"BikePoint/{id}")
        # skip if request failed
        if bikepoint_info_raw.status_code != 200:
            continue
        bikepoint_info = json.loads(bikepoint_info_raw.text)
        # info from the bikepoint
        new_row = {}
        # Safely extract a short common name and the location suffix (text after comma)
        common = bikepoint_info.get("commonName", "")
        if common:
            parts = [p.strip() for p in common.split(",", 1)]
            new_row["commonName"] = parts[0]
            # if there's a suffix after the comma, store it in 'location', otherwise blank
            new_row["location"] = parts[1] if len(parts) > 1 else ""
        else:
            # fallback to id so the row isn't empty
            new_row["commonName"] = id
            new_row["location"] = ""

        # Pull out additional properties if present
        for prop in bikepoint_info.get("additionalProperties", []):
            key = prop.get("key")
            value = prop.get("value")
            if key == "NbBikes":
                new_row["NbBikes"] = value
            if key == "NbEmptyDocks":
                new_row["NbEmpty"] = value

        # Ensure numeric fields exist with sensible defaults
        new_row.setdefault("NbBikes", 0)
        new_row.setdefault("NbEmpty", 0)

        bike_info_df.loc[len(bike_info_df)] = new_row

    return bike_info_df
