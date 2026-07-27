package com.autopr.keyboardaudio;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.media.projection.MediaProjectionManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.io.File;
import java.io.FileInputStream;
import java.nio.charset.StandardCharsets;

public class MainActivity extends Activity {
    private static final int REQ_CAPTURE = 1001;
    private TextView status;
    private TextView recordingState;
    private TextView rawStatus;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final Runnable statusPoller = new Runnable() {
        @Override
        public void run() {
            refreshRecordingStatus();
            handler.postDelayed(this, 1000);
        }
    };

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        int pad = (int) (16 * getResources().getDisplayMetrics().density);
        root.setPadding(pad, pad, pad, pad);
        requestNotificationPermission();

        status = new TextView(this);
        status.setText("1. Enable this app as input method.\n2. Grant audio capture.\n3. Start automation from PC.");
        root.addView(status);

        recordingState = new TextView(this);
        recordingState.setTextSize(18);
        recordingState.setPadding(0, pad / 2, 0, pad / 2);
        recordingState.setText("Recording status: not authorized");
        root.addView(recordingState);

        rawStatus = new TextView(this);
        rawStatus.setTextSize(12);
        rawStatus.setText("Raw status: none");
        root.addView(rawStatus);

        Button ime = new Button(this);
        ime.setText("Open input method settings");
        ime.setOnClickListener(v -> startActivity(new Intent(Settings.ACTION_INPUT_METHOD_SETTINGS)));
        root.addView(ime);

        Button grant = new Button(this);
        grant.setText("Grant internal audio capture");
        grant.setOnClickListener(this::requestProjection);
        root.addView(grant);

        Button test = new Button(this);
        test.setText("Test record 3s");
        test.setOnClickListener(v -> {
            Intent intent = new Intent(this, AudioCaptureService.class);
            intent.setAction(AudioCaptureService.ACTION_START_RECORD);
            intent.putExtra(AudioCaptureService.EXTRA_DURATION, 3);
            startForegroundService(intent);
            status.setText("Test recording requested. Check notification and status.txt.");
        });
        root.addView(test);

        Button refresh = new Button(this);
        refresh.setText("Refresh recording status");
        refresh.setOnClickListener(v -> refreshRecordingStatus());
        root.addView(refresh);

        Button stop = new Button(this);
        stop.setText("Stop audio service");
        stop.setOnClickListener(v -> {
            Intent intent = new Intent(this, AudioCaptureService.class);
            intent.setAction(AudioCaptureService.ACTION_SHUTDOWN);
            startService(intent);
            status.setText("Audio service stop requested.");
        });
        root.addView(stop);

        setContentView(root);
        refreshRecordingStatus();
    }

    @Override
    protected void onResume() {
        super.onResume();
        handler.post(statusPoller);
    }

    @Override
    protected void onPause() {
        super.onPause();
        handler.removeCallbacks(statusPoller);
    }

    private void requestProjection(View view) {
        MediaProjectionManager mgr = (MediaProjectionManager) getSystemService(Context.MEDIA_PROJECTION_SERVICE);
        startActivityForResult(mgr.createScreenCaptureIntent(), REQ_CAPTURE);
    }

    private void requestNotificationPermission() {
        if (Build.VERSION.SDK_INT >= 33
                && checkSelfPermission("android.permission.POST_NOTIFICATIONS") != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[] {"android.permission.POST_NOTIFICATIONS"}, 2001);
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == REQ_CAPTURE && resultCode == RESULT_OK && data != null) {
            Intent intent = new Intent(this, AudioCaptureService.class);
            intent.setAction(AudioCaptureService.ACTION_INIT_PROJECTION);
            intent.putExtra(AudioCaptureService.EXTRA_RESULT_CODE, resultCode);
            intent.putExtra(AudioCaptureService.EXTRA_RESULT_DATA, data);
            intent.putExtra(AudioCaptureService.EXTRA_START_AFTER_INIT, true);
            intent.putExtra(AudioCaptureService.EXTRA_DURATION, 3);
            startForegroundService(intent);
            status.setText("Audio capture permission granted. Test recording started for 3 seconds.");
            refreshRecordingStatus();
        } else {
            status.setText("Audio capture permission denied.");
            refreshRecordingStatus();
        }
    }

    private void refreshRecordingStatus() {
        String raw = readStatus();
        rawStatus.setText("Raw status: " + (raw.isEmpty() ? "none" : raw));
        recordingState.setText("Recording status: " + describeStatus(raw));
    }

    private String describeStatus(String raw) {
        if (raw == null || raw.isEmpty() || raw.startsWith("SERVICE_CREATED")) {
            return "not authorized / service idle";
        }
        if (raw.startsWith("START_RECORD") || raw.startsWith("CHUNK")) {
            return "recording internal audio";
        }
        if (raw.startsWith("READY projection initialized")) {
            return "authorized, not recording";
        }
        if (raw.startsWith("OK bytes=")) {
            return "authorized, recording finished";
        }
        if (raw.startsWith("ERROR: already recording")) {
            return "recording internal audio";
        }
        if (raw.startsWith("ERROR: MediaProjection is not initialized")) {
            return "not authorized";
        }
        if (raw.startsWith("ERROR")) {
            return "error: " + raw;
        }
        if (raw.startsWith("STOP_RECORD")) {
            return "not recording";
        }
        return raw;
    }

    private String readStatus() {
        File dir = getExternalFilesDir("recordings");
        if (dir == null) {
            return "";
        }
        File file = new File(dir, AudioCaptureService.STATUS_NAME);
        if (!file.exists()) {
            return "";
        }
        try (FileInputStream input = new FileInputStream(file)) {
            byte[] data = new byte[(int) file.length()];
            int read = input.read(data);
            if (read <= 0) {
                return "";
            }
            return new String(data, 0, read, StandardCharsets.UTF_8).trim();
        } catch (Exception ignored) {
            return "";
        }
    }
}
