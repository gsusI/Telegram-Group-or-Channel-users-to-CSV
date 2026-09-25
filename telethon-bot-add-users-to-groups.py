"""Compatibility entry point for Telegram CSV tool."""

from telegram_csv import main

# Existing setup remains supported: edit these three values, or set the
# TELEGRAM_API_ID, TELEGRAM_API_HASH, and TELEGRAM_PHONE environment variables.
api_id = 000000
api_hash = "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
phone = "+34000000000"


if __name__ == "__main__":
    raise SystemExit(main(credentials=(api_id, api_hash, phone)))
