import os
import threading
import requests
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# ======================
# ENV VARIABLES
# ======================
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

if not TOKEN:
    raise ValueError("Missing TELEGRAM_BOT_TOKEN")

if not OPENROUTER_API_KEY:
    raise ValueError("Missing OPENROUTER_API_KEY")


# ======================
# TELEGRAM HANDLERS
# ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أهلاً! أنا Hermes Agent 🤖")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text

    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "openai/gpt-4o-mini",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant called Hermes."},
                {"role": "user", "content": user_text}
            ]
        }
    )

    if response.status_code == 200:
        reply = response.json()["choices"][0]["message"]["content"]
    else:
        reply = "AI error"

    await update.message.reply_text(reply)


# ======================
# SIMPLE WEB SERVER (Render keep-alive)
# ======================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")


def run_server():
    port = int(os.getenv("PORT", 8080))

    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()


# ======================
# MAIN APP
# ======================
def main():

    # keep-alive server
    threading.Thread(target=run_server, daemon=True).start()

    # telegram bot
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot started")

    app.run_polling()


if __name__ == "__main__":
    main()
