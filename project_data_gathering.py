# created on 06/11/25 by gooseberry-py on a raspberry pi 5
import httpx
from queries_to_bikepoint_api_async import (
    get_specific_boris_bike_info,
)
from queries_to_line_api_async import (
    _get_tube_status_update,
    _next_train_or_bus,
)

# load_dotenv(dotenv_path="config_dummy.env")


async def constant_data_pull(tube_and_bus_stops, bikepoints):
    client = httpx.AsyncClient(
        headers={"Accept": "application/json"},
        base_url="https://api.tfl.gov.uk/",
    )

    data_dict = {}
    tube_line_status = await _get_tube_status_update(client)
    data_dict["tube_line_status"] = tube_line_status

    next_tube_and_bus_df = await _next_train_or_bus(client, tube_and_bus_stops)
    data_dict["next_tube_and_bus_df"] = next_tube_and_bus_df

    boris_bike_df = await get_specific_boris_bike_info(client, bikepoints)
    data_dict["boris_bike_df"] = boris_bike_df
    return data_dict


# if __name__ == "__main__":
#     env_path = Path(__file__).parent / "config.env"
#     load_dotenv(env_path)

#     tube_and_bus_stops = json.loads(os.getenv("tube_and_bus_stops"))
#     bikepoints = json.loads((os.getenv("bikepoints")))

#     data_dict = asyncio.run(constant_data_pull(tube_and_bus_stops, bikepoints))
