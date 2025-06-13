import requests
import base64
import json
import os
import getpass
import logging

# --- Application Imports ---
if __name__ == "__main__":
    import atexit


log = logging.getLogger(__name__)


# --- Statics ---
api_url = "https://ticket.akademie-awo.de/glpi/apirest.php"
app_token = None
session_token = None
username = None

def init_glpi(app_token_param):
    global app_token
    if not app_token_param or "PLEASE_REPLACE" in app_token_param:
        raise ValueError("GLPI Library Error: App-Token is missing or invalid. Please set it in glpi_config.toml.")
    app_token = app_token_param
    log.info("GLPI library initialized with an App-Token.")

# --- Basics that we should always have ---
def killsession():
    global session_token
    if session_token:
        sendglpi("/killSession", session_token)

def restore_session(session_token_param, username_param):
    global session_token, username
    if not app_token:
        raise RuntimeError("GLPI Library Error: init_glpi() must be called before using the API.")
    
    try:
        headers = {
            'Content-Type': 'application/json',
            'App-Token': f'{app_token}',
            'Session-Token': f'{session_token_param}'
        }
        response = requests.get(f"{api_url}/getMyProfiles", headers=headers, timeout=5)
        if response.status_code == 200:
            session_token = session_token_param
            username = username_param
            log.info(f"Session restored for user: {username}")
            return True
        else:
            log.warning("Saved session token is invalid")
            return False
    except Exception as e:
        log.error(f"Failed to restore session: {e}")
        return False

def confirm(question):
    valid_yes = ['y', 'yes', 'Y', 'Yes', 'YES', 'Ja', 'JA', 'ja', 'j']
    valid_no = ['n', 'no', 'N', 'No', 'NO', 'Nein', 'nein', 'NEIN']
    
    while True:
        answer = input(f"{question} (y/n): ").strip()
        if answer in valid_yes:
            return True
        elif answer in valid_no:
            return False
        else:
            log.warning("Invalid Option. (y/n)")



# --- GLPI Library ---

def sendglpi(endpoint, session_token_param=None, method="GET", payload={}):
    global session_token, username
    if not app_token:
        raise RuntimeError("GLPI Library Error: init_glpi() must be called before using the API.")
    
    if session_token_param is None:
        session_token_param = session_token
    
    if not session_token_param:
        raise RuntimeError("GLPI Library Error: No session token available. Please authenticate first.")
    
    log.debug(f'{method} request to {endpoint}, with session Token {session_token_param} and payload {payload}')
    if endpoint.startswith(api_url):
        url = f"{endpoint}"
    else:
        url = f"{api_url}{endpoint}"
    headers = {
        'Content-Type': 'application/json',
        'App-Token': f'{app_token}',
        'Session-Token': f'{session_token_param}'
    }
    response = requests.request(f"{method}", url, headers=headers, data=payload, timeout=5)
    
    if response.status_code == 401:
        session_token = None
        username = None
        log.warning("Session token expired or invalid - cleared session")
    
    if response.status_code == 404:
        raise Exception("Site not found")
    responset = response.text
    log.debug(responset)
    for letter in responset:
        if letter == "#":
            raise Exception
    return responset

def getId(itemtype, query):
    if not query:
        return None
    try:
        response = sendglpi(f"/search/{itemtype}?criteria[0][link]=AND&criteria[0][field]=1&criteria[0][searchtype]=contains&criteria[0][value]={query}&forcedisplay=2")
        if response == '["ERROR_RIGHT_MISSING","Sie haben keine ausreichenden Rechte f\\xc3\\xbcr diese Aktion."]':
            log.error(f'1403: Permission denied reading {itemtype}')
            return 1403
        response = json.loads(response)
        try:
            log.debug(f'Requested {itemtype} has ID {response['data'][0]['2']}')
            return response['data'][0]['2']
        except (KeyError, IndexError):
            log.warning(f'1404: No Result Matching {query} in {itemtype}')
            return 1404
    except Exception as e:
        log.error(f'Error getting ID for {itemtype} "{query}": {e}')
        return None

getID = getId
getid = getId

def add(itemtype, data):
    match itemtype:
        case "Computer": 
            log.debug('Reached add: Computer')
            
            payload_input = {
                "name": data.get("name"),
                "serial": data.get("serial"),
                "locations_id": getId("Location", data.get("location")),
                "users_id_tech": getId("User", username),
                "groups_id_tech": 1,
                "computermodels_id": getId("ComputerModel", data.get("model")),
                "comment" : data.get("comment"),
                "manufacturers_id": getId("Manufacturer", data.get("manufacturer")),
                "computertypes_id": getId("ComputerType", data.get("computer_type")),
                "_plugin_fields_funktionsfhigkeitfielddropdowns_id_defined": [7],
            }

            battery_health_str = data.get("battery_health")
            if battery_health_str:
                try:
                    health_value = int(battery_health_str)
                    payload_input["akkugesundheitinfield"] = health_value
                    log.debug(f"Adding custom field for battery health: {health_value} (as integer)")
                except (ValueError, TypeError):
                    log.warning(f"Could not convert battery health '{battery_health_str}' to an integer. Skipping field.")

            payload = {"input": payload_input}
            
            log.debug(f"Payload Pre-Conversion: {payload}")
            payload_json = json.dumps(payload)
            log.debug(f"Payload Post-Conversion: {payload_json}")
            
            response = sendglpi(f"/{itemtype}/", None, "POST", payload_json)
            log.debug(f"Response {response}")
            
            response_data = json.loads(response)
            computer_id = response_data.get("id")
            
            if not computer_id:
                log.error(f"Failed to create computer. Response: {response}")
                raise Exception(f"Computer creation failed: {response_data.get('message', 'Unknown error')}")

            items_to_add = ["cpu", "processor", "gpu", "ram", "hdd", "os"]
            if any(item in data for item in items_to_add):
                addToItemtype(computer_id, data)
            
            return computer_id

def addToItemtype(device_id, data):
    # 1. Handle Hardware Components
    hardware_components = ["cpu", "processor", "gpu", "ram", "hdd"]
    for component in hardware_components:
        if component in data and data.get(component):
            log.debug(f"Adding hardware component '{component}' to device ID {device_id}")
            item_payload = {'items_id': device_id, 'itemtype': 'Computer'}
            
            match component:
                case "processor" | "cpu":
                    item_payload['deviceprocessors_id'] = getId("DeviceProcessor", data.get(component))
                    endpoint = "/Item_DeviceProcessor"
                case "gpu":
                    item_payload['devicegraphiccards_id'] = getId("DeviceGraphicCard", data.get(component))
                    endpoint = "/Item_DeviceGraphicCard"
                case "ram":
                    item_payload['devicememories_id'] = getId("DeviceMemory", data.get(component))
                    endpoint = "/Item_DeviceMemory"
                case "hdd":
                    item_payload['deviceharddrives_id'] = getId("DeviceHardDrive", data.get(component))
                    endpoint = "/Item_DeviceHardDrive"
                case _:
                    continue
            
            payload = json.dumps({'input': item_payload})
            sendglpi(endpoint, None, method="POST", payload=payload)

    # 2. Handle Operating System Link
    if data.get("os"):
        log.debug(f"Linking Operating System to device ID {device_id}")
        os_id = getId("OperatingSystem", data.get("os"))
        os_version_id = getId("OperatingSystemVersion", data.get("os_version"))
        os_edition_id = getId("OperatingSystemEdition", data.get("os_edition"))  # Added this line

        if os_id and os_id not in [1403, 1404]:
            os_payload_input = {
                'items_id': device_id,
                'itemtype': 'Computer',
                'operatingsystems_id': os_id,
            }
            if os_version_id and os_version_id not in [1403, 1404]:
                os_payload_input['operatingsystemversions_id'] = os_version_id
            if os_edition_id and os_edition_id not in [1403, 1404]:  # Added this block
                os_payload_input['operatingsystemeditions_id'] = os_edition_id
            
            payload = json.dumps({'input': os_payload_input})
            sendglpi("/Item_OperatingSystem", None, method="POST", payload=payload)
        else:
            log.warning(f"Could not link Operating System because its ID could not be found for: {data.get('os')}")


def search(mode, query):
    match mode:
        case "serial":
            return(sendglpi(f"/search/Computer/?criteria[0][link]=AND&criteria[0][field]=5&criteria[0][searchtype]=contains&criteria[0][value]={query}"))
    

def auth(username_param, password, verify, remember):
    global session_token, username
    if not app_token:
        raise RuntimeError("GLPI Library Error: init_glpi() must be called before using the API.")
    
    log.debug('Reached Auth')
    log.debug(f"{username_param}, Verify: {verify}, RememberMe: {remember}")
    auth_tuple = (username_param, password)
    payload = {}
    headers = {
        'Content-Type': 'application/json',
        'App-Token': f'{app_token}',
    }
    response = requests.request("GET", f"{api_url}/initSession", headers=headers, data=payload, timeout=5, verify=verify,auth=auth_tuple)
    log.debug(response.text)
    response_text = str(response.content, 'utf-8')
    
    if 'ERROR_GLPI_LOGIN' in response_text:
        log.error("1401: Bad Username or Password")
        return 1401
        
    log.debug(response_text)
    if response_text.startswith('{'):
        response_json = json.loads(response_text)
        if 'session_token' in response_json: 
            log.info('Authentication to GLPI Successful')
            session_token = response_json['session_token']
            username = username_param
            return [response_json['session_token'], remember]
        else:
            log.error('1400: Something went wrong. Check Debug Logs')
            return 1400
    else:
        log.error(f"Unexpected auth response: {response_text}")
        return 1400

# --- Application --- (This part remains for standalone testing)
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # This is a placeholder for testing. In the GUI, the token is loaded from config.
    try:
        init_glpi("PLEASE_REPLACE_IN_CONFIG_FILE") # Replace with a valid token for testing
    except ValueError as e:
        log.error(e)
        exit(1)