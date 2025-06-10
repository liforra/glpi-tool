# GLPI GUI Client

A modern, feature-rich desktop application for interacting with GLPI (IT Asset Management) systems. Built with Python and tkinter, this application provides an intuitive interface for managing computer assets, performing searches, and gathering system information.

## Features

- **Authentication Management**
  - Secure login with username/password
  - Session persistence and auto-login
  - SSL verification options
  - Session timeout handling

- **Computer Asset Management**
  - Add new computers to GLPI inventory
  - Automatic system information gathering
  - Support for hardware details (CPU, GPU, RAM, Storage)
  - Manufacturer and model detection
  - Serial number and location tracking
  - Direct browser integration - Open newly added computers in GLPI web interface

- **Search Functionality**
  - Search computers by serial number
  - JSON-formatted results display
  - Real-time search capabilities

- **System Information Gathering**
  - Cross-platform system detection (Windows/Linux)
  - Hardware component identification
  - Automatic data population
  - WMI support for Windows
  - DMI/DMIdecode support for Linux

- **Modern UI/UX**
  - Purple dark theme (default)
  - Fluent design theme (requires sv-ttk)
  - Responsive layout with tabs
  - Password visibility toggle with custom icons
  - Status indicators and progress feedback
  - Custom checkboxes and rounded design elements

- **Configuration Management**
  - TOML-based configuration
  - Persistent settings
  - Customizable themes and behavior
  - Default value management

## Requirements

### Core Dependencies
```
tkinter (usually included with Python)
toml
requests
Pillow (for custom icons)
psutil (optional, for enhanced system info)
```

### Platform-Specific Dependencies

#### Windows
```
wmi (for hardware detection)
pythoncom (for WMI initialization)
```

#### Linux
```
dmidecode (system package)
lscpu (usually available)
sudo access (for hardware detection)
```

### Optional Dependencies
```
sv-ttk (for fluent theme support)
```

## Installation

1. **Clone the repository:**
```bash
git clone https://gitea.liforra.de/liforra/glpi-tui.git
cd glpi-tui
```

2. **Install Python dependencies:**
```bash
pip install -r requirements.txt
```

3. **Install required dependencies for icons:**
```bash
pip install Pillow  # Required for eye icons
```

4. **Install optional dependencies:**
```bash
# For enhanced theming
pip install sv-ttk

# For Windows (if not already installed)
pip install wmi pywin32

# For enhanced system info
pip install psutil
```

5. **Configure the application:**
   - Update the `app_token` in `glpi_config.toml`
   - Modify other settings as needed

## Configuration

The application uses a TOML configuration file (`glpi_config.toml`) with the following sections:

### Application Settings
```toml
[application]
name = "GLPI GUI Client"
version = "6.3.0"
```

### GLPI Connection
```toml
[glpi]
app_token = "YOUR_GLPI_APP_TOKEN_HERE"
verify_ssl = true
timeout = 10
default_location = "Your Default Location"
```

### Authentication
```toml
[authentication]
remember_session = true
session_timeout_hours = 8
auto_login = false
username = ""
password = ""
```

### UI Customization
```toml
[ui]
theme = "purple"  # or "fluent"
auto_fill_defaults = true
auto_gather_system_info = true
purple_theme_rounded = true  # Enable rounded elements in purple theme
```

### Logging
```toml
[logging]
level = "WARNING"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
file = "glpi_gui.log"
```

## Usage

1. **Start the application:**
```bash
python main.py
```

2. **Login:**
   - Enter your GLPI username and password
   - Configure SSL verification as needed
   - Optionally enable session remembering

3. **Add Computers:**
   - Navigate to the "Add Computer" tab
   - Click "Gather System Info" to auto-populate fields
   - Fill in additional details as needed
   - Click "Add Computer" to submit
   - Click "Open in GLPI" to view the computer in your web browser

4. **Search:**
   - Navigate to the "Search" tab
   - Enter a serial number to search
   - View results in JSON format

## Building as Executable

### PyInstaller (Recommended)

PyInstaller bundles your Python application and all its dependencies into a single executable file, making distribution simple without requiring Python to be installed on target systems.

1. **Install PyInstaller:**
```bash
pip install pyinstaller
```

2. **Build the executable:**
```bash
# Basic one-file executable with assets
pyinstaller --onefile --windowed --add-data "glpi_config.toml;." --add-data "assets;assets" --name "GLPI-GUI-Client" main.py

# With icon (if you have one)
pyinstaller --onefile --windowed --icon=icon.ico --add-data "glpi_config.toml;." --add-data "assets;assets" --name "GLPI-GUI-Client" main.py

# For better compatibility, include hidden imports
pyinstaller --onefile --windowed --add-data "glpi_config.toml;." --add-data "assets;assets" --hidden-import=PIL --hidden-import=PIL.Image --hidden-import=PIL.ImageTk --name "GLPI-GUI-Client" main.py
```

### Alternative Build Methods

#### Nuitka (High Performance)
```bash
pip install nuitka
python -m nuitka --onefile --windows-disable-console --enable-plugin=tk-inter --include-data-dir=assets=assets --include-data-files=glpi_config.toml=glpi_config.toml main.py
```

#### Cython (Compilation)
```bash
pip install cython
# Requires additional setup.py configuration and manual asset copying
```

## Assets and Attribution

This project uses icons from [Flaticon](https://www.flaticon.com/):

- **Eye icons** (eye_open.png, eye_closed.png) created by [Freepik](https://www.freepik.com) from [Flaticon](https://www.flaticon.com/)

### License Compatibility
- The eye icons are used under Flaticon's free license with attribution
- This is compatible with the project's GNU AGPL v3.0 license
- Icons are included in the `assets/` folder and bundled with the executable


## Troubleshooting

### Common Issues

1. **"App-Token is missing or invalid"**
   - Ensure you've configured your GLPI app token in `glpi_config.toml`
   - Verify the token has appropriate permissions in GLPI

2. **SSL Certificate Errors**
   - Set `verify_ssl = false` in configuration for self-signed certificates
   - Update your system's certificate store

3. **System Info Gathering Fails**
   - On Linux: Ensure `dmidecode` is installed and you have sudo access
   - On Windows: Install WMI dependencies (`pip install wmi pywin32`)

4. **Theme Issues**
   - Install `sv-ttk` for fluent theme support
   - Fall back to "purple" theme if fluent is unavailable

5. **Missing Eye Icons**
   - Ensure `assets/eye_open.png` and `assets/eye_closed.png` exist
   - Install Pillow: `pip install Pillow`
   - Application will fall back to text icons if images are unavailable

### Build Issues

1. **Missing Dependencies in Executable**
   - Use `--hidden-import` flags in PyInstaller
   - Include data files with `--add-data`
   - Ensure assets folder is included: `--add-data "assets;assets"`

2. **Large Executable Size**
   - Use `--onedir` instead of `--onefile` for faster startup
   - Consider Nuitka for smaller, optimized builds

3. **Antivirus False Positives**
   - Code sign your executables
   - Submit to antivirus vendors for whitelisting

## AI Disclaimer

This project incorporates AI-assisted development. While approximately 90% of the GLPI library is self-written, the remaining portions and various other components have been developed with AI assistance to enhance functionality and code quality.

## License

This project is licensed under the GNU Affero General Public License v3.0. See the LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## Support

For issues and support:
1. Check the troubleshooting section above
2. Review application logs in `glpi_gui.log`
3. Open an issue on the project repository