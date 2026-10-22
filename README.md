# Entity

Entity is one portable profile app shared by Inner Breeze and Werkzeug. It also
runs independently with its own native account provider. The portable profile
preferences also run in Kryon's generic ZIB player, without account capabilities.

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
