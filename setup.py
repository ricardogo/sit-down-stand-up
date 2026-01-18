"""
Setup script for creating a standalone macOS app bundle using py2app
"""
from setuptools import setup

APP = ['standup_reminder.py']
DATA_FILES = ['icon.png']
OPTIONS = {
    'argv_emulation': False,
    'iconfile': 'icon.icns',
    'plist': {
        'CFBundleName': 'Sit Down. Stand Up',
        'CFBundleDisplayName': 'Sit Down. Stand Up',
        'CFBundleGetInfoString': "Reminds you to stand up at regular intervals",
        'CFBundleIdentifier': "com.sitdown.standup",
        'CFBundleVersion': "1.7.0",
        'CFBundleShortVersionString': "1.7.0",
        'NSHumanReadableCopyright': "Copyright © 2026",
        'LSUIElement': True,  # Set to False to show in Dock, True to hide
    },
    'packages': ['rumps'],
}

setup(
    name='Sit Down. Stand Up',
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
