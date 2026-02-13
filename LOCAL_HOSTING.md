# Local Hosting Setup (Ubuntu)

This guide runs all apps on your Ubuntu desktop for local/LAN testing:

- Homepage hub: `http://<ubuntu-ip>:8080`
- Blackjack: `http://<ubuntu-ip>:5101`
- Yahtzee: `http://<ubuntu-ip>:5102`
- Daily Math: `http://<ubuntu-ip>:5103`

## Quick start (one command)

After you complete venv setup once, you can launch everything with:

```bash
cd ~/hosting_apps
bash ./star_local.sh start
```

Useful commands:

```bash
bash ./star_local.sh status
bash ./star_local.sh stop
bash ./star_local.sh restart
```

Optional env vars before start:

```bash
export OPENAI_API_KEY="sk-..."
export BLACKJACK_PORT=5101
export YAHTZEE_PORT=5102
export MATH_PORT=5103
export HUB_PORT=8080
```

## 1) Install prerequisites

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git
```

## 2) Clone/open project

```bash
cd ~
git clone <your-repo-url> hosting_apps
cd hosting_apps
```

If the repo already exists, just `cd` into it.

## 3) Prepare each app environment

### Blackjack (`blackjack-game`)

```bash
cd ~/hosting_apps/blackjack-game
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
deactivate
```

### Yahtzee (`yahtzee-game`)

```bash
cd ~/hosting_apps/yahtzee-game
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
deactivate
```

### Daily Math (`Daily_math_games_v2`)

```bash
cd ~/hosting_apps/Daily_math_games_v2
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
deactivate
```

## 4) Start all apps (4 terminals)

Run each block in its own terminal tab/window.

### Terminal A: Blackjack on port 5101

```bash
cd ~/hosting_apps/blackjack-game
source .venv/bin/activate
PORT=5101 python app.py
```

### Terminal B: Yahtzee on port 5102

```bash
cd ~/hosting_apps/yahtzee-game
source .venv/bin/activate
PORT=5102 python app.py
```

### Terminal C: Daily Math on port 5103

```bash
cd ~/hosting_apps/Daily_math_games_v2
source .venv/bin/activate
export OPENAI_API_KEY="sk-..."
uvicorn app.main:app --host 0.0.0.0 --port 5103
```

Notes:
- `OPENAI_API_KEY` is only required for generating new daily sets (`POST /generate`).
- Browsing existing static pages still works without a key.

### Terminal D: Homepage hub on port 8080

```bash
cd ~/hosting_apps
python3 -m http.server 8080 --bind 0.0.0.0 --directory home-page
```

## 5) Open the homepage

On Ubuntu host:

```text
http://localhost:8080
```

From another device on your network:

```text
http://<ubuntu-ip>:8080
```

Find your Ubuntu LAN IP:

```bash
hostname -I
```

## 6) Add future apps to the homepage

Edit `home-page/index.html`:

- Copy one app card block.
- Change the app name.
- Change both `data-port` and `data-port-link` to the new app port.

Then refresh the homepage.

## 7) Troubleshooting

- Port already in use:
  - Change the port, or stop the existing process:
  - `ss -ltnp | grep :5101` (swap port as needed)
- Cannot access from other devices:
  - Confirm server is bound to `0.0.0.0`.
  - Allow firewall ports:
  - `sudo ufw allow 8080`
  - `sudo ufw allow 5101:5103/tcp`
- Homepage loads but app links fail:
  - Confirm each app terminal is still running.
  - Open the app URL directly first (for example `http://<ubuntu-ip>:5101`).
