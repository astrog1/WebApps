# Blackjack (Flask + Socket.IO)

**Features**
- Rooms with 4-letter codes; create/join
- Up to 6 seated players per table
- 6-deck shoe, dealer hits soft 17 (configurable)
- Bets, insurance (when dealer shows Ace), double, single split, late surrender
- Blackjack pays 3:2; pushes return bet
- Dark UI styled like your Yahtzee app

## Run locally
```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python app.py  # open http://localhost:5000
```

## Docker
```bash
docker build -t blackjack-game .
docker run -d --name blackjack-game -p 5006:5000 blackjack-game
# open http://<your-pc-ip>:5006
```

## Notes
- Minimum bet: 5, Maximum bet: 500 (change in `app.py`)
- Starting chips per player: 1000 (change in `Player` dataclass)
- Basic anti-spam is included.
- Splits: single split only. Insurance cost: half the main bet, pays 2:1 if dealer has blackjack.
- Surrender: late surrender, refunds 50% immediately for that hand.
```
"""

# --- write files to the canvas virtual fs (display only) ---
print("app.py\n"+app_py)
print("\n\n# templates/index.html\n"+index_html)
print("\n\n# static/style.css\n"+style_css)
print("\n\n# requirements.txt\n"+requirements_txt)
print("\n\n# Dockerfile\n"+Dockerfile_txt)
print("\n\n# README.md\n"+readme_md)
