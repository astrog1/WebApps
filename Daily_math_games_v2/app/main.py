from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import db, openai_client, utils


BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Daily Math Game", version="1.0.0")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@app.on_event("startup")
def startup() -> None:
    db.init_db()


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    today = utils.today_local_date_str()
    today_exists = db.daily_set_exists(today)
    today_meta = db.get_daily_meta(today) if today_exists else None

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "today_exists": today_exists,
            "today": today,
            "today_meta": today_meta,
        },
    )


@app.get("/play", response_class=HTMLResponse)
def play_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "play.html", {})


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)


@app.post("/generate")
def generate_today() -> dict:
    today = utils.today_local_date_str()
    existing = db.get_daily_set(today)
    if existing is not None:
        return {
            "status": "existing",
            "payload": existing,
            "meta": db.get_daily_meta(today),
        }

    try:
        result = openai_client.generate_daily_payload(today)
        db.insert_daily_set(
            today,
            result.payload,
            usage=result.usage,
            model_name=result.model,
        )
        return {
            "status": "generated",
            "payload": result.payload,
            "meta": db.get_daily_meta(today),
        }
    except sqlite3.IntegrityError:
        payload = db.get_daily_set(today)
        if payload is not None:
            return {
                "status": "existing",
                "payload": payload,
                "meta": db.get_daily_meta(today),
            }
        raise HTTPException(status_code=500, detail="Failed to store generated set")
    except openai_client.OpenAIGenerationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/daily/today")
def get_today_daily() -> dict:
    today = utils.today_local_date_str()
    payload = db.get_daily_set(today)
    if payload is None:
        raise HTTPException(status_code=404, detail="No daily set for today")
    return payload


@app.get("/daily/today/meta")
def get_today_meta() -> dict:
    today = utils.today_local_date_str()
    meta = db.get_daily_meta(today)
    if meta is None:
        raise HTTPException(status_code=404, detail="No daily set metadata for today")
    return meta


@app.get("/daily/{date_str}")
def get_daily_by_date(date_str: str) -> dict:
    if not utils.is_valid_date_str(date_str):
        raise HTTPException(status_code=400, detail="Date must be YYYY-MM-DD")

    payload = db.get_daily_set(date_str)
    if payload is None:
        raise HTTPException(status_code=404, detail="No daily set for this date")
    return payload


@app.get("/daily/{date_str}/meta")
def get_daily_meta_by_date(date_str: str) -> dict:
    if not utils.is_valid_date_str(date_str):
        raise HTTPException(status_code=400, detail="Date must be YYYY-MM-DD")

    meta = db.get_daily_meta(date_str)
    if meta is None:
        raise HTTPException(status_code=404, detail="No daily set metadata for this date")
    return meta
