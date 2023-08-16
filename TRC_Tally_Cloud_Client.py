import requests
import paho.mqtt.client as mqtt
import xml.etree.ElementTree as ET
import time
import json
import tkinter as tk
import os

if not os.path.exists("config.json"):
    print("configFile not found. Downloading...")
    tally_url = "https://raw.githubusercontent.com/reverendseverin/trc_tally/master/config.json"
    try:
        response = requests.get(tally_url)
        response.raise_for_status()  # Raise an exception for HTTP errors
        with open("config.json", "w") as file:
            file.write(response.text)
        print("Downloaded config.json successfully.")
    except requests.RequestException as e:
        print(f"Error downloading config.json: {e}")
        exit(1)  # Exit the program as the file is essential
# Load configurations from config.json
with open('config.json', 'r') as file:
    config = json.load(file)

mqtt_broker_ip = config['mqtt_broker_ip']
mqtt_broker_port = config['mqtt_broker_port']
tallyfile = config['tallyfile']
api_url = config['api_url']
api_refresh = config['api_refresh']

# Callback when connected successfully to the broker
def on_connect(client, userdata, flags, rc):
    print(f"Connected with result code {str(rc)}")

# Initialize MQTT client and set callback functions
client = mqtt.Client()
client.on_connect = on_connect

# Connect to the broker
client.connect(mqtt_broker_ip, mqtt_broker_port, 60)

# Check if tallyAssignments.json exists in the directory
if not os.path.exists("tallyAssignments.json"):
    print("tallyAssignments.json not found. Downloading...")
    tally_url = "https://raw.githubusercontent.com/reverendseverin/trc_tally/master/tallyAssignments.json"
    try:
        response = requests.get(tally_url)
        response.raise_for_status()  # Raise an exception for HTTP errors
        with open("tallyAssignments.json", "w") as file:
            file.write(response.text)
        print("Downloaded tallyAssignments.json successfully.")
    except requests.RequestException as e:
        print(f"Error downloading tallyAssignments.json: {e}")
        exit(1)  # Exit the program as the file is essential
# Load tally assignments (assuming this is still in JSON format)
with open(tallyfile, "r") as file:
    tally_assignments = json.load(file)

previous_active = None
previous_preview = None

# GUI Initialization
window = tk.Tk()
window.title("TRC Tally Monitor")
header = tk.Label(window, text="TRC Tally Monitor", bg="blue", fg="white", height=2, font=("Arial", 16, "bold"))
header.pack(fill=tk.X, pady=0)

# Create and pack labels for each tally
tally_labels = {}
for tally in tally_assignments:
    label = tk.Label(window, text=f"{tally['name']}: Initializing...", width=20, height=2)
    label.pack(pady=1)
    tally_labels[tally['vMixID']] = label

def update_tally_lights(active, preview):
    global previous_active, previous_preview

    # Only update if there's a change
    if active != previous_active or preview != previous_preview:
        for tally in tally_assignments:
            status = "OFF"
            font_color = "black"
            font_style = ("Arial", 10)  # Default font: not bold
            
            if tally['vMixID'] == active:
                client.publish(tally['mac'], "1")
                status = "ACTIVE"
                font_color = "red"
                font_style = ("Arial", 15, "bold")
            elif tally['vMixID'] == preview:
                client.publish(tally['mac'], "2")
                status = "PREVIEW"
                font_color = "green"
                font_style = ("Arial", 15, "bold")
            else:
                client.publish(tally['mac'], "0")
                font_style = ("Arial", 15)
                
            # Update GUI label
            tally_labels[tally['vMixID']].config(text=f"{tally['name']}: {status}", fg=font_color, font=font_style)
            print(f"Updated Tally {tally['name']} (MAC: {tally['mac']}) to {status}")

        previous_active = active
        previous_preview = preview

def poll_vmix():
    try:
        response = requests.get(api_url)
        response.raise_for_status()  # Raise an exception for HTTP errors
        root = ET.fromstring(response.content)
        
        # Extracting active and preview values
        active = int(root.find('active').text)
        preview_elem = root.find('preview')
        preview = int(preview_elem.text) if preview_elem is not None else None
        
        # Update the tally lights based on the fetched data
        update_tally_lights(active, preview)

    except requests.RequestException as e:
        print(f"Error making request: {e}. Pausing 2 seconds")
        time.sleep(2)
    except ET.ParseError:
        print("Error parsing XML")
    except (TypeError, ValueError) as e:
        print(f"Error processing XML values: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")

    window.after(api_refresh, poll_vmix)

if __name__ == '__main__':
    poll_vmix()
    window.mainloop()  # Start the GUI loop