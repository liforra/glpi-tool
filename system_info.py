import platform
import subprocess
import json
import logging
import re
import os
from pathlib import Path

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
        result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=15)
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
        log.warning(f"Command '{' '.join(command)}' failed: {e}")
        return None

def _round_storage_gb(gib):
    """Rounds the OS-reported Gibibyte (GiB) size to the nearest common marketing Gigabyte (GB) size."""
    if not gib: return 0
    estimated_marketing_gb = gib * (1024**3 / 1000**3)
    sizes = [120, 128, 240, 250, 256, 480, 500, 512, 960, 1000, 1024, 2048, 4096]
    for size in sizes:
        if size >= estimated_marketing_gb:
            return size
    return round(gib)

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
    """Extracts the core model name from a full GPU brand string."""
    if not name: 
        return "Unknown"
    
    # Remove common prefixes and suffixes
    cleaned_name = re.sub(r'\((R|TM)\)', '', name).strip()
    cleaned_name = re.sub(r'\s+', ' ', cleaned_name)  # Normalize whitespace
    
    # Remove manufacturer prefixes but keep the important part
    prefixes_to_remove = [
        "NVIDIA ", "AMD ", "Intel\\(R\\) ", "Intel ", 
        "Advanced Micro Devices, Inc\\. ", "Corporation "
    ]
    
    for prefix in prefixes_to_remove:
        cleaned_name = re.sub(f"^{prefix}", "", cleaned_name, flags=re.IGNORECASE)
    
    # Special handling for common GPU naming patterns
    if "geforce" in cleaned_name.lower():
        # Extract GeForce model (e.g., "GeForce GTX 1060" -> "GeForce GTX 1060")
        match = re.search(r'(geforce\s+(?:gtx|rtx)?\s*\d+\w*)', cleaned_name, re.IGNORECASE)
        if match:
            return match.group(1)
    
    if "radeon" in cleaned_name.lower():
        # Extract Radeon model (e.g., "Radeon RX 580" -> "Radeon RX 580")
        match = re.search(r'(radeon\s+(?:rx|r\d+)?\s*\d+\w*)', cleaned_name, re.IGNORECASE)
        if match:
            return match.group(1)
    
    if "intel" in cleaned_name.lower() and ("hd" in cleaned_name.lower() or "uhd" in cleaned_name.lower() or "iris" in cleaned_name.lower()):
        # Extract Intel integrated graphics (e.g., "Intel HD Graphics 620" -> "Intel HD Graphics 620")
        match = re.search(r'(intel\s+(?:hd|uhd|iris)\s+graphics\s*\d*)', cleaned_name, re.IGNORECASE)
        if match:
            return match.group(1)
    
    return cleaned_name.strip() if cleaned_name.strip() else name

def _clean_manufacturer_name(name):
    """Removes common corporate suffixes from a manufacturer name."""
    if not name: return "Unknown"
    # List of suffixes to remove, case-insensitive.
    # The regex looks for these words at the end of the string, preceded by optional space/comma.
    suffixes = ["Inc", "Corporation", "Corp", "Limited", "Ltd", "Company"]
    pattern = r'[\s,]*(' + '|'.join(suffixes) + r')\.?$'
    cleaned_name = re.sub(pattern, '', name, flags=re.IGNORECASE)
    return cleaned_name.strip()

class SystemInfoGatherer:
    def __init__(self):
        self.info = {}
        self.system = platform.system()

    def gather_all_info(self):
        """Gather all system information using the best available methods."""
        if self.system == "Windows":
            pythoncom.CoInitializeEx(0)
            
        log.info("Starting system information gathering...")
        self.info = {
            "name": self.get_computer_name(),
            "serial": self.get_serial_number(),
            "manufacturer": self.get_manufacturer(),
            "model": self.get_model(),
            "os": self.get_operating_system(),
            "os_version": self.get_os_version(),
            "processor": self.get_processor(),
            "gpu": self.get_gpu(),
            "ram": self.get_ram_info(),
            "hdd": self.get_storage_info(),
        }
        log.info("System information gathering complete.")
        return self.info

    def get_computer_name(self):
        return platform.node()

    def get_serial_number(self):
        if self.system == "Windows" and WMI_AVAILABLE:
            try:
                return wmi.WMI().Win32_BIOS()[0].SerialNumber.strip()
            except Exception as e:
                log.warning(f"WMI failed to get serial number: {e}")
        elif self.system == "Linux":
            return _run_command(['sudo', 'dmidecode', '-s', 'system-serial-number'])
        return "Unknown"

    def get_manufacturer(self):
        """Get the cleaned manufacturer name."""
        full_name = "Unknown"
        if self.system == "Windows" and WMI_AVAILABLE:
            try:
                full_name = wmi.WMI().Win32_ComputerSystem()[0].Manufacturer
            except Exception as e:
                log.warning(f"WMI failed to get manufacturer: {e}")
        elif self.system == "Linux":
            full_name = _run_command(['sudo', 'dmidecode', '-s', 'system-manufacturer'])
        
        return _clean_manufacturer_name(full_name)

    def get_model(self):
        if self.system == "Windows" and WMI_AVAILABLE:
            try:
                return wmi.WMI().Win32_ComputerSystem()[0].Model.strip()
            except Exception as e:
                log.warning(f"WMI failed to get model: {e}")
        elif self.system == "Linux":
            return _run_command(['sudo', 'dmidecode', '-s', 'system-product-name'])
        return "Unknown"

    def get_operating_system(self):
        if self.system == "Windows":
            return self._get_windows_edition()
        elif self.system == "Linux":
            return self._get_linux_distro()
        else:
            return platform.system()

    def get_os_version(self):
        if self.system == "Windows":
            return self._get_windows_version()
        elif self.system == "Linux":
            return self._get_linux_version()
        else:
            return platform.release()

    # --- Windows helpers ---

    def _get_windows_edition(self):
        # Try to get the marketing name (e.g., "Windows 11")
        try:
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
            pass

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
            pass

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
            pass

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

    # --- Linux helpers ---

    def _get_linux_distro(self):
        try:
            # Try lsb_release
            output = subprocess.check_output(["lsb_release", "-d"], text=True)
            match = re.search(r"Description:\s*(.*)", output)
            if match:
                return match.group(1).strip()
        except Exception:
            pass
        # Try /etc/os-release
        try:
            with open("/etc/os-release") as f:
                for line in f:
                    if line.startswith("PRETTY_NAME="):
                        return line.strip().split("=", 1)[1].strip('"')
        except Exception:
            pass
        return "Linux"

    def _get_linux_version(self):
        try:
            # Try lsb_release
            output = subprocess.check_output(["lsb_release", "-r"], text=True)
            match = re.search(r"Release:\s*(.*)", output)
            if match:
                return match.group(1).strip()
        except Exception:
            pass
        # Try /etc/os-release
        try:
            with open("/etc/os-release") as f:
                for line in f:
                    if line.startswith("VERSION_ID="):
                        return line.strip().split("=", 1)[1].strip('"')
        except Exception:
            pass
        return platform.release()

    def get_processor(self):
        full_name = "Unknown"
        if self.system == "Windows" and WMI_AVAILABLE:
            try:
                full_name = wmi.WMI().Win32_Processor()[0].Name.strip()
            except Exception as e:
                log.warning(f"WMI failed to get CPU name: {e}")
        elif self.system == "Linux":
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
                wmi_gpus = wmi.WMI().Win32_VideoController()
                for gpu in wmi_gpus:
                    if gpu.Name:
                        gpus.append(gpu.Name.strip())
            except Exception as e:
                log.warning(f"WMI failed to get GPU names: {e}")
        elif self.system == "Linux":
            output = _run_command(['lspci'])
            if output:
                for line in output.splitlines():
                    if "VGA compatible controller" in line:
                        gpu_name = line.split(":")[-1].strip()
                        gpus.append(gpu_name)
        
        if not gpus:
            return "Unknown"
        
        # Filter out virtual/fake graphics adapters
        filtered_gpus = self._filter_virtual_gpus(gpus)
        
        if not filtered_gpus:
            return "Unknown"
        
        # Prioritize dedicated graphics cards over integrated ones
        prioritized_gpu = self._prioritize_gpu(filtered_gpus)
        
        return _clean_gpu_name(prioritized_gpu)

    def _filter_virtual_gpus(self, gpu_list):
        """Filter out virtual, remote, and fake graphics adapters."""
        virtual_keywords = [
            "spacedesk",
            "parsec",
            "teamviewer",
            "vnc",
            "rdp",
            "remote",
            "virtual",
            "microsoft basic display adapter",
            "microsoft basic render driver",
            "generic pnp monitor",
            "standard vga",
            "citrix",
            "vmware",
            "virtualbox",
            "hyper-v",
            "qemu",
            "parallels"
        ]
        
        filtered = []
        for gpu in gpu_list:
            gpu_lower = gpu.lower()
            is_virtual = any(keyword in gpu_lower for keyword in virtual_keywords)
            if not is_virtual:
                filtered.append(gpu)
        
        log.debug(f"Filtered GPUs: {gpu_list} -> {filtered}")
        return filtered

    def _prioritize_gpu(self, gpu_list):
        """Prioritize dedicated graphics cards over integrated ones."""
        if len(gpu_list) == 1:
            return gpu_list[0]
        
        # Dedicated GPU keywords (higher priority)
        dedicated_keywords = [
            "geforce", "gtx", "rtx", "quadro", "tesla",  # NVIDIA
            "radeon", "rx ", "vega", "fury", "firepro",  # AMD
            "arc"  # Intel Arc (dedicated)
        ]
        
        # Integrated GPU keywords (lower priority)
        integrated_keywords = [
            "intel hd", "intel uhd", "intel iris", "intel graphics",
            "amd radeon graphics", "radeon graphics",
            "vega graphics", "ryzen", "apu"
        ]
        
        dedicated_gpus = []
        integrated_gpus = []
        other_gpus = []
        
        for gpu in gpu_list:
            gpu_lower = gpu.lower()
            
            # Check if it's a dedicated GPU
            if any(keyword in gpu_lower for keyword in dedicated_keywords):
                dedicated_gpus.append(gpu)
            # Check if it's an integrated GPU
            elif any(keyword in gpu_lower for keyword in integrated_keywords):
                integrated_gpus.append(gpu)
            else:
                other_gpus.append(gpu)
        
        # Priority: Dedicated > Other > Integrated
        if dedicated_gpus:
            selected = dedicated_gpus[0]
            log.debug(f"Selected dedicated GPU: {selected} from {gpu_list}")
            return selected
        elif other_gpus:
            selected = other_gpus[0]
            log.debug(f"Selected other GPU: {selected} from {gpu_list}")
            return selected
        else:
            selected = integrated_gpus[0] if integrated_gpus else gpu_list[0]
            log.debug(f"Selected integrated GPU: {selected} from {gpu_list}")
            return selected

    def get_ram_info(self):
        total_gb = 0
        ram_type = ""
        if self.system == "Windows" and WMI_AVAILABLE:
            try:
                c = wmi.WMI()
                total_bytes = sum(int(mem.Capacity) for mem in c.Win32_PhysicalMemory())
                total_gb = round(total_bytes / (1024**3))
                mem_types = {20: "DDR", 21: "DDR2", 24: "DDR3", 26: "DDR4", 34: "DDR5"}
                wmi_mem_type = c.Win32_PhysicalMemory()[0].MemoryType
                ram_type = mem_types.get(wmi_mem_type, "")
            except Exception as e:
                log.warning(f"WMI failed to get detailed RAM info: {e}")
        elif self.system == "Linux":
            output = _run_command(['sudo', 'dmidecode', '--type', 'memory'])
            if output:
                total_gb_calc = 0
                for line in output.splitlines():
                    if "Size:" in line and "No Module Installed" not in line:
                        parts = line.split()
                        if len(parts) > 1 and parts[1].isdigit():
                            size = int(parts[1])
                            unit = parts[2] if len(parts) > 2 else ""
                            if unit == "MB": total_gb_calc += size / 1024
                            elif unit == "GB": total_gb_calc += size
                    if "Type:" in line and not ram_type:
                        ram_type = line.split(":")[-1].strip()
                total_gb = round(total_gb_calc)

        if total_gb == 0 and psutil:
            total_gb = round(psutil.virtual_memory().total / (1024**3))
        return f"{ram_type} {total_gb} GB".strip() if total_gb else "Unknown"

    def get_storage_info(self):
        if psutil:
            try:
                mount_point = 'C:\\' if self.system == "Windows" else '/'
                usage = psutil.disk_usage(mount_point)
                actual_gib = usage.total / (1024**3)
                rounded_gb = _round_storage_gb(actual_gib)
                return f"SSD {rounded_gb} GB"
            except Exception as e:
                log.warning(f"psutil failed to get disk info: {e}")
        return "Unknown"

def main():
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    print("Attempting to gather system info. If it fails, try running as Administrator/sudo.")
    gatherer = SystemInfoGatherer()
    info = gatherer.gather_all_info()
    print("\n--- Cleaned System Information ---")
    print(json.dumps(info, indent=2))
    print("--------------------------------\n")

if __name__ == "__main__":
    main()