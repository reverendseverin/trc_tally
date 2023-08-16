import logging
from flask import Flask, Response

app = Flask(__name__)

XML_CONTENT = '''<vmix>
<version>11.0.0.16</version>
<inputs>
<input key="26cae087-b7b6-4d45-98e4-de03ab4feb6b" number="1" type="Xaml" title="NewsHD.xaml" state="Paused" position="0" duration="0" muted="True" loop="False" selectedIndex="0">
NewsHD.xaml
<text index="0" name="Headline">Hello</text>
<text index="1" name="Description">Hello</text>
</input>
<input key="55cbe357-a801-4d54-8ff2-08ee68766fae" number="2" type="VirtualSet" title="LateNightNews" state="Paused" position="0" duration="0" muted="True" loop="False" selectedIndex="0">
LateNightNews
<overlay index="0" key="2fe8ff9d-e400-4504-85ab-df7c17a1edd4"/>
<overlay index="1" key="20e4ee9a-05cc-4f58-bb69-cd179e1c1958"/>
<overlay index="2" key="94b88db0-c5cd-49d8-98a2-27d83d4bf3fe"/>
</input>
</inputs>
<overlays>
<overlay number="1"/>
<overlay number="2">1</overlay>
<overlay number="3"/>
<overlay number="4"/>
<overlay number="5"/>
<overlay number="6"/>
</overlays>
<preview>1</preview>
<active>2</active>
<fadeToBlack>False</fadeToBlack>
<transitions>
<transition number="1" effect="Fade" duration="500"/>
<transition number="2" effect="Wipe" duration="500"/>
<transition number="3" effect="Fly" duration="500"/>
<transition number="4" effect="CubeZoom" duration="3000"/>
</transitions>
<recording>False</recording>
<external>False</external>
<streaming>False</streaming>
<playList>False</playList>
<multiCorder>False</multiCorder>
</vmix>'''  # as you provided

@app.route("/")
def serve_xml():
    return Response(XML_CONTENT, mimetype='application/xml')

def update_xml_content(preview_value, active_value):
    global XML_CONTENT
    # Use the xml.etree.ElementTree module to parse and update the XML
    import xml.etree.ElementTree as ET
    root = ET.fromstring(XML_CONTENT)
    
    root.find('preview').text = str(preview_value)
    root.find('active').text = str(active_value)
    
    XML_CONTENT = ET.tostring(root, encoding="utf-8").decode("utf-8")

def cli_loop():
    while True:
        try:
            # Prompt the user for updates
            preview_value = input("Enter new value for <preview>: ")
            active_value = input("Enter new value for <active>: ")
            
            update_xml_content(preview_value, active_value)
            
            print("<preview> and <active> updated!")
        
        except Exception as e:
            print(f"An error occurred: {e}")

if __name__ == "__main__":
    import threading
    
    # Suppress Flask and Werkzeug's default log messages
    app.logger.setLevel(logging.ERROR)
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    
    # Start the Flask app on a separate thread
    flask_thread = threading.Thread(target=app.run, kwargs={'port': 8088})
    flask_thread.start()

    # Start the CLI loop in the main thread
    cli_loop()