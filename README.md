# Empório da Música — agente de atendimento

Protótipo de um agente de atendimento por mensagem de texto para a Empório da
Música, loja fictícia de instrumentos musicais em Campo Grande/MS. O agente
responde dúvidas sobre catálogo, preços, pedidos e políticas da loja, e sabe
quando consultar cada fonte.

Desafio técnico para a vaga de AI Engineer na Artefact.

---

## Como rodar

**Requisitos:** Python 3.11+ (desenvolvido e testado no 3.13) e uma chave da
API Anthropic — [console.anthropic.com](https://console.anthropic.com/settings/keys).

```bash
git clone <url-do-repositorio>
cd emp_musicabot
python -m venv .venv
```

Ative o ambiente — `\.venv\Scripts\activate` no Windows, `source .venv/bin/activate`
no Linux/macOS — e então:

```bash
pip install -r requirements.txt
```

Copie `.env.example` para `.env` e preencha a chave:

```bash
cp .env.example .env
```

```
ANTHROPIC_API_KEY=sk-ant-...
```

Conversar com o agente:

```bash
python -m emporio.cli
```

Outros modos:

```bash
python -m emporio.cli -p "quais violões vocês têm até R$1000?"
```

```bash
python -m emporio.cli -s joao
```

```bash
python -m emporio.cli --listar
```

`-p` faz uma pergunta e sai. `-s` nomeia a sessão: rodar de novo com o mesmo
nome retoma a conversa de onde parou, inclusive depois de fechar o terminal.
`--listar` mostra as sessões gravadas.

Rodar os testes:

```bash
python -m pytest tests -q
```

Regerar os exemplos de conversa (consome API):

```bash
python scripts/generate_examples.py
```

---

## Arquitetura

```
mensagem do cliente
        │
        ▼
   ┌─────────┐   pediu ferramenta?   ┌──────────────┐
   │ agente  │ ───────────────────▶  │ ferramentas  │
   │ (LLM)   │ ◀───────────────────  │ (7, puras)   │
   └─────────┘      resultado        └──────────────┘
        │                                   │
        │ não pediu                  ┌──────┴───────┐
        ▼                            ▼              ▼
    resposta                  CSVs tratados   índice BM25
                                (pandas)      (políticas)
```

| Arquivo | Papel |
|---|---|
| `emporio/config.py` | Chaves, caminhos e a data de referência |
| `emporio/data.py` | CSVs → DataFrames normalizados e consultáveis |
| `emporio/policies.py` | PDF → 29 seções → índice BM25 |
| `emporio/tools.py` | As 7 ferramentas que o modelo pode chamar |
| `emporio/prompts.py` | Persona, roteamento e limites |
| `emporio/agent.py` | O grafo LangGraph |
| `emporio/cli.py` | Interface de conversa |

### As ferramentas

| Ferramenta | Para quê |
|---|---|
| `search_products` | Catálogo com filtro de termo, categoria e faixa de preço |
| `product_details` | Ficha completa: specs, estoque, preços |
| `list_categories` | O que a loja vende e quantos itens tem de cada |
| `active_promotions` | Só as promoções vigentes |
| `lookup_order` | Status, itens, rastreio e prazos de troca do pedido |
| `payment_options` | PIX, parcelas válidas e frete |
| `search_policies` | Busca no manual e devolve o trecho citável |

### Convenção de idioma

O código é em inglês — nomes de módulo, função, variável, comentários e
docstrings. Fica em português só o que é **conteúdo**, não estrutura: o system
prompt (define uma persona que fala com cliente brasileiro), o texto que as
ferramentas devolvem, as mensagens do CLI e as flags que a equipe da loja
digitaria. A fronteira é simples: se uma pessoa lê aquilo na tela, está em
português; se é o programa falando com o programa, está em inglês.

A exceção que importa: os **nomes e descrições das ferramentas estão em
inglês**, e eles não são só documentação — vão no payload da API e são o que o
modelo lê para escolher qual chamar. Na prática o Claude roteia igualmente bem
com descrição em inglês e conversa em português, mas é uma mudança que afeta
comportamento, não só legibilidade.

---

## Decisões técnicas

### Híbrido: function calling nos dados, retrieval nas políticas

Os dados da loja são tabulares e pequenos (65 produtos, 20 pedidos). Perguntas
reais sobre eles são filtros e agregações — *"violões até R$1000"*, *"cadê meu
pedido 8"* — e é exatamente nisso que busca por similaridade erra: embedding não
sabe que 999 ≤ 1000. Então o catálogo é exposto como **ferramentas
determinísticas** sobre DataFrames.

Considerei um **agente de SQL**, que daria mais flexibilidade de consulta. Para
65 linhas não compensa: adiciona uma superfície de falha inteira (SQL inválido,
injeção, erro silencioso de join) sem resolver nenhum problema que as sete
ferramentas não resolvam. Se o catálogo fossem as 300 mil linhas que uma loja
real teria, a conta inverteria.

As **políticas** são o caso oposto: texto corrido em linguagem natural, onde a
pergunta do cliente quase nunca usa as palavras do manual. Aí retrieval é a
ferramenta certa.

A seção 7.1 do próprio manual fecha a questão: *"nunca fornecer informações
sobre preços, estoque ou prazos sem consultar o sistema"*. O agente foi
construído para que isso seja estruturalmente verdade, não uma instrução que o
modelo pode ignorar.

### Por que LangGraph

O ciclo `modelo → ferramenta → modelo` é ~40 linhas escritas à mão, e cheguei a
considerar fazê-lo assim para evitar a dependência. Fiquei com LangGraph por um
motivo concreto: o **checkpointer**. Ele persiste o estado do grafo por
`thread_id`, o que dá retomada de conversa com as chamadas de ferramenta
incluídas, sem eu escrever uma camada de serialização. O CLI usa `SqliteSaver`
e o gerador de exemplos usa `InMemorySaver` — a diferença entre os dois é o
argumento passado para `build_graph`.

O grafo está escrito explicitamente (`agente` → `tools_condition` →
`ferramentas` → `agente`) em vez de `create_react_agent`, porque o ciclo é o
coração do projeto e esconder isso atrás de uma chamada tiraria o que há de
mais interessante para ler.

### Modelo: `claude-haiku-5-5`

A tarefa é roteamento entre sete ferramentas bem descritas e redação curta em
português — não exige raciocínio pesado. O Haiku 5.5 é o modelo mais barato da
geração atual e tem function calling confiável; num atendimento que roda milhares
de conversas, isso é a diferença entre viável e inviável. O modelo é
configurável por `EMPORIO_MODEL`, então subir para Sonnet é mudar uma linha do
`.env`.

Uma particularidade: o Haiku 5.5 rejeita valores de amostragem diferentes do
padrão (`temperature`, `top_p`, `top_k`). Verifiquei o payload montado pelo
`langchain-anthropic` antes de qualquer chamada para confirmar que ele não
envia esses campos.

### Retrieval: BM25 sobre as seções, não embeddings

O manual tem 8 páginas. Caberia inteiro no system prompt, e isso funcionaria.
Preferi expô-lo como **ferramenta** por duas razões: mantém o prefixo do prompt
pequeno e estável, e torna explícita e auditável a decisão *"isto é pergunta de
política"* — que é justamente o comportamento que o desafio pede para o agente
acertar. Nos exemplos gerados dá para ver o agente escolhendo entre consultar
dados e consultar o manual.

A busca é lexical (BM25) e não vetorial, porque com ~25 trechos curtos e
perguntas em português cheias de termos literais do manual (*troca, garantia,
boleto, frete*) ela acerta, e evita puxar um segundo provedor só para gerar
embeddings.

Um detalhe que só apareceu testando: o cliente escreve *"me arrependi"* e o
manual diz *"Direito de Arrependimento"*. Sem tratamento, a seção 4.1 nunca era
recuperada. A solução foi cortar os radicais em 5 caracteres — um stemmer
pobre, mas suficiente para o corpus e sem os falsos positivos de um stemmer
completo. Com ele, as 11 perguntas de teste trazem a seção certa no top-3.

### Extração do PDF

O modo padrão do `pypdf` devolve este manual com uma palavra por linha, o que
destrói qualquer chance de detectar títulos. O modo `layout` preserva a
estrutura visual, e aí as 29 seções numeradas saem com um regex de uma linha.

### Prompt: identidade no prompt, fatos na ferramenta

O system prompt tem persona, tom, regras de roteamento e limites — e **nenhum
dado da loja**. Endereço, horário e formas de pagamento aceitas não estão
escritos lá, mesmo sendo estáveis. Se estivessem, haveria duas fontes de verdade
para a mesma informação, e elas divergiriam na primeira vez que o manual fosse
atualizado.

O tom veio da seção 7.1 do manual: *"informal mas profissional (...) como se
estivesse conversando com um amigo que entende de música"*. A agente se chama
Dani.

---

## Suposições assumidas

**A data de referência do agente é configurável, e o padrão não é hoje.**
Os dados vão de 2025-10-15 a 2026-03-22. Rodar o agente com a data real do
sistema colocaria todos os pedidos fora das janelas de 7 dias (arrependimento) e
30 dias (troca por defeito), tornando impossível demonstrar essas regras. O
padrão é `2026-03-23`, o dia seguinte ao último pedido — o único valor que
mantém a base inteira coerentemente no passado. Configurável em
`EMPORIO_DATA_REFERENCIA`; `hoje` usa a data real.

**Não existe `customers.csv`.** O enunciado menciona dados de clientes, mas o
arquivo não foi entregue — `orders.customer_id` aponta para uma tabela que não
existe. Consequências: o agente não cumprimenta pelo nome (o fluxo 7.2 do manual
pede isso "se disponível") e não localiza pedido por nome, CPF ou e-mail. A
identificação é pelo número do pedido, e o agente não entrega dados de um pedido
sem que o cliente informe o número.

**A data de recebimento é aproximada pela previsão de entrega.** A base não
registra quando o produto chegou de fato, só `estimated_delivery`. É o que o
agente usa para contar os 7 dias de arrependimento, e ele diz a data em que se
baseou ao responder.

**O manual e o catálogo se contradizem, e o catálogo ganha.** O manual fala em
*"mais de 300 instrumentos"* e lista sopros e cordas orquestrais; o CSV tem 65
produtos e nenhum item nessas categorias. Disponibilidade e preço sempre saem da
tabela.

**Promoção vencida é tratada como inexistente.** Das 25 promoções cadastradas, 4
têm `is_active = 1`. As outras 21 não chegam ao agente — ele não consegue
oferecê-las nem por acidente. A seção 7.3 do manual manda verificar vigência e
nunca prometer desconto vencido; em vez de confiar no modelo para isso, o dado
não existe. (O exemplo 3 mostra o cliente perguntando por uma delas.)

**O agente não executa ações, só informa.** Não cancela pedido, não emite
reembolso, não aplica desconto e não reserva produto — os CSVs são a fonte da
verdade e escrever neles a partir de uma conversa exigiria autenticação do
cliente, que não temos.

---

## Limitações conhecidas

**Não há avaliação automatizada do agente.** Os 27 testes cobrem as ferramentas,
que são funções puras — travam as regras do manual (PIX que não acumula com
promoção, parcela mínima, janelas de prazo) sem gastar uma chamada de LLM. O que
*não* está coberto é a decisão do modelo: nada garante que ele vá chamar
`search_policies` na pergunta certa. Essa é a lacuna mais séria do projeto.

**A busca de produtos exige que todas as palavras apareçam.** Uma busca por
"violão elétrico nylon" filtra por cada termo; se o cliente escrever o modelo
errado, não há fallback por similaridade.

**BM25 não entende sinônimo.** "Posso pagar fiado?" não recupera a seção de
formas de pagamento, porque nenhuma palavra bate. O corte de radical resolve
flexão, não vocabulário.

**O histórico cresce sem limite.** Uma conversa longa reenvia tudo a cada turno.
Com 1M de contexto e atendimento curto não é um problema prático, mas não há
compactação.

**Uma conversa por vez.** O `SqliteSaver` síncrono atende um CLI; uma API com
concorrência pediria a versão assíncrona.

### Com mais tempo

A primeira coisa seria o **conjunto de avaliação**: 30 a 40 perguntas rotuladas
com a ferramenta que *deveria* ser chamada e um fato que *precisa* aparecer na
resposta. Sem isso, qualquer mexida no prompt é palpite — não dá para saber se
melhorou ou piorou. É o que separa o protótipo de algo que se mantém.

Depois:

- **Busca híbrida nas políticas** — BM25 combinado com embeddings resolveria o
  problema de sinônimo, que é o teto da abordagem atual.
- **Cache de prompt** no bloco de system + definições de ferramenta. O prefixo
  já é estável por construção, então é quase de graça.
- **`customers.csv`** e, com ele, identificação do cliente, saudação pelo nome e
  histórico de compras para recomendação.
- **Handoff para humano** — um gatilho explícito quando o cliente reclama ou
  pede alguém. Hoje o agente orienta a procurar a loja, mas não registra nada.
- **Uma API** (FastAPI) no lugar do CLI, que é o que um WhatsApp real precisaria.

---

## Exemplos de interação

Em [`examples/`](examples/), cinco conversas geradas por
`scripts/generate_examples.py` rodando contra o modelo de verdade — incluindo quais
ferramentas o agente escolheu chamar em cada turno. Nenhuma foi escrita à mão.

| # | Cenário | O que demonstra |
|---|---|---|
| 1 | [Catálogo por faixa de preço](examples/01-catalogo-por-faixa-de-preco.md) | Consulta ao catálogo com filtro numérico |
| 2 | [Informações gerais e escopo](examples/02-informacoes-gerais-e-escopo.md) | Políticas + recusa de acessórios |
| 3 | [Promoção expirada](examples/03-promocao-expirada.md) | **Não trivial** — o cliente cobra um desconto que não vale mais |
| 4 | [Devolução de pedido](examples/04-devolucao-pedido.md) | **Não trivial** — cruza dados do pedido com a janela de prazo da política |
| 5 | [Fora de escopo e rastreio](examples/05-fora-de-escopo-e-pedido-em-transito.md) | Recusa educada + dois pedidos em estados diferentes |

---

## Uso de assistentes de código

Usei o **Claude Code** (modelo Opus 5) em sessão interativa, do início ao fim.
O fluxo foi deliberadamente de duas fases.

**Primeiro exploração, sem escrever código.** Pedi que lesse o enunciado e os
dados e me trouxesse o que estava lá antes de propor qualquer arquitetura. Essa
passada rendeu as descobertas que mais moldaram o projeto: que `customers.csv`
não existe, que só 4 das 25 promoções estão vigentes — e que o Takamine GD20, o
produto sugerido no próprio enunciado, tem uma promoção expirada, o que virou o
exemplo 3. O descompasso entre a data real e o fim dos dados também apareceu
aqui, antes de virar bug.

**Depois implementação em blocos verificáveis.** Dados → políticas →
ferramentas → grafo → CLI, com teste rodando a cada etapa e um commit por bloco.
O histórico do repositório é esse processo, não uma reconstrução.

As **decisões de arquitetura foram minhas**, tomadas sobre opções que pedi que
fossem apresentadas com trade-offs: function calling em vez de agente de SQL,
LangGraph em vez de loop próprio, BM25 em vez de embeddings, data de referência
configurável em vez de reescrever os CSVs. Em cada uma, a justificativa está
acima — e o ponto de usar o assistente foi chegar nelas com os dados na mão, não
no abstrato.

Onde ele rendeu mais: varrer os CSVs atrás de casos de borda (descontinuado com
estoque, pedido sem rastreio, promoções duplicadas no mesmo produto) e
transformar isso em teste. Onde precisei corrigir: a primeira versão do índice
de políticas engolia as seções-pai sem corpo próprio (`5.`, `6.`, `8.`) e não
recuperava a seção 4.1 para *"me arrependi"* — os dois só apareceram porque medi
a recuperação em vez de aceitar que parecia funcionar.
