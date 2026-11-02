"""O grafo do agente.

Duas caixas e uma condição: o modelo decide, as ferramentas executam, e o
resultado volta para o modelo até ele ter o que responder.

    START → agente ──(pediu ferramenta?)──→ ferramentas ──┐
                │                                          │
                └──────────────── END          ←───────────┘

Está escrito à mão em vez de `create_react_agent` porque o ciclo é o coração
do projeto — deixá-lo visível vale mais aqui do que economizar dez linhas.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import anthropic
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from .config import CONFIG
from .ferramentas import FERRAMENTAS
from .prompts import montar_system_prompt

# Respostas de atendimento são curtas; o teto existe só para o turno em que o
# modelo escreve vários argumentos de ferramenta de uma vez.
MAX_TOKENS = 4096


def construir_modelo(modelo: str | None = None) -> ChatAnthropic:
    """Cliente do modelo, já com as ferramentas acopladas.

    Sem `temperature`: o Haiku 5.5 rejeita valores de amostragem diferentes do
    padrão, e a variação de resposta aqui não é desejável de qualquer forma.
    """
    llm = ChatAnthropic(
        model=modelo or CONFIG.modelo,
        max_tokens=MAX_TOKENS,
    )
    return llm.bind_tools(FERRAMENTAS)


def construir_grafo(
    modelo: str | None = None,
    checkpointer: Any | None = None,
):
    """Monta e compila o grafo do agente."""
    llm = construir_modelo(modelo)
    system = SystemMessage(content=montar_system_prompt(CONFIG.hoje))

    def nó_agente(state: MessagesState) -> dict[str, list[BaseMessage]]:
        # O system prompt é remontado a cada turno em vez de ficar guardado no
        # estado: assim o histórico persistido tem só a conversa, e mudar a
        # persona não exige migrar as sessões antigas.
        resposta = llm.invoke([system, *state["messages"]])
        return {"messages": [resposta]}

    grafo = StateGraph(MessagesState)
    grafo.add_node("agente", nó_agente)
    grafo.add_node("ferramentas", ToolNode(FERRAMENTAS))

    grafo.add_edge(START, "agente")
    grafo.add_conditional_edges(
        "agente",
        tools_condition,
        {"tools": "ferramentas", END: END},
    )
    grafo.add_edge("ferramentas", "agente")

    return grafo.compile(checkpointer=checkpointer)


def abrir_checkpointer(caminho: Path | None = None) -> SqliteSaver:
    """Histórico de conversa em SQLite, retomável por `thread_id`.

    O checkpointer do LangGraph já guarda o estado do grafo turno a turno, o
    que inclui as chamadas de ferramenta — então uma sessão retomada volta com
    o contexto inteiro, não só com o texto das mensagens.
    """
    caminho = caminho or (CONFIG.diretorio_sessoes / "conversas.sqlite")
    caminho.parent.mkdir(parents=True, exist_ok=True)
    conexao = sqlite3.connect(caminho, check_same_thread=False)
    return SqliteSaver(conexao)


def responder(grafo, mensagem: str, thread_id: str) -> str:
    """Envia uma mensagem ao agente e devolve o texto final da resposta."""
    estado = grafo.invoke(
        {"messages": [HumanMessage(content=mensagem)]},
        config={"configurable": {"thread_id": thread_id}},
    )
    return texto_da_resposta(estado["messages"][-1])


def texto_da_resposta(mensagem: BaseMessage) -> str:
    """Extrai o texto de uma resposta, ignorando blocos de raciocínio."""
    if isinstance(mensagem.content, str):
        return mensagem.content
    partes = [
        bloco.get("text", "")
        for bloco in mensagem.content
        if isinstance(bloco, dict) and bloco.get("type") == "text"
    ]
    return "\n".join(p for p in partes if p).strip()


class ErroDeAtendimento(RuntimeError):
    """Falha de API já traduzida para algo que a pessoa consegue agir."""


def traduzir_erro(exc: Exception) -> ErroDeAtendimento:
    """Transforma a exceção do SDK na causa real, sem despejar stack trace.

    Quem roda isto quer saber o que fazer a seguir — se falta crédito, se a
    chave está errada ou se é só esperar —, não ler cinquenta quadros de
    pilha do LangGraph.
    """
    if isinstance(exc, anthropic.AuthenticationError):
        return ErroDeAtendimento(
            "Chave de API recusada. Confira ANTHROPIC_API_KEY no .env — ela "
            "precisa ser uma chave do console.anthropic.com, começando por "
            "'sk-ant-'."
        )

    if isinstance(exc, anthropic.PermissionDeniedError):
        return ErroDeAtendimento(
            "A chave não tem permissão para este modelo. Verifique o "
            f"EMPORIO_MODEL ({CONFIG.modelo}) e o workspace da chave."
        )

    if isinstance(exc, anthropic.RateLimitError):
        return ErroDeAtendimento(
            "Limite de requisições atingido. Espere alguns segundos e tente "
            "de novo."
        )

    if isinstance(exc, anthropic.BadRequestError):
        mensagem = str(getattr(exc, "message", exc))
        if "credit balance" in mensagem.lower():
            return ErroDeAtendimento(
                "A conta da API não tem créditos. A chave é válida, mas o "
                "saldo está zerado — adicione créditos em Plans & Billing no "
                "console.anthropic.com.\n"
                "Assinatura do Claude (Pro/Max) não financia a API: o saldo é "
                "separado."
            )
        return ErroDeAtendimento(f"Requisição recusada pela API: {mensagem}")

    if isinstance(exc, anthropic.APITimeoutError):
        return ErroDeAtendimento("A API demorou demais para responder.")

    if isinstance(exc, anthropic.APIConnectionError):
        return ErroDeAtendimento(
            "Não foi possível falar com a API da Anthropic. Verifique a "
            "conexão (e o proxy, se houver)."
        )

    if isinstance(exc, anthropic.APIStatusError):
        return ErroDeAtendimento(
            f"A API devolveu erro {exc.status_code}: "
            f"{getattr(exc, 'message', exc)}"
        )

    raise exc


def ferramentas_usadas(mensagem: BaseMessage) -> list[str]:
    if isinstance(mensagem, AIMessage) and mensagem.tool_calls:
        return [c["name"] for c in mensagem.tool_calls]
    return []
