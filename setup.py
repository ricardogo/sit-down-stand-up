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
        'CFBundleName': 'Get up, Stand up',
        'CFBundleDisplayName': 'Get up, Stand up',
        'CFBundleGetInfoString': "Reminds you to stand up at regular intervals",
        'CFBundleIdentifier': "com.sitdown.standup",
        'CFBundleVersion': "2.1.0",
        'CFBundleShortVersionString': "2.1.0",
        'NSHumanReadableCopyright': "Copyright © 2026",
        'LSUIElement': True,  # Set to False to show in Dock, True to hide
    },
    'packages': ['rumps'],
}

setup(
    name='Get up, Stand up',
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
