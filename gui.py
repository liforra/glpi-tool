import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, simpledialog
import toml
import os
import logging
import atexit
from pathlib import Path
from datetime import datetime, timedelta
import threading
import json
import sys

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

import glpi
from system_info import SystemInfoGatherer

try:
    import sv_ttk
    SV_TTK_AVAILABLE = True
except ImportError:
    SV_TTK_AVAILABLE = False
    logging.warning("sv-ttk library not found. 'fluent' theme will not be available.")

class ConfigManager:
    # This class is unchanged but included for completeness.
    def __init__(self, config_path=resource_path("glpi_config.toml")):
        self.config_path = Path(config_path)
        self.config = self.load_config()

    def load_config(self):
        default_config = self._get_default_config()
        if self.config_path.exists():
            try:
                user_config = toml.load(self.config_path)
                self._update_dict(default_config, user_config)
            except Exception as e:
                logging.error(f"Error loading or parsing config file: {e}")
        self.save_config(default_config)
        return default_config

    def _get_default_config(self):
        return {
            "application": {"name": "GLPI GUI Client", "version": "6.0.0"},
            "logging": {"level": "WARNING", "file": "glpi_gui.log"},
            "authentication": {
                "remember_session": True,
                "session_timeout_hours": 8,
                "auto_login": False,
                "username": "",
                "password": "",
            },
            "glpi": {
                "app_token": "PLEASE_REPLACE_IN_CONFIG_FILE",
                "verify_ssl": True,
                "timeout": 10,
                "default_location": "Akademie",
            },
            "ui": {
                "theme": "purple",
                "auto_fill_defaults": True,
                "auto_gather_system_info": True,
            },
            "fluent_theme_colors": {
                "mode": "dark", "primary": "#8a2be2", "background": "#201a2b",
                "foreground": "#dcd4e8", "widget_background": "#302a40",
                "widget_foreground": "#dcd4e8", "accent": "#9966cc",
            },
            "session": {"token": "", "expires": "", "username": ""},
        }

    def save_config(self, config=None):
        if config is None: config = self.config
        try:
            with open(self.config_path, "w") as f: toml.dump(config, f)
        except Exception as e: logging.error(f"Error saving config: {e}")

    def _update_dict(self, base, update):
        for k, v in update.items():
            if isinstance(v, dict) and k in base and isinstance(base[k], dict):
                self._update_dict(base[k], v)
            else: base[k] = v

    def update_session(self, token, username):
        expires = datetime.now() + timedelta(hours=self.config["authentication"]["session_timeout_hours"])
        self.config["session"] = {"token": token, "expires": expires.isoformat(), "username": username}
        self.save_config()

    def clear_session(self):
        self.config["session"] = {"token": "", "expires": "", "username": ""}
        self.save_config()

    def is_session_valid(self):
        if not self.config.get("session", {}).get("token"): return False
        try:
            return datetime.now() < datetime.fromisoformat(self.config["session"]["expires"])
        except: return False

class ThemeManager:
    @staticmethod
    def apply(root, config):
        theme_name = config.get("ui", {}).get("theme", "legacy").lower()
        if theme_name == "fluent" and SV_TTK_AVAILABLE:
            ThemeManager.apply_fluent_theme(root, config)
        elif theme_name == "purple":
            ThemeManager.apply_purple_theme(root)

    @staticmethod
    def apply_fluent_theme(root, config):
        colors = config.get("fluent_theme_colors", {})
        sv_ttk.set_theme(colors.get("mode", "dark"))
        style = ttk.Style()
        bg = colors.get("background")
        fg = colors.get("foreground")
        primary = colors.get("primary")
        
        widgets_to_style = ["TFrame", "TLabel", "TCheckbutton", "TLabelframe", "TNotebook"]
        for widget in widgets_to_style:
            style.configure(widget, background=bg, foreground=fg)
        style.configure("TLabelframe.Label", background=bg, foreground=fg)
        style.map("TNotebook.Tab", background=[("selected", primary)])
        root.configure(background=bg)

    @staticmethod
    def apply_purple_theme(root):
        style = ttk.Style()
        BG = "#201a2b"
        FG = "#dcd4e8"
        WIDGET_BG = "#302a40"
        PRIMARY = "#8a2be2" # BlueViolet
        ACCENT = "#9966cc" # Amethyst
        BORDER = "#4a445c"

        root.configure(background=BG)
        style.theme_use('clam')
        
        style.configure(".", background=BG, foreground=FG, borderwidth=0, font=("Segoe UI", 10))
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=FG)
        
        style.configure("TButton", background=WIDGET_BG, foreground=FG, bordercolor=BORDER, lightcolor=WIDGET_BG, darkcolor=WIDGET_BG, padding=8, font=("Segoe UI", 9, "bold"))
        style.map("TButton", background=[("active", ACCENT), ("pressed", ACCENT)])
        
        style.configure("TEntry", fieldbackground=WIDGET_BG, foreground=FG, bordercolor=BORDER, insertcolor=FG)
        style.configure("ScrolledText", background=WIDGET_BG, foreground=FG, bordercolor=BORDER, insertbackground=FG)
        
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=BG, foreground=FG, padding=[10, 5], borderwidth=0)
        style.map("TNotebook.Tab", background=[("selected", PRIMARY)], foreground=[("selected", "white")])
        
        style.configure("TLabelframe", background=BG, bordercolor=BORDER, padding=10)
        style.configure("TLabelframe.Label", background=BG, foreground=ACCENT, font=("Segoe UI", 11, "bold"))

class LoginFrame(ttk.Frame):
    # This class is unchanged but included for completeness.
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        
        frame = ttk.Frame(self, padding="20")
        frame.pack(expand=True)
        
        ttk.Label(frame, text="GLPI Authentication", font=("Segoe UI", 14, "bold")).pack(pady=(0, 20))
        ttk.Label(frame, text="Username:").pack(anchor=tk.W)
        self.username_var = tk.StringVar()
        self.username_entry = ttk.Entry(frame, textvariable=self.username_var, width=40)
        self.username_entry.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(frame, text="Password:").pack(anchor=tk.W)
        self.password_var = tk.StringVar()
        self.password_entry = ttk.Entry(frame, textvariable=self.password_var, show="*", width=40)
        self.password_entry.pack(fill=tk.X, pady=(0, 10))
        
        self.remember_var = tk.BooleanVar(value=self.controller.config_manager.config["authentication"]["remember_session"])
        ttk.Checkbutton(frame, text="Remember session", variable=self.remember_var).pack(anchor=tk.W)
        
        self.verify_ssl_var = tk.BooleanVar(value=self.controller.config_manager.config["glpi"]["verify_ssl"])
        ttk.Checkbutton(frame, text="Verify SSL", variable=self.verify_ssl_var).pack(anchor=tk.W)
        
        button_frame = ttk.Frame(frame)
        button_frame.pack(pady=20)
        ttk.Button(button_frame, text="Login", command=self.login).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="Exit", command=self.controller.destroy).pack(side=tk.LEFT)
        
        self.status_label = ttk.Label(frame, text="", foreground="red")
        self.status_label.pack()
        
        self.username_entry.focus()
        self.load_saved_credentials()

    def load_saved_credentials(self):
        auth_config = self.controller.config_manager.config["authentication"]
        if auth_config.get("username"): self.username_var.set(auth_config["username"])
        if auth_config.get("password"): self.password_var.set(auth_config["password"])

    def login(self):
        self.controller.attempt_login(
            self.username_var.get(),
            self.password_var.get(),
            self.remember_var.get(),
            self.verify_ssl_var.get(),
            self.status_label
        )

class AddComputerFrame(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, padding=10)
        self.controller = controller
        self.username = controller.username
        
        self.setup_ui()
        self.load_defaults()
        if self.controller.config_manager.config.get("ui", {}).get("auto_gather_system_info", True):
            self.gather_system_info()
    
    def setup_ui(self):
        canvas = tk.Canvas(self, highlightthickness=0, background=self.winfo_toplevel().cget('bg'))
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        content_frame = ttk.Frame(scrollable_frame, padding=10)
        content_frame.pack(fill="x", expand=True)

        toolbar_frame = ttk.Frame(content_frame)
        toolbar_frame.pack(fill=tk.X, pady=(0, 20))
        ttk.Button(toolbar_frame, text="🔄 Gather System Info", command=self.gather_system_info).pack(side=tk.LEFT)
        self.status_label = ttk.Label(toolbar_frame, text="Ready", foreground="green")
        self.status_label.pack(side=tk.RIGHT)
        
        basic_fields = {
            "Name": "name", "Serial Number": "serial", "Location": "location",
            "Model": "model", "Manufacturer": "manufacturer"
        }
        hardware_fields = {
            "Operating System": "os", "OS Version": "os_version", "Processor": "processor",
            "GPU": "gpu", "RAM": "ram", "Hard Drive": "hdd"
        }
        
        basic_lf = ttk.LabelFrame(content_frame, text="Basic Information")
        basic_lf.pack(fill="x", expand=True, pady=(0, 15))
        self.basic_vars = self._create_fields(basic_lf, basic_fields)

        hardware_lf = ttk.LabelFrame(content_frame, text="Hardware")
        hardware_lf.pack(fill="x", expand=True)
        self.hardware_vars = self._create_fields(hardware_lf, hardware_fields)
        
        button_frame = ttk.Frame(content_frame)
        button_frame.pack(fill=tk.X, pady=(20, 0))
        ttk.Button(button_frame, text="Add Computer", command=self.add_computer).pack(side=tk.RIGHT, padx=(10, 0))
        ttk.Button(button_frame, text="Clear Form", command=self.clear_form).pack(side=tk.RIGHT)

    def _create_fields(self, parent, fields):
        variables = {}
        for i, (label_text, data_key) in enumerate(fields.items()):
            ttk.Label(parent, text=f"{label_text}:").grid(row=i, column=0, sticky=tk.W, pady=5, padx=5)
            var = tk.StringVar()
            variables[data_key] = var
            ttk.Entry(parent, textvariable=var).grid(row=i, column=1, pady=5, padx=5, sticky=tk.EW)
        parent.grid_columnconfigure(1, weight=1)
        return variables

    def load_defaults(self):
        if self.controller.config_manager.config.get("ui", {}).get("auto_fill_defaults", True):
            self.basic_vars["location"].set(self.controller.config_manager.config.get("glpi", {}).get("default_location", ""))
    
    def gather_system_info(self):
        self.status_label.config(text="Gathering system info...", foreground="orange")
        self.config(cursor="wait")
        threading.Thread(target=self._gather_system_info_thread, daemon=True).start()
    
    def _gather_system_info_thread(self):
        try:
            info = SystemInfoGatherer().gather_all_info()
            self.after(0, self._update_fields_with_system_info, info)
        except Exception as e:
            self.after(0, self._handle_gather_error, str(e))
    
    def _update_fields_with_system_info(self, info):
        all_vars = {**self.basic_vars, **self.hardware_vars}
        for key, var in all_vars.items():
            if key in info and info.get(key) and info.get(key) != "Unknown":
                var.set(info[key])
        self.status_label.config(text="System info gathered", foreground="green")
        self.config(cursor="")
    
    def _handle_gather_error(self, error):
        self.status_label.config(text="Error gathering info", foreground="red")
        self.config(cursor="")
        logging.error(f"System info gathering error: {error}")
    
    def add_computer(self):
        if not self.basic_vars["serial"].get().strip():
            messagebox.showerror("Error", "Serial Number is a required field.", parent=self)
            return
        data = {key: var.get().strip() for key, var in {**self.basic_vars, **self.hardware_vars}.items()}
        data["tech_user"] = self.username
        try:
            computer_id = glpi.add("Computer", data)
            if computer_id:
                messagebox.showinfo("Success", f"Computer added with ID: {computer_id}", parent=self)
                self.clear_form()
            else:
                messagebox.showerror("Error", "Failed to add computer. Check logs.", parent=self)
        except Exception as e:
            messagebox.showerror("Error", f"Error adding computer: {str(e)}", parent=self)

    def clear_form(self):
        for var in self.basic_vars.values(): var.set("")
        for var in self.hardware_vars.values(): var.set("")
        self.load_defaults()

class SearchFrame(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, padding=10)
        self.controller = controller
        self.setup_ui()

    def setup_ui(self):
        search_bar_frame = ttk.Frame(self)
        search_bar_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(search_bar_frame, text="Search Serial:").pack(side=tk.LEFT, padx=(0, 5))
        self.query_var = tk.StringVar()
        query_entry = ttk.Entry(search_bar_frame, textvariable=self.query_var, width=40)
        query_entry.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        query_entry.bind("<Return>", self._perform_search)
        
        search_button = ttk.Button(search_bar_frame, text="Search", command=self._perform_search)
        search_button.pack(side=tk.LEFT, padx=5)

        self.results_text = scrolledtext.ScrolledText(self, wrap=tk.WORD, state="disabled")
        self.results_text.pack(fill=tk.BOTH, expand=True)

    def _perform_search(self, event=None):
        query = self.query_var.get().strip()
        if not query: return
        
        self.results_text.config(state="normal", cursor="wait")
        self.results_text.delete("1.0", tk.END)
        self.results_text.insert(tk.END, f"Searching for '{query}'...")
        self.update_idletasks()

        threading.Thread(target=self._search_thread, args=(query,), daemon=True).start()

    def _search_thread(self, query):
        try:
            result_str = glpi.search("serial", query)
            try:
                result_json = json.loads(result_str)
                formatted_result = json.dumps(result_json, indent=2)
            except json.JSONDecodeError:
                formatted_result = result_str
            self.after(0, self._update_results, formatted_result)
        except Exception as e:
            self.after(0, self._update_results, f"An error occurred:\n{str(e)}")

    def _update_results(self, result_text):
        self.results_text.delete("1.0", tk.END)
        self.results_text.insert(tk.END, result_text)
        self.results_text.config(state="disabled", cursor="")

class MainFrame(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        menubar = tk.Menu(self.controller)
        self.controller.config(menu=menubar)
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Logout", command=self.controller.logout)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.controller.destroy)

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=5, pady=5)

        add_computer_tab = AddComputerFrame(notebook, controller)
        search_tab = SearchFrame(notebook, controller)

        notebook.add(add_computer_tab, text="Add Computer")
        notebook.add(search_tab, text="Search")

class GLPIGUIApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.config_manager = ConfigManager()
        self.username = None
        self.current_frame = None

        self.setup_logging()
        
        try:
            app_token = self.config_manager.config["glpi"]["app_token"]
            glpi.init_glpi(app_token)
        except (ValueError, KeyError) as e:
            logging.critical(f"CRITICAL ERROR: {e}")
            messagebox.showerror("Configuration Error", str(e))
            self.after(100, self.destroy)
            return

        ThemeManager.apply(self, self.config_manager.config)
        
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        atexit.register(self.cleanup)

        self.container = ttk.Frame(self)
        self.container.pack(fill="both", expand=True)

        self.check_session_and_start()

    def setup_logging(self):
        cfg = self.config_manager.config["logging"]
        level = getattr(logging, cfg["level"].upper(), logging.WARNING)
        logging.basicConfig(level=level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', handlers=[logging.FileHandler(resource_path(cfg["file"])), logging.StreamHandler()])
        logging.info("Application starting up...")

    def switch_frame(self, frame_class):
        if self.current_frame:
            self.current_frame.destroy()
        self.current_frame = frame_class(self.container, self)
        self.current_frame.pack(fill="both", expand=True)
        logging.debug(f"Switched to frame: {frame_class.__name__}")

    def check_session_and_start(self):
        if self.config_manager.config["authentication"]["remember_session"] and self.config_manager.is_session_valid():
            session = self.config_manager.config["session"]
            self.on_login_success(session["token"], session["username"], False)
        else:
            self.show_login_frame()

    def show_login_frame(self):
        self.title("GLPI Login")
        self.geometry("400x350")
        self.config(menu=tk.Menu(self))
        self.switch_frame(LoginFrame)

    def attempt_login(self, username, password, remember, verify_ssl, status_label):
        if not username or not password:
            status_label.config(text="Username and password are required")
            return
        
        self.config(cursor="wait")
        status_label.config(text="Authenticating...")
        
        def _authenticate():
            try:
                result = glpi.auth(username, password, verify_ssl, remember)
                self.after(0, self._handle_auth_result, result, username, remember, status_label)
            except Exception as e:
                self.after(0, self._handle_auth_error, str(e), status_label)

        threading.Thread(target=_authenticate, daemon=True).start()

    def _handle_auth_result(self, result, username, remember, status_label):
        self.config(cursor="")
        if isinstance(result, list) and len(result) >= 1:
            self.on_login_success(result[0], username, remember)
        else:
            messages = {1401: "Invalid username or password", 1400: "Authentication failed"}
            status_label.config(text=messages.get(result, f"Failed (Code: {result})"))

    def _handle_auth_error(self, error, status_label):
        self.config(cursor="")
        status_label.config(text=f"Error: {error}")

    def on_login_success(self, token, username, remember):
        self.username = username
        if remember:
            self.config_manager.update_session(token, username)
        
        self.title(self.config_manager.config["application"]["name"])
        self.geometry("800x600")
        self.switch_frame(MainFrame)

    def logout(self):
        self.cleanup_session()
        self.show_login_frame()

    def cleanup_session(self):
        if hasattr(glpi, 'session_token') and glpi.session_token:
            try: glpi.killsession()
            except: pass
        glpi.session_token = None
        if hasattr(glpi, 'username'): glpi.username = None
        self.config_manager.clear_session()

    def cleanup(self):
        self.cleanup_session()

    def on_closing(self):
        self.cleanup()
        self.destroy()

if __name__ == "__main__":
    app = GLPIGUIApp()
    app.mainloop()