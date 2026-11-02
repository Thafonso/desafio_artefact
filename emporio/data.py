"""Data layer: the store's CSVs, normalized and queryable.

The original CSVs stay untouched in ``context/``. Everything that needs
cleaning (price as a number, ``specs`` as JSON, category join, active
promotion) happens once at load time, so the agent's tools always work on
data that is already trustworthy.

User-facing values stay in Portuguese: they end up in the reply the customer
reads.
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

from .config import CONFIG, CSV_FILES

PIX_DISCOUNT = 0.05

AVAILABILITY_BY_STATUS = {
    "active": "disponível",
    "discontinued": "descontinuado",
    "coming_soon": "em breve",
}

ORDER_STATUS_PT = {
    "pending": "aguardando pagamento",
    "confirmed": "pagamento confirmado, em separação",
    "shipped": "enviado",
    "delivered": "entregue",
    "cancelled": "cancelado",
}

PAYMENT_METHOD_PT = {
    "pix": "PIX",
    "debit": "cartão de débito",
    "boleto": "boleto bancário",
    "credit_3x": "cartão de crédito em 3x",
    "credit_6x": "cartão de crédito em 6x",
    "credit_12x": "cartão de crédito em 12x",
}


def normalize(text: str) -> str:
    """Lowercase, accent-free and punctuation-free — for tolerant matching."""
    stripped = unicodedata.normalize("NFKD", str(text))
    stripped = "".join(c for c in stripped if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9\s]", " ", stripped.lower()).strip()


def _parse_specs(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


@dataclass(frozen=True)
class Catalog:
    products: pd.DataFrame
    categories: pd.DataFrame
    orders: pd.DataFrame
    order_items: pd.DataFrame
    promotions: pd.DataFrame

    # ----------------------------------------------------------------- pricing

    @staticmethod
    def prices(row: pd.Series) -> dict[str, Any]:
        """List, promotional and PIX price for one product.

        Manual, section 6.2: promotions do not stack, and the 5% PIX discount
        does **not** apply on top of an already discounted price.
        """
        list_price = float(row["price_brl"])
        discount = int(row["discount_percent"] or 0)

        if discount:
            final = round(list_price * (1 - discount / 100), 2)
            return {
                "list_price": list_price,
                "discount_percent": discount,
                "promotion": row["promotion"],
                "final_price": final,
                "pix_price": final,
                "pix_has_extra_discount": False,
            }

        return {
            "list_price": list_price,
            "discount_percent": 0,
            "promotion": None,
            "final_price": list_price,
            "pix_price": round(list_price * (1 - PIX_DISCOUNT), 2),
            "pix_has_extra_discount": True,
        }

    def product_to_dict(self, row: pd.Series) -> dict[str, Any]:
        product = {
            "product_id": int(row["product_id"]),
            "name": row["name"],
            "category": row["category"],
            "availability": row["availability"],
            "stock": int(row["stock_quantity"]),
            "description": row["description"],
            "specs": row["specs_dict"],
        }
        product.update(self.prices(row))
        return product

    # ----------------------------------------------------------------- queries

    def search_products(
        self,
        term: str | None = None,
        category: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        available_only: bool = True,
        on_sale_only: bool = False,
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        df = self.products

        if available_only:
            df = df[(df["status"] == "active") & (df["stock_quantity"] > 0)]

        if on_sale_only:
            df = df[df["discount_percent"] > 0]

        if category:
            target = normalize(category)
            df = df[df["category_norm"].str.contains(target, na=False)]

        if term:
            for word in (w for w in normalize(term).split() if len(w) > 1):
                df = df[df["searchable"].str.contains(re.escape(word), na=False)]

        # Filter on what the customer actually pays, not on the list price.
        effective_price = df["price_brl"] * (1 - df["discount_percent"] / 100)
        if min_price is not None:
            df = df[effective_price >= min_price]
        if max_price is not None:
            df = df[effective_price <= max_price]

        df = df.sort_values("price_brl")
        return [self.product_to_dict(row) for _, row in df.head(limit).iterrows()]

    def product_by_id(self, product_id: int) -> dict[str, Any] | None:
        df = self.products[self.products["product_id"] == int(product_id)]
        if df.empty:
            return None
        return self.product_to_dict(df.iloc[0])

    def active_promotions(self) -> list[dict[str, Any]]:
        df = self.products[self.products["discount_percent"] > 0]
        df = df.sort_values("discount_percent", ascending=False)
        return [self.product_to_dict(row) for _, row in df.iterrows()]

    def categories_with_stock(self) -> list[dict[str, Any]]:
        available = self.products[
            (self.products["status"] == "active") & (self.products["stock_quantity"] > 0)
        ]
        counts = available.groupby("category").size().to_dict()
        return [
            {
                "category": name,
                "description": description,
                "available_products": counts.get(name, 0),
            }
            for name, description in zip(
                self.categories["name"], self.categories["description"]
            )
        ]

    def order_by_id(self, order_id: int) -> dict[str, Any] | None:
        df = self.orders[self.orders["order_id"] == int(order_id)]
        if df.empty:
            return None
        order = df.iloc[0]

        rows = self.order_items[self.order_items["order_id"] == int(order_id)]
        items = []
        for _, item in rows.iterrows():
            product = self.product_by_id(item["product_id"])
            items.append(
                {
                    "product_id": int(item["product_id"]),
                    "name": product["name"] if product else "(produto não encontrado)",
                    "quantity": int(item["quantity"]),
                }
            )

        return {
            "order_id": int(order["order_id"]),
            "status": ORDER_STATUS_PT.get(order["status"], order["status"]),
            "raw_status": order["status"],
            "order_date": order["order_date"].date().isoformat(),
            "total_brl": float(order["total_brl"]),
            "payment_method": PAYMENT_METHOD_PT.get(
                order["payment_method"], order["payment_method"]
            ),
            "tracking_code": order["tracking_code"] or None,
            "estimated_delivery": (
                order["estimated_delivery"].date().isoformat()
                if pd.notna(order["estimated_delivery"])
                else None
            ),
            "note": order["notes"] or None,
            "items": items,
        }


def _load_products(promotions: pd.DataFrame) -> pd.DataFrame:
    products = pd.read_csv(CSV_FILES["products"], encoding="utf-8")
    categories = pd.read_csv(CSV_FILES["categories"], encoding="utf-8")

    products["price_brl"] = pd.to_numeric(products["price_brl"])
    products["stock_quantity"] = (
        pd.to_numeric(products["stock_quantity"]).fillna(0).astype(int)
    )
    products["name"] = products["name"].str.strip()
    products["specs_dict"] = products["specs"].map(_parse_specs)
    products["availability"] = products.apply(
        lambda row: "sem estoque"
        if row["status"] == "active" and row["stock_quantity"] == 0
        else AVAILABILITY_BY_STATUS.get(row["status"], row["status"]),
        axis=1,
    )

    products = products.merge(
        categories[["category_id", "name"]].rename(columns={"name": "category"}),
        on="category_id",
        how="left",
    )

    # Only live promotions reach the catalog. An expired one is treated as
    # non-existent — section 7.3 forbids promising a discount that lapsed.
    live = promotions[promotions["is_active"] == 1]
    best = (
        live.sort_values("discount_percent", ascending=False)
        .groupby("product_id")
        .first()
        .reset_index()[["product_id", "discount_percent", "description"]]
        .rename(columns={"description": "promotion"})
    )
    products = products.merge(best, on="product_id", how="left")
    products["discount_percent"] = products["discount_percent"].fillna(0).astype(int)
    products["promotion"] = products["promotion"].where(
        products["promotion"].notna(), None
    )

    products["category_norm"] = products["category"].map(normalize)
    products["searchable"] = (
        products["name"].map(normalize)
        + " "
        + products["description"].map(normalize)
        + " "
        + products["category_norm"]
    )
    return products


@lru_cache(maxsize=1)
def load_catalog() -> Catalog:
    promotions = pd.read_csv(CSV_FILES["promotions"], encoding="utf-8")
    products = _load_products(promotions)

    orders = pd.read_csv(CSV_FILES["orders"], encoding="utf-8")
    orders["order_date"] = pd.to_datetime(orders["order_date"])
    orders["estimated_delivery"] = pd.to_datetime(
        orders["estimated_delivery"], errors="coerce"
    )
    orders["total_brl"] = pd.to_numeric(orders["total_brl"])
    for column in ("tracking_code", "notes"):
        orders[column] = orders[column].fillna("").str.strip()

    return Catalog(
        products=products,
        categories=pd.read_csv(CSV_FILES["categories"], encoding="utf-8"),
        orders=orders,
        order_items=pd.read_csv(CSV_FILES["order_items"], encoding="utf-8"),
        promotions=promotions,
    )


def today() -> date:
    """The agent's "today" — configurable, see ``config.py``."""
    return CONFIG.reference_date


def days_since(value: str | date | datetime | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = date.fromisoformat(value)
    if isinstance(value, datetime):
        value = value.date()
    return (today() - value).days
