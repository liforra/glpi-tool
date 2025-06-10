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

#def ToItemType(itemtype:str):
#    processor = ["cpu", "processor","prozessor"]
#    gpu =
#    os =
#    harddrive =
#    computer =
#    computermodel = 
#    user = ["user", "benutzer", "techniti"]
#    if itemtype.lower() in processor:
#        return "Processor"

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
        except KeyError:
            log.warning(f'1404: No Result Matching {query}')
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
            required_keys = ["name", "serial", "location", "tech_user", "model"]
            #if not all(key in data for key in required_keys):
            #    log.error(f"Fehlende Daten für Computer. Benötigt: {required_keys}, Vorhanden: {data.keys()}")
            #    return # Oder eine Exception werfen
            payload = {
                "input": {
                    "name": data.get("name"),
                    "serial": data.get("serial"),
                    "locations_id": getId("Location", data.get("location")),
                    "users_id_tech": getId("User", username),
                    "groups_id_tech": 1,
                    "computermodels_id": getId("ComputerModel", data.get("model")),
                    "comment": f"\r\nThis Computer was automagically added using The GLPIClient. {username} is responsible for any wrongdoings. Added from {(os.popen('hostname').read().strip() or 'Unknown Device')}",
                    "manufacturers_id": getId("Manufacturer", data.get("manufacturer")),
                    "operatingsystems_id": getId("OperatingSystem", data.get("os")),
                    "operatingsystemversions_id": getId("OperatingSystemVersion", data.get("os_version")),
                }
            }
            log.debug(f"Payload Pre-Conversion: {payload}")
            payload = json.dumps(payload)
            log.debug(f"Payload Post-Conversion: {payload}")
            response = sendglpi(f"{api_url}/{itemtype}/", None, "POST", payload)
            log.debug(f"Response {response}")
            response = json.loads(response)
            id = response["id"]
            components = ["cpu", "processor", "gpu", "ram", "hdd"]
            if any(item in data for item in components):
                addToItemtype(id, data)
                return id
            else:
                return id

def addToItemtype(device_id, data): # "processor" part written by a human, rest extended by AI
    components = ["cpu", "processor", "gpu", "ram", "hdd"]
    for component in components:
        if component in data:
            match component:
                case "processor" | "cpu":
                    payload = json.dumps({
                        'input': {
                            'items_id': device_id,
                            'deviceprocessors_id': getId("DeviceProcessor", data.get(component)),
                            'itemtype': 'Computer'
                        }
                    })
                    sendglpi("/Item_DeviceProcessor", None, method="POST", payload=payload)
                
                case "gpu":
                    payload = json.dumps({
                        'input': {
                            'items_id': device_id,
                            'devicegraphiccards_id': getId("DeviceGraphicCard", data.get(component)),
                            'itemtype': 'Computer'
                        }
                    })
                    sendglpi("/Item_DeviceGraphicCard", None, method="POST", payload=payload)
                
                case "ram":
                    payload = json.dumps({
                        'input': {
                            'items_id': device_id,
                            'devicememories_id': getId("DeviceMemory", data.get(component)),
                            'itemtype': 'Computer'
                        }
                    })
                    sendglpi("/Item_DeviceMemory", None, method="POST", payload=payload)
                
                case "hdd":
                    payload = json.dumps({
                        'input': {
                            'items_id': device_id,
                            'deviceharddrives_id': getId("DeviceHardDrive", data.get(component)),
                            'itemtype': 'Computer'
                        }
                    })
                    sendglpi("/Item_DeviceHardDrive", None, method="POST", payload=payload)
                
                case "os":
                    payload = json.dumps({
                        'input': {
                            'operatingsystems_id': getId("OperatingSystem", data.get(component))
                        }
                    })
                    sendglpi(f"/Computer/{device_id}", None, method="PUT", payload=payload)
                case "os_version":
                    payload = json.dumps({
                        'input': {
                            'operatingsystemversions_id': getId("OperatingSystemVersion", data.get(component))
                        }
                    })
                    sendglpi(f"/Computer/{device_id}", None, method="PUT", payload=payload)

def search(mode, query): #TODO: Dont return the response, format the response nicer (maybe a list?)
    match mode:
        case "serial": # this is here incase the user wants to search for something other then the serial number  c
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
    response = str(response.content).strip('b').strip("'") # There is a random "b" at the front and the data is encapsulated in ' So this gets rid of that
    if response == '["ERROR_GLPI_LOGIN","Falscher Benutzername oder Passwort"]':
        log.error("1401: Bad Username or Password")
        return 1401
    log.debug(response)
    if response.startswith('{'): # This is a dumb way to check if its json, lets hope it doesnt break
        response = json.loads(response)
        if(response['session_token']): 
            log.info('Authentication to GLPI Sucessfull')
            session_token = response['session_token']
            username = username_param
            return [response['session_token'], remember]
        else:
            log.error('1400: Something went wrong. That\'s all we know. Check Debug Logs')
            return 1400

# --- Application ---

if __name__ == "__main__":
    attempts = 0
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Initialize with environment variable for standalone usage
    if os.getenv("APP_TOKEN"):
        init_glpi(os.getenv("APP_TOKEN"))
    else:
        log.error("APP_TOKEN environment variable not set")
        exit(1)
    
    while not session_token:
        attempts += 1
        username_input = input("Enter your Username: ")
        auth_result = auth(username_input, getpass.getpass('Password: '), confirm('Verify SSL?'), False)
        if isinstance(auth_result, list):
            session_token = auth_result[0]
        else:
            match auth_result:
                case 1401:
                    log.warning(f'Incorrect Username or Password. ({auth_result})')
                    continue
                case 1400:
                    log.error(f'Something went wrong in the Authentication. ({auth_result})')
                    break
                case _:
                    log.error(f'Something seriously went wrong in the Authentication ({auth_result})')
                    break
    
    
    
    print('1 to Search, 2 to Add a computer, 3 to Exit, 4 to find Ids of Items')
    option = input()
    match int(option):
        case 1:
            print(search("serial", input("Please Enter your Search Query: ")))
        case 3:
            killsession()
            exit()
        case 4:
            log.debug(getId(input('What Item are you looking for? '), input("Please enter the Search query: ")))
        case 2:
            test_data = {"manufacturer":"Dell","name": "GLPIAPI Test Computer","serial": "794502","os": "windows 11","os_version":"24h2","gpu": "Xe Graphics", "processor": "i5-1145G7","ram": "16 GB","hdd": "SSD 256"}
            add("Computer", test_data)
            processor = input("Please enter the processor of the Device ")
            #gpu = input("Please enter the GPU of the Deivce ")
            ram = input("Please enter the RAM of the Device ")
            os = input("Please enter the OS of the Device ")
            os_version = input("Please enter the OS Version of the Device ")
            hdd = input("Enter the drive of the Device ")
            add("Computer", {"name":input("Please enter the name of the Device"), "serial": input("Please enter the Serial Number"), "location": "Akademie", "tech_user": username, "model": input("Enter the model Pls "), "manufacturer": input("Enter the Manufacturer of the Device "), "processor": processor, "os": os, "os_version": os_version, "hdd": hdd, "ram": ram})