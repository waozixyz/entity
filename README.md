# Self

Self is one portable profile app shared by Inner Breeze and Werkzeug. It also
runs independently in Kryon's ZIB player.

```sh
make test
make run
```

Dependencies use `ziran.toml` and `ziran.lock`. Local development overrides belong
in the ignored `ziran.local.toml`. The locked compiler uses Ziran IR55.

## Hosting

The bundle identifies as `self` and uses Kryon's standard app protocol. Hosts
provide the versioned `self.json` preferences document through ordinary scoped
`ReadStoreHost` and `WriteStoreHost` calls. The `self/model` export encodes and
validates that document. It contains display preferences and node origins;
account keys and tool secrets stay with the host.

Hosts select the available controls and picture choices, supply localized labels
through `AppLocaleHost`, and add named extension routes. Self returns a route
through `AppReply`; the host accepts only its own routes. Send the `reload`
command after returning from an extension. Run `APP_SAVE` before leaving Self
and keep the page open if saving fails.

The default node is `https://api.waozi.xyz`. Selecting a node does not create an
account or enable synchronization. A host maps the node selection to its own
existing account and storage operations.

The optional `self.assets` service supplies an absolute extracted asset root to
hosts that need one. Other hosts use the bundle-relative `assets/self/` paths.
The picture atlas comes from Kryon and the flower picture from Inner Breeze.

## Visual reference and checks

The generated [design reference](design/self-reference.png) informed the native
widget implementation; it is not a screenshot of the running app. The generation
mode and prompt are recorded in [design/prompt.txt](design/prompt.txt).

`scripts/ui_test.py PLAYER BUNDLE [--narrow]` exercises editing, the picture
picker, node validation, adding, selecting, removing, and persistence after a
restart. Run it only on a private display with `SELF_PRIVATE_DISPLAY=1`.
