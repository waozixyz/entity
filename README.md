# Entity

Entity is one portable profile app shared by Inner Breeze, Werkzeug and standalone Shovey/Arcade. It also
runs independently with its own native account provider. The portable profile
preferences also run in Kryon's generic ZX player, without account capabilities.

```sh
make test
make run
```

Dependencies use `ziran.toml` and `ziran.lock`. Local development overrides belong
in the ignored `ziran.local.toml`. The locked compiler uses Ziran IR55.

## Hosting

The bundle identifies as `entity` and uses Kryon's standard app protocol. Hosts
provide the versioned `entity.json` preferences document through ordinary scoped
`ReadStoreHost` and `WriteStoreHost` calls. The `entity/model` export encodes and
validates that document. It contains display preferences and node origins;
account keys and tool secrets stay with the host.

Hosts select the available controls and picture choices, supply localized labels
through `AppLocaleHost`, and add named extension routes. Entity returns a route
through `AppReply`; the host accepts only its own routes. Send the `reload`
command after returning from an extension. Run `APP_SAVE` before leaving Entity
and keep the page open if saving fails. Hosts that supply their own title and Back
control set `host_navigation` in `EntityState`; Entity then omits its duplicate
navigation. Standalone Entity keeps its own navigation.

The default node is `https://api.waozi.xyz`. Selecting a node does not create an
account or enable synchronization. A host maps the node selection to its own
existing account and storage operations.

The optional `entity.assets` service supplies an absolute extracted asset root to
hosts that need one. Other hosts use the bundle-relative `assets/entity/` paths.
The picture atlas comes from Kryon and the flower picture from Inner Breeze.

Embedding hosts may stage `asset-groups.json` through
`scripts/stage-assets.py --group profile --output HOST_STAGING`. The `profile`
group keeps ordinary picture choices; `leaderboard` adds optional game imagery.
Full builds retain both. The native `entity.asset` service answers `available`
only for a safe bundle-relative asset present in the current verified bundle,
and `missing` otherwise. Leaderboards use the ordinary profile picture when
optional game imagery is absent, including after updating a fuller install.

## Visual reference and checks

The generated [design reference](design/entity-reference.png) informed the native
widget implementation; it is not a screenshot of the running app. The generation
mode and prompt are recorded in [design/prompt.txt](design/prompt.txt).

`scripts/ui_test.py PLAYER BUNDLE [--narrow]` exercises editing, the picture
picker, node validation, adding, selecting, removing, and persistence after a
restart. Run it only on a private display with `ENTITY_PRIVATE_DISPLAY=1`.

## Account management

The optional `entity.management` service provides bounded public account status,
node usage/media preferences, and a capability mask. Requests carry a strictly
increasing sequence and the current verified owner ID. Providers enqueue them
during the VM run and execute them afterward. They reject stale identities and
never replay deferred actions. Native hosts supply their own file chooser callback, including deferred mobile
pickers, and resume it after a platform result. Private keys, native file paths and record-vault
material stay in the native host. See `management.zi` and `native_management.zi`.

The shared UI includes account IDs and aliases, encrypted key backup/import,
QR/device connection, explicit merge/replace choices, sync status/controls where
the host supports them, logout, and confirmed remote deletion. Hosts expose only
capabilities they implement. Extension cards can include a summary and badge.

Public IDs use the full text where the host font and available width allow it.
Pressing an ID opens a dialog with its scannable QR code and complete text;
pressing that text or Copy copies the full public ID. Narrow views shorten
only the inline label. The dialog follows the current account and closes
when that account changes.

In the browser every waozi.xyz site shares one sign-in. A page that loads
https://account.waozi.xyz/share.js and calls `WaoziAccount.attach(Module)`
before starting gives Entity the shared key as `Module.sharedAccountKey`; a
site without its own account signs in with it, and signing in, creating an
account, linking a device or logging out is passed back through
`Module.shareAccount`. A site keeps its own account if it already has one.

Recovery retains the existing plain and passphrase-protected Daochi key formats.
An optional protected native context preserves Werkzeug's record vault across
backup/import and new shared QR transfers. Plain-key QR transfers retain Inbe's
existing payload. Receivers validate the account keys before import. Older Inbe
versions cannot read a QR payload carrying the new recovery context.

Standalone Entity stores private files under `$XDG_DATA_HOME/entity` (or
`~/.local/share/entity`); `ENTITY_DATA` selects a fixture/profile directory. Desktop
hosts can share public name, intention, picture and node preferences under the
same verified account ID through `SharedProfileLoad`/`SharedProfileSave`. Different
account IDs stay separate. This local sharing does not share credentials or
claim cross-device profile sync. Android and browser app sandboxes retain host
storage. Standalone Entity does not advertise sync or quota data it has not fetched.

`scripts/native_test.py` checks native recovery compatibility, tamper rejection,
QR payloads, cancellation, one-time actions and account-scoped persistence.
`scripts/native_ui_test.py` checks the standalone native account flows and must
run with `ENTITY_PRIVATE_DISPLAY=1` on a private Xvfb display.

## Entity records

The `entity.records` app service (`entity/entity_records`) keeps the account's
own records of each kind an app names, such as Shovey's level drafts in
`private.entity.v1.levels` (Daochi `docs/entity-data.md`). Requests (`list`,
`get`, `put`, `delete`, `status`) answer at once from the device's copy, so a
save never waits for the node; the native host then syncs the records in the
account's signed sync as the `entity` app, sealed with the record key of
their kind. Records saved before an account is connected stay on the device
and become that account's own once it is. Documents are JSON objects of at
most 140 KiB. Native hosts route the service and call `EntityHostPump` each
frame. `make records-test` checks one device and two devices of a throwaway
account through a private local Daochi node.

## Collection sharing client

`entity/collection_client` owns one publications request per `CollectionClient`
instance. It uses the existing `entity/level_collections` wire builders and
does not change the service or node protocol. Configure `service` with a
`CollectionClientService(context: *void, service: string, request: string) -> string`
adapter to the host's current public app service, and `owner` with a
`CollectionClientOwner(context: *void) -> string` callback returning the current
verified public owner ID or a stable local-profile identity. An empty owner
means signed out. Callbacks run synchronously on the frame thread; do not
reenter the client, except to Reset/Cancel from the service callback. Keep the
callbacks and context stable until Reset. Neither callback receives keys.

Build a request with `CollectionPublishRequest`, `CollectionUnpublishRequest`,
`CollectionFindRequest` or `CollectionFetchRequest`, then call
`CollectionClientStart(client: *CollectionClient, operation: CollectionClientOperation,
request: string) -> CollectionClientResult`. The operation enum is `Publish`,
`Unpublish`, `Find` or `Fetch` and must match the request exactly. Start copies
the request and queues it; it returns `Pending` without calling the service.
Starting while pending returns `Busy` in that call's result and preserves the
active request. Free the caller's request builder normally after Start.

Call `CollectionClientPump(client: *CollectionClient, now: s64) -> CollectionClientResult`
with monotonic milliseconds. Pump sends at most one service request: first the
original operation, then only `status` with the same provider request number.
`poll_delay` defaults to 1000 ms; a positive value changes the interval and a
negative value allows a poll on every Pump. No mutation is automatically
retried. A pending status may omit its number; a supplied number must match.
States are `Idle`, `Pending`, `Done`, `Failed`, `Rejected`, `Unavailable` and
`Cancelled`. Results carry the operation, request number, typed error and up to
47 bytes of the provider's error code in `detail`. Remote errors map to
`SignedOut`, `Offline`, `NotFound`, `Forbidden`, `TooLarge`, `Invalid`, `Busy`
or `Remote`; local failures also include `Malformed` and `OwnerChanged`.

`CollectionClientReadReply(client: *CollectionClient, output: *Vec(u8))` clears
and copies the retained terminal wire reply into caller-owned output. Replies
are fully parsed as JSON, checked for their operation's completion envelope,
and retained within 512 KiB; `reply_limit` can lower this bound. Requests are
limited to 256 KiB and owner identities to 128 bytes. There is no partial reply
on overflow or malformed input. Apps still validate publication metadata,
collection documents and game rules, and choose all translated UI messages.

Pump checks ownership before sending, after calling the service, and before
returning a retained completion. Owner changes discard old results. Call
`CollectionClientReset(client: *CollectionClient)` on logout/relogin, even if
the public owner ID stays the same, and before disposing or reconfiguring an
instance. `CollectionClientCancel(client: *CollectionClient)` clears local
interest with a `Cancelled` result. Reset/Cancel release owned buffers and
invalidate a reply arriving during the service callback. An accepted provider
operation may still finish; these functions do not undo publications.

`env -u DISPLAY -u WAYLAND_DISPLAY make -j1 collection-client-test` runs the
fake-transport lifecycle tests, existing wire helper tests and a portable VM
smoke test without accounts or network access.

## Standalone hosts and Dew

The `entity/native_host` export opens the same profile bundle for native hosts.
The host supplies its private account directory and client name; embedded game
collections carry no Entity bundle or account store. Run `EntityHostPump` after
VM frames, save before closing the profile, and keep the page open if saving
fails. Hosts that draw navigation pass `host_navigation = true` to
`EntityHostOpen`.

Native hosts expose the shared intention field and can use
`EntityHostDewAvailable` and `EntityHostDew` for a direct Dew entry. Dew uses
the host's existing Back control when the host supplies navigation.
Hosts that draw their own top-up page, such as dew.waozi.xyz, read the
balance and the account's Monero funding address with `EntityHostDewStatus`
and ask the node for either with `EntityHostDewRequest("refresh")` or
`EntityHostDewRequest("address")`. `EntityHostDewRequest("deposits")` lists
the account's recent Monero deposits for `EntityHostDewDeposits`.
`scripts/build-web.py` links such a host without `--bundle`.

The Profile's Top up opens https://dew.waozi.xyz/?account=ID for the signed-in
account (the Dew shop's "Buy N Dew with another coin" adds `&dew=N`) when the host is a native Entity host; hosts that answer Dew actions
themselves keep their own top-up. A host that is the top-up page passes an
empty `EntityHostTopUpUrl` and reads `EntityHostTopUpRequested` instead.

On the Waozi node, connected native profiles can read their Dew balance, obtain
their Monero funding address, and confirm a node-priced storage plan. Purchases
are saved before sending. An uncertain result retains its request ID for an
explicit retry; it never becomes a new debit. Switching or logging out cancels
the old account's in-flight requests. The `entity/dew_model` export shares strict
integer balance, allowance and funding-address validation with Inner Breeze.
Game hosts can also expose `entity.game-shop` from `game_shop_native`. Its fixed
Apfelwurm cosmetics cost 10, 20 and 30 Dew. `status` and `refresh` return the
current public owner, device ID, ownership mask and request status; naming a
product (`wurm.mint`, `wurm.berry`, `wurm.rose`) buys it after the game confirms
the price. The provider uses authenticated Dew spending with one stable key
per account and product. Retrying from another device cannot debit twice.
Ownership is restored from exact ledger receipts; enqueueing or a failed
request never grants a skin. Hosts call `EntityGameShopPump` after frames
(included in `EntityHostPump`).
Hosts that already expose `entity.dew` can use the same service through
`shop:REQUEST`; `EntityDewPump` advances it. The fixed `shop:visit` request
queues opening `https://waozi.xyz/` after the guest frame.
`python3 scripts/game_shop_test.py` verifies authenticated purchases, duplicate
retries, fresh-device restoration and account isolation on a private local node
with throwaway keys and Dew.

The Profile shows Inbe's shared `DewBalance` card inline. Native game hosts hide storage usage, storage plans and node media-storage controls; Inbe retains its storage indicator and actions. The picture modal offers Abstract and Classic choices with large thumbnails. Both picture families publish the chosen picture for Friends and Leaderboard through the authenticated public profile metadata. Game hosts hide the
Name and Intention fields and identify players by their alias or public ID.
The browser host uses Kryon's existing `BundleApp` lifecycle, IndexedDB-backed
files and the same native Entity account provider; game bundles receive only
a navigation service and never see account keys. `scripts/build-web.py` links
this provider for browser applications with the locked cryptography packages.

## Google Play Dew pricing

The 10 Dew pack uses a 20% premium over the node's current Monero value,
rounded up to a clean local price. The larger packs retain their bulk rates:
100 Dew at 15%, 500 Dew at 10%, 1,000 Dew at 5%, and 5,000 Dew at the base value.
Existing products are changed only when their prices are explicitly provisioned.

Purchase screens show savings per Dew against the 10 Dew pack, calculated from
Google Play's actual prices in the same currency. Whole percentages round down;
missing prices, currency mismatches and packs without savings have no badge.
Regional rounding can change the displayed percentage. `--pack 10 --apply`
provisions only the small pack and leaves the other prices unchanged.

## Shared game progress

`entity/game_progress` defines `entity.game-progress.v1` records in the
`game-progress` kind. Native account providers use `entity/game_progress_id` to derive one stable 32-digit
record ID from the game's stable name, independent of its wrapper or device.
The record service derives this ID when omitted and rejects another ID, so
standalone and hosted games use the same account record. Portable games get
that record with `{"operation":"get","kind":"game-progress","game":NAME}`;
they do not implement record IDs or account cryptography.

A document contains `game`, `unlocked` (1–4096), a `completed` string of up to
4096 zero/one marks, and `updated_at`. Unlocks take the maximum and completion
marks are combined, including newly discovered marks in older replies. Legacy
`state` fields are ignored and never serialized: unfinished boards, positions,
lives, scores and run state remain device data.

`entity/game_progress_client` supplies the reusable owner-bound lifecycle:

- Configure `service(context, service, request) -> string` and
  `owner(context) -> string`, matching the collection client's host convention.
  The owner is a verified public identity, never an account key. The service
  adapter must keep requests bound to that identity through account transitions.
- Supply `persist(context, owner, record, pending) -> bool`. It must durably save
  the earned record and pending marker together in the caller's own schema and
  owner namespace. It must not navigate, switch profiles or publish run state.
- `GameProgressClientBind(client, owner, record, pending)` copies this owner's
  already durable earned save, including caller-selected legacy migration data.
  Empty owner means guest: persistence runs locally with no account service.
  Never seed a new account with the previous owner's device campaign.
- `GameProgressClientQueue(client, earned)` copies and monotonically merges only
  earnings selected by the game. Its result is pending until Pump persists them;
  callers must wait for `durable=true` before acknowledging local earnings.
- `GameProgressClientPump(client, now, allow_read)` takes monotonic milliseconds,
  persists pending earnings before upload, hydrates before the first put, and
  polls exact provider request IDs. `allow_read=false` defers gets and their
  status polls during active play; persistence and hydrated puts still proceed.
  Zero poll/read delays select 1000/5000 ms; negative delays disable waiting.
- `GameProgressClientRead(client, output)` copies the merged earned snapshot for
  caller-controlled adoption. `Reset` drops the binding and any request interest;
  call it on logout/relogin even for the same identity. Owner changes return
  `OwnerChanged` and require an explicit new Bind with that owner's local save.

The result exposes `state`, `error`, provider `request`, `hydrated`, `dirty`, and
`durable`. `Acknowledged` means a provider put returned done and its pending
marker was durably updated locally. It does **not** mean remote account sync;
legacy-copy retirement must still use the provider's actual sync evidence.
Earnings queued while a put is pending stay dirty after its acknowledgement.
Failed persistence is retried without issuing an upload or advertising a durable
acknowledgement. Failed service attempts retain earnings and retry with the poll
delay; only a valid done/missing read establishes hydration. Replies are bounded
(default/hard maximum 32768 bytes); `reply_limit` may lower that limit.
Callbacks are synchronous and must not reenter the client. Borrowed input and
reply storage is copied before subsequent callbacks can overwrite host scratch.

Game integrations remain responsible for their publication policy (Shovey wins,
Wurm completions and migrated unlocks, Choano growth stages), local resume and
reward schemas, and when/how to adopt a hydrated snapshot. No consumer migration
is included in this module. Run `make -j1 game-progress-client-test` for the same
fake-host lifecycle cases through native source and portable `.zx` execution.

Older Shovey saves can retain earned reward eligibility during the node's
security upgrade. After an eligibility refusal, the native provider attempts
one migration of the account's frozen pre-upgrade progress and retries the
normal claim once. It validates the frozen encrypted record locally and sends
only that random version's nonce-prefix opening subkey; account private keys
and reusable record keys stay on the device. The node retains earned unlocks
and completion marks separately from new route evidence. Migration never
credits Dew, and normal claims remain once per account. Missing snapshots and
connection failures remain visible failures rather than successful claims.

## Shared leaderboard

Leaderboard lives inside Profile. Hosts provide `entity.leaderboard` with a
bounded `ProfileLeaderboard` snapshot from `entity/leaderboard_model`: installed
boards, the selected board, and ranked friend rows. Selection requests carry
the snapshot's owner, a listed board ID and metric. A host rejects stale owners
and boards it no longer has installed. The `leaderboard` command opens the page;
Back returns to Profile. Labels use the host's existing leaderboard translations.

Native game hosts use `entity/leaderboard_native`. Forward a game's `leaderboard`
score report to `EntityLeaderboardReport` with its verified identity and title,
and supply `leaderboard_installed` to check current installed membership.
Profile keeps scores separately for each account, publishes the installed
games' reported totals through the existing friend-statistics API, and fetches
rankings asynchronously in `EntityLeaderboardPump` (part of `EntityHostPump`).
Uninstalling hides a retained score immediately. Account changes cancel old
requests and clear old friend rows. No game gets another game's records or keys.
`python3 scripts/leaderboard-test.py` tests these boundaries locally, including
asynchronous publication and friend ranking with a private in-memory transport.
Add `--ui` to render empty and populated boards on private Xvfb displays and
verify Profile/Back navigation.

## Profile pictures

Click the picture in Profile or Account to open one modal with Abstract and
Classic tabs. Classic retains the existing icon set; Abstract contains three
generated bitmap pictures. The chosen picture family follows the verified Daochi account in
`private.entity.v1.profile`, record `00000000000000000000000000000001`, schema
`entity.profile-appearance.v1`, through the existing encrypted Entity record
service. Old profile documents keep their classic picture.

`entity/telegram_connection` owns bot URI validation, account-change cancellation,
link/disconnect/poll/ack ordering and retry policy. An app configures its bot name
and relay path and supplies authenticated transport and its message handler.
Profile draws `entity.telegram` snapshots and sends owner-bound actions; hosts
retain key access and validate pending authorization request IDs before approval.

## Game reward claim client

`entity/game_reward_client` exports `GameRewardClient`, its `Result`, `State`
and `Error` types, and these synchronous operations:

- `GameRewardClientStart(client: *GameRewardClient, reward: string) -> GameRewardClientResult`
  copies a valid provider reward name (1–64 bytes) and binds the current owner.
  It queues local interest; it does not send or award anything. A pending client
  rejects another Start with `error = Busy`, preserving the existing claim.
- `GameRewardClientPump(client: *GameRewardClient, now: s64) -> GameRewardClientResult`
  sends at most one service call. The first is `entity.dew` / `claim:REWARD`;
  subsequent calls use `claim-status` only, with monotonic milliseconds and
  `poll_delay` (zero = 1000, negative = no delay, overflow saturates).
- `GameRewardClientReadReply(client: *GameRewardClient, output: *Vec(u8))`
  clears output and copies a retained, validated terminal wire reply while its
  owner remains current. It exposes no borrowed host storage.
- `GameRewardClientReset(client: *GameRewardClient)` releases storage and clears
  the binding/result. Call on logout/relogin even for the same identity, and
  before disposal or reconfiguring callbacks.
- `GameRewardClientCancel(client: *GameRewardClient)` resets local interest and
  records `Cancelled`. It cannot cancel an award already accepted by a provider.

Configure `context`, `service(context, service, request) -> string` and
`owner(context) -> string`. Owner returns only a verified public identity
(up to 128 bytes), empty when signed out. Request/reply strings are borrowed
for the callback; the client copies inputs before later callbacks reuse scratch.
Callbacks must not reenter except to Reset/Cancel; either invalidates a synchronous
completion, including inside owner callbacks. Adapters must route to the verified
owner, cancel/reject old-owner work on account transitions, and exclusively reserve
Entity's one reward claim slot until it finishes. Another client must not replace
that slot. The current protocol exposes no request number, so none is invented.

`Pending` is not an award. A matching `done` reply requires a boolean `credited`,
positive integer `units` and nonnegative integer `balance`, both at most
9007199254740991, matching the existing reward helper's monetary semantics.
`Done` means this reply credited the account; `AlreadyClaimed` means
`credited:false`, carrying the catalog units without reporting a new award.
`result.claim` uses the existing Daochi `RewardClaim` model. Neither implies
remote record synchronization. Provider `busy`, `signin`, `ineligible` and
`failed` remain distinct terminal states; arbitrary success text is rejected.
Malformed, duplicate-field, wrong-reward or oversized replies stop without an
award or automatic claim replay. Replies default to a hard 4096-byte maximum;
positive `reply_limit` can lower it. Malformed/oversized replies clear retained
text and claim data; validated provider failures retain their wire reply.

The caller owns eligibility, completion/route evidence, legacy migration, durable
records, account selection, strings/UI and adoption of the provider's grant.
An explicit Start after a terminal result is a caller retry decision: retain the
same reward name for the same award. After uncertain outcomes, reconcile with
the provider before starting another mutation; Reset/Cancel is not reconciliation.
There is no cross-process resume or persistent provider request identity in this
protocol. No games are migrated in this module change.

Run `env -u DISPLAY -u WAYLAND_DISPLAY make -j1 game-reward-client-test` for native C,
source-to-portable VM and saved-IR-to-portable VM fake-host lifecycle tests, plus
the dependency's existing reward wire/model fixture. All scratch stays in ignored
`work/reward-client`; no accounts or provider network are used.

## Native package artifacts

Entity's Ziran project tool (`tools/artifacts.zi`) owns the native Profile and
account cryptography build graph. Consumers request the generic package API:

```sh
ziran pkg artifact entity:native-profile --platform linux-x86_64-gnu --locked
ziran pkg artifact entity:native-crypto --platform linux-x86_64-gnu --locked
```

Each command prints one absolute `artifact.tsv` path. Resolve its declared output
paths beside that descriptor and verify the recorded SHA-256 values. The Profile
artifact's `dependencies.tsv` maps `self:native-crypto` to its crypto descriptor;
follow that edge rather than discovering package sources or rebuilding libraries.

`native-profile` supplies `libentity.a`, `headers.tar`, `entity.zx`, `font.ttf`,
`ziran_web.js` and `link.txt`. Extract the generated headers into a private build
folder and add that folder and its `ziran/` child as include paths. C hosts include
`src/native_host.h` and use its generated declarations (for example,
`native_host_EntityHostProfileSections`). The archive contains the complete
Entity native-host graph, including its generated dependency objects; do not
compile another copy of that graph into the same host. `entity.zx` already embeds
Entity's picture assets. Hosts retain the current bundle lifecycle, private
account directory, service adapters and account isolation described above.

`native-crypto` supplies `libmonocypher.a`, `liboqs.a` (ML-DSA-44 only),
`libziran.a`, `libplatform.a` and `link.txt`. Link the host archive before those support archives.
The platform archive contains Windows Schannel curl and zlib objects. It is a
valid empty archive on targets that use system libraries or host capabilities.
Windows transport retains curl with Schannel, without OpenSSL, SSH, LDAP/LDAPS
or SMB, and uses the same platform trust/security behavior as the existing host.
`link.txt` is TSV: `archive` rows give descriptor-relative archives in link
order, `pkg-config` rows name packages to query, and `library` and `flag`
rows supply individual linker arguments. Read these rows for the Profile, then
its dependency descriptors; consumers keep no crypto archive or source lists. Browser `js-library` and `embed` rows
name descriptor-relative support files and virtual asset destinations.
These are compiler-version-specific C ABI artifacts, not a stable binary SDK.
No application main, account keys or app-specific collection is packaged.
An ordinary Ziran program importing Entity already owns its generated graph:
link `native-crypto` and the Profile system/resource rows, omitting the Profile
`libentity.a` archive. A foreign C host links `libentity.a` once, then support
archives in the declared order. Do not combine both generated graphs.

Consumer variation belongs in the package options, for example:

```toml
[tool.entity]
edition = "fdroid" # direct (default), fdroid, play
# Android only; retain the app’s actual minimum API:
# ndk = "/absolute/android-ndk"
# android_api = "21" # default "24"; also supports "23"
```

The native target is independent of `--target=c`, the language backend. Cross
builds require an absolute `CC` executable and matching `AR` (or the sibling
`emar`/`llvm-ar`). Supported cross targets are
`emscripten-wasm32-emscripten`, `windows-x86_64-mingw`,
`android-aarch64-bionic` and `android-armv7-bionic`. Windows uses an absolute
`x86_64-w64-mingw32-gcc` driver and its matching `ar`, `windres`, `ranlib` and
`objcopy` siblings. Entity builds its locked curl/zlib sources; consumers need
no curl source paths, archive inventory or extra target zlib installation.
Windows generated graph objects contain GCC LTO and native code. The declared
`-flto=1` link flag removes unused graph functions before PE linking, including
unused host callbacks and cryptographic algorithms; hosts must retain that flag.
LTO runs with one worker and keeps normal Windows unwind metadata.
Android takes a keyed absolute `ndk` root and `android_api` string: `"21"`,
`"23"` or `"24"` (default). Select the matching NDK compiler driver and sibling
`llvm-ar`, for example `aarch64-linux-android21-clang` with `android_api="21"`.
The API option is inherited by the crypto prerequisite and changes artifact
identity. It does not raise an application’s minimum SDK. Unsupported targets,
API values, mismatched compiler/archive drivers and unknown editions fail
before artifact compilation. These recipes produce support
archives and assets; packaging an APK or a web application remains the host's job.

The driver keys the resolved dependency graph, explicit recipe files, compiler,
target, native flags, options and prerequisite descriptors. Dirty graph checkouts
produce isolated artifacts. Two clean consumers share one verified artifact.
`make -j1 artifact-test` requires that clean graph and links/runs two synthetic
C consumers without accounts or a display. For development,
`python3 tests/native_artifacts.py --dirty` explicitly tests isolation instead;
it does not certify clean reuse. Later game migrations consume these outputs;
this change does not alter any game's build or account policy.

To validate a published candidate independently of local edits, run
`python3 tests/native_artifacts.py --published ENTITY_COMMIT --toolchain ZIRAN_COMMIT`
with full commit IDs. This uses the normal immutable package graph without a
local Entity override. Subsequent cross fixtures inherit that resolved graph.

The focused cross fixture `tests/native_artifacts_cross.py TARGET` accepts
`--ndk`, `--android-api`, `--edition` and explicit `--dirty` isolation mode. It
validates descriptor hashes and actual C-host compile/link output. Windows also
links an ordinary Ziran import graph against descriptor-only support metadata,
retaining curl and checking platform archive member uniqueness. Cross binaries
are never executed; compile/link success does not establish runtime behavior.
