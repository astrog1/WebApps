# WebApps

This repository is my central place for all current and future web apps that I host.

## Current Apps
- `blackjack-game` - Multiplayer Blackjack (Flask + Socket.IO)
- `yahtzee-game` - Multiplayer Yahtzee (Flask + Socket.IO)
- `Daily_math_games_v2` - Daily math challenge app (FastAPI + SQLite + OpenAI API)
- `home-page` - Local homepage hub that links to all apps

## Ubuntu Local Hosting Guide

Use `LOCAL_HOSTING.md` for full Linux setup and run instructions (all apps at once + homepage).

Quick launcher (Linux):

```bash
bash ./star_local.sh start
```

## Windows 11 Setup and Run (Scripted)

Use the repo scripts for setup/start/stop:
- `setup_local.ps1` (one-time venv + dependencies)
- `start_local.ps1` (`start`, `stop`, `status`, `restart`)

### 1) Install prerequisites (one-time)
- Install Git for Windows.
- Install Python 3.10+ and enable "Add python.exe to PATH" during install.

Verify in PowerShell:

```powershell
git --version
python --version
pip --version
```

### 2) Clone the repo (or open existing folder)

```powershell
cd $HOME\Desktop
git clone <your-repo-url> hosting_apps
cd hosting_apps
```

If the folder already exists, just `cd` into it.

### 3) Allow local scripts (one-time)

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### 4) Run setup (one-time)

```powershell
cd C:\Users\<your-user>\Desktop\hosting_apps
.\setup_local.ps1
```

This creates `.venv` and installs dependencies for:
- `yahtzee-game`
- `Daily_math_games_v2`

### 5) Set OpenAI API key (needed for Daily Math generation)

Persistent user env var:

```powershell
setx OPENAI_API_KEY "sk-..."
```

Open a new PowerShell window after `setx`, then `cd` back to the repo.

### 6) Start services

```powershell
.\start_local.ps1 start
```

### 7) Status / Stop / Restart

```powershell
.\start_local.ps1 status
.\start_local.ps1 stop
.\start_local.ps1 restart
```

### 8) Default local URLs

- Hub: `http://localhost:8080`
- Yahtzee: `http://localhost:5102`
- Daily Math: `http://localhost:5103`

### Optional port/bind overrides (set before `start`)

```powershell
$env:YAHTZEE_PORT = "5102"
$env:MATH_PORT = "5103"
$env:HUB_PORT = "8080"
$env:HOST_BIND = "0.0.0.0"
.\start_local.ps1 start
```

### Logs

Runtime logs and PID files are written under:
- `.local_runtime\logs`
- `.local_runtime\pids`

## Notes
- `start_local.ps1` currently starts `yahtzee-game`, `Daily_math_games_v2`, and `home-page`.
- Each app has its own folder-level `README.md` with more details.
