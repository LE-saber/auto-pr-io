# ADB Keyboard Skill

When text must be entered on Android, prefer the `type` action:

```json
{"type":"type","text":"要输入的文字"}
```

The executor will automatically try to enable the installed ADB Keyboard IME and send text by broadcast. This supports Chinese, spaces, punctuation, and multiline text better than `adb shell input text`.

Before typing, make sure the target input field is focused. If it is not focused, first return a `click` or `tap` action on the input field, then return the `type` action in the next step.

If the keyboard is not active or text input failed, return:

```json
{"type":"enable_keyboard"}
```

Then retry the `type` action on the next step.
