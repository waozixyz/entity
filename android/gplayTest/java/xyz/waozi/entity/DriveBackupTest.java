package xyz.waozi.entity;

import android.app.Activity;
import android.content.Intent;
import android.test.InstrumentationTestCase;
import java.lang.reflect.Method;

/** Moto-only smoke test: deliberately refuses any configured Google account flow. */
public final class DriveBackupTest extends InstrumentationTestCase {
    public void testUnconfiguredPlayBackupCancelsWithoutGoogle() throws Exception {
        android.content.Context target = getInstrumentation().getTargetContext();
        int key = target.getResources().getIdentifier("waozi_drive_picker_key", "string", target.getPackageName());
        assertTrue("This test requires an unconfigured Play build", key != 0 && target.getString(key).isEmpty());
        Intent launcher = target.getPackageManager().getLaunchIntentForPackage(target.getPackageName());
        assertNotNull(launcher);
        assertEquals(Intent.ACTION_MAIN, launcher.getAction());
        assertTrue(launcher.hasCategory(Intent.CATEGORY_LAUNCHER));
        launcher.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        Activity activity = getInstrumentation().startActivitySync(launcher);
        try {
            Class<?> adapter = activity.getClassLoader().loadClass("xyz.waozi.entity.DriveBackup");
            Method call = adapter.getMethod("call", Activity.class, String.class);
            assertEquals("yes", call.invoke(null, activity, "available"));
            assertTrue(((String) call.invoke(null, activity, "bad-request")).contains("invalid"));
            assertTrue(((String) call.invoke(null, activity, "restore")).contains("pending"));
            getInstrumentation().waitForIdleSync();
            call.invoke(null, activity, "cancel");
            getInstrumentation().waitForIdleSync();
            assertTrue(((String) call.invoke(null, activity, "poll")).contains("cancelled"));
        } finally {
            getInstrumentation().runOnMainSync(activity::finish);
        }
    }
}
