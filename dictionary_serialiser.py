import json
import logging

logger = logging.getLogger(__name__)

tube_and_bus_stops = {
    "Clapham South Underground Station": ("940GZZLUCPS", "northern"),
    "Clapham South Bus 1": ("490000052SB", "G1"),  # northbound
    "Clapham South Bus 2": ("490000052SD", "249"),  # southbound to CJ
    "Clapham South Bus 3": ("490000052SC", "155"),  # northbound
    "Clapham South Bus 4": ("490000052SD", "155"),  # southbound to CJ
}


bikepoints = {
    "BikePoints_753": "Clapham South, Clapham South",
    "BikePoints_866": "Limburg Road, Clapham Junction",
    "BikePoints_532": "Jubilee Plaza, Canary Wharf",
    "BikePoints_551": "Import Dock, Canary Wharf",
    "BikePoints_136": "Queen Victoria Street, St. Paul's",
}

serialized_dict_of_useful_tube_and_bus_stops = json.dumps(tube_and_bus_stops)
serialized_dict_of_useful_bikepoints = json.dumps(bikepoints)
logger.info(serialized_dict_of_useful_tube_and_bus_stops)
logger.info(serialized_dict_of_useful_bikepoints)
