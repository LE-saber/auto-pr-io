# AutoPr Keyboard Audio

Android helper APK for this project. It combines:

- ADB Keyboard-compatible IME:
  - IME id: `com.autopr.keyboardaudio/.AdbImeService`
  - supports `ADB_INPUT_TEXT`
  - supports `ADB_INPUT_B64`
- Android settings UI:
  - open input method settings
  - request internal audio capture permission
  - stop foreground audio service
- Internal audio capture helper:
  - uses Android `MediaProjection`
  - uses `AudioPlaybackCaptureConfiguration`
  - writes `latest.wav` to:
    `/sdcard/Android/data/com.autopr.keyboardaudio/files/recordings/latest.wav`

## Build

Install Android Studio or Android SDK + Gradle, then run:

```bash
cd android/AutoPrKeyboardAudio
gradle :app:assembleDebug
```

The APK will be under:

```text
app/build/outputs/apk/debug/app-debug.apk
```

## Install

```bash
adb install -r app/build/outputs/apk/debug/app-debug.apk
adb shell ime enable com.autopr.keyboardaudio/.AdbImeService
adb shell ime set com.autopr.keyboardaudio/.AdbImeService
```

## First-time audio setup

Open the app on Android and tap:

```text
Grant internal audio capture
```

Android will show the system MediaProjection permission dialog. This must be accepted manually.

## ADB record command

```bash
adb shell am broadcast \
  -a com.autopr.keyboardaudio.START_RECORD \
  --ei duration 3
```

Then pull:

```bash
adb pull /sdcard/Android/data/com.autopr.keyboardaudio/files/recordings/latest.wav latest.wav
```

## Streaming chunks

For low-latency local ASR, start recording with chunk output:

```bash
adb shell am start-foreground-service \
  -n com.autopr.keyboardaudio/.AudioCaptureService \
  -a com.autopr.keyboardaudio.START_RECORD \
  --ei duration 5 \
  --ei chunk_ms 1000
```

The service keeps `latest.wav` for the full recording and also writes chunk files:

```text
/sdcard/Android/data/com.autopr.keyboardaudio/files/recordings/chunk_0001.wav
/sdcard/Android/data/com.autopr.keyboardaudio/files/recordings/chunk_0002.wav
```

The Python `sensevoice_streaming` mode polls these chunks and transcribes each
chunk with local FunASR/SenseVoice as soon as it appears.

## Limitations

Android only allows playback capture for apps/audio streams that permit capture. Some apps, calls, DRM content, or protected media may produce silence.
