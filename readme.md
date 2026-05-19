
# 🔓 MI Bootloader Unlock Tool

**Automated, Multi-Platform, High-Precision Request Sender for Xiaomi Bootloader Unlock**

[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20Android%20(Termux)-blue)](https://github.com/fl4te/mi-bootloader-unlock-tool)
[![Python](https://img.shields.io/badge/Python-3.8%2B-yellow)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-Educational%20Use%20Only-red)](https://github.com/fl4te/mi-bootloader-unlock-tool)

---

> This is a fork of [flowTech-x/unlock-tool](https://github.com/flowTech-x/unlock-tool), enhanced with a GUI, improved timing logic, and multi-platform support.

---

## Features

**Multi-Platform Support**
  - Windows
  - Linux
  - Android (Termux)

**GUI & CLI Modes**
  - Tkinter-based graphical interface
  - Terminal-based automation (`script.py`)

**4 Parallel Slots**
  - Run up to 4 simultaneous unlock request sessions

**Token Reuse Logic**
  - Only 2 tokens required
  - Slots 1 & 3 use Token 1
  - Slots 2 & 4 use Token 2

**NTP Time Synchronization**
  - Automatically syncs with Beijing time (`Asia/Shanghai`)

**Burst Mode**
  - Configurable:
    - burst count
    - interval
    - pre-fire offset

**Auto / Midnight Mode**
  - Fire requests automatically at `00:00 Beijing Time`
  - Or set a custom manual fire time

**Real-Time Logs**
  - Color-coded status output
  - Errors, debug info, and success logs

**TMUX/PSMUX Integration**
  - Auto-splits terminal into 4 panes for parallel execution

---

# Requirements

## All Platforms

- Python 3.8+
- `pip`
- Stable internet connection
- Firefox Browser or one of its forks

---

## Linux

- Python 3.8+
- `tkinter` (usually bundled with Python)
- `tmux` (Linux CLI mode only)

---

## Windows

- Python 3.8+
- `tkinter` (usually bundled with Python)
- `psmux` (Windows CLI mode only)

---

## Android (Termux)

- **Termux (F-Droid or direct apk download version only)**  
  https://f-droid.org/packages/com.termux/
  https://github.com/termux/termux-app
  

- `tmux`

> Do NOT use the Play Store version of Termux (deprecated)

---

# Installation

## 1) Clone the Repository

```bash
git clone https://github.com/fl4te/mi-bootloader-unlock-tool.git
cd mi-bootloader-unlock-tool
```

## 2) Install Dependencies
**Linux/Windows**
```bash
pip install -r requirements.txt
```
> Missing packages may be auto-installed on first launch.

**Android (Termux)**
```bash
pkg install python tmux -y  
pip install -r requirements.txt
```
# Token Setup
## Get your Xiaomi Tokens

1) Log into your Xiaomi account on:
    -   Mi Community Global
2) Open Firefox with the Cookie-Editor extension installed, keep in mind this tool supports 2 tokens, you can get a second token using Firefox Containers.
3) Extract the cookie value:
```
new_bbs_serviceToken
```
4) Copy the cookie VALUE only.
5) Add tokens to token.txt or in the according fields within the GUI tool.
```
YOUR_TOKEN_1
YOUR_TOKEN_2
```
**Token Mapping:**
| Slot | Token |
|--|--|
| 1 | Token 1 |
| 2 | Token 2 |
| 3 | Token 1 |
| 4 | Token 2 |

# Usage
## Option 1: GUI (recommended)
**Launch the GUI tool:**
```bash
Linux/Termux:
python gui.py

Windows:
python.exe gui.py
```
**GUI features:**
-   Configure burst settings
-   Enable / disable slots
-   Set manual fire times
-   Real-time colored logs

Click **RUN** to begin.

## Option 2: CLI
**Single Slot:**
```bash
python script.py
```
**4 parallel slots:**
```bash
Linux/Termux
chmod +x start_4.sh
./start_4.sh

or
bash start_4.sh
```
```powershell
Windows:
.\start_4.ps1
```
Each pane will prompt for a slot number (`1-4`).

----------

# !! Disclaimer !!

## Educational Use Only

This tool is provided strictly for educational and research purposes.

### Risks
-   Xiaomi may suspend or ban accounts
-   Unlocking bootloaders may:
    -   void warranties
    -   reduce device security
    -   violate terms of service

> Use entirely at your own risk.
