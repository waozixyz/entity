package xyz.waozi.entity;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
import android.os.Bundle;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import com.google.android.gms.auth.api.identity.AuthorizationRequest;
import com.google.android.gms.auth.api.identity.ClearTokenRequest;
import com.google.android.gms.auth.api.identity.AuthorizationResult;
import com.google.android.gms.auth.api.identity.Identity;
import com.google.android.gms.common.GoogleApiAvailability;
import com.google.android.gms.common.ConnectionResult;
import com.google.android.gms.common.api.Scope;
import org.json.JSONObject;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Private Play-only authorization and Picker surface, shared by all Waozi apps. */
public final class DriveActivity extends Activity {
    private static final int AUTHORIZE = 6041;
    private static final int ACCOUNT = 6042;
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private SharedPreferences preferences;
    private DriveBackupFlow flow;
    private byte[] local;
    private String token;
    private android.accounts.Account account;
    private volatile boolean finished;
    private volatile boolean writing;
    private boolean retried;
    private WebView picker;
    private Job retry;
    private interface Job { void run() throws IOException; }

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        if (!DriveBackup.attach(this, getIntent().getIntExtra("waoziDriveRequest", -1))) {
            finished = true;
            finish();
            return;
        }
        preferences = getSharedPreferences("waozi-drive-backup-v3", MODE_PRIVATE);
        String command = DriveBackup.takeCommand();
        if (state != null || command == null) {
            done("cancelled", "");
            return;
        }
        if (command.startsWith("save\n")) {
            local = command.substring(5).getBytes(StandardCharsets.UTF_8);
            if (!DriveBackupFlow.sealed(local)) {
                done("invalid", "");
                return;
            }
        }
        // A default/unconfigured build must never start an account or Google network flow.
        if (config("picker_key").isEmpty() || !config("project_number").matches("[0-9]+")) {
            fail("setup");
            return;
        }
        if (GoogleApiAvailability.getInstance().isGooglePlayServicesAvailable(this) != ConnectionResult.SUCCESS) {
            fail("unavailable");
            return;
        }
        retry = this::start;
        // Never reuse an implicit account when several Google accounts are present.
        startActivityForResult(android.accounts.AccountManager.newChooseAccountIntent(
                null, null, new String[]{"com.google"}, null, null, null, null), ACCOUNT);
    }
    private String text(String name) {
        int id = getResources().getIdentifier("waozi_drive_" + name, "string", getPackageName());
        return id == 0 ? "Google Drive" : getString(id);
    }
    private String config(String name) {
        int id = getResources().getIdentifier("waozi_drive_" + name, "string", getPackageName());
        return id == 0 ? "" : getString(id);
    }
    private void authorize() {
        if (finished) {
            return;
        }
        AuthorizationRequest request = AuthorizationRequest.builder()
                .setAccount(account)
                .setRequestedScopes(java.util.Collections.singletonList(new Scope("https://www.googleapis.com/auth/drive.file")))
                .build();
        Identity.getAuthorizationClient(this).authorize(request)
                .addOnSuccessListener(result -> authorized(result))
                .addOnFailureListener(error -> fail("unauthorized"));
    }
    private void authorized(AuthorizationResult result) {
        if (finished) {
            return;
        }
        if (result.hasResolution()) {
            try {
                startIntentSenderForResult(result.getPendingIntent().getIntentSender(), AUTHORIZE, null, 0, 0, 0);
            } catch (android.content.IntentSender.SendIntentException error) {
                fail("unauthorized");
            }
            return;
        }
        token = result.getAccessToken();
        if (token == null || token.isEmpty()) {
            fail("unauthorized");
            return;
        }
        flow = new DriveBackupFlow(new DriveRest(token, preferences, () -> !finished));
        work(retry);
    }
    @Override protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (finished) {
            return;
        }
        if (requestCode == ACCOUNT) {
            if (resultCode != RESULT_OK || data == null) {
                done("cancelled", "");
                return;
            }
            String name = data.getStringExtra(android.accounts.AccountManager.KEY_ACCOUNT_NAME);
            String type = data.getStringExtra(android.accounts.AccountManager.KEY_ACCOUNT_TYPE);
            if (name == null || name.isEmpty() || !"com.google".equals(type)) {
                fail("unauthorized");
                return;
            }
            account = new android.accounts.Account(name, type);
            authorize();
            return;
        }
        if (requestCode != AUTHORIZE) {
            return;
        }
        if (resultCode != RESULT_OK || data == null) {
            done("cancelled", "");
            return;
        }
        try {
            authorized(Identity.getAuthorizationClient(this).getAuthorizationResultFromIntent(data));
        } catch (com.google.android.gms.common.api.ApiException error) {
            fail("unauthorized");
        }
    }
    private void work(Job job) {
        if (finished) {
            return;
        }
        retry = job;
        worker.execute(() -> {
            try {
                job.run();
            } catch (DriveBackupFlow.Failure error) {
                writing = false;
                if (("unauthorized".equals(error.code) || "forbidden".equals(error.code)) && !retried) {
                    retried = true;
                    runOnUiThread(() -> Identity.getAuthorizationClient(this)
                            .clearToken(ClearTokenRequest.builder().setToken(token).build())
                            .addOnSuccessListener(ignored -> authorize())
                            .addOnFailureListener(ignored -> fail("unauthorized")));
                } else {
                    fail(error.code);
                }
            } catch (IOException | RuntimeException error) {
                fail("error");
            }
        });
    }
    private void start() throws IOException {
        String linked = preferences.getString("file_id", "");
        // Restore always shows Picker: never assume a grant from another Play app.
        if (local == null) {
            runOnUiThread(this::pick);
        } else if (!linked.isEmpty()) {
            selected(linked);
        } else {
            choices();
        }
    }
    private void choices() throws IOException {
        List<DriveBackupFlow.File> files = flow.candidates();
        String[] labels = new String[files.size() + 1];
        for (int i = 0; i < files.size(); i++) {
            DriveBackupFlow.File file = files.get(i);
            labels[i] = file.name + "\n" + file.id;
        }
        labels[files.size()] = text("pick");
        runOnUiThread(() -> {
            AlertDialog.Builder dialog = new AlertDialog.Builder(this).setTitle(text("select"))
                    .setItems(labels, (ignored, index) -> {
                        if (index == files.size()) {
                            pick();
                        } else {
                            work(() -> selected(files.get(index).id));
                        }
                    }).setNegativeButton(android.R.string.cancel, (ignored, which) -> done("cancelled", ""))
                    .setOnCancelListener(ignored -> done("cancelled", ""));
            if (files.isEmpty() && local != null) {
                dialog.setPositiveButton(text("create"), (ignored, which) -> work(() -> {
                    writing = true;
                    DriveBackupFlow.File created = flow.create(local);
                    writing = false;
                    link(created);
                    done("saved", "");
                }));
            }
            dialog.show();
        });
    }
    private void selected(String id) throws IOException {
        DriveBackupFlow.Blob remote = flow.read(id);
        if (local == null) {
            link(remote.file);
            done("restored", new String(remote.bytes, StandardCharsets.UTF_8));
            return;
        }
        if (Arrays.equals(local, remote.bytes)) {
            link(remote.file);
            done("saved", "");
            return;
        }
        runOnUiThread(() -> new AlertDialog.Builder(this).setTitle("Google Drive")
                .setMessage(text("conflict"))
                .setPositiveButton(text("replace"), (dialog, which) -> work(() -> {
                    writing = true;
                    DriveBackupFlow.File updated = flow.replace(remote, local);
                    writing = false;
                    link(updated);
                    done("saved", "");
                }))
                .setNeutralButton(text("pick"), (dialog, which) -> pick())
                .setNegativeButton(text("keep"), (dialog, which) -> done("cancelled", ""))
                .setOnCancelListener(dialog -> done("cancelled", "")).show());
    }
    private void link(DriveBackupFlow.File file) throws IOException {
        if (!preferences.edit().putString("file_id", file.id).putString("version", file.version).commit()) {
            throw new DriveBackupFlow.Failure("error");
        }
    }
    private void pick() {
        String key = config("picker_key");
        String project = config("project_number");
        String origin = config("picker_origin");
        Uri base = Uri.parse(origin);
        if (key.isEmpty() || !project.matches("[0-9]+") || !"https".equals(base.getScheme())
                || base.getHost() == null || base.getUserInfo() != null || base.getPort() != -1
                || !(base.getPath().isEmpty() || "/".equals(base.getPath())) || base.getQuery() != null || base.getFragment() != null) {
            fail("setup");
            return;
        }
        final String callback = origin.replaceAll("/$", "") + "/entity-drive-picked";
        picker = new WebView(this);
        picker.setSaveEnabled(false);
        WebSettings settings = picker.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setCacheMode(WebSettings.LOAD_NO_CACHE);
        settings.setSaveFormData(false);
        picker.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                return navigate(request.getUrl(), request.isForMainFrame());
            }
            @Override public boolean shouldOverrideUrlLoading(WebView view, String url) {
                // Android 6 calls this overload rather than WebResourceRequest.
                return navigate(Uri.parse(url), true);
            }
            private boolean navigate(Uri uri, boolean mainFrame) {
                if (mainFrame) {
                    if (callback.equals(uri.buildUpon().fragment(null).build().toString())) {
                        String id = uri.getFragment();
                        if (id != null && id.matches("[A-Za-z0-9_-]{1,256}")) {
                            closePicker();
                            work(() -> selected(id));
                        } else {
                            done("cancelled", "");
                        }
                    }
                    return true;
                }
                // Picker frames can contact Google over HTTPS; never open another application.
                return !"https".equals(uri.getScheme());
            }
        });
        String html = "<!doctype html><html><meta name=viewport content='width=device-width,initial-scale=1'>"
                + "<script src='https://apis.google.com/js/api.js'></script><script>"
                + "gapi.load('picker',function(){new google.picker.PickerBuilder()"
                + ".addView(new google.picker.DocsView(google.picker.ViewId.DOCS).setIncludeFolders(false))"
                + ".setOAuthToken(" + JSONObject.quote(token) + ").setDeveloperKey(" + JSONObject.quote(key) + ")"
                + ".setAppId(" + JSONObject.quote(project) + ").setOrigin(" + JSONObject.quote(origin) + ")"
                + ".setSize(window.innerWidth,window.innerHeight)"
                + ".setCallback(function(d){if(d.action===google.picker.Action.PICKED){location.href="
                + JSONObject.quote(callback + "#") + "+encodeURIComponent(d.docs[0].id);}"
                + "else if(d.action===google.picker.Action.CANCEL){location.href=" + JSONObject.quote(callback) + ";}})"
                + ".build().setVisible(true);});</script></html>";
        setContentView(picker);
        picker.loadDataWithBaseURL(origin + "/entity-drive-picker/", html, "text/html", "UTF-8", null);
    }
    private void closePicker() {
        if (picker != null) {
            picker.stopLoading();
            picker.loadUrl("about:blank");
            picker.destroy();
            picker = null;
        }
    }
    private void fail(String code) {
        runOnUiThread(() -> {
            if (finished || isFinishing()) {
                return;
            }
            closePicker();
            new AlertDialog.Builder(this).setTitle("Google Drive").setMessage(text(code))
                    .setPositiveButton(android.R.string.ok, (dialog, which) -> done(code, ""))
                    .setNeutralButton(text("missing".equals(code) ? "select" : "pick"), (dialog, which) -> {
                        if (token == null || "setup".equals(code) || "unavailable".equals(code)) {
                            done(code, "");
                        } else if ("missing".equals(code) && local != null) {
                            // An explicit new selection can find another file or offer creation.
                            // Keep the old ID until the user successfully chooses its replacement.
                            work(this::choices);
                        } else {
                            pick();
                        }
                    })
                    .setOnCancelListener(dialog -> done(code, "")).show();
        });
    }
    private void done(String status, String content) {
        runOnUiThread(() -> {
            if (finished) {
                return;
            }
            finished = true;
            if ("saved".equals(status)) {
                android.widget.Toast.makeText(this, text("saved"), android.widget.Toast.LENGTH_LONG).show();
            }
            DriveBackup.finish(this, status, content);
            finish();
        });
    }
    void cancelOperation() {
        done(writing ? "uncertain" : "cancelled", "");
    }
    @Override public void onBackPressed() {
        cancelOperation();
    }
    @Override protected void onDestroy() {
        if (!finished) {
            DriveBackup.finish(this, "cancelled", "");
        }
        finished = true;
        closePicker();
        token = null;
        if (local != null) {
            Arrays.fill(local, (byte) 0);
            local = null;
        }
        worker.shutdownNow();
        DriveBackup.detach(this);
        super.onDestroy();
    }
}
