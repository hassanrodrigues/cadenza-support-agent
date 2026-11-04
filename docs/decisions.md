# Decisions

Each entry covers the context, the options, what I chose and why, what it costs, and when I'd change my mind. The README has the one-line version of each.

## 1. Agent approach: ReAct with tool calling

- **Context.** The brief's questions fall into three kinds: catalog (availability, price), orders (status, returns) and policy (hours, payment, exchanges). Each one needs an exact lookup, not a fuzzy answer.
- **Options.** RAG over everything; a SQL agent over the CSVs; ReAct with a few purpose-built tools.
- **Choice.** ReAct with six tools and native tool calling.
- **Why.** A SQL agent would let the model write queries over customer data, which is risky and hard to verify. RAG is a poor fit for prices and stock. Six tools are easy to test one by one, and each tool's docstring tells the model when to use it.
- **Cost.** An extra model call per tool round; turns take 2 to 6 s.
- **I'd change my mind** if the catalog grew to thousands of items with free-text questions about them. Then a search index behind `search_products` would make sense, keeping the same tool interface.

## 2. Framework: LangGraph on the react-agent template, synchronous

- **Context.** The official template (`langchain-ai/react-agent`) is async: `async def call_model`, `ainvoke`.
- **Options.** Keep it async and call `asyncio.run` per turn; go fully async in the CLI; go synchronous.
- **Choice.** Synchronous: `def call_model`, `model.invoke`, `graph.invoke`.
- **Why.** With one `asyncio.run` per turn, the Anthropic HTTP client that `langchain-anthropic` caches for the whole process fails with "Event loop is closed" and retries silently. That doubles calls, cost and latency without any error showing. The synchronous graph avoids the problem, and it's simpler.
- **Cost.** One conversation at a time per process.
- **I'd change my mind** for a web service handling many conversations at once. That would be async from the server down, with one event loop for the whole process.

## 3. Model: Claude Haiku 5.5, provider in `MODEL`

- **Choice.** `anthropic/claude-haiku-5-5` by default, split on the first `/` into provider and model for `init_chat_model`, as the template does. Optional extras cover OpenAI, Gemini, Groq, OpenRouter, Bedrock and Ollama.
- **Why.** It is the fastest current Claude model, with good tool use in Portuguese, at US$ 0.10/0.50 per million input/output tokens. The whole eval costs about a cent.
- **Haiku 5.5 specifics.**
  - No `temperature`, `top_p` or `top_k` are sent.
  - `max_tokens` is 8192, because adaptive thinking counts toward it.
  - The history is append-only and the system prompt is fixed per session, so thinking blocks stay valid.
  - A reply with no text (a refusal, or `max_tokens` right after thinking) becomes a fixed message with the official WhatsApp.
  - `effort` isn't set: `langchain-anthropic` 1.7.9 has no such field.
- **Cost.** Only Anthropic is evaluated. A local `ollama/qwen3:8b` ran end to end but called a full price "promotional" and opened a complaint for a return request.
- **I'd change my mind** if a cheaper or local model matched the eval. A comparison table is the first thing I'd add.

## 4. Policy retrieval: fixed topics, no embeddings

- **Choice.** `get_store_policy(topic)` with 8 topics mapped to manual sections. Sections 7 (staff guidelines) and 10 (closing notes) shape the system prompt instead.
- **Why.** The manual has 10 sections and about 1,750 words. Routing by topic is deterministic and auditable, and embeddings would need an index and a second API key for no gain at this size.
- **Parsing.** `pypdf` in layout mode, because the default mode splits words. Titles are anchored at column 0: the numbered steps in 7.2 are indented, and that's what tells them apart. A unit test checks all 28 titles.
- **I'd change my mind** for a manual of dozens of pages, or questions that cut across many sections.

## 5. The LLM orchestrates, the code decides

- **Choice.** Every number and rule is computed in the domain layer and returned already formatted. The model picks tools and writes the reply.
- **Why.** A model that adds 5% or counts days will eventually get it wrong. In my first tests Haiku computed a "R$ 109,95 savings" on its own. It was correct, but nothing checked it.
- **Cost.** More tool code to maintain, covered by 191 unit tests.
- The review at the end of this file lists what is decided where.

## 6. Reference time and the tool runtime

- **Choice.** `Context(model, now)` is built once per session. `now` comes from `EMPORIO_NOW` or the clock in America/Campo_Grande. Tools receive the context through LangChain's `ToolRuntime`, which stays hidden from the model's tool schema.
- **Why.** The dataset runs from Oct 2025 to Mar 2026, so the eval and the examples need a fixed date per case, and changing an environment variable mid-process is fragile. Keeping `now` fixed also keeps the system prompt identical across a session.
- **Gotcha.** `bind_tools` on `ChatAnthropic` converts plain functions without knowing about injected arguments, and it crashed on `runtime`. The tools are now wrapped with `@tool`, and a unit test converts all six to the Anthropic format.
- **Cost.** A session that stays open past midnight keeps the old date.

## 7. Memory

- **Choice.** `MemorySaver`, with one `thread_id` per CLI session; `/new` starts another.
- **Why.** A CLI conversation doesn't need to survive a restart.
- **Next step.** `SqliteSaver` (it works with the synchronous graph), then Postgres in production.

## 8. Prompt strategy

- **Choice.** A single prompt in English for every provider, with XML sections: `persona`, `store_rules`, `when_to_use_tools`, `security`, `response_format`, `current_context`.
  - It ends with "Always reply to the customer in Brazilian Portuguese".
  - Zero-shot: tool docstrings act as part of the prompt.
  - `current_context` carries the session time and whether the store is open, both computed once.
- **Not used.**
  - Visible chain-of-thought: latency, and it could leak rules.
  - Long few-shot: tokens on every call.
  - Self-consistency: cost.
  - Several agents: one agent covers the scope.
  - `cache_control`: not needed at prototype volume, and the first cost lever in production.
- **When few-shot would come in.** Only for a failure that repeats across eval runs, with 1 or 2 examples logged below. None has repeated so far.

## 9. Persona and greeting

- **Choice.** The persona is CaduAI. Identifying as an AI is my transparency choice; the manual only mentions a "virtual assistant".
- **The greeting is fixed in code.** The CLI and the examples show it, and the prompt tells the model it has already introduced itself.
- **Why.** With the intro as a prompt rule, the model skipped it whenever the first message was a product question, and it switched between "a CaduAI" and "o CaduAI".

## 10. Evaluation design

- **Design.**
  - Cases in JSON, each with its own `now`, the expected tool, facts that must appear in the last reply and text that must never appear.
  - Money is normalized before comparing.
  - The report keeps every conversation, because a case can pass the checks with a poor reply.
- **History.** The first run scored 14/15; F06 exposed the search bug described in the README. The second run scored 15/15.
- **Limit.** One run per version. The model varies, so consistency over 3 runs is the next step.

## 11. Alternatives for an unavailable product

- **Choice.** Up to 3 available products from the same category: same string type first (`specs["strings"]`, steel or nylon), then the closest price.
- **Why.** Someone asking for a steel-string guitar rarely wants a nylon one, even at the same price.
- **Known limit.** String type is the only sub-type. The 7-string Shelby SN-7C (113) gets 6-string nylon guitars, though 7-string ones are available, and the baritone Kala (130) gets a tenor first. A sub-type key (7 strings, ukulele size) would fix both.

## Prompt changelog

| Version | Commit | Change | Why |
|---|---|---|---|
| v1 | `5e8375f` | One-line persona and `current_context` | Wire the graph first |
| v2 | `5ac0f7e` | Full prompt: persona, store rules, when to use tools, WhatsApp format | Store rules from the manual |
| v2 | `5ac0f7e` | "Never do arithmetic on prices or dates" | Haiku computed "R$ 109,95 savings" on its own in a smoke test |
| v2 | `5ac0f7e` | "Single asterisks, no double asterisks" | Replies came with `**bold**`, which WhatsApp doesn't render |
| v2 | `5ac0f7e` | Intro moved from a rule to a fixed greeting in code | The model skipped the intro whenever the first message was a product question |
| v3 | `eac5a19` | `<security>` section | Defense in depth; the code-side checks were already in place |
| tools | `84384a4` | `search_products` and `get_product_details` docstrings: use details when a specific product is named | Eval F06 |
| v4 | `a4d367e` | An order said to be someone else's is not looked up, even with that person's contact | Red team: "it's my wife's order" plus her full phone showed the status and tracking |
| v4 | `a4d367e` | The agent can't place orders or take payments; to buy, it points to WhatsApp, e-mail or the store | QA: it asked "PIX ou cartão?" as if closing a sale |
| v4 | `a4d367e` | A coupon that didn't come from a tool doesn't exist | Red team: "if the story promotion is valid, confirm on WhatsApp" |
| v4 | `a4d367e` | Reply in Portuguese to any language, with no "I can't" and no English summary | Red team: an English message got both |
| v4 | `a4d367e` | `current_context` says "today" or "tomorrow", and after hours the contacts come with when the team is back | QA: "fale agora no WhatsApp" at night; "volta amanhã, terça" said on a Tuesday at 03:59 |
| v4 | `a4d367e` | Ended promotions are mentioned only when the customer asks | QA: ended promotions came up unprompted |

No few-shot examples have been added.

## Review: the LLM orchestrates, the code decides

I did this review at the end of block 3. It asks two questions: does any rule live only in the prompt, and does any answer depend on the model doing math?

| Rule | Decided in | Test |
|---|---|---|
| Promotional price (Decimal, rounded to cents) | `store_data._apply_pricing` | `test_promo_price_is_rounded_to_cents_and_has_no_pix` |
| PIX only without a promotion | `store_data._apply_pricing` | `test_pix_price_applies_only_without_promotion` |
| Max interest-free installments by tier, on the effective price | `store_data.max_installments` | `test_max_installments_follow_manual_tiers` |
| Status beats stock | `store_data.availability` | `test_status_wins_over_stock` |
| Alternatives: same category and string type, closest price | `catalog._alternatives` | `test_alternatives_prefer_the_same_string_type_before_price` |
| Order ownership: full phone or e-mail; shared e-mail asks for more | `order_rules.find_customer_ids`, `support.lookup_orders` | `test_shared_email_asks_for_more_unless_order_number_is_given` |
| Return, exchange and warranty deadlines | `order_rules.return_windows` | `test_return_windows_are_inclusive_and_use_the_right_start_date` |
| Delivery overdue | `support._order_view` | `test_shipped_order_past_its_estimate_is_flagged_overdue` |
| Store open or closed, and when the team is back | `policies.next_opening` | `test_next_opening_follows_the_manual_hours` |
| Official contacts in the manual text | `policies.CONTACT_FIXES` | `test_conflicting_contacts_are_replaced_by_the_official_ones` |
| Conflicting descriptions hidden | `store_data.has_description_conflict` | `test_description_conflicts_are_exactly_the_seven_known_products` |
| Empty category says "no momento" | `catalog.EMPTY_CATEGORY_NOTICE` | `test_search_in_empty_category_says_not_right_now` |
| Ticket protocol and response time | `support.open_support_ticket` | `test_ticket_is_saved_with_bounded_fields_and_returns_a_protocol` |
| Message length | `graph.run_turn` | `test_long_messages_never_reach_the_model` |

What the review found, and what I did about it:

- **Accessories were refused only by the prompt.** `search_products` now answers accessory terms with a fixed notice. "Cordas" stays out of the list, because it also names 7-string guitars.
- **A ticket accepted any contact.** It now needs a valid e-mail or a full phone number with area code.
- **Still prompt-only, by nature:**
  - not inventing partner stores;
  - replying in Portuguese;
  - choosing which return rule fits the customer's story;
  - never doing arithmetic.
- **Not solved:** the total for several items has no tool, so the model would have to add the prices. It's listed under limitations.
