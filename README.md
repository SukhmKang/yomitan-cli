# jp-cli-tool

A tiny terminal Japanese lookup helper.

Right now it implements:

```bash
python3 -m jp_cli watch
python3 -m jp_cli desktop
python3 -m jp_cli import-jmdict jmdict-eng-3.6.2.json
python3 -m jp_cli lookup "先生"
python3 -m jp_cli show "先生に言われたことがまだ気になっている。"
python3 -m jp_cli explain "先生に言われたことがまだ気になっている。"
python3 -m jp_cli inspect "先生に言われたことがまだ気になっている。"
```

The watcher polls the macOS clipboard, detects Japanese text, and classifies it
as a word/phrase or sentence.
For sentences, it shows a Yomitan-style dictionary match table that you can page
through with the left and right arrow keys, plus an LLM-generated N2-friendly
explanation when an OpenAI API key is configured. The LLM response is requested
as structured JSON and then rendered into terminal sections.

Dictionary lookups use an imported JMdict JSON file stored in a local SQLite
database under `.jp_data/`.

## Desktop companion

The persistent desktop window stays open and updates whenever you copy Japanese.
It does not automatically open, move, or raise itself when the clipboard
changes.

```bash
python -m jp_cli desktop
```

Use the left/right or up/down arrow keys to move through dictionary matches.
`Tab` toggles between the dictionary and `やさしく説明` views. The explanation
runs in a background worker so dictionary navigation remains responsive.

Sentence lookup is dictionary-driven. At each useful character position it:

1. Tries source prefixes longest-first.
2. Generates chained, condition-aware deinflections.
3. Validates candidates against structured JMdict word classes.
4. Consumes the longest grammar-valid dictionary span.

`fugashi` only supplies negative boundary hints for particles and auxiliaries,
plus a weak part-of-speech tie-breaker. It does not choose displayed word
boundaries or dictionary forms.

The deinflection architecture and Japanese transform rules are adapted from
[Yomitan](https://github.com/yomidevs/yomitan), licensed under
GPL-3.0-or-later. See `LICENSE`.

LLM explanations are cached in the same SQLite database by sentence and model, so
copying the same sentence again reuses the stored structured explanation.

## Try it

Activate your virtualenv first:

```bash
source .venv/bin/activate
```

Create a local `.env` file for the LLM explanation:

```bash
cp .env.example .env
```

Then edit `.env`:

```bash
OPENAI_API_KEY=your_api_key_here
JP_LLM_MODEL=gpt-4.1-mini
```

Import JMdict:

```bash
python -m jp_cli import-jmdict jmdict-eng-3.6.2.json
```

Test dictionary lookup:

```bash
python -m jp_cli lookup "先生"
python -m jp_cli lookup "言う"
```

In one terminal:

```bash
python -m jp_cli watch
```

Then copy Japanese text from anywhere with `Cmd+C`.

Use `←` and `→` to move through dictionary matches.

Use `Tab` to toggle the detail pane between the selected word and the
`やさしく説明` explanation.

Press `q` or `Ctrl+C` in the watcher terminal to quit.

You can also test the detector directly:

```bash
python -m jp_cli inspect "食べられなかった"
python -m jp_cli inspect "先生に言われたことがまだ気になっている。"
```

To test the sentence pager without using the clipboard:

```bash
python -m jp_cli show "先生に言われたことがまだ気になっている。"
```

To test only the LLM explanation:

```bash
python -m jp_cli explain "先生に言われたことがまだ気になっている。"
```

If you want the shorter `jp` command:

```bash
python -m pip install -e .
jp watch
```
