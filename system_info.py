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
    """
    Rounds the OS-reported Gibibyte (GiB) size to the nearest
    common marketing Gigabyte (GB) size.
    """
    if not gib:
        return 0
    
    # This factor converts from GiB (2^30) to an estimated marketing GB (10^9)
    # A 256 GB drive is ~238.4 GiB. 238.4 * 1.0737... ≈ 256.
    estimated_marketing_gb = gib * (1024**3 / 1000**3)
    
    sizes = [120, 128, 240, 250, 256, 480, 500, 512, 960, 1000, 1024, 2048, 4096]
    
    # Find the smallest marketing size that is >= our estimated size
    for size in sizes:
        if size >= estimated_marketing_gb:
            return size
            
    # If it's larger than any known size, return the rounded actual size
    return round(gib)


def _clean_processor_name(name):
    """Extracts the core model number from a full CPU brand string."""
    if not name:
        return "Unknown"
    match = re.search(
        r'(i[3579]-\w+|Ryzen\s\d\s\w+|Xeon\s\w-\w+|Pentium\s\w+|Celeron\s\w+)',
        name,
        re.IGNORECASE
    )
    if match:
        return match.group(1).strip()
    name = re.sub(r'Intel\(R\)\sCore\(TM\)\s', '', name)
    name = re.sub(r'\sCPU\s@\s.*', '', name)
    return name.strip()

def _clean_gpu_name(name):
    """Extracts the core model name from a full GPU brand string."""
    if not name:
        return "Unknown"
    cleaned_name = re.sub(r'\((R|TM)\)', '', name).strip()
    prefixes = ["Intel", "NVIDIA", "AMD"]
    for prefix in prefixes:
        if cleaned_name.lower().startswith(prefix.lower()):
            cleaned_name = cleaned_name[len(prefix):].strip()
            break
    return cleaned_name if cleaned_name else name

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
        if self.system == "Windows" and WMI_AVAILABLE:
            try:
                return wmi.WMI().Win32_ComputerSystem()[0].Manufacturer.strip()
            except Exception as e:
                log.warning(f"WMI failed to get manufacturer: {e}")
        elif self.system == "Linux":
            return _run_command(['sudo', 'dmidecode', '-s', 'system-manufacturer'])
        return "Unknown"

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
        return platform.system()

    def get_os_version(self):
        if self.system == "Windows":
            return platform.release()
        return platform.release()

    def get_processor(self):
        """Get the cleaned processor brand name."""
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
        """Get the cleaned primary GPU name."""
        full_name = "Unknown"
        if self.system == "Windows" and WMI_AVAILABLE:
            try:
                gpus = [gpu.Name for gpu in wmi.WMI().Win32_VideoController() if gpu.Name]
                real_gpus = [gpu for gpu in gpus if "Microsoft Basic Display Adapter" not in gpu]
                full_name = ", ".join(real_gpus) if real_gpus else ", ".join(gpus)
            except Exception as e:
                log.warning(f"WMI failed to get GPU name: {e}")
        elif self.system == "Linux":
            output = _run_command(['lspci'])
            if output:
                for line in output.splitlines():
                    if "VGA compatible controller" in line:
                        full_name = line.split(":")[-1].strip()
                        break
        return _clean_gpu_name(full_name)

    def get_ram_info(self):
        """Get total RAM size and type (e.g., DDR4 16 GB)."""
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
        """Get primary storage size, rounded to marketing value."""
        if psutil:
            try:
                mount_point = 'C:\\' if self.system == "Windows" else '/'
                usage = psutil.disk_usage(mount_point)
                # Get size in GiB
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