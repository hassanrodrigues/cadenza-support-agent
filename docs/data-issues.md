# Data issues and assumptions

I profiled the six CSVs and the policy manual before writing any code. Most conflicts below are resolved in code and tested; the Where column shows the ones handled in the prompt or only documented.

## Catalog and promotions

| Issue | Evidence | Decision | Where |
|---|---|---|---|
| Status and stock disagree | 96 Giannini GF-3D: `active` with 0 stock. 113 Shelby SN-7C: `discontinued`, 0. 136 Ibanez Bass 2X: `discontinued` with 13 units, at R$ 441 against R$ 7,157+ for the other basses. 130 Kala KA-ABP-CTG: `coming_soon` with 2 units, yet it appears in orders 3 (delivered) and 14 | Status beats stock: `discontinued` and `coming_soon` are not for sale; `active` with 0 stock is out of stock, with alternatives | `store_data.availability`, `test_status_wins_over_stock` |
| Name and description name different brands | 7 products in categories 2 to 4. 135 "Music Man" is described as a "Fender Jazz Bass"; 137 "Yamaha" as a 5-string Ibanez with 4 strings in its specs; 140 "Pearl" as a "Tama, 100% Birch" with Maple shells; 142 "Korg" as a "Roland" with 88 keys but 61 in its specs | Identity comes from name and specs. These descriptions never reach the model or the search index. The rule is "brand in the name missing from the description", after skipping prefixes like "Bateria Acústica". It applies only to categories 1 to 4, because guitar and ukulele descriptions rarely name a brand | `store_data.has_description_conflict`, `test_description_conflicts_are_exactly_the_seven_known_products` |
| Categories with no products | 6 (woodwinds), 7 (brass) and 8 (orchestral strings) are empty, though the manual says the store sells them | "No momento não temos", never "não vendemos" | `catalog.EMPTY_CATEGORY_NOTICE`, eval F07 |
| Promotions have no dates | None of the 25 promotions has a start or end date | Active means `is_active=1`, so only 4 are active (products 127, 121, 90, 94). Inactive ones count as ended and are shown as "ended" when the customer asks | `store_data._apply_pricing`, eval F05 |
| Promotion percentages outside the manual's ranges | Black Friday at 10% (manual: 15 to 30%), Aniversário at 30% (manual: 10 to 25%) | The system data (CSV) sets price and discount; the manual describes campaigns in general | `store_data._apply_pricing` |
| Several promotions per product | 93, 96 and 99 have two each, all inactive | The highest active discount would win, since promotions never stack | `store_data._apply_pricing` |
| Catalog size | The manual says "more than 300 instruments"; the catalog has 65 | Availability comes only from the catalog tools; the policy tool adds a note saying so | `policies.TOPIC_NOTES` |
| Typo in a product name | 84 is "Giannini GN-15 Nylon Cedr Natural" | Left as data; the model sometimes writes "Cedro" | none |
| Rounding to the cent | Promo, PIX and installment values are rounded HALF_UP. For 12 prices ending in ,90 the PIX price is 1 cent above HALF_EVEN (product 81: R$ 569,91 against R$ 569,90), and for 31 products n × installment differs from the price by −5 to +4 cents | HALF_UP everywhere; the customer sees the rounded values the tools return, never a recomputed one | `store_data.to_money`, `store_data.max_installments` |

## Orders and customers

| Issue | Evidence | Decision | Where |
|---|---|---|---|
| Totals differ from the current prices | Order 3: R$ 3,450 against 2 × R$ 1,749. Order 20 (cancelled): R$ 1,400 against R$ 1,488. `order_items` has no unit price | The agent reports the recorded `total_brl` and never recalculates: without unit prices, there's nothing to audit against | `support._order_view` |
| Old orders break the installment rules | Order 9: 6x R$ 58.32. Order 16: 6x R$ 71.65. Order 18: 12x R$ 38.33 | Historical data; the agent doesn't reprocess past orders | none, documented only |
| Delivery date | Only `estimated_delivery` exists, and only for shipped and delivered orders | Assumption: every order is an online purchase (they all have shipping), and the delivery date is `estimated_delivery` | `order_rules.return_windows` |
| Overdue shipment | Order 8 is `shipped` with an estimate of 28/02/2026 | Flagged `delivery_overdue` when the estimate has passed | `test_shipped_order_past_its_estimate_is_flagged_overdue`, eval F09 |
| Orders after "now" | The dataset runs to 22/03/2026 | Orders dated after the session's reference time are ignored | `test_orders_after_the_reference_time_are_ignored` |
| Shared e-mail | Customers 11 and 43 share bruno.martins@jmail.com; only 11 has an order (10) | An e-mail that matches more than one customer asks for the phone or the order number | `test_shared_email_asks_for_more_unless_order_number_is_given` |
| Phone format | All 50 phones have 11 digits; 55 is both Brazil's country code and a valid area code | Strip a leading 55 only when 12 or 13 digits remain; require the full number with area code | `order_rules.normalize_phone` |
| Phone with a leading 0 | "0 67 99789-0123" (long-distance prefix) has 12 digits | Refused as incomplete: the rule accepts 10 or 11 digits, or 55 plus 10 or 11 | `order_rules.normalize_phone` |
| PIX orders at list price | Orders 1, 5, 10, 13 and 17 were paid by PIX, but their totals equal the list price, without the 5% | The agent reports the recorded total and never recalculates | `support._order_view` |
| No shipping fee on small local orders | Orders 7, 8, 9, 11 and 16 are under R$ 500 from Campo Grande customers, and none includes the R$ 35 fee (manual 5.1) | Same: the recorded total stands | none, documented only |
| Local deliveries by post | Campo Grande orders took 7 to 11 business days with Correios tracking; the manual promises a courier in 1 to 3 business days | Consistent with treating every order as shipped; deadlines use `estimated_delivery` | `order_rules.return_windows` |
| Promotional items at full price | Orders 2 (product 94) and 11 (product 127) include items on an active promotion today, charged at full price | Promotions have no dates, so I can't tell whether they were active at purchase | none, documented only |
| Reference time before delivery | With `EMPORIO_NOW` earlier than a delivered order's estimated delivery, `days_since_delivery` is negative and the regret window shows as open | Only happens with a pinned clock earlier than the data; left as is | `support._order_view` |

## Policy manual

| Issue | Evidence | Decision | Where |
|---|---|---|---|
| Two WhatsApp numbers | (67) 3341-4444 on the cover and in table 1.2; (67) 3321-4500 in section 7 | (67) 3341-4444, which appears in 2 of 3 places, including the company data table. The other is replaced when the manual is loaded | `policies.CONTACT_FIXES`, `test_conflicting_contacts_are_replaced_by_the_official_ones` |
| Two e-mails | `contato@emporiodamusica.com.br` on the cover; `contato@empóriodamusica.com.br` (accented) in table 1.2 | The unaccented one: an accented domain is unusual and most likely a typo | same |
| Installment rules disagree | The table says "up to 12x, minimum R$ 100". Section 3.1 has tiers: up to 3x "no minimum (except below R$ 50)", 4x to 6x R$ 80, 7x to 12x R$ 100 | Section 3.1 is more specific and wins. Up to 3x is read as a R$ 50 minimum. Installments use the effective price (the promotional one when active). The policy tool sends a note with the resolution | `store_data.max_installments`, `policies.TOPIC_NOTES` |
| "Preference" exchange window | Section 4.3 gives "7 days" with no start date | Read as 7 days from delivery, like the regret window | `order_rules.PREFERENCE_DAYS` |
| Partner stores | Section 7.1 says to suggest partner stores, but the manual names none | The agent never invents one | prompt, example 5 |
| "Final sale" items | Section 4.4 excludes them from exchanges, but the data has no such flag | Not checked; listed under limitations | none |
| Holidays | The store closes on holidays; the `holidays` package doesn't cover Campo Grande's municipal holiday (26/08) | Not checked yet; the prompt says so in `current_context` | limitation |
| Business hours vs. an always-on assistant | The manual describes staff hours | Assumption: the assistant answers any time, but out of hours it says when the team is back for anything that needs a person | `policies.next_opening`, eval F08 |
