"""Ferramentas do agente.

Cada ferramenta é determinística: lê os dados tratados ou o índice de políticas
e devolve texto pronto para o modelo citar. Nenhum preço, estoque ou prazo é
inventado pelo LLM — a seção 7.1 do manual é explícita sobre isso.

As docstrings são a descrição que o modelo lê para decidir quando chamar cada
ferramenta, então são escritas para ele, não para quem mantém o código.
"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import tool

from .dados import carregar_catalogo, dias_desde, hoje
from .politicas import carregar_politicas

FRETE_GRATIS_ACIMA_DE = 500.0
TAXA_FRETE_METROPOLITANA = 35.0

PRAZO_ARREPENDIMENTO = 7
PRAZO_TROCA_DEFEITO = 30
PRAZO_GARANTIA_LEGAL = 90


def _brl(valor: float) -> str:
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _linha_produto(p: dict[str, Any]) -> str:
    partes = [f"#{p['product_id']} {p['nome']} ({p['categoria']})"]

    if p["desconto_percent"]:
        partes.append(
            f"de {_brl(p['preco_tabela'])} por {_brl(p['preco_final'])} "
            f"(-{p['desconto_percent']}%, promoção '{p['promocao']}')"
        )
        partes.append("o desconto de PIX não acumula com promoção")
    else:
        partes.append(f"{_brl(p['preco_tabela'])}")
        partes.append(f"no PIX {_brl(p['preco_pix'])} (-5%)")

    partes.append(f"situação: {p['situacao']}, {p['estoque']} em estoque")
    return " | ".join(partes)


@tool
def buscar_produtos(
    termo: str | None = None,
    categoria: str | None = None,
    preco_min: float | None = None,
    preco_max: float | None = None,
    apenas_em_promocao: bool = False,
    incluir_indisponiveis: bool = False,
) -> str:
    """Busca instrumentos no catálogo da loja.

    Use sempre que o cliente perguntar o que a loja tem, pedir recomendação,
    filtrar por faixa de preço ou perguntar se um instrumento está disponível.

    Args:
        termo: palavras do nome ou da descrição (ex.: "takamine", "violão nylon").
        categoria: uma de Guitarras, Baixos, Baterias e Percussão, Teclados e
            Pianos, Violões, Instrumentos de Sopro (Madeiras), Instrumentos de
            Sopro (Metais), Cordas Orquestrais, Ukuleles.
        preco_min: preço mínimo em reais, já considerando promoção vigente.
        preco_max: preço máximo em reais, já considerando promoção vigente.
        apenas_em_promocao: True para trazer só itens com promoção vigente.
        incluir_indisponiveis: True para incluir itens sem estoque,
            descontinuados ou ainda não lançados.
    """
    catalogo = carregar_catalogo()
    resultados = catalogo.buscar_produtos(
        termo=termo,
        categoria=categoria,
        preco_min=preco_min,
        preco_max=preco_max,
        apenas_disponiveis=not incluir_indisponiveis,
        apenas_em_promocao=apenas_em_promocao,
    )

    if not resultados:
        return (
            "Nenhum produto no catálogo atende a esses filtros. "
            "Tente afrouxar o preço, outra categoria, ou use "
            "incluir_indisponiveis=True para ver itens sem estoque."
        )

    return "\n".join(_linha_produto(p) for p in resultados)


@tool
def detalhar_produto(product_id: int) -> str:
    """Mostra ficha completa de um produto: specs, estoque, preços e promoção.

    Use depois de `buscar_produtos`, quando o cliente quiser saber mais sobre um
    item específico (madeira do tampo, se tem captação, escala, cor).

    Args:
        product_id: o número que aparece como #N em `buscar_produtos`.
    """
    produto = carregar_catalogo().produto_por_id(product_id)
    if produto is None:
        return f"Não existe produto #{product_id} no catálogo."

    linhas = [_linha_produto(produto), f"Descrição: {produto['descricao']}"]
    if produto["specs"]:
        specs = ", ".join(f"{k}: {v}" for k, v in produto["specs"].items())
        linhas.append(f"Especificações: {specs}")
    return "\n".join(linhas)


@tool
def listar_categorias() -> str:
    """Lista as categorias da loja e quantos itens cada uma tem disponíveis agora.

    Use quando o cliente perguntar o que a loja vende, ou antes de afirmar que
    a loja não trabalha com algum tipo de instrumento.
    """
    linhas = []
    for c in carregar_catalogo().categorias_com_estoque():
        linhas.append(
            f"{c['categoria']}: {c['produtos_disponiveis']} disponíveis — {c['descricao']}"
        )
    return "\n".join(linhas)


@tool
def promocoes_ativas() -> str:
    """Lista as promoções vigentes hoje, com preço antigo e novo.

    Use quando o cliente perguntar por ofertas, descontos ou promoções. As
    promoções já encerradas não aparecem aqui e não devem ser oferecidas.
    """
    resultados = carregar_catalogo().promocoes_ativas()
    if not resultados:
        return "Não há nenhuma promoção vigente no momento."
    return "\n".join(_linha_produto(p) for p in resultados)


def _elegibilidade(pedido: dict[str, Any]) -> list[str]:
    """Traduz datas do pedido nas janelas de troca/devolução do manual."""
    if pedido["status_bruto"] == "cancelled":
        return ["Pedido cancelado — não há entrega nem prazo de devolução a contar."]

    if pedido["status_bruto"] != "delivered":
        return [
            "Pedido ainda não entregue: o prazo de 7 dias de arrependimento só "
            "começa a contar a partir do recebimento."
        ]

    # Não temos a data real de recebimento na base, só a previsão de entrega —
    # é a melhor aproximação disponível para contar os prazos.
    recebimento = pedido["previsao_entrega"]
    if not recebimento:
        return ["Pedido entregue, mas sem data de entrega registrada na base."]

    dias = dias_desde(recebimento)
    dias_compra = dias_desde(pedido["data_pedido"])
    linhas = [f"Entregue em {recebimento} — há {dias} dias (hoje: {hoje().isoformat()})."]

    if dias <= PRAZO_ARREPENDIMENTO:
        linhas.append(
            f"DENTRO do prazo de arrependimento ({PRAZO_ARREPENDIMENTO} dias "
            f"corridos): faltam {PRAZO_ARREPENDIMENTO - dias} dias."
        )
    else:
        linhas.append(
            f"FORA do prazo de arrependimento ({PRAZO_ARREPENDIMENTO} dias "
            f"corridos após o recebimento)."
        )

    if dias_compra <= PRAZO_TROCA_DEFEITO:
        linhas.append(
            f"DENTRO do prazo de troca por defeito de fabricação "
            f"({PRAZO_TROCA_DEFEITO} dias após a compra)."
        )
    else:
        linhas.append(
            f"FORA do prazo de troca por defeito ({PRAZO_TROCA_DEFEITO} dias "
            f"após a compra; a compra foi há {dias_compra} dias)."
        )

    if dias <= PRAZO_GARANTIA_LEGAL:
        linhas.append(
            f"DENTRO da garantia legal de {PRAZO_GARANTIA_LEGAL} dias contra "
            f"defeito de fabricação: faltam {PRAZO_GARANTIA_LEGAL - dias} dias."
        )
    else:
        linhas.append(f"FORA da garantia legal de {PRAZO_GARANTIA_LEGAL} dias.")

    return linhas


@tool
def consultar_pedido(order_id: int) -> str:
    """Consulta um pedido pelo número: status, itens, rastreio e prazos de troca.

    Use quando o cliente perguntar sobre um pedido, rastreamento, entrega,
    cancelamento, troca ou devolução. Se o cliente não informou o número do
    pedido, peça antes de chamar — não há como localizar por nome.

    A resposta inclui o cálculo de quais janelas de troca e devolução do manual
    ainda estão abertas para esse pedido.

    Args:
        order_id: número do pedido informado pelo cliente.
    """
    pedido = carregar_catalogo().pedido_por_id(order_id)
    if pedido is None:
        return (
            f"Não existe pedido #{order_id} na base. Confirme o número com o "
            "cliente (os pedidos vão de 1 a 20)."
        )

    itens = "; ".join(
        f"{i['quantidade']}x {i['nome']} (#{i['product_id']})" for i in pedido["itens"]
    )
    linhas = [
        f"Pedido #{pedido['order_id']} — {pedido['status']}",
        f"Feito em {pedido['data_pedido']} | total {_brl(pedido['total_brl'])} "
        f"| pagamento: {pedido['forma_pagamento']}",
        f"Itens: {itens}",
    ]
    if pedido["codigo_rastreio"]:
        linhas.append(
            f"Rastreio: {pedido['codigo_rastreio']} | previsão de entrega: "
            f"{pedido['previsao_entrega']}"
        )
    elif pedido["status_bruto"] in {"pending", "confirmed"}:
        linhas.append(
            "Sem código de rastreio: ele é gerado e enviado por e-mail e "
            "WhatsApp quando o pedido é despachado."
        )
    if pedido["observacao"]:
        linhas.append(f"Observação interna: {pedido['observacao']}")

    linhas.extend(_elegibilidade(pedido))
    return "\n".join(linhas)


@tool
def simular_pagamento(
    valor_total: float,
    preco_ja_promocional: bool = False,
    entrega_regiao_metropolitana: bool = True,
) -> str:
    """Calcula formas de pagamento, parcelas válidas e frete para um valor.

    Use quando o cliente perguntar "em quantas vezes posso parcelar", "quanto
    fica no PIX", "o frete é grátis?" — as regras de parcela mínima e de frete
    são aritméticas e precisam ser calculadas, não estimadas.

    Args:
        valor_total: valor da compra em reais.
        preco_ja_promocional: True se o valor já tem desconto de promoção —
            nesse caso o desconto de PIX não se aplica.
        entrega_regiao_metropolitana: True para Campo Grande e região, False
            para outras cidades.
    """
    linhas = [f"Valor da compra: {_brl(valor_total)}"]

    if preco_ja_promocional:
        linhas.append(
            "PIX: sem os 5% — o desconto de PIX não acumula com preço promocional."
        )
    else:
        linhas.append(f"PIX (-5%): {_brl(round(valor_total * 0.95, 2))}")

    linhas.append("Débito e boleto: à vista, sem desconto adicional.")

    validas = []
    for n in range(1, 13):
        parcela = valor_total / n
        if n <= 3:
            minimo = 50.0 if n > 1 else 0.0
        elif n <= 6:
            minimo = 80.0
        else:
            minimo = 100.0
        if parcela >= minimo:
            validas.append(f"{n}x de {_brl(round(parcela, 2))}")

    if validas:
        linhas.append("Crédito sem juros: " + "; ".join(validas) + ".")
        maior = len(validas)
        if maior < 12:
            linhas.append(
                f"Acima de {maior}x a parcela ficaria abaixo do mínimo permitido."
            )
    else:
        linhas.append("Crédito: valor baixo demais para parcelar.")

    if valor_total > 2000:
        linhas.append("Pode combinar formas de pagamento (ex.: PIX + cartão).")

    if entrega_regiao_metropolitana:
        if valor_total > FRETE_GRATIS_ACIMA_DE:
            linhas.append(
                "Frete grátis (pedido acima de "
                f"{_brl(FRETE_GRATIS_ACIMA_DE)} na região metropolitana), "
                "entrega em 1 a 3 dias úteis por motoboy próprio."
            )
        else:
            linhas.append(
                f"Frete: {_brl(TAXA_FRETE_METROPOLITANA)} (pedido abaixo de "
                f"{_brl(FRETE_GRATIS_ACIMA_DE)}), entrega em 1 a 3 dias úteis."
            )
    else:
        linhas.append(
            "Frete para fora da região metropolitana é calculado pelo CEP, peso "
            "e dimensões: PAC 5-12 dias úteis, SEDEX 2-5, Jadlog 3-8, todos com "
            "rastreio e seguro. Instrumentos grandes podem exigir cotação."
        )

    return "\n".join(linhas)


@tool
def consultar_politicas(pergunta: str) -> str:
    """Busca no manual de políticas da loja e devolve os trechos relevantes.

    Use para regras e informações gerais: horário de funcionamento, endereço e
    contato, formas de pagamento aceitas, trocas, devoluções, garantia, frete,
    privacidade, e o que a loja vende ou não vende.

    Args:
        pergunta: a dúvida do cliente, com as palavras dele.
    """
    secoes = carregar_politicas().buscar(pergunta, k=3)
    if not secoes:
        return (
            "Nada no manual responde a isso. Não invente a regra: diga que vai "
            "confirmar com a equipe."
        )
    return "\n\n".join(str(s) for s in secoes)


FERRAMENTAS = [
    buscar_produtos,
    detalhar_produto,
    listar_categorias,
    promocoes_ativas,
    consultar_pedido,
    simular_pagamento,
    consultar_politicas,
]
