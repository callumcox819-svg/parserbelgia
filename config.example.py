# Copy to config.py for local runs only.
# On Railway use Variables (config.py is NOT deployed -- see .gitignore).

BOT_TOKEN = "your_token_from_botfather"

# Ваш Telegram user id (узнать: @userinfobot), можно несколько через запятую
ADMIN_IDS = "123456789"

DEFAULT_LIMIT = 50

PROXY = "socks5://user:password@host:1080"
# PROXY = "http://user:password@host:10789"
# PROXY = None

# Ricardo: несколько CH-прокси (по одному на строку в Railway Variables)
# PROXIES = """socks5://user:pass@ch1:1080
# socks5://user:pass@ch2:1080"""
