# Codex and Grok usage for Omarchy

A Quickshell bar widget for the current Omarchy Shell. The bar shows Codex and Cursor/Grok usage remaining, each prefixed with its app icon. Hover for Codex session usage, weekly pace, reset time, and a burn chart, with Grok usage below.

The Grok section reports Cursor's shared plan allowance and billing-cycle reset. It is not a Grok-only quota. Each provider can fail independently.

## Requirements

- Omarchy Shell with plugin support
- Python 3.11 or newer
- Codex CLI signed in with ChatGPT
- Cursor signed in locally for the Grok section

## Install

```sh
omarchy plugin add https://github.com/luinbytes/omarchy-codex-usage.git --enable
```

The plugin ID remains `community.codex-usage`, so existing installations keep their widget identity. Its entry point is `Panel.qml`; `usage.py` fetches usage data. This replaces the older Quattro implementation.

## Install from a downloaded folder

Copy the complete folder, including `assets/`, to `~/.config/omarchy/plugins/community.codex-usage/`. Then run:

```sh
omarchy shell shell rescanPlugins
omarchy plugin enable community.codex-usage --section right
```

If replacing an already loaded copy, restart Omarchy Shell to clear cached QML:

```sh
omarchy restart shell
```

The widget requires the current Omarchy Shell APIs (`qs.Ui` and `qs.Commons`). Older Quattro versions are not supported. Cursor is optional; its section shows unavailable when Cursor is absent or signed out. The widget reads the standard Cursor configuration beneath `XDG_CONFIG_HOME`, or `~/.config` when that variable is unset.

## Use

- Hover to open the card and refresh.
- Right-click to refresh immediately.
- Left-click to open Codex in the browser.
- Usage refreshes every three minutes.

`--` beside an app icon means its usage is unavailable. The other provider continues to work.

## Configuration

The helper inherits these environment variables from the shell:

| Variable | Default | Purpose |
| --- | --- | --- |
| `CODEX_BIN` | auto | Codex CLI executable; checks PATH, then the Linux desktop app bundle |
| `CODEX_QUICKSHELL_TIMEOUT` | `12` | Codex request timeout in seconds |
| `GROK_USAGE_TIMEOUT` | `12` | Cursor request timeout in seconds |

## Verify

```sh
python3 usage.py --self-test
python3 usage.py --quickshell
omarchy plugin validate .
```

The helper prints one JSON object with Codex fields at the top level and Cursor/Grok fields under `grok`.

## Privacy

Codex usage comes from the local app server through `account/rateLimits/read`. The Cursor request uses the login token from Cursor's local settings database. Credentials are never included in the output. Provider failures log only the provider name and exception type, not raw server messages or local paths.

## Attribution

The pace calculation and seven-slot burn chart are adapted from [CodexBar](https://github.com/steipete/CodexBar), Copyright © 2026 Peter Steinberger, under the MIT License.

App icons are from [Lobe Icons](https://github.com/lobehub/lobe-icons), under the [MIT License](assets/LICENSE.lobe-icons).

MIT. See [LICENSE](LICENSE).
