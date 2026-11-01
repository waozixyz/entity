# Google Drive account backups (Play only)

Entity owns this optional Android adapter and the fake-transport policy tests.
Only a Google Play host includes it. Normal/F-Droid hosts neither load its
Gradle file nor include its Java, resources, manifest activity, Google scopes,
or Google dependencies. The existing local backup path remains independent.

The adapter sends the existing `RecoveryEncode` v3 text unchanged. No password,
private key, login proof, or unsealed account data crosses the Android bridge.
The file is visible in My Drive as `Waozi Account Backup.waozi-account`, with
MIME type `application/octet-stream` and public metadata property
`waoziBackup=entity-v3`. "Public" here means cross-client metadata; it does not
make the file publicly readable. No permissions/sharing API is used.

A new app/phone uses Google Picker rather than assuming another client's
`drive.file` grant. Each app stores the selected file ID and observed version
privately. Renaming a file does not break the link. An existing different
backup always requires an explicit keep/replace decision, followed by a fresh
content/revision comparison. Unknown formats are never replaced. Creation is
explicit, re-lists accessible marked files, and refuses to create if any exist.
A generated file ID is persisted before creation so an uncertain result does
not trigger a fresh duplicate. That pending ID survives app restarts.

## Google Cloud setup by the owner

1. Create or select **one** [Google Cloud project](https://console.cloud.google.com/projectselector2/home/dashboard)
   for all Waozi Play apps. Record its numeric project number (not project ID).
2. In [API Library](https://console.cloud.google.com/apis/library), enable
   [Google Drive API](https://console.cloud.google.com/apis/library/drive.googleapis.com)
   and [Google Picker API](https://console.cloud.google.com/apis/library/picker.googleapis.com).
3. Configure one [Google Auth Platform consent identity](https://console.cloud.google.com/auth/branding):
   Waozi name, support email, owned domain, homepage/privacy links and audience.
   In Data Access request **only** `https://www.googleapis.com/auth/drive.file`.
   Add test users while the app is in Testing. See Google's
   [consent setup](https://developers.google.com/workspace/guides/configure-oauth-consent).
4. In [Clients](https://console.cloud.google.com/auth/clients), create one
   **Android OAuth client for every package/signing-certificate pair**.
   Breeze Play production package is `xyz.waozi.inbe`. Copy its **Play App Signing
   certificate SHA-1** from Play Console > Test and release > Setup > App signing;
   an upload certificate is a different identity. Create additional clients for
   other Play apps using their real package IDs and Play App Signing SHA-1s.
   For this task's debug build, use `xyz.waozi.inbe.gplay.debug` and the local debug
   certificate SHA-1 (`droid/gradlew -p droid :app:signingReport`). Never copy a
   keystore/password/client secret into the repository. See
   [Android authorization setup](https://developer.android.com/identity/authorization)
   and [Play app signing](https://support.google.com/googleplay/android-developer/answer/9842756).
5. In [Credentials](https://console.cloud.google.com/apis/credentials), create a
   separate **public browser API key for Picker**. Restrict its API access to
   Google Picker API and its HTTP referrers to `https://waozi.xyz/*` (or the exact
   owned HTTPS origin you configure). This is a browser key, not the Android
   package-restricted key and not an OAuth client secret. See
   [Picker prerequisites and sample](https://developers.google.com/workspace/drive/picker/guides/web-picker-sample).
6. Pass the following properties to the Play build using private local Gradle
   configuration or CI configuration. No populated configuration is committed:

   ```properties
   waozi.drivePickerKey=YOUR_RESTRICTED_PUBLIC_PICKER_API_KEY
   waozi.driveProjectNumber=YOUR_NUMERIC_CLOUD_PROJECT_NUMBER
   waozi.drivePickerOrigin=https://waozi.xyz
   ```

   Native AuthorizationClient discovers its Android client through package plus
   signing certificate. There is no embedded client secret, refresh token, or
   service account. The Picker uses the native access token directly; this
   implementation does not run a separate web OAuth flow or need a web client ID.
7. Install each configured Play build and test with the intended Google account.
   Save in one app, choose that same file with Picker in another app/phone, and
   enter its original backup password. Test different signing identities,
   accounts, file rename/deletion, revoke/re-authorize, expiry, quota and offline
   behavior before advertising cross-app recovery as verified.

## Host integration

Breeze includes this now. Another Play host needs the same initial APK wiring;
Java/manifest changes cannot arrive through a `.zx` package update alone.
After that initial integration the shared Entity package owns policy and UI.
Within **only** the host's Play build configuration:

```groovy
ext.waoziEntityDir = /* Entity package directory resolved by this host */
apply from: new File(waoziEntityDir, 'android/gplay.gradle')
```

The script expects a `gplay` build type. Hosts using another variant shape
should attach these source/resource directories and the `gplayImplementation`
auth dependency to their Play-only source set. In the **Play-only manifest** add:

```xml
<activity android:name="xyz.waozi.entity.DriveActivity"
    android:exported="false"
    android:configChanges="keyboardHidden|orientation|screenSize"
    android:theme="@android:style/Theme.Material.Light.NoActionBar" />
```

The shared Gradle script keeps the JNI entrypoint from shrinking using Entity’s own rules:

```proguard
-keep class xyz.waozi.entity.DriveBackup {
    public static java.lang.String call(android.app.Activity, java.lang.String);
}
```

The existing Entity management provider detects this class only in Android
`GOOGLE_PLAY` builds and offers branded Drive buttons. Restored text goes through
`ProviderImportText`, the existing password prompt, `RecoveryDecode`, and the
existing merge/replace workflow. The format and cryptography are unchanged.

## Local tests and current limits

Run `build-queue -- python3 android/tests/test_adapter.py`. It compiles the
shared policy with plain Java and a fake Drive transport. It tests envelope
bounds/version/hex, duplicate resolution, unchanged data, changed revision or
bytes during confirmation, invalid files, file-ID stability and failure mapping.
Native recovery/provider tests remain in `build-queue -- make native-test`.

Real authorization, file I/O and cross-client grants have not been proven without
owner Cloud setup. The Picker is embedded in an isolated HTTPS-origin WebView,
uses no JavaScript/native bridge, permits no file/content access or external
app navigation, and does not perform OAuth login in the WebView. Whether Google
Picker accepts this native-token/origin combination on all supported devices
remains to be tested. The token stays in memory and is never in a URL or log.

Drive v3 does not document atomic compare-and-swap for this flow. We compare
metadata/download/metadata and recheck immediately before PATCH, but a small
race between that check and the server update remains. Two independent apps
can explicitly create at once before either sees the other's new file; the next
list requires an explicit selection. We do not promise global uniqueness.

Retries are manual, except one cache-cleared reauthorization after HTTP 401 or denied/revoked access (403).
No background synchronization, quota backoff, or offline queue is implemented.
An interrupted write can have succeeded remotely: it is reported as uncertain,
never retried blindly, and reconciled by ID before another create. Process death
cancels the interactive flow; no password is persisted. Initial host inclusion
and signed APK updates are still needed in apps other than Breeze. This change
does not publish to Google Play or any other store.

Breeze's stable Play debug build (run from Breeze) is:

```sh
build-queue -- droid/gradlew -p droid --no-daemon -Dorg.gradle.jvmargs= :app:assembleGplayDebug :app:assembleGplayDebugAndroidTest -Papp.onlyAbi=armeabi-v7a
```

Its native code uses the
same `GOOGLE_PLAY` gate, with a separate package, signing key and output path;
it does not overwrite the production Play APK. `assembleGplayDebugAndroidTest`
builds the shared unconfigured-flow test for the Moto.

# Passkeys and Sign in with Google (Play and web)

`SignInBridge` is the Play-only Android side; browsers use the same logic in
`src/sign_in_bridge.zi`. Normal and F-Droid builds have neither, and offer the
username and password instead. Desktop builds also have no passkey or Google
sign-in today.

A passkey gives a WebAuthn PRF value that unlocks its own sealed copy of the
account key. The node stores only that sealed text and a digest. Where the
passkey provider returns no PRF value, the app says so and asks for the password.
Google only tells the node which account to look for; a password or passkey
still unlocks it. The `.key` backup stays the master key, and no one can reset a
lost password.

## Google Cloud and domain setup by the owner

Use the same Cloud project as Drive above.

1. In [Clients](https://console.cloud.google.com/auth/clients), create a **Web
   application** client. Add `https://entity.waozi.xyz` and `https://waozi.xyz`
   under Authorized JavaScript origins. Copy its client ID; it is not a secret.
   See [Google's client ID guide](https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid).
2. Keep the Android OAuth clients from Drive step 4, one per package and signing
   certificate pair. Sign in with Google needs them too.
3. In [Data Access](https://console.cloud.google.com/auth/scopes) add only
   `openid`. The node keeps no email or name.
4. Set this on the Daochi node, web client first, then restart it:

   ```sh
   DAOCHI_GOOGLE_SIGNIN_CLIENT_IDS=WEB_CLIENT_ID
   ```

   The Google button stays hidden until the node has this value.
5. For Android passkeys, publish
   `https://waozi.xyz/.well-known/assetlinks.json` with
   `delegate_permission/common.get_login_creds` for each Play package, using its
   **Play App Signing SHA-256** from Play Console > Test and release > Setup >
   App signing. Never publish a debug certificate there. See
   [Credential Manager prerequisites](https://developer.android.com/identity/credential-manager/prerequisites).
