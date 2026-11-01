package xyz.waozi.entity;

import android.app.Activity;
import android.os.Build;
import android.os.CancellationSignal;
import android.util.Base64;

import androidx.credentials.ClearCredentialStateRequest;
import androidx.credentials.CreateCredentialResponse;
import androidx.credentials.CreatePublicKeyCredentialRequest;
import androidx.credentials.CreatePublicKeyCredentialResponse;
import androidx.credentials.Credential;
import androidx.credentials.CredentialManager;
import androidx.credentials.CredentialManagerCallback;
import androidx.credentials.CustomCredential;
import androidx.credentials.GetCredentialRequest;
import androidx.credentials.GetCredentialResponse;
import androidx.credentials.GetPublicKeyCredentialOption;
import androidx.credentials.PublicKeyCredential;
import androidx.credentials.exceptions.ClearCredentialException;
import androidx.credentials.exceptions.CreateCredentialCancellationException;
import androidx.credentials.exceptions.CreateCredentialException;
import androidx.credentials.exceptions.GetCredentialCancellationException;
import androidx.credentials.exceptions.GetCredentialException;
import androidx.credentials.exceptions.NoCredentialException;

import com.google.android.libraries.identity.googleid.GetSignInWithGoogleOption;
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.util.concurrent.Executor;

// Play edition only: passkeys and Google through Credential Manager. Entity's
// shared code decides what to do with the answers. No account key reaches this
// class; it hands back a PRF value or a Google ID token and keeps neither after
// they are polled.
public final class SignInBridge {
    private static final String RELYING_PARTY = "waozi.xyz";
    private static final String PRF_INPUT = "waozi-account-passkey-prf-v1";

    private static final Object lock = new Object();
    private static String answer = "{\"status\":\"cancelled\"}";
    private static CancellationSignal cancellation;

    private SignInBridge() {
    }

    public static String call(Activity activity, String request) {
        String[] parts = request.split("\n", -1);
        switch (parts[0]) {
            case "available":
                return Build.VERSION.SDK_INT >= 23 ? "yes" : "no";
            case "poll":
                return poll();
            case "cancel":
                cancel();
                return "{\"status\":\"cancelled\"}";
            case "forget":
                forget(activity);
                return "{\"status\":\"ok\"}";
            case "passkey_create":
                return parts.length == 3 ? create(activity, parts[1], parts[2]) : status("error");
            case "passkey_get":
                return get(activity);
            case "google":
                return parts.length == 3 ? google(activity, parts[1], parts[2]) : status("error");
            default:
                return status("error");
        }
    }

    private static String status(String value) {
        return "{\"status\":\"" + value + "\"}";
    }

    private static String poll() {
        synchronized (lock) {
            String current = answer;
            if (!current.contains("\"pending\"")) {
                answer = status("cancelled");
            }
            return current;
        }
    }

    private static void finish(String value) {
        synchronized (lock) {
            answer = value;
            cancellation = null;
        }
    }

    private static CancellationSignal begin() {
        synchronized (lock) {
            answer = status("pending");
            cancellation = new CancellationSignal();
            return cancellation;
        }
    }

    private static void cancel() {
        synchronized (lock) {
            if (cancellation != null) {
                cancellation.cancel();
            }
            cancellation = null;
            answer = status("cancelled");
        }
    }

    private static void forget(Activity activity) {
        cancel();
        CredentialManager.create(activity).clearCredentialStateAsync(new ClearCredentialStateRequest(),
                null, mainExecutor(activity), new CredentialManagerCallback<Void, ClearCredentialException>() {
                    @Override
                    public void onResult(Void result) {
                    }

                    @Override
                    public void onError(ClearCredentialException error) {
                    }
                });
    }

    private static Executor mainExecutor(Activity activity) {
        return activity::runOnUiThread;
    }

    private static String encode(byte[] value) {
        return Base64.encodeToString(value, Base64.URL_SAFE | Base64.NO_WRAP | Base64.NO_PADDING);
    }

    private static byte[] decode(String value) {
        return Base64.decode(value, Base64.URL_SAFE | Base64.NO_WRAP | Base64.NO_PADDING);
    }

    private static String hex(byte[] value) {
        StringBuilder text = new StringBuilder(value.length * 2);
        for (byte item : value) {
            text.append(String.format("%02x", item & 255));
        }
        return text.toString();
    }

    private static byte[] unhex(String value) {
        byte[] output = new byte[value.length() / 2];
        for (int index = 0; index < output.length; index++) {
            output[index] = (byte) Integer.parseInt(value.substring(index * 2, index * 2 + 2), 16);
        }
        return output;
    }

    private static String challenge() {
        // The node verifies no signature, so nothing checks this value; WebAuthn
        // only requires one to exist.
        byte[] bytes = new byte[32];
        new SecureRandom().nextBytes(bytes);
        return encode(bytes);
    }

    private static JSONObject extension() throws JSONException {
        JSONObject first = new JSONObject();
        first.put("first", encode(PRF_INPUT.getBytes(StandardCharsets.UTF_8)));
        JSONObject prf = new JSONObject();
        prf.put("eval", first);
        JSONObject extensions = new JSONObject();
        extensions.put("prf", prf);
        return extensions;
    }

    static String createRequest(String account, String name) throws JSONException {
        JSONObject relying = new JSONObject();
        relying.put("id", RELYING_PARTY);
        relying.put("name", "Waozi");
        JSONObject user = new JSONObject();
        user.put("id", encode(unhex(account)));
        user.put("name", name);
        user.put("displayName", name);
        JSONArray kinds = new JSONArray();
        kinds.put(new JSONObject().put("type", "public-key").put("alg", -7));
        kinds.put(new JSONObject().put("type", "public-key").put("alg", -257));
        JSONObject selection = new JSONObject();
        selection.put("residentKey", "required");
        selection.put("requireResidentKey", true);
        selection.put("userVerification", "required");
        JSONObject options = new JSONObject();
        options.put("rp", relying);
        options.put("user", user);
        options.put("challenge", challenge());
        options.put("pubKeyCredParams", kinds);
        options.put("authenticatorSelection", selection);
        options.put("timeout", 120000);
        options.put("extensions", extension());
        return options.toString();
    }

    static String getRequest(String credentialId) throws JSONException {
        JSONObject options = new JSONObject();
        options.put("rpId", RELYING_PARTY);
        options.put("challenge", challenge());
        options.put("userVerification", "required");
        options.put("timeout", 120000);
        options.put("extensions", extension());
        if (!credentialId.isEmpty()) {
            JSONArray allowed = new JSONArray();
            allowed.put(new JSONObject().put("type", "public-key").put("id", credentialId));
            options.put("allowCredentials", allowed);
        }
        return options.toString();
    }

    // Reads Credential Manager's registration or assertion JSON, in the same
    // fields the browser path fills. A manager without PRF answers no_prf.
    static String passkeyAnswer(String responseJson) throws JSONException, NoSuchAlgorithmException {
        JSONObject response = new JSONObject(responseJson);
        byte[] identifier = decode(response.getString("rawId"));
        String credential = hex(MessageDigest.getInstance("SHA-256").digest(identifier));
        JSONObject results = response.optJSONObject("clientExtensionResults");
        JSONObject prf = results == null ? null : results.optJSONObject("prf");
        JSONObject values = prf == null ? null : prf.optJSONObject("results");
        String first = values == null ? "" : values.optString("first", "");
        if (first.isEmpty()) {
            return status("no_prf");
        }
        JSONObject output = new JSONObject();
        output.put("status", "ok");
        output.put("credential", credential);
        output.put("prf", hex(decode(first)));
        JSONObject inner = response.optJSONObject("response");
        String handle = inner == null ? "" : inner.optString("userHandle", "");
        if (!handle.isEmpty()) {
            output.put("account", hex(decode(handle)));
        }
        return output.toString();
    }

    // Enabled without a value means PRF exists but needs the passkey's first use.
    static boolean prfEnabled(String responseJson) throws JSONException {
        JSONObject results = new JSONObject(responseJson).optJSONObject("clientExtensionResults");
        JSONObject prf = results == null ? null : results.optJSONObject("prf");
        return prf != null && prf.optBoolean("enabled", false);
    }

    private static String createFailure(CreateCredentialException error) {
        return error instanceof CreateCredentialCancellationException ? status("cancelled") : status("unsupported");
    }

    private static String getFailure(GetCredentialException error) {
        if (error instanceof GetCredentialCancellationException || error instanceof NoCredentialException) {
            return status("cancelled");
        }
        return status("unsupported");
    }

    private static String create(Activity activity, String account, String name) {
        final String requestJson;
        try {
            requestJson = createRequest(account, name);
        } catch (JSONException error) {
            return status("error");
        }
        CancellationSignal signal = begin();
        CredentialManager.create(activity).createCredentialAsync(activity, new CreatePublicKeyCredentialRequest(requestJson),
                signal, mainExecutor(activity), new CredentialManagerCallback<CreateCredentialResponse, CreateCredentialException>() {
                    @Override
                    public void onResult(CreateCredentialResponse result) {
                        created(activity, result);
                    }

                    @Override
                    public void onError(CreateCredentialException error) {
                        finish(createFailure(error));
                    }
                });
        return status("pending");
    }

    private static void created(Activity activity, CreateCredentialResponse result) {
        if (!(result instanceof CreatePublicKeyCredentialResponse)) {
            finish(status("error"));
            return;
        }
        String responseJson = ((CreatePublicKeyCredentialResponse) result).getRegistrationResponseJson();
        try {
            String read = passkeyAnswer(responseJson);
            if (!read.contains("no_prf")) {
                finish(read);
                return;
            }
            if (!prfEnabled(responseJson)) {
                finish(read);
                return;
            }
            read(activity, new JSONObject(responseJson).getString("rawId"));
        } catch (JSONException | NoSuchAlgorithmException error) {
            finish(status("error"));
        }
    }

    private static String get(Activity activity) {
        begin();
        read(activity, "");
        return status("pending");
    }

    private static void read(Activity activity, String credentialId) {
        final String requestJson;
        try {
            requestJson = getRequest(credentialId);
        } catch (JSONException error) {
            finish(status("error"));
            return;
        }
        CancellationSignal signal;
        synchronized (lock) {
            signal = cancellation;
        }
        GetCredentialRequest request = new GetCredentialRequest.Builder()
                .addCredentialOption(new GetPublicKeyCredentialOption(requestJson))
                .build();
        CredentialManager.create(activity).getCredentialAsync(activity, request, signal, mainExecutor(activity),
                new CredentialManagerCallback<GetCredentialResponse, GetCredentialException>() {
                    @Override
                    public void onResult(GetCredentialResponse result) {
                        Credential credential = result.getCredential();
                        if (!(credential instanceof PublicKeyCredential)) {
                            finish(status("error"));
                            return;
                        }
                        try {
                            finish(passkeyAnswer(((PublicKeyCredential) credential).getAuthenticationResponseJson()));
                        } catch (JSONException | NoSuchAlgorithmException error) {
                            finish(status("error"));
                        }
                    }

                    @Override
                    public void onError(GetCredentialException error) {
                        finish(getFailure(error));
                    }
                });
    }

    private static String google(Activity activity, String client, String nonce) {
        GetSignInWithGoogleOption.Builder option = new GetSignInWithGoogleOption.Builder(client);
        if (!nonce.isEmpty()) {
            option.setNonce(nonce);
        }
        GetCredentialRequest request = new GetCredentialRequest.Builder()
                .addCredentialOption(option.build())
                .build();
        CancellationSignal signal = begin();
        CredentialManager.create(activity).getCredentialAsync(activity, request, signal, mainExecutor(activity),
                new CredentialManagerCallback<GetCredentialResponse, GetCredentialException>() {
                    @Override
                    public void onResult(GetCredentialResponse result) {
                        Credential credential = result.getCredential();
                        if (!(credential instanceof CustomCredential) ||
                                !GoogleIdTokenCredential.TYPE_GOOGLE_ID_TOKEN_CREDENTIAL.equals(credential.getType()) &&
                                !GoogleIdTokenCredential.TYPE_GOOGLE_ID_TOKEN_SIWG_CREDENTIAL.equals(credential.getType())) {
                            finish(status("error"));
                            return;
                        }
                        try {
                            String token = GoogleIdTokenCredential.createFrom(credential.getData()).getIdToken();
                            JSONObject output = new JSONObject();
                            output.put("status", "ok");
                            output.put("token", token);
                            finish(output.toString());
                        } catch (JSONException error) {
                            finish(status("error"));
                        }
                    }

                    @Override
                    public void onError(GetCredentialException error) {
                        finish(getFailure(error));
                    }
                });
        return status("pending");
    }
}
