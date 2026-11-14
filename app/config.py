"""Configuration centralisée, lue depuis les variables d'environnement."""

from __future__ import annotations

import os
import secrets
from pathlib import Path


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "y", "oui"}


DISCORD_TOKEN: str = os.getenv("DISCORD_TOKEN", "").strip()
DASHBOARD_PASSWORD: str = os.getenv("DASHBOARD_PASSWORD", "").strip()
SECRET_KEY: str = os.getenv("SECRET_KEY", "").strip() or secrets.token_hex(32)

# Mot de passe généré si aucun n'est fourni (affiché dans les logs au démarrage)
GENERATED_PASSWORD: str = "" if DASHBOARD_PASSWORD else secrets.token_urlsafe(9)

DATA_DIR: Path = Path(os.getenv("DATA_DIR", "data")).resolve()
DB_PATH: Path = DATA_DIR / "botsecret.sqlite3"

SESSION_MAX_AGE: int = int(os.getenv("SESSION_MAX_AGE", str(60 * 60 * 24 * 7)))
COOKIE_SECURE: bool = _env_bool("COOKIE_SECURE", False)

LOG_MAX_LINES: int = 500
