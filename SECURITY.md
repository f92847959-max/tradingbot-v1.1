# Security Policy

## Supported Use

This repository contains an automated trading system. Public source code does not make the system safe for live trading by itself. Keep live trading disabled until broker credentials, risk limits, database access, and API exposure have been reviewed in your own environment.

## Secret Handling

Never commit real values for:

- `CAPITAL_EMAIL`
- `CAPITAL_PASSWORD`
- `CAPITAL_API_KEY`
- `API_KEY`
- `POSTGRES_PASSWORD`
- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- model artifacts trained on private account data
- logs, exported trade history, broker responses, and local databases

Use `.env.example` as a template only. Store real values outside the repository, preferably under `C:\Users\<you>\secrets\ai-trading-gold\.env`, then point `GOLD_ENV_PATH` at that file.

## Before Publishing

1. Rotate any credentials that were ever stored in local files.
2. Confirm `git status --short` does not show `.env`, logs, databases, model artifacts, or generated data.
3. If a secret file was ever committed, rewrite Git history before making the repository public.
4. Start with `CAPITAL_DEMO=true` and `TRADING_MODE=semi_auto`.
5. Use a long random `API_KEY` and keep `API_AUTH_ENABLED=true`.
6. Keep APIs bound to `127.0.0.1` unless a reverse proxy, TLS, authentication, and network access controls are configured.

## Reporting

Do not open public issues containing credentials, tokens, broker account details, logs with account data, or live trade identifiers. Report security issues privately to the repository owner.
