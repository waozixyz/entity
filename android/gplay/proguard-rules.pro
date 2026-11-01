# JNI finds this Play-only entrypoint by its public name.
-keep class xyz.waozi.entity.DriveBackup {
    public static java.lang.String call(android.app.Activity, java.lang.String);
}
-keep class xyz.waozi.entity.SignInBridge {
    public static java.lang.String call(android.app.Activity, java.lang.String);
}
