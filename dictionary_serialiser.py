import json

dict_of_useful_tube_and_bus_stops = {
    "Blackhorse Road Underground Station":("940GZZLUBLR","victoria"),
    "King's Cross St. Pancras Underground Station":('940GZZLUKSX',"victoria"),
    'Barrhill Road':('490003598S',"45"),
    'Alderbrook Road':('490003175N', "155"),
    }

dict_of_useful_bikepoints = {
    "BikePoints_1":"River Street , Clerkenwell",
    "BikePoints_2":"Phillimore Gardens, Kensington",
    }

serialized_dict_of_useful_tube_and_bus_stops = json.dumps(dict_of_useful_tube_and_bus_stops)
serialized_dict_of_useful_bikepoints = json.dumps(dict_of_useful_bikepoints)
print(serialized_dict_of_useful_tube_and_bus_stops)
print(serialized_dict_of_useful_bikepoints)