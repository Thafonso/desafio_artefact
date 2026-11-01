"""Camada de dados: CSVs da loja normalizados e consultáveis.

Os CSVs originais ficam intactos em ``context/``. Tudo que precisa de tratamento
(preço como número, ``specs`` em JSON, join de categoria, promoção vigente)
acontece uma única vez no carregamento, para que as ferramentas do agente
trabalhem sobre dados já confiáveis.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache
from typing import Any

import pandas as pd

from .config import ARQUIVOS_CSV, CONFIG

DESCONTO_PIX = 0.05

SITUACAO_POR_STATUS = {
    "active": "disponível",
    "discontinued": "descontinuado",
    "coming_soon": "em breve",
}

STATUS_PEDIDO_PT = {
    "pending": "aguardando pagamento",
    "confirmed": "pagamento confirmado, em separação",
    "shipped": "enviado",
    "delivered": "entregue",
    "cancelled": "cancelado",
}

PAGAMENTO_PT = {
    "pix": "PIX",
    "debit": "cartão de débito",
    "boleto": "boleto bancário",
    "credit_3x": "cartão de crédito em 3x",
    "credit_6x": "cartão de crédito em 6x",
    "credit_12x": "cartão de crédito em 12x",
}


def normalizar(texto: str) -> str:
    """Minúsculas, sem acento e sem pontuação — para busca tolerante."""
    sem_acento = unicodedata.normalize("NFKD", str(texto))
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9\s]", " ", sem_acento.lower()).strip()


def _parse_specs(bruto: Any) -> dict[str, Any]:
    if not isinstance(bruto, str) or not bruto.strip():
        return {}
    try:
        return json.loads(bruto)
    except json.JSONDecodeError:
        return {}


@dataclass(frozen=True)
class Catalogo:
    produtos: pd.DataFrame
    categorias: pd.DataFrame
    pedidos: pd.DataFrame
    itens_pedido: pd.DataFrame
    promocoes: pd.DataFrame

    # ------------------------------------------------------------------ preço

    @staticmethod
    def precos(linha: pd.Series) -> dict[str, Any]:
        """Preço de tabela, promocional e no PIX para um produto.

        Regra da seção 6.2 do manual: promoções não são cumulativas e o desconto
        de PIX (5%) **não** incide sobre preço já promocional.
        """
        tabela = float(linha["price_brl"])
        desconto = int(linha["desconto_percent"] or 0)

        if desconto:
            final = round(tabela * (1 - desconto / 100), 2)
            return {
                "preco_tabela": tabela,
                "desconto_percent": desconto,
                "promocao": linha["promocao"],
                "preco_final": final,
                "preco_pix": final,
                "pix_tem_desconto_extra": False,
            }

        return {
            "preco_tabela": tabela,
            "desconto_percent": 0,
            "promocao": None,
            "preco_final": tabela,
            "preco_pix": round(tabela * (1 - DESCONTO_PIX), 2),
            "pix_tem_desconto_extra": True,
        }

    def produto_para_dict(self, linha: pd.Series) -> dict[str, Any]:
        dados = {
            "product_id": int(linha["product_id"]),
            "nome": linha["name"],
            "categoria": linha["categoria"],
            "situacao": linha["situacao"],
            "estoque": int(linha["stock_quantity"]),
            "descricao": linha["description"],
            "specs": linha["specs_dict"],
        }
        dados.update(self.precos(linha))
        return dados

    # ---------------------------------------------------------------- consulta

    def buscar_produtos(
        self,
        termo: str | None = None,
        categoria: str | None = None,
        preco_min: float | None = None,
        preco_max: float | None = None,
        apenas_disponiveis: bool = True,
        apenas_em_promocao: bool = False,
        limite: int = 8,
    ) -> list[dict[str, Any]]:
        df = self.produtos

        if apenas_disponiveis:
            df = df[(df["status"] == "active") & (df["stock_quantity"] > 0)]

        if apenas_em_promocao:
            df = df[df["desconto_percent"] > 0]

        if categoria:
            alvo = normalizar(categoria)
            df = df[df["categoria_norm"].str.contains(alvo, na=False)]

        if termo:
            palavras = [p for p in normalizar(termo).split() if len(p) > 1]
            for palavra in palavras:
                df = df[df["busca"].str.contains(re.escape(palavra), na=False)]

        # Filtra pelo preço que o cliente de fato paga, não pelo de tabela.
        preco_efetivo = df["price_brl"] * (1 - df["desconto_percent"] / 100)
        if preco_min is not None:
            df = df[preco_efetivo >= preco_min]
        if preco_max is not None:
            df = df[preco_efetivo <= preco_max]

        df = df.sort_values("price_brl")
        return [self.produto_para_dict(linha) for _, linha in df.head(limite).iterrows()]

    def produto_por_id(self, product_id: int) -> dict[str, Any] | None:
        df = self.produtos[self.produtos["product_id"] == int(product_id)]
        if df.empty:
            return None
        return self.produto_para_dict(df.iloc[0])

    def promocoes_ativas(self) -> list[dict[str, Any]]:
        df = self.produtos[self.produtos["desconto_percent"] > 0]
        df = df.sort_values("desconto_percent", ascending=False)
        return [self.produto_para_dict(linha) for _, linha in df.iterrows()]

    def categorias_com_estoque(self) -> list[dict[str, Any]]:
        disponiveis = self.produtos[
            (self.produtos["status"] == "active") & (self.produtos["stock_quantity"] > 0)
        ]
        contagem = disponiveis.groupby("categoria").size().to_dict()
        return [
            {
                "categoria": nome,
                "descricao": desc,
                "produtos_disponiveis": contagem.get(nome, 0),
            }
            for nome, desc in zip(self.categorias["name"], self.categorias["description"])
        ]

    def pedido_por_id(self, order_id: int) -> dict[str, Any] | None:
        df = self.pedidos[self.pedidos["order_id"] == int(order_id)]
        if df.empty:
            return None
        pedido = df.iloc[0]

        itens = self.itens_pedido[self.itens_pedido["order_id"] == int(order_id)]
        detalhe_itens = []
        for _, item in itens.iterrows():
            produto = self.produto_por_id(item["product_id"])
            detalhe_itens.append(
                {
                    "product_id": int(item["product_id"]),
                    "nome": produto["nome"] if produto else "(produto não encontrado)",
                    "quantidade": int(item["quantity"]),
                }
            )

        return {
            "order_id": int(pedido["order_id"]),
            "status": STATUS_PEDIDO_PT.get(pedido["status"], pedido["status"]),
            "status_bruto": pedido["status"],
            "data_pedido": pedido["order_date"].date().isoformat(),
            "total_brl": float(pedido["total_brl"]),
            "forma_pagamento": PAGAMENTO_PT.get(
                pedido["payment_method"], pedido["payment_method"]
            ),
            "codigo_rastreio": pedido["tracking_code"] or None,
            "previsao_entrega": (
                pedido["estimated_delivery"].date().isoformat()
                if pd.notna(pedido["estimated_delivery"])
                else None
            ),
            "observacao": pedido["notes"] or None,
            "itens": detalhe_itens,
        }


def _carregar_produtos(promocoes: pd.DataFrame) -> pd.DataFrame:
    produtos = pd.read_csv(ARQUIVOS_CSV["produtos"], encoding="utf-8")
    categorias = pd.read_csv(ARQUIVOS_CSV["categorias"], encoding="utf-8")

    produtos["price_brl"] = pd.to_numeric(produtos["price_brl"])
    produtos["stock_quantity"] = pd.to_numeric(produtos["stock_quantity"]).fillna(0).astype(int)
    produtos["name"] = produtos["name"].str.strip()
    produtos["specs_dict"] = produtos["specs"].map(_parse_specs)
    produtos["situacao"] = produtos.apply(
        lambda l: "sem estoque"
        if l["status"] == "active" and l["stock_quantity"] == 0
        else SITUACAO_POR_STATUS.get(l["status"], l["status"]),
        axis=1,
    )

    produtos = produtos.merge(
        categorias[["category_id", "name"]].rename(columns={"name": "categoria"}),
        on="category_id",
        how="left",
    )

    # Só promoções vigentes entram no catálogo. Promoção vencida é tratada como
    # inexistente — o manual (7.3) proíbe prometer desconto fora de vigência.
    vigentes = promocoes[promocoes["is_active"] == 1]
    melhor = (
        vigentes.sort_values("discount_percent", ascending=False)
        .groupby("product_id")
        .first()
        .reset_index()[["product_id", "discount_percent", "description"]]
        .rename(columns={"discount_percent": "desconto_percent", "description": "promocao"})
    )
    produtos = produtos.merge(melhor, on="product_id", how="left")
    produtos["desconto_percent"] = produtos["desconto_percent"].fillna(0).astype(int)
    produtos["promocao"] = produtos["promocao"].where(produtos["promocao"].notna(), None)

    produtos["categoria_norm"] = produtos["categoria"].map(normalizar)
    produtos["busca"] = (
        produtos["name"].map(normalizar)
        + " "
        + produtos["description"].map(normalizar)
        + " "
        + produtos["categoria_norm"]
    )
    return produtos


@lru_cache(maxsize=1)
def carregar_catalogo() -> Catalogo:
    promocoes = pd.read_csv(ARQUIVOS_CSV["promocoes"], encoding="utf-8")
    produtos = _carregar_produtos(promocoes)

    pedidos = pd.read_csv(ARQUIVOS_CSV["pedidos"], encoding="utf-8")
    pedidos["order_date"] = pd.to_datetime(pedidos["order_date"])
    pedidos["estimated_delivery"] = pd.to_datetime(
        pedidos["estimated_delivery"], errors="coerce"
    )
    pedidos["total_brl"] = pd.to_numeric(pedidos["total_brl"])
    for coluna in ("tracking_code", "notes"):
        pedidos[coluna] = pedidos[coluna].fillna("").str.strip()

    return Catalogo(
        produtos=produtos,
        categorias=pd.read_csv(ARQUIVOS_CSV["categorias"], encoding="utf-8"),
        pedidos=pedidos,
        itens_pedido=pd.read_csv(ARQUIVOS_CSV["itens_pedido"], encoding="utf-8"),
        promocoes=promocoes,
    )


def hoje() -> date:
    """O 'hoje' do agente — configurável, ver ``config.py``."""
    return CONFIG.data_referencia


def dias_desde(valor: str | date | datetime | None) -> int | None:
    if valor is None:
        return None
    if isinstance(valor, str):
        valor = date.fromisoformat(valor)
    if isinstance(valor, datetime):
        valor = valor.date()
    return (hoje() - valor).days
