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
app_token = os.getenv("APP_TOKEN")

# --- Basics that we should always have ---

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

def sendglpi(endpoint:str, session_token:str, method="GET", payload={}):
    log.debug(f'{method} request to {endpoint}, with session Token {session_token} and payload {payload}')
    if endpoint.startswith(api_url):
        url = f"{endpoint}"
    else:
        url = f"{api_url}{endpoint}"
    headers = {
        'Content-Type': 'application/json',
        'App-Token': f'{app_token}',
        'Session-Token': f'{session_token}'
    }
    #return requests.request("GET", url, headers=headers, data=payload, timeout=5, verify=verify,auth=auth)
    response = requests.request(f"{method}", url, headers=headers, data=payload, timeout=5)
    if response.status_code == 404:
        raise Exception("Site not found")
    responset = response.text
    #response = str(response.content).strip('b').strip("'")
    log.debug(responset)
    
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

def getId(itemtype:str, query:str):
    #ToItemType(itemtype)
    response = sendglpi(f"/search/{itemtype}?criteria[0][link]=AND&criteria[0][field]=1&criteria[0][searchtype]=contains&criteria[0][value]={query}&forcedisplay=2", session_token)
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
getID = getId
getid = getId
def add(itemtype:str, data:dict):
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
                    "users_id_tech": getId("User", data.get("tech_user")),
                    "groups_id_tech": 1,
                    "computermodels_id": getId("ComputerModel", data.get("model")),
                    "comment": f"\r\nThis Computer was automagically added using The GLPIClient. {username} is responsible for any wrongdoings. Added from {(os.popen('hostname').read().strip() or 'Unknown Device')}",
                    "manufacturers_id": getId("Manufacturer", data.get("manufacturer"))
                }
            }
            log.debug(f"Payload Pre-Conversion: {payload}")
            payload = json.dumps(payload)
            log.debug(f"Payload Post-Conversion: {payload}")
            response = sendglpi(f"{api_url}/{itemtype}/", session_token, "POST", payload)
            log.debug(f"Response {response}")
            response = json.loads(response)
            id = response["id"]
            components = ["cpu", "processor", "gpu", "ram", "hdd", "os", "os_version"]
            if any(item in data for item in components):
                addToItemtype(id, data)
            else:
                return id
def addToItemtype(device_id: int, data: dict):
    # What each component type maps to in GLPI
    component_mappings = {
        "processor": ("Processor", "processors_id"),
        "cpu": ("Processor", "processors_id"), 
        "gpu": ("GraphicCard", "graphiccards_id"),
        "ram": ("Memory", "memories_id"),
        "hdd": ("HardDrive", "harddrives_id"),
        "os": ("OperatingSystem", "operatingsystems_id"),
        "os_version": ("OperatingSystemVersion", "operatingsystemversions_id"),
    }
    
    components_to_update = {}
    
    # Process each component in the data
    for component_type, component_name in data.items():
        # Clean up the key (remove spaces, underscores, make lowercase)
        clean_type = component_type.lower().replace(" ", "").replace("_", "")
        
        # Check if we know how to handle this component type
        if clean_type not in component_mappings:
            log.warning(f"Don't know how to handle component type: {component_type}")
            continue
        
        # Get GLPI info for this component type
        glpi_itemtype, glpi_field_name = component_mappings[clean_type]
        
        # Search for this specific component in GLPI
        found_id = getId(glpi_itemtype, component_name)
        
        # Check if we successfully found the component
        if isinstance(found_id, int) and found_id not in [1403, 1404]:
            # Success - add it to our update list
            components_to_update[glpi_field_name] = found_id
            log.info(f"Found {component_type}: '{component_name}' with ID {found_id}")
        else:
            # Failed - log what went wrong
            log.error(f"Couldn't find {component_type}: '{component_name}'")
    
    # If we didn't find any valid components, don't do anything
    if not components_to_update:
        log.warning("No valid components found to update")
        return
    
    # Send the update to GLPI
    update_data = json.dumps({"input": components_to_update})
    response = sendglpi(f"/Computer/{device_id}", session_token, "PUT", update_data)
    
    log.info(f"Device {device_id} updated. Response: {response}")
def search(mode:str, query:str): #TODO: Dont return the response, format the response nicer (maybe a list?)
    match mode:
        case "serial": # this is here incase the user wants to search for something other then the serial number  c
            return(sendglpi(f"/search/Computer/?criteria[0][link]=AND&criteria[0][field]=5&criteria[0][searchtype]=contains&criteria[0][value]={query}", session_token))
    

def auth(username:str, password:str, verify:bool, remember:bool):
    log.debug('Reached Auth')
    log.debug(f"{username}, Verify: {verify}, RememberMe: {remember}")
    auth = (username, password)
    payload = {}
    headers = {
        'Content-Type': 'application/json',
        'App-Token': f'{app_token}',
    }
    response = requests.request("GET", f"{api_url}/initSession", headers=headers, data=payload, timeout=5, verify=verify,auth=auth)
    response = str(response.content).strip('b').strip("'") # There is a random "b" at the front and the data is encapsulated in ' So this gets rid of that
    if response == '["ERROR_GLPI_LOGIN","Falscher Benutzername oder Passwort"]':
        log.error("1401: Bad Username or Password")
        return 1401
    log.debug(response)
    if response.startswith('{'): # This is a dumb way to check if its json, lets hope it doesnt break
        response = json.loads(response)
        if(response['session_token']): 
            log.info('Authentication to GLPI Sucessfull')
            return response['session_token']
        else:
            log.error('1400: Something went wrong. That\'s all we know. Check Debug Logs')
            return 1400

# --- Application ---

if __name__ == "__main__":
    global username
    attempts = 0
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    session_token = None
    
    while not session_token:
        attempts += 1
        username = input("Enter your Username: ")
        session_token = auth(username, getpass.getpass('Password: '), confirm('Verify SSL?'), False)
        if isinstance(session_token, int):
            match session_token:
                case 1401:
                    log.warning(f'Incorrect Username or Password. ({session_token})')
                    session_token = None
                    continue
                case 1400:
                    log.error(f'Something went wrong in the Authentication. ({session_token})')
                    break
                case _:
                    log.error(f'Something seriously went wrong in the Authentication ({session_token})')
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
            test_data = {"manufacturer":"Dell","name": "GLPIAPI Test Computer","serial": "794502","os": "windows 11","gpu": "Xe Graphics", "cpu": "i5-1145G7","ram": "16 GB","hdd": "SSD 256"}
            add("Computer", test_data)
            processor = input("Please enter the processor of the Device ")
            #gpu = input("Please enter the GPU of the Deivce ")
            ram = input("Please enter the RAM of the Device ")
            os = input("Please enter the OS of the Device ")
            os_version = input("Please enter the OS Version of the Device ")
            hdd = input("Enter the drive of the Device ")
            add("Computer", {"name":input("Please enter the name of the Device"), "serial": input("Please enter the Serial Number"), "location": "Akademie", "tech_user": username, "model": input("Enter the model Pls "), "manufacturer": input("Enter the Manufacturer of the Device "), "processor": processor, "os": os, "os_version": os_version, "hdd": hdd, "ram": ram})
