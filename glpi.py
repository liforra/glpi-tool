import requests
import base64
import json
import os
import getpass
import logging


if __name__ == "__main__":
    import atexit


log = logging.getLogger(__name__)


# --- Statics ---
api_url = "https://ticket.akademie-awo.de/glpi/apirest.php"
app_token = os.getenv("APP_TOKEN")

# --- Basics that we should always have ---

def confirm(question):
    valid_yes = ['y', 'yes', 'Y', 'Yes', 'YES']
    valid_no = ['n', 'no', 'N', 'No', 'NO']
    
    while True:
        answer = input(f"{question} (y/n): ").strip()
        if answer in valid_yes:
            return True
        elif answer in valid_no:
            return False
        else:
            log.warning("Invalid Option. (y/n)")








def sendglpi(endpoint:str, session_token:str, method="GET", payload=""):
    log.debug(f'{method} request to {endpoint}, with session Token {session_token} and payload {payload}')
    if endpoint.startswith(api_url):
        url = f"{endpoint}"
    else:
        url = f"{api_url}{endpoint}"
    payload = {}
    headers = {
        'Content-Type': 'application/json',
        'App-Token': f'{app_token}',
        'Session-Token': f'{session_token}'
    }
    #return requests.request("GET", url, headers=headers, data=payload, timeout=5, verify=verify,auth=auth)
    response = requests.request(f"{method}", url, headers=headers, data=payload, timeout=5)
    response = str(response.content).strip('b').strip("'")
    log.debug(response)
    return response

def getId(itemtype:str=="Processor", query:str):
    match itemtype:
        case "Processor":
            log.debug("Reached getId: Processor")
            print(sendglpi("DeviceProcessor?criteria[0][link]=AND&criteria[0][field]=1&criteria[0][searchtype]=contains&criteria[0][value]={query}&forcedisplay=2", session_token))
        case "Model":
            log.debug("Reached getId: Model")
        case "Location":
            log.debug("Reached getId: Location")
def add(itemtype:str, data:list):
    match itemtype:
        case "Computer": 
            log.debug('Reached add: Computer')
            payload = {
                "input": {
                    "name": data[0],
                    "serial": data[1],
                    "locations_id": getId("Location", data[2]),
                    "users_id_tech": getId("User", data[3]),
                    "groups_id_tech": 1,
                    "computermodels_id": getId("Model", data[4]),
                    "comment": f"\r\nThis Computer was automagically added using The GLPIClient. {username} is responsible for any acounts. Added from {(os.popen('hostname').read().strip() or 'unknown_hostname')}"
                }
            }
            print(sendglpi(f"{{glpi_url}}/apirest.php/{mode}   /", session_token))

def search(mode:str, query:str):
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
            log.error('0400: Something went wrong. That\'s all we know. Check Debug Logs')
            return 1400



if __name__ == "__main__":
    attempts = 0
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    session_token = None
    
    while not session_token:
        attempts += 1
        session_token = auth(input("Enter your Username: "), getpass.getpass('Password: '), confirm('Verify SSL?'), False)
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
        case 1:##
            print(search("serial", input("Please Enter your Search Query: ")))
        case 2:
            name = ""
            serial = ""
            location = ""
            users_id_tech = finduser(username)
            groups_id_tech = 1
            computermodels_id = findmodel()
            add('Computer', [name,serial,location,users_id_tech,groups_id_tech,computermodels_id])
        case 3:
            killsession()
            exit()
        case 4:
            getId(input('What Item are you looking for? '), input("Please enter the Search query: "))
    
    
    
    
    
    
    

    
    
    
    

    
    
    
    getId("Processor",input("Enter Processor Model: "))
    
    
    
    exit()

