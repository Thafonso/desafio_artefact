# Empório da Música — customer support agent

Prototype of a text-message support agent for Empório da Música, a fictional
musical instrument store in Campo Grande, Brazil. The agent answers questions
about the catalog, prices, orders and store policies, and knows which source to
consult for each.

Technical challenge for the AI Engineer role at Artefact.

> The agent talks to Brazilian customers, so everything it says — and
> everything the CLI prints — is in Portuguese. The code and this document are
> in English; see [Language convention](#language-convention).

---

## Running it

**Requirements:** Python 3.11+ (developed and tested on 3.13) and an Anthropic
API key — [console.anthropic.com](https://console.anthropic.com/settings/keys).

```bash
git clone https://github.com/Thafonso/desafio_artefact.git
cd desafio_artefact
python -m venv .venv
```

Activate the environment — `.venv\Scripts\activate` on Windows,
`source .venv/bin/activate` on Linux/macOS — then:

```bash
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in the key:

```bash
cp .env.example .env
```

```
ANTHROPIC_API_KEY=sk-ant-...
```

Talk to the agent:

```bash
python -m emporio.cli
```

Other modes:

```bash
python -m emporio.cli -p "quais violões vocês têm até R$1000?"
```

```bash
python -m emporio.cli -s joao
```

```bash
python -m emporio.cli --listar
```

`-p` asks one question and exits. `-s` names the session: running again with
the same name resumes the conversation where it stopped, even after closing the
terminal. `--listar` shows the saved sessions.

Run the tests:

```bash
python -m pytest tests -q
```

Regenerate the example conversations (spends API credit):

```bash
python scripts/generate_examples.py
```

---

## Architecture

```
customer message
        │
        ▼
   ┌─────────┐   asked for a tool?   ┌──────────────┐
   │  agent  │ ───────────────────▶  │    tools     │
   │  (LLM)  │ ◀───────────────────  │ (7, pure)    │
   └─────────┘        result         └──────────────┘
        │                                   │
        │ no tool                    ┌──────┴───────┐
        ▼                            ▼              ▼
      reply                   cleaned CSVs    BM25 index
                                (pandas)      (policies)
```

| File | Role |
|---|---|
| `emporio/config.py` | Keys, paths and the reference date |
| `emporio/data.py` | CSVs → normalized, queryable DataFrames |
| `emporio/policies.py` | PDF → 29 sections → BM25 index |
| `emporio/tools.py` | The 7 tools the model can call |
| `emporio/prompts.py` | Persona, routing and limits |
| `emporio/agent.py` | The LangGraph graph |
| `emporio/cli.py` | Conversation interface |

### The tools

| Tool | What for |
|---|---|
| `search_products` | Catalog, filtered by term, category and price range |
| `product_details` | Full record: specs, stock, prices |
| `list_categories` | What the store sells and how many of each |
| `active_promotions` | Live promotions only |
| `lookup_order` | Status, items, tracking and exchange windows |
| `payment_options` | PIX, valid instalments and shipping |
| `search_policies` | Searches the manual, returns a quotable passage |

### Language convention

The code is in English — module, function and variable names, comments and
docstrings. Portuguese is reserved for **content**, not structure: the system
prompt (it defines a persona talking to Brazilian customers), the text the
tools return, the CLI messages and the flags the store's team would type. The
line is simple: if a person reads it on screen, it is Portuguese; if it is the
program talking to the program, it is English.

The exception that matters: the **tool names and descriptions are in English**,
and they are not just documentation — they travel in the API payload and are
what the model reads to pick one. In practice Claude routes just as well with
English descriptions and a Portuguese conversation, but it is a change that
affects behaviour, not only readability.

---

## Technical decisions

### Hybrid: function calling on the data, retrieval on the policies

The store's data is tabular and small (65 products, 20 orders). Real questions
about it are filters and aggregations — *"violões até R$1000"*, *"cadê meu
pedido 8"* — and that is exactly where similarity search fails: an embedding
does not know that 999 ≤ 1000. So the catalog is exposed as **deterministic
tools** over DataFrames.

I considered a **SQL agent**, which would give more query flexibility. For 65
rows it does not pay off: it adds an entire failure surface (invalid SQL,
injection, silently wrong joins) without solving anything the seven tools do
not already solve. If the catalog were the 300k rows a real store would have,
the trade would invert.

The **policies** are the opposite case: prose in natural language, where the
customer's question almost never uses the manual's words. There, retrieval is
the right tool.

Section 7.1 of the manual settles it: *"never give information about prices,
stock or deadlines without checking the system"*. The agent is built so that
this is structurally true, not an instruction the model may ignore.

### Why LangGraph

The `model → tool → model` loop is ~40 hand-written lines, and I did consider
writing it that way to avoid the dependency. I kept LangGraph for one concrete
reason: the **checkpointer**. It persists graph state by `thread_id`, which
gives resumable conversations with the tool calls included, without me writing
a serialization layer. The CLI uses `SqliteSaver` and the example generator
uses `InMemorySaver` — the difference between them is one argument to
`build_graph`.

The graph is written out explicitly (`agent` → `tools_condition` → `tools` →
`agent`) instead of `create_react_agent`, because the loop is the heart of the
project and hiding it behind one call would remove the most interesting thing
to read.

### Model: `claude-haiku-5-5`

The task is routing between seven well-described tools and writing short
Portuguese replies — it does not need heavy reasoning. Haiku 5.5 is the
cheapest model of the current generation and its function calling is reliable;
in a support channel running thousands of conversations, that is the difference
between viable and not. The model is configurable through `EMPORIO_MODEL`, so
moving up to Sonnet is one line in `.env`.

One quirk: Haiku 5.5 rejects sampling values other than the default
(`temperature`, `top_p`, `top_k`). I inspected the payload assembled by
`langchain-anthropic` before making any call, to confirm it does not send those
fields.

### Retrieval: BM25 over the sections, not embeddings

The manual is 8 pages. It would fit whole in the system prompt, and that would
work. I chose to expose it as a **tool** for two reasons: it keeps the prompt
prefix small and stable, and it makes the decision *"this is a policy
question"* explicit and auditable — which is precisely the behaviour the
challenge asks the agent to get right. In the generated examples you can watch
the agent choosing between querying data and querying the manual.

The search is lexical (BM25) rather than vector-based, because with ~25 short
passages and Portuguese questions full of the manual's literal terms (*troca,
garantia, boleto, frete*) it hits, and it avoids pulling in a second provider
just to generate embeddings.

A detail that only showed up under test: the customer writes *"me arrependi"*
and the manual says *"Direito de Arrependimento"*. Untreated, section 4.1 was
never retrieved. The fix was cutting stems at 5 characters — a poor man's
stemmer, but enough for this corpus and without the false positives of a full
one. With it, all 11 test questions bring the right section into the top 3.

### PDF extraction

pypdf's default mode returns this manual with one word per line, which destroys
any chance of detecting headings. `layout` mode preserves the visual structure,
and then the 29 numbered sections fall out of a one-line regex.

### Prompt: identity in the prompt, facts in the tools

The system prompt holds persona, tone, routing rules and limits — and **no
store data**. Address, opening hours and accepted payment methods are not
written there, stable as they are. If they were, there would be two sources of
truth for the same fact, and they would diverge the first time the manual was
updated.

The tone comes from section 7.1 of the manual: *"informal but professional
(...) as if talking to a friend who knows music"*. The agent is called Dani.

---

## Assumptions made

**The agent's reference date is configurable, and the default is not today.**
The data runs from 2025-10-15 to 2026-03-22. Running the agent on the real
system date would put every order outside the 7-day (withdrawal) and 30-day
(defect exchange) windows, making those rules impossible to demonstrate. The
default is `2026-03-23`, the day after the last order — the only value that
keeps the whole dataset coherently in the past. Configurable through
`EMPORIO_DATA_REFERENCIA`; `hoje` uses the real date.

**The agent does not use a customer table.** `orders.customer_id` points at a
table this project does not consume, so the agent does not know who it is
talking to and cannot find an order by name, tax ID or email. Identification is
by order number, and it does not hand over order data unless the customer
supplies that number.

That carries two costs, which I would rather state than hide. The manual asks,
in flow 7.2, to "greet the customer by name (if available)" — and the agent
never greets. And the customer's city, which decides whether delivery is in the
metro area, is out of its reach: `payment_options` takes that as a parameter
and assumes Campo Grande by default (see Limitations).

**The delivery date is approximated by the delivery estimate.** The dataset
does not record when the product actually arrived, only `estimated_delivery`.
That is what the agent counts the 7 days from, and it states the date it based
itself on when answering.

**The manual and the catalog contradict each other, and the catalog wins.** The
manual claims *"more than 300 instruments"* and lists wind and orchestral
strings; the CSV has 65 products and nothing in those categories. Availability
and price always come from the table.

**An expired promotion is treated as non-existent.** Of the 25 promotions on
file, 4 have `is_active = 1`. The other 21 never reach the agent — it cannot
offer them even by accident. Section 7.3 of the manual requires checking
validity and never promising a lapsed discount; rather than trusting the model
with that, the data simply does not exist. (Example 3 shows a customer asking
about one of them.)

**The manual carries two different phone numbers, and both get used.** Section
1.2 gives (67) 3341-4444 as "phone / WhatsApp"; section 7 gives (67) 3321-4500
as "the WhatsApp channel". In the example conversations the agent cites one or
the other depending on which section it retrieved. I did not invent a
tie-break: both are in the document the store provided, and picking one would
be me deciding a business fact. This is the kind of thing you confirm with the
client before going to production.

**The agent informs, it does not act.** It does not cancel orders, issue
refunds, apply discounts or reserve products — the CSVs are the source of truth
and writing to them from a conversation would require authenticating the
customer, which we cannot do.

---

## Known limitations

**There is no automated evaluation of the agent.** The 27 tests cover the
tools, which are pure functions — they lock down the manual's rules (PIX not
stacking with a promotion, minimum instalments, deadline windows) without
spending an LLM call. What is *not* covered is the model's decision: nothing
guarantees it will call `search_policies` on the right question. This is the
most serious gap in the project.

**Product search requires every word to appear.** A search for "violão elétrico
nylon" filters on each term; if the customer misspells the model, there is no
similarity fallback.

**BM25 does not understand synonyms.** "Posso pagar fiado?" does not retrieve
the payment section, because no word matches. Stem cutting solves inflection,
not vocabulary.

**A two-topic question drowns one of them.** This showed up in the first round
of examples: the agent searched *"pedido atrasado não entregue, contato da loja
e WhatsApp"* in a single call, the delivery terms dominated the ranking and the
contact section did not come back even in the top 6 — so the agent told the
customer it did not have the number. I mitigated it in the prompt, asking for
one search per topic, and the regenerated conversations now make short, focused
calls. That is mitigation, not a fix: the fragility belongs to the retriever,
and hybrid search removes it.

**Shipping assumes Campo Grande.** `payment_options` defaults to
`metro_area_delivery=True`, and the agent has no way to know the customer's
city — it would have to ask, and it does not always ask. For someone outside
the metro area the correct rule is per-postcode quoting (PAC, SEDEX or Jadlog),
not the "free shipping above R$500" metro rule. This is the limitation that
bothers me most of those left, because it produces a *wrong* answer rather than
an incomplete one. The real fix is not prompting, it is having the customer's
city alongside the order.

**History grows without bound.** A long conversation resends everything each
turn. With a 1M context window and short support exchanges this is not a
practical problem, but there is no compaction.

**One conversation at a time.** The synchronous `SqliteSaver` is fine for a
CLI; an API with concurrency would want the async version.

### With more time

The first thing would be the **evaluation set**: 30 to 40 questions labelled
with the tool that *should* be called and a fact that *must* appear in the
answer. Without it, any change to the prompt is guesswork — there is no way to
know whether it helped or hurt. That is what separates a prototype from
something maintainable.

After that:

- **Hybrid policy search** — BM25 combined with embeddings would solve the
  synonym problem, which is the ceiling of the current approach.
- **Prompt caching** on the system block and tool definitions. The prefix is
  already stable by construction, so it is nearly free.
- **A customer table** and, with it, greeting by name, the city for shipping
  calculations, and purchase history for recommendations.
- **Human handoff** — an explicit trigger when a customer complains or asks for
  a person. Today the agent points them to the store but records nothing.
- **An API** (FastAPI) instead of the CLI, which is what a real WhatsApp
  integration would need.

---

## Example interactions

In [`examples/`](examples/), five conversations produced by
`scripts/generate_examples.py` running against the real model — including which
tools the agent chose to call on each turn. None were written by hand. The
conversations themselves are in Portuguese, since that is the language the
agent works in.

| # | Scenario | What it shows |
|---|---|---|
| 1 | [Catalog by price range](examples/01-catalogo-por-faixa-de-preco.md) | Catalog query with a numeric filter |
| 2 | [Store info and scope](examples/02-informacoes-gerais-e-escopo.md) | Policies + turning down accessories |
| 3 | [Expired promotion](examples/03-promocao-expirada.md) | **Non-trivial** — the customer claims a discount that no longer applies |
| 4 | [Order return](examples/04-devolucao-pedido.md) | **Non-trivial** — crosses order data with the policy's deadline window |
| 5 | [Out of scope and tracking](examples/05-fora-de-escopo-e-pedido-em-transito.md) | Polite refusal + two orders in different states |

---

## Use of coding assistants

I used **Claude Code** (Opus 5) in an interactive session, start to finish. The
workflow was deliberately in two phases.

**Exploration first, no code.** I asked it to read the brief and the data and
bring me what was actually there before proposing any architecture. That pass
produced the findings that shaped the project most: that only 4 of the 25
promotions are live — and that the Takamine GD20, the product suggested in the
brief itself, carries an expired one, which became example 3. The mismatch
between the real date and the end of the data also surfaced here, before it
could become a bug.

**Then implementation in verifiable blocks.** Data → policies → tools → graph →
CLI, with tests running at each step and one commit per block. The commits in
the repository follow the order in which the blocks were built and validated.

The **architectural decisions were mine**, taken over options I asked to see
with their trade-offs: function calling over a SQL agent, LangGraph over a
hand-rolled loop, BM25 over embeddings, a configurable reference date over
rewriting the CSVs. The justification for each is above — and the point of
using the assistant was to reach them with the data in hand, not in the
abstract.

Where it paid off most: sweeping the CSVs for edge cases (discontinued items
still in stock, orders without tracking, duplicate promotions on the same
product) and turning those into tests. Where I had to correct it: the first
version of the policy index swallowed parent sections with no body of their own
(`5.`, `6.`, `8.`) and failed to retrieve section 4.1 for *"me arrependi"* —
both only surfaced because retrieval was measured instead of assumed to work.
