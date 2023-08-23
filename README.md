
# TRC Tally

This project integrates vMix's API and the Tally MA workflows to control lights via a cloud broker via MQTT requests.


## Dependencies

The TRC Tally Controller requires 2 dependencies to run.

requests is used to query the vMIX API.

paho-mqtt is utilized to send requests to the MQTT broker.

To install these dependencies, python is required. In addition the following packages are needed:

```py
  pip install requests
  pip install paho-mqtt
```

The application also requires **config.json** and **tallyassignments.json** these will automatically be added by the script so ensure you run the code in a encapsulated folder.


## Docker Setup

To install the docker container run the following line
```bash
docker run -d -p 18069:18069 -v /mosquitto.conf:/mosquitto/config/mosquitto.conf eclipse-mosquitto:latest   
```
Mosquitto.conf can be found in the repo
