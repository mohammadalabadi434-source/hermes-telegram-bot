import os
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading

# جلب التوكن من متغيرات البيئة
TOKEN = os.getenv(8737811338:AAEyFElH3znciEzHnpBmyOeFOA9RLd4CP7Q)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أهلاً بك! أنا مساعدك الذكي Hermes Agent. كيف يمكنني مساعدتك اليوم؟")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    reply = f"لقد استلمت رسالتك: {user_text} \n(جاري ربط الـ Agent حالياً...)"
    await update.message.reply_text(reply)

# سيرفر وهمي لإبقاء Render سعيداً
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

def run_health_check():
    server = HTTPServer(('0.0.0.0', int(os.getenv("PORT", 8080))), HealthCheckHandler)
    server.serve_forever()

async def main():
    # تشغيل السيرفر الوهمي في الخلفية
    threading.Thread(target=run_health_check, daemon=True).start()

    # بناء وتشغيل البوت بشكل متوافق مع خوادم الويب
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("البوت يبدأ الآن...")
    
    # هذه الطريقة تمنع انهيار السيرفر status 1
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    
    # إبقاء البوت يعمل دون توقف
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    # تشغيل المجلد الرئيسي بأمان
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
