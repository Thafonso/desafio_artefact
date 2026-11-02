"""Command-line interface for the agent.

    python -m emporio.cli                      new conversation
    python -m emporio.cli -s joao              resume (or create) session "joao"
    python -m emporio.cli --listar             show the saved sessions
    python -m emporio.cli -p "voces tem ukulele?"   one question, then exit

Tool calls show up in grey as they happen: in a support agent, seeing *what it
went to check* is half the evaluation.

Flags and on-screen text are in Portuguese — this is what the store's team
would run.
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid

from langchain_core.messages import AIMessage, HumanMessage
from rich.console import Console
from rich.panel import Panel

from .agent import (
    SupportError,
    build_graph,
    open_checkpointer,
    reply_text,
    translate_error,
)
from .config import CONFIG
from .prompts import AGENT_NAME, GREETING

console = Console()

TOOL_LABEL = {
    "search_products": "consultando o catálogo",
    "product_details": "abrindo a ficha do produto",
    "list_categories": "conferindo as categorias",
    "active_promotions": "verificando as promoções vigentes",
    "lookup_order": "localizando o pedido",
    "payment_options": "calculando pagamento e frete",
    "search_policies": "consultando o manual de políticas",
}


def _require_credentials() -> None:
    if not os.getenv("ANTHROPIC_API_KEY"):
        console.print(
            "[bold red]ANTHROPIC_API_KEY não definida.[/] "
            "Copie .env.example para .env e preencha a chave."
        )
        raise SystemExit(1)


def _run_turn(graph, thread_id: str, message: str) -> str:
    """Run one turn, surfacing tools as the agent calls them."""
    reply = ""
    config = {"configurable": {"thread_id": thread_id}}

    try:
        steps = graph.stream(
            {"messages": [HumanMessage(content=message)]},
            config=config,
            stream_mode="updates",
        )
        for step in steps:
            for node, update in step.items():
                if node != "agent":
                    continue
                for msg in update["messages"]:
                    if not isinstance(msg, AIMessage):
                        continue
                    if msg.tool_calls:
                        for call in msg.tool_calls:
                            label = TOOL_LABEL.get(call["name"], call["name"])
                            console.print(f"  [dim]… {label}[/]")
                    else:
                        reply = reply_text(msg)
    except Exception as exc:  # noqa: BLE001 — translate_error re-raises the unknown
        raise translate_error(exc) from None

    return reply


def _list_sessions() -> None:
    checkpointer = open_checkpointer()
    seen: dict[str, str] = {}
    for point in checkpointer.list(None):
        thread = point.config["configurable"]["thread_id"]
        seen.setdefault(thread, point.checkpoint["ts"])

    if not seen:
        console.print("Nenhuma sessão gravada ainda.")
        return

    console.print(f"[bold]{len(seen)} sessão(ões):[/]")
    for thread, when in seen.items():
        console.print(f"  {thread}  [dim]último turno: {when[:19]}[/]")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="emporio",
        description="Agente de atendimento da Empório da Música.",
    )
    parser.add_argument(
        "-s", "--sessao", help="identificador da conversa (retoma se já existir)"
    )
    parser.add_argument("-p", "--pergunta", help="faz uma única pergunta e sai")
    parser.add_argument(
        "--listar", action="store_true", help="lista as sessões gravadas e sai"
    )
    args = parser.parse_args(argv)

    if args.listar:
        _list_sessions()
        return 0

    _require_credentials()

    thread_id = args.sessao or f"cli-{uuid.uuid4().hex[:8]}"
    graph = build_graph(checkpointer=open_checkpointer())

    if args.pergunta:
        try:
            reply = _run_turn(graph, thread_id, args.pergunta)
        except SupportError as error:
            console.print(f"[bold red]{error}[/]")
            return 1
        console.print(f"\n[bold cyan]{AGENT_NAME}:[/] {reply}")
        return 0

    console.print(
        Panel(
            GREETING,
            title="Empório da Música",
            subtitle=f"sessão {thread_id} · modelo {CONFIG.model} · hoje {CONFIG.today}",
            border_style="cyan",
        )
    )
    console.print("[dim]Ctrl+C ou 'sair' para encerrar.[/]\n")

    while True:
        try:
            message = console.input("[bold green]você:[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Até mais![/]")
            return 0

        if not message:
            continue
        if message.lower() in {"sair", "exit", "quit", "/sair"}:
            console.print("[dim]Até mais![/]")
            return 0

        try:
            reply = _run_turn(graph, thread_id, message)
        except SupportError as error:
            # The session survives: a rate limit should not kill the
            # conversation, and the history so far is already checkpointed.
            console.print(f"[bold red]{error}[/]\n")
            continue
        console.print(f"[bold cyan]{AGENT_NAME}:[/] {reply}\n")


if __name__ == "__main__":
    sys.exit(main())
