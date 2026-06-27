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

> **First run:** the dictionary is not bundled. Before `lookup`, `watch`, `show`,
> or `desktop` will return results, you must build the local database once with
> `import-jmdict`. See [Dictionary database location](#dictionary-database-location).

The watcher polls the system clipboard, detects Japanese text, and classifies it
as a word/phrase or sentence.
For sentences, it shows a Yomitan-style dictionary match table that you can page
through with the left and right arrow keys, plus an LLM-generated N2-friendly
explanation when an OpenAI API key is configured. The LLM response is requested
as structured JSON and then rendered into terminal sections.

Dictionary lookups use an imported JMdict JSON file stored in a local SQLite
database. By default it lives at `~/.jp_data/jp.sqlite3` so `jp` works from any
directory once imported. You can point it elsewhere with the `JP_DB_PATH`
environment variable or the `--db-path` flag (see [Dictionary database
location](#dictionary-database-location)).

## Desktop companion

The persistent desktop window stays open and updates whenever you copy Japanese.
It does not automatically open, move, or raise itself when the clipboard
changes.

```bash
python -m jp_cli desktop
```

### Build the desktop app

#### macOS

Install the packaging dependency once:

```bash
/opt/homebrew/bin/python3.11 -m venv .venv
.venv/bin/python -m pip install -e . pyinstaller
```

After making changes, rebuild, install to `~/Applications`, and relaunch:

```bash
./scripts/build_macos_app.sh
```

The script builds and verifies a native Apple-silicon bundle, quits the running
copy, replaces `~/Applications/JP Companion.app`, and opens the new version. It
also removes temporary build artifacts after a successful installation.

To create `dist/JP Companion.app` without installing or launching it:

```bash
./scripts/build_macos_app.sh --build-only
```

The packaged app uses the dictionary at `~/.jp_data/jp.sqlite3` and loads
optional API settings from `~/.jp_data/.env`. The build script generates the
macOS icon from `assets/jp-companion-icon.png`.

#### Windows

Install the packaging dependency once:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e . pyinstaller
```

After making changes, rebuild, install to `%LOCALAPPDATA%\Programs\JP Companion`,
and relaunch:

```powershell
.\scripts\build_windows_app.ps1
```

To create `dist\JP Companion\JP Companion.exe` without installing or launching it:

```powershell
.\scripts\build_windows_app.ps1 -BuildOnly
```

The packaged app uses the dictionary at `%USERPROFILE%\.jp_data\jp.sqlite3` and
loads optional API settings from `%USERPROFILE%\.jp_data\.env`. If
`assets\jp-companion-icon.ico` exists, the build script uses it as the Windows
application icon.

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

On Windows:

```powershell
.\.venv\Scripts\Activate.ps1
```

Create the shared data directory and copy the example configuration there:

```bash
mkdir -p ~/.jp_data
cp .env.example ~/.jp_data/.env
```

On Windows:

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.jp_data"
Copy-Item .env.example "$env:USERPROFILE\.jp_data\.env"
```

Then edit `~/.jp_data/.env`:

```bash
OPENAI_API_KEY=your_api_key_here
JP_LLM_MODEL=gpt-4.1-mini
```

## Dictionary database location

A fresh checkout ships **no** dictionary — the JMdict JSON and the built SQLite
database are too large to commit. Every user must build the database once with
`import-jmdict` (see below).

The database location is resolved in this order (highest priority first):

1. `--db-path <path>` flag (works on any subcommand,
   e.g. `jp lookup 先生 --db-path ~/dicts/jp.sqlite3`)
2. `JP_DB_PATH` environment variable (can be set in your shell or
   `~/.jp_data/.env`)
3. Default: `~/.jp_data/jp.sqlite3`

`import-jmdict` writes to the same resolved path, so set `JP_DB_PATH` (or pass
`--db-path`) consistently for both import and lookups. The parent directory is
created automatically.

Import JMdict (downloads of `jmdict-eng-*.json` are available from the
[JMdict project](https://github.com/scriptin/jmdict-simplified)):

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

Then copy Japanese text from anywhere to the clipboard.

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
