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

On the Waozi node, connected native profiles can read their Dew balance, obtain
their Monero funding address, and confirm a node-priced storage plan. Purchases
are saved before sending. An uncertain result retains its request ID for an
explicit retry; it never becomes a new debit. Switching or logging out cancels
the old account's in-flight requests. The `entity/dew_model` export shares strict
integer balance, allowance and funding-address validation with Inner Breeze.
No currency transfer or game-specific shop is added.

The Profile shows Inbe's shared `DewBalance` card inline. Game hosts hide the
Name and Intention fields and identify players by their alias or public ID.
The browser host uses Kryon's existing `BundleApp` lifecycle, IndexedDB-backed
files and the same native Entity account provider; game bundles receive only
a navigation service and never see account keys. `scripts/build-web.py` links
this provider for browser applications with the locked cryptography packages.

## Shared game progress

`entity/game_progress` defines `entity.game-progress.v1` records in the
`game-progress` kind. Native account providers use `entity/game_progress_id` to derive one stable 32-digit
record ID from the game's stable name, independent of its wrapper or device.
The record service derives this ID when omitted and rejects another ID, so
standalone and hosted games use the same account record. Portable games get
that record with `{"operation":"get","kind":"game-progress","game":NAME}`;
they do not implement record IDs or account cryptography.

A document contains `game`, `unlocked` (1–4096), a `completed` string of up to
4096 zero/one marks, an opaque `state` string (up to 8192 bytes), and
`updated_at`. Unlocks take the maximum and completion marks are combined;
the position from the furthest unlocked campaign wins, with the newer record
revision breaking ties. A fresh installation downloads account progress before
uploading its local save. These rules apply both when
saving locally and when receiving another device's record, including an
older reply that carries a newly earned completion. Games migrate their old
saves into this record and keep those saves until the account confirms sync.
