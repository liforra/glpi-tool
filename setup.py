from setuptools import setup, find_packages

setup(
    name="GLPI GUI Client",
    version="0.0.1", # This will be replaced by the workflow
    packages=find_packages(), # This will find gui, glpi, system_info if they are in a package structure
    py_modules=["gui", "glpi", "system_info"], # Explicitly list individual .py files at the root
    install_requires=[
        "toml",
        "requests",
        "psutil",
        "Pillow",
        "wmi; sys_platform == 'win32'",
        "pywin32; sys_platform == 'win32'",
        "sv-ttk"
    ],
)