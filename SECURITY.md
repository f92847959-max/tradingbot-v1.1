# Security Policy

## Disclaimer

This repository contains an experimental, automated trading system. The public source code is provided **as-is, for educational and research purposes**. It is **not** a production-ready trading product and does **not** constitute financial advice. Running it against a live brokerage account can lead to financial losses. You are solely responsible for any deployment, configuration, and trading decisions.

## Reporting a Vulnerability

Please **do not** open a public GitHub issue for security problems.

Use GitHub's private **Security Advisories** to report a vulnerability:

- Go to the [Security tab](https://github.com/f92847959-max/tradingbot-v1.1/security) of this repository
- Click **Report a vulnerability**
- Fill in the form with as much detail as possible

What to include in your report:

- A clear description of the issue and the affected component (file/module)
- Steps to reproduce (proof-of-concept welcome)
- Potential impact and any suggested mitigation

Please give the maintainer a reasonable amount of time to investigate and patch before any public disclosure.

## Supported Versions

Only the latest commit on the `master` branch is actively maintained. Older commits, forks, and tagged releases are provided without security guarantees.

| Version       | Supported          |
| ------------- | ------------------ |
| `master` HEAD | :white_check_mark: |
| Older commits | :x:                |

## In Scope

Examples of issues that are in scope:

- Hardcoded or leaked credentials in the source tree
- Authentication or authorization bypass in the API (`api/`, `goldbot-control-app/backend/`)
- Insecure handling of broker credentials, tokens, or API keys
- SQL/command/template injection, SSRF, deserialization issues
- Webhook signature verification weaknesses (`api/routers/webhook.py`)
- Insecure default configuration that exposes the system to the public internet
- Vulnerabilities in dependency pinning or supply-chain risks (`requirements.lock`, `pyproject.toml`)

## Out of Scope

Out-of-scope reports will typically be closed without action:

- Vulnerabilities that require pre-existing access to the local machine where the bot runs
- Issues that depend on disabled defaults (e.g., running with `API_AUTH_ENABLED=false` on a public IP)
- Trading-strategy weaknesses, financial losses, or model performance complaints
- Best-practice suggestions without a concrete attack scenario
- Reports against archived or third-party code under `mirofish_seeds/` or external dependencies (please report those upstream)

## Secret Handling (for Forks and Contributors)

If you fork, clone, or contribute to this repository, **never commit real values** for any of the following:

- `CAPITAL_EMAIL`, `CAPITAL_PASSWORD`, `CAPITAL_API_KEY`
- `API_KEY`
- `POSTGRES_PASSWORD`
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`
- Model artifacts trained on private account data
- Logs, exported trade history, broker responses, or local databases

Use `.env.example` as a template only. Store real values **outside the repository**, for example under `C:\Users\<you>\secrets\ai-trading-gold\.env`, and point `GOLD_ENV_PATH` at that file.

If you suspect a secret was ever committed (even in an old commit), rotate it immediately and request a history rewrite via a private security advisory.

## Hardening Checklist for Self-Hosting

If you decide to run this code yourself, at minimum:

1. Start with `CAPITAL_DEMO=true` and `TRADING_MODE=semi_auto`
2. Use a long, random `API_KEY` and keep `API_AUTH_ENABLED=true`
3. Bind APIs to `127.0.0.1` unless a reverse proxy, TLS, authentication, and network access controls are configured
4. Run the database with a dedicated, least-privilege user
5. Keep `requirements.lock` pinned and rebuild the environment for reproducible installs
6. Review broker rate limits and your own risk caps (`MAX_RISK_PER_TRADE_PCT`, `MAX_DAILY_LOSS_PCT`, `MAX_OPEN_POSITIONS`)
7. Monitor logs and alerts; treat unexpected order flow as a security incident

## Reporting Etiquette

- Do **not** include real credentials, tokens, broker account numbers, or live trade identifiers in any report
- Do **not** test against accounts or systems you do not own
- Do **not** perform automated scanning that would generate excessive load on third-party services (broker APIs, etc.)
