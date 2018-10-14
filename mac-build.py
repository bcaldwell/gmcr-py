"""
Usage:
    python mac-build.py py2app
"""

from setuptools import setup

APP = ['a_Main_Window.py']
DATA_FILES = ['icons', 'test_data', 'Examples']
APP_NAME = "GMCR+"
OPTIONS = {
  'argv_emulation': True,
  'iconfile': 'gmcr.ico',
      'plist': {
        'CFBundleName': APP_NAME,
        'CFBundleDisplayName': APP_NAME,
        'CFBundleGetInfoString': "Graph modeling using GMCR+",
        'CFBundleIdentifier': "com.bcaldwell.osx.gmcr",
        'CFBundleVersion': "0.4.0",
        'CFBundleShortVersionString': "0.4.0",
        'NSHumanReadableCopyright': u"Copyright © 2018"
    }
}

setup(
    name=APP_NAME,
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
