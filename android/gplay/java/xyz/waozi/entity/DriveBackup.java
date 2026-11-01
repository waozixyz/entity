package xyz.waozi.entity;

import android.app.Activity;
import android.content.Intent;
import org.json.JSONObject;
import org.json.JSONException;

/** Class-loader bridge: only a Play source set includes this class. */
public final class DriveBackup {
    private static String command;
    private static String answer = "{\"status\":\"idle\"}";
    private static boolean busy;
    private static DriveActivity current;
    private static int serial;

    private DriveBackup() {}
    public static synchronized String call(Activity activity, String request) {
        if (request == null) {
            return "{\"status\":\"invalid\"}";
        }
        if ("available".equals(request)) {
            return "yes";
        }
        if ("poll".equals(request)) {
            return answer;
        }
        if ("cancel".equals(request)) {
            if (current != null) {
                current.cancelOperation();
            } else {
                serial++;
                finish("cancelled", "");
            }
            return answer;
        }
        if (busy) {
            return "{\"status\":\"busy\"}";
        }
        if (!("restore".equals(request) || request.startsWith("save\n")) || request.length() > 17700) {
            return "{\"status\":\"invalid\"}";
        }
        busy = true;
        final int ticket = ++serial;
        command = request;
        answer = "{\"status\":\"pending\"}";
        activity.runOnUiThread(() -> {
            try {
                activity.startActivity(new Intent(activity, DriveActivity.class).putExtra("waoziDriveRequest", ticket));
            } catch (RuntimeException error) {
                synchronized (DriveBackup.class) {
                    if (ticket == serial) {
                        finish("unavailable", "");
                    }
                }
            }
        });
        return answer;
    }
    static synchronized boolean attach(DriveActivity activity, int ticket) {
        if (ticket != serial || !busy || current != null) {
            return false;
        }
        current = activity;
        return true;
    }
    static synchronized void detach(DriveActivity activity) {
        if (current == activity) {
            current = null;
        }
    }
    static synchronized String takeCommand() {
        String result = command;
        command = null;
        return result;
    }
    static synchronized void finish(DriveActivity activity, String status, String content) {
        if (current == activity) {
            finish(status, content);
        }
    }
    private static synchronized void finish(String status, String content) {
        try {
            answer = new JSONObject().put("status", status).put("content", content).toString();
        } catch (JSONException error) {
            answer = "{\"status\":\"error\"}";
        }
        busy = false;
        command = null;
    }
}
