# ADB Phone Agent Skill

Use a fixed JSON action protocol. Return exactly one JSON object and never return an empty object.

Supported actions:

- `{"type":"click","x":500,"y":500}`
- `{"action":"tap","element":[500,500]}`
- `{"type":"type","text":"message to input"}`
- `{"type":"scroll","x":500,"y":700,"direction":"down","amount":300}`
- `{"type":"back"}`
- `{"type":"home"}`
- `{"type":"wait","seconds":1}`
- `{"type":"done"}`

For `glm_adb`, coordinates use a normalized 1000x1000 coordinate system. Top-left is `[0,0]`; bottom-right is `[1000,1000]`. The executor scales normalized coordinates to real phone pixels.

If the next step is uncertain but the screen is visible, return `wait` or `screenshot`, not `{}`.
