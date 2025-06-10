import requests
import json
import os
import logging

log = logging.getLogger(__name__)

api_url = "https://ticket.akademie-awo.de/glpi/apirest.php"
_app_token = None
_session_token = None
_username = None

def init_glpi(app_token):
    global _app_token
    if not app_token or "PLEASE_REPLACE" in app_token:
        raise ValueError("GLPI Library Error: App-Token is missing or invalid. Please set it in glpi_config.toml.")
    _app_token = app_token
    log.info("GLPI library initialized with an App-Token.")

def killsession():
    if _session_token:
        sendglpi("/killSession", _session_token)

def sendglpi(endpoint:str, session_token:str, method="GET", payload={}):
    if not _app_token:
        raise RuntimeError("GLPI Library Error: init_glpi() must be called before using the API.")
    url = f"{api_url}{endpoint}" if not endpoint.startswith(api_url) else endpoint
    headers = {'Content-Type': 'application/json', 'App-Token': f'{_app_token}', 'Session-Token': f'{session_token}'}
    
    log.debug(f'{method} request to {url} with payload {payload}')
    response = requests.request(method, url, headers=headers, data=payload, timeout=10)
    response.raise_for_status() # Will raise an exception for 4xx/5xx errors
    return response.text

def getId(itemtype:str, query:str):
    if not query: return None
    try:
        response_str = sendglpi(f"/search/{itemtype}?criteria[0][link]=AND&criteria[0][field]=1&criteria[0][searchtype]=contains&criteria[0][value]={query}&forcedisplay=2", _session_token)
        response_json = json.loads(response_str)
        if response_json.get("totalcount", 0) > 0:
            item_id = response_json['data'][0]['2']
            log.debug(f'Found ID for {itemtype} "{query}": {item_id}')
            return item_id
        else:
            log.warning(f'1404: No result for {itemtype} matching "{query}"')
            return None
    except Exception as e:
        log.error(f'Error getting ID for {itemtype} "{query}": {e}')
        return None

def add(itemtype:str, data:dict):
    if itemtype == "Computer":
        log.debug('Reached add: Computer')
        payload_input = {"name": data.get("name"), "serial": data.get("serial")}
        
        # --- FIX: Only add IDs to payload if they are found ---
        mappings = {
            "locations_id": ("Location", data.get("location")),
            "users_id_tech": ("User", _username),
            "computermodels_id": ("ComputerModel", data.get("model")),
            "manufacturers_id": ("Manufacturer", data.get("manufacturer")),
            "operatingsystems_id": ("OperatingSystem", data.get("os")),
            "operatingsystemversions_id": ("OperatingSystemVersion", data.get("os_version")),
        }
        for key, (item_type, value) in mappings.items():
            item_id = getId(item_type, value)
            if item_id:
                payload_input[key] = item_id

        payload_input["comment"] = f"Automagically added by {(_username or 'Unknown User')} from {(os.popen('hostname').read().strip() or 'Unknown Device')}."
        
        payload = json.dumps({"input": payload_input})
        response_str = sendglpi(f"/{itemtype}/", _session_token, "POST", payload)
        
        # --- FIX: Properly check for success before getting ID ---
        response_json = json.loads(response_str)
        if isinstance(response_json, dict) and "id" in response_json:
            new_id = response_json["id"]
            log.info(f"Successfully added Computer with ID: {new_id}")
            # Add components if any
            # addToItemtype(new_id, data) # This can be re-enabled if needed
            return new_id
        else:
            log.error(f"Failed to add computer. GLPI returned: {response_str}")
            raise Exception(f"Failed to add computer. GLPI returned: {response_json}")
    return None

def search(mode:str, query:str):
    if mode == "serial":
        return sendglpi(f"/search/Computer/?criteria[0][link]=AND&criteria[0][field]=5&criteria[0][searchtype]=contains&criteria[0][value]={query}", _session_token)

def auth(username:str, password:str, verify:bool, remember:bool):
    global _session_token, _username
    if not _app_token:
        raise RuntimeError("GLPI Library Error: init_glpi() must be called before using the API.")
    
    headers = {'Content-Type': 'application/json', 'App-Token': f'{_app_token}'}
    response = requests.get(f"{api_url}/initSession", headers=headers, timeout=5, verify=verify, auth=(username, password))
    
    response_text = response.text
    if 'ERROR_GLPI_LOGIN' in response_text:
        log.error("1401: Bad Username or Password")
        return 1401
    
    response_json = response.json()
    if 'session_token' in response_json:
        log.info('Authentication to GLPI Successful')
        _session_token = response_json['session_token']
        _username = username
        return [response_json['session_token'], remember]
    
    log.error(f'1400: Authentication failed. Response: {response_text}')
    return 1400