# WebApps

This repository is my central place for all current and future web apps that I host.

## Current Apps
- `blackjack-game` - Multiplayer Blackjack (Flask + Socket.IO)
- `yahtzee-game` - Multiplayer Yahtzee (Flask + Socket.IO)
- `Daily_math_games_v2` - Daily math challenge app (FastAPI + SQLite + OpenAI API)

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

### 2) Yahtzee Game
```powershell
cd yahtzee-game
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```
Open: `http://localhost:5000`

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

## Notes
- Run one app at a time unless you change ports.
- Each app has its own folder-level `README.md` with more details.
