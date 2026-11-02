"""Interface de linha de comando do agente.

    python -m emporio.cli                      conversa nova
    python -m emporio.cli -s joao              retoma (ou cria) a sessão "joao"
    python -m emporio.cli --listar             mostra as sessões já gravadas
    python -m emporio.cli -p "voces tem ukulele?"   uma pergunta e sai

As chamadas de ferramenta aparecem em cinza enquanto acontecem: num agente de
atendimento, ver *o que ele foi consultar* é metade da avaliação.
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid

from langchain_core.messages import AIMessage, HumanMessage
from rich.console import Console
from rich.panel import Panel

from .agente import (
    ErroDeAtendimento,
    abrir_checkpointer,
    construir_grafo,
    texto_da_resposta,
    traduzir_erro,
)
from .config import CONFIG
from .prompts import NOME_AGENTE, SAUDACAO

console = Console()

RÓTULO_FERRAMENTA = {
    "buscar_produtos": "consultando o catálogo",
    "detalhar_produto": "abrindo a ficha do produto",
    "listar_categorias": "conferindo as categorias",
    "promocoes_ativas": "verificando as promoções vigentes",
    "consultar_pedido": "localizando o pedido",
    "simular_pagamento": "calculando pagamento e frete",
    "consultar_politicas": "consultando o manual de políticas",
}


def _exigir_credencial() -> None:
    if not os.getenv("ANTHROPIC_API_KEY"):
        console.print(
            "[bold red]ANTHROPIC_API_KEY não definida.[/] "
            "Copie .env.example para .env e preencha a chave."
        )
        raise SystemExit(1)


def _conversar(grafo, thread_id: str, mensagem: str) -> str:
    """Roda um turno, mostrando as ferramentas conforme o agente as chama."""
    resposta = ""
    config = {"configurable": {"thread_id": thread_id}}

    try:
        passos = grafo.stream(
            {"messages": [HumanMessage(content=mensagem)]},
            config=config,
            stream_mode="updates",
        )
        for passo in passos:
            for nó, atualização in passo.items():
                if nó != "agente":
                    continue
                for msg in atualização["messages"]:
                    if not isinstance(msg, AIMessage):
                        continue
                    if msg.tool_calls:
                        for chamada in msg.tool_calls:
                            rótulo = RÓTULO_FERRAMENTA.get(
                                chamada["name"], chamada["name"]
                            )
                            console.print(f"  [dim]… {rótulo}[/]")
                    else:
                        resposta = texto_da_resposta(msg)
    except Exception as exc:  # noqa: BLE001 — traduzir_erro repassa o que não conhece
        raise traduzir_erro(exc) from None

    return resposta


def _listar_sessões() -> None:
    checkpointer = abrir_checkpointer()
    vistas: dict[str, str] = {}
    for ponto in checkpointer.list(None):
        thread = ponto.config["configurable"]["thread_id"]
        vistas.setdefault(thread, ponto.checkpoint["ts"])

    if not vistas:
        console.print("Nenhuma sessão gravada ainda.")
        return

    console.print(f"[bold]{len(vistas)} sessão(ões):[/]")
    for thread, quando in vistas.items():
        console.print(f"  {thread}  [dim]último turno: {quando[:19]}[/]")


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
        _listar_sessões()
        return 0

    _exigir_credencial()

    thread_id = args.sessao or f"cli-{uuid.uuid4().hex[:8]}"
    grafo = construir_grafo(checkpointer=abrir_checkpointer())

    if args.pergunta:
        try:
            resposta = _conversar(grafo, thread_id, args.pergunta)
        except ErroDeAtendimento as erro:
            console.print(f"[bold red]{erro}[/]")
            return 1
        console.print(f"\n[bold cyan]{NOME_AGENTE}:[/] {resposta}")
        return 0

    console.print(
        Panel(
            SAUDACAO,
            title="Empório da Música",
            subtitle=f"sessão {thread_id} · modelo {CONFIG.modelo} · hoje {CONFIG.hoje}",
            border_style="cyan",
        )
    )
    console.print("[dim]Ctrl+C ou 'sair' para encerrar.[/]\n")

    while True:
        try:
            mensagem = console.input("[bold green]você:[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Até mais![/]")
            return 0

        if not mensagem:
            continue
        if mensagem.lower() in {"sair", "exit", "quit", "/sair"}:
            console.print("[dim]Até mais![/]")
            return 0

        try:
            resposta = _conversar(grafo, thread_id, mensagem)
        except ErroDeAtendimento as erro:
            # A sessão continua: um limite de requisição não deve derrubar a
            # conversa, e o histórico até aqui já está no checkpointer.
            console.print(f"[bold red]{erro}[/]\n")
            continue
        console.print(f"[bold cyan]{NOME_AGENTE}:[/] {resposta}\n")


if __name__ == "__main__":
    sys.exit(main())
