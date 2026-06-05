"""
Entry point cho Telegram Bot.
Chạy: python -m server.bot
"""
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

from server.bot.bot import run_bot

if __name__ == "__main__":
    run_bot()
