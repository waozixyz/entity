package xyz.waozi.entity;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.List;

/** Storage policy shared by every Play host. Transport never receives a password or key. */
public final class DriveBackupFlow {
    public static final int MAX_BYTES = 17663;
    public static final String MARKER = "entity-v3";
    public static final String NAME = "Waozi Account Backup.waozi-account";
    public static final String PREFIX = "waozi-account-backup-v3\nalgorithm=ML-DSA-44\nkdf=Argon2id\nmemory_kib=65536\npasses=3\nlanes=1\nsalt=";

    public static final class Failure extends IOException {
        public final String code;
        public Failure(String code) {
            super(code);
            this.code = code;
        }
    }
    public static final class File {
        public final String id;
        public final String name;
        public final String version;
        public File(String id, String name, String version) {
            this.id = id;
            this.name = name;
            this.version = version;
        }
    }
    public static final class Blob {
        public final File file;
        public final byte[] bytes;
        public Blob(File file, byte[] bytes) {
            this.file = file;
            this.bytes = bytes;
        }
    }
    public interface Transport {
        List<File> list() throws IOException;
        Blob read(String id) throws IOException;
        File create(byte[] sealed) throws IOException;
        File replace(String id, String version, byte[] sealed) throws IOException;
    }
    private final Transport transport;
    public DriveBackupFlow(Transport transport) {
        this.transport = transport;
    }

    // Structural check only. Entity's unchanged RecoveryDecode authenticates restore.
    public static boolean sealed(byte[] bytes) {
        if (bytes == null || bytes.length == 0 || bytes.length > MAX_BYTES) {
            return false;
        }
        String text = new String(bytes, StandardCharsets.UTF_8);
        if (!Arrays.equals(bytes, text.getBytes(StandardCharsets.UTF_8)) || !text.startsWith(PREFIX)) {
            return false;
        }
        int at = PREFIX.length();
        if (!hex(text, at, 32)) {
            return false;
        }
        at += 32;
        if (!text.startsWith("\nnonce=", at)) {
            return false;
        }
        at += 7;
        if (!hex(text, at, 24)) {
            return false;
        }
        at += 24;
        if (!text.startsWith("\nciphertext=", at)) {
            return false;
        }
        at += 12;
        int end = text.endsWith("\n") ? text.length() - 1 : text.length();
        return end - at > 32 && (end - at) % 2 == 0 && hex(text, at, end - at);
    }
    private static boolean hex(String text, int at, int count) {
        if (at < 0 || count <= 0 || at + count > text.length()) {
            return false;
        }
        for (int i = at; i < at + count; i++) {
            char c = text.charAt(i);
            if (!(c >= '0' && c <= '9') && !(c >= 'a' && c <= 'f') && !(c >= 'A' && c <= 'F')) {
                return false;
            }
        }
        return true;
    }
    public Blob read(String id) throws IOException {
        Blob remote = transport.read(id);
        if (!sealed(remote.bytes)) {
            throw new Failure("invalid");
        }
        return remote;
    }
    public List<File> candidates() throws IOException {
        return transport.list();
    }
    // Creation is always an explicit choice, with a fresh duplicate check.
    public File create(byte[] local) throws IOException {
        if (!sealed(local)) {
            throw new Failure("invalid");
        }
        byte[] snapshot = local.clone();
        if (!transport.list().isEmpty()) {
            throw new Failure("duplicate");
        }
        return transport.create(snapshot);
    }
    // A confirmed comparison is single-use. Changes during the dialog require another choice.
    public File replace(Blob confirmed, byte[] local) throws IOException {
        if (!sealed(local)) {
            throw new Failure("invalid");
        }
        byte[] snapshot = local.clone();
        Blob current = read(confirmed.file.id);
        if (!current.file.version.equals(confirmed.file.version) || !Arrays.equals(current.bytes, confirmed.bytes)) {
            throw new Failure("changed");
        }
        if (Arrays.equals(current.bytes, snapshot)) {
            return current.file;
        }
        return transport.replace(current.file.id, current.file.version, snapshot);
    }
    public static String failure(int status, String reason) {
        if (status == 401) {
            return "unauthorized";
        }
        if (status == 404) {
            return "missing";
        }
        if (status == 409 || status == 412) {
            return "changed";
        }
        if ("storageQuotaExceeded".equals(reason)) {
            return "full";
        }
        if (status == 429 || "rateLimitExceeded".equals(reason) || "userRateLimitExceeded".equals(reason)) {
            return "quota";
        }
        if (status == 403) {
            return "forbidden";
        }
        if (status >= 500) {
            return "offline";
        }
        return "error";
    }
}
