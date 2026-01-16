#!/usr/bin/env python3
"""
StandUp Reminder - A macOS menu bar app that reminds you to stand up every 30 minutes
"""

import rumps
import json
import os
import urllib.request
import zipfile
import shutil
import subprocess
import time as time_module

VERSION = "1.1.0"
GITHUB_REPO = "ricardogo/sit-down-stand-up"
VERSION_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/version.json"
UPDATE_CHECK_INTERVAL = 24 * 60 * 60  # 24 hours in seconds


class StandUpApp(rumps.App):
    def __init__(self):
        super(StandUpApp, self).__init__("Sit Down. Stand Up", "🪑")

        # Interval presets
        self.intervals = {"1 minute": 1 * 60, "30 minutes": 30 * 60, "1 hour": 60 * 60}

        self.work_duration = 30 * 60  # 30 minutes in seconds (default)
        self.countdown_duration = 5 * 60  # 5 minutes in seconds
        self.time_remaining = self.work_duration
        self.is_countdown = False
        self.current_interval = "30 minutes"

        # Create the rumps timer (runs on main thread)
        self.timer = rumps.Timer(self.tick, 1)

        # Create interval submenu
        self.interval_menu_items = [
            rumps.MenuItem("1 minute", callback=self.change_interval),
            rumps.MenuItem("30 minutes", callback=self.change_interval),
            rumps.MenuItem("1 hour", callback=self.change_interval),
        ]

        # Set default checkmark
        self.interval_menu_items[1].state = True

        # Store reference to timer display menu item
        self.timer_menu_item = rumps.MenuItem("Time until standing up: 30:00")

        # Menu items
        self.menu = [
            self.timer_menu_item,
            rumps.separator,
            ("Remind me every...", self.interval_menu_items),
            rumps.MenuItem("Reset Reminder", callback=self.reset_timer),
            rumps.separator,
            rumps.MenuItem("Check for Updates...", callback=self.check_for_updates_menu),
        ]

        # Load saved settings
        self.load_config()

        # Set initial display
        self.update_display()

        # Set up update checker (runs every hour, but only updates if 24h passed)
        self.update_timer = rumps.Timer(self.check_for_updates_auto, 3600)
        self.update_timer.start()

        # Check for updates on startup if 24h has passed
        self.check_for_updates_auto(None)

        self.timer.start()

    @property
    def config_path(self):
        """Get the path to the config file"""
        config_dir = os.path.expanduser("~/.config/standup_reminder")
        os.makedirs(config_dir, exist_ok=True)
        return os.path.join(config_dir, "config.json")

    def load_config(self):
        """Load saved settings from config file"""
        try:
            with open(self.config_path, "r") as f:
                config = json.load(f)
                interval_name = config.get("interval", "30 minutes")
                if interval_name in self.intervals:
                    self.current_interval = interval_name
                    self.work_duration = self.intervals[interval_name]
                    self.time_remaining = self.work_duration
                    # Update menu checkmarks
                    for item in self.interval_menu_items:
                        item.state = item.title == interval_name
        except (FileNotFoundError, json.JSONDecodeError):
            pass  # Use defaults if no config exists

    def save_config(self):
        """Save current settings to config file"""
        # Load existing config to preserve other values (like last_update_check)
        try:
            with open(self.config_path, "r") as f:
                config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            config = {}

        config["interval"] = self.current_interval
        with open(self.config_path, "w") as f:
            json.dump(config, f)

    def tick(self, _):
        """Called every second to update the countdown"""
        self.time_remaining -= 1

        if self.time_remaining <= 0:
            if not self.is_countdown:
                # Work period ended, start countdown
                self.start_countdown()
            else:
                # Countdown ended, restart work period
                self.restart_work_timer()

        # Always update the display
        self.update_display()

    def start_countdown(self):
        """Start the 5-minute countdown after work period"""
        self.is_countdown = True
        self.time_remaining = self.countdown_duration
        self.title = "🧍"  # Standing person emoji

        # Show notification
        rumps.notification(
            title="Stand Up",
            subtitle="",
            message="Stand up, stretch, and move around for 5 minutes.",
            sound=False,
        )

        self.update_display()

    def restart_work_timer(self):
        """Restart the work timer after countdown"""
        self.is_countdown = False
        self.time_remaining = self.work_duration
        self.title = "🪑"  # Chair emoji

        # Show notification
        rumps.notification(
            title="Sit Down",
            subtitle="",
            message=f"{self.current_interval} timer has been reset.",
            sound=False,
        )

        self.update_display()

    def update_display(self):
        """Update the menu bar display"""
        minutes = (self.time_remaining + 59) // 60  # Round up

        if self.is_countdown:
            # Show timer in menubar during standup mode
            if self.time_remaining < 60:
                time_str = "<1m"
            else:
                time_str = f"{minutes}m"
            self.title = f"🧍 {time_str}"
            self.timer_menu_item.title = f"Stand up time: {time_str}"
        else:
            # Just show emoji during work mode
            self.title = "🪑"
            self.timer_menu_item.title = f"Time until standing up: {minutes}m"

    def reset_timer(self, sender):
        """Reset the timer to start over"""
        self.is_countdown = False
        self.time_remaining = self.work_duration
        self.title = "🪑"

        self.update_display()

    def change_interval(self, sender):
        """Change the work interval duration"""
        # Update checkmarks
        for item in self.interval_menu_items:
            item.state = False
        sender.state = True

        # Update the interval
        interval_name = sender.title
        self.current_interval = interval_name
        self.work_duration = self.intervals[interval_name]

        # Save the setting
        self.save_config()

        # Reset to new interval
        self.is_countdown = False
        self.time_remaining = self.work_duration
        self.title = "🪑"

        self.update_display()

    def check_for_updates_auto(self, _):
        """Automatically check for updates if 24 hours have passed"""
        try:
            with open(self.config_path, "r") as f:
                config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            config = {}

        last_check = config.get("last_update_check", 0)
        now = time_module.time()

        if now - last_check >= UPDATE_CHECK_INTERVAL:
            self._check_for_updates(silent=True)
            config["last_update_check"] = now
            with open(self.config_path, "w") as f:
                json.dump(config, f)

    def check_for_updates_menu(self, _):
        """Manual update check from menu"""
        self._check_for_updates(silent=False)

    def _check_for_updates(self, silent=False):
        """Check for updates and prompt user if available"""
        try:
            with urllib.request.urlopen(VERSION_URL, timeout=10) as response:
                data = json.loads(response.read().decode())

            remote_version = data.get("version", "0.0.0")
            download_url = data.get("download_url", "")
            release_notes = data.get("notes", "")

            if self._version_compare(remote_version, VERSION) > 0:
                # New version available
                result = rumps.alert(
                    title="Update Available",
                    message=f"Version {remote_version} is available (you have {VERSION}).\n\n{release_notes}\n\nWould you like to update now?",
                    ok="Update",
                    cancel="Later",
                )
                if result == 1:  # User clicked "Update"
                    self._download_and_install_update(download_url)
            elif not silent:
                rumps.alert(
                    title="No Updates",
                    message=f"You're running the latest version ({VERSION}).",
                    ok="OK",
                )
        except Exception as e:
            if not silent:
                rumps.alert(
                    title="Update Check Failed",
                    message=f"Could not check for updates: {str(e)}",
                    ok="OK",
                )

    def _version_compare(self, v1, v2):
        """Compare two version strings. Returns >0 if v1 > v2, <0 if v1 < v2, 0 if equal"""
        v1_parts = [int(x) for x in v1.split(".")]
        v2_parts = [int(x) for x in v2.split(".")]

        for i in range(max(len(v1_parts), len(v2_parts))):
            p1 = v1_parts[i] if i < len(v1_parts) else 0
            p2 = v2_parts[i] if i < len(v2_parts) else 0
            if p1 > p2:
                return 1
            elif p1 < p2:
                return -1
        return 0

    def _download_and_install_update(self, download_url):
        """Download and install the update"""
        try:
            # Get the current app path
            app_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            if not app_path.endswith(".app"):
                # Running from source, not packaged app
                rumps.alert(
                    title="Update Error",
                    message="Cannot auto-update when running from source. Please download manually.",
                    ok="OK",
                )
                return

            # Download to temp location
            temp_dir = os.path.join(os.path.expanduser("~"), ".config", "standup_reminder", "update_temp")
            os.makedirs(temp_dir, exist_ok=True)
            zip_path = os.path.join(temp_dir, "update.zip")

            rumps.notification(
                title="Downloading Update",
                subtitle="",
                message="Please wait...",
                sound=False,
            )

            urllib.request.urlretrieve(download_url, zip_path)

            # Extract the zip
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)

            # Find the .app in the extracted contents
            new_app_path = None
            for item in os.listdir(temp_dir):
                if item.endswith(".app"):
                    new_app_path = os.path.join(temp_dir, item)
                    break

            if not new_app_path:
                raise Exception("Could not find app in downloaded update")

            # Create update script that will run after app quits
            script_path = os.path.join(temp_dir, "update.sh")
            with open(script_path, "w") as f:
                f.write(f'''#!/bin/bash
sleep 2
rm -rf "{app_path}"
mv "{new_app_path}" "{app_path}"
open "{app_path}"
rm -rf "{temp_dir}"
''')
            os.chmod(script_path, 0o755)

            # Run the update script and quit
            subprocess.Popen([script_path], start_new_session=True)
            rumps.quit_application()

        except Exception as e:
            rumps.alert(
                title="Update Failed",
                message=f"Could not install update: {str(e)}",
                ok="OK",
            )


if __name__ == "__main__":
    app = StandUpApp()
    app.run()
