# cida-work

Use this skill for CIDA / VocabGo vocabulary practice screens on `app.vocabgo.com`. The goal is to complete exercise questions correctly through screen observation, audio transcription, option selection, and the green Continue button.

Keywords: CIDA, VocabGo, app.vocabgo.com, vocabulary practice, 自动化做题测试, 做题, 练习, 题目, 题型, 词义, 听力, 填空, 搭配, 多选, 单选.

## Global UI Rules

- The page title is usually `练习` and has a progress bar near the top.
- The top-left `返回` control is only for leaving the exercise. Do not tap it during normal solving.
- The bottom green button labeled `继续` means Continue / Next. Tap it only after the current card or question is already answered, or when the screen is a vocabulary learning card with no answer choices.
- The black document-with-magnifier icon near the bottom opens details/explanation. Do not use it unless extra explanation is needed.
- A yellow/orange left-pointing arrow button inside an exercise is Delete/Backspace for removing the last selected word. It is not Back, Next, or Submit.
- Android system navigation buttons at the very bottom are not part of the exercise. Do not tap them.

## First Identify the Screen Type

Before acting, classify the current screen into one of these types:

1. Vocabulary card / learning card
2. Sentence meaning multiple choice
3. Listening multiple choice
4. Collocation, multi-select, or phrase-fill exercise

Do not repeatedly click the same area. If the screen does not change after a click, re-observe and choose a different action.

## Type 1: Vocabulary Card / Learning Card

Visual pattern:

- A large English word is centered in a pale green card.
- Pronunciation lines for American/British audio may appear below the word.
- A Chinese meaning section such as `词义` is visible.
- There are no answer choices to select.
- A large green `继续` button appears near the bottom.

Action:

```json
{"type":"click","x":<center of green Continue button>,"y":<center of green Continue button>}
```

Do not click pronunciation icons unless the user task specifically asks to listen.

## Type 2: Sentence Meaning Multiple Choice

Visual pattern:

- An English sentence is displayed.
- One target word in the sentence is green and underlined.
- A Chinese translation may appear under the sentence.
- Several large rectangular answer options list part of speech and Chinese meanings.

Reasoning:

- Use the target word in the sentence and the Chinese translation to infer the correct meaning.
- Match part of speech when available (`n.`, `v.`, `vt.`, `vi.`, `adj.`, etc.).
- Pick the option whose Chinese meaning and usage best fits the sentence.
- If one option is already green with a check mark, it is selected. If the screen then has a green `继续` button, tap Continue.

Action:

```json
{"type":"click","x":<center of correct option>,"y":<center of correct option>}
```

After selection, if `继续` appears, tap it.

## Type 3: Listening Multiple Choice

Visual pattern:

- A green circular play button and text like `播放` appear.
- The answer options are meanings or definitions.
- The needed word or phrase is spoken, not written on the screen.

Action sequence:

1. If audio has not been played, tap the green play button once.
2. Request audio transcription.

```json
{"type":"listen_audio","duration":5,"question":"transcribe the spoken word or phrase for this vocabulary listening question"}
```

3. Use the transcript to choose the matching option.

Important:

- Do not keep tapping the play button.
- If an audio transcript is already available, use it now; do not request `listen_audio` again unless the transcript is empty or clearly unrelated.
- If the transcript is a word, choose the option whose Chinese meaning matches that word.
- If the transcript is unclear, use visible option meanings and likely pronunciation, then choose the best match.

## Type 4A: Collocation / Multi-Select

Visual pattern:

- The prompt says: `Choose the words commonly used together with <target word>`.
- Chinese hint may say: `本题有4个答案，选中3个即可通过`.
- It shows counters such as `剩余机会` and `还需选中`.
- Candidate words are displayed as rounded rectangular chips.
- Selected correct chips become green with a check mark.
- A star on a chip can indicate a revealed correct answer or an important candidate; inspect it but do not blindly tap it if the required count is already zero.

Reasoning:

- Choose words that form natural English collocations with the target word.
- Stop selecting once `还需选中` is `0`.
- If the green `继续` button is visible after enough selections, tap Continue.

Action:

```json
{"type":"click","x":<center of selected collocation chip>,"y":<center of selected collocation chip>}
```

## Type 4B: Phrase Fill From Word Tiles

Visual pattern:

- A target word appears above one or more underline blanks.
- Chinese meaning appears below the blanks.
- Word tiles are shown in a grid.
- There may be an orange/yellow left arrow button.

Reasoning:

- Count the visible blanks before selecting. One underline group usually means one word; multiple adjacent underline groups usually mean a phrase.
- Fill the blanks in left-to-right order.
- Choose tiles that form the correct phrase matching the Chinese meaning.
- Example pattern: target `bail` with two blanks and meaning `保释；保释中` should form `on bail`, so choose `on` then `bail`.
- If the wrong tile was selected, use the yellow/orange left arrow to delete the last selected tile. Do not treat it as submit or back.

Action:

```json
{"type":"click","x":<center of next correct word tile>,"y":<center of next correct word tile>}
```

After all blanks are filled and the answer is marked correct, tap `继续` if visible.

## Completion / Continue Behavior

- If the screen says `回答正确`, the answer is complete. Tap `继续`.
- If a green `继续` button is visible and the current task has no unanswered blanks or unselected required options, tap it.
- If the question still requires selections (`还需选中` greater than 0) or blanks are empty, do not tap Continue yet.
- If an answer is wrong and a delete arrow is present, use delete only when it removes an incorrect selected word.

## JSON Action Discipline

Return exactly one JSON action. Prefer one of:

```json
{"type":"click","x":500,"y":500}
{"type":"listen_audio","duration":5,"question":"what word or phrase is spoken?"}
{"type":"wait","seconds":1}
{"type":"done"}
```

Use `done` only when the overall user-requested automation task is complete, not merely because one question was answered.
