import os
import json
import threading
import asyncio
import aiohttp
import pytz
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler

load_dotenv()

TOKEN              = os.getenv("TELEGRAM_BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
TAVILY_API_KEY     = os.getenv("TAVILY_API_KEY", "")
TIMEZONE           = os.getenv("TIMEZONE", "Asia/Amman")

if not TOKEN or not OPENROUTER_API_KEY:
    raise ValueError("Missing TELEGRAM_BOT_TOKEN or OPENROUTER_API_KEY")

TASKS_FILE = "scheduled_tasks.json"

# ─────────────────────────── helpers ───────────────────────────

def load_tasks():
    if os.path.exists(TASKS_FILE):
        with open(TASKS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_tasks(tasks):
    with open(TASKS_FILE, "w", encoding="utf-8") as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)

def get_current_time_str():
    tz  = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    days   = ["الاثنين","الثلاثاء","الأربعاء","الخميس","الجمعة","السبت","الأحد"]
    months = ["يناير","فبراير","مارس","أبريل","مايو","يونيو",
               "يوليو","أغسطس","سبتمبر","أكتوبر","نوفمبر","ديسمبر"]
    return (
        f"🕐 الوقت: {now.strftime('%H:%M:%S')}\n"
        f"📅 {days[now.weekday()]}، {now.day} {months[now.month-1]} {now.year}\n"
        f"🌍 {TIMEZONE}"
    )

# ─────────────────────────── web search ────────────────────────

async def tavily_search(query: str) -> str:
    """بحث حقيقي عبر Tavily API"""
    if not TAVILY_API_KEY:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": TAVILY_API_KEY,
                    "query": query,
                    "search_depth": "advanced",
                    "max_results": 6,
                    "include_answer": True,
                },
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                parts = []
                if data.get("answer"):
                    parts.append(f"📌 {data['answer']}\n")
                for i, r in enumerate(data.get("results", [])[:5], 1):
                    parts.append(
                        f"[{i}] {r.get('title','')}\n"
                        f"{r.get('content','')[:250]}\n"
                        f"🔗 {r.get('url','')}"
                    )
                return "\n\n".join(parts) if parts else None
    except Exception as e:
        print(f"[Tavily Error] {e}")
        return None

# ─────────────────────────── AI core ───────────────────────────

SYSTEM_PROMPT = """أنت Hermes Agent، مساعد ذكي ومتقدم.

لديك القدرة على:
- البحث عن أي معلومات حديثة على الإنترنت
- معرفة الوقت والتاريخ الحالي بدقة
- الإجابة على الأسئلة العامة

قواعد مهمة:
- أجب دائماً باللغة العربية
- إذا أُعطيت نتائج بحث، استخدمها واستند إليها في إجابتك
- إذا أُعطيت الوقت الحالي، اذكره في إجابتك
- لا تقل أبداً أنك لا تستطيع الوصول للإنترنت
- كن مختصراً وواضحاً ومفيداً"""

async def ask_ai(user_message: str, search_results: str = None, current_time: str = None) -> str:
    """استدعاء OpenRouter مباشرة بدون LangChain"""
    
    # بناء الرسالة مع السياق
    context_parts = []
    if current_time:
        context_parts.append(f"[معلومة: الوقت الحالي هو]\n{current_time}")
    if search_results:
        context_parts.append(f"[نتائج البحث على الإنترنت]\n{search_results}")
    
    full_message = user_message
    if context_parts:
        full_message = "\n\n".join(context_parts) + f"\n\n[سؤال المستخدم]\n{user_message}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://hermes-bot.app",
                },
                json={
                    "model": "openai/gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user",   "content": full_message},
                    ],
                    "max_tokens": 1000,
                    "temperature": 0.5,
                },
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                data = await resp.json()
                return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"❌ خطأ في الاتصال بالذكاء الاصطناعي: {str(e)}"

def needs_search(text: str) -> bool:
    """تحديد إذا كانت الرسالة تحتاج بحثاً على الإنترنت"""
    keywords = [
        "أخبار","اخبار","خبر","حديث","جديد","اليوم","الآن","الان","ما هو","ماهو",
        "أحدث","احدث","تطورات","أسعار","اسعار","سعر","طقس","مباراة","نتيجة",
        "ابحث","بحث","تحقق","news","latest","current","price","weather","search",
        "رئيس","وزير","حكومة","انتخاب","تكنولوجيا","ذكاء اصطناعي","شركة","إطلاق",
    ]
    text_lower = text.lower()
    return any(k in text_lower for k in keywords)

def needs_time(text: str) -> bool:
    """تحديد إذا كانت الرسالة تسأل عن الوقت"""
    keywords = ["الوقت","الساعة","التاريخ","اليوم","كم الساعة","ما الوقت","متى"]
    return any(k in text for k in keywords)

# ─────────────────────────── handlers ──────────────────────────

async def process_message(user_text: str) -> str:
    """المعالج الذكي للرسائل — يقرر تلقائياً متى يبحث"""
    search_results = None
    current_time   = None

    if needs_time(user_text):
        current_time = get_current_time_str()

    if needs_search(user_text):
        search_results = await tavily_search(user_text)

    return await ask_ai(user_text, search_results, current_time)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🤖 *Hermes Agent* — مساعدك الذكي\n\n"
        "الأوامر:\n"
        "• `/time` — الوقت والتاريخ الآن\n"
        "• `/schedule [موضوع] [HH:MM]` — تقرير يومي تلقائي\n"
        "  مثال: `/schedule أخبار التكنولوجيا 08:00`\n"
        "• `/mytasks` — مهامك المجدولة\n"
        "• `/deltask [رقم]` — حذف مهمة\n\n"
        "أو اكتب أي سؤال 🚀"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def time_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(get_current_time_str())


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    await update.message.reply_text("⏳ جاري المعالجة...")
    reply = await process_message(user_text)
    await update.message.reply_text(reply)


# ─────────────────────── scheduler ─────────────────────────────

scheduled_tasks = load_tasks()
scheduler = AsyncIOScheduler(timezone=TIMEZONE)


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
    if chat_id not in scheduled_tasks:
        scheduled_tasks[chat_id] = []

    task_id = (max((t["id"] for t in scheduled_tasks[chat_id]), default=0)) + 1
    task = {"id": task_id, "topic": topic, "hour": hour, "minute": minute, "active": True}
    scheduled_tasks[chat_id].append(task)
    save_tasks(scheduled_tasks)

    _add_job(context.application, chat_id, task)

    await update.message.reply_text(
        f"✅ تم جدولة التقرير!\n\n"
        f"📌 الموضوع: *{topic}*\n"
        f"⏰ الوقت: {hour:02d}:{minute:02d} يومياً\n"
        f"🔢 رقم المهمة: {task_id}",
        parse_mode="Markdown"
    )


async def mytasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    active  = [t for t in scheduled_tasks.get(chat_id, []) if t["active"]]

    if not active:
        await update.message.reply_text("📭 لا توجد مهام مجدولة.\nاستخدم /schedule لإضافة مهمة.")
        return

    lines = ["📋 *مهامك المجدولة:*\n"]
    for t in active:
        lines.append(f"🔢 {t['id']}: *{t['topic']}* — ⏰ {t['hour']:02d}:{t['minute']:02d}")
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
    found = False
    for t in scheduled_tasks.get(chat_id, []):
        if t["id"] == task_id and t["active"]:
            t["active"] = False
            found = True
            job_id = f"{chat_id}_{task_id}"
            if scheduler.get_job(job_id):
                scheduler.remove_job(job_id)
            break

    if found:
        save_tasks(scheduled_tasks)
        await update.message.reply_text(f"✅ تم حذف المهمة رقم {task_id}")
    else:
        await update.message.reply_text("❌ لم يتم إيجاد المهمة")


def _add_job(app, chat_id: str, task: dict):
    job_id = f"{chat_id}_{task['id']}"

    async def send_report():
        topic = task["topic"]
        await app.bot.send_message(
            chat_id=int(chat_id),
            text=f"⏰ *تقريرك اليومي: {topic}*\n\n🔍 جاري البحث...",
            parse_mode="Markdown"
        )
        query  = f"أحدث أخبار وتطورات {topic} اليوم"
        search = await tavily_search(query)
        reply  = await ask_ai(query, search_results=search, current_time=get_current_time_str())
        await app.bot.send_message(chat_id=int(chat_id), text=reply)

    scheduler.add_job(
        send_report,
        trigger="cron",
        hour=task["hour"],
        minute=task["minute"],
        id=job_id,
        replace_existing=True,
    )


# ─────────────────────── health server ─────────────────────────

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Hermes is running")
    def log_message(self, *a): pass

def run_server():
    port = int(os.getenv("PORT", 8080))
    HTTPServer(("0.0.0.0", port), HealthHandler).serve_forever()


# ─────────────────────────── main ──────────────────────────────

def main():
    threading.Thread(target=run_server, daemon=True).start()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start",    start))
    app.add_handler(CommandHandler("time",     time_command))
    app.add_handler(CommandHandler("schedule", schedule_command))
    app.add_handler(CommandHandler("mytasks",  mytasks_command))
    app.add_handler(CommandHandler("deltask",  deltask_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # استعادة المهام المحفوظة
    for cid, tasks in scheduled_tasks.items():
        for t in tasks:
            if t["active"]:
                _add_job(app, cid, t)

    scheduler.start()
    print("✅ Hermes Agent started!")
    app.run_polling()


if __name__ == "__main__":
    main()
