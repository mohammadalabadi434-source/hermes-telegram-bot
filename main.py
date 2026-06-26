import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)


TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    raise ValueError("Missing TELEGRAM_BOT_TOKEN")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "أهلاً! أنا Hermes Agent 🤖"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    await update.message.reply_text(
        f"وصلتني رسالتك: {text}"
    )


class HealthCheckHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")


def run_server():

    port = int(os.getenv("PORT", 8080))

    server = HTTPServer(
        ("0.0.0.0", port),
        HealthCheckHandler
    )

    server.serve_forever()


def main():

    threading.Thread(
        target=run_server,
        daemon=True
    ).start()


    app = Application.builder().token(TOKEN).build()


    app.add_handler(
        CommandHandler("start", start)
    )


    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )


    print("Bot started")


    app.run_polling()



if __name__ == "__main__":
    main()
