import base64
import requests
import json
import logging

log = logging.getLogger(__name__)

class GLPIClient:
    """
    A class for interacting with the GLPI API.
    """

    def __init__(self, config):
        """
        Initialize the GLPIClient with a configuration dictionary.
        """
        self.config = config
        self.glpi_url = config["glpi"]["glpi_url"]
        if self.glpi_url.endswith('/'):
            self.glpi_url = self.glpi_url[:-1]
        self.api_version = config["glpi"].get("api_version", "v1")
        self.client_id = config["glpi"].get("client_id")
        self.client_secret = config["glpi"].get("client_secret")
        self.scope = config["glpi"].get("scope", "api")
        self.app_token = config["glpi"].get("app_token")
        self.verify_ssl = config["glpi"]["verify_ssl"]
        self.user_agent = "GiteaGLPI-TUI/1.0"
        self.session_token = None
        self.username = None
        self.metrics = {"requests": 0, "errors": 0, "errors_4xx": 0, "errors_5xx": 0, "unauthorized": 0}

    def discover_api_versions(self):
        """
        Discover available API versions from the GLPI server.
        """
        discovery_url = f"{self.glpi_url}/api.php/"
        headers = {
            "Accept": "application/json",
            "User-Agent": self.user_agent
        }
        try:
            response = requests.get(discovery_url, headers=headers, verify=self.verify_ssl)
            if response.status_code == 200:
                try:
                    payload = response.json()
                except ValueError:
                    log.error("Failed to decode GLPI discovery response as JSON")
                    return []

                if "api_versions" in payload:
                    return payload.get("api_versions", [])

                return payload.get("versions", [])
            return []
        except Exception as e:
            log.error(f"Failed to discover API versions: {e}")
            return []

    def init_session(self, username, password):
        """
        Initialize a session with the GLPI API.
        """
        self.username = username
        log.info(f"Initializing session for user '{username}' using API {self.api_version}")
        if self.api_version == "v2":
            success, token_or_message = self._init_session_v2(username, password)
        else:
            success, token_or_message = self._init_session_v1(username, password)

        if success:
            self.session_token = token_or_message
        return success, token_or_message

    def _init_session_v1(self, username, password):
        """
        Initialize a v1 session.
        """
        url = f"{self.glpi_url}/apirest.php/initSession"
        log.debug(f"v1 init session URL: {url}")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": self.user_agent,
            "App-Token": self.app_token,
            "Accept": "application/json"
        }
        try:
            response = requests.get(
                url,
                headers=headers,
                auth=(username, password),
                verify=self.verify_ssl
            )
            log.debug(f"v1 init session response text: {response.text}")
            if response.status_code == 200:
                self.session_token = response.json().get('session_token')
                return True, self.session_token
            else:
                return False, response.json().get('message', 'Login failed')
        except Exception as e:
            return False, str(e)

    def _init_session_v2(self, username, password):
        """
        Initialize a v2 session.
        """
        url = f"{self.glpi_url}/api.php/token"
        data = {
            "grant_type": "password",
            "username": username,
            "password": password
        }
        if self.client_id:
            data["client_id"] = self.client_id
        if self.client_secret:
            data["client_secret"] = self.client_secret
        if self.scope:
            data["scope"] = self.scope
        log.debug(f"v2 init session URL: {url}")
        log.debug(
            "v2 init session data: {'grant_type': 'password', 'client_id': '%s', 'client_secret': 'REDACTED', 'username': '%s', 'password': 'REDACTED', 'scope': '%s'}",
            self.client_id,
            username,
            self.scope,
        )
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": self.user_agent,
            "Accept": "application/json"
        }
        if self.app_token:
            headers["GLPI-App-Token"] = self.app_token
        try:
            response = requests.post(url, headers=headers, data=data, verify=self.verify_ssl)
            content_type = response.headers.get("Content-Type", "")
            try:
                response_data = response.json()
            except ValueError:
                log.error(f"Unexpected v2 response (status {response.status_code}) from {url}: {response.text[:200]}")
                if response.status_code == 404:
                    return False, {"type": "v2_not_found", "message": "GLPI API v2 token endpoint not found (404)."}
                return False, f"Unexpected response from GLPI API (HTTP {response.status_code})"
            else:
                if "application/json" not in content_type.lower():
                    log.error(
                        "Unexpected content type '%s' for v2 response from %s (status %s). Body preview: %s",
                        content_type,
                        url,
                        response.status_code,
                        response.text[:200]
                    )
                    if response.status_code == 404:
                        return False, {"type": "v2_not_found", "message": "GLPI API v2 token endpoint not found (404)."}
                    return False, f"Unexpected response format from GLPI API (HTTP {response.status_code})"

            if response.status_code == 200:
                self.session_token = response_data.get('access_token')
                return True, self.session_token

            if response.status_code == 404:
                return False, {"type": "v2_not_found", "message": response_data.get('detail') or response_data.get('message') or 'GLPI API v2 token endpoint not found (404).'}

            if response.status_code == 400:
                hint = response_data.get('hint', '')
                err = response_data.get('error')
                if (err == 'invalid_request' and ('client_id' in hint or not self.client_id)):
                    try:
                        fb_headers = {
                            "Content-Type": "application/x-www-form-urlencoded",
                            "User-Agent": self.user_agent,
                            "Accept": "application/json"
                        }
                        if self.app_token:
                            fb_headers["GLPI-App-Token"] = self.app_token
                        fb_data = {
                            "grant_type": "password",
                            "username": username,
                            "password": password,
                            "scope": self.scope or "api",
                        }
                        response_fb = requests.post(url, headers=fb_headers, data=fb_data, auth=(self.client_id or "", self.client_secret or ""), verify=self.verify_ssl)
                        try:
                            response_data_fb = response_fb.json()
                        except ValueError:
                            response_data_fb = {"message": response_fb.text}
                        if response_fb.status_code == 200:
                            self.session_token = response_data_fb.get('access_token')
                            return True, self.session_token
                        log.error(f"GLPI v2 authentication fallback failed (HTTP {response_fb.status_code}): {response_data_fb}")
                    except Exception as e_fb:
                        log.error(f"GLPI v2 authentication fallback error: {e_fb}")
                    return False, 'GLPI v2 OAuth requires valid client credentials. Check glpi.client_id/client_secret.'
            message = response_data.get('detail') or response_data.get('message') or response_data.get('error_description') or response_data.get('error') or 'Login failed'
            log.error(f"GLPI v2 authentication failed (HTTP {response.status_code}): {response_data}")
            return False, message
        except Exception as e:
            return False, str(e)

    def verify_session(self, session_token):
        """
        Verify if a session token is still valid.
        """
        if self.api_version == "v2":
            return self._verify_session_v2(session_token)
        else:
            return self._verify_session_v1(session_token)

    def _verify_session_v1(self, session_token):
        url = f"{self.glpi_url}/apirest.php/getFullSession"
        headers = {
            "Content-Type": "application/json",
            "Session-Token": session_token,
            "App-Token": self.app_token,
            "User-Agent": self.user_agent
        }
        try:
            response = requests.get(url, headers=headers, verify=self.verify_ssl)
            if response.status_code == 200:
                self.session_token = session_token
                return True
            return False
        except Exception as e:
            log.error(f"Error verifying v1 token: {e}")
            return False

    def _verify_session_v2(self, access_token):
        url = f"{self.glpi_url}/api.php/v2/Administration/User/Me"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "User-Agent": self.user_agent,
            "Accept": "application/json"
        }
        try:
            response = requests.get(url, headers=headers, verify=self.verify_ssl)
            if response.status_code == 200:
                self.session_token = access_token
                return True
            return False
        except Exception as e:
            log.error(f"Error verifying v2 token: {e}")
            return False

    def kill_session(self):
        """
        End a session with the GLPI API.
        """
        if not self.session_token:
            return False
            
        if self.api_version == "v1":
            url = f"{self.glpi_url}/apirest.php/killSession"
            headers = {
                "Content-Type": "application/json",
                "Session-Token": self.session_token,
                "App-Token": self.app_token,
                "User-Agent": self.user_agent
            }
            try:
                response = requests.get(url, headers=headers, verify=self.verify_ssl)
                if response.status_code == 200:
                    self.session_token = None
                    return True
                return False
            except Exception as e:
                log.error(f"Error killing v1 session: {e}")
                return False
        
        # For v2, there is no explicit logout endpoint, so we just clear the token
        self.session_token = None
        return True

    def _send_request(self, endpoint, method="GET", payload=None, params=None):
        if not self.session_token:
            raise RuntimeError("GLPI Client Error: No session token available. Please authenticate first.")

        if self.api_version == "v2":
            base_url = f"{self.glpi_url}/api.php/v2"
            headers = {
                "Authorization": f"Bearer {self.session_token}",
                "User-Agent": self.user_agent,
                "Accept": "application/json"
            }
            if self.app_token:
                headers["GLPI-App-Token"] = self.app_token
            if method.upper() != "GET":
                headers["Content-Type"] = "application/json"
        else:
            base_url = f"{self.glpi_url}/apirest.php"
            headers = {
                "Session-Token": self.session_token,
                "App-Token": self.app_token,
                "User-Agent": self.user_agent,
                "Accept": "application/json"
            }
            if method.upper() != "GET":
                headers["Content-Type"] = "application/json"
        def do_request(base: str):
            url = f"{base}{endpoint}"
            log.debug(f"{method} request to {url} params={params} payload={payload}")
            if method.upper() == "GET":
                return requests.request(method, url, headers=headers, params=params, verify=self.verify_ssl)
            return requests.request(method, url, headers=headers, json=payload, params=params, verify=self.verify_ssl)

        try:
            self.metrics["requests"] += 1
            if self.api_version == "v2":
                response = do_request(base_url)
            else:
                base = f"{self.glpi_url}/apirest.php"
                response = do_request(base)

            if response.status_code == 401:
                self.session_token = None
                self.username = None
                log.warning("Session token expired or invalid - cleared session")
                self.metrics["unauthorized"] += 1
                raise Exception("401 Unauthorized: Session expired or invalid.")
            if response.status_code >= 400:
                log.error(f"GLPI API Error: {response.status_code} - {response.text}")
                self.metrics["errors"] += 1
                if 400 <= response.status_code < 500:
                    self.metrics["errors_4xx"] += 1
                elif response.status_code >= 500:
                    self.metrics["errors_5xx"] += 1
                response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            log.error(f"GLPI request failed: {e}")
            raise

    def search(self, itemtype, criteria):
        if self.api_version == "v2":
            def norm(x):
                return " ".join(str(x).lower().split())
            query = criteria.get("query", "")
            qn = norm(query)
            limit = criteria.get("limit") or 99999999

            if itemtype == "Computer":
                if query:
                    results = []
                    try:
                        r1 = self._send_request("/Assets/Computer", method="GET", params={"limit": limit, "filter": f"name=like=*{query}*"})
                        results.extend(r1 or [])
                    except Exception:
                        pass
                    try:
                        r2 = self._send_request("/Assets/Computer", method="GET", params={"limit": limit, "filter": f"serial=like=*{query}*"})
                        results.extend(r2 or [])
                    except Exception:
                        pass
                    seen = set()
                    uniq = []
                    for it in results:
                        i = it.get("id")
                        if i not in seen:
                            seen.add(i)
                            uniq.append(it)
                    return uniq
                return self._send_request("/Assets/Computer", method="GET", params={"limit": limit})

            params = {"limit": limit}
            if itemtype in ["DeviceProcessor", "DeviceGraphicCard", "DeviceMemory", "DeviceHardDrive"]:
                component_map = {
                    "DeviceProcessor": "/Components/Processor",
                    "DeviceGraphicCard": "/Components/GraphicCard",
                    "DeviceMemory": "/Components/Memory",
                    "DeviceHardDrive": "/Components/HardDrive",
                }
                endpoint = component_map.get(itemtype, f"/Components/{itemtype}")
                if query:
                    try:
                        qtok = "*" + "*".join(query.split()) + "*"
                        return self._send_request(endpoint, method="GET", params={"limit": limit, "filter": f"designation=like={qtok}"})
                    except Exception:
                        pass
                return self._send_request(endpoint, method="GET", params={"limit": limit})

            if itemtype == "Manufacturer":
                if query:
                    try:
                        return self._send_request("/Dropdowns/Manufacturer", method="GET", params={"limit": limit, "filter": f"name=like=*{query}*"})
                    except Exception:
                        pass
                return self._send_request("/Dropdowns/Manufacturer", method="GET", params={"limit": limit})

            if itemtype == "Location":
                if query:
                    try:
                        return self._send_request("/Administration/Location", method="GET", params={"limit": limit, "filter": f"name=like=*{query}*"})
                    except Exception:
                        pass
                return self._send_request("/Administration/Location", method="GET", params={"limit": limit})

            endpoint = f"/Assets/{itemtype}"
            if query:
                try:
                    return self._send_request(endpoint, method="GET", params={"limit": limit, "filter": f"name=like=*{query}*"})
                except Exception:
                    pass
            return self._send_request(endpoint, method="GET", params={"limit": limit})
        else:
            endpoint = f"/search/{itemtype}?criteria[0][field]=1&criteria[0][searchtype]=contains&criteria[0][value]={criteria.get('query')}&forcedisplay=2"
            return self._send_request(endpoint, method="GET")

    def search_computer(self, serial_number):
        if self.api_version == "v2":
            def norm(x):
                return " ".join(str(x).lower().split())
            qn = norm(serial_number)
            try:
                r1 = self._send_request("/Assets/Computer", method="GET", params={"limit": 99999999, "filter": f"name=like=*{serial_number}*"})
            except Exception:
                r1 = []
            try:
                r2 = self._send_request("/Assets/Computer", method="GET", params={"limit": 99999999, "filter": f"serial=like=*{serial_number}*"})
            except Exception:
                r2 = []
            seen = set()
            uniq = []
            for it in (r1 or []) + (r2 or []):
                i = it.get("id")
                if i not in seen:
                    seen.add(i)
                    uniq.append(it)
            return uniq
        else:
            return self._send_request(f"/search/Computer/?criteria[0][field]=5&criteria[0][searchtype]=contains&criteria[0][value]={serial_number}", method="GET")

    def getId(self, itemtype, query):
        if not query:
            return None
        try:
            if self.api_version == "v2":
                return self._getId_v2(itemtype, query)
            else: # v1
                response = self._send_request(f"/search/{itemtype}?criteria[0][link]=AND&criteria[0][field]=1&criteria[0][searchtype]=contains&criteria[0][value]={query}&forcedisplay=2")
                if response == '["ERROR_RIGHT_MISSING","Sie haben keine ausreichenden Rechte f\\xc3\\xbcr diese Aktion."]':
                    log.error(f'1403: Permission denied reading {itemtype}')
                    return 1403
                
                if 'data' in response and response['data']:
                    log.debug(f"Requested {itemtype} has ID {response['data'][0]['2']}")
                    return response['data'][0]['2']
                else:
                    log.warning(f'1404: No Result Matching {query} in {itemtype}')
                    return 1404
        except Exception as e:
            log.error(f'Error getting ID for {itemtype} "{query}": {e}')
            if "401" in str(e):
                raise # Re-raise auth errors to be handled by the GUI
            return None

    def add(self, itemtype, data):
        if itemtype != "Computer":
            raise NotImplementedError("Adding items other than 'Computer' is not yet implemented.")
        log.debug("Reached add: Computer")
        if self.api_version == "v2":
            payload = {
                "name": data.get("name"),
                "serial": data.get("serial"),
                "location": self.getId("Location", data.get("location")),
                "user": self.getId("User", self.username),
                "model": self.getId("ComputerModel", data.get("model")),
                "manufacturer": self.getId("Manufacturer", data.get("manufacturer")),
                "comment": data.get("comment"),
            }
            payload = self._sanitize_v2_computer_payload(payload)
            response_data = self._send_request("/Assets/Computer", method="POST", payload=payload)
        else:
            payload_input = {
                "name": data.get("name"),
                "serial": data.get("serial"),
                "locations_id": self.getId("Location", data.get("location")),
                "users_id_tech": self.getId("User", self.username),
                "groups_id_tech": 1,
                "computermodels_id": self.getId("ComputerModel", data.get("model")),
                "comment": data.get("comment"),
                "manufacturers_id": self.getId("Manufacturer", data.get("manufacturer")),
                "computertypes_id": self.getId("ComputerType", data.get("computer_type")),
                "_plugin_fields_funktionsfhigkeitfielddropdowns_id_defined": [7],
            }
            battery_health_str = data.get("battery_health")
            if battery_health_str:
                try:
                    payload_input["akkugesundheitinfield"] = int(battery_health_str)
                except (ValueError, TypeError):
                    log.warning(f"Could not convert battery health '{battery_health_str}' to an integer. Skipping field.")
            payload = {"input": payload_input}
            response_data = self._send_request(f"/{itemtype}/", method="POST", payload=payload)
        computer_id = response_data.get("id")
        if not computer_id:
            log.error(f"Failed to create computer. Response: {response_data}")
            raise Exception(f"Computer creation failed: {response_data.get('message', 'Unknown error')}")
        items_to_add = ["cpu", "processor", "gpu", "ram", "hdd", "os"]
        if any(item in data for item in items_to_add):
            self.addToItemtype(computer_id, data)
        return computer_id

    def _sanitize_v2_computer_payload(self, payload):
        sanitized = {}
        for k, v in payload.items():
            if k in ("location", "user", "model", "manufacturer"):
                if isinstance(v, int) and v > 0 and v not in (1403, 1404):
                    sanitized[k] = v
                else:
                    log.warning(f"Dropping invalid field '{k}' with value '{v}' in v2 Computer payload")
            else:
                if v is not None and (not isinstance(v, str) or v.strip() != ""):
                    sanitized[k] = v
        return sanitized

    def _getId_v2(self, itemtype, query):
        def norm(x):
            return " ".join(str(x).lower().split())
        qn = norm(query)
        mapping = {
            "DeviceProcessor": ("/Components/Processor", "designation"),
            "DeviceGraphicCard": ("/Components/GraphicCard", "designation"),
            "DeviceMemory": ("/Components/Memory", "designation"),
            "DeviceHardDrive": ("/Components/HardDrive", "designation"),
            "Manufacturer": ("/Dropdowns/Manufacturer", "name"),
            "Location": ("/Administration/Location", "name"),
            "ComputerModel": ("/Assets/ComputerModel", "name"),
            "User": ("/Administration/User", "name"),
            "OperatingSystem": ("/Administration/OperatingSystem", "name"),
            "OperatingSystemVersion": ("/Administration/OperatingSystemVersion", "name"),
            "OperatingSystemEdition": ("/Administration/OperatingSystemEdition", "name"),
        }
        if itemtype in mapping:
            base, field = mapping[itemtype]
            try:
                if field == "designation":
                    qtok = "*" + "*".join(query.split()) + "*"
                    resp = self._send_request(base, method="GET", params={"filter": f"{field}=like={qtok}"})
                else:
                    resp = self._send_request(base, method="GET", params={"filter": f"{field}=like=*{query}*"})
                if isinstance(resp, list) and resp:
                    for it in resp:
                        name = (it.get("name") or it.get("label") or it.get("designation") or "")
                        if norm(name) == qn:
                            return it.get("id")
                    return resp[0].get("id")
            except Exception:
                pass
            try:
                resp_all = self._send_request(base, method="GET")
                if isinstance(resp_all, list) and resp_all:
                    best = None
                    for it in resp_all:
                        name = (it.get("name") or it.get("label") or it.get("designation") or "")
                        if norm(name) == qn:
                            best = it
                            break
                        if not best and qn in norm(name):
                            best = it
                    if best:
                        return best.get("id")
            except Exception:
                pass
        return self._getId_v1_fallback(itemtype, query)
    
    def _getId_v1_fallback(self, itemtype, query):
        """Fallback to v1 API for items that don't work in v2"""
        def norm(x):
            return " ".join(str(x).lower().split())
        qn = norm(query)
        
        try:
            # Temporarily switch to v1 API for this call
            original_api_version = self.api_version
            self.api_version = "v1"
            
            try:
                # Use v1 search endpoint
                endpoint = f"/search/{itemtype}?criteria[0][link]=AND&criteria[0][field]=1&criteria[0][searchtype]=contains&criteria[0][value]={query}&forcedisplay=2"
                response = self._send_request(endpoint, method="GET")
                
                if response == '["ERROR_RIGHT_MISSING","Sie haben keine ausreichenden Rechte f\\xc3\\xbcr diese Aktion."]':
                    log.error(f'1403: Permission denied reading {itemtype}')
                    return 1403
                
                if 'data' in response and response['data']:
                    log.debug(f"Found v1 match for {itemtype} '{query}': ID {response['data'][0]['2']}")
                    return response['data'][0]['2']
                else:
                    log.warning(f'1404: No Result Matching {query} in {itemtype} (v1 fallback)')
                    return 1404
                    
            except Exception as e:
                log.error(f'v1 fallback failed for {itemtype} "{query}": {e}')
                if "401" in str(e):
                    raise  # Re-raise auth errors
                return 1404
            finally:
                # Always restore original API version
                self.api_version = original_api_version
                
        except Exception as e:
            log.error(f'v1 fallback setup failed for {itemtype} "{query}": {e}')
            return 1404

    def _link_component_v1(self, device_id, component_itemtype, component_id):
        """Fallback to v1 API for linking components."""
        log.warning(f"Using v1 API to link {component_itemtype} to device {device_id}")
        try:
            # Temporarily switch to v1 API for this call
            original_api_version = self.api_version
            self.api_version = "v1"

            endpoint = f"/Item_{component_itemtype}"
            item_payload = {
                'items_id': device_id,
                'itemtype': 'Computer',
                f'{component_itemtype.lower()}s_id': component_id
            }
            payload = {'input': item_payload}
            self._send_request(endpoint, method="POST", payload=payload)
        except Exception as e:
            log.error(f"v1 component linking failed: {e}")
        finally:
            # Always restore original API version
            self.api_version = original_api_version

    def addToItemtype(self, device_id, data):
        # 1. Handle Hardware Components
        hardware_components = ["cpu", "processor", "gpu", "ram", "hdd"]
        for component in hardware_components:
            if component in data and data.get(component):
                log.debug(f"Adding hardware component '{component}' to device ID {device_id}")
                
                component_value = data.get(component)
                endpoint = None
                payload = None
                
                if self.api_version == "v2":
                    component_id = None
                    if component in ("processor", "cpu"):
                        component_id = self.getId("DeviceProcessor", component_value)
                    elif component == "gpu":
                        component_id = self.getId("DeviceGraphicCard", component_value)
                    elif component == "ram":
                        component_id = self.getId("DeviceMemory", component_value)
                    elif component == "hdd":
                        component_id = self.getId("DeviceHardDrive", component_value)
                    
                    if component_id and component_id not in [1403, 1404]:
                        payload = {}
                        if component in ("processor", "cpu"):
                            payload["processors"] = [{"id": component_id}]
                        elif component == "gpu":
                            payload["graphicCards"] = [{"id": component_id}]
                        elif component == "ram":
                            payload["memories"] = [{"id": component_id}]
                        elif component == "hdd":
                            payload["hardDrives"] = [{"id": component_id}]
                        if payload:
                            try:
                                self._send_request(f"/Assets/Computer/{device_id}", method="PATCH", payload=payload)
                            except Exception as e:
                                log.warning(f"v2 component linking failed for {component}: {e}, falling back to v1")
                                component_itemtype = None
                                if component in ("processor", "cpu"):
                                    component_itemtype = "DeviceProcessor"
                                elif component == "gpu":
                                    component_itemtype = "DeviceGraphicCard"
                                elif component == "ram":
                                    component_itemtype = "DeviceMemory"
                                elif component == "hdd":
                                    component_itemtype = "DeviceHardDrive"
                                
                                if component_itemtype:
                                    self._link_component_v1(device_id, component_itemtype, component_id)
                else:
                    # v1 API component linking
                    item_payload = {'items_id': device_id, 'itemtype': 'Computer'}
                    
                    if component in ("processor", "cpu"):
                        item_payload['deviceprocessors_id'] = self.getId("DeviceProcessor", component_value)
                        endpoint = "/Item_DeviceProcessor"
                    elif component == "gpu":
                        item_payload['devicegraphiccards_id'] = self.getId("DeviceGraphicCard", component_value)
                        endpoint = "/Item_DeviceGraphicCard"
                    elif component == "ram":
                        item_payload['devicememories_id'] = self.getId("DeviceMemory", component_value)
                        endpoint = "/Item_DeviceMemory"
                    elif component == "hdd":
                        item_payload['deviceharddrives_id'] = self.getId("DeviceHardDrive", component_value)
                        endpoint = "/Item_DeviceHardDrive"
                    
                    if endpoint:
                        payload = {'input': item_payload}
                        self._send_request(endpoint, method="POST", payload=payload)

        # 2. Handle Operating System Link
        if data.get("os"):
            log.debug(f"Linking Operating System to device ID {device_id}")
            os_id = self.getId("OperatingSystem", data.get("os"))
            os_version_id = self.getId("OperatingSystemVersion", data.get("os_version"))
            os_edition_id = self.getId("OperatingSystemEdition", data.get("os_edition"))

            if os_id and os_id not in [1403, 1404]:
                if self.api_version == "v2":
                    payload = {"operatingSystem": {"id": os_id}}
                    if os_version_id and os_version_id not in [1403, 1404]:
                        payload["operatingSystemVersion"] = {"id": os_version_id}
                    if os_edition_id and os_edition_id not in [1403, 1404]:
                        payload["operatingSystemEdition"] = {"id": os_edition_id}
                    try:
                        self._send_request(f"/Assets/Computer/{device_id}", method="PATCH", payload=payload)
                    except Exception as e:
                        log.warning(f"v2 OS linking failed: {e}")
                else:
                    # v1 API OS linking
                    os_payload_input = {
                        'items_id': device_id,
                        'itemtype': 'Computer',
                        'operatingsystems_id': os_id,
                    }
                    if os_version_id and os_version_id not in [1403, 1404]:
                        os_payload_input['operatingsystemversions_id'] = os_version_id
                    if os_edition_id and os_edition_id not in [1403, 1404]:
                        os_payload_input['operatingsystemeditions_id'] = os_edition_id
                    
                    payload = {'input': os_payload_input}
                    self._send_request("/Item_OperatingSystem", method="POST", payload=payload)
            else:
                log.warning(f"Could not link Operating System because its ID could not be found for: {data.get('os')}")
