# SysCtl - Windows System Control Center

[![Latest Release](https://img.shields.io/github/v/release/ganeshparajuli11/desktop-optimizer-windows-app?label=Download&style=for-the-badge&logo=windows&color=0078d4)](https://github.com/ganeshparajuli11/desktop-optimizer-windows-app/releases/latest)
[![Build](https://img.shields.io/github/actions/workflow/status/ganeshparajuli11/desktop-optimizer-windows-app/build.yml?style=for-the-badge)](https://github.com/ganeshparajuli11/desktop-optimizer-windows-app/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.8+-blue?style=for-the-badge&logo=python)](https://python.org)

A powerful, modern open-source system monitor and optimizer for Windows.
Built with Python + CustomTkinter. RTX GPU support via NVIDIA NVML Python bindings.

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

---

## Screenshots

> Dashboard with live graphs / StandBy clock / Docker monitor

---

## Other Install Options

### Run from source (developers)
```bash
git clone https://github.com/ganeshparajuli11/desktop-optimizer-windows-app.git
cd desktop-optimizer-windows-app
pip install customtkinter psutil nvidia-ml-py
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

### Docker Monitor
Requires Docker Desktop installed and running. Shows live CPU/memory per container with stop/restart/logs buttons. Docker stats refresh every 8 seconds in their own thread so they never lag the rest of the app.

---

## Build the .exe yourself

```bash
# Install build tools
pip install pyinstaller customtkinter psutil nvidia-ml-py

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

It does **not** send any data anywhere. All operations are local.

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
