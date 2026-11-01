"""Configuração central do agente.

Tudo que depende do ambiente (chaves, caminhos, data de referência) é resolvido
aqui, para que os demais módulos não leiam ``os.environ`` espalhado pelo código.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

RAIZ = Path(__file__).resolve().parent.parent
CONTEXTO = RAIZ / "context"

ARQUIVOS_CSV = {
    "produtos": CONTEXTO / "desafio_tecnico_ai_eng - products.csv",
    "categorias": CONTEXTO / "desafio_tecnico_ai_eng - categories.csv",
    "pedidos": CONTEXTO / "desafio_tecnico_ai_eng - orders.csv",
    "itens_pedido": CONTEXTO / "desafio_tecnico_ai_eng - order_items.csv",
    "promocoes": CONTEXTO / "desafio_tecnico_ai_eng - promotions.csv",
}

ARQUIVO_POLITICAS = CONTEXTO / "políticas_da_loja.pdf"

# Dia seguinte ao último pedido da base. Ver justificativa em .env.example.
DATA_REFERENCIA_PADRAO = date(2026, 3, 23)

MODELO_PADRAO = "claude-haiku-5-5"


@dataclass(frozen=True)
class Config:
    modelo: str
    data_referencia: date
    diretorio_sessoes: Path

    @property
    def hoje(self) -> date:
        return self.data_referencia


def _ler_data_referencia() -> date:
    bruto = os.getenv("EMPORIO_DATA_REFERENCIA", "").strip()
    if not bruto:
        return DATA_REFERENCIA_PADRAO
    if bruto.lower() in {"hoje", "today", "real"}:
        return date.today()
    try:
        return date.fromisoformat(bruto)
    except ValueError as exc:
        raise ValueError(
            f"EMPORIO_DATA_REFERENCIA inválida: {bruto!r}. "
            "Use o formato AAAA-MM-DD ou 'hoje'."
        ) from exc


def carregar_config() -> Config:
    return Config(
        modelo=os.getenv("EMPORIO_MODEL", MODELO_PADRAO),
        data_referencia=_ler_data_referencia(),
        diretorio_sessoes=RAIZ / "sessions",
    )


CONFIG = carregar_config()
