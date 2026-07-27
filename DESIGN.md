# auto-pr-io Workbench

> Product interface for supervising Windows and Android VLM automation.

## 1. Visual Theme & Atmosphere

This is an operational desktop tool, not a marketing surface. The interface
should feel quiet, precise, and trustworthy while a task is running for several
minutes. Controls recede; screen content, current state, and failures remain
immediately visible.

Design register: product UI.

- Dark graphite workspace intended for focused desktop use.
- Familiar controls and predictable placement over visual novelty.
- Dense enough for repeated work, with clear grouping and no nested cards.
- Build and Chat are distinct workspace states.
- Android and Windows are target environments, not separate applications.

## 2. Color

Semantic palette:

- Background: `#0B0D10`
- Navigation: `#0E1115`
- Surface: `#12161B`
- Raised surface: `#181D23`
- Border: `#2A323B`
- Text: `#E8EDF2`
- Muted text: `#9AA5B1`
- Primary accent: `#35B8AC`
- Selection: `#173E3B`
- Information: `#6EA8FE`
- Success: `#53B987`
- Warning: `#D9A441`
- Error: `#E06C75`

Rules:

- Accent is reserved for the active target, selection, and primary action.
- Success, warning, and error colors communicate state only.
- Body text must remain readable; muted text is never used for essential state.
- Do not add gradients, glows, glass effects, or decorative color fields.

## 3. Typography

- UI family: Segoe UI on Windows, system sans-serif fallback elsewhere.
- Code and log family: Cascadia Mono, then Consolas.
- Base size: user-adjustable 9-16 pt.
- Navigation/product title: base + 2, semibold.
- Section title: base, semibold.
- Body/control labels: base, regular.
- Metadata/status: base - 1, regular.
- Technical identifiers and coordinates use the mono family.

Only headings, selected navigation, and primary commands are bold. Do not make
the entire interface bold.

## 4. Spacing

Use the scale `4, 8, 12, 16, 24, 32` pixels.

- 4: control-internal relationships.
- 8: standard row and toolbar gap.
- 12: panel inset.
- 16: separation between control groups.
- 24: major section break.
- 32: sparse empty-state spacing.

Adjacent labels and inputs stay tight. Distinct task phases get larger gaps.
Do not use arbitrary per-widget padding unless optical alignment requires it.

## 5. Layout & Composition

Application shell:

1. Header: product identity, global state, language, font size, settings.
2. Navigation rail: Workspace, History, Skills, Logs.
3. Workspace content:
   - left: target, connection, model, task, execution options;
   - center: live screen, always the largest surface;
   - right: activity, Chat response, and forbidden-zone inspector.
4. Status bar: one concise current-state line.

The three workspace panes are resizable and have minimum useful widths.
History, Skills, and Logs are dedicated views instead of permanent competing
panels. The live screen must remain usable at the default 1400x850 window size.

## 6. Components

- Segmented controls: target (Windows/Android) and work mode (Build/Chat).
- Primary button: Start; one per workspace.
- Destructive/interrupt button: Stop or Delete, visually distinct.
- Device selector: state dot, device name, refresh command, detail line.
- Activity table: step, action, concise detail.
- Log viewer: level, preset, free-text filter, clear command.
- History: record list plus detail and screenshot preview.
- Skills: selectable list plus editor and explicit force checkbox.
- Settings: category navigation with one focused form at a time.

Every asynchronous operation exposes idle, working, success, and error states.
Buttons that cannot currently run are disabled instead of silently ignored.

## 7. Motion & Interaction

Tkinter transitions remain immediate. Motion is limited to state feedback:

- status text and color changes;
- progress indicator while scanning or running;
- current click marker on the live screen;
- live screen refresh.

Keyboard commands:

- `Ctrl+Enter`: start task.
- `Escape`: stop task.
- `F5`: refresh ADB devices.
- `Ctrl+S`: save current screenshot or current editor content by context.

Pane dragging must not cause content to overlap. Touch-style oversized controls
are unnecessary; this is a mouse and keyboard desktop tool.

## 8. Voice & Brand

Copy is direct and operational:

- Prefer "No ADB device found" to playful error language.
- State what happened and what the user can do next.
- Use sentence case.
- Keep backend and model names unchanged across locales.
- Do not expose stack traces in status labels; full details belong in Logs.

All visible interface text must come from the new localization catalog. Allow
at least 30 percent expansion for English, Japanese, and Traditional Chinese.

## 9. Anti-patterns

- No landing-page hero, gradients, decorative illustration, or marketing copy.
- No cards nested inside cards.
- No three-column wall of permanently visible utility panels.
- No global bold typography.
- No arbitrary colors, spacing, border radii, or shadows.
- No icon-only control without a tooltip or adjacent label.
- No modal for routine navigation; reserve dialogs for settings and confirmation.
- No hardcoded Chinese or English UI strings outside localization data.
- No hidden task state and no silent backend failure.
- No reuse or subclassing of the legacy `ui` package.
