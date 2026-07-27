package com.autopr.keyboardaudio;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.media.AudioAttributes;
import android.media.AudioFormat;
import android.media.AudioPlaybackCaptureConfiguration;
import android.media.AudioRecord;
import android.media.projection.MediaProjection;
import android.media.projection.MediaProjectionManager;
import android.os.Build;
import android.os.Environment;
import android.os.IBinder;
import android.util.Log;

import java.io.File;
import java.io.ByteArrayOutputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

public class AudioCaptureService extends Service {
    private static final String TAG = "AutoPrAudio";
    public static final String ACTION_INIT_PROJECTION = "com.autopr.keyboardaudio.INIT_PROJECTION";
    public static final String ACTION_SHUTDOWN = "com.autopr.keyboardaudio.SHUTDOWN";
    public static final String ACTION_START_RECORD = "com.autopr.keyboardaudio.START_RECORD";
    public static final String ACTION_STOP_RECORD = "com.autopr.keyboardaudio.STOP_RECORD";
    public static final String EXTRA_RESULT_CODE = "result_code";
    public static final String EXTRA_RESULT_DATA = "result_data";
    public static final String EXTRA_DURATION = "duration";
    public static final String EXTRA_CHUNK_MS = "chunk_ms";
    public static final String EXTRA_START_AFTER_INIT = "start_after_init";
    public static final String OUTPUT_NAME = "latest.wav";
    public static final String STATUS_NAME = "status.txt";
    public static final String CHUNK_PREFIX = "chunk_";
    private static final int MAX_RECORD_SECONDS = 21600; // 6 hours; PC side stops the service.

    private MediaProjection projection;
    private volatile boolean recording = false;
    private Thread worker;

    @Override
    public void onCreate() {
        super.onCreate();
        startForeground(1, notification("Ready"));
        writeStatus("SERVICE_CREATED");
        Log.i(TAG, "Service created");
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent == null || intent.getAction() == null) {
            writeStatus("IGNORED empty intent");
            return START_STICKY;
        }
        String action = intent.getAction();
        Log.i(TAG, "onStartCommand action=" + action);
        try {
            if (ACTION_INIT_PROJECTION.equals(action)) {
                MediaProjectionManager mgr = (MediaProjectionManager) getSystemService(Context.MEDIA_PROJECTION_SERVICE);
                int code = intent.getIntExtra(EXTRA_RESULT_CODE, 0);
                Intent data = intent.getParcelableExtra(EXTRA_RESULT_DATA);
                if (mgr == null || data == null) {
                    writeStatus("ERROR: missing MediaProjection data");
                } else {
                    projection = mgr.getMediaProjection(code, data);
                    if (projection == null) {
                        writeStatus("ERROR: MediaProjection returned null");
                    } else if (intent.getBooleanExtra(EXTRA_START_AFTER_INIT, false)) {
                        int duration = intent.getIntExtra(EXTRA_DURATION, 3);
                        writeStatus("READY projection initialized; starting test record");
                        startRecording(Math.max(1, Math.min(duration, 300)));
                    } else {
                        writeStatus("READY projection initialized");
                    }
                }
            } else if (ACTION_START_RECORD.equals(action)) {
                int duration = intent.getIntExtra(EXTRA_DURATION, 3);
                int chunkMs = intent.getIntExtra(EXTRA_CHUNK_MS, 0);
                if (chunkMs > 0) {
                    startRecording(Math.max(1, Math.min(duration, MAX_RECORD_SECONDS)), Math.max(500, Math.min(chunkMs, 10000)));
                } else {
                    startRecording(Math.max(1, Math.min(duration, MAX_RECORD_SECONDS)), 0);
                }
            } else if (ACTION_STOP_RECORD.equals(action)) {
                recording = false;
                writeStatus(projection == null ? "STOP_RECORD requested; not authorized" : "READY projection initialized; idle");
            } else if (ACTION_SHUTDOWN.equals(action)) {
                recording = false;
                writeStatus("SHUTDOWN requested");
                stopSelf();
            } else {
                writeStatus("IGNORED action=" + action);
            }
        } catch (Exception exc) {
            writeStatus("ERROR action=" + action + " " + exc.getClass().getName() + ": " + exc.getMessage());
            Log.e(TAG, "Action failed: " + action, exc);
        }
        return START_STICKY;
    }

    private void startRecording(int durationSec) {
        startRecording(durationSec, 0);
    }

    private void startRecording(int durationSec, int chunkMs) {
        if (projection == null || recording) {
            writeStatus(projection == null ? "ERROR: MediaProjection is not initialized" : "ERROR: already recording");
            return;
        }
        recording = true;
        startForeground(1, notification("Recording internal audio"));
        writeStatus("START_RECORD duration=" + durationSec + " chunk_ms=" + chunkMs);
        Log.i(TAG, "Recording started duration=" + durationSec + " chunkMs=" + chunkMs);
        worker = new Thread(() -> recordPcmWav(durationSec, chunkMs), "AutoPrAudioRecord");
        worker.start();
    }

    private void recordPcmWav(int durationSec, int chunkMs) {
        int sampleRate = 44100;
        int channelMask = AudioFormat.CHANNEL_IN_STEREO;
        int encoding = AudioFormat.ENCODING_PCM_16BIT;
        int minBuffer = AudioRecord.getMinBufferSize(sampleRate, channelMask, encoding);
        int bufferSize = Math.max(minBuffer, sampleRate * 4);

        AudioPlaybackCaptureConfiguration config = new AudioPlaybackCaptureConfiguration.Builder(projection)
            .addMatchingUsage(AudioAttributes.USAGE_MEDIA)
            .addMatchingUsage(AudioAttributes.USAGE_GAME)
            .addMatchingUsage(AudioAttributes.USAGE_UNKNOWN)
            .build();

        AudioRecord record = new AudioRecord.Builder()
            .setAudioFormat(new AudioFormat.Builder()
                .setSampleRate(sampleRate)
                .setChannelMask(channelMask)
                .setEncoding(encoding)
                .build())
            .setBufferSizeInBytes(bufferSize)
            .setAudioPlaybackCaptureConfig(config)
            .build();

        File out = outputFile();
        out.getParentFile().mkdirs();
        cleanupChunks(out.getParentFile());
        byte[] buffer = new byte[bufferSize];
        long endAt = System.currentTimeMillis() + durationSec * 1000L;
        long nextChunkAt = chunkMs > 0 ? System.currentTimeMillis() + chunkMs : Long.MAX_VALUE;
        int totalBytes = 0;
        int chunkIndex = 0;
        ByteArrayOutputStream chunkBuffer = chunkMs > 0 ? new ByteArrayOutputStream(sampleRate * 4) : null;

        boolean failed = false;
        try (FileOutputStream fos = new FileOutputStream(out)) {
            writeWavHeader(fos, 0, sampleRate, 2, 16);
            record.startRecording();
            while (recording && System.currentTimeMillis() < endAt) {
                int read = record.read(buffer, 0, buffer.length);
                if (read > 0) {
                    fos.write(buffer, 0, read);
                    totalBytes += read;
                    if (chunkBuffer != null) {
                        chunkBuffer.write(buffer, 0, read);
                    }
                }
                if (chunkBuffer != null && System.currentTimeMillis() >= nextChunkAt && chunkBuffer.size() > 0) {
                    chunkIndex += 1;
                    writeChunk(out.getParentFile(), chunkIndex, chunkBuffer.toByteArray(), sampleRate, 2, 16);
                    chunkBuffer.reset();
                    nextChunkAt = System.currentTimeMillis() + chunkMs;
                }
            }
            if (chunkBuffer != null && chunkBuffer.size() > 0) {
                chunkIndex += 1;
                writeChunk(out.getParentFile(), chunkIndex, chunkBuffer.toByteArray(), sampleRate, 2, 16);
            }
            patchWavHeader(out, totalBytes, sampleRate, 2, 16);
            writeStatus("OK bytes=" + totalBytes + " chunks=" + chunkIndex + " path=" + out.getAbsolutePath());
            Log.i(TAG, "Recording finished bytes=" + totalBytes + " path=" + out.getAbsolutePath());
        } catch (Exception ignored) {
            failed = true;
            writeStatus("ERROR: " + ignored.getClass().getName() + ": " + ignored.getMessage());
            Log.e(TAG, "Recording failed", ignored);
        } finally {
            try { record.stop(); } catch (Exception ignored) {}
            record.release();
            recording = false;
            startForeground(1, notification("Ready"));
            if (!failed && projection != null) {
                writeStatus("READY projection initialized; idle");
            }
        }
    }

    private File outputFile() {
        File dir = getExternalFilesDir("recordings");
        if (dir == null) {
            dir = new File(Environment.getExternalStorageDirectory(), "AutoPrAudio");
        }
        return new File(dir, OUTPUT_NAME);
    }

    private File chunkFile(File dir, int index) {
        return new File(dir, String.format(java.util.Locale.US, "%s%04d.wav", CHUNK_PREFIX, index));
    }

    private void cleanupChunks(File dir) {
        File[] files = dir.listFiles();
        if (files == null) return;
        for (File file : files) {
            if (file.getName().startsWith(CHUNK_PREFIX) && file.getName().endsWith(".wav")) {
                try { file.delete(); } catch (Exception ignored) {}
            }
        }
    }

    private void writeChunk(File dir, int index, byte[] pcm, int sampleRate, int channels, int bits) throws IOException {
        File chunk = chunkFile(dir, index);
        try (FileOutputStream out = new FileOutputStream(chunk)) {
            writeWavHeader(out, pcm.length, sampleRate, channels, bits);
            out.write(pcm);
        }
        writeStatus("CHUNK index=" + index + " path=" + chunk.getAbsolutePath());
    }

    private File statusFile() {
        File dir = getExternalFilesDir("recordings");
        if (dir == null) {
            dir = new File(Environment.getExternalStorageDirectory(), "AutoPrAudio");
        }
        dir.mkdirs();
        return new File(dir, STATUS_NAME);
    }

    private void writeStatus(String status) {
        try (FileOutputStream fos = new FileOutputStream(statusFile())) {
            fos.write(status.getBytes(StandardCharsets.UTF_8));
        } catch (Exception ignored) {
        }
    }

    private Notification notification(String text) {
        String channelId = "autopr_audio";
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationChannel ch = new NotificationChannel(channelId, "AutoPr Audio", NotificationManager.IMPORTANCE_LOW);
            getSystemService(NotificationManager.class).createNotificationChannel(ch);
        }
        Notification.Builder b = Build.VERSION.SDK_INT >= 26 ? new Notification.Builder(this, channelId) : new Notification.Builder(this);
        return b.setContentTitle("AutoPr Keyboard Audio").setContentText(text).setSmallIcon(android.R.drawable.ic_btn_speak_now).build();
    }

    private static void writeWavHeader(FileOutputStream out, int pcmBytes, int sampleRate, int channels, int bits) throws IOException {
        int byteRate = sampleRate * channels * bits / 8;
        byte[] header = new byte[44];
        header[0]='R'; header[1]='I'; header[2]='F'; header[3]='F';
        writeInt(header, 4, 36 + pcmBytes);
        header[8]='W'; header[9]='A'; header[10]='V'; header[11]='E';
        header[12]='f'; header[13]='m'; header[14]='t'; header[15]=' ';
        writeInt(header, 16, 16);
        writeShort(header, 20, (short)1);
        writeShort(header, 22, (short)channels);
        writeInt(header, 24, sampleRate);
        writeInt(header, 28, byteRate);
        writeShort(header, 32, (short)(channels * bits / 8));
        writeShort(header, 34, (short)bits);
        header[36]='d'; header[37]='a'; header[38]='t'; header[39]='a';
        writeInt(header, 40, pcmBytes);
        out.write(header);
    }

    private static void patchWavHeader(File file, int pcmBytes, int sampleRate, int channels, int bits) throws IOException {
        byte[] header = new byte[44];
        fillWavHeader(header, pcmBytes, sampleRate, channels, bits);
        try (java.io.RandomAccessFile raf = new java.io.RandomAccessFile(file, "rw")) {
            raf.seek(0);
            raf.write(header);
        }
    }

    private static void fillWavHeader(byte[] header, int pcmBytes, int sampleRate, int channels, int bits) {
        int byteRate = sampleRate * channels * bits / 8;
        header[0]='R'; header[1]='I'; header[2]='F'; header[3]='F';
        writeInt(header, 4, 36 + pcmBytes);
        header[8]='W'; header[9]='A'; header[10]='V'; header[11]='E';
        header[12]='f'; header[13]='m'; header[14]='t'; header[15]=' ';
        writeInt(header, 16, 16);
        writeShort(header, 20, (short)1);
        writeShort(header, 22, (short)channels);
        writeInt(header, 24, sampleRate);
        writeInt(header, 28, byteRate);
        writeShort(header, 32, (short)(channels * bits / 8));
        writeShort(header, 34, (short)bits);
        header[36]='d'; header[37]='a'; header[38]='t'; header[39]='a';
        writeInt(header, 40, pcmBytes);
    }

    private static void writeInt(byte[] b, int off, int v) {
        b[off]=(byte)v; b[off+1]=(byte)(v>>8); b[off+2]=(byte)(v>>16); b[off+3]=(byte)(v>>24);
    }

    private static void writeShort(byte[] b, int off, short v) {
        b[off]=(byte)v; b[off+1]=(byte)(v>>8);
    }

    @Override
    public IBinder onBind(Intent intent) { return null; }
}
