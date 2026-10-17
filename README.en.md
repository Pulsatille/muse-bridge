# muse-bridge

Let local AI agents (Hermes Agent / any MCP client) **command the cloud Muse** (muse.ai web AI) through a browser DOM bridge, and retrieve real replies. Multi-account, proxy spreading, portable auth packages.

> A public-good open-source project. This project does NOT use the Muse official API — it drives **your own browser login session** (Playwright DOM), and is **only for operating accounts you are authorized to use**. Please read `docs/DISCLAIMER.md` before use.

## Who is it for? How to use it?

**Target agents**: any local AI agent that supports **MCP (Model Context Protocol)**, most typically:

- **Hermes Agent** (v0.13.0+, the native target of this project)
- Any MCP client: Claude Code / Codex / Cursor / OpenClaw / etc.

**Usage in one sentence**: give it a logged-in Muse account, then tell it "use Muse to do XX". It will automatically:

1. Call `muse_send` to dispatch your task into the cloud Muse web composer
2. Call `muse_poll` to poll back Muse's real reply
3. Use `muse_status` / `muse_accounts` to check account health, switch accounts, and spread quota

**Full local Hermes setup** (see `docs/INSTALL.md` for details):

```bash
# 1) Install dependencies
pip install -r requirements.txt
python -m playwright install chromium

# 2) Prepare an account (login state)
python -m muse_bridge.accounts import muse-default --auth /path/to/auth.json
#    or first-time login: python -m muse_bridge.cli login

# 3) Register as a Hermes MCP server (edit ~/.hermes/config.yaml)
#    mcp_servers:
#      muse-bridge:
#        command: python
#        args: ["-X", "utf8", "-m", "muse_bridge.mcp_server"]
#        cwd: "/path/to/muse-bridge/src"

# 4) Verify
hermes mcp test muse-bridge   # should list 5 tools
```

**Hermes skill file**: the repo ships `skills/muse-bridge/SKILL.md`. Install it and Hermes will learn to drive these tools by itself:

```bash
mkdir -p ~/.hermes/skills/muse-bridge
copy skills\muse-bridge\SKILL.md ~\.hermes\skills\muse-bridge\SKILL.md
```

## Features

- **MCP stdio server**: 5 tools `muse_send / muse_poll / muse_status / muse_accounts / muse_export`, zero third-party deps
- **Browser DOM bridge**: Playwright persistent context + real login state (`storage_state`), headless composer injection, input validation, unique marker proving delivery
- **Multi-account**: `registry.json` manages profiles + proxies + portable auth packages centrally; spread quota across accounts
- **Portable auth package**: copy `auth.json` (Playwright storage_state) to another machine and `import` to reproduce the login state

## Quick Start

```powershell
# 1) Install dependencies
pip install -r requirements.txt
python -m playwright install chromium

# 2) Log in a Muse account once (generates accounts/muse-default/auth.json)
python -m muse_bridge.cli login

# 3) Start the MCP server (connect any MCP client)
python -m muse_bridge.mcp_server
```

Or use the CLI directly (without MCP):

```powershell
python -m muse_bridge.cli "help me check today's news"
python -m muse_bridge.worker status
python -m muse_bridge.accounts list
```

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `MUSE_HOME` | Data root (default `~/.hermes-muse-bridge`): accounts/registry.json, profiles, auth.json |
| `MUSE_PY` | Python interpreter with playwright (auto-detected) |
| `MUSE_CHROME` | Chromium executable path (auto-detected from Playwright cache) |
| `MUSE_DEFAULT_ACCOUNT` | Default account id (default from registry.default) |
| `MUSE_ACCOUNT` | Worker process-level default account id |

## Directory Layout

```
muse-bridge/
├── src/muse_bridge/       # Core code
│   ├── mcp_server.py      # MCP stdio server (5 tools)
│   ├── worker.py          # Playwright DOM worker (send/poll/status/accounts)
│   ├── accounts.py        # Multi-account registry CLI
│   └── cli.py             # Standalone CLI dispatcher
├── docs/                  # Install / Architecture / Disclaimer
├── skills/                # Hermes skill (SKILL.md)
├── tests/                 # Core tests
├── run_me.py              # One-click assemble / test / package
├── pyproject.toml
└── requirements.txt
```

## Testing

```powershell
python -m muse_bridge.accounts list   # should print empty list even with no accounts
python run_me.py --check                # compile + MCP handshake self-check
python tests/test_core.py              # 3/3 core tests
```

## Roadmap

> **Important note**: the following are **future plans with inherent uncertainty**. Whether and how they are implemented depends on the author's actual practice and time. **If anyone in the community implements any of these ahead of time, you are welcome to open a PR / fork and merge it directly** (first-come-first-served for the same goal). The author will not refuse on the grounds of "this is my plan".

- **Account Isolation**: fully isolate different Muse accounts' browser profiles, auth packages and data directories so they never read/write each other — preventing one bad account from polluting others.
- **Geo Partitioning**: assign different proxy egresses and browser fingerprints (locale, timezone, UA) per account's region, reducing the chance of multi-account correlation and thus **preventing bans**.
- Others TBD: auto re-login on session expiry, quota usage stats, Muse reply quality scoring, multi-machine sync.

## Author's Words (Project Philosophy)

> I believe that the best outcome for a big company's product is not about grabbing more users than rivals, but about who can cooperate better to serve our daily lives. That is why I strongly urge vendors to open up some interfaces when building personal AI agents, so local agents can interoperate with each other — making technology serve life, not money. The reason I chose Hermes is simply that it runs on my computer — lighter and smoother than OpenClaw. This project is an attempt to turn that "open, interoperable, technology-for-humans" philosophy into reality: since Muse does not open its cloud interface, we open it through a browser DOM bridge.

More: `docs/INSTALL.md` (server deployment), `docs/ARCHITECTURE.md` (interfaces/data flow), `docs/DISCLAIMER.md` (disclaimer). The author's original words, corrected Chinese version and English translation: `AUTHOR_NOTES.md`.