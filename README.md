
# TRC Tally

This project integrates vMix's API and the Tally MA workflows to control lights via a cloud broker via MQTT requests.

## App Installation
App can be found in the /app folder.

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
