"""The agent graph.

Two boxes and one condition: the model decides, the tools run, and the result
goes back to the model until it has something to answer with.

    START → agent ──(asked for a tool?)──→ tools ──┐
              │                                     │
              └──────────────── END     ←───────────┘

Written by hand rather than with `create_react_agent` because the loop is the
heart of the project — keeping it visible is worth more here than saving ten
lines.
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
from .prompts import build_system_prompt
from .tools import TOOLS

# Support replies are short; the ceiling exists only for the turn where the
# model writes several tool arguments at once.
MAX_TOKENS = 4096


def build_model(model: str | None = None) -> ChatAnthropic:
    """The model client, with the tools already bound.

    No `temperature`: Haiku 5.5 rejects sampling values other than the default,
    and response variation would not be desirable here anyway.
    """
    llm = ChatAnthropic(
        model=model or CONFIG.model,
        max_tokens=MAX_TOKENS,
    )
    return llm.bind_tools(TOOLS)


def build_graph(model: str | None = None, checkpointer: Any | None = None):
    """Assemble and compile the agent graph."""
    llm = build_model(model)
    system = SystemMessage(content=build_system_prompt(CONFIG.today))

    def agent_node(state: MessagesState) -> dict[str, list[BaseMessage]]:
        # The system prompt is rebuilt each turn instead of being stored in
        # state: persisted history then holds only the conversation, and
        # changing the persona does not require migrating old sessions.
        reply = llm.invoke([system, *state["messages"]])
        return {"messages": [reply]}

    graph = StateGraph(MessagesState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(TOOLS))

    graph.add_edge(START, "agent")
    graph.add_conditional_edges(
        "agent",
        tools_condition,
        {"tools": "tools", END: END},
    )
    graph.add_edge("tools", "agent")

    return graph.compile(checkpointer=checkpointer)


def open_checkpointer(path: Path | None = None) -> SqliteSaver:
    """Conversation history in SQLite, resumable by `thread_id`.

    LangGraph's checkpointer stores the graph state turn by turn, tool calls
    included — so a resumed session comes back with the whole context, not
    just the message text.
    """
    path = path or (CONFIG.sessions_dir / "conversas.sqlite")
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, check_same_thread=False)
    return SqliteSaver(connection)


def ask(graph, message: str, thread_id: str) -> str:
    """Send one message to the agent and return the final reply text."""
    state = graph.invoke(
        {"messages": [HumanMessage(content=message)]},
        config={"configurable": {"thread_id": thread_id}},
    )
    return reply_text(state["messages"][-1])


def reply_text(message: BaseMessage) -> str:
    """Pull the text out of a reply, skipping reasoning blocks."""
    if isinstance(message.content, str):
        return message.content
    parts = [
        block.get("text", "")
        for block in message.content
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    return "\n".join(p for p in parts if p).strip()


def tools_called(message: BaseMessage) -> list[str]:
    if isinstance(message, AIMessage) and message.tool_calls:
        return [c["name"] for c in message.tool_calls]
    return []


class SupportError(RuntimeError):
    """An API failure already translated into something actionable."""


def translate_error(exc: Exception) -> SupportError:
    """Turn an SDK exception into the actual cause, without a stack trace.

    Whoever runs this wants to know what to do next — top up credit, fix the
    key, or just wait — not read fifty frames of LangGraph internals.

    Messages stay in Portuguese: they are shown to the person running the CLI.
    """
    if isinstance(exc, anthropic.AuthenticationError):
        return SupportError(
            "Chave de API recusada. Confira ANTHROPIC_API_KEY no .env — ela "
            "precisa ser uma chave do console.anthropic.com, começando por "
            "'sk-ant-'."
        )

    if isinstance(exc, anthropic.PermissionDeniedError):
        return SupportError(
            "A chave não tem permissão para este modelo. Verifique o "
            f"EMPORIO_MODEL ({CONFIG.model}) e o workspace da chave."
        )

    if isinstance(exc, anthropic.RateLimitError):
        return SupportError(
            "Limite de requisições atingido. Espere alguns segundos e tente "
            "de novo."
        )

    if isinstance(exc, anthropic.BadRequestError):
        message = str(getattr(exc, "message", exc))
        if "credit balance" in message.lower():
            return SupportError(
                "A conta da API não tem créditos. A chave é válida, mas o "
                "saldo está zerado — adicione créditos em Plans & Billing no "
                "console.anthropic.com.\n"
                "Assinatura do Claude (Pro/Max) não financia a API: o saldo é "
                "separado."
            )
        return SupportError(f"Requisição recusada pela API: {message}")

    if isinstance(exc, anthropic.APITimeoutError):
        return SupportError("A API demorou demais para responder.")

    if isinstance(exc, anthropic.APIConnectionError):
        return SupportError(
            "Não foi possível falar com a API da Anthropic. Verifique a "
            "conexão (e o proxy, se houver)."
        )

    if isinstance(exc, anthropic.APIStatusError):
        return SupportError(
            f"A API devolveu erro {exc.status_code}: {getattr(exc, 'message', exc)}"
        )

    raise exc
