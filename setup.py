"""Script for generation of an .msi install package for GMCR-py.

Call from console with `python setup.py bdist_msi`
     py -3.6 setup.py bdist_msi
     py -3.6_32 setup.py bdist_msi

Built versions will appear in the `dist` top directory.
"""

# Copyright:   (c) Oskar Petersons 2013

from version import __version__
from cx_Freeze import setup, Executable
import os

os.environ['TCL_LIBRARY'] = "C:/Python35/tcl/tcl8.6"
os.environ['TK_LIBRARY'] = "C:/Python35/tcl/tk8.6"

# Set other directories to be included.
buildOptions = {'include_files':
                ['Examples/', 'icons/', 'gmcr-vis/css/', 'gmcr-vis/js/',
                 'gmcr-vis/js-lib/', 'gmcr-vis/json/', 'gmcr-vis/favicon.ico',
                 'gmcr-vis/index.html', 'gmcr.ico', 'GMCR+handout.pdf',
                 'END USER AGREEMENT.txt', 'C:/Python36/DLLs/tcl86t.dll',
                 'C:/Python36/DLLs/tk86t.dll'],
                'packages': ["tkinter", "numpy", "multiprocessing"],
                'replace_paths': ["*="],
                'silent': True}

# http://msdn.microsoft.com/en-us/library/windows/desktop/aa371847(v=vs.85).aspx
shortcut_table = [
    ("DesktopShortcut",        # Shortcut
     "DesktopFolder",          # Directory_
     "GMCR+",                  # Name
     "TARGETDIR",              # Component_
     "[TARGETDIR]GMCRplus.exe",    # Target
     None,                     # Arguments
     None,                     # Description
     None,                     # Hotkey
     None,                     # Icon
     None,                     # IconIndex
     None,                     # ShowCmd
     'TARGETDIR'               # WkDir
     ),
    ("StartMenuShortcut",      # Shortcut
     "ProgramMenuFolder",      # Directory_
     "GMCR+",                  # Name
     "TARGETDIR",              # Component_
     "[TARGETDIR]GMCRplus.exe",    # Target
     None,                     # Arguments
     None,                     # Description
     None,                     # Hotkey
     None,                     # Icon
     None,                     # IconIndex
     None,                     # ShowCmd
     'TARGETDIR'               # WkDir
     )
]

# Create the table dictionary
msi_data = {"Shortcut": shortcut_table}

# Change default MSI options and specify the use of the above defined tables
bdist_msi_options = {'data': msi_data,
                     'upgrade_code': '272b3c8b-515d-4e8d-980c-f007dac5ecdf'}

# Specify executables
executables = [
    Executable('a_Main_Window.py',
               base='Win32GUI',
               targetName='GMCRplus.exe',
               # appendScriptToExe=True,
               # appendScriptToLibrary=False,
               icon='gmcr.ico',
               shortcutName='GMCR+',
               shortcutDir='ProgramMenuFolder')
]

# Run setup
setup(name='GMCRplus',
      version=__version__,
      description='Graph Model for Conflict Resolution',
      options={'build_exe': buildOptions,
               'bdist_msi': bdist_msi_options},
      executables=executables)
