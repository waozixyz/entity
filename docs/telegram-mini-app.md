# Telegram Mini Apps

Entity’s `entity/telegram_mini_app` export defines the client contract for a
signed-in Entity host. The Telegram Mini App supplies its raw `WebApp.initData`
query string. The issuer verifies it for the configured app and bot, then
returns launch parameters safe to expose to application code. Entity continues
to use the existing account sign-in and wallet. [Telegram Mini Apps](https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app)

The routes below require a compatible issuer. The client fixture exercises the
contract with synthetic replies. It makes no Telegram or issuer network calls.

## Launch and catalog

Send requests over HTTPS to the signed-in account’s configured, trusted wallet
issuer. Use the existing bearer session for an owner account. A hosted Mini App
uses `Authorization: Delegate ds1.<session_id>` with the existing per-request
`X-Mesh-Delegate` proof. The owner separately approves the ability to read the
Dew balance and buy through Telegram. Its signed grant has `telegram_stars: true`
and appends `telegram-stars-purchases\n` (one LF) to the canonical grant message
after the existing scope lines. Continue signing the existing message for grants
that omit the flag. A Telegram-linked Lumi-only delegate can verify launch and
receives `stars_available: false`. The hosted capability covers its own invoice
and read-only balance routes. Keep raw `initData` and session credentials
in memory for the request. Exclude them from logs, telemetry,
URLs, and persisted browser state. The browser can use Telegram SDK presence for
layout. Use the issuer’s validated data for app routing and purchase availability.

| Method and path | Request | Successful response |
| --- | --- | --- |
| `POST /api/v1/telegram/launch` | `{app_id, init_data}` | `{app_id, start_param?, chat_type?, stars_available}` |
| `GET /api/v1/tokens/purchases/telegram/catalog?app_id=APP` | No body | `{currency: "XTR", products: [{product_id, title, amount, units}]}` |
| `GET /api/v1/tokens/purchases/telegram/balance?app_id=APP` | No body | `{account_id, app_id, asset_id: "waozi:token", balance}` |

`start_param` is an optional URL-safe token of up to 512 bytes from the verified
launch. Interpret it with an app-defined allowlist, for example to prefill an
invitation or navigate to a known screen. Require normal app confirmation for
side effects. `chat_type` is optional (`sender`, `private`, `group`, `supergroup`,
or `channel`). A valid launch may have neither optional field. The contract
exposes no Telegram user or chat ID. `initDataUnsafe`, browser query parameters
and `invoiceClosed` carry no account or purchase authority.

Show Stars offers when `WebApp.openInvoice` is available, the issuer returns
`stars_available: true`, and the catalog has products. `amount` is a whole number
of Stars and `units` is the amount the issuer credits in wallet units. For Dew,
one Dew is 1,000,000 units. Display both from the catalog and render the title
as text. The issuer configures an explicit XTR price for each enabled canonical
pack. Telegram requires XTR for digital purchases in Mini Apps. [Telegram Stars payments](https://core.telegram.org/bots/payments-stars)

## Invoice and settlement

| Method and path | Request | Successful response |
| --- | --- | --- |
| `POST /api/v1/tokens/purchases/telegram/invoices` | `{app_id, product_id, request_id, init_data}` | `{invoice_id, invoice_url?, product_id, currency: "XTR", amount, units, status}` |
| `GET /api/v1/tokens/purchases/telegram/invoices/ID` | No body | Same invoice record, with `invoice_url` optional |
| `POST /api/v1/tokens/purchases/telegram/invoices/ID/cancel` | No body | Same record. HTTP 409 if checkout was approved and is pending. |

Generate a fresh unpredictable `request_id` for each confirmed purchase and
retain it with the selected terms in that account’s purchase state. Retry an
uncertain response with the same ID and product. Keep IDs scoped to the owner
and app. On account or issuer change, discard pending UI replies, close the
purchase dialog and clear its catalog and launch data. Revalidate after sign-in.

Launch verification uses the configured bot, checked freshness, and a
server-verified binding to the account. The issuer rejects duplicate decoded
fields and protects account binding against replay. The signed parameters remain
valid input for a purchase within the issuer’s freshness window.

The issuer resolves the pack and price server-side and binds the quote to the
verified Telegram buyer, bot, app and signed-in Entity account. It creates the
invoice with Telegram’s `createInvoiceLink`, currency `XTR`, one price item and
an empty provider token. The opaque invoice payload identifies the stored quote.
The creation reply for a pending invoice includes its HTTPS `t.me` invoice link.
[Telegram Bot API](https://core.telegram.org/bots/api#createinvoicelink)

The web bridge calls `WebApp.openInvoice(invoice_url, onClosed)` with the link
from a verified issuer response. Its callback reports `paid`, `pending`,
`cancelled`, or `failed`. Treat these as dialog states and refresh the invoice
status through the issuer. A dialog can close while the issuer still shows
`pending`. A distinct deliberate purchase uses a distinct `request_id`.
[Mini App events](https://core.telegram.org/bots/webapps#events-available-for-mini-apps)

| Issuer status | UI behavior |
| --- | --- |
| `pending` | Await the payment result. A valid URL can open checkout. |
| `credited` | Reload the wallet balance. Owner sessions can reload the ledger. |
| `cancelled`, `failed`, `expired` | Show the issuer’s outcome. |
| `refunded` | Reload the wallet to reflect the verified reversal. |

The issuer settles invoices using authenticated Telegram payment events or
transaction history. It checks Telegram’s webhook secret on incoming updates
and validates the bot, stored payload, buyer, currency and exact amount. Reply
to `pre_checkout_query` within ten seconds. A successful
payment commits the canonical wallet credit and a unique Telegram charge ID in
one transaction. Repeated deliveries return the existing result. A payment
that succeeds after the client has closed still settles. An unconfirmed invoice
can expire server-side without a grant. A verified refund reconciles the original
charge through the wallet’s reversal flow. For recovery, reconcile authenticated
transaction history through the same charge identity and settlement rules. Use
`refundStarPayment` with the stored buyer and charge ID for merchant-initiated
refunds. When the merchant bot also handles other updates, dispatch payments
through its existing webhook. [Webhook configuration](https://core.telegram.org/bots/api#setwebhook) · [Checkout and refund](https://core.telegram.org/bots/api#answerprecheckoutquery) · [Transaction history](https://core.telegram.org/bots/api#getstartransactions)

## Ziran interface

Import `entity/telegram_mini_app`. Use `TelegramLaunchPath` and
`TelegramStarsInvoicesPath` for the POST routes. The functions below implement
request construction and response validation. The host supplies authenticated
transport and checks that each response still belongs to the current account
and issuer. Parse only successful issuer responses.

```zi
Telegram :: #import "entity/telegram_mini_app";

launch: Telegram.TelegramLaunchContext
catalog: Telegram.TelegramStarsCatalog
invoice: Telegram.TelegramStarsInvoice
body: Vec(u8)

// Encode within the authenticated host, send, then clear its request buffer.
if Telegram.TelegramLaunchRequest(app_id, init_data, *body) {
    // POST body to Telegram.TelegramLaunchPath.
}
if Telegram.TelegramReadLaunch(launch_reply, app_id, *launch) && launch.stars_available &&
    Telegram.TelegramReadStarsCatalog(catalog_reply, *catalog) && catalog.count > 0 {
    // Show catalog.products[:catalog.count] and let the user confirm an offer.
}

// Copy the confirmed product and retain it with the purchase request ID.
if Telegram.TelegramReadStarsInvoice(create_reply, *confirmed_product, "", *invoice) &&
    invoice.state == .Pending {
    // Open the returned link through the Telegram bridge.
}
```

Use `TelegramStarsCatalogRequestPath` for the catalog and
`TelegramStarsInvoiceRequest` for creation. Use `TelegramStarsStatusRequestPath`
for refresh and `TelegramStarsCancelRequestPath` for explicit cancellation.
Give `TelegramReadStarsInvoice` the recorded invoice ID and
the same `TelegramStarsProduct` confirmed at creation. The parser rejects a
mismatched product, price, wallet quantity, currency or invoice ID. URL fields
are exposed only for pending invoices. `TelegramInvoiceClosedState` returns a
separate `TelegramInvoiceClosed` type for the browser callback.

Use `TelegramStarsBalanceRequestPath` and `TelegramReadStarsBalance` to update
the wallet after settlement. Pass the expected account ID and app ID from the
current session. The parser checks both and the canonical Dew asset. The signed
balance can be negative after a refund of already-used Dew.

Each reply is one JSON object of at most 16 KiB. The catalog may contain up to
32 products with distinct IDs. Each title can be up to 128 bytes. The SDK uses
ASCII letters, digits, underscores, hyphens and periods for IDs, with at most
64 bytes for app IDs and 128 bytes for product and request IDs. Invoice IDs use
32 lowercase hex digits and account IDs use 64. Use a random UUID or equivalent
for the request ID. Report offer quantities as JSON
integers in the positive JavaScript safe-integer range.

## Issuer compatibility tests

Run the issuer tests against a disposable wallet with signed test launch data
and a fake Telegram transport. Exercise the same JSON endpoints the host uses.

| Fixture | Expected result |
| --- | --- |
| Fresh signed launch for the bound buyer and bot | The reply carries the expected app and only its safe launch fields. |
| Stale launch, duplicate decoded fields, bad signature or an unbound buyer | The issuer rejects the request without issuing purchase authority. |
| Matching purchase-only delegate, Lumi-only delegate or a different owner | Only the matching purchase delegate can purchase and read its own result and balance. General wallet mutations reject both delegates. |
| Repeated purchase request with the same ID | The same terms return the same invoice. A changed product conflicts. |
| Authenticated pre-checkout for a stored invoice | A matching buyer, amount, currency and payload can proceed. Wrong terms and unauthorized webhooks are rejected. |
| Closed or expired checkout with no successful payment | The wallet receives no grant. |
| Repeated successful payment from Telegram, including a concurrent retry | The owner receives one ledger credit. The repeat reports the same settlement. |
| Verified refund, including repeated receipt | The original credit is reversed once. |

Return the validated `invoice_url` with a newly created pending invoice. A
status read may omit it while still pending. Send wallet units and Stars as
integers. Return an error when the owner, app or issuer authorization fails.

Run `make -j1 telegram-mini-app-test` for the same request, launch, catalog and
invoice fixtures in C and the portable VM. The synthetic catalog contains a
fictional XTR amount. Deployment needs the bot and approved per-pack prices,
registered Mini App URL, webhook secret and enabled issuer configuration.
The merchant also needs a `/paysupport` response and customer support for
refunds. [Telegram merchant requirements](https://core.telegram.org/bots/payments-stars#going-live)

A Telegram test account and test bot use the separate Bot API `/test/` path and
separate issuer state. The local fixtures emulate the provider and require no
Telegram account. [Telegram test environment](https://core.telegram.org/bots/webapps#using-bots-in-the-test-environment)
