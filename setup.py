from setuptools import setup, Extension
from Cython.Build import cythonize
import sys

# Wir definieren die Python-Dateien, die wir kompilieren wollen.
extensions = [
    Extension(
        "gui",          # <--- HIER GEÄNDERT
        ["gui.py"],     # <--- HIER GEÄNDERT
    ),
    Extension(
        "glpi",
        ["glpi.py"],
    ),
    Extension(
        "system_info",
        ["system_info.py"],
    ),
]

# Zusätzliche Compiler-Argumente
compiler_args = []
if sys.platform == "win32":
    compiler_args.append("/WX-")

setup(
    name="GLPI GUI Client",
    ext_modules=cythonize(
        extensions,
        compiler_directives={"language_level": "3"},
        annotate=True,
    ),
    options={'build_ext': {'compiler_args': compiler_args}},
)