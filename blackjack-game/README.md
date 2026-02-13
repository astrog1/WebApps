# Blackjack Game (Flask + Socket.IO)

Multiplayer Blackjack web app with room codes and real-time gameplay over Socket.IO.

## Features
- Create/join game rooms with short codes
- Up to 6 seated players per table
- Betting with min/max limits
- Hit, stand, double, split, surrender, and insurance actions
- Dealer flow with delayed reveal/draw animations
- Round results and chip tracking per player

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
docker build -t blackjack-game .
docker run -d --name blackjack-game -p 5000:5000 blackjack-game
```

Open:
- `http://localhost:5000`

## Optional Environment Variables
- `SECRET_KEY` (default: internal fallback)
- `DEALER_REVEAL_DELAY` (default: `0.9` seconds)
- `DEALER_DRAW_DELAY` (default: `0.9` seconds)
- `PORT` (default: `5000`)

Example (Linux/macOS):
```bash
PORT=5101 python app.py
```

Example (PowerShell):
```powershell
$env:PORT = "5101"
python app.py
```

## Project Files
- `app.py` - Flask app and Socket.IO game logic
- `templates/index.html` - UI template
- `static/style.css` - App styling
- `requirements.txt` - Python dependencies
- `dockerfile` - Container build and startup
