<p align="center"><img src="ui/logo.svg" alt="EmbedCo logo" width="96"></p>

# EmbedCo

Visual block programming for Arduino and other microcontrollers.

## Installation

Use the installer scripts to install **arduino-cli** (for compile/upload) and EmbedCo’s Python dependencies.

**Linux / macOS (bash):**

```bash
chmod +x installer/install.sh
./installer/install.sh
```

Options: `--prefix DIR` (arduino-cli install location, default `~/.local/bin`), `--project-dir DIR`, `--skip-arduino-cli`, `--skip-python-deps`.

**Windows (PowerShell):**

```powershell
.\installer\install.ps1
```

Runs an interactive checkbox menu to select components (arduino-cli, Python dependencies, Arduino core index update, Arduino AVR core `arduino:avr`). Use Up/Down to move, Space to toggle, Enter to continue.

Options: `-Prefix <DIR>` (default `$env:LOCALAPPDATA\EmbedCo\bin`), `-ProjectDir <DIR>`, `-SkipArduinoCli`, `-SkipPythonDeps`, `-NonInteractive` (use defaults/parameters without the menu).

> After installing arduino-cli, ensure its install directory is on your `PATH` (the Windows installer adds it to the user PATH; restart your terminal if needed). You may also need to install board cores, e.g. `arduino-cli core install arduino:avr`.

## Run the editor

    pip install -r requirements.txt
    python server.py

Your browser opens at http://127.0.0.1:8000. Build with blocks, watch the sketch
update live, then copy it or download the .ino file. Export JSON saves your
project; Import JSON loads it again.

## Upload to a board

Click **Upload** in the editor: it compiles the current sketch with
[arduino-cli](https://arduino.github.io/arduino-cli/) and flashes it to the
selected board + serial port (detected automatically, e.g. COM5). Requires
arduino-cli on PATH plus the board core installed for the chosen board.
**Verify (compile only)** checks the sketch without flashing.

## Projects (VS Code-style Explorer)

- **Projects** (activity bar) opens the Explorer: every project is a
  `<name>.json` file in `projects/`, with board / last-edited / node count
- **+ New** creates one, click to open, **rename**, **duplicate**, **delete**
- **Save** (or **Ctrl+S**) writes the current canvas; the breadcrumb bar shows
  `projects/<name>.json` and whether it is `modified` or `saved`
- The last-open project restores on reload, like a VS Code workspace.

## Canvas zoom & pan

- **Ctrl+scroll** zooms at the cursor (30–250%, persisted), **+ / − / 0** keys,
  zoom buttons + % readout, **fit**, **grid toggle**
- Drag empty canvas (or hold **Space**) to pan; the **minimap** bottom-right
  shows the viewport and jumps the canvas when clicked

## Keyboard shortcuts & Settings

- Press **?** (or Plugins > Settings) for the full reference. Highlights:
  `Ctrl+S` save, `Ctrl+N` new, `Ctrl+O` Explorer, `Ctrl+P` Quick Open,
  `Ctrl+,` Settings, `Ctrl+Z` / `Ctrl+Shift+Z` undo/redo, `Delete` remove node,
  `Ctrl+D` duplicate node, `Ctrl+E` export, `Ctrl+Enter` upload,
  `Ctrl+1…4` switch views, `Esc` close/deselect
- **Settings** (bottom of the activity bar, or `Ctrl+,`): theme, grid,
  minimap, zoom, code-preview highlighting / line numbers / word wrap /
  font size, and autosave (every 5–30s) — all persisted in your browser

## Plugins

- Drop a plugin `.json` into **`plugins/`** (a JSON object with a `categories` map, same block schema as the YAML category files)
  and restart `server.py` — or install one from the **Plugins** panel
- Each plugin can be **enabled/disabled** there; disabled blocks vanish from
  the palette but old projects that use them still build

## Command line

    python main.py                         build the built-in examples into ./output
    python main.py project.json            build a project exported from the editor
    python main.py project.json --board esp32 --out build/

Exit code is 0 on success, 1 if any project failed to build, 2 on I/O errors.

## Project layout

    server.py, main.py          thin entry points (editor / CLI builder)
    embedco/
      settings.py               configuration (defaults + EMBEDCO_* env vars)
      logging_config.py         console/file/JSON logging, request ids, excepthooks
      errors.py                 exception hierarchy (BlockError, ServiceError, ...)
      util.py                   slugify, atomic file writes
      cli.py                    argparse front-ends for server.py / main.py
      generator/                block graph -> Arduino sketch (no I/O beyond loading YAML)
        text.py                 C++ text helpers          boards.py   board profiles
        catalog.py              block catalog + palette   plugins.py  plugin registry
        state.py                per-run state             inputs.py   input resolution
        control.py              if/repeat/while/timer     core.py     EmbedCoGenerator
      services/                 business logic, no HTTP knowledge
        codegen.py              thread-safe generator facade
        projects.py             atomic JSON project store
        arduino.py              arduino-cli compile/upload, serial ports
        terminal.py             in-browser terminal (audited)
      web/                      HTTP layer
        router.py  routes.py    route table + API handlers
        handler.py              request ids, access log, guards, error mapping
        app.py                  service wiring, server lifecycle, signals
    blocks/categories/*.yaml    block definitions and C++ templates
    boards.yaml                 board profiles
    ui/index.html               the editor
    tests/                      unittest suite (golden generator output, HTTP, store)

## Configuration

Flags on `server.py` (`--host --port --no-browser --log-level --log-format`) override
environment variables, which override defaults.

| Variable | Default | Meaning |
|---|---|---|
| `EMBEDCO_HOME` | repo root | where `blocks/`, `boards.yaml`, `plugins/`, `projects/`, `ui/` live |
| `EMBEDCO_HOST` / `_PORT` | `127.0.0.1` / `8000` | bind address / port |
| `EMBEDCO_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `EMBEDCO_LOG_FORMAT` | `text` | `text` or `json` (one object per line) |
| `EMBEDCO_LOG_DIR` | `<home>/logs` | log directory |
| `EMBEDCO_LOG_TO_FILE` | `1` | write rotating log files |
| `EMBEDCO_TERMINAL` | `1` | in-browser terminal (forced off on non-loopback binds) |
| `EMBEDCO_MAX_BODY_BYTES` | `5242880` | request body limit (413 above this) |

## Logging

- Console (stderr) plus `logs/embedco.log` (10 MiB x 5 rotation) and `logs/error.log`
  (WARNING and above, 5 MiB x 3).
- Every record carries a `request_id`. Send `X-Request-ID` to supply your own (it is
  validated); otherwise one is generated. It is echoed in the response header and in
  every error body, so a user-reported id leads straight to the matching log lines.
- Loggers: `embedco.access` (one line per request with status and duration),
  `embedco.terminal.audit` (every terminal command), plus one logger per module.
- With `EMBEDCO_LOG_FORMAT=json`, extra fields (`method`, `path`, `status`,
  `duration_ms`, `client`) are real JSON keys, ready for Loki/ELK/CloudWatch.
- Unexpected exceptions are logged with full tracebacks and answered with a generic
  500 plus the request id; internals are never sent to the browser. Uncaught exceptions
  in any thread are logged too.
- Expected user errors (bad blocks, validation) log at INFO; security rejections
  (bad Host/Origin, oversized bodies, rejected terminal calls) log at WARNING.

## Security notes

The editor is a **local tool with no authentication**. Built in:

- Host and Origin checks on every request (blocks DNS-rebinding and cross-site POSTs).
- Request body size limit, per-connection socket timeout, `nosniff`/`DENY`/`no-referrer` headers.
- Project ids are validated and resolved inside `projects/` (no path traversal).
- Serial port and library names are validated before reaching `arduino-cli`.
- The terminal runs arbitrary shell commands: it needs the `X-EmbedCo-Terminal` header, only
  works with a loopback Host, is audit-logged, and is disabled if you bind to a
  non-loopback address. Do not put this server on an untrusted network.

## Tests

    python -m unittest discover -s tests -t .

`tests/golden/generator_cases.json` holds sketches produced by the original
single-file generator; the suite fails if the refactored generator output ever diverges.

## Files

- `blocks/categories/*.yaml`  category-specific block definitions and C++ templates
- `blocks/README.md`  block schema and instructions for adding a category
- `boards.yaml`  board profiles (ADC size, PWM pins, library swaps)
- `plugins/`  drop-in plugin `.json` files (created on first install)

## IDE layout update

The frontend now uses a VS Code-style bottom dock. The right sidebar is reserved for
selected-node properties; Code Preview and Serial Monitor live in the bottom dock.
The dock starts collapsed, expands when a tab is selected, and can be resized by
dragging its top edge. The active dock tab and open/collapsed state are remembered
in local storage.

Bootstrap Icons are loaded from jsDelivr, so the icon font requires an internet
connection. The Serial Monitor uses the browser Web Serial API (Chrome/Edge on
localhost). The Terminal tab explains the browser security boundary: an in-browser
web app cannot expose an arbitrary operating-system shell; use the terminal running
`server.py`. Build Logs and Problems are populated from actual compile/upload results.


## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=Nonsense0909688/EmbedCo&type=Date)](https://star-history.com/#Nonsense0909688/EmbedCo&Date)
