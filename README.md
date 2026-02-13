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

## Run Locally

### Prerequisites
- Python 3.10+ installed
- PowerShell (commands below use PowerShell syntax)

### 1) Blackjack Game
```powershell
cd blackjack-game
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```
Open: `http://localhost:5000`

Use a custom port if needed:

```powershell
$env:PORT = "5101"
python app.py
```

### 2) Yahtzee Game
```powershell
cd yahtzee-game
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```
Open: `http://localhost:5000`

Use a custom port if needed:

```powershell
$env:PORT = "5102"
python app.py
```

### 3) Daily Math Games
```powershell
cd Daily_math_games_v2
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:OPENAI_API_KEY = "sk-..."
uvicorn app.main:app --reload
```
Open:
- `http://127.0.0.1:8000/`
- `http://127.0.0.1:8000/play`

### 4) Homepage Hub
```powershell
cd home-page
python -m http.server 8080
```
Open:
- `http://127.0.0.1:8080`

## Notes
- You can run all apps together by assigning unique ports.
- Each app has its own folder-level `README.md` with more details.
