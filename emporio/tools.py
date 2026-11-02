"""The agent's tools.

Each tool is deterministic: it reads the cleaned data or the policy index and
returns text the model can quote. No price, stock level or deadline is ever
invented by the LLM — section 7.1 of the manual is explicit about that.

Docstrings are the descriptions the model reads to decide which tool to call,
so they are written for it, not for whoever maintains the code. The returned
strings stay in Portuguese: they end up in the reply the customer reads.
"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import tool

from .data import days_since, load_catalog, today
from .policies import load_policies

FREE_SHIPPING_ABOVE = 500.0
METRO_SHIPPING_FEE = 35.0

WITHDRAWAL_WINDOW_DAYS = 7
DEFECT_EXCHANGE_WINDOW_DAYS = 30
LEGAL_WARRANTY_DAYS = 90


def _brl(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _product_line(product: dict[str, Any]) -> str:
    parts = [f"#{product['product_id']} {product['name']} ({product['category']})"]

    if product["discount_percent"]:
        parts.append(
            f"de {_brl(product['list_price'])} por {_brl(product['final_price'])} "
            f"(-{product['discount_percent']}%, promoção '{product['promotion']}')"
        )
        parts.append("o desconto de PIX não acumula com promoção")
    else:
        parts.append(f"{_brl(product['list_price'])}")
        parts.append(f"no PIX {_brl(product['pix_price'])} (-5%)")

    parts.append(f"situação: {product['availability']}, {product['stock']} em estoque")
    return " | ".join(parts)


@tool
def search_products(
    term: str | None = None,
    category: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    on_sale_only: bool = False,
    include_unavailable: bool = False,
) -> str:
    """Search instruments in the store catalog.

    Use this whenever the customer asks what the store has, asks for a
    recommendation, gives a price range, or asks whether an instrument is in
    stock.

    Args:
        term: words from the name or description (e.g. "takamine",
            "violão nylon").
        category: one of Guitarras, Baixos, Baterias e Percussão, Teclados e
            Pianos, Violões, Instrumentos de Sopro (Madeiras), Instrumentos de
            Sopro (Metais), Cordas Orquestrais, Ukuleles.
        min_price: minimum price in BRL, already accounting for a live promotion.
        max_price: maximum price in BRL, already accounting for a live promotion.
        on_sale_only: True to return only items with a live promotion.
        include_unavailable: True to also include out-of-stock, discontinued
            or not-yet-released items.
    """
    catalog = load_catalog()
    results = catalog.search_products(
        term=term,
        category=category,
        min_price=min_price,
        max_price=max_price,
        available_only=not include_unavailable,
        on_sale_only=on_sale_only,
    )

    if not results:
        return (
            "Nenhum produto no catálogo atende a esses filtros. "
            "Tente afrouxar o preço, outra categoria, ou use "
            "include_unavailable=True para ver itens sem estoque."
        )

    return "\n".join(_product_line(p) for p in results)


@tool
def product_details(product_id: int) -> str:
    """Show a product's full record: specs, stock, prices and promotion.

    Use after `search_products`, when the customer wants to know more about one
    specific item (top wood, pickup, scale length, colour).

    Args:
        product_id: the number shown as #N by `search_products`.
    """
    product = load_catalog().product_by_id(product_id)
    if product is None:
        return f"Não existe produto #{product_id} no catálogo."

    lines = [_product_line(product), f"Descrição: {product['description']}"]
    if product["specs"]:
        specs = ", ".join(f"{k}: {v}" for k, v in product["specs"].items())
        lines.append(f"Especificações: {specs}")
    return "\n".join(lines)


@tool
def list_categories() -> str:
    """List the store's categories and how many items each has in stock now.

    Use when the customer asks what the store sells, or before claiming the
    store does not carry some kind of instrument.
    """
    lines = []
    for c in load_catalog().categories_with_stock():
        lines.append(
            f"{c['category']}: {c['available_products']} disponíveis — {c['description']}"
        )
    return "\n".join(lines)


@tool
def active_promotions() -> str:
    """List the promotions live today, with old and new price.

    Use when the customer asks about offers, discounts or sales. Promotions
    that already ended do not appear here and must not be offered.
    """
    results = load_catalog().active_promotions()
    if not results:
        return "Não há nenhuma promoção vigente no momento."
    return "\n".join(_product_line(p) for p in results)


def _eligibility(order: dict[str, Any]) -> list[str]:
    """Turn the order's dates into the manual's exchange/return windows."""
    if order["raw_status"] == "cancelled":
        return ["Pedido cancelado — não há entrega nem prazo de devolução a contar."]

    if order["raw_status"] != "delivered":
        return [
            "Pedido ainda não entregue: o prazo de 7 dias de arrependimento só "
            "começa a contar a partir do recebimento."
        ]

    # The dataset has no real delivery date, only the estimate — it is the
    # best approximation available for counting the windows.
    received_on = order["estimated_delivery"]
    if not received_on:
        return ["Pedido entregue, mas sem data de entrega registrada na base."]

    days = days_since(received_on)
    days_since_purchase = days_since(order["order_date"])
    lines = [f"Entregue em {received_on} — há {days} dias (hoje: {today().isoformat()})."]

    if days <= WITHDRAWAL_WINDOW_DAYS:
        lines.append(
            f"DENTRO do prazo de arrependimento ({WITHDRAWAL_WINDOW_DAYS} dias "
            f"corridos): faltam {WITHDRAWAL_WINDOW_DAYS - days} dias."
        )
    else:
        lines.append(
            f"FORA do prazo de arrependimento ({WITHDRAWAL_WINDOW_DAYS} dias "
            f"corridos após o recebimento)."
        )

    if days_since_purchase <= DEFECT_EXCHANGE_WINDOW_DAYS:
        lines.append(
            f"DENTRO do prazo de troca por defeito de fabricação "
            f"({DEFECT_EXCHANGE_WINDOW_DAYS} dias após a compra)."
        )
    else:
        lines.append(
            f"FORA do prazo de troca por defeito ({DEFECT_EXCHANGE_WINDOW_DAYS} "
            f"dias após a compra; a compra foi há {days_since_purchase} dias)."
        )

    if days <= LEGAL_WARRANTY_DAYS:
        lines.append(
            f"DENTRO da garantia legal de {LEGAL_WARRANTY_DAYS} dias contra "
            f"defeito de fabricação: faltam {LEGAL_WARRANTY_DAYS - days} dias."
        )
    else:
        lines.append(f"FORA da garantia legal de {LEGAL_WARRANTY_DAYS} dias.")

    return lines


@tool
def lookup_order(order_id: int) -> str:
    """Look up an order by number: status, items, tracking and exchange windows.

    Use when the customer asks about an order, tracking, delivery,
    cancellation, exchange or return. If the customer has not given the order
    number, ask for it before calling — there is no way to find an order by
    name.

    The answer includes which of the manual's exchange and return windows are
    still open for that order.

    Args:
        order_id: the order number the customer gave.
    """
    order = load_catalog().order_by_id(order_id)
    if order is None:
        return (
            f"Não existe pedido #{order_id} na base. Confirme o número com o "
            "cliente (os pedidos vão de 1 a 20)."
        )

    items = "; ".join(
        f"{i['quantity']}x {i['name']} (#{i['product_id']})" for i in order["items"]
    )
    lines = [
        f"Pedido #{order['order_id']} — {order['status']}",
        f"Feito em {order['order_date']} | total {_brl(order['total_brl'])} "
        f"| pagamento: {order['payment_method']}",
        f"Itens: {items}",
    ]
    if order["tracking_code"]:
        lines.append(
            f"Rastreio: {order['tracking_code']} | previsão de entrega: "
            f"{order['estimated_delivery']}"
        )
    elif order["raw_status"] in {"pending", "confirmed"}:
        lines.append(
            "Sem código de rastreio: ele é gerado e enviado por e-mail e "
            "WhatsApp quando o pedido é despachado."
        )
    if order["note"]:
        lines.append(f"Observação interna: {order['note']}")

    lines.extend(_eligibility(order))
    return "\n".join(lines)


@tool
def payment_options(
    total: float,
    price_already_discounted: bool = False,
    metro_area_delivery: bool = True,
) -> str:
    """Work out payment methods, valid instalments and shipping for an amount.

    Use when the customer asks "how many instalments can I split this into",
    "how much is it with PIX", "is shipping free?" — the minimum-instalment and
    shipping rules are arithmetic and must be computed, not estimated.

    Args:
        total: purchase amount in BRL.
        price_already_discounted: True if the amount already carries a
            promotional discount — the PIX discount then does not apply.
        metro_area_delivery: True for Campo Grande and its metro area, False
            for other cities.
    """
    lines = [f"Valor da compra: {_brl(total)}"]

    if price_already_discounted:
        lines.append(
            "PIX: sem os 5% — o desconto de PIX não acumula com preço promocional."
        )
    else:
        lines.append(f"PIX (-5%): {_brl(round(total * 0.95, 2))}")

    lines.append("Débito e boleto: à vista, sem desconto adicional.")

    valid = []
    for n in range(1, 13):
        instalment = total / n
        if n <= 3:
            minimum = 50.0 if n > 1 else 0.0
        elif n <= 6:
            minimum = 80.0
        else:
            minimum = 100.0
        if instalment >= minimum:
            valid.append(f"{n}x de {_brl(round(instalment, 2))}")

    if valid:
        lines.append("Crédito sem juros: " + "; ".join(valid) + ".")
        if len(valid) < 12:
            lines.append(
                f"Acima de {len(valid)}x a parcela ficaria abaixo do mínimo permitido."
            )
    else:
        lines.append("Crédito: valor baixo demais para parcelar.")

    if total > 2000:
        lines.append("Pode combinar formas de pagamento (ex.: PIX + cartão).")

    if metro_area_delivery:
        if total > FREE_SHIPPING_ABOVE:
            lines.append(
                "Frete grátis (pedido acima de "
                f"{_brl(FREE_SHIPPING_ABOVE)} na região metropolitana), "
                "entrega em 1 a 3 dias úteis por motoboy próprio."
            )
        else:
            lines.append(
                f"Frete: {_brl(METRO_SHIPPING_FEE)} (pedido abaixo de "
                f"{_brl(FREE_SHIPPING_ABOVE)}), entrega em 1 a 3 dias úteis."
            )
    else:
        lines.append(
            "Frete para fora da região metropolitana é calculado pelo CEP, peso "
            "e dimensões: PAC 5-12 dias úteis, SEDEX 2-5, Jadlog 3-8, todos com "
            "rastreio e seguro. Instrumentos grandes podem exigir cotação."
        )

    return "\n".join(lines)


@tool
def search_policies(question: str) -> str:
    """Search the store's policy manual and return the relevant passages.

    Use for rules and general information: opening hours, address and contact,
    accepted payment methods, exchanges, returns, warranty, shipping, privacy,
    and what the store does or does not sell.

    Args:
        question: the customer's doubt, in their own words.
    """
    sections = load_policies().search(question, k=3)
    if not sections:
        return (
            "Nada no manual responde a isso. Não invente a regra: diga que vai "
            "confirmar com a equipe."
        )
    return "\n\n".join(str(s) for s in sections)


TOOLS = [
    search_products,
    product_details,
    list_categories,
    active_promotions,
    lookup_order,
    payment_options,
    search_policies,
]
