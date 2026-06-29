"""
Hermes Agent — main.py
ميزات:
  ✅ ذاكرة دائمة (SQLite) — يتذكر كل شيء حتى بعد إعادة التشغيل
  ✅ سجل محادثات شخصي قابل للاسترجاع
  ✅ جدولة يومية بأوامر بسيطة
  ✅ بحث حقيقي عبر Tavily
  ✅ تاريخ ميلادي + هجري دقيق
"""

import os, json, threading, asyncio, aiohttp, pytz
from datetime import datetime, date
from http.server import BaseHTTPRequestHandler, HTTPServer

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from hijridate import Gregorian as HijriGregorian

import database as db

load_dotenv()

TOKEN              = os.getenv("TELEGRAM_BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
TAVILY_API_KEY     = os.getenv("TAVILY_API_KEY", "")
TIMEZONE           = os.getenv("TIMEZONE", "Asia/Amman")

if not TOKEN or not OPENROUTER_API_KEY:
    raise ValueError("Missing TELEGRAM_BOT_TOKEN or OPENROUTER_API_KEY")

HIJRI_MONTHS_AR = [
    "محرم","صفر","ربيع الأول","ربيع الآخر",
    "جمادى الأولى","جمادى الآخرة","رجب","شعبان",
    "رمضان","شوال","ذو القعدة","ذو الحجة"
]

scheduler = AsyncIOScheduler(timezone=TIMEZONE)

# ══════════════════════════════════════════
#  الوقت والتاريخ
# ══════════════════════════════════════════
def get_current_time_str() -> str:
    tz  = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    days   = ["الاثنين","الثلاثاء","الأربعاء","الخميس","الجمعة","السبت","الأحد"]
    months = ["يناير","فبراير","مارس","أبريل","مايو","يونيو",
               "يوليو","أغسطس","سبتمبر","أكتوبر","نوفمبر","ديسمبر"]
    try:
        h = HijriGregorian(now.year, now.month, now.day).to_hijri()
        hijri = f"{h.day} {HIJRI_MONTHS_AR[h.month-1]} {h.year} هـ"
    except Exception:
        hijri = ""
    return (
        f"🕐 {now.strftime('%H:%M:%S')}\n"
        f"📅 {days[now.weekday()]}، {now.day} {months[now.month-1]} {now.year} م\n"
        f"🌙 {hijri}\n"
        f"🌍 {TIMEZONE}"
    )

# ══════════════════════════════════════════
#  البحث
# ══════════════════════════════════════════
async def tavily_search(query: str) -> str | None:
    if not TAVILY_API_KEY:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.tavily.com/search",
                json={"api_key": TAVILY_API_KEY, "query": query,
                      "search_depth": "advanced", "max_results": 5, "include_answer": True},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                parts = []
                if data.get("answer"):
                    parts.append(f"📌 {data['answer']}\n")
                for i, r in enumerate(data.get("results", [])[:5], 1):
                    parts.append(f"[{i}] {r.get('title','')}\n{r.get('content','')[:250]}\n🔗 {r.get('url','')}")
                return "\n\n".join(parts) if parts else None
    except Exception as e:
        print(f"[Tavily] {e}")
        return None

def needs_search(text: str) -> bool:
    kw = ["أخبار","اخبار","خبر","حديث","جديد","اليوم","الآن","الان","أحدث","احدث",
          "تطورات","أسعار","اسعار","سعر","طقس","مباراة","نتيجة","ابحث","بحث",
          "تكنولوجيا","ذكاء اصطناعي","شركة","إطلاق","رئيس","وزير","حكومة",
          "news","latest","current","price","weather","search"]
    return any(k in text.lower() for k in kw)

def needs_time(text: str) -> bool:
    return any(k in text for k in ["الوقت","الساعة","التاريخ","اليوم","كم الساعة","ما الوقت","متى"])

# ══════════════════════════════════════════
#  الذكاء الاصطناعي مع الذاكرة
# ══════════════════════════════════════════
SYSTEM_PROMPT = """أنت Hermes Agent، مساعد ذكي ومتقدم.

لديك ذاكرة كاملة بالمحادثات السابقة مع المستخدم — استخدمها دائماً.
إذا ذكر المستخدم اسمه أو تفضيلاته أو أي معلومة شخصية، تذكّرها واستخدمها في ردودك.

قواعد:
- أجب دائماً باللغة العربية
- إذا أُعطيت نتائج بحث، استند إليها
- إذا أُعطيت الوقت الحالي، اذكره
- كن مختصراً وواضحاً ومفيداً
- إذا عرفت اسم المستخدم، خاطبه به"""

async def ask_ai(chat_id: str, user_message: str,
                 search_results: str = None,
                 current_time: str = None) -> str:
    # بناء السياق
    context_parts = []
    if current_time:
        context_parts.append(f"[الوقت الحالي]\n{current_time}")
    if search_results:
        context_parts.append(f"[نتائج البحث]\n{search_results}")

    full_user_msg = user_message
    if context_parts:
        full_user_msg = "\n\n".join(context_parts) + f"\n\n[رسالة المستخدم]\n{user_message}"

    # جلب تاريخ المحادثة من قاعدة البيانات
    history = await db.get_history(chat_id, limit=20)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += history
    messages.append({"role": "user", "content": full_user_msg})

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}",
                         "Content-Type": "application/json"},
                json={"model": "openai/gpt-4o-mini", "messages": messages,
                      "max_tokens": 1000, "temperature": 0.5},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                data = await resp.json()
                return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"❌ خطأ: {str(e)}"

# ══════════════════════════════════════════
#  معالج الرسائل الرئيسي
# ══════════════════════════════════════════
async def process_and_respond(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user     = update.effective_user
    chat_id  = str(update.effective_chat.id)
    user_msg = update.message.text

    # حفظ/تحديث المستخدم
    await db.upsert_user(chat_id, user.username, user.first_name)

    # حفظ رسالة المستخدم في السجل
    await db.save_message(chat_id, "user", user_msg)

    await update.message.reply_text("⏳ جاري المعالجة...")

    # هل نحتاج وقت / بحث؟
    current_time   = get_current_time_str() if needs_time(user_msg) else None
    search_results = await tavily_search(user_msg) if needs_search(user_msg) else None

    reply = await ask_ai(chat_id, user_msg, search_results, current_time)

    # حفظ رد البوت في السجل
    await db.save_message(chat_id, "assistant", reply)

    await update.message.reply_text(reply)

# ══════════════════════════════════════════
#  الأوامر
# ══════════════════════════════════════════
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    chat_id = str(update.effective_chat.id)
    await db.upsert_user(chat_id, user.username, user.first_name)

    name = user.first_name or "صديقي"
    text = (
        f"👋 أهلاً *{name}*! أنا *Hermes Agent*\n\n"
        "🧠 أتذكر كل محادثاتنا السابقة\n\n"
        "*الأوامر:*\n"
        "• `/time` — الوقت والتاريخ الآن\n"
        "• `/history` — سجل محادثاتك معي\n"
        "• `/clear` — مسح سجل المحادثات\n"
        "• `/me` — معلوماتك المحفوظة\n\n"
        "⏰ *الجدولة اليومية:*\n"
        "• `/schedule [موضوع] [HH:MM]`\n"
        "  مثال: `/schedule أخبار التكنولوجيا 08:00`\n"
        "• `/mytasks` — مهامك المجدولة\n"
        "• `/deltask [رقم]` — حذف مهمة\n\n"
        "اكتب أي سؤال وسأجيبك! 🚀"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def time_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(get_current_time_str())


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    text = await db.get_history_text(chat_id, limit=30)

    # تقسيم النص إذا كان طويلاً (حد تيليغرام 4096 حرف)
    if len(text) <= 4000:
        await update.message.reply_text(f"📜 *سجل محادثاتك:*\n\n{text}", parse_mode="Markdown")
    else:
        # أرسله على دفعات
        chunks = [text[i:i+3800] for i in range(0, len(text), 3800)]
        for i, chunk in enumerate(chunks):
            header = "📜 *سجل محادثاتك:*\n\n" if i == 0 else ""
            await update.message.reply_text(f"{header}{chunk}", parse_mode="Markdown")


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    await db.clear_history(chat_id)
    await update.message.reply_text("🗑️ تم مسح سجل المحادثات.")


async def me_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    user    = await db.get_user(chat_id)
    prefs   = await db.get_preferences(chat_id)

    if not user:
        await update.message.reply_text("لا توجد معلومات محفوظة بعد.")
        return

    tasks  = await db.get_tasks(chat_id)
    n_msgs = len(await db.get_history(chat_id, limit=1000))

    lines = [
        f"👤 *معلوماتك المحفوظة*\n",
        f"الاسم: {user.get('first_name','—')}",
        f"المعرف: @{user.get('username','—')}",
        f"عضو منذ: {(user.get('created_at','')[:10])}",
        f"إجمالي الرسائل: {n_msgs}",
        f"المهام المجدولة: {len(tasks)}",
    ]
    if prefs:
        lines.append(f"\n⚙️ *التفضيلات:*")
        for k, v in prefs.items():
            lines.append(f"  • {k}: {v}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ══════════════════════════════════════════
#  الجدولة
# ══════════════════════════════════════════
async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "❌ الاستخدام:\n`/schedule [الموضوع] [HH:MM]`\n\n"
            "مثال:\n`/schedule أخبار التكنولوجيا 08:00`",
            parse_mode="Markdown"
        )
        return

    time_str = args[-1]
    topic    = " ".join(args[:-1])

    try:
        hour, minute = map(int, time_str.split(":"))
        assert 0 <= hour <= 23 and 0 <= minute <= 59
    except:
        await update.message.reply_text("❌ الوقت غير صحيح. استخدم HH:MM مثل 08:00")
        return

    chat_id = str(update.effective_chat.id)
    task_id = await db.add_task(chat_id, topic, hour, minute)
    _register_job(context.application, chat_id, task_id, topic, hour, minute)

    await update.message.reply_text(
        f"✅ *تم جدولة التقرير!*\n\n"
        f"📌 الموضوع: {topic}\n"
        f"⏰ الوقت: {hour:02d}:{minute:02d} يومياً\n"
        f"🔢 رقم المهمة: {task_id}",
        parse_mode="Markdown"
    )


async def mytasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    tasks   = await db.get_tasks(chat_id)

    if not tasks:
        await update.message.reply_text("📭 لا توجد مهام مجدولة.\nاستخدم /schedule لإضافة مهمة.")
        return

    lines = ["📋 *مهامك المجدولة:*\n"]
    for t in tasks:
        lines.append(f"🔢 {t['id']}: *{t['topic']}* — ⏰ {t['hour']:02d}:{t['minute']:02d} يومياً")
    lines.append("\nلحذف مهمة: `/deltask [رقم]`")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def deltask_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ الاستخدام: `/deltask [رقم]`", parse_mode="Markdown")
        return
    try:
        task_id = int(context.args[0])
    except:
        await update.message.reply_text("❌ رقم غير صحيح")
        return

    chat_id = str(update.effective_chat.id)
    deleted = await db.delete_task(task_id, chat_id)

    if deleted:
        job_id = f"task_{task_id}"
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
        await update.message.reply_text(f"✅ تم حذف المهمة رقم {task_id}")
    else:
        await update.message.reply_text("❌ لم يتم إيجاد المهمة")


# ══════════════════════════════════════════
#  تسجيل وظائف الـ Scheduler
# ══════════════════════════════════════════
def _register_job(app, chat_id: str, task_id: int, topic: str, hour: int, minute: int):
    job_id = f"task_{task_id}"

    async def send_report():
        await app.bot.send_message(
            chat_id=int(chat_id),
            text=f"⏰ *تقريرك اليومي: {topic}*\n🔍 جاري البحث...",
            parse_mode="Markdown"
        )
        search = await tavily_search(f"أحدث أخبار وتطورات {topic} اليوم")
        reply  = await ask_ai(chat_id,
                              f"قدم تقريراً شاملاً عن: {topic}",
                              search_results=search,
                              current_time=get_current_time_str())
        # حفظ التقرير في السجل
        await db.save_message(chat_id, "assistant", f"[تقرير يومي: {topic}]\n{reply}")
        await app.bot.send_message(chat_id=int(chat_id), text=reply)

    scheduler.add_job(send_report, trigger="cron",
                      hour=hour, minute=minute,
                      id=job_id, replace_existing=True)


# ══════════════════════════════════════════
#  خادم الصحة
# ══════════════════════════════════════════
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Hermes is running")
    def log_message(self, *a): pass

def run_server():
    HTTPServer(("0.0.0.0", int(os.getenv("PORT", 8080))), HealthHandler).serve_forever()

# ══════════════════════════════════════════
#  main
# ══════════════════════════════════════════
async def post_init(app: Application):
    """يُشغَّل بعد بدء التطبيق — تهيئة DB وتحميل المهام"""
    await db.init_db()
    tasks = await db.get_all_active_tasks()
    for t in tasks:
        _register_job(app, str(t["chat_id"]), t["id"],
                      t["topic"], t["hour"], t["minute"])
    print(f"✅ Loaded {len(tasks)} scheduled task(s) from DB")


def main():
    threading.Thread(target=run_server, daemon=True).start()

    app = (Application.builder()
           .token(TOKEN)
           .post_init(post_init)
           .build())

    app.add_handler(CommandHandler("start",    start))
    app.add_handler(CommandHandler("time",     time_command))
    app.add_handler(CommandHandler("history",  history_command))
    app.add_handler(CommandHandler("clear",    clear_command))
    app.add_handler(CommandHandler("me",       me_command))
    app.add_handler(CommandHandler("schedule", schedule_command))
    app.add_handler(CommandHandler("mytasks",  mytasks_command))
    app.add_handler(CommandHandler("deltask",  deltask_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_and_respond))

    scheduler.start()
    print("✅ Hermes Agent started!")
    app.run_polling()


if __name__ == "__main__":
    main()
