#!/usr/bin/env python3
"""
StandUp Reminder - A macOS menu bar app that reminds you to stand up every 30 minutes
"""

import rumps
import json
import os


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
        ]

        # Load saved settings
        self.load_config()

        # Set initial display
        self.update_display()

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
        config = {"interval": self.current_interval}
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
            self.timer_menu_item.title = f"Stand up time: {minutes}m"
        else:
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


if __name__ == "__main__":
    app = StandUpApp()
    app.run()
