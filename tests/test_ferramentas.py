"""Testes das ferramentas determinísticas.

São funções puras sobre os CSVs, então dá para travar o comportamento sem
gastar uma chamada de LLM. O que se testa aqui são as regras do manual que o
modelo não deve ter que deduzir sozinho.
"""

from __future__ import annotations

import pytest

from emporio.dados import carregar_catalogo
from emporio.ferramentas import (
    buscar_produtos,
    consultar_pedido,
    consultar_politicas,
    detalhar_produto,
    promocoes_ativas,
    simular_pagamento,
)
from emporio.politicas import carregar_politicas


@pytest.fixture(scope="module")
def catalogo():
    return carregar_catalogo()


# --------------------------------------------------------------------- preços


def test_pix_da_5_porcento_em_preco_de_tabela(catalogo):
    takamine = catalogo.produto_por_id(95)  # sem promoção vigente
    assert takamine["preco_tabela"] == 2199.0
    assert takamine["preco_pix"] == 2089.05
    assert takamine["pix_tem_desconto_extra"] is True


def test_pix_nao_acumula_com_promocao(catalogo):
    """Seção 6.2: o desconto de PIX não incide sobre preço já promocional."""
    ohana = catalogo.produto_por_id(121)  # 20% vigente
    assert ohana["desconto_percent"] == 20
    assert ohana["preco_final"] == 439.20
    assert ohana["preco_pix"] == ohana["preco_final"]
    assert ohana["pix_tem_desconto_extra"] is False


def test_promocao_vencida_nao_vira_desconto(catalogo):
    """O Takamine GD20 tem promoção de 12% com is_active = 0."""
    assert catalogo.produto_por_id(95)["desconto_percent"] == 0
    # idem para a Black Friday de 30% do Tagima Woodstock
    assert catalogo.produto_por_id(91)["desconto_percent"] == 0


def test_apenas_quatro_promocoes_vigentes(catalogo):
    vigentes = {p["product_id"] for p in catalogo.promocoes_ativas()}
    assert vigentes == {90, 94, 121, 127}


def test_promocoes_ativas_nao_cita_campanha_encerrada():
    texto = promocoes_ativas.invoke({})
    assert "Black Friday" not in texto


# --------------------------------------------------------------------- busca


def test_filtro_de_preco_usa_valor_efetivo(catalogo):
    """O Ohana custa 549 de tabela, mas 439,20 com a promoção vigente."""
    ate_500 = {p["product_id"] for p in catalogo.buscar_produtos(preco_max=500, limite=99)}
    assert 121 in ate_500


def test_violoes_ate_mil_so_traz_disponiveis(catalogo):
    achados = catalogo.buscar_produtos(categoria="Violões", preco_max=1000, limite=99)
    assert achados
    for p in achados:
        assert p["categoria"] == "Violões"
        assert p["preco_final"] <= 1000
        assert p["estoque"] > 0
        assert p["situacao"] == "disponível"


def test_busca_por_nome_encontra_o_modelo():
    texto = buscar_produtos.invoke({"termo": "takamine gd20"})
    assert "Takamine GD20" in texto
    assert "R$ 2.199,00" in texto


def test_descontinuado_fica_fora_da_busca_padrao(catalogo):
    """O Ibanez Bass 2X tem 13 unidades, mas saiu de linha."""
    padrao = {p["product_id"] for p in catalogo.buscar_produtos(limite=99)}
    assert 136 not in padrao

    ficha = detalhar_produto.invoke({"product_id": 136})
    assert "descontinuado" in ficha


def test_busca_sem_resultado_orienta_o_agente():
    texto = buscar_produtos.invoke({"categoria": "Cordas Orquestrais"})
    assert "Nenhum produto" in texto


# -------------------------------------------------------------------- pedidos


def test_pedido_enviado_mostra_rastreio():
    texto = consultar_pedido.invoke({"order_id": 8})
    assert "BRJL5544332BR" in texto
    assert "enviado" in texto
    assert "prazo de 7 dias" in texto  # ainda não entregue


def test_pedido_sem_rastreio_explica_o_motivo():
    texto = consultar_pedido.invoke({"order_id": 13})
    assert "Sem código de rastreio" in texto


def test_pedido_cancelado_traz_o_motivo_e_nao_fala_de_prazo():
    texto = consultar_pedido.invoke({"order_id": 18})
    assert "Item fora de estoque" in texto
    assert "cancelado" in texto.lower()


def test_pedido_entregue_fora_do_prazo_de_arrependimento():
    """Pedido 7: entregue em 2026-02-17, hoje é 2026-03-23."""
    texto = consultar_pedido.invoke({"order_id": 7})
    assert "FORA do prazo de arrependimento" in texto
    # mas a garantia legal de 90 dias ainda está de pé
    assert "DENTRO da garantia legal" in texto


def test_pedido_inexistente_nao_inventa():
    texto = consultar_pedido.invoke({"order_id": 999})
    assert "Não existe pedido" in texto


# ---------------------------------------------------------------- pagamentos


def test_parcela_minima_de_cem_reais_limita_o_parcelamento():
    """R$ 900: 9x daria R$ 100 exatos; 10x cairia abaixo do mínimo."""
    texto = simular_pagamento.invoke({"valor_total": 900.0})
    assert "9x de R$ 100,00" in texto
    assert "10x" not in texto


def test_frete_gratis_acima_de_quinhentos():
    assert "Frete grátis" in simular_pagamento.invoke({"valor_total": 600.0})
    assert "R$ 35,00" in simular_pagamento.invoke({"valor_total": 400.0})


def test_pix_suprimido_quando_preco_ja_e_promocional():
    texto = simular_pagamento.invoke(
        {"valor_total": 439.20, "preco_ja_promocional": True}
    )
    assert "não acumula" in texto
    assert "-5%" not in texto


def test_fora_da_regiao_metropolitana_nao_promete_valor():
    texto = simular_pagamento.invoke(
        {"valor_total": 1500.0, "entrega_regiao_metropolitana": False}
    )
    assert "calculado pelo CEP" in texto
    assert "SEDEX" in texto


# ---------------------------------------------------------------- políticas


@pytest.mark.parametrize(
    ("pergunta", "secao"),
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
def test_politica_relevante_aparece_no_top3(pergunta, secao):
    achadas = [s.numero for s in carregar_politicas().buscar(pergunta, k=3)]
    assert secao in achadas


def test_consultar_politicas_devolve_trecho_citavel():
    texto = consultar_politicas.invoke({"pergunta": "qual o endereço da loja"})
    assert "Rua 14 de Maio, 3200" in texto
    assert "[1.2 Dados da Empresa]" in texto
