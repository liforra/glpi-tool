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

# Add PIL import for image handling
try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logging.warning("PIL/Pillow not found. Eye icons will use fallback text.")

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

# Import your existing GLPI library by its actual filename
import glpi

# Import system info gatherer
from system_info import SystemInfoGatherer

# Import the theme library if it exists
try:
    import sv_ttk
    SV_TTK_AVAILABLE = True
except ImportError:
    SV_TTK_AVAILABLE = False
    logging.warning("sv-ttk library not found. 'fluent' theme will not be available.")

class ConfigManager:
    def __init__(self, config_path=None):
        if config_path is None:
            # Always use the directory where the executable is located, not the bundle directory
            if getattr(sys, 'frozen', False):
                # Running as PyInstaller bundle
                exe_dir = os.path.dirname(sys.executable)
            else:
                # Running as script
                exe_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(exe_dir, "glpi_config.toml")
        
        self.config_path = Path(config_path)
        self.config = self.load_config()

    def load_config(self):
        default_config = self._get_default_config()
        if self.config_path.exists():
            try:
                user_config = toml.load(self.config_path)
                self._update_dict(default_config, user_config)
                logging.info(f"Loaded config from: {self.config_path}")
            except Exception as e:
                logging.error(f"Error loading or parsing config file: {e}")
        else:
            logging.info(f"Config file not found, creating new one at: {self.config_path}")
        
        self.save_config(default_config)
        return default_config

    def _get_default_config(self):
        return {
            "application": {"name": "GLPI GUI Client", "version": "6.3.0"},
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
                "purple_theme_rounded": True,
            },
            "fluent_theme_colors": {
                "mode": "dark", "primary": "#8a2be2", "background": "#201a2b",
                "foreground": "#dcd4e8", "widget_background": "#302a40",
                "widget_foreground": "#dcd4e8", "accent": "#9966cc",
            },
            "session": {"token": "", "expires": "", "username": ""},
        }

    def save_config(self, config=None):
        if config is None: 
            config = self.config
        try:
            # Ensure the directory exists
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, "w") as f: 
                toml.dump(config, f)
            logging.debug(f"Config saved to: {self.config_path}")
        except Exception as e: 
            logging.error(f"Error saving config to {self.config_path}: {e}")

    def _update_dict(self, base, update):
        for k, v in update.items():
            if isinstance(v, dict) and k in base and isinstance(base[k], dict):
                self._update_dict(base[k], v)
            else: 
                base[k] = v

    def update_session(self, token, username):
        expires = datetime.now() + timedelta(hours=self.config["authentication"]["session_timeout_hours"])
        self.config["session"] = {"token": token, "expires": expires.isoformat(), "username": username}
        self.save_config()

    def clear_session(self):
        self.config["session"] = {"token": "", "expires": "", "username": ""}
        self.save_config()

    def is_session_valid(self):
        if not self.config.get("session", {}).get("token"): 
            return False
        try:
            return datetime.now() < datetime.fromisoformat(self.config["session"]["expires"])
        except: 
            return False

class ThemeManager:
    @staticmethod
    def apply(root, config):
        theme_name = config.get("ui", {}).get("theme", "legacy").lower()
        if theme_name == "fluent" and SV_TTK_AVAILABLE:
            ThemeManager.apply_fluent_theme(root, config)
        elif theme_name == "purple":
            ThemeManager.apply_purple_theme(root, config)

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
    def apply_purple_theme(root, config):
        style = ttk.Style()
        BG = "#201a2b"
        FG = "#dcd4e8"
        WIDGET_BG = "#302a40"
        PRIMARY = "#8a2be2"
        ACCENT = "#9966cc"
        DARK_BORDER = "#1a1525"
        WIDGET_BORDER = "#403750"
        
        rounded = config.get("ui", {}).get("purple_theme_rounded", True)

        root.configure(background=BG)
        
        style.theme_use('alt')
        
        style.configure(".", 
            background=BG, 
            foreground=FG, 
            troughcolor=BG,
            bordercolor=DARK_BORDER,
            lightcolor=DARK_BORDER,
            darkcolor=DARK_BORDER,
            focuscolor=ACCENT,
            selectbackground=ACCENT,
            selectforeground=FG,
            font=("Segoe UI", 10)
        )
        
        style.configure("TFrame", 
            background=BG,
            borderwidth=0,
            relief="flat"
        )
        
        style.configure("TLabel", 
            background=BG, 
            foreground=FG
        )
        
        style.configure("TButton",
            background=WIDGET_BG,
            foreground=FG,
            borderwidth=0 if rounded else 1,
            bordercolor=WIDGET_BORDER,
            lightcolor=WIDGET_BG,
            darkcolor=WIDGET_BG,
            relief="flat",
            padding=(8, 6),
            font=("Segoe UI", 9, "bold")
        )
        style.map("TButton",
            background=[
                ("active", ACCENT),
                ("pressed", ACCENT),
                ("focus", WIDGET_BG)
            ],
            foreground=[
                ("active", "white"),
                ("pressed", "white")
            ],
            bordercolor=[
                ("active", ACCENT if not rounded else WIDGET_BG),
                ("pressed", ACCENT if not rounded else WIDGET_BG)
            ],
            lightcolor=[
                ("active", ACCENT),
                ("pressed", ACCENT)
            ],
            darkcolor=[
                ("active", ACCENT),
                ("pressed", ACCENT)
            ]
        )
        
        style.configure("TEntry",
            fieldbackground=WIDGET_BG,
            background=WIDGET_BG,
            foreground=FG,
            borderwidth=0 if rounded else 1,
            bordercolor=WIDGET_BORDER,
            lightcolor=WIDGET_BORDER,
            darkcolor=WIDGET_BORDER,
            insertcolor=FG,
            selectbackground=ACCENT,
            selectforeground="white",
            relief="solid",
            padding=(8, 6)
        )
        style.map("TEntry",
            fieldbackground=[
                ("focus", WIDGET_BG),
                ("!focus", WIDGET_BG)
            ],
            bordercolor=[
                ("focus", ACCENT),
                ("!focus", WIDGET_BORDER)
            ],
            lightcolor=[
                ("focus", ACCENT),
                ("!focus", WIDGET_BORDER)
            ],
            darkcolor=[
                ("focus", ACCENT),
                ("!focus", WIDGET_BORDER)
            ]
        )
        
        style.configure("TCheckbutton",
            background=BG,
            foreground=FG,
            focuscolor="none",
            borderwidth=0,
            relief="flat",
            indicatorsize=14,
            indicatorbackground=WIDGET_BG,
            indicatorforeground=WIDGET_BG,
            indicatorcolor=WIDGET_BG,
            indicatorrelief="flat",
            indicatorborderwidth=0,
            highlightthickness=0
        )
        style.map("TCheckbutton",
            background=[
                ("active", BG),
                ("pressed", BG),
                ("focus", BG),
                ("!focus", BG)
            ],
            foreground=[
                ("active", ACCENT),
                ("!active", FG)
            ],
            indicatorbackground=[
                ("selected", PRIMARY),
                ("pressed", ACCENT),
                ("active", WIDGET_BG),
                ("!selected", WIDGET_BG)
            ],
            indicatorcolor=[
                ("selected", "white"),
                ("pressed", "white"),
                ("!selected", WIDGET_BG)
            ],
            indicatorforeground=[
                ("selected", "white"),
                ("pressed", "white"),
                ("!selected", WIDGET_BG)
            ]
        )
        
        style.configure("TNotebook",
            background=BG,
            borderwidth=0,
            tabmargins=[0, 0, 0, 0]
        )
        style.configure("TNotebook.Tab",
            background=BG,
            foreground=FG,
            padding=[15, 8],
            borderwidth=0,
            relief="flat",
            focuscolor="none"
        )
        style.map("TNotebook.Tab",
            background=[
                ("selected", PRIMARY),
                ("!selected", BG)
            ],
            foreground=[
                ("selected", "white"),
                ("!selected", FG)
            ]
        )
        
        style.configure("TLabelframe",
            background=BG,
            borderwidth=0 if rounded else 1,
            bordercolor=WIDGET_BORDER,
            lightcolor=WIDGET_BORDER,
            darkcolor=WIDGET_BORDER,
            relief="flat",
            padding=15
        )
        style.configure("TLabelframe.Label",
            background=BG,
            foreground=ACCENT,
            font=("Segoe UI", 11, "bold")
        )
        
        style.configure("TScrollbar",
            background=WIDGET_BG,
            troughcolor=BG,
            bordercolor=WIDGET_BORDER,
            lightcolor=WIDGET_BG,
            darkcolor=WIDGET_BG,
            arrowcolor=FG
        )
        
        for widget_type in ["TCombobox", "TSpinbox", "TScale", "TProgressbar"]:
            try:
                style.configure(widget_type,
                    background=WIDGET_BG,
                    foreground=FG,
                    bordercolor=WIDGET_BORDER,
                    lightcolor=WIDGET_BORDER,
                    darkcolor=WIDGET_BORDER,
                    troughcolor=BG,
                    selectbackground=ACCENT
                )
            except:
                pass

class CustomCheckbox(tk.Frame):
    def __init__(self, parent, text, variable, **kwargs):
        super().__init__(parent, bg="#201a2b", **kwargs)
        self.variable = variable
        self.text = text
        
        self.checkbox = tk.Canvas(
            self, 
            width=16, 
            height=16, 
            bg="#201a2b", 
            highlightthickness=0,
            cursor="hand2"
        )
        self.checkbox.pack(side=tk.LEFT, padx=(0, 8))
        
        self.label = tk.Label(
            self,
            text=text,
            bg="#201a2b",
            fg="#dcd4e8",
            font=("Segoe UI", 10),
            cursor="hand2"
        )
        self.label.pack(side=tk.LEFT)
        
        self.checkbox.bind("<Button-1>", self._toggle)
        self.label.bind("<Button-1>", self._toggle)
        self.bind("<Button-1>", self._toggle)
        
        self._draw_checkbox()
        
        self.variable.trace_add("write", lambda *args: self._draw_checkbox())
    
    def _toggle(self, event=None):
        self.variable.set(not self.variable.get())
    
    def _draw_checkbox(self):
        self.checkbox.delete("all")
        
        bg_color = "#302a40"
        border_color = "#8a2be2" if self.variable.get() else "#4a445c"
        check_color = "#ffffff"
        
        self.checkbox.create_rectangle(
            1, 1, 15, 15,
            fill=bg_color,
            outline=border_color,
            width=2
        )
        
        if self.variable.get():
            self.checkbox.create_line(
                4, 8, 7, 11,
                fill=check_color,
                width=2,
                capstyle=tk.ROUND
            )
            self.checkbox.create_line(
                7, 11, 12, 4,
                fill=check_color,
                width=2,
                capstyle=tk.ROUND
            )

class CustomEyeButton(tk.Frame):
    def __init__(self, parent, command, **kwargs):
        super().__init__(parent, bg="#302a40", **kwargs)
        self.command = command
        self.visible = False
        
        self.open_icon = None
        self.closed_icon = None
        self.has_icons = False
        
        if PIL_AVAILABLE:
            try:
                open_img = Image.open(resource_path("assets/eye_open.png")).resize((24, 24), Image.Resampling.LANCZOS)
                closed_img = Image.open(resource_path("assets/eye_closed.png")).resize((24, 24), Image.Resampling.LANCZOS)
                
                self.open_icon = ImageTk.PhotoImage(self._tint_image(open_img, "#ffffff"))
                self.closed_icon = ImageTk.PhotoImage(self._tint_image(closed_img, "#ffffff"))
                self.has_icons = True
            except Exception as e:
                logging.warning(f"Could not load eye icons: {e}")
        
        if self.has_icons:
            self.widget = tk.Label(
                self,
                image=self.open_icon,
                borderwidth=0,
                background="#302a40",
                cursor="hand2"
            )
            self.widget.bind("<Button-1>", lambda e: self._on_click())
            self.widget.bind("<Enter>", self._on_hover)
            self.widget.bind("<Leave>", self._on_leave)
        else:
            self.widget = tk.Button(
                self,
                text="👁",
                command=self._on_click,
                borderwidth=0, relief="flat", background="#302a40",
                activebackground="#9966cc", foreground="#ffffff",
                activeforeground="#ffffff", font=("Segoe UI", 14),
                highlightthickness=0, cursor="hand2"
            )
        
        self.widget.pack(padx=4, pady=4)

    def _tint_image(self, image, color):
        if image.mode != 'RGBA': 
            image = image.convert('RGBA')
        color_layer = Image.new('RGBA', image.size, color)
        alpha_mask = image.split()[-1]
        tinted_image = Image.new('RGBA', image.size)
        tinted_image.paste(color_layer, (0,0), mask=alpha_mask)
        return tinted_image

    def _on_click(self):
        self.visible = not self.visible
        self._update_icon()
        if self.command:
            self.command()

    def _on_hover(self, event):
        if self.has_icons:
            self.widget.config(background="#9966cc")

    def _on_leave(self, event):
        if self.has_icons:
            self.widget.config(background="#302a40")

    def set_visible(self, visible):
        self.visible = visible
        self._update_icon()

    def _update_icon(self):
        if self.has_icons:
            image = self.closed_icon if self.visible else self.open_icon
            self.widget.config(image=image)
        else:
            text = "🙈" if self.visible else "👁"
            self.widget.config(text=text)

class LoginFrame(ttk.Frame):
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
        password_frame = ttk.Frame(frame)
        password_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.password_var = tk.StringVar()
        self.password_entry = ttk.Entry(password_frame, textvariable=self.password_var, show="*", width=40)
        self.password_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        self.password_visible = tk.BooleanVar(value=False)
        
        self.eye_button = CustomEyeButton(password_frame, self._toggle_password_visibility)
        self.eye_button.pack(side=tk.LEFT, padx=(5, 0))
        
        self.remember_var = tk.BooleanVar(value=self.controller.config_manager.config["authentication"]["remember_session"])
        self.remember_checkbox = CustomCheckbox(frame, "Remember session", self.remember_var)
        self.remember_checkbox.pack(anchor=tk.W, pady=(10, 5))
        
        self.verify_ssl_var = tk.BooleanVar(value=self.controller.config_manager.config["glpi"]["verify_ssl"])
        self.verify_ssl_checkbox = CustomCheckbox(frame, "Verify SSL", self.verify_ssl_var)
        self.verify_ssl_checkbox.pack(anchor=tk.W, pady=(0, 10))
        
        button_frame = ttk.Frame(frame)
        button_frame.pack(pady=20)
        ttk.Button(button_frame, text="Login", command=self.login).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="Exit", command=self.controller.destroy).pack(side=tk.LEFT)
        
        self.status_label = ttk.Label(frame, text="", foreground="red")
        self.status_label.pack()
        
        self.username_entry.focus()
        self.load_saved_credentials()

    def _toggle_password_visibility(self):
        if self.password_visible.get():
            self.password_entry.config(show="*")
            self.password_visible.set(False)
        else:
            self.password_entry.config(show="")
            self.password_visible.set(True)
        
        self.eye_button.set_visible(self.password_visible.get())

    def load_saved_credentials(self):
        auth_config = self.controller.config_manager.config["authentication"]
        if auth_config.get("username"): 
            self.username_var.set(auth_config["username"])
        if auth_config.get("password"): 
            self.password_var.set(auth_config["password"])

    def login(self):
        self.controller.attempt_login(
            self.username_var.get(),
            self.password_var.get(),
            self.remember_var.get(),
            self.verify_ssl_var.get(),
            self.status_label
        )

class MissingComponentsDialog(tk.Toplevel):
    def __init__(self, parent, missing_components, on_continue, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.title("Elemente fehlen")
        self.resizable(False, False)
        self.grab_set()
        self.result = None

        # Theme colors (match your purple theme)
        BG = "#201a2b"
        FG = "#dcd4e8"
        ACCENT = "#9966cc"
        DANGER = "#c0392b"
        BTN_BG = "#302a40"
        BTN_FG = FG

        self.configure(bg=BG)

        # Build message
        msg = "Leider wurden die folgenden Elemente nicht in der Datenbank gefunden:\n\n"
        for label, value in missing_components.items():
            msg += f"{label}: {value}\n"
        msg += "\nKontaktiere einen Administrator um dieses Problem zu lösen."

        # Message area
        msg_frame = tk.Frame(self, bg=BG)
        msg_frame.pack(padx=20, pady=(20, 10), fill="x")
        msg_label = tk.Label(
            msg_frame, text=msg, justify="left", anchor="w",
            bg=BG, fg=FG, font=("Segoe UI", 10), wraplength=400
        )
        msg_label.pack(fill="x")

        # Button frame
        btn_frame = tk.Frame(self, bg=BG)
        btn_frame.pack(pady=(0, 10), padx=10, fill="x")

        # Cancel button
        cancel_btn = ttk.Button(btn_frame, text="Abbrechen", command=self._cancel)
        cancel_btn.pack(side="left", padx=5)

        # Copy message button
        copy_btn = ttk.Button(btn_frame, text="Nachricht kopieren", command=lambda: self._copy_message(msg))
        copy_btn.pack(side="left", padx=5)

        # Advanced/Show More for "Continue Anyway"
        self.advanced_shown = False
        self.advanced_btn = ttk.Button(btn_frame, text="Mehr anzeigen...", command=self._show_advanced)
        self.advanced_btn.pack(side="left", padx=5)

        # Placeholder for the "Continue Anyway" button
        self.continue_btn = None
        self.on_continue = on_continue

        # Style for the danger button
        style = ttk.Style(self)
        style.configure("Danger.TButton",
                        background=DANGER, foreground="white",
                        font=("Segoe UI", 10, "bold"),
                        borderwidth=0, focusthickness=3, focuscolor=ACCENT)
        style.map("Danger.TButton",
                  background=[("active", "#e74c3c")],
                  foreground=[("active", "white")])

    def _cancel(self):
        self.result = "cancel"
        self.destroy()

    def _copy_message(self, msg):
        self.clipboard_clear()
        self.clipboard_append(msg)
        messagebox.showinfo("Kopiert", "Die Nachricht wurde in die Zwischenablage kopiert.", parent=self)

    def _show_advanced(self):
        if not self.advanced_shown:
            self.advanced_shown = True
            # Add a red "Continue Anyway" button (styled)
            self.continue_btn = ttk.Button(
                self, text="Trotzdem fortfahren", style="Danger.TButton", command=self._continue_anyway
            )
            self.continue_btn.pack(pady=(10, 15), ipadx=10, ipady=3)
            self.advanced_btn.config(state="disabled")

    def _continue_anyway(self):
        self.result = "continue"
        self.destroy()

class AddComputerFrame(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, padding=10)
        self.controller = controller
        self.username = controller.username
        self.last_added_computer_id = None
        
        self.setup_ui()
        self.load_defaults()
        if self.controller.config_manager.config.get("ui", {}).get("auto_gather_system_info", True):
            self.gather_system_info()
    
    def setup_ui(self):
        toolbar_frame = ttk.Frame(self)
        toolbar_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Button(toolbar_frame, text="🔄 Gather System Info", command=self.gather_system_info).pack(side=tk.LEFT)
        
        self.open_glpi_button = ttk.Button(
            toolbar_frame, 
            text="🌐 Open in GLPI", 
            command=self.open_computer_in_glpi
        )
        self.open_glpi_button.pack(side=tk.LEFT, padx=(10, 0))
        
        self.status_label = ttk.Label(self, text="Ready", foreground="green")
        self.status_label.pack(in_=toolbar_frame, side=tk.RIGHT)

        content_frame = ttk.Frame(self)
        content_frame.pack(fill="both", expand=True)
        content_frame.grid_columnconfigure(0, weight=1)
        content_frame.grid_columnconfigure(1, weight=1)

        basic_fields = {
            "Name": "name", "Serial Number": "serial", "Location": "location",
            "Model": "model", "Manufacturer": "manufacturer"
        }
        hardware_fields = {
            "Operating System": "os", "OS Version": "os_version", "Processor": "processor",
            "GPU": "gpu", "RAM": "ram", "Hard Drive": "hdd"
        }
        
        basic_lf = ttk.LabelFrame(content_frame, text="Basic Information")
        basic_lf.grid(row=0, column=0, padx=(0, 5), pady=5, sticky="nsew")
        self.basic_vars = self._create_fields(basic_lf, basic_fields)

        hardware_lf = ttk.LabelFrame(content_frame, text="Hardware")
        hardware_lf.grid(row=0, column=1, padx=(5, 0), pady=5, sticky="nsew")
        self.hardware_vars = self._create_fields(hardware_lf, hardware_fields)
        
        button_frame = ttk.Frame(self)
        button_frame.pack(fill=tk.X, pady=(15, 0))
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

        # Gather all data
        data = {key: var.get().strip() for key, var in {**self.basic_vars, **self.hardware_vars}.items()}
        data["tech_user"] = self.username

        # Check for missing components in GLPI - consolidated check with German labels
        missing = {}
        component_checks = {
            "GPU": ("DeviceGraphicCard", data.get("gpu")),
            "Prozessor": ("DeviceProcessor", data.get("processor")),  # German: Processor
            "Arbeitsspeicher": ("DeviceMemory", data.get("ram")),     # German: RAM/Memory
            "Festplatte": ("DeviceHardDrive", data.get("hdd")),       # German: Hard Drive
            "Modell": ("ComputerModel", data.get("model")),           # German: Model
            "Hersteller": ("Manufacturer", data.get("manufacturer")), # German: Manufacturer
        }
        
        for label, (itemtype, value) in component_checks.items():
            # Only check if a value is provided
            if value and glpi.getId(itemtype, value) in (None, 1403, 1404):
                missing[label] = value

        if missing:
            def on_continue():
                self._actually_add_computer(data)
            dialog = MissingComponentsDialog(self, missing, on_continue)
            self.wait_window(dialog)
            if dialog.result == "continue":
                self._actually_add_computer(data)
            # If cancel or closed, do nothing
            return

        # If all checks pass, proceed to add the computer
        self._actually_add_computer(data)

    def _actually_add_computer(self, data):
        try:
            computer_id = glpi.add("Computer", data)
            if computer_id:
                self.last_added_computer_id = computer_id
                logging.info(f"Computer added successfully with ID: {computer_id}")
                messagebox.showinfo("Success", f"Computer added with ID: {computer_id}\n\nYou can now click 'Open in GLPI' to view it in your browser.", parent=self)
                self.clear_form()
            else:
                messagebox.showerror("Error", "Failed to add computer. Check logs.", parent=self)
        except Exception as e:
            logging.error(f"Error adding computer: {e}")
            if "401" in str(e) or "Unauthorized" in str(e):
                messagebox.showerror("Session Expired", "Your session has expired. Please logout and login again.", parent=self)
            else:
                messagebox.showerror("Error", f"Error adding computer: {str(e)}", parent=self)

    def open_computer_in_glpi(self):
        if not self.last_added_computer_id:
            messagebox.showwarning(
                "No Computer Available", 
                "No computer ID available.\n\nPlease add a computer first, then you can open it in GLPI.", 
                parent=self
            )
            return
        
        try:
            base_url = glpi.api_url.replace("/apirest.php", "")
            computer_url = f"{base_url}/front/computer.form.php?id={self.last_added_computer_id}"
            
            logging.info(f"Opening computer {self.last_added_computer_id} in browser: {computer_url}")
            
            import webbrowser
            webbrowser.open(computer_url)
            
            self.status_label.config(text=f"Opened computer {self.last_added_computer_id} in browser", foreground="green")
            
        except Exception as e:
            logging.error(f"Failed to open computer in GLPI: {e}")
            messagebox.showerror("Error", f"Failed to open computer in GLPI:\n{str(e)}", parent=self)

    def clear_form(self):
        for var in self.basic_vars.values(): 
            var.set("")
        for var in self.hardware_vars.values(): 
            var.set("")
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
        if not query: 
            return
        
        self.results_text.config(state="normal", cursor="wait")
        self.results_text.delete("1.0", tk.END)
        self.results_text.insert(tk.END, f"Searching for '{query}'...")
        self.update_idletasks()

        threading.Thread(target=self._search_thread, args=(query,), daemon=True).start()

    def _search_thread(self, query):
        try:
            # Check session before searching
            if not hasattr(glpi, 'session_token') or not glpi.session_token:
                self.after(0, self._update_results, "Session expired. Please logout and login again.")
                return
                
            result_str = glpi.search("serial", query)
            try:
                result_json = json.loads(result_str)
                formatted_result = json.dumps(result_json, indent=2)
            except json.JSONDecodeError:
                formatted_result = result_str
            self.after(0, self._update_results, formatted_result)
        except Exception as e:
            error_msg = f"An error occurred:\n{str(e)}"
            if "401" in str(e) or "Unauthorized" in str(e):
                error_msg = "Session expired. Please logout and login again."
            self.after(0, self._update_results, error_msg)

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
        
        # Use the same directory logic for log files
        if getattr(sys, 'frozen', False):
            # Running as PyInstaller bundle
            log_dir = os.path.dirname(sys.executable)
        else:
            # Running as script
            log_dir = os.path.dirname(os.path.abspath(__file__))
        
        log_file_path = os.path.join(log_dir, cfg["file"])
        
        logging.basicConfig(
            level=level, 
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
            handlers=[
                logging.FileHandler(log_file_path), 
                logging.StreamHandler()
            ]
        )
        logging.info("Application starting up...")
        logging.info(f"Config file location: {self.config_manager.config_path}")
        logging.info(f"Log file location: {log_file_path}")

    def switch_frame(self, frame_class):
        if self.current_frame:
            self.current_frame.destroy()
        self.current_frame = frame_class(self.container, self)
        self.current_frame.pack(fill="both", expand=True)
        logging.debug(f"Switched to frame: {frame_class.__name__}")

    def check_session_and_start(self):
        if self.config_manager.config["authentication"]["remember_session"] and self.config_manager.is_session_valid():
            session = self.config_manager.config["session"]
            if glpi.restore_session(session["token"], session["username"]):
                self.on_login_success(session["token"], session["username"], False)
            else:
                self.show_login_frame()
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
        self.geometry("850x500")
        self.switch_frame(MainFrame)

    def logout(self):
        self.cleanup_session()
        self.show_login_frame()

    def cleanup_session(self):
        try: 
            glpi.killsession()
        except: 
            pass
        self.config_manager.clear_session()

    def cleanup(self):
        self.cleanup_session()

    def on_closing(self):
        self.cleanup()
        self.destroy()

if __name__ == "__main__":
    app = GLPIGUIApp()
    app.mainloop()