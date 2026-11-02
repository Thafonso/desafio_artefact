"""Central configuration.

Everything environment-dependent (keys, paths, reference date) is resolved
here, so the rest of the package never reads ``os.environ`` directly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
CONTEXT_DIR = ROOT / "context"

CSV_FILES = {
    "products": CONTEXT_DIR / "desafio_tecnico_ai_eng - products.csv",
    "categories": CONTEXT_DIR / "desafio_tecnico_ai_eng - categories.csv",
    "orders": CONTEXT_DIR / "desafio_tecnico_ai_eng - orders.csv",
    "order_items": CONTEXT_DIR / "desafio_tecnico_ai_eng - order_items.csv",
    "promotions": CONTEXT_DIR / "desafio_tecnico_ai_eng - promotions.csv",
}

POLICIES_FILE = CONTEXT_DIR / "políticas_da_loja.pdf"

# The day after the most recent order in the dataset. Rationale in .env.example.
DEFAULT_REFERENCE_DATE = date(2026, 3, 23)

DEFAULT_MODEL = "claude-haiku-5-5"


@dataclass(frozen=True)
class Config:
    model: str
    reference_date: date
    sessions_dir: Path

    @property
    def today(self) -> date:
        return self.reference_date


def _read_reference_date() -> date:
    raw = os.getenv("EMPORIO_DATA_REFERENCIA", "").strip()
    if not raw:
        return DEFAULT_REFERENCE_DATE
    if raw.lower() in {"hoje", "today", "real"}:
        return date.today()
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(
            f"EMPORIO_DATA_REFERENCIA inválida: {raw!r}. "
            "Use o formato AAAA-MM-DD ou 'hoje'."
        ) from exc


def load_config() -> Config:
    return Config(
        model=os.getenv("EMPORIO_MODEL", DEFAULT_MODEL),
        reference_date=_read_reference_date(),
        sessions_dir=ROOT / "sessions",
    )


CONFIG = load_config()
