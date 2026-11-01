"""Índice de busca sobre o manual de políticas da loja.

O manual tem 8 páginas e 10 seções numeradas — pequeno o bastante para caber
inteiro num prompt. Mesmo assim ele é exposto ao agente como *ferramenta* de
busca, por duas razões:

1. mantém o system prompt enxuto e estável (bom para cache de prompt);
2. torna explícita e auditável a decisão "isto é pergunta de política" — que é
   justamente o comportamento que o agente precisa acertar.

A recuperação é BM25 sobre as seções. Com ~20 trechos curtos e perguntas em
português cheias de termos literais do manual ("troca", "garantia", "boleto"),
busca lexical acerta sem precisar de um segundo provedor para embeddings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from pypdf import PdfReader
from rank_bm25 import BM25Okapi

from .config import ARQUIVO_POLITICAS
from .dados import normalizar

CABECALHO = re.compile(r"^Empório da Música\s+Manual de Políticas", re.IGNORECASE)
RODAPE = re.compile(r"^Página\s+\d+\s*$", re.IGNORECASE)
TITULO = re.compile(r"^(\d{1,2}(?:\.\d{1,2})?)\.?\s+(\S.*)$")

STOPWORDS = {
    "a", "ao", "aos", "as", "da", "das", "de", "do", "dos", "e", "em", "na",
    "nas", "no", "nos", "o", "os", "para", "por", "que", "um", "uma", "com",
    "qual", "quais", "como", "posso", "pode", "meu", "minha", "eu", "voces",
    "se", "sobre", "tem", "ter", "ser", "e", "ou",
}


@dataclass(frozen=True)
class Secao:
    numero: str
    titulo: str
    texto: str

    def __str__(self) -> str:
        cabecalho = f"{self.numero} {self.titulo}".strip()
        return f"[{cabecalho}]\n{self.texto}"


def _linhas_limpas() -> list[str]:
    leitor = PdfReader(ARQUIVO_POLITICAS)
    linhas: list[str] = []
    for pagina in leitor.pages:
        for linha in pagina.extract_text(extraction_mode="layout").splitlines():
            linha = re.sub(r"\s+", " ", linha).strip()
            if not linha or CABECALHO.match(linha) or RODAPE.match(linha):
                continue
            linhas.append(linha)
    return linhas


def _dividir_em_secoes(linhas: list[str]) -> list[Secao]:
    secoes: list[Secao] = []
    numero, titulo = "0", "Identificação da loja"
    corpo: list[str] = []

    for linha in linhas:
        match = TITULO.match(linha)
        # Uma linha só vira título se for curta: evita confundir com itens de
        # tabela que começam por número ("3 dias úteis", "90 dias ...").
        if match and len(linha) < 70 and not linha.endswith("."):
            # Seção sem corpo próprio (um "5." seguido direto de "5.1") ainda
            # entra no índice: o título é o que responde "o que vocês cobrem?".
            if corpo or numero != "0":
                secoes.append(Secao(numero, titulo, "\n".join(corpo)))
            numero, titulo = match.group(1), match.group(2)
            corpo = []
        else:
            corpo.append(linha)

    if corpo:
        secoes.append(Secao(numero, titulo, "\n".join(corpo)))
    return secoes


# Radical por prefixo, em vez de um stemmer de verdade. O cliente escreve
# "me arrependi" e o manual diz "Direito de Arrependimento"; "devolver" x
# "devolução"; "trocar" x "trocas". Cortar em 5 caracteres aproxima essas
# famílias sem a dependência (e os falsos positivos) de um stemmer completo
# num corpus de ~25 trechos.
TAMANHO_RADICAL = 5


def _tokenizar(texto: str) -> list[str]:
    palavras = normalizar(texto).split()
    return [
        p[:TAMANHO_RADICAL]
        for p in palavras
        if p not in STOPWORDS and len(p) > 1
    ]


@dataclass
class IndicePoliticas:
    secoes: list[Secao]
    _bm25: BM25Okapi

    def buscar(self, pergunta: str, k: int = 3) -> list[Secao]:
        consulta = _tokenizar(pergunta)
        if not consulta:
            return self.secoes[:k]
        notas = self._bm25.get_scores(consulta)
        ordenadas = sorted(zip(notas, self.secoes), key=lambda par: par[0], reverse=True)
        return [secao for nota, secao in ordenadas[:k] if nota > 0]

    def por_numero(self, numero: str) -> Secao | None:
        return next((s for s in self.secoes if s.numero == numero), None)

    def sumario(self) -> list[str]:
        return [f"{s.numero} {s.titulo}".strip() for s in self.secoes]


@lru_cache(maxsize=1)
def carregar_politicas() -> IndicePoliticas:
    secoes = _dividir_em_secoes(_linhas_limpas())
    # O título entra duas vezes no documento indexado: numa busca curta como
    # "trocas e devoluções" ele é o sinal mais forte que existe.
    corpus = [_tokenizar(f"{s.titulo} {s.titulo} {s.texto}") for s in secoes]
    return IndicePoliticas(secoes=secoes, _bm25=BM25Okapi(corpus))
