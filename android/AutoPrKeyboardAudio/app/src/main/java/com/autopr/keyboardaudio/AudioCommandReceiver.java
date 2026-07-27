package com.autopr.keyboardaudio;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.util.Log;

import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;

public class AudioCommandReceiver extends BroadcastReceiver {
    private static final String TAG = "AutoPrAudio";

    @Override
    public void onReceive(Context context, Intent intent) {
        String action = intent == null ? "" : intent.getAction();
        writeStatus(context, "RECEIVER action=" + action);
        Log.i(TAG, "Receiver action=" + action);
        try {
            Intent service = new Intent(context, AudioCaptureService.class);
            service.setAction(action);
            service.putExtras(intent);
            context.startForegroundService(service);
        } catch (Exception exc) {
            writeStatus(context, "RECEIVER_ERROR " + exc.getClass().getName() + ": " + exc.getMessage());
            Log.e(TAG, "Receiver failed", exc);
        }
    }

    private static void writeStatus(Context context, String status) {
        try {
            File dir = context.getExternalFilesDir("recordings");
            if (dir != null) {
                dir.mkdirs();
                try (FileOutputStream fos = new FileOutputStream(new File(dir, AudioCaptureService.STATUS_NAME))) {
                    fos.write(status.getBytes(StandardCharsets.UTF_8));
                }
            }
        } catch (Exception ignored) {
        }
    }
}
