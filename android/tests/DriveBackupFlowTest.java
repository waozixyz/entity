package xyz.waozi.entity;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

public final class DriveBackupFlowTest {
    private static byte[] sealed(char c) {
        return (DriveBackupFlow.PREFIX + repeat('a', 32) + "\nnonce=" + repeat('b', 24)
                + "\nciphertext=" + repeat(c, 160) + "\n").getBytes(StandardCharsets.UTF_8);
    }
    private static String repeat(char c, int n) {
        char[] chars = new char[n];
        java.util.Arrays.fill(chars, c);
        return new String(chars);
    }
    private static void check(boolean condition) {
        if (!condition) {
            throw new AssertionError();
        }
    }
    private interface Job { void run() throws IOException; }
    private static void fails(String code, Job job) throws IOException {
        try {
            job.run();
            throw new AssertionError("Expected " + code);
        } catch (DriveBackupFlow.Failure error) {
            check(code.equals(error.code));
        }
    }
    private static final class Fake implements DriveBackupFlow.Transport {
        List<DriveBackupFlow.File> files = new ArrayList<>();
        DriveBackupFlow.Blob blob = new DriveBackupFlow.Blob(new DriveBackupFlow.File("id1", "renamed", "1"), sealed('a'));
        int reads;
        int creates;
        int writes;
        String failure;
        @Override public List<DriveBackupFlow.File> list() throws IOException {
            if (failure != null) {
                throw new DriveBackupFlow.Failure(failure);
            }
            return files;
        }
        @Override public DriveBackupFlow.Blob read(String id) throws IOException {
            reads++;
            if (failure != null) {
                throw new DriveBackupFlow.Failure(failure);
            }
            check(id.equals(blob.file.id));
            return blob;
        }
        @Override public DriveBackupFlow.File create(byte[] bytes) {
            creates++;
            check(java.util.Arrays.equals(bytes, sealed('b')));
            return new DriveBackupFlow.File("id2", DriveBackupFlow.NAME, "1");
        }
        @Override public DriveBackupFlow.File replace(String id, String version, byte[] bytes) {
            writes++;
            check(reads > 0 && id.equals(blob.file.id) && version.equals(blob.file.version));
            check(java.util.Arrays.equals(bytes, sealed('b')));
            return new DriveBackupFlow.File(id, blob.file.name, "2");
        }
    }
    public static void main(String[] args) throws IOException {
        check(DriveBackupFlow.sealed(sealed('a')));
        check(!DriveBackupFlow.sealed("plain-private-key".getBytes(StandardCharsets.UTF_8)));
        check(!DriveBackupFlow.sealed(new byte[17664]));
        check(!DriveBackupFlow.sealed(new String(sealed('a'), StandardCharsets.UTF_8).replace("v3", "v4").getBytes(StandardCharsets.UTF_8)));
        check(!DriveBackupFlow.sealed(new String(sealed('a'), StandardCharsets.UTF_8).replace("salt=aa", "salt=zz").getBytes(StandardCharsets.UTF_8)));
        check(!DriveBackupFlow.sealed(new String(sealed('a'), StandardCharsets.UTF_8).replace("passes=3", "passes=9").getBytes(StandardCharsets.UTF_8)));
        check(!DriveBackupFlow.sealed((new String(sealed('a'), StandardCharsets.UTF_8) + "garbage").getBytes(StandardCharsets.UTF_8)));
        Fake fake = new Fake();
        DriveBackupFlow flow = new DriveBackupFlow(fake);
        check(flow.candidates().isEmpty() && fake.creates == 0);
        check(flow.create(sealed('b')).id.equals("id2") && fake.creates == 1);
        fake.files.add(fake.blob.file);
        fails("duplicate", () -> flow.create(sealed('b')));
        fake.files.add(new DriveBackupFlow.File("id3", fake.blob.file.name, "3"));
        check(flow.candidates().size() == 2 && fake.writes == 0);
        fails("duplicate", () -> flow.create(sealed('b')));
        check(fake.creates == 1);
        DriveBackupFlow.Blob compared = flow.read("id1");
        check(flow.replace(compared, sealed('a')).version.equals("1") && fake.writes == 0);
        check(flow.replace(compared, sealed('b')).version.equals("2") && fake.writes == 1);
        fake.blob = new DriveBackupFlow.Blob(new DriveBackupFlow.File("id1", "renamed again", "2"), sealed('a'));
        fails("changed", () -> flow.replace(compared, sealed('b')));
        check(fake.writes == 1);
        // Bytes changed while version is unexpectedly unchanged: still no silent overwrite.
        fake.blob = new DriveBackupFlow.Blob(compared.file, sealed('c'));
        fails("changed", () -> flow.replace(compared, sealed('b')));
        fake.blob = new DriveBackupFlow.Blob(compared.file, "unknown-envelope".getBytes(StandardCharsets.UTF_8));
        fails("invalid", () -> flow.replace(compared, sealed('b')));
        for (String code : new String[]{"offline", "missing", "unauthorized", "forbidden", "quota", "full", "uncertain"}) {
            fake.failure = code;
            fails(code, () -> flow.read("id1"));
            fails(code, () -> flow.create(sealed('b')));
        }
        check(fake.writes == 1 && fake.creates == 1);
        check(DriveBackupFlow.failure(401, "").equals("unauthorized"));
        check(DriveBackupFlow.failure(403, "storageQuotaExceeded").equals("full"));
        check(DriveBackupFlow.failure(403, "rateLimitExceeded").equals("quota"));
        check(DriveBackupFlow.failure(403, "userRateLimitExceeded").equals("quota"));
        check(DriveBackupFlow.failure(403, "revoked").equals("forbidden"));
        check(DriveBackupFlow.failure(404, "").equals("missing"));
        check(DriveBackupFlow.failure(412, "").equals("changed"));
        check(DriveBackupFlow.failure(429, "").equals("quota"));
        check(DriveBackupFlow.failure(503, "").equals("offline"));
        System.out.println("Drive fake-transport tests passed: envelope bounds, duplicates, rename/ID, compare before replace, changed bytes/revision, failures.");
    }
}
