package xyz.waozi.entity;

import android.content.SharedPreferences;
import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

/** Bounded Drive v3 I/O. No Google SDK for storage; no tokens on disk or in URLs. */
final class DriveRest implements DriveBackupFlow.Transport {
    private static final String API = "https://www.googleapis.com/drive/v3/files";
    private static final String UPLOAD = "https://www.googleapis.com/upload/drive/v3/files";
    private static final String FIELDS = "id,name,version,size,trashed,ownedByMe,properties";
    private final String token;
    interface Active { boolean get(); }
    private final Active active;
    private final SharedPreferences preferences;

    DriveRest(String token, SharedPreferences preferences, Active active) {
        this.token = token;
        this.active = active;
        this.preferences = preferences;
    }
    private static String encode(String value) throws IOException {
        return URLEncoder.encode(value, "UTF-8");
    }
    private static void id(String id) throws IOException {
        if (id == null || !id.matches("[A-Za-z0-9_-]{1,256}")) {
            throw new DriveBackupFlow.Failure("invalid");
        }
    }
    private byte[] request(String method, String url, String type, byte[] body, int cap) throws IOException {
        if (!active.get()) {
            throw new DriveBackupFlow.Failure("cancelled");
        }
        HttpURLConnection connection = (HttpURLConnection) new URL(url).openConnection();
        connection.setInstanceFollowRedirects(false);
        connection.setConnectTimeout(15000);
        connection.setReadTimeout(20000);
        connection.setRequestMethod(method);
        connection.setRequestProperty("Authorization", "Bearer " + token);
        connection.setRequestProperty("Accept", "application/json");
        boolean submitted = false;
        try {
            if (body != null) {
                connection.setDoOutput(true);
                connection.setRequestProperty("Content-Type", type);
                connection.setFixedLengthStreamingMode(body.length);
                if (!active.get()) {
                    throw new DriveBackupFlow.Failure("cancelled");
                }
                submitted = true;
                try (java.io.OutputStream output = connection.getOutputStream()) {
                    output.write(body);
                }
            }
            int status = connection.getResponseCode();
            if (status < 200 || status > 299) {
                String reason = "";
                try {
                    JSONObject error = new JSONObject(new String(read(connection.getErrorStream(), 8192), StandardCharsets.UTF_8));
                    JSONArray errors = error.optJSONObject("error").optJSONArray("errors");
                    if (errors != null && errors.length() > 0) {
                        reason = errors.getJSONObject(0).optString("reason");
                    }
                } catch (JSONException | NullPointerException ignored) {
                    // Never echo response bodies: error text can contain private request data.
                }
                throw new DriveBackupFlow.Failure(DriveBackupFlow.failure(status, reason));
            }
            return read(connection.getInputStream(), cap);
        } catch (DriveBackupFlow.Failure error) {
            throw error;
        } catch (IOException error) {
            throw new DriveBackupFlow.Failure(submitted ? "uncertain" : "offline");
        } finally {
            connection.disconnect();
        }
    }
    private static byte[] read(InputStream input, int cap) throws IOException {
        if (input == null) {
            return new byte[0];
        }
        try (InputStream stream = input; ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            byte[] block = new byte[2048];
            int count;
            while ((count = stream.read(block)) != -1) {
                if (output.size() + count > cap) {
                    throw new DriveBackupFlow.Failure("invalid");
                }
                output.write(block, 0, count);
            }
            return output.toByteArray();
        }
    }
    private JSONObject json(String method, String url, String type, byte[] body) throws IOException {
        try {
            return new JSONObject(new String(request(method, url, type, body, 32768), StandardCharsets.UTF_8));
        } catch (JSONException error) {
            throw new DriveBackupFlow.Failure("invalid");
        }
    }
    private DriveBackupFlow.File file(JSONObject item) throws IOException {
        String id = item.optString("id");
        id(id);
        String version = item.optString("version");
        JSONObject properties = item.optJSONObject("properties");
        if (version.isEmpty() || item.optBoolean("trashed") || !item.optBoolean("ownedByMe") || properties == null
                || !DriveBackupFlow.MARKER.equals(properties.optString("waoziBackup"))) {
            throw new DriveBackupFlow.Failure("invalid");
        }
        return new DriveBackupFlow.File(id, item.optString("name"), version);
    }
    private JSONObject metadata(String id) throws IOException {
        id(id);
        return json("GET", API + "/" + id + "?fields=" + encode(FIELDS), null, null);
    }
    @Override public List<DriveBackupFlow.File> list() throws IOException {
        String query = "trashed = false and 'me' in owners and properties has { key='waoziBackup' and value='entity-v3' }";
        JSONObject result = json("GET", API + "?q=" + encode(query) + "&spaces=drive&pageSize=16&fields="
                + encode("nextPageToken,files(" + FIELDS + ")"), null, null);
        if (!result.optString("nextPageToken").isEmpty()) {
            throw new DriveBackupFlow.Failure("duplicate");
        }
        List<DriveBackupFlow.File> files = new ArrayList<>();
        JSONArray items = result.optJSONArray("files");
        if (items == null) {
            throw new DriveBackupFlow.Failure("invalid");
        }
        for (int index = 0; index < items.length(); index++) {
            try {
                files.add(file(items.getJSONObject(index)));
            } catch (JSONException error) {
                throw new DriveBackupFlow.Failure("invalid");
            }
        }
        return files;
    }
    @Override public DriveBackupFlow.Blob read(String id) throws IOException {
        JSONObject before = metadata(id);
        DriveBackupFlow.File selected = file(before);
        long size = before.optLong("size", -1);
        if (size <= 0 || size > DriveBackupFlow.MAX_BYTES) {
            throw new DriveBackupFlow.Failure("invalid");
        }
        byte[] content = request("GET", API + "/" + id + "?alt=media", null, null, DriveBackupFlow.MAX_BYTES);
        DriveBackupFlow.File after = file(metadata(id));
        if (!selected.version.equals(after.version) || content.length != size) {
            throw new DriveBackupFlow.Failure("changed");
        }
        return new DriveBackupFlow.Blob(after, content);
    }
    @Override public DriveBackupFlow.File create(byte[] content) throws IOException {
        // Pre-generated ID is durable before POST: an uncertain result can be reconciled without a duplicate.
        String pending = preferences.getString("pending_create", "");
        if (!pending.isEmpty()) {
            try {
                DriveBackupFlow.Blob previous = read(pending);
                if (!java.util.Arrays.equals(previous.bytes, content)) {
                    throw new DriveBackupFlow.Failure("uncertain");
                }
                preferences.edit().remove("pending_create").commit();
                return previous.file;
            } catch (DriveBackupFlow.Failure error) {
                if (!"missing".equals(error.code)) {
                    throw error;
                }
            }
        }
        try {
            if (pending.isEmpty()) {
                JSONObject ids = json("GET", API + "/generateIds?count=1&space=drive&type=files", null, null);
                pending = ids.getJSONArray("ids").getString(0);
            }
            id(pending);
            if (!preferences.edit().putString("pending_create", pending).commit()) {
                throw new DriveBackupFlow.Failure("error");
            }
            JSONObject metadata = new JSONObject().put("id", pending).put("name", DriveBackupFlow.NAME)
                    .put("mimeType", "application/octet-stream")
                    .put("properties", new JSONObject().put("waoziBackup", DriveBackupFlow.MARKER));
            String boundary = "waozi_entity_v3_boundary";
            ByteArrayOutputStream body = new ByteArrayOutputStream();
            body.write(("--" + boundary + "\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
                    + metadata.toString() + "\r\n--" + boundary
                    + "\r\nContent-Type: application/octet-stream\r\n\r\n").getBytes(StandardCharsets.UTF_8));
            body.write(content);
            body.write(("\r\n--" + boundary + "--\r\n").getBytes(StandardCharsets.UTF_8));
            DriveBackupFlow.File created = file(json("POST", UPLOAD + "?uploadType=multipart&fields=" + encode(FIELDS),
                    "multipart/related; boundary=" + boundary, body.toByteArray()));
            preferences.edit().remove("pending_create").commit();
            return created;
        } catch (JSONException error) {
            throw new DriveBackupFlow.Failure("invalid");
        }
    }
    @Override public DriveBackupFlow.File replace(String id, String version, byte[] content) throws IOException {
        // Recheck immediately before mutation. Drive v3 does not document atomic compare-and-swap.
        if (!file(metadata(id)).version.equals(version)) {
            throw new DriveBackupFlow.Failure("changed");
        }
        return file(json("PATCH", UPLOAD + "/" + id + "?uploadType=media&fields=" + encode(FIELDS),
                "application/octet-stream", content));
    }
}
