# Codex Usage for Omarchy

A small Omarchy Quattro bar widget that shows remaining Codex weekly usage. Hover over it for session usage, weekly pace, reset time, and a seven-day burn chart. Right-click to refresh.

The widget asks the locally installed Codex app server for `account/rateLimits/read`. It does not read or print authentication tokens.

## Requirements

- Omarchy 4 with the Quattro shell
- Codex CLI, signed in with ChatGPT
- Python 3

No installer, background service, `sudo`, or additional package is required.

## Install

```sh
omarchy plugin add https://github.com/luinbytes/omarchy-codex-usage.git --enable
```

The widget is added to the right section of the bar. Move it if preferred:

```sh
omarchy bar move community.codex-usage --section left
```

## Use

- Hover: open the usage card and refresh its data
- Right-click: refresh immediately
- The widget refreshes automatically every three minutes

`[USG --]` means Codex is unavailable, not signed in, or did not return a usage window. Right-click after fixing the Codex login to retry.

## Configure

The helper recognizes these optional environment variables inherited by `omarchy-shell`:

| Variable | Default | Purpose |
| --- | --- | --- |
| `CODEX_BIN` | `codex` | Codex CLI executable |
| `CODEX_QUICKSHELL_TIMEOUT` | `12` | App-server timeout in seconds |

## Verify

```sh
python3 usage.py --self-test
python3 usage.py
omarchy plugin validate .
qmllint -I "$OMARCHY_PATH/shell" BarWidget.qml
```

The second command should print one JSON object using the current Codex login. It must not print a token.

## Update and remove

```sh
omarchy plugin update community.codex-usage
omarchy plugin remove community.codex-usage
```

## Privacy and security

Omarchy plugins run unsandboxed as the current user. This plugin starts `codex app-server --stdio` only while refreshing usage and requests the supported `account/rateLimits/read` method. Review the source before installing it.

Never add `~/.codex/auth.json`, `.env` files, logs, screenshots containing personal information, or local shell configuration to this repository.

## Attribution

The pace calculation and seven-slot burn chart are adapted from [CodexBar](https://github.com/steipete/CodexBar), Copyright © 2026 Peter Steinberger, under the MIT License.

## License

MIT. See [LICENSE](LICENSE).
