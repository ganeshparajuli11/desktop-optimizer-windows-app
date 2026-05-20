# SysCtl - Windows System Control Center

[![Latest Release](https://img.shields.io/github/v/release/ganeshparajuli11/desktop-optimizer-windows-app?label=Download&style=for-the-badge&logo=windows&color=0078d4)](https://github.com/ganeshparajuli11/desktop-optimizer-windows-app/releases/latest)
[![Build](https://img.shields.io/github/actions/workflow/status/ganeshparajuli11/desktop-optimizer-windows-app/build.yml?style=for-the-badge)](https://github.com/ganeshparajuli11/desktop-optimizer-windows-app/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.8+-blue?style=for-the-badge&logo=python)](https://python.org)

A powerful, modern open-source system monitor and optimizer for Windows.
Built with Python + CustomTkinter. RTX GPU support via pynvml.

---

## Download & Run (No install needed)

> **Easiest way — just download and run the exe:**

1. Go to [**Releases**](https://github.com/ganeshparajuli11/desktop-optimizer-windows-app/releases/latest)
2. Download **`SysCtl.exe`**
3. Double-click it
4. Windows will show a **UAC permission prompt** — click **Yes** (needed for startup management and system optimization)
5. The app opens — you're done!

> No Python, no pip, no setup required. Just the exe.

---

## Features

| Feature | Description |
|---------|-------------|
| Process Manager | Live RAM/CPU per process, one-click kill, filter/sort |
| Network Monitor | Real-time upload/download speed, active connections |
| Disk I/O Monitor | Per-drive usage, read/write speed, per-process I/O |
| GPU Monitor | RTX load, VRAM, temperature, power draw (pynvml) |
| Docker Monitor | Live container stats, stop/restart/logs from the UI |
| StandBy Clock | Fullscreen clock for second monitor with live stats + timer |
| Profiles | Gaming Mode, Dev Mode, Battery Saver, Normal |
| Smart Alerts | Windows notifications when RAM/CPU/GPU thresholds exceeded |
| Startup Manager | View and remove startup apps from registry + startup folder |
| Quick Actions | Free RAM, Clean Temp, Flush DNS, Kill RAM Hogs |
| Beginner CPU Optimizer | Safe/Balanced/Aggressive with explain mode, result card, and undo |
| Background Apps | Safe one-click stop controls, startup blocklist, always-allow whitelist, presets |
| Focus Hub | 25/45/60 min focus sessions, optional break sound, completion notification |
| Unified Home | Plain-language health cards for CPU/RAM/Temp/Battery/Network with details toggle |
| Smart Assistant | One-click actions: “My PC is slow”, “Prepare for meeting”, “Battery rescue” |
| Daily Summary | Focus minutes, apps closed count, CPU stability trend, simple daily sentence |

---

## Screenshots

> Dashboard with live graphs / StandBy clock / Docker monitor

---

## Other Install Options

### Run from source (developers)
```bash
git clone https://github.com/ganeshparajuli11/desktop-optimizer-windows-app.git
cd desktop-optimizer-windows-app
pip install customtkinter psutil pynvml
python sysctl.py
```

### One-click batch installer
Download the repo and double-click `RunSysCtl.bat` — it installs dependencies and launches the app.

### pip package
```bash
pip install sysctl-monitor
sysctl
```

---

## Requirements

| | Requirement |
|-|-------------|
| OS | Windows 10 / 11 (64-bit) |
| Python | 3.8+ (only needed if running from source) |
| GPU tab | NVIDIA GPU with drivers (hidden automatically if not present) |
| Docker tab | Docker Desktop (shows status if not installed) |

---

## Usage

The `.exe` automatically requests admin permission on launch via UAC. If you run from source, right-click your terminal and **Run as Administrator** for full features (startup registry editing, killing system processes).

### StandBy Clock
- Click the **StandBy** tab → **Launch StandBy Clock**
- Drag the window to your second monitor
- Press **F11** for fullscreen
- Click the timer area to start/stop, double-click to reset
- Press **Escape** to close

### Profiles
| Profile | What it does |
|---------|-------------|
| Gaming Mode | Kills background apps, maxes GPU priority, High Performance power plan |
| Dev Mode | Balanced plan, cleans npm/pip cache, keeps Docker running |
| Battery Saver | Power Saver plan, kills heavy background apps |
| Normal | Resets everything to defaults |

### CPU Optimizer (Beginner-friendly)
- Open **CPU Optimizer**
- Keep mode on **Safe** (default) for everyday use
- Click **Optimize CPU Now**
- Review:
  - CPU before optimization
  - CPU after optimization
  - 5-minute average comparison
- Use **Undo Last Optimization** to restore previous power settings where possible

### Background Apps
- Open **Background Apps**
- Review running heavy/tray-like apps with friendly names
- Actions:
  - **Stop now**
  - **Stop on startup**
  - **Keep always allowed**
- Presets:
  - **Work Focus**
  - **Gaming Focus**
  - **Battery Saver**

### Focus Hub
- Open **Focus Hub**
- Start a **25 / 45 / 60 min** focus timer
- Optional:
  - **Play break reminder sound**
  - **Start Focus with Safe CPU Optimize**
- On session end, SysCtl shows a Windows notification

### Home + Daily Summary
- **Home** tab shows beginner-friendly Good/Warning/Critical cards
- Use **Show details** for extra metrics
- **Daily Summary** shows focus time, closed apps count, CPU stability trend, and a plain summary line

### Docker Monitor
Requires Docker Desktop installed and running. Shows live CPU/memory per container with stop/restart/logs buttons. Docker stats refresh every 8 seconds in their own thread so they never lag the rest of the app.

---

## Build the .exe yourself

```bash
# Install build tools
pip install pyinstaller customtkinter psutil pynvml

# Build (uses sysctl.spec — includes UAC manifest)
build_exe.bat
```

Output: `dist/SysCtl.exe` — standalone, no Python required on the target machine.

**Or let GitHub Actions build it for you:**
```bash
git tag v1.0.0
git push --tags
```
GitHub will build and attach `SysCtl.exe` to the release automatically.

---

## Why does it ask for admin permission?

SysCtl needs admin access to:
- Remove startup registry entries (`HKLM\...\Run`)
- Kill system-level processes
- Switch Windows power plans
- Apply GPU performance registry tweaks
- Apply some Balanced/Aggressive or profile-level performance tuning

It does **not** send any data anywhere. All operations are local.

### Data persistence
SysCtl stores local JSON state under Windows user AppData (`%APPDATA%\sysctl\sysctl_state.json`) for:
- Safe settings and defaults
- Background app whitelist/startup blocklist
- CPU optimizer history for undo/results
- Daily summary counters

If JSON becomes corrupted, SysCtl resets safely and keeps a `.corrupt.json` backup.

---

## Manual test steps for new features

1. Launch SysCtl and verify tabs exist: **Home**, **CPU Optimizer**, **Background Apps**, **Focus Hub**, **Assistant**, **Daily Summary**
2. In **CPU Optimizer**, run **Safe** mode and verify before/after/5-minute result text updates
3. Run **Balanced/Aggressive** and verify Explain dialog + risk label appears before applying
4. Click **Undo Last Optimization** and verify undo status message appears
5. In **Background Apps**, verify:
   - critical system apps are not killable
   - Stop now handles access errors with safe fallback text
   - Stop on startup and Keep always allowed persist after restart
6. Apply each preset (Work/Gaming/Battery) and verify closed app count/status updates
7. In **Focus Hub**, start 25 min session, confirm timer starts; stop manually and restart
8. Enable break sound + notification, set a short test session by editing timer during development and verify end notification/sound
9. In **Assistant**, run each one-click action and verify explain text + expected result + undo button behavior
10. In **Home**, toggle **Show details** and verify plain cards update (Good/Warning/Critical)
11. In **Daily Summary**, confirm focus minutes, apps closed, CPU stability trend, and summary sentence update
12. Close and reopen app; confirm JSON-backed settings and summary values are retained

---

## Contributing

Pull requests are welcome! Open an issue first to discuss what you want to change.

```bash
# Fork, then:
git checkout -b feature/your-idea
git commit -m "Add your idea"
git push origin feature/your-idea
# Open a Pull Request on GitHub
```

---

## License

MIT — see [LICENSE](LICENSE). Free to use, modify, and distribute.

---

## Roadmap

- [ ] Custom app icon (.ico)
- [ ] Plugin system for custom tabs
- [ ] Config file (save alert thresholds, profile settings)
- [ ] WSL2 resource monitor
- [ ] Temperature history export (CSV)
- [ ] Auto-start on Windows boot option
- [ ] Installer (NSIS/Inno Setup) for clean uninstall support
