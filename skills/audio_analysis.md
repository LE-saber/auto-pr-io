# Audio Analysis Skill

When the Android task depends on sound, spoken instructions, a voice message, a video, a call, or a listening test, request the speech transcription tool instead of guessing from the screenshot.

Do not repeatedly click a play, speaker, voice-message, or audio button. If playback needs to be started, click it once. On the next step, request the transcription tool.

Return:

```json
{"type":"listen_audio","duration":3,"question":"what should I listen for?"}
```

Use `duration` between 1 and 30 seconds for normal tasks. Use a longer duration only when the audio is known to be long.

After the tool returns a transcript, use the transcript as context for the next UI action. If the transcript is empty, retry once with a slightly longer duration or continue from the visible screen if audio is not essential.

If the transcript says audio is unavailable or unsupported, do not keep clicking the same audio/play button. Either explain that audio capture is unavailable, ask the user for the audio text, or continue only if the visible screen is enough.

If the project says the AutoPr Keyboard Audio helper is not installed or has not produced audio, the user must install/open the helper APK and tap "Grant internal audio capture" once on the Android device.
