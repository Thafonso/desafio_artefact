"""Run scripted conversations and write the interaction examples to examples/.

    python scripts/generate_examples.py            # every script
    python scripts/generate_examples.py 3 4        # only scripts 3 and 4

The conversations go into the repository as a deliverable, so what gets
written is a real run against the model — including which tools the agent
chose to call on each turn. Nothing here is hand-written.

The scripts and the generated files are in Portuguese: they are customer
conversations with a Brazilian store.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_core.messages import AIMessage, HumanMessage  # noqa: E402
from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402

from emporio.agent import (  # noqa: E402
    SupportError,
    build_graph,
    reply_text,
    translate_error,
)
from emporio.config import CONFIG, ROOT  # noqa: E402
from emporio.prompts import AGENT_NAME  # noqa: E402

OUTPUT_DIR = ROOT / "examples"

SCRIPTS: list[dict] = [
    {
        "file": "01-catalogo-por-faixa-de-preco.md",
        "title": "Catálogo com filtro de preço",
        "summary": (
            "O cliente dá uma faixa de preço e o agente consulta o catálogo em "
            "vez de responder de memória. O filtro roda sobre o preço que o "
            "cliente de fato paga, não sobre o de tabela."
        ),
        "turns": [
            "oi! quais opções de violões disponíveis custando até R$1000?",
            "o Yamaha F310 é bom pra quem tá começando?",
            "quanto fica no pix?",
        ],
    },
    {
        "file": "02-informacoes-gerais-e-escopo.md",
        "title": "Informações da loja e pedido fora do catálogo",
        "summary": (
            "Endereço e horário saem do manual de políticas. Em seguida o "
            "cliente pede acessórios, que a loja não comercializa — o agente "
            "redireciona sem inventar um produto."
        ),
        "turns": [
            "qual o endereço da loja?",
            "vocês abrem sábado que horas?",
            "preciso de um jogo de cordas e umas palhetas também, tem?",
        ],
    },
    {
        "file": "03-promocao-expirada.md",
        "title": "Promoção expirada (cenário não trivial)",
        "summary": (
            "O Takamine GD20 tem uma promoção de 12% cadastrada com "
            "is_active = 0. O cliente pergunta justamente por ela. O agente "
            "precisa informar o preço atual e não prometer um desconto que "
            "não está mais vigente (manual, seção 7.3)."
        ),
        "turns": [
            "quanto custa o Takamine GD20?",
            "ué, eu vi num anúncio que tinha 12% de desconto nele. ainda vale?",
            "e tem alguma promoção rolando hoje então?",
        ],
    },
    {
        "file": "04-devolucao-pedido.md",
        "title": "Devolução com cálculo de prazo (cenário não trivial)",
        "summary": (
            "O agente cruza dois mundos: o pedido (data de entrega, vinda do "
            "CSV) e a política (janela de 7 dias para arrependimento). "
            "O prazo do pedido 7 já venceu, então a resposta certa é negar com "
            "transparência — e apontar a garantia legal de 90 dias, que ainda "
            "está de pé."
        ),
        "turns": [
            "me arrependi da minha compra, posso devolver meu pedido?",
            "é o pedido 7",
            "e se for defeito de fábrica, muda alguma coisa?",
        ],
    },
    {
        "file": "05-fora-de-escopo-e-pedido-em-transito.md",
        "title": "Pergunta fora de escopo e rastreio de pedido",
        "summary": (
            "Pergunta sem relação com a loja é recusada com leveza. Na "
            "sequência, um pedido já despachado e outro ainda sem rastreio — "
            "o agente explica a diferença em vez de inventar um código."
        ),
        "turns": [
            "qual a capital da Mongólia?",
            "haha beleza. cadê meu pedido 8?",
            "e o pedido 13, que tá demorando?",
        ],
    },
]


def run_script(graph, script: dict) -> str:
    thread_id = f"exemplo-{uuid.uuid4().hex[:8]}"
    lines = [
        f"# {script['title']}",
        "",
        script["summary"],
        "",
        f"> Gerado por `scripts/generate_examples.py` · modelo `{CONFIG.model}` · "
        f"data de referência do agente: {CONFIG.today.isoformat()}",
        "",
        "---",
        "",
    ]

    for message in script["turns"]:
        print(f"    > {message}")
        lines.append(f"**cliente:** {message}")
        lines.append("")

        called: list[str] = []
        reply = ""

        try:
            steps = graph.stream(
                {"messages": [HumanMessage(content=message)]},
                config={"configurable": {"thread_id": thread_id}},
                stream_mode="updates",
            )
            for step in steps:
                update = step.get("agent")
                if not update:
                    continue
                for msg in update["messages"]:
                    if not isinstance(msg, AIMessage):
                        continue
                    if msg.tool_calls:
                        called.extend(
                            f"{c['name']}({_format_args(c['args'])})"
                            for c in msg.tool_calls
                        )
                    else:
                        reply = reply_text(msg)
        except Exception as exc:  # noqa: BLE001
            raise translate_error(exc) from None

        if called:
            lines.append("<sub>🔧 " + " · ".join(called) + "</sub>")
            lines.append("")

        lines.append(f"**{AGENT_NAME}:** {reply}")
        lines.append("")

    return "\n".join(lines)


def _format_args(args: dict) -> str:
    useful = {k: v for k, v in args.items() if v not in (None, False)}
    return ", ".join(f"{k}={v!r}" for k, v in useful.items())


def main(argv: list[str]) -> int:
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY não definida — copie .env.example para .env.")
        return 1

    chosen = [int(a) for a in argv] if argv else list(range(1, len(SCRIPTS) + 1))
    OUTPUT_DIR.mkdir(exist_ok=True)

    # In-memory history: the scripts need context between turns ("é o pedido 7"
    # only makes sense after the previous question), but must not pollute the
    # real session database.
    graph = build_graph(checkpointer=InMemorySaver())

    for number in chosen:
        script = SCRIPTS[number - 1]
        print(f"[{number}] {script['title']}")
        destination = OUTPUT_DIR / script["file"]
        try:
            conversation = run_script(graph, script)
        except SupportError as error:
            print(f"\n{error}")
            return 1
        destination.write_text(conversation, encoding="utf-8")
        print(f"    -> {destination.relative_to(ROOT)}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
