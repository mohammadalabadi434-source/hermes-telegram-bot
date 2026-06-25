import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading

# جلب التوكن من متغيرات البيئة (Render Environment Variables)
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أهلاً بك! أنا مساعدك الذكي Hermes Agent. كيف يمكنني مساعدتك اليوم؟")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    # هنا يمكنك إرسال user_text إلى الـ API الخاص بـ Hermes وجلب الرد
    # سنضع رداً تلقائياً مؤقتاً للتأكد من عمل البوت
    reply = f"لقد استلمت رسالتك: {user_text} \n(جاري ربط الـ Agent حالياً...)"
    await update.message.reply_text(reply)

# سيرفر وهمي صغير فقط لإبقاء Render سعيداً ولا يغلق الخدمة
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

def run_health_check():
    server = HTTPServer(('0.0.0.0', int(os.getenv("PORT", 8080))), HealthCheckHandler)
    server.serve_forever()

def main():
    # تشغيل السيرفر الوهمي في خلفية الكود
    threading.Thread(target=run_health_check, daemon=True).start()

    # تشغيل البوت بنظام Polling
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("البوت يعمل الآن...")
    app.run_polling()

if __name__ == "__main__":
    main()
