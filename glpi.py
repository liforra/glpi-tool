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
    global _session_token
    if _session_token:
        sendglpi("/killSession", _session_token)

def sendglpi(endpoint, session_token=None, method="GET", payload={}):
    global _session_token, _username
    if not _app_token:
        raise RuntimeError("GLPI Library Error: init_glpi() must be called before using the API.")
    
    if session_token is None:
        session_token = _session_token
    
    if not session_token:
        raise RuntimeError("GLPI Library Error: No session token available. Please authenticate first.")
    
    url = f"{api_url}{endpoint}" if not endpoint.startswith(api_url) else endpoint
    headers = {'Content-Type': 'application/json', 'App-Token': f'{_app_token}', 'Session-Token': f'{session_token}'}
    
    log.debug(f'{method} request to {url} with payload {payload}')
    response = requests.request(method, url, headers=headers, data=payload, timeout=10)
    
    if response.status_code == 401:
        _session_token = None
        _username = None
        log.warning("Session token expired or invalid - cleared session")
    
    response.raise_for_status()
    return response.text

def restore_session(session_token, username):
    global _session_token, _username
    if not _app_token:
        raise RuntimeError("GLPI Library Error: init_glpi() must be called before using the API.")
    
    try:
        headers = {'Content-Type': 'application/json', 'App-Token': f'{_app_token}', 'Session-Token': f'{session_token}'}
        response = requests.get(f"{api_url}/getMyProfiles", headers=headers, timeout=5)
        if response.status_code == 200:
            _session_token = session_token
            _username = username
            log.info(f"Session restored for user: {username}")
            return True
        else:
            log.warning("Saved session token is invalid")
            return False
    except Exception as e:
        log.error(f"Failed to restore session: {e}")
        return False

def getId(itemtype, query):
    if not query: 
        return None
    try:
        response_str = sendglpi(f"/search/{itemtype}?criteria[0][link]=AND&criteria[0][field]=1&criteria[0][searchtype]=contains&criteria[0][value]={query}&forcedisplay=2")
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

def add(itemtype, data):
    if itemtype == "Computer":
        log.debug('Reached add: Computer')
        payload_input = {"name": data.get("name"), "serial": data.get("serial")}
        
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
        response_str = sendglpi(f"/{itemtype}/", None, "POST", payload)
        
        response_json = json.loads(response_str)
        if isinstance(response_json, dict) and "id" in response_json:
            new_id = response_json["id"]
            log.info(f"Successfully added Computer with ID: {new_id}")
            return new_id
        else:
            log.error(f"Failed to add computer. GLPI returned: {response_str}")
            raise Exception(f"Failed to add computer. GLPI returned: {response_json}")
    return None

def search(mode, query):
    if mode == "serial":
        return sendglpi(f"/search/Computer/?criteria[0][link]=AND&criteria[0][field]=5&criteria[0][searchtype]=contains&criteria[0][value]={query}")

def auth(username, password, verify, remember):
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