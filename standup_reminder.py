#!/usr/bin/env python3
"""
StandUp Reminder - A macOS menu bar app that reminds you to stand up every 30 minutes
"""

import rumps
import json
import os
import random
import urllib.request
import zipfile
import shutil
import subprocess
import time as time_module
import uuid
import threading
from posthog import Posthog
from AppKit import (
    NSAlternateKeyMask, NSWorkspace, NSWorkspaceScreensDidSleepNotification,
    NSWorkspaceScreensDidWakeNotification, NSView, NSTextField, NSButton,
    NSFont, NSColor, NSMakeRect, NSTextAlignmentCenter, NSBezelStyleRounded,
    NSLineBreakByWordWrapping, NSPopover, NSViewController, NSPopoverBehaviorTransient,
    NSMinYEdge, NSImageView, NSImage, NSImageScaleProportionallyUpOrDown
)
from Foundation import NSNotificationCenter
import objc
import UserNotifications

VERSION = "1.7.2"
SNOOZE_DURATION = 5 * 60  # 5 minutes in seconds

# PostHog analytics
posthog = Posthog(
    project_api_key='phc_waWKd8uTCu5RJa0ElmxORrfRdbufIQtFSsbz55JL5GX',
    host='https://eu.i.posthog.com'
)


class NotificationDelegate(objc.lookUpClass('NSObject')):
    """Delegate to handle notification interactions using UNUserNotificationCenter"""
    app = None  # Will be set to StandUpApp instance

    # UNUserNotificationCenterDelegate methods
    # Signature: v@:@@@ = void, self, _cmd, center, response, completionHandler(block)
    @objc.typedSelector(b'v@:@@@?')
    def userNotificationCenter_didReceiveNotificationResponse_withCompletionHandler_(self, center, response, handler):
        """Called when user interacts with notification"""
        action = response.actionIdentifier()
        user_info = response.notification().request().content().userInfo()
        data = user_info.get("data") if user_info else None

        # Check if action button was clicked (not dismiss)
        if action == "snooze" and self.app:
            self.app.snooze()
        elif action == "moved" and self.app:
            self.app.record_completed()
        elif action == UserNotifications.UNNotificationDefaultActionIdentifier:
            # User clicked on notification body
            if data == "standup" and self.app:
                self.app.snooze()
            elif data == "sitdown" and self.app:
                self.app.record_completed()
        elif action == UserNotifications.UNNotificationDismissActionIdentifier:
            # User dismissed the notification
            if data == "sitdown" and self.app:
                self.app.clear_streak()

        # Must call completion handler
        handler()

    @objc.typedSelector(b'v@:@@@?')
    def userNotificationCenter_willPresentNotification_withCompletionHandler_(self, center, notification, handler):
        """Always show notifications even when app is active"""
        handler(UserNotifications.UNNotificationPresentationOptionBanner | UserNotifications.UNNotificationPresentationOptionSound)


class PopoverDelegate(objc.lookUpClass('NSObject')):
    """Helper class to handle popover button clicks"""

    def initWithPopover_leftCallback_rightCallback_(self, popover, left_callback, right_callback):
        self = objc.super(PopoverDelegate, self).init()
        if self is None:
            return None
        self.popover = popover
        self.left_callback = left_callback
        self.right_callback = right_callback
        return self

    @objc.typedSelector(b'v@:@')
    def leftButtonClicked_(self, sender):
        self.popover.close()
        if self.left_callback:
            self.left_callback()

    @objc.typedSelector(b'v@:@')
    def rightButtonClicked_(self, sender):
        self.popover.close()
        if self.right_callback:
            self.right_callback()

def get_icon_path():
    """Get the path to the app icon"""
    # When running as app bundle, icon is in Resources
    bundle_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if bundle_path.endswith('.app/Contents'):
        return os.path.join(bundle_path, 'Resources', 'icon.icns')
    # When running from source
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'icon.png')

ICON_PATH = get_icon_path()
STANDUP_MESSAGES = [
    "Stand up, stretch, and move around for 5 minutes.",
    "Do 20 jumping jacks!",
    "Walk around the block.",
    "Stretch for 5 minutes.",
    "Walk your dog.",
    "Climb some stairs (if you have 'em).",
    "Can't move right now? Stand up for a while.",
]
GITHUB_REPO = "ricardogo/sit-down-stand-up"
VERSION_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/version.json"
UPDATE_CHECK_INTERVAL = 24 * 60 * 60  # 24 hours in seconds


class StandUpApp(rumps.App):
    def __init__(self):
        super(StandUpApp, self).__init__("Sit Down. Stand Up", "🧑‍💻")

        # Interval presets
        self.intervals = {"1 minute": 1 * 60, "30 minutes": 30 * 60, "60 minutes": 60 * 60}

        self.work_duration = 30 * 60  # 30 minutes in seconds (default)
        self.countdown_duration = 5 * 60  # 5 minutes in seconds
        self.time_remaining = self.work_duration
        self.is_countdown = False
        self.is_snooze = False  # Track if we're in snooze mode
        self.current_interval = "30 minutes"

        # Create the rumps timer (runs on main thread)
        self.timer = rumps.Timer(self.tick, 1)

        # Create interval submenu
        # Hidden placeholder that "1 minute" replaces when Option is held
        self.placeholder_item = rumps.MenuItem("")  # Empty/invisible item
        self.one_minute_item = rumps.MenuItem("1 minute", callback=self.change_interval)
        self.interval_menu_items = [
            self.placeholder_item,  # Invisible placeholder
            self.one_minute_item,   # Alternate - replaces placeholder when Option held
            rumps.MenuItem("30 minutes", callback=self.change_interval),
            rumps.MenuItem("60 minutes", callback=self.change_interval),
        ]

        # Set default checkmark on 30 minutes (index 2 now)
        self.interval_menu_items[2].state = True

        # Make placeholder hidden (no callback = grayed/hidden effect)
        self.placeholder_item._menuitem.setHidden_(True)

        # Make "1 minute" an alternate to the placeholder (appears when Option held)
        self.one_minute_item._menuitem.setAlternate_(True)
        self.one_minute_item._menuitem.setKeyEquivalentModifierMask_(NSAlternateKeyMask)

        # Store reference to timer display menu item
        self.timer_menu_item = rumps.MenuItem("Time until standing up: 30:00")

        # Snooze menu item (only visible during stand up mode)
        self.snooze_menu_item = rumps.MenuItem("Snooze", callback=self.snooze_clicked)
        self.snooze_menu_item._menuitem.setHidden_(True)  # Initially hidden

        # Stop/Restart menu item
        self.is_paused = False
        self.pause_menu_item = rumps.MenuItem("Stop", callback=self.toggle_pause)

        # Dev menu (hidden, shown with Option key)
        self.dev_menu_placeholder = rumps.MenuItem("")
        self.dev_menu_items = [
            rumps.MenuItem("Trigger Stand up", callback=self.dev_trigger_standup),
            rumps.MenuItem("Trigger Sit down", callback=self.dev_trigger_sitdown),
            rumps.MenuItem("Notification Settings...", callback=self.dev_notification_settings),
            rumps.separator,
            rumps.MenuItem("Record Stood Up", callback=lambda _: self.record_completed()),
            rumps.MenuItem("Record Snoozed", callback=lambda _: self.record_snoozed()),
            rumps.separator,
            rumps.MenuItem("Fake Old Version (1.0.0)", callback=self.dev_fake_old_version),
        ]
        self.dev_menu = ("Dev", self.dev_menu_items)

        # Stats menu - use lambda to keep items enabled but do nothing
        noop = lambda _: None
        self.stats_today_header = rumps.MenuItem("Today", callback=noop)
        self.stats_today_stoodup = rumps.MenuItem("  Stood up: 0", callback=noop)
        self.stats_today_snoozed = rumps.MenuItem("  Snoozed: 0", callback=noop)
        self.stats_today_best = rumps.MenuItem("  Best streak: 0", callback=noop)
        self.stats_alltime_header = rumps.MenuItem("All-time", callback=noop)
        self.stats_alltime_stoodup = rumps.MenuItem("  Stood up: 0", callback=noop)
        self.stats_alltime_snoozed = rumps.MenuItem("  Snoozed: 0", callback=noop)
        self.stats_alltime_best = rumps.MenuItem("  Best streak: 0", callback=noop)
        self.stats_streak = rumps.MenuItem("Streak: 0 🔥", callback=noop)
        self.stats_menu_items = [
            self.stats_streak,
            rumps.separator,
            self.stats_today_header,
            self.stats_today_stoodup,
            self.stats_today_snoozed,
            self.stats_today_best,
            rumps.separator,
            self.stats_alltime_header,
            self.stats_alltime_stoodup,
            self.stats_alltime_snoozed,
            self.stats_alltime_best,
        ]
        self.stats_menu = ("Stats", self.stats_menu_items)

        # Track if we're waiting for user to respond to sit down notification
        self.pending_sitdown_response = False

        # Menu items
        self.menu = [
            self.timer_menu_item,
            self.snooze_menu_item,
            self.pause_menu_item,
            rumps.separator,
            ("Remind me every...", self.interval_menu_items),
            rumps.separator,
            self.stats_menu,
            rumps.separator,
            self.dev_menu_placeholder,
            self.dev_menu,
            rumps.MenuItem("Check for Updates...", callback=self.check_for_updates_menu),
        ]

        # Hide dev menu placeholder and make dev menu alternate (shown with Option)
        self.dev_menu_placeholder._menuitem.setHidden_(True)
        dev_menu_item = self.menu["Dev"]
        dev_menu_item._menuitem.setAlternate_(True)
        dev_menu_item._menuitem.setKeyEquivalentModifierMask_(NSAlternateKeyMask)

        # Load saved settings
        self.load_config()

        # Set initial display
        self.update_display()

        # Set up update checker (runs every hour, but only updates if 24h passed)
        self.update_timer = rumps.Timer(self.check_for_updates_auto, 3600)
        self.update_timer.start()

        # Check for updates on startup if 24h has passed
        self.check_for_updates_auto(None)

        # Register for screen sleep/wake notifications
        workspace = NSWorkspace.sharedWorkspace()
        notification_center = workspace.notificationCenter()
        notification_center.addObserver_selector_name_object_(
            self, 'screenDidSleep:', NSWorkspaceScreensDidSleepNotification, None
        )
        notification_center.addObserver_selector_name_object_(
            self, 'screenDidWake:', NSWorkspaceScreensDidWakeNotification, None
        )

        # Set up UNUserNotificationCenter
        self.notification_delegate = NotificationDelegate.alloc().init()
        self.notification_delegate.app = self
        center = UserNotifications.UNUserNotificationCenter.currentNotificationCenter()
        center.setDelegate_(self.notification_delegate)

        # Request notification permissions
        center.requestAuthorizationWithOptions_completionHandler_(
            UserNotifications.UNAuthorizationOptionAlert | UserNotifications.UNAuthorizationOptionSound,
            lambda granted, error: None
        )

        # Set up notification categories with actions
        snooze_action = UserNotifications.UNNotificationAction.actionWithIdentifier_title_options_(
            "snooze", "Snooze", 0
        )
        standup_category = UserNotifications.UNNotificationCategory.categoryWithIdentifier_actions_intentIdentifiers_options_(
            "standup", [snooze_action], [], 0
        )

        moved_action = UserNotifications.UNNotificationAction.actionWithIdentifier_title_options_(
            "moved", "Yep!", 0
        )
        sitdown_category = UserNotifications.UNNotificationCategory.categoryWithIdentifier_actions_intentIdentifiers_options_(
            "sitdown", [moved_action], [], 0
        )

        center.setNotificationCategories_({standup_category, sitdown_category})

        # Show notification settings prompt on first run
        self.check_first_run()

        # Initialize stats menu
        self.update_stats_menu()

        self.timer.start()

        # Track app opened
        self.track("app_opened", {"version": VERSION})

    def check_first_run(self):
        """Check if this is the first run and show notification settings prompt"""
        try:
            with open(self.config_path, "r") as f:
                config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            config = {}

        if not config.get("notification_prompt_shown"):
            self.show_notification_settings_prompt()
            config["notification_prompt_shown"] = True
            with open(self.config_path, "w") as f:
                json.dump(config, f)

    def dev_trigger_standup(self, _):
        """Dev: Trigger stand up notification"""
        self.show_standup_notification()

    def dev_trigger_sitdown(self, _):
        """Dev: Trigger sit down notification"""
        self.show_sitdown_notification()

    def dev_fake_old_version(self, _):
        """Dev: Fake old version to test updates"""
        global VERSION
        VERSION = "1.0.0"
        rumps.alert("Version set to 1.0.0", "Now use 'Check for Updates...' to test the update flow.")

    def show_standup_notification(self):
        """Show the stand up notification with streak message if applicable"""
        stats = self.load_stats()
        streak = stats.get("streak", 0)
        if streak >= 1:
            message = f"🔥 {streak} moves and counting. Keep going!"
        else:
            message = random.choice(STANDUP_MESSAGES)

        content = UserNotifications.UNMutableNotificationContent.alloc().init()
        content.setTitle_("Time to move!")
        content.setBody_(message)
        content.setCategoryIdentifier_("standup")
        content.setUserInfo_({"data": "standup"})

        notification_id = f"standup-{time_module.time()}"
        request = UserNotifications.UNNotificationRequest.requestWithIdentifier_content_trigger_(
            notification_id, content, None
        )
        UserNotifications.UNUserNotificationCenter.currentNotificationCenter().addNotificationRequest_withCompletionHandler_(
            request, lambda error: None
        )

        # Auto-dismiss after 10 seconds
        def remove_notification():
            time_module.sleep(10)
            UserNotifications.UNUserNotificationCenter.currentNotificationCenter().removeDeliveredNotificationsWithIdentifiers_([notification_id])

        threading.Thread(target=remove_notification, daemon=True).start()

    def show_sitdown_notification(self):
        """Show the sit down notification"""
        self.pending_sitdown_response = True

        content = UserNotifications.UNMutableNotificationContent.alloc().init()
        content.setTitle_("You can sit down again")
        content.setBody_("Did you move?")
        content.setCategoryIdentifier_("sitdown")
        content.setUserInfo_({"data": "sitdown"})

        request = UserNotifications.UNNotificationRequest.requestWithIdentifier_content_trigger_(
            f"sitdown-{time_module.time()}", content, None
        )
        UserNotifications.UNUserNotificationCenter.currentNotificationCenter().addNotificationRequest_withCompletionHandler_(
            request, lambda error: None
        )

    def dev_notification_settings(self, _):
        """Dev: Show notification settings prompt"""
        self.show_notification_settings_prompt()

    def show_notification_settings_prompt(self):
        """Show popover prompt to configure notification settings"""
        popover_width = 350
        popover_height = 388

        # Create the popover
        self.popover = NSPopover.alloc().init()
        self.popover.setBehavior_(NSPopoverBehaviorTransient)

        # Create content view
        content = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, popover_width, popover_height))

        # App icon (32px padding above)
        icon_size = 128
        icon_y = popover_height - 32 - icon_size
        icon_view = NSImageView.alloc().initWithFrame_(
            NSMakeRect((popover_width - icon_size) / 2, icon_y, icon_size, icon_size)
        )
        icon_image = NSImage.alloc().initWithContentsOfFile_(ICON_PATH)
        icon_view.setImage_(icon_image)
        icon_view.setImageScaling_(NSImageScaleProportionallyUpOrDown)
        content.addSubview_(icon_view)

        # Title label (16px below icon)
        title_height = 25
        title_y = icon_y - 16 - title_height
        title = NSTextField.alloc().initWithFrame_(NSMakeRect(15, title_y, popover_width - 30, title_height))
        title.setStringValue_("Welcome to Sit Down. Stand Up")
        title.setBezeled_(False)
        title.setDrawsBackground_(False)
        title.setEditable_(False)
        title.setSelectable_(False)
        title.setFont_(NSFont.boldSystemFontOfSize_(14))
        title.setAlignment_(NSTextAlignmentCenter)
        content.addSubview_(title)

        # Message label (fills space between title and buttons)
        message_y = 55
        message_height = title_y - 8 - message_y
        message = NSTextField.alloc().initWithFrame_(NSMakeRect(15, message_y, popover_width - 30, message_height))
        message.setStringValue_("🔔 Be notified to stand up for 5 minutes, every 30 minutes, and improve your health.\n\n🔥 Log each time you stand, and build up a streak.\n\n👉 For the best experience, 'Open Settings', find this app and change the banner style to 'Alerts'.")
        message.setBezeled_(False)
        message.setDrawsBackground_(False)
        message.setEditable_(False)
        message.setSelectable_(False)
        message.setFont_(NSFont.systemFontOfSize_(12))
        message.setAlignment_(NSTextAlignmentCenter)
        message.cell().setWraps_(True)
        message.cell().setLineBreakMode_(NSLineBreakByWordWrapping)
        content.addSubview_(message)

        # Create delegate for button callbacks
        def open_settings():
            os.system('open "x-apple.systempreferences:com.apple.Notifications-Settings"')

        self.popover_delegate = PopoverDelegate.alloc().initWithPopover_leftCallback_rightCallback_(
            self.popover, None, open_settings
        )

        # Center buttons horizontally with gap
        skip_width = 80
        settings_width = 115
        gap = 0
        total_width = skip_width + gap + settings_width
        start_x = (popover_width - total_width) / 2

        # Skip button
        skip_btn = NSButton.alloc().initWithFrame_(NSMakeRect(start_x, 15, skip_width, 28))
        skip_btn.setTitle_("Skip")
        skip_btn.setBezelStyle_(NSBezelStyleRounded)
        skip_btn.setTarget_(self.popover_delegate)
        skip_btn.setAction_(objc.selector(self.popover_delegate.leftButtonClicked_, signature=b'v@:@'))
        content.addSubview_(skip_btn)

        # Open Settings button
        settings_btn = NSButton.alloc().initWithFrame_(NSMakeRect(start_x + skip_width + gap, 15, settings_width, 28))
        settings_btn.setTitle_("Open Settings")
        settings_btn.setBezelStyle_(NSBezelStyleRounded)
        settings_btn.setTarget_(self.popover_delegate)
        settings_btn.setAction_(objc.selector(self.popover_delegate.rightButtonClicked_, signature=b'v@:@'))
        settings_btn.setKeyEquivalent_("\r")  # Enter key
        content.addSubview_(settings_btn)

        # Create view controller and set content
        vc = NSViewController.alloc().init()
        vc.setView_(content)
        self.popover.setContentViewController_(vc)
        self.popover.setContentSize_(content.frame().size)

        # Get the status item button from rumps and show popover
        status_button = self._nsapp.nsstatusitem.button()
        self.popover.showRelativeToRect_ofView_preferredEdge_(
            status_button.bounds(), status_button, NSMinYEdge
        )

    def screenDidSleep_(self, notification):
        """Called when screen goes to sleep (user left)"""
        self.timer.stop()

    def screenDidWake_(self, notification):
        """Called when screen wakes up (user returned) - restart timer from beginning"""
        self.is_countdown = False
        self.is_snooze = False
        self.time_remaining = self.work_duration
        self.title = "🧑‍💻"
        self.snooze_menu_item._menuitem.setHidden_(True)
        self.update_display()
        self.timer.start()

    @property
    def config_path(self):
        """Get the path to the config file"""
        config_dir = os.path.expanduser("~/.config/standup_reminder")
        os.makedirs(config_dir, exist_ok=True)
        return os.path.join(config_dir, "config.json")

    @property
    def stats_path(self):
        """Get the path to the stats file"""
        config_dir = os.path.expanduser("~/.config/standup_reminder")
        os.makedirs(config_dir, exist_ok=True)
        return os.path.join(config_dir, "stats.json")

    def get_user_id(self):
        """Get or create a unique user ID for analytics"""
        try:
            with open(self.config_path, "r") as f:
                config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            config = {}

        if "user_id" not in config:
            config["user_id"] = str(uuid.uuid4())
            with open(self.config_path, "w") as f:
                json.dump(config, f)

        return config["user_id"]

    def track(self, event, properties=None):
        """Track an event with PostHog"""
        try:
            posthog.capture(
                distinct_id=self.get_user_id(),
                event=event,
                properties=properties or {}
            )
            posthog.flush()
        except Exception:
            pass  # Silently fail if tracking fails

    def load_stats(self):
        """Load stats from file"""
        try:
            with open(self.stats_path, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {"days": {}}

    def save_stats(self, stats):
        """Save stats to file"""
        with open(self.stats_path, "w") as f:
            json.dump(stats, f, indent=2)

    def update_stats_menu(self):
        """Update the stats menu with current values"""
        stats = self.load_stats()
        today = time_module.strftime("%Y-%m-%d")

        # Streak
        streak = stats.get("streak", 0)
        self.stats_streak.title = f"Current streak: {streak} 🔥"

        # Today's stats
        today_stats = stats["days"].get(today, {"completed": 0, "snoozed": 0, "best_streak": 0})
        self.stats_today_stoodup.title = f"  Stood up: {today_stats.get('completed', 0)}"
        self.stats_today_snoozed.title = f"  Snoozed: {today_stats.get('snoozed', 0)}"
        self.stats_today_best.title = f"  Best streak: {today_stats.get('best_streak', 0)}"

        # All-time stats
        total_stoodup = 0
        total_snoozed = 0
        for day_stats in stats["days"].values():
            total_stoodup += day_stats.get("completed", 0)
            total_snoozed += day_stats.get("snoozed", 0)

        self.stats_alltime_stoodup.title = f"  Stood up: {total_stoodup}"
        self.stats_alltime_snoozed.title = f"  Snoozed: {total_snoozed}"
        self.stats_alltime_best.title = f"  Best streak: {stats.get('best_streak', 0)}"

    def record_prompt(self):
        """Record that a stand up prompt was shown"""
        today = time_module.strftime("%Y-%m-%d")
        stats = self.load_stats()
        if today not in stats["days"]:
            stats["days"][today] = {"prompts": 0, "completed": 0, "snoozed": 0}
        if "snoozed" not in stats["days"][today]:
            stats["days"][today]["snoozed"] = 0
        stats["days"][today]["prompts"] += 1
        self.save_stats(stats)
        self.update_stats_menu()

    def record_completed(self):
        """Record that user confirmed they moved"""
        today = time_module.strftime("%Y-%m-%d")
        stats = self.load_stats()
        if today not in stats["days"]:
            stats["days"][today] = {"prompts": 0, "completed": 0, "snoozed": 0, "best_streak": 0}
        if "snoozed" not in stats["days"][today]:
            stats["days"][today]["snoozed"] = 0
        if "best_streak" not in stats["days"][today]:
            stats["days"][today]["best_streak"] = 0
        stats["days"][today]["completed"] += 1

        # Increment streak
        stats["streak"] = stats.get("streak", 0) + 1
        current_streak = stats["streak"]

        # Update today's best streak if current is higher
        if current_streak > stats["days"][today]["best_streak"]:
            stats["days"][today]["best_streak"] = current_streak

        # Update all-time best streak if current is higher
        if current_streak > stats.get("best_streak", 0):
            stats["best_streak"] = current_streak

        self.save_stats(stats)
        self.pending_sitdown_response = False
        self.update_stats_menu()

        # Track stood up event
        self.track("stood_up", {"streak": current_streak})

    def record_snoozed(self):
        """Record that user snoozed"""
        today = time_module.strftime("%Y-%m-%d")
        stats = self.load_stats()
        if today not in stats["days"]:
            stats["days"][today] = {"prompts": 0, "completed": 0, "snoozed": 0}
        if "snoozed" not in stats["days"][today]:
            stats["days"][today]["snoozed"] = 0
        stats["days"][today]["snoozed"] += 1
        self.save_stats(stats)
        self.update_stats_menu()

        # Track snoozed event
        self.track("snoozed")

    def clear_streak(self):
        """Clear the current streak"""
        stats = self.load_stats()
        stats["streak"] = 0
        self.save_stats(stats)
        self.pending_sitdown_response = False
        self.update_stats_menu()

        # Track sit down dismissed event
        self.track("sit_down_dismissed")

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
        self.is_snooze = False
        self.time_remaining = self.countdown_duration
        self.title = "🕺"  # Standing person emoji
        self.snooze_menu_item._menuitem.setHidden_(False)  # Show snooze menu

        self.show_standup_notification()
        self.update_display()

    def snooze_clicked(self, _):
        """Handle snooze menu item click"""
        self.snooze()

    def snooze(self):
        """Snooze the stand up reminder for 5 minutes"""
        self.is_countdown = False
        self.is_snooze = True
        self.time_remaining = SNOOZE_DURATION
        self.title = "😴"
        self.snooze_menu_item._menuitem.setHidden_(True)  # Hide snooze menu

        # Record that user snoozed
        self.record_snoozed()

        self.update_display()

    def toggle_pause(self, _):
        """Toggle between paused and running states"""
        if self.is_paused:
            # Resume - restart timer from scratch
            self.is_paused = False
            self.is_countdown = False
            self.is_snooze = False
            self.time_remaining = self.work_duration
            self.title = "🧑‍💻"
            self.snooze_menu_item._menuitem.setHidden_(True)
            self.pause_menu_item.title = "Stop"
            self.timer.start()
            self.update_display()
        else:
            # Pause
            self.is_paused = True
            self.timer.stop()
            self.title = "⏹️"
            self.snooze_menu_item._menuitem.setHidden_(True)
            self.pause_menu_item.title = "Restart"
            self.timer_menu_item.title = "Stopped"

    def restart_work_timer(self):
        """Restart the work timer after countdown"""
        self.is_countdown = False
        self.is_snooze = False
        self.time_remaining = self.work_duration
        self.title = "🧑‍💻"  # Chair emoji
        self.snooze_menu_item._menuitem.setHidden_(True)  # Hide snooze menu

        # If user didn't respond to previous sit down notification, reset streak
        if self.pending_sitdown_response:
            stats = self.load_stats()
            stats["streak"] = 0
            self.save_stats(stats)
            self.update_stats_menu()

        # Record that we prompted the user
        self.record_prompt()

        self.show_sitdown_notification()
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
            self.title = f"🕺 {time_str}"
            self.timer_menu_item.title = f"Move around for: {time_str}"
        elif self.is_snooze:
            # Snooze mode - show sleep emoji
            self.title = "😴"
            self.timer_menu_item.title = f"Snoozed: {minutes}m"
        else:
            # Normal sit down mode
            self.title = "🧑‍💻"
            self.timer_menu_item.title = f"Standing up in: {minutes}m"

    def reset_timer(self, sender):
        """Reset the timer to start over"""
        self.is_countdown = False
        self.is_snooze = False
        self.time_remaining = self.work_duration
        self.title = "🧑‍💻"
        self.snooze_menu_item._menuitem.setHidden_(True)  # Hide snooze menu

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
        self.is_snooze = False
        self.time_remaining = self.work_duration
        self.title = "🧑‍💻"
        self.snooze_menu_item._menuitem.setHidden_(True)  # Hide snooze menu

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
        """Download the update and open in Finder for manual install"""
        try:
            # Download to Downloads folder
            downloads_dir = os.path.expanduser("~/Downloads")
            zip_path = os.path.join(downloads_dir, "SitDown.StandUp.app.zip")

            rumps.notification(
                title="Downloading Update",
                subtitle="",
                message="Please wait...",
                sound=False,
            )

            urllib.request.urlretrieve(download_url, zip_path)

            # Extract the zip
            extract_dir = os.path.join(downloads_dir, "SitDown.StandUp.Update")
            shutil.rmtree(extract_dir, ignore_errors=True)
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)

            # Remove the zip
            os.remove(zip_path)

            # Open the folder in Finder
            subprocess.run(["open", extract_dir])

            rumps.alert(
                title="Update Downloaded",
                message="The new version is in your Downloads folder.\n\nTo install:\n1. Drag the app to Applications\n2. Right-click → Open\n3. Click 'Open' to approve",
                ok="OK",
            )

        except Exception as e:
            rumps.alert(
                title="Update Failed",
                message=f"Could not download update: {str(e)}",
                ok="OK",
            )


if __name__ == "__main__":
    app = StandUpApp()
    app.run()
