# StandUp Reminder

A simple macOS menu bar app that reminds you to stand up at regular intervals with a 5-minute countdown.

## Features

- 🪑 Sits in your menu bar with a chair emoji during work periods
- ⏰ Configurable work intervals: 1 minute, 30 minutes, or 1 hour
- 🧍 Shows a 5-minute countdown with a standing person emoji
- 🔄 Automatically restarts the timer after each break
- 🔔 Sends notifications when it's time to stand and when break is over
- ⚡ Manual reset option available from the menu

## Installation

1. Install Python 3 if you don't have it already
2. Install the required dependencies:
   ```bash
   pip3 install -r requirements.txt
   ```

## Usage

Run the app:
```bash
python3 standup_reminder.py
```

The app will appear in your menu bar with a 🪑 icon.

### How it works:
1. The app starts with a 30-minute work timer (default)
2. After the work period, you'll get a notification to stand up
3. The icon changes to 🧍 and shows a 5-minute countdown
4. After 5 minutes, you'll get a notification that the break is over
5. The timer automatically restarts for another work period

### Menu Options:
- Click the icon to see time remaining
- **Work Interval**: Choose between 1 minute, 30 minutes, or 1 hour intervals
- **Reset Timer**: Manually reset the work timer
- **Quit**: Close the app

## Making it Run on Startup

To make the app run automatically when you log in:

1. Open **System Preferences** → **Users & Groups** → **Login Items**
2. Create a simple shell script (e.g., `start_standup.sh`):
   ```bash
   #!/bin/bash
   cd /Users/ricardo/Projects/StandUp
   /usr/local/bin/python3 standup_reminder.py
   ```
3. Make it executable: `chmod +x start_standup.sh`
4. Add the script to your Login Items

## Customization

Work intervals can be changed directly from the menu (1 minute, 30 minutes, or 1 hour).

For advanced customization, you can edit `standup_reminder.py`:
- Add more interval options to the `self.intervals` dictionary (line 16-20)
- Change the break duration: `self.countdown_duration = 5 * 60` (in seconds)
