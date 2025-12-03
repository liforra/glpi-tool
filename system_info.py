import platform
import subprocess
import json
import logging
import re
import os
from pathlib import Path
import tempfile

# Attempt to import optional libraries
try:
    import psutil
except ImportError:
    psutil = None
    logging.warning("psutil library not found. RAM/Storage info will be limited.")

try:
    if platform.system() == "Windows":
        import wmi
        import pythoncom
        WMI_AVAILABLE = True
    else:
        WMI_AVAILABLE = False
except ImportError:
    WMI_AVAILABLE = False
    logging.warning("wmi library not found. Hardware detection on Windows will be limited.")

log = logging.getLogger(__name__)

def _run_command(command):
    """Helper to run a command and capture output."""
    try:
        # Hide the console window for subprocess on Windows
        startupinfo = None
        if platform.system() == "Windows":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
        result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=20, startupinfo=startupinfo)
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
        log.warning(f"Command '{' '.join(command)}' failed: {e}")
        return None

def _round_storage_gb(gib):
    """Improved storage size rounding with more accurate marketing sizes."""
    if not gib: 
        return 0
    
    # Convert GiB to approximate GB (marketing)
    estimated_marketing_gb = gib * (1024**3 / 1000**3)
    
    # Extended list of common drive sizes
    common_sizes = [
        # Small drives
        32, 64, 120, 128, 
        # Medium drives  
        240, 250, 256, 480, 500, 512,
        # Large drives
        960, 1000, 1024, 2000, 2048, 4000, 4096, 8000, 8192
    ]
    
    # Find the closest matching size
    best_match = min(common_sizes, key=lambda x: abs(x - estimated_marketing_gb))
    
    # Only use the best match if it's reasonably close (within 15%)
    if abs(best_match - estimated_marketing_gb) / estimated_marketing_gb <= 0.15:
        return best_match
    
    # If no close match, round to nearest reasonable size
    if estimated_marketing_gb < 100:
        return round(estimated_marketing_gb / 16) * 16  # Round to 16GB increments
    elif estimated_marketing_gb < 1000:
        return round(estimated_marketing_gb / 32) * 32  # Round to 32GB increments  
    else:
        return round(estimated_marketing_gb / 128) * 128  # Round to 128GB increments

def _clean_processor_name(name):
    """Extracts the core model number from a full CPU brand string."""
    if not name: return "Unknown"
    match = re.search(
        r'(i[3579]-\w+|Ryzen\s\d\s\w+|Xeon\s\w-\w+|Pentium\s\w+|Celeron\s\w+)',
        name, re.IGNORECASE
    )
    if match: return match.group(1).strip()
    name = re.sub(r'Intel\(R\)\sCore\(TM\)\s', '', name)
    name = re.sub(r'\sCPU\s@\s.*', '', name)
    return name.strip()

def _clean_gpu_name(name):
    """Extracts the core model name from a full GPU brand string, based on common patterns."""
    if not name:
        return "Unknown"

    # Normalize the name by removing trademarks and standardizing whitespace
    cleaned_name = re.sub(r'\((R|TM)\)', '', name).strip()
    cleaned_name = re.sub(r'\s+', ' ', cleaned_name)

    # List of regex patterns to extract the core GPU name.
    # Order is important: from more specific to more general.
    patterns = [
        # NVIDIA Specific
        re.compile(r'(NVS\s+\d+\s*\w*)', re.IGNORECASE),
        re.compile(r'(Quadro\s+[\w\s]+\d{3,})', re.IGNORECASE),
        re.compile(r'(GeForce\s+(?:RTX|GTX|GT)\s+[\d\s\w-]+)', re.IGNORECASE),
        
        # AMD/ATI Specific - handles "Radeon HD 7970", "Radeon R9 290", "Radeon RX 580"
        re.compile(r'(Radeon\s+(?:HD|R\d|RX)\s+[\d\s\w]+)', re.IGNORECASE),
        # Handles "Radeon Vega 8"
        re.compile(r'(Radeon\s+Vega\s+\d+)', re.IGNORECASE),
        # Handles "Radeon 680M"
        re.compile(r'(Radeon\s+\d{3,4}M)', re.IGNORECASE),
        
        # Intel Specific
        re.compile(r'(Iris\s+(?:Xe|Pro|Plus)[\s\w()]+)', re.IGNORECASE),
        re.compile(r'(Intel\s+(?:UHD|HD)\s+Graphics\s*[\w\d]*)', re.IGNORECASE),
        re.compile(r'(Intel\s+GMA\s+[\w\d]+)', re.IGNORECASE),

        # Generic Radeon/GeForce/Quadro catch-alls for anything missed
        re.compile(r'(Radeon\s+[\w\d\s]+)', re.IGNORECASE),
        re.compile(r'(GeForce\s+[\w\d\s]+)', re.IGNORECASE),
        re.compile(r'(Quadro\s+[\w\d\s]+)', re.IGNORECASE),

        # APU Codenames from user list
        re.compile(r'(Cezanne|Renoir)', re.IGNORECASE)
    ]

    for pattern in patterns:
        match = pattern.search(cleaned_name)
        if match:
            # Return the first match found, cleaned of extra whitespace
            return match.group(0).strip()

    # If no specific pattern matches, perform a generic cleanup by removing manufacturer prefixes.
    generic_cleaned = re.sub(r'^(AMD|NVIDIA|Intel|ATI)[\s/]*', '', cleaned_name, flags=re.IGNORECASE)
    generic_cleaned = re.sub(r' Corporation| Inc\.', '', generic_cleaned, flags=re.IGNORECASE)
    
    return generic_cleaned.strip() if generic_cleaned.strip() else name

def _clean_manufacturer_name(name):
    """
    Cleans and standardizes the manufacturer name against a known list.
    """
    if not name:
        return "Unknown"

    MANUFACTURER_MAP = {
        "HPE (Hewlett Packard Enterprise)": ["hewlett packard enterprise", "hpe"],
        "HP": ["hewlett-packard", "hewlett packard", "hp"],
        "ASRock": ["asrock"],
        "Asus": ["asus", "asustek"],
        "Dell EMC": ["dell emc"],
        "Dell": ["dell"],
        "Gigabyte": ["gigabyte", "gigabyte technology"],
        "MSI": ["msi", "micro-star"],
        "Supermicro": ["supermicro", "super micro"],
        "Wortmann (TERRA)": ["wortmann"],
        "TUXEDO Computers": ["tuxedo"],
        "Schenker / XMG": ["schenker", "xmg"],
        "SilentiumPC (Endorfy)": ["silentiumpc"],
        "Alpenföhn (EKL)": ["alpenföhn"],
        "Acronis": ["acronis"], "ABUS": ["abus"], "Acer": ["acer"], "ADATA": ["adata"],
        "Adesso": ["adesso"], "AG Neovo": ["ag neovo"], "Alcatel-Lucent Enterprise": ["alcatel-lucent"],
        "Allied Telesis": ["allied telesis"], "AMD": ["amd", "advanced micro devices"], "AOC": ["aoc"],
        "APC (Schneider Electric)": ["apc", "american power conversion"], "Aqua Computer": ["aqua computer"],
        "Arista": ["arista"], "Aruba (HPE)": ["aruba"], "Audio-Technica": ["audio-technica"],
        "Aten": ["aten"], "AVM (FRITZ!)": ["avm"], "Bachmann": ["bachmann"], "baramundi": ["baramundi"],
        "Barco": ["barco"], "be quiet!": ["be quiet"], "Belinea": ["belinea"], "BenQ": ["benq"],
        "beyerdynamic": ["beyerdynamic"], "Bitdefender": ["bitdefender"], "bluechip": ["bluechip"],
        "Bosch": ["bosch"], "Brennenstuhl": ["brennenstuhl"], "Brother": ["brother"], "Canon": ["canon"],
        "CHERRY": ["cherry"], "Cisco": ["cisco"], "Compulab": ["compulab"], "Cooler Master": ["cooler master"],
        "Corsair": ["corsair"], "Crucial (Micron)": ["crucial"], "CSL-Computer": ["csl-computer"],
        "D-Link": ["d-link"], "Da-Lite": ["da-lite"], "Datacolor": ["datacolor"], "Datalogic": ["datalogic"],
        "Delock": ["delock"], "Develop": ["develop"], "devolo": ["devolo"], "Digitus (ASSMANN)": ["digitus"],
        "DrayTek": ["draytek"], "Dynabook (Toshiba)": ["dynabook"], "DYMO": ["dymo"], "Eaton": ["eaton"],
        "Eizo": ["eizo"], "Eminent": ["eminent"], "EPOS": ["epos"], "Epson": ["epson"], "ESET": ["eset"],
        "EVGA": ["evga"], "Fairphone": ["fairphone"], "Fellowes": ["fellowes"], "Fortinet": ["fortinet"],
        "Fractal Design": ["fractal design"], "Fujifilm": ["fujifilm"], "Fujitsu": ["fujitsu"],
        "G DATA": ["g data"], "G.Skill": ["g.skill"], "Garmin": ["garmin"], "Gigaset": ["gigaset"],
        "Goobay": ["goobay"], "GoodRAM": ["goodram"], "Google": ["google"], "GoPro": ["gopro"],
        "Hama": ["hama"], "Hannspree": ["hannspree"], "Harting": ["harting"], "Homematic IP (eQ-3)": ["homematic ip"],
        "HTC": ["htc"], "Huawei": ["huawei"], "HYRICAN": ["hyrican"], "HyperX": ["hyperx"],
        "IBM": ["ibm", "international business machines"], "iFixit": ["ifixit"], "iiyama": ["iiyama"],
        "InLine (INTOS)": ["inline"], "Insta360": ["insta360"], "Intenso": ["intenso"],
        "Inter-Tech": ["inter-tech"], "Intel": ["intel"], "IOGEAR": ["iogear"], "iRobot": ["irobot"],
        "Jabra": ["jabra"], "Jaybird": ["jaybird"], "JBL": ["jbl"], "Juniper": ["juniper"],
        "Kaspersky": ["kaspersky"], "Kensington": ["kensington"], "Keychron": ["keychron"],
        "Kingston": ["kingston"], "KIOXIA": ["kioxia"], "Konftel": ["konftel"], "Kyocera": ["kyocera"],
        "Lacie (Seagate)": ["lacie"], "Lancom": ["lancom"], "Lenovo": ["lenovo"], "Lexar": ["lexar"],
        "Lexmark": ["lexmark"], "LG": ["lg", "lg electronics"], "Lian Li": ["lian li"], "LINDY": ["lindy"],
        "LogiLink": ["logilink"], "Logitech": ["logitech"], "M-Audio": ["m-audio"], "Matrox": ["matrox"],
        "MediaTek": ["mediatek"], "MEDION": ["medion"], "Mevo": ["mevo"], "Microchip": ["microchip"],
        "Microsoft": ["microsoft"], "MikroTik": ["mikrotik"], "Naim": ["naim"], "Ncase": ["ncase"],
        "NEC": ["nec"], "NetApp": ["netapp"], "NFC": ["nfc"], "Nikon": ["nikon"], "NOCTUA": ["noctua"],
        "Nokia": ["nokia"], "Nvidia": ["nvidia"], "Oculus (Meta)": ["oculus"], "OKI": ["oki"],
        "Okuma": ["okuma"], "OnePlus": ["oneplus"], "Optoma": ["optoma"], "Orbi (Netgear)": ["orbi"],
        "OWC (Other World Computing)": ["owc", "other world computing"], "Palo Alto Networks": ["palo alto networks"],
        "Panduit": ["panduit"], "Patriot": ["patriot"], "Philips": ["philips"],
        "Plantronics (Poly)": ["plantronics"], "PNY": ["pny"], "Poly (HP)": ["poly"],
        "PowerWalker (BlueWalker)": ["powerwalker"], "QNAP": ["qnap"], "QPAD": ["qpad"],
        "Qualcomm": ["qualcomm"], "Raspberry Pi": ["raspberry pi"], "Razer": ["razer"],
        "Realtek": ["realtek"], "Ricoh": ["ricoh"], "Ring": ["ring"], "Rittal": ["rittal"],
        "Roland": ["roland"], "Sabrent": ["sabrent"], "Samsung": ["samsung"],
        "SanDisk (Western Digital)": ["sandisk"], "Seagate": ["seagate"], "Seasonic": ["seasonic"],
        "Sennheiser": ["sennheiser"], "Sharkoon": ["sharkoon"], "Sharp/NEC": ["sharp"],
        "Shelly": ["shelly"], "Shure": ["shure"], "Siemens": ["siemens"], "SilverStone": ["silverstone"],
        "SK hynix": ["sk hynix", "hynix"], "Snom": ["snom"], "Sophos": ["sophos"], "Sony": ["sony"],
        "StarTech": ["startech"], "SteelSeries": ["steelseries"], "Synology": ["synology"],
        "TA Triumph-Adler": ["ta triumph-adler"], "tado°": ["tado"], "Targus": ["targus"], "TCL": ["tcl"],
        "TeamGroup": ["teamgroup"], "TeamViewer": ["teamviewer"], "TerraMaster": ["terramaster"],
        "Teufel": ["teufel"], "Thermaltake": ["thermaltake"], "Thrustmaster": ["thrustmaster"],
        "TP-Link": ["tp-link"], "Transcend": ["transcend"], "Trend Micro": ["trend micro"],
        "Tripp Lite (Eaton)": ["tripp lite"], "Triton": ["triton"], "Ubiquiti": ["ubiquiti"],
        "Unifi (Ubiquiti)": ["unifi"], "UTAX": ["utax"], "Valueline": ["valueline"], "Veeam": ["veeam"],
        "Verbatism": ["verbatism"], "Veritas": ["veritas"], "ViewSonic": ["viewsonic"],
        "Vivitek": ["vivitek"], "Wacom": ["wacom"], "WatchGuard": ["watchguard"],
        "Western Digital": ["western digital", "wd"], "Wyze": ["wyze"], "Xerox": ["xerox"],
        "XFX": ["xfx"], "Yealink": ["yealink"], "Yi Technology": ["yi technology"], "Zebra": ["zebra"],
        "Zyxel": ["zyxel"],
    }
    
    lower_name = name.lower()
    lower_name = re.sub(r'[\s,]* (inc|corporation|corp|ltd|gmbh|computer)[\.]?$', '', lower_name).strip()

    for canonical, aliases in MANUFACTURER_MAP.items():
        for alias in aliases:
            if len(alias) <= 3:
                if re.search(r'\b' + re.escape(alias) + r'\b', lower_name):
                    return canonical
            else:
                if alias in lower_name:
                    return canonical

    return name.strip()

def _standardize_os_name(raw_name):
    if not raw_name: return "Unknown"
    lower_raw_name = raw_name.lower()
    OS_MAP = {
        "Windows 11": ["windows 11", "win11"], "Windows 10": ["windows 10", "win10"],
        "Windows 7": ["windows 7", "win7"], "Windows Server 2025": ["windows server 2025"],
        "Windows Server 2022": ["windows server 2022"], "Windows Server 2019": ["windows server 2019"],
        "Windows Server 2016": ["windows server 2016"], "Windows Server 2012 R2": ["windows server 2012 r2"],
        "Windows Server 2008 R2": ["windows server 2008 r2"],
        "Ubuntu Server LTS 22.04 / 24.04": ["ubuntu server 24.04", "ubuntu 24.04 lts", "ubuntu 22.04 lts", "ubuntu server 22.04"],
        "Debian 12": ["debian 12"], "RHEL 8 / 9": ["rhel 9", "red hat enterprise linux 9", "rhel 8", "red hat enterprise linux 8"],
        "SUSE SLES 15": ["suse sles 15", "sles 15"], "iOS 26": ["ios 26"], "iOS 18": ["ios 18"], "iOS 17": ["ios 17"],
        "Android": ["android"], "VMware ESXi": ["vmware esxi", "esxi"], "Microsoft Hyper-V": ["microsoft hyper-v", "hyper-v"],
        "Proxmox VE": ["proxmox ve", "proxmox"], "macOS": ["macos", "os x", "darwin"],
        "Sonstige Embedded/CE": ["embedded", "ce", "iot core", "windows ce", "tizen", "webos", "routeros", "vyos"]
    }
    for canonical, keywords in OS_MAP.items():
        for keyword in keywords:
            if keyword in lower_raw_name:
                return canonical
    if "windows" in lower_raw_name: return "Windows"
    if "linux" in lower_raw_name: return "Linux"
    if "mac" in lower_raw_name: return "macOS"
    return raw_name.strip()

def _standardize_os_version(raw_version, os_name_hint=""):
    if not raw_version: return "Unknown"
    lower_raw_version = str(raw_version).lower()
    lower_os_name = os_name_hint.lower()
    if "windows" in lower_os_name:
        for ver in ["25H2", "24H2", "23H2", "22H2", "21H2"]:
            if ver.lower() in lower_raw_version: return ver
        if "windows 11" in lower_os_name:
            if "22621" in lower_raw_version: return "22H2"
            if "22000" in lower_raw_version: return "21H2"
        if "windows 10" in lower_os_name:
            if "19045" in lower_raw_version: return "22H2"
            if "19044" in lower_raw_version: return "21H2"
        if "10" == lower_raw_version: return "10"
        if "7" == lower_raw_version: return "7"
    if "macos" in lower_os_name or "os x" in lower_os_name:
        versions = {"High Sierra 10.13": ["10.13", "high sierra"], "Mojave 10.14": ["10.14", "mojave"],
                    "Catalina 10.15": ["10.15", "catalina"], "Big Sur 11": ["11.", "big sur"],
                    "Monterey 12": ["12.", "monterey"], "Ventura 13": ["13.", "ventura"],
                    "Sonoma 14": ["14.", "sonoma"], "Sequoia 15": ["15.", "sequoia"]}
        for name, keys in versions.items():
            if any(key in lower_raw_version for key in keys): return name
    if "android" in lower_os_name:
        versions = {"16 Baklava": ["16", "baklava"], "15 Vanilla Ice Cream": ["15", "vanilla ice cream"],
                    "14 Upside Down Cake": ["14", "upside down cake"], "13 Tiramisu": ["13", "tiramisu"],
                    "12L Snow Cone": ["12l"], "12 Snow Cone": ["12", "snow cone"],
                    "11 Red Velvet Cake": ["11", "red velvet cake"], "10 Quince Tart": ["10", "quince tart"],
                    "9 Pie": ["9", "pie"], "8.1 Oreo": ["8.1"], "8.0 Oreo": ["8.0", "oreo"],
                    "7.1 Nougat": ["7.1"], "7.0 Nougat": ["7.0", "nougat"], "6.0 Marshmallow": ["6.0", "marshmallow"],
                    "5.1 Lollipop": ["5.1"], "5.0 Lollipop": ["5.0", "lollipop"], "4.4 KitKat": ["4.4", "kitkat"],
                    "4.3 Jelly Bean": ["4.3"], "4.2 Jelly Bean": ["4.2"], "4.1 Jelly Bean": ["4.1"],
                    "4.0 Ice Cream Sandwich": ["4.0", "ice cream sandwich"]}
        for name, keys in versions.items():
            if any(key in lower_raw_version for key in keys): return name
    return raw_version.strip()

def _standardize_os_edition(raw_edition, os_name_hint=""):
    if not raw_edition: return "Unknown"
    lower_raw_edition = raw_edition.lower()
    if "pro for workstations" in lower_raw_edition: return "Pro for Workstations"
    if "pro" in lower_raw_edition: return "Pro"
    if "enterprise" in lower_raw_edition: return "Enterprise"
    if "education" in lower_raw_edition: return "Education"
    if "home" in lower_raw_edition: return "Home"
    if "server" in lower_raw_edition: return "Server"
    if "desktop" in lower_raw_edition: return "Desktop"
    if "workstation" in lower_raw_edition: return "Workstation"
    return raw_edition.strip()

class SystemInfoGatherer:
    def __init__(self, status_callback=None):
        self.info = {}
        self.system = platform.system()
        self.status_callback = status_callback
        
    def _update_status(self, message, step=None, total_steps=None):
        """Update status via callback if provided."""
        if self.status_callback:
            if step is not None and total_steps is not None:
                progress_msg = f"[{step}/{total_steps}] {message}"
            else:
                progress_msg = message
            self.status_callback(progress_msg)
        log.info(message)

    def gather_all_info(self):
        """Gather all system information using the best available methods."""
        total_steps = 13
        
        if self.system == "Windows":
            pythoncom.CoInitializeEx(0)
            
        self._update_status("Initializing system information gathering...", 1, total_steps)
        
        self.info = {}
        
        self._update_status("Getting computer name...", 2, total_steps)
        self.info["name"] = self.get_computer_name()
        
        self._update_status("Retrieving serial number...", 3, total_steps)
        self.info["serial"] = self.get_serial_number()
        
        self._update_status("Detecting computer type...", 4, total_steps)
        self.info["computer_type"] = self.get_computer_type()
        
        self._update_status("Detecting manufacturer...", 5, total_steps)
        self.info["manufacturer"] = self.get_manufacturer()
        
        self._update_status("Getting system model...", 6, total_steps)
        self.info["model"] = self.get_model()
        
        self._update_status("Identifying operating system...", 7, total_steps)
        self.info["os"] = self.get_operating_system()
        
        self._update_status("Getting OS version...", 8, total_steps)
        self.info["os_version"] = self.get_os_version()
        
        self._update_status("Getting OS edition...", 9, total_steps)
        self.info["os_edition"] = self.get_os_edition()
        
        self._update_status("Detecting processor...", 10, total_steps)
        self.info["processor"] = self.get_processor()
        
        self._update_status("Scanning graphics cards...", 11, total_steps)
        self.info["gpu"] = self.get_gpu()
        
        self._update_status("Analyzing memory and storage...", 12, total_steps)
        self.info["ram"] = self.get_ram_info()
        self.info["hdd"] = self.get_storage_info()
        
        self._update_status("Checking battery health...", 13, total_steps)
        self.info["battery_health"] = self.get_battery_health()
        
        self._update_status("System information gathering completed successfully!")
        log.info("System information gathering complete.")
        return self.info

    def get_computer_name(self):
        return platform.node()

    def get_serial_number(self):
        if self.system == "Windows" and WMI_AVAILABLE:
            try:
                self._update_status("Querying WMI for BIOS serial number...")
                return wmi.WMI().Win32_BIOS()[0].SerialNumber.strip()
            except Exception as e:
                log.warning(f"WMI failed to get serial number: {e}")
                self._update_status("WMI query failed, serial number unavailable")
        elif self.system == "Linux":
            self._update_status("Running dmidecode for serial number...")
            return _run_command(['sudo', 'dmidecode', '-s', 'system-serial-number'])
        return "Unknown"

    def get_computer_type(self):
        """Detect if the computer is a Desktop or Laptop."""
        if self.system == "Windows" and WMI_AVAILABLE:
            try:
                self._update_status("Querying WMI for computer type...")
                # Check chassis type via WMI
                chassis_types = wmi.WMI().Win32_SystemEnclosure()
                for chassis in chassis_types:
                    if chassis.ChassisTypes:
                        chassis_type = chassis.ChassisTypes[0]
                        # SMBIOS chassis type codes:
                        # 8, 9, 10, 14 = Laptop/Portable
                        # 3, 4, 5, 6, 7, 15, 16 = Desktop/Tower
                        if chassis_type in [8, 9, 10, 14]:
                            return "Laptop"
                        elif chassis_type in [3, 4, 5, 6, 7, 15, 16]:
                            return "Desktop"
                
                # Fallback: Check for battery presence
                batteries = wmi.WMI().Win32_Battery()
                if batteries:
                    return "Laptop"
                else:
                    return "Desktop"
                    
            except Exception as e:
                log.warning(f"WMI computer type detection failed: {e}")
                self._update_status("WMI query failed for computer type")
        
        elif self.system == "Linux":
            try:
                self._update_status("Running dmidecode for computer type...")
                # Check chassis type via dmidecode
                output = _run_command(['sudo', 'dmidecode', '-s', 'chassis-type'])
                if output:
                    chassis_type = output.lower().strip()
                    laptop_types = ['laptop', 'notebook', 'portable', 'sub notebook', 'handheld']
                    desktop_types = ['desktop', 'tower', 'mini tower', 'space-saving', 'pizza box', 'mini', 'stick']
                    
                    if any(ltype in chassis_type for ltype in laptop_types):
                        return "Laptop"
                    elif any(dtype in chassis_type for dtype in desktop_types):
                        return "Desktop"
                
                # Fallback: Check for battery in /sys/class/power_supply
                try:
                    base_path = "/sys/class/power_supply"
                    if os.path.exists(base_path):
                        batteries = [b for b in os.listdir(base_path) if b.startswith("BAT")]
                        if batteries:
                            return "Laptop"
                        else:
                            return "Desktop"
                except Exception:
                    pass
                    
            except Exception as e:
                log.warning(f"Linux computer type detection failed: {e}")
                self._update_status("dmidecode failed for computer type")
        
        # Final fallback: assume Desktop if we can't determine
        return "Desktop"

    def get_manufacturer(self):
        """Get the cleaned manufacturer name."""
        full_name = "Unknown"
        if self.system == "Windows" and WMI_AVAILABLE:
            try:
                self._update_status("Querying WMI for system manufacturer...")
                full_name = wmi.WMI().Win32_ComputerSystem()[0].Manufacturer
            except Exception as e:
                log.warning(f"WMI failed to get manufacturer: {e}")
                self._update_status("WMI query failed for manufacturer")
        elif self.system == "Linux":
            self._update_status("Running dmidecode for manufacturer...")
            full_name = _run_command(['sudo', 'dmidecode', '-s', 'system-manufacturer'])
        
        return _clean_manufacturer_name(full_name)

    def get_model(self):
        if self.system == "Windows" and WMI_AVAILABLE:
            try:
                self._update_status("Querying WMI for system model...")
                return wmi.WMI().Win32_ComputerSystem()[0].Model.strip()
            except Exception as e:
                log.warning(f"WMI failed to get model: {e}")
                self._update_status("WMI query failed for model")
        elif self.system == "Linux":
            self._update_status("Running dmidecode for system model...")
            return _run_command(['sudo', 'dmidecode', '-s', 'system-product-name'])
        return "Unknown"

    def get_operating_system(self):
        if self.system == "Windows":
            self._update_status("Detecting Windows edition...")
            return self._get_windows_edition()
        elif self.system == "Linux":
            self._update_status("Detecting Linux distribution...")
            return self._get_linux_distro()
        else:
            return platform.system()

    def get_os_version(self):
        if self.system == "Windows":
            self._update_status("Getting Windows version information...")
            return self._get_windows_version()
        elif self.system == "Linux":
            self._update_status("Getting Linux version information...")
            return self._get_linux_version()
        else:
            return platform.release()

    def get_os_edition(self):
        """Get the operating system edition (Pro, Home, Enterprise, etc.)"""
        if self.system == "Windows":
            self._update_status("Detecting Windows edition...")
            return self._get_windows_edition_detailed()
        elif self.system == "Linux":
            self._update_status("Detecting Linux edition...")
            return self._get_linux_edition()
        else:
            return "Unknown"

    # --- Windows helpers ---

    def _get_windows_edition(self):
        # Try to get the marketing name (e.g., "Windows 11")
        try:
            self._update_status("Running systeminfo command...")
            # Try using systeminfo (works on most Windows)
            output = subprocess.check_output("systeminfo", shell=True, text=True, encoding="utf-8", errors="ignore")
            match = re.search(r"OS Name:\s*(.*)", output)
            if match:
                name = match.group(1).strip()
                # Usually like "Microsoft Windows 11 Pro"
                if "Windows" in name:
                    # Return "Windows 11" or "Windows 10" etc.
                    match2 = re.search(r"(Windows \d+)", name)
                    if match2:
                        return match2.group(1)
                    else:
                        return name
        except Exception:
            self._update_status("systeminfo command failed, using fallback...")

        # Fallback: Use platform.release()
        rel = platform.release()
        if rel == "10":
            # Could be Windows 10 or 11, try to check build number
            build = platform.version()
            try:
                build_num = int(build.split(".")[2])
                if build_num >= 22000:
                    return "Windows 11"
                else:
                    return "Windows 10"
            except Exception:
                return "Windows 10/11"
        elif rel == "11":
            return "Windows 11"
        else:
            return f"Windows {rel}"

    def _get_windows_version(self):
        # Try to get the update version (e.g., "24H2", "22H2") from systeminfo
        try:
            self._update_status("Analyzing Windows version details...")
            output = subprocess.check_output("systeminfo", shell=True, text=True, encoding="utf-8", errors="ignore")
            # Look for "24H2", "22H2", etc. anywhere in the output
            match = re.search(r"\b\d{2}H2\b", output)
            if match:
                return match.group(0)
            # Try to find "Version: 24H2" or "Version 24H2"
            match2 = re.search(r"Version[:\s]+(\d{2}H2)", output)
            if match2:
                return match2.group(1)
        except Exception:
            self._update_status("systeminfo failed, checking registry...")

        # Try registry (DisplayVersion or ReleaseId)
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion") as key:
                try:
                    display_version, _ = winreg.QueryValueEx(key, "DisplayVersion")
                    if re.match(r"\d{2}H2", display_version):
                        return display_version
                except FileNotFoundError:
                    pass
                try:
                    release_id, _ = winreg.QueryValueEx(key, "ReleaseId")
                    if re.match(r"\d{2}H2", release_id):
                        return release_id
                except FileNotFoundError:
                    pass
        except Exception:
            self._update_status("Registry access failed, using build number...")

        # Fallback: Try to extract from build number
        try:
            build = platform.version()
            build_num = int(build.split(".")[2])
            # Map known build numbers to marketing versions
            build_map = {
                22000: "21H2",
                22621: "22H2",
                26100: "24H2",
                # Add more mappings as needed
            }
            for b, v in build_map.items():
                if build_num >= b:
                    version = v
            if 'version' in locals():
                return version
            else:
                return f"Build {build_num}"
        except Exception:
            pass

        # Last fallback
        return platform.release()

    def _get_windows_edition_detailed(self):
        """Get detailed Windows edition information."""
        try:
            self._update_status("Running systeminfo for Windows edition...")
            output = subprocess.check_output("systeminfo", shell=True, text=True, encoding="utf-8", errors="ignore")
            match = re.search(r"OS Name:\s*(.*)", output)
            if match:
                name = match.group(1).strip()
                # Extract edition (Pro, Home, Enterprise, etc.)
                if "Pro" in name:
                    return "Pro"
                elif "Home" in name:
                    return "Home"
                elif "Enterprise" in name:
                    return "Enterprise"
                elif "Education" in name:
                    return "Education"
                elif "Server" in name:
                    return "Server"
        except Exception:
            self._update_status("systeminfo failed for edition, trying registry...")
        
        # Try registry
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion") as key:
                try:
                    edition_id, _ = winreg.QueryValueEx(key, "EditionID")
                    return edition_id
                except FileNotFoundError:
                    pass
                try:
                    product_name, _ = winreg.QueryValueEx(key, "ProductName")
                    if "Pro" in product_name:
                        return "Pro"
                    elif "Home" in product_name:
                        return "Home"
                    elif "Enterprise" in product_name:
                        return "Enterprise"
                except FileNotFoundError:
                    pass
        except Exception:
            pass
        
        return "Unknown"

    # --- Linux helpers ---

    def _get_linux_distro(self):
        try:
            self._update_status("Running lsb_release...")
            # Try lsb_release
            output = subprocess.check_output(["lsb_release", "-d"], text=True)
            match = re.search(r"Description:\s*(.*)", output)
            if match:
                return match.group(1).strip()
        except Exception:
            self._update_status("lsb_release failed, checking /etc/os-release...")
        # Try /etc/os-release
        try:
            with open("/etc/os-release") as f:
                for line in f:
                    if line.startswith("PRETTY_NAME="):
                        return line.strip().split("=", 1)[1].strip('"')
        except Exception:
            self._update_status("Could not determine Linux distribution")
        return "Linux"

    def _get_linux_version(self):
        try:
            self._update_status("Getting Linux release version...")
            # Try lsb_release
            output = subprocess.check_output(["lsb_release", "-r"], text=True)
            match = re.search(r"Release:\s*(.*)", output)
            if match:
                return match.group(1).strip()
        except Exception:
            self._update_status("lsb_release failed, checking /etc/os-release...")
        # Try /etc/os-release
        try:
            with open("/etc/os-release") as f:
                for line in f:
                    if line.startswith("VERSION_ID="):
                        return line.strip().split("=", 1)[1].strip('"')
        except Exception:
            self._update_status("Could not determine Linux version")
        return platform.release()

    def _get_linux_edition(self):
        """Get Linux edition/variant information."""
        try:
            # Check for specific editions in /etc/os-release
            with open("/etc/os-release") as f:
                content = f.read()
                if "VARIANT=" in content:
                    match = re.search(r'VARIANT="([^"]*)"', content)
                    if match:
                        return match.group(1)
                if "VARIANT_ID=" in content:
                    match = re.search(r'VARIANT_ID="?([^"\n]*)"?', content)
                    if match:
                        return match.group(1)
        except Exception:
            pass
        
        # Check for common Linux editions
        try:
            with open("/etc/os-release") as f:
                content = f.read().lower()
                if "server" in content:
                    return "Server"
                elif "desktop" in content:
                    return "Desktop"
                elif "workstation" in content:
                    return "Workstation"
        except Exception:
            pass
        
        return "Desktop"  # Default for Linux

    def get_processor(self):
        full_name = "Unknown"
        if self.system == "Windows" and WMI_AVAILABLE:
            try:
                self._update_status("Querying WMI for processor information...")
                full_name = wmi.WMI().Win32_Processor()[0].Name.strip()
            except Exception as e:
                log.warning(f"WMI processor query failed: {e}")
        elif self.system == "Linux":
            self._update_status("Running lscpu for processor information...")
            output = _run_command(['lscpu'])
            if output:
                match = re.search(r'Model name:\s+(.+)', output)
                if match:
                    full_name = match.group(1).strip()
        return _clean_processor_name(full_name)

    def get_gpu(self):
        """Get the primary GPU, prioritizing dedicated cards over integrated ones."""
        gpus = []
        
        if self.system == "Windows" and WMI_AVAILABLE:
            try:
                self._update_status("Querying WMI for graphics cards...")
                wmi_gpus = wmi.WMI().Win32_VideoController()
                for gpu in wmi_gpus:
                    if gpu.Name:
                        gpus.append(gpu.Name.strip())
            except Exception as e:
                log.warning(f"WMI graphics query failed: {e}")
        elif self.system == "Linux":
            self._update_status("Running lspci for graphics information...")
            output = _run_command(['lspci'])
            if output:
                for line in output.splitlines():
                    if "VGA compatible controller" in line:
                        gpu_name = line.split(":")[-1].strip()
                        gpus.append(gpu_name)
        
        if not gpus:
            self._update_status("No graphics cards detected")
            return "Unknown"
        
        self._update_status(f"Found {len(gpus)} graphics adapter(s), filtering...")
        filtered_gpus = self._filter_virtual_gpus(gpus)
        
        if not filtered_gpus:
            self._update_status("No physical graphics cards found after filtering")
            return "Unknown"
        
        self._update_status("Prioritizing dedicated graphics cards...")
        prioritized_gpu = self._prioritize_gpu(filtered_gpus)
        
        return _clean_gpu_name(prioritized_gpu)

    def _filter_virtual_gpus(self, gpu_list):
        """Filter out virtual, remote, and fake graphics adapters."""
        virtual_keywords = [
            "spacedesk", "parsec", "teamviewer", "vnc", "rdp", "remote", "virtual",
            "microsoft basic display adapter", "microsoft basic render driver",
            "generic pnp monitor", "standard vga", "citrix", "vmware", "virtualbox",
            "hyper-v", "qemu", "parallels"
        ]
        
        filtered = [gpu for gpu in gpu_list if not any(keyword in gpu.lower() for keyword in virtual_keywords)]
        log.debug(f"Filtered GPUs: {gpu_list} -> {filtered}")
        return filtered

    def _prioritize_gpu(self, gpu_list):
        """Prioritize dedicated graphics cards over integrated ones."""
        if len(gpu_list) == 1:
            return gpu_list[0]
        
        dedicated_keywords = ["geforce", "gtx", "rtx", "quadro", "tesla", "radeon", "rx ", "vega", "fury", "firepro", "arc"]
        integrated_keywords = ["intel hd", "intel uhd", "intel iris", "intel graphics", "amd radeon graphics", "radeon graphics", "vega graphics", "ryzen", "apu"]
        
        dedicated_gpus = [gpu for gpu in gpu_list if any(keyword in gpu.lower() for keyword in dedicated_keywords)]
        integrated_gpus = [gpu for gpu in gpu_list if any(keyword in gpu.lower() for keyword in integrated_keywords)]
        
        if dedicated_gpus:
            selected = dedicated_gpus[0]
            log.debug(f"Selected dedicated GPU: {selected} from {gpu_list}")
            return selected
        
        other_gpus = [gpu for gpu in gpu_list if gpu not in integrated_gpus]
        if other_gpus:
            selected = other_gpus[0]
            log.debug(f"Selected other GPU: {selected} from {gpu_list}")
            return selected
        
        selected = integrated_gpus[0] if integrated_gpus else gpu_list[0]
        log.debug(f"Selected integrated GPU: {selected} from {gpu_list}")
        return selected

    def get_ram_info(self):
        total_gb = 0
        ram_type = ""
        modules = []
        
        if self.system == "Windows" and WMI_AVAILABLE:
            try:
                self._update_status("Querying WMI for memory information...")
                c = wmi.WMI()
                memory_modules = c.Win32_PhysicalMemory()
                
                # Calculate total memory
                total_bytes = sum(int(mem.Capacity) for mem in memory_modules if mem.Capacity)
                total_gb = round(total_bytes / (1024**3))
                
                mem_types = {20: "DDR", 21: "DDR2", 24: "DDR3", 26: "DDR4", 34: "DDR5"}
                form_map = {8: "DIMM", 12: "SO-DIMM"}
                for mem in memory_modules:
                    size_gb = 0
                    try:
                        if mem.Capacity:
                            size_gb = round(int(mem.Capacity) / (1024**3))
                    except Exception:
                        pass
                    mtype = None
                    if mem.MemoryType and mem.MemoryType in mem_types:
                        mtype = mem_types[mem.MemoryType]
                    speed = None
                    try:
                        if getattr(mem, 'Speed', None):
                            speed = int(mem.Speed)
                        elif getattr(mem, 'ConfiguredClockSpeed', None):
                            speed = int(mem.ConfiguredClockSpeed)
                    except Exception:
                        speed = None
                    form = None
                    try:
                        ff = getattr(mem, 'FormFactor', None)
                        if ff in form_map:
                            form = form_map[ff]
                    except Exception:
                        form = None
                    modules.append({"size": size_gb, "type": mtype, "speed": speed, "form": form})
                for m in modules:
                    if m.get("type"):
                        ram_type = m["type"]
                        break
                
                # If WMI doesn't provide type, try to get it from manufacturer/part number
                if not ram_type:
                    for mem in memory_modules:
                        if mem.PartNumber:
                            part_num = mem.PartNumber.strip().upper()
                            if "DDR5" in part_num:
                                ram_type = "DDR5"
                                break
                            elif "DDR4" in part_num:
                                ram_type = "DDR4"
                                break
                            elif "DDR3" in part_num:
                                ram_type = "DDR3"
                                break
                            elif "DDR2" in part_num:
                                ram_type = "DDR2"
                                break
                            elif "DDR" in part_num:
                                ram_type = "DDR"
                                break
                                
            except Exception as e:
                log.warning(f"WMI memory query failed: {e}")
                self._update_status("WMI memory query failed, trying alternative methods...")
        
        elif self.system == "Linux":
            self._update_status("Running dmidecode for memory information...")
            output = _run_command(['sudo', 'dmidecode', '--type', 'memory'])
            if output:
                total_gb_calc = 0
                memory_types = []
                current_module = {}
                for line in output.splitlines():
                    line = line.strip()
                    
                    if line.startswith("Memory Device"):
                        # Start of new memory device section
                        if current_module.get('size') and current_module.get('type'):
                            memory_types.append(current_module['type'])
                            total_gb_calc += current_module['size']
                            modules.append(current_module)
                        current_module = {}
                        
                    elif "Size:" in line and "No Module Installed" not in line and "Unknown" not in line:
                        parts = line.split()
                        if len(parts) >= 2:
                            try:
                                size = int(parts[1])
                                unit = parts[2] if len(parts) > 2 else ""
                                if unit.upper() == "MB":
                                    current_module['size'] = size / 1024
                                elif unit.upper() == "GB":
                                    current_module['size'] = size
                            except (ValueError, IndexError):
                                continue
                                
                    elif "Type:" in line:
                        type_parts = line.split(":", 1)
                        if len(type_parts) > 1:
                            mem_type = type_parts[1].strip()
                            # Clean up the memory type
                            if mem_type and mem_type != "Unknown" and mem_type != "<OUT OF SPEC>":
                                current_module['type'] = mem_type
                    elif "Form Factor:" in line:
                        ff = line.split(":", 1)[1].strip().upper()
                        if ff:
                            if "SODIMM" in ff or "SO-DIMM" in ff:
                                current_module['form'] = "SO-DIMM"
                            elif "DIMM" in ff:
                                current_module['form'] = "DIMM"
                    elif "Speed:" in line or "Configured Clock Speed:" in line:
                        sp = line.split(":", 1)[1]
                        digits = ''.join(ch for ch in sp if ch.isdigit())
                        if digits:
                            try:
                                current_module['speed'] = int(digits)
                            except Exception:
                                pass
                
                # Process the last module
                if current_module.get('size') and current_module.get('type'):
                    memory_types.append(current_module['type'])
                    total_gb_calc += current_module['size']
                    modules.append(current_module)
                
                total_gb = round(total_gb_calc)
                
                # Use the most common memory type found
                if memory_types:
                    ram_type = max(set(memory_types), key=memory_types.count)

        # Fallback to psutil if we couldn't get the info above
        if total_gb == 0 and psutil:
            self._update_status("Using psutil for memory information...")
            total_gb = round(psutil.virtual_memory().total / (1024**3))
            
            # Try to get memory type from /proc/meminfo or dmidecode without sudo
            if self.system == "Linux" and not ram_type:
                try:
                    # Try dmidecode without sudo (might work on some systems)
                    output = _run_command(['dmidecode', '--type', 'memory'])
                    if output:
                        for line in output.splitlines():
                            if "Type:" in line:
                                type_parts = line.split(":", 1)
                                if len(type_parts) > 1:
                                    mem_type = type_parts[1].strip()
                                    if mem_type and mem_type != "Unknown":
                                        ram_type = mem_type
                                        break
                except:
                    pass

        if modules:
            best = None
            for m in modules:
                if m.get("size") and m.get("type"):
                    best = m
                    break
            if not best:
                best = modules[0]
            size_int = int(round(best.get("size") or total_gb or 0))
            t = best.get("type") or ram_type or ""
            f = best.get("form") or ("SO-DIMM" if self.system == "Windows" else "DIMM")
            s = best.get("speed")
            if t and size_int > 0:
                if s:
                    return f"{f} {t} {size_int}GB {s}MHz"
                return f"{f} {t} {size_int}GB"
        if total_gb > 0:
            if ram_type:
                return f"{ram_type} {total_gb} GB"
            if total_gb >= 32:
                return f"DDR4 {total_gb} GB"
            elif total_gb >= 8:
                return f"DDR4 {total_gb} GB"
            else:
                return f"DDR3 {total_gb} GB"
        return "Unknown"

    def get_storage_info(self):
        """Get storage information with drive type detection (HDD, SSD, M.2 NVMe, M.2 SATA, mSATA)."""
        if self.system == "Windows" and WMI_AVAILABLE:
            try:
                self._update_status("Analyzing Windows storage devices...")
                return self._get_windows_storage_info()
            except Exception as e:
                log.warning(f"Windows storage detection failed: {e}")
                self._update_status("Windows storage detection failed, using fallback...")
        elif self.system == "Linux":
            try:
                self._update_status("Analyzing Linux storage devices...")
                return self._get_linux_storage_info()
            except Exception as e:
                log.warning(f"Linux storage detection failed: {e}")
                self._update_status("Linux storage detection failed, using fallback...")
        
        # Fallback to basic psutil detection
        if psutil:
            try:
                self._update_status("Using basic storage detection...")
                mount_point = 'C:\\' if self.system == "Windows" else '/'
                usage = psutil.disk_usage(mount_point)
                actual_gib = usage.total / (1024**3)
                rounded_gb = _round_storage_gb(actual_gib)
                return f"SATA {rounded_gb} GB"  # Default assumption for modern systems
            except Exception as e:
                log.warning(f"psutil failed to get disk info: {e}")
                self._update_status("Storage analysis failed")
        
        return "Unknown"

    def _get_windows_storage_info(self):
        """Get Windows storage information with drive type detection."""
        pythoncom.CoInitializeEx(0)
        c = wmi.WMI()
        
        # Get all physical disks and find the boot/system drive
        disks = c.Win32_DiskDrive()
        primary_disk = None
        
        # Method 1: Try to find the boot drive first
        try:
            logical_disks = c.Win32_LogicalDisk()
            boot_drive_letter = None
            for logical in logical_disks:
                if logical.SystemDrive or (logical.DeviceID and logical.DeviceID.startswith('C:')):
                    boot_drive_letter = logical.DeviceID
                    break
            
            if boot_drive_letter:
                # Find which physical disk contains the boot partition
                partitions = c.Win32_DiskPartition()
                for partition in partitions:
                    logical_disks_on_partition = partition.associators("Win32_LogicalDiskToPartition")
                    for logical in logical_disks_on_partition:
                        if logical.DeviceID == boot_drive_letter:
                            # Found the partition, now find the physical disk
                            physical_disks = partition.associators("Win32_DiskDriveToDiskPartition")
                            if physical_disks:
                                primary_disk = physical_disks[0]
                                break
                    if primary_disk:
                        break
        except Exception as e:
            log.warning(f"Boot drive detection failed: {e}")
        
        # Method 2: Fallback to largest drive if boot drive detection failed
        if not primary_disk:
            largest_size = 0
            for disk in disks:
                try:
                    if disk.Size and int(disk.Size) > largest_size:
                        largest_size = int(disk.Size)
                        primary_disk = disk
                except (ValueError, TypeError):
                    continue
        
        # Method 3: Final fallback to first available disk
        if not primary_disk and disks:
            primary_disk = disks[0]
        
        if not primary_disk:
            return "Unknown"
        
        # Calculate size more accurately
        try:
            disk_size_bytes = int(primary_disk.Size) if primary_disk.Size else 0
            # Convert to GiB first, then round to marketing size
            actual_gib = disk_size_bytes / (1024**3)
            rounded_gb = _round_storage_gb(actual_gib)
        except (ValueError, TypeError):
            return "Unknown"
        
        # Determine drive type with better detection
        drive_type = self._determine_windows_drive_type(primary_disk)
        
        # Log detailed information for debugging
        log.debug(f"Selected disk: {getattr(primary_disk, 'Model', 'Unknown')} - "
                  f"Size: {disk_size_bytes} bytes ({actual_gib:.1f} GiB) -> {rounded_gb} GB - "
                  f"Type: {drive_type}")
        
        return f"{drive_type} {rounded_gb} GB"

    def _determine_windows_drive_type(self, disk):
        """Determine the type of Windows drive with improved detection."""
        try:
            # Get all available properties
            interface = getattr(disk, 'InterfaceType', '').upper() if disk.InterfaceType else ''
            model = getattr(disk, 'Model', '').upper() if disk.Model else ''
            media_type = getattr(disk, 'MediaType', '').upper() if disk.MediaType else ''
            caption = getattr(disk, 'Caption', '').upper() if disk.Caption else ''
            
            # Combine model and caption for better detection
            full_model_info = f"{model} {caption}".strip()
            
            log.debug(f"Drive detection - Interface: {interface}, Model: {model}, "
                      f"MediaType: {media_type}, Caption: {caption}")
            
            # Enhanced NVMe detection
            nvme_indicators = ['NVME', 'NVM EXPRESS', 'NVME SSD', 'PM991', 'PM981', 'SN850', 
                              'SN750', 'SN550', 'WD_BLACK', 'KINGSTON NV1', 'CRUCIAL P1', 
                              'CRUCIAL P2', 'CRUCIAL P5']
            
            if (interface == 'NVME' or 
                any(indicator in full_model_info for indicator in nvme_indicators)):
                return "M.2 NVMe"
            
            # Enhanced SSD detection
            ssd_indicators = ['SSD', 'SOLID STATE', 'FLASH', 'SAMSUNG SSD', 'CRUCIAL MX', 
                             'KINGSTON SA', 'WD BLUE', 'INTEL SSD', 'ADATA SU']
            
            is_ssd = (
                'SSD' in full_model_info or 
                'SOLID STATE' in full_model_info or
                media_type == 'SSD' or
                any(indicator in full_model_info for indicator in ssd_indicators) or
                self._is_known_ssd_model(full_model_info)
            )
            
            if is_ssd:
                # Better form factor detection for SSDs
                if any(indicator in full_model_info for indicator in ['M.2', 'M2', 'NGFF']):
                    return "M.2 SATA"
                elif any(indicator in full_model_info for indicator in ['MSATA', 'mSATA']):
                    return "mSATA"
                elif interface in ['SATA', 'IDE', 'ATA']:
                    return "SATA"
                else:
                    # Unknown interface but it's an SSD - make educated guess
                    size_gb = int(disk.Size) / (1024**3) if disk.Size else 0
                    if size_gb <= 128:  # Small drives often mSATA/M.2
                        return "M.2 SATA"
                    else:
                        return "SATA"
            else:
                # Traditional spinning drive indicators
                hdd_indicators = ['WD', 'WESTERN DIGITAL', 'SEAGATE', 'TOSHIBA', 'HITACHI', 
                                 'HGST', 'BARRACUDA', 'BLUE', 'BLACK', 'RED']
                
                # If no SSD indicators and has HDD indicators, or interface suggests mechanical
                if (any(indicator in full_model_info for indicator in hdd_indicators) or
                    interface in ['IDE', 'SATA'] and not is_ssd):
                    return "HDD"
                
                # Default fallback
                return "HDD"
                
        except Exception as e:
            log.warning(f"Error determining Windows drive type: {e}")
            # Safer fallback logic
            if hasattr(disk, 'Model') and disk.Model:
                model_upper = disk.Model.upper()
                if 'NVME' in model_upper or 'NVM' in model_upper:
                    return "M.2 NVMe"
                elif 'SSD' in model_upper:
                    return "SATA"
            return "HDD"

    def _get_linux_storage_info(self):
        """Get Linux storage information with drive type detection."""
        # First, try to find the primary storage device
        primary_device = None
        largest_size = 0
        
        # Method 1: Use lsblk to get block devices
        try:
            output = _run_command(['lsblk', '-J', '-o', 'NAME,SIZE,TYPE,ROTA,TRAN'])
            if output:
                data = json.loads(output)
                for device in data.get('blockdevices', []):
                    if device.get('type') == 'disk':
                        size_str = device.get('size', '0B')
                        # Parse size (e.g., "500G", "1T")
                        size_bytes = self._parse_linux_size(size_str)
                        if size_bytes > largest_size:
                            largest_size = size_bytes
                            primary_device = device
        except Exception as e:
            log.warning(f"lsblk JSON parsing failed: {e}")
        
        # Method 2: Fallback to basic lsblk
        if not primary_device:
            try:
                output = _run_command(['lsblk', '-d', '-o', 'NAME,SIZE,ROTA,TRAN'])
                if output:
                    lines = output.strip().split('\n')[1:]  # Skip header
                    for line in lines:
                        parts = line.split()
                        if len(parts) >= 2:
                            device_name = parts[0]
                            size_str = parts[1]
                            size_bytes = self._parse_linux_size(size_str)
                            if size_bytes > largest_size:
                                largest_size = size_bytes
                                rota = parts[2] if len(parts) > 2 else '1'
                                tran = parts[3] if len(parts) > 3 else ''
                                primary_device = {
                                    'name': device_name,
                                    'size': size_str,
                                    'rota': rota,
                                    'tran': tran
                                }
            except Exception as e:
                log.warning(f"Basic lsblk failed: {e}")
        
        if not primary_device:
            return "Unknown"
        
        # Calculate size
        actual_gib = largest_size / (1024**3)
        rounded_gb = _round_storage_gb(actual_gib)
        
        # Determine drive type
        drive_type = self._determine_linux_drive_type(primary_device)
        
        return f"{drive_type} {rounded_gb} GB"

    def _determine_linux_drive_type(self, device):
        """Determine the type of Linux drive (HDD, SSD, M.2 NVMe, M.2 SATA, mSATA)."""
        try:
            device_name = device.get('name', '')
            transport = device.get('tran', '').lower()
            rotational = device.get('rota', '1') == '1'
            
            # Check for NVMe drives (they appear as nvme* devices)
            if device_name.startswith('nvme') or transport == 'nvme':
                return "M.2 NVMe"
            
            # If it's rotational, it's definitely an HDD
            if rotational:
                return "HDD"
            
            # Non-rotational drive (SSD) - determine interface type
            if transport in ['sata', 'ata']:
                # Try to determine if it's M.2 SATA or regular SATA
                # Check device path for clues
                try:
                    with open(f'/sys/block/{device_name}/device/model', 'r') as f:
                        model = f.read().strip().upper()
                        if 'M.2' in model or 'M2' in model:
                            return "M.2 SATA"
                        elif 'MSATA' in model:
                            return "mSATA"
                except:
                    pass
                
                # Check form factor through other means
                try:
                    # Check if device is in a specific slot type
                    device_path = f'/sys/block/{device_name}/device'
                    if os.path.exists(device_path):
                        # Look for PCI subsystem info that might indicate M.2
                        subsystem_path = os.path.join(device_path, 'subsystem')
                        if os.path.exists(subsystem_path):
                            subsystem = os.readlink(subsystem_path)
                            if 'pci' in subsystem.lower():
                                # Modern SATA SSDs connected via PCIe are often M.2
                                return "M.2 SATA"
                except:
                    pass
                
                return "SATA"
            
            elif transport == 'usb':
                return "SATA"  # USB-connected drives are typically SATA-based
            
            else:
                # Unknown transport, but it's an SSD
                return "SATA"  # Default assumption
                
        except Exception as e:
            log.warning(f"Error determining Linux drive type: {e}")
            return "SATA"

    def _parse_linux_size(self, size_str):
        """Parse Linux size string (e.g., '500G', '1.5T') to bytes."""
        try:
            size_str = size_str.strip().upper()
            if size_str.endswith('B'):
                size_str = size_str[:-1]
            
            multipliers = {
                'K': 1024,
                'M': 1024**2,
                'G': 1024**3,
                'T': 1024**4,
                'P': 1024**5
            }
            
            for suffix, multiplier in multipliers.items():
                if size_str.endswith(suffix):
                    number = float(size_str[:-1])
                    return int(number * multiplier)
            
            # No suffix, assume bytes
            return int(float(size_str))
            
        except (ValueError, TypeError):
            return 0

    def _is_known_ssd_model(self, model):
        """Check if the model name indicates a known SSD manufacturer/series."""
        ssd_indicators = [
            'SAMSUNG SSD', 'CRUCIAL', 'KINGSTON', 'SANDISK', 'INTEL SSD',
            'WD ', 'WESTERN DIGITAL', 'CORSAIR', 'ADATA', 'TRANSCEND',
            'MUSHKIN', 'OCZ', 'PATRIOT', 'PLEXTOR', 'TOSHIBA SSD',
            'LITEON', 'SK HYNIX', 'MICRON'
        ]
        
        model_upper = model.upper()
        return any(indicator in model_upper for indicator in ssd_indicators)

    def get_battery_health(self):
        """Get battery health, trying WMI first, then falling back to powercfg."""
        if self.system == "Windows":
            # --- METHOD 1: Fast WMI check ---
            if WMI_AVAILABLE:
                try:
                    self._update_status("Querying WMI for battery health...")
                    batteries = wmi.WMI().Win32_Battery()
                    if batteries:
                        battery = batteries[0]
                        if battery.DesignCapacity is not None and battery.FullChargeCapacity is not None:
                            design_capacity = int(battery.DesignCapacity)
                            full_charge_capacity = int(battery.FullChargeCapacity)
                            if design_capacity > 0:
                                health = (full_charge_capacity / design_capacity) * 100
                                self._update_status("Successfully retrieved battery health via WMI.")
                                return f"{int(health)}"
                except Exception as e:
                    log.warning(f"WMI battery query failed: {e}")
            
            # --- METHOD 2: Robust powercfg fallback ---
            self._update_status("WMI method failed or unavailable, trying powercfg fallback...")
            temp_report_path = ""
            try:
                # Create a temporary file path
                temp_dir = tempfile.gettempdir()
                temp_report_path = os.path.join(temp_dir, "battery-report.html")
                
                command = ['powercfg', '/batteryreport', '/output', temp_report_path, '/duration', '1']
                _run_command(command)
                
                if not os.path.exists(temp_report_path):
                    log.error("powercfg did not generate a report.")
                    return None

                with open(temp_report_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                
                # --- FIX: More robust regex to find the values ---
                design_cap_match = re.search(r'DESIGN CAPACITY.*?<td.*?>\s*([\d.,]+)\s*mWh', content, re.IGNORECASE | re.DOTALL)
                full_cap_match = re.search(r'FULL CHARGE CAPACITY.*?<td.*?>\s*([\d.,]+)\s*mWh', content, re.IGNORECASE | re.DOTALL)

                if design_cap_match and full_cap_match:
                    design_val_str = design_cap_match.group(1).replace(',', '').replace('.', '')
                    full_val_str = full_cap_match.group(1).replace(',', '').replace('.', '')
                    
                    design_val = int(design_val_str)
                    full_val = int(full_val_str)

                    if design_val > 0:
                        health = (full_val / design_val) * 100
                        self._update_status("Successfully parsed battery health from powercfg report.")
                        return f"{int(health)}"
                else:
                    self._update_status("Could not parse battery report.")
                    log.warning("Failed to find capacity values in powercfg report.")

            except Exception as e:
                self._update_status("powercfg command failed.")
                log.error(f"Failed to get battery health via powercfg: {e}")
            finally:
                if temp_report_path and os.path.exists(temp_report_path):
                    try:
                        os.remove(temp_report_path)
                    except OSError as e:
                        log.error(f"Could not remove temporary battery report: {e}")

        elif self.system == "Linux":
            # (Linux implementation remains the same)
            try:
                self._update_status("Checking /sys/class/power_supply for battery...")
                base_path = "/sys/class/power_supply"
                batteries = [b for b in os.listdir(base_path) if b.startswith("BAT")]
                if not batteries:
                    self._update_status("No battery found.")
                    return None
                
                battery_path = os.path.join(base_path, batteries[0])
                
                if os.path.exists(os.path.join(battery_path, "energy_full_design")):
                    with open(os.path.join(battery_path, "energy_full_design")) as f: design = int(f.read())
                    with open(os.path.join(battery_path, "energy_full")) as f: full = int(f.read())
                else:
                    with open(os.path.join(battery_path, "charge_full_design")) as f: design = int(f.read())
                    with open(os.path.join(battery_path, "charge_full")) as f: full = int(f.read())
                
                if design > 0:
                    health = (full / design) * 100
                    return f"{int(health)}"
            except Exception as e:
                log.warning(f"Failed to get battery health on Linux: {e}")
                self._update_status("Failed to read battery health files.")
        
        self._update_status("Battery health could not be determined.")
        return None


def main():
    """For testing purposes: gathers and prints all system info."""
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    def print_status(message):
        print(message)
    
    gatherer = SystemInfoGatherer(status_callback=print_status)
    all_info = gatherer.gather_all_info()
    
    print("\n--- System Information Report ---")
    print(json.dumps(all_info, indent=4))
    print("---------------------------------")

if __name__ == "__main__":
    main()
