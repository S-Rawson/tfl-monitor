# tfl-monitor
To build an interface with TFL to display bus and tube times

## how to use
- go to file display_code.py and run
- you will need to amend the config_dummy.env file to your needs
- the way to find the data you need is through the functions in the files "queries_to_line_api" and "queries_to_bikepoint_api" files
- what you can do is run the default queries and it will give you dictionaries with all of the stops on a line / a list of all bikepoints
- these lines can then be used in the file "dictionary serialiser" to create the strings of the dictionaries needed for your env files
- that should be about it
- please note for speed the code runs through the two api-async files

## Ideal end result 
The touchscreen display would have at all times (refreshing every second or so) the following pieces of information
- the status of the northern line
- the ETA of the next two trains on the northern line (northbound)
- the ETA of the certaub busses
- status details from nearby "Boris Bike" stations
  - how many bikes are available
  - how many spaces are available

## Trying to run the code directly in the terminal 
ran the following in my terminal 

source /home/user/Documents/Coding_Projects/tfl-monitor/.venv/bin/activate
 /home/user/Documents/Coding_Projects/tfl-monitor/display_code.py
