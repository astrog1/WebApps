# Yahtzee Game (Flask + Socket.IO)

Multiplayer Yahtzee web app served by Flask with real-time state updates over Socket.IO.

## Features
- Real-time multiplayer turns and score updates
- Up to 3 rolls per turn with hold/unhold dice
- Full Yahtzee scorecard with upper bonus and bonus Yahtzees
- Duplicate-join protection per device
- Game-over standings and play-again flow

## Requirements
- Python 3.10+

## Run Locally (PowerShell)
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Open:
- `http://localhost:5000`

## Run with Docker
```bash
docker build -t yahtzee-game .
docker run -d --name yahtzee-game -p 5000:5000 yahtzee-game
```

Open:
- `http://localhost:5000`

## Project Files
- `app.py` - Flask app, Socket.IO events, and embedded HTML/CSS/JS UI
- `requirements.txt` - Python dependencies
- `Dockerfile` - Container build and startup

## Optional Environment Variables
- `PORT` (default: `5000`)

Example (Linux/macOS):
```bash
PORT=5102 python app.py
```

Example (PowerShell):
```powershell
$env:PORT = "5102"
python app.py
```
