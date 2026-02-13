# Daily Math Game (Local-First)

Daily Math Game is a mobile-first FastAPI app that generates and stores one math set per day in local SQLite using OpenAI (`gpt-4.1-mini` by default).

## Stack

- Python 3.11+
- FastAPI + Uvicorn
- Jinja2 templates
- Vanilla JavaScript (no frontend framework)
- SQLite
- OpenAI API via HTTP (`httpx`)

## Project Structure

```text
.
|-- app/
|   |-- main.py
|   |-- db.py
|   |-- openai_client.py
|   |-- schemas.py
|   |-- utils.py
|   |-- templates/
|   |   |-- base.html
|   |   |-- index.html
|   |   `-- play.html
|   `-- static/
|       |-- styles.css
|       `-- play.js
|-- requirements.txt
|-- .gitignore
`-- README.md
```

## Setup (Windows PowerShell)

### 1) Create and activate virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2) Install dependencies

```powershell
pip install -r requirements.txt
```

### 3) Set OpenAI API key

```powershell
$env:OPENAI_API_KEY = "sk-..."
```

Optional model override (default is `gpt-4.1-mini`):

```powershell
$env:OPENAI_MODEL = "gpt-4.1-mini"
```

### 4) Run the app

```powershell
uvicorn app.main:app --reload
```

Open:

- Landing: http://127.0.0.1:8000/
- Play: http://127.0.0.1:8000/play

## Setup (Ubuntu Desktop)

### 1) Install Python tooling

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
```

### 2) Create and activate virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3) Install dependencies

```bash
python -m pip install -r requirements.txt
```

### 4) Set OpenAI API key

```bash
export OPENAI_API_KEY="sk-..."
```

Optional model override (default is `gpt-4.1-mini`):

```bash
export OPENAI_MODEL="gpt-4.1-mini"
```

### 5) Run the app

```bash
uvicorn app.main:app --reload
```

Open:

- Landing: http://127.0.0.1:8000/
- Play: http://127.0.0.1:8000/play

## API Endpoints

- `POST /generate`
  - If today exists in SQLite, returns existing payload + metadata.
  - Otherwise generates using OpenAI and stores payload + token usage metadata.
- `GET /daily/today`
  - Returns today's payload or 404.
- `GET /daily/today/meta`
  - Returns today's metadata including model + input/output/total tokens.
- `GET /daily/{date}`
  - Returns payload for `YYYY-MM-DD` date or 404.
- `GET /daily/{date}/meta`
  - Returns metadata for `YYYY-MM-DD` date or 404.

## PowerShell test calls

Generate today:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/generate
```

Read today payload:

```powershell
Invoke-RestMethod -Method Get -Uri http://127.0.0.1:8000/daily/today
```

Read today token usage metadata:

```powershell
Invoke-RestMethod -Method Get -Uri http://127.0.0.1:8000/daily/today/meta
```

Read specific date:

```powershell
Invoke-RestMethod -Method Get -Uri http://127.0.0.1:8000/daily/2026-02-10
Invoke-RestMethod -Method Get -Uri http://127.0.0.1:8000/daily/2026-02-10/meta
```

## Token Usage Output

Token usage is shown in two places:

- Landing page (`/`) after today's set exists (input/output/total tokens + model).
- Metadata endpoints (`/daily/today/meta`, `/daily/{date}/meta`).

## OpenAI Setup and Billing

### You need

- An OpenAI account
- An API key
- Billing enabled for API usage

### Create API key

- API keys page: https://platform.openai.com/api-keys

### Billing setup and pricing

- Billing overview: https://platform.openai.com/settings/organization/billing/overview
- Usage dashboard: https://platform.openai.com/usage
- API pricing: https://platform.openai.com/pricing

## How token charging works

For each API call, OpenAI reports token usage in:

- input tokens (prompt/messages)
- output tokens (model completion)
- total tokens

Your account is charged according to the model's per-token pricing on the pricing page. This app stores those usage numbers for each generated day.

## Troubleshooting

- `OPENAI_API_KEY is missing`: set `$env:OPENAI_API_KEY` before starting the app.
- On Ubuntu/Linux, use `export OPENAI_API_KEY="sk-..."` before starting the app.
- HTTP 401 from OpenAI: API key is invalid or missing.
- HTTP 429 from OpenAI: rate limit or quota/billing issue.
- Slow generation: retries may occur if strict schema validation fails.

## Notes

- SQLite file defaults to `daily_math_game.db` in project root.
- Override DB path with environment variable `DAILY_MATH_DB` if needed.
- Date key uses server local date (`YYYY-MM-DD`).
