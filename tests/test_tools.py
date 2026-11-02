"""Tests for the deterministic tools.

They are pure functions over the CSVs, so the behaviour can be locked down
without spending an LLM call. What is tested here are the manual's rules that
the model should not have to work out on its own.

Assertions match Portuguese strings because that is what the tools return to
the customer.
"""

from __future__ import annotations

import pytest

from emporio.data import load_catalog
from emporio.policies import load_policies
from emporio.tools import (
    active_promotions,
    lookup_order,
    payment_options,
    product_details,
    search_policies,
    search_products,
)


@pytest.fixture(scope="module")
def catalog():
    return load_catalog()


# --------------------------------------------------------------------- prices


def test_pix_gives_5_percent_off_list_price(catalog):
    takamine = catalog.product_by_id(95)  # no live promotion
    assert takamine["list_price"] == 2199.0
    assert takamine["pix_price"] == 2089.05
    assert takamine["pix_has_extra_discount"] is True


def test_pix_does_not_stack_with_promotion(catalog):
    """Section 6.2: the PIX discount does not apply on a promotional price."""
    ohana = catalog.product_by_id(121)  # 20% live
    assert ohana["discount_percent"] == 20
    assert ohana["final_price"] == 439.20
    assert ohana["pix_price"] == ohana["final_price"]
    assert ohana["pix_has_extra_discount"] is False


def test_expired_promotion_is_not_a_discount(catalog):
    """The Takamine GD20 carries a 12% promotion with is_active = 0."""
    assert catalog.product_by_id(95)["discount_percent"] == 0
    # same for the Tagima Woodstock's 30% Black Friday
    assert catalog.product_by_id(91)["discount_percent"] == 0


def test_only_four_promotions_are_live(catalog):
    live = {p["product_id"] for p in catalog.active_promotions()}
    assert live == {90, 94, 121, 127}


def test_active_promotions_never_names_a_closed_campaign():
    text = active_promotions.invoke({})
    assert "Black Friday" not in text


# ---------------------------------------------------------------------- search


def test_price_filter_uses_effective_value(catalog):
    """The Ohana lists at 549, but costs 439.20 with the live promotion."""
    under_500 = {p["product_id"] for p in catalog.search_products(max_price=500, limit=99)}
    assert 121 in under_500


def test_guitars_under_1000_are_all_available(catalog):
    found = catalog.search_products(category="Violões", max_price=1000, limit=99)
    assert found
    for product in found:
        assert product["category"] == "Violões"
        assert product["final_price"] <= 1000
        assert product["stock"] > 0
        assert product["availability"] == "disponível"


def test_search_by_name_finds_the_model():
    text = search_products.invoke({"term": "takamine gd20"})
    assert "Takamine GD20" in text
    assert "R$ 2.199,00" in text


def test_discontinued_is_out_of_the_default_search(catalog):
    """The Ibanez Bass 2X has 13 units in stock but was dropped from the line."""
    default = {p["product_id"] for p in catalog.search_products(limit=99)}
    assert 136 not in default

    record = product_details.invoke({"product_id": 136})
    assert "descontinuado" in record


def test_empty_search_tells_the_agent_what_to_do():
    text = search_products.invoke({"category": "Cordas Orquestrais"})
    assert "Nenhum produto" in text


# ---------------------------------------------------------------------- orders


def test_shipped_order_shows_tracking():
    text = lookup_order.invoke({"order_id": 8})
    assert "BRJL5544332BR" in text
    assert "enviado" in text
    assert "prazo de 7 dias" in text  # not delivered yet


def test_order_without_tracking_explains_why():
    text = lookup_order.invoke({"order_id": 13})
    assert "Sem código de rastreio" in text


def test_cancelled_order_gives_the_reason_and_no_deadline():
    text = lookup_order.invoke({"order_id": 18})
    assert "Item fora de estoque" in text
    assert "cancelado" in text.lower()


def test_delivered_order_past_the_withdrawal_window():
    """Order 7: delivered on 2026-02-17, reference date is 2026-03-23."""
    text = lookup_order.invoke({"order_id": 7})
    assert "FORA do prazo de arrependimento" in text
    # the 90-day legal warranty is still open, though
    assert "DENTRO da garantia legal" in text


def test_unknown_order_is_not_invented():
    text = lookup_order.invoke({"order_id": 999})
    assert "Não existe pedido" in text


# -------------------------------------------------------------------- payments


def test_minimum_instalment_caps_the_split():
    """R$900: 9x lands on exactly R$100; 10x would fall below the minimum."""
    text = payment_options.invoke({"total": 900.0})
    assert "9x de R$ 100,00" in text
    assert "10x" not in text


def test_free_shipping_above_500():
    assert "Frete grátis" in payment_options.invoke({"total": 600.0})
    assert "R$ 35,00" in payment_options.invoke({"total": 400.0})


def test_pix_suppressed_when_price_is_already_discounted():
    text = payment_options.invoke({"total": 439.20, "price_already_discounted": True})
    assert "não acumula" in text
    assert "-5%" not in text


def test_outside_metro_area_promises_no_amount():
    text = payment_options.invoke({"total": 1500.0, "metro_area_delivery": False})
    assert "calculado pelo CEP" in text
    assert "SEDEX" in text


# -------------------------------------------------------------------- policies


@pytest.mark.parametrize(
    ("question", "section"),
    [
        ("qual o endereço da loja", "1.2"),
        ("me arrependi da compra, posso devolver?", "4.1"),
        ("que horas vocês abrem no sábado", "2"),
        ("dá pra pagar com boleto?", "3"),
        ("chegou com defeito de fábrica", "4.2"),
        ("quanto tempo de garantia", "8.1"),
        ("o desconto do pix vale junto com a promoção?", "6.2"),
    ],
)
def test_relevant_policy_lands_in_top3(question, section):
    found = [s.number for s in load_policies().search(question, k=3)]
    assert section in found


def test_search_policies_returns_a_quotable_passage():
    text = search_policies.invoke({"question": "qual o endereço da loja"})
    assert "Rua 14 de Maio, 3200" in text
    assert "[1.2 Dados da Empresa]" in text
