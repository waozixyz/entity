# Changelog

## [Unreleased]

- The web build includes Kryon's test driver only when `KRYON_TEST_DRIVER` is set, and the canvas profile host test builds its page that way. Kryon no longer puts the driver in ordinary builds.

- Build achievement notifications with the current Kryon widget imports.

- Remember completed password backups for the same shared desktop account across apps; dismissed reminders remain separate from recovery evidence.

- Every backup, including the .key file, is now protected by a password. A new password needs at least 8 characters, a number and a lowercase letter, and the field says what is still missing.
- If you're signed in without a password-protected backup, the account screen offers to save one, with Not now. Older backup files still open and offer to save a protected copy.
- Choosing your .key file comes first on the sign-in screen: it's your identity, and it signs you in without any server.

- Show one star for each character typed in a shared password field, with no fake prefill or eight-star limit.

- Messages such as a wrong password stay on screen on the website instead of disappearing within a second.

- Every waozi.xyz site with its own key store, such as Breeze and Werk, follows the shared sign-in and sign-out. A site signed in to a different account offers Continue as @name.

- Sign in with a passkey in browsers and Google Play builds where the passkey provider supports PRF. It unlocks a sealed copy of your key that the node can't open. Elsewhere, use your password.
- Sign in with Google to find your account in browsers and Google Play builds, on Waozi's own node only. Your password or passkey still unlocks it.

- In Google Play builds, optionally save encrypted account backups to Google Drive and choose the same backup in another app or phone. Local backup files remain available.

- Continue as @name on a computer where another waozi app is signed in, using one shared account file.
- Continue as @name on Android from another waozi app signed in on this phone. That app asks first and seals the account to a one-time key; only waozi apps with a listed signing certificate can ask.
- Sign in with a username and password when you saved a backup online. The backup is sealed on this device; no one can reset your password.
- Sign out always works, offline and without a backup. It reminds you once to back up unless this device already did.
- Link devices with X25519 and ML-KEM-768 together; the code carries a relay ID and key hash so it stays easy to scan. Older codes keep working.
- Seal new backups with Argon2id in a storage-independent format and ask for a password of at least 8 characters. Older backup files keep opening.
- Restore Shovey Island purchases across devices and confirm the current Dew price before unlocking.

- Sign in like any other app: choose your backup file, then enter its password, and try again without finding the file again.
- Name saved backups after your username, or your public ID when you have none.
- Require a repeated password for every new backup, say plainly that no one can reset it, and go straight to saving one after creating an account. Older backup files still open.
-Add the shared game daily-chest plan.
- Buy Shovey skins and separately counted Dew coin packs.
- Buy three Choano decorations with Dew: Pearl, Flower and Wizard.

- Preserve the surrounding game theme when nested controls finish drawing.

- Embedding apps can keep profile pictures without bundled game imagery; leaderboards use profile pictures when optional game art is absent.

- Filter Android account-key imports to key files and related backup types.
- Own native Profile, runtime and cryptography artifacts through the generic Ziran package API, with explicit platform and edition selection.

- Share owner-bound reward claim polling and validated credited/already-claimed results without replaying uncertain claims.
- Share earned-progress hydration, owner isolation, durable pending saves and service acknowledgement across games.
- Share one owner-bound collection client across games, with bounded replies, typed outcomes and configurable status polling.
- Buy Dew from a shop of packs: Google Play prices with their real savings, or Monero prices with a custom amount and the payment code filled in.
- Show Wurm's current skin artwork in leaderboards and friends, including the new coin and daily reward skins.
- Publish your own level collections as private, for friends or for everyone, and find others' without Inner Breeze.
- Send a chosen profile picture to your node the same way from every app, and keep one chosen before signing in.
- Never send the starting picture of a new account as if you had chosen it.
- Show friends' abstract pictures in every app that hosts Entity.
- Show a profile picture chosen in another app in every app that reads it from your node.
