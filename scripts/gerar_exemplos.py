"""Roda conversas roteirizadas e grava os exemplos de interação em examples/.

    python scripts/gerar_exemplos.py            # todos os roteiros
    python scripts/gerar_exemplos.py 3 4        # só os roteiros 3 e 4

As conversas vão para o repositório como entregável, então o que é gravado é a
execução real contra o modelo — incluindo quais ferramentas o agente escolheu
chamar em cada turno. Nada aqui é escrito à mão.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_core.messages import AIMessage, HumanMessage  # noqa: E402
from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402

from emporio.agente import (  # noqa: E402
    ErroDeAtendimento,
    construir_grafo,
    texto_da_resposta,
    traduzir_erro,
)
from emporio.config import CONFIG, RAIZ  # noqa: E402
from emporio.prompts import NOME_AGENTE  # noqa: E402

SAÍDA = RAIZ / "examples"

ROTEIROS: list[dict] = [
    {
        "arquivo": "01-catalogo-por-faixa-de-preco.md",
        "titulo": "Catálogo com filtro de preço",
        "resumo": (
            "O cliente dá uma faixa de preço e o agente consulta o catálogo em "
            "vez de responder de memória. O filtro roda sobre o preço que o "
            "cliente de fato paga, não sobre o de tabela."
        ),
        "turnos": [
            "oi! quais opções de violões disponíveis custando até R$1000?",
            "o Yamaha F310 é bom pra quem tá começando?",
            "quanto fica no pix?",
        ],
    },
    {
        "arquivo": "02-informacoes-gerais-e-escopo.md",
        "titulo": "Informações da loja e pedido fora do catálogo",
        "resumo": (
            "Endereço e horário saem do manual de políticas. Em seguida o "
            "cliente pede acessórios, que a loja não comercializa — o agente "
            "redireciona sem inventar um produto."
        ),
        "turnos": [
            "qual o endereço da loja?",
            "vocês abrem sábado que horas?",
            "preciso de um jogo de cordas e umas palhetas também, tem?",
        ],
    },
    {
        "arquivo": "03-promocao-expirada.md",
        "titulo": "Promoção expirada (cenário não trivial)",
        "resumo": (
            "O Takamine GD20 tem uma promoção de 12% cadastrada com "
            "is_active = 0. O cliente pergunta justamente por ela. O agente "
            "precisa informar o preço atual e não prometer um desconto que "
            "não está mais vigente (manual, seção 7.3)."
        ),
        "turnos": [
            "quanto custa o Takamine GD20?",
            "ué, eu vi num anúncio que tinha 12% de desconto nele. ainda vale?",
            "e tem alguma promoção rolando hoje então?",
        ],
    },
    {
        "arquivo": "04-devolucao-pedido.md",
        "titulo": "Devolução com cálculo de prazo (cenário não trivial)",
        "resumo": (
            "O agente cruza dois mundos: o pedido (data de entrega real, vinda "
            "do CSV) e a política (janela de 7 dias para arrependimento). "
            "O prazo do pedido 7 já venceu, então a resposta certa é negar com "
            "transparência — e apontar a garantia legal de 90 dias, que ainda "
            "está de pé."
        ),
        "turnos": [
            "me arrependi da minha compra, posso devolver meu pedido?",
            "é o pedido 7",
            "e se for defeito de fábrica, muda alguma coisa?",
        ],
    },
    {
        "arquivo": "05-fora-de-escopo-e-pedido-em-transito.md",
        "titulo": "Pergunta fora de escopo e rastreio de pedido",
        "resumo": (
            "Pergunta sem relação com a loja é recusada com leveza. Na "
            "sequência, um pedido já despachado e outro ainda sem rastreio — "
            "o agente explica a diferença em vez de inventar um código."
        ),
        "turnos": [
            "qual a capital da Mongólia?",
            "haha beleza. cadê meu pedido 8?",
            "e o pedido 13, que tá demorando?",
        ],
    },
]


def rodar_roteiro(grafo, roteiro: dict) -> str:
    thread_id = f"exemplo-{uuid.uuid4().hex[:8]}"
    linhas = [
        f"# {roteiro['titulo']}",
        "",
        roteiro["resumo"],
        "",
        f"> Gerado por `scripts/gerar_exemplos.py` · modelo `{CONFIG.modelo}` · "
        f"data de referência do agente: {CONFIG.hoje.isoformat()}",
        "",
        "---",
        "",
    ]

    for mensagem in roteiro["turnos"]:
        print(f"    > {mensagem}")
        linhas.append(f"**cliente:** {mensagem}")
        linhas.append("")

        ferramentas: list[str] = []
        resposta = ""

        try:
            passos = grafo.stream(
                {"messages": [HumanMessage(content=mensagem)]},
                config={"configurable": {"thread_id": thread_id}},
                stream_mode="updates",
            )
            for passo in passos:
                atualização = passo.get("agente")
                if not atualização:
                    continue
                for msg in atualização["messages"]:
                    if not isinstance(msg, AIMessage):
                        continue
                    if msg.tool_calls:
                        ferramentas.extend(
                            f"{c['name']}({_args(c['args'])})" for c in msg.tool_calls
                        )
                    else:
                        resposta = texto_da_resposta(msg)
        except Exception as exc:  # noqa: BLE001
            raise traduzir_erro(exc) from None

        if ferramentas:
            linhas.append("<sub>🔧 " + " · ".join(ferramentas) + "</sub>")
            linhas.append("")

        linhas.append(f"**{NOME_AGENTE}:** {resposta}")
        linhas.append("")

    return "\n".join(linhas)


def _args(args: dict) -> str:
    úteis = {k: v for k, v in args.items() if v not in (None, False)}
    return ", ".join(f"{k}={v!r}" for k, v in úteis.items())


def main(argv: list[str]) -> int:
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY não definida — copie .env.example para .env.")
        return 1

    escolhidos = [int(a) for a in argv] if argv else list(range(1, len(ROTEIROS) + 1))
    SAÍDA.mkdir(exist_ok=True)
    # Memória em RAM: os roteiros precisam de contexto entre turnos ("é o
    # pedido 7" só faz sentido depois da pergunta anterior), mas não devem
    # sujar o banco de sessões reais.
    grafo = construir_grafo(checkpointer=InMemorySaver())

    for numero in escolhidos:
        roteiro = ROTEIROS[numero - 1]
        print(f"[{numero}] {roteiro['titulo']}")
        destino = SAÍDA / roteiro["arquivo"]
        try:
            conversa = rodar_roteiro(grafo, roteiro)
        except ErroDeAtendimento as erro:
            print(f"\n{erro}")
            return 1
        destino.write_text(conversa, encoding="utf-8")
        print(f"    -> {destino.relative_to(RAIZ)}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
