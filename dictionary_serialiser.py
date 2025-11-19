import json

dict_of_useful_tube_and_bus_stops = {
    "Clapham Common Underground Station":("940GZZLUCPC","northern"),
    'Clapham Common Station Bus 2':('490000050K',"35"),#southbound to CJ
    'Clapham Common Station Bus 4':('490000050K',"37"),#southbound to CJ
    'Clapham Common Station Bus 5':('490000050D',"155"),#northbound to Oval
    'Dorset Road Oval 1':("490006134S", "155"),#southbound to CC - dorset road stop H
    }

dict_of_useful_bikepoints = {
    "BikePoints_355":"Clapham Common Station, Clapham Common",
    "BikePoints_808":"Gauden Road, Clapham",
    "BikePoints_55":"Finsbury Circus, Liverpool Street",
    "BikePoints_603":"Caldwell Street, Stockwell"
    }

serialized_dict_of_useful_tube_and_bus_stops = json.dumps(dict_of_useful_tube_and_bus_stops)
serialized_dict_of_useful_bikepoints = json.dumps(dict_of_useful_bikepoints)
print(serialized_dict_of_useful_tube_and_bus_stops)
print(serialized_dict_of_useful_bikepoints)