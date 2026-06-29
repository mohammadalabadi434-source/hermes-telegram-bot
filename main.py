import os
import threading
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime
import pytz

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from langchain_openai import ChatOpenAI
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate
from langchain.memory import ConversationBufferWindowMemory

from tools import web_search, calculator, get_current_time

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
TIMEZONE = os.getenv("TIMEZONE", "Asia/Amman")  # منطقتك الزمنية

if not TOKEN or not OPENROUTER_API_KEY:
    raise ValueError("Missing environment variables!")

# ===== إعداد الذكاء الاصطناعي =====
llm = ChatOpenAI(
    model="openai/gpt-4o-mini",
    openai_api_key=OPENROUTER_API_KEY,
    openai_api_base="https://openrouter.ai/api/v1",
    temperature=0.5
)

tools = [web_search, calculator, get_current_time]
memory = ConversationBufferWindowMemory(k=10, return_messages=True, memory_key="chat_history")

prompt = ChatPromptTemplate.from_messages([
    ("system", """أنت Hermes Agent، مساعد ذكي متقدم.

أدواتك المتاحة:
- web_search: ابحث عن أي معلومات حديثة على الإنترنت
- calculator: احسب أي عملية رياضية
- get_current_time: احصل على الوقت والتاريخ الحالي بدقة

قواعد مهمة:
- إذا سأل المستخدم عن الوقت أو التاريخ → استخدم get_current_time فوراً
- إذا سأل عن أخبار أو معلومات حديثة → استخدم web_search فوراً
- لا تقل أبداً "لا أعرف" أو "ليس لدي معلومات" — استخدم الأدوات
- أجب دائماً باللغة العربية
- كن دقيقاً ومختصراً"""),
    ("placeholder", "{chat_history}"),
    ("human", "{input}"),
    ("placeholder", "{agent_scratchpad}"),
])

agent = create_tool_calling_agent(llm, tools, prompt)
agent_executor = AgentExecutor(agent=agent, tools=tools, memory=memory, verbose=True)

# ===== تخزين المهام المجدولة =====
# الصيغة: { chat_id: [ {id, topic, hour, minute, active}, ... ] }
TASKS_FILE = "scheduled_tasks.json"

def load_tasks():
    if os.path.exists(TASKS_FILE):
        with open(TASKS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_tasks(tasks):
    with open(TASKS_FILE, "w", encoding="utf-8") as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)

scheduled_tasks = load_tasks()

# ===== Scheduler =====
scheduler = AsyncIOScheduler(timezone=TIMEZONE)

# ===== أوامر البوت =====

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🤖 *Hermes Agent* — مساعدك الذكي\n\n"
        "الأوامر المتاحة:\n"
        "• `/start` — عرض هذه الرسالة\n"
        "• `/time` — الوقت والتاريخ الآن\n"
        "• `/schedule [الموضوع] [HH:MM]` — جدولة تقرير يومي\n"
        "  مثال: `/schedule أخبار التكنولوجيا 08:00`\n"
        "• `/mytasks` — عرض مهامك المجدولة\n"
        "• `/deltask [رقم_المهمة]` — حذف مهمة\n\n"
        "أو اكتب أي سؤال وسأجيبك! 🚀"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def time_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = get_current_time.invoke({"timezone": TIMEZONE})
    await update.message.reply_text(result)


async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    الاستخدام: /schedule أخبار التكنولوجيا 08:00
    """
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "❌ الاستخدام الصحيح:\n`/schedule [الموضوع] [HH:MM]`\n\n"
            "مثال:\n`/schedule أخبار التكنولوجيا 08:00`",
            parse_mode="Markdown"
        )
        return

    # آخر عنصر هو الوقت، وما قبله هو الموضوع
    time_str = args[-1]
    topic = " ".join(args[:-1])

    try:
        hour, minute = map(int, time_str.split(":"))
        assert 0 <= hour <= 23 and 0 <= minute <= 59
    except:
        await update.message.reply_text("❌ الوقت غير صحيح. استخدم الصيغة HH:MM مثل 08:00")
        return

    chat_id = str(update.effective_chat.id)
    if chat_id not in scheduled_tasks:
        scheduled_tasks[chat_id] = []

    task_id = len(scheduled_tasks[chat_id]) + 1
    task = {"id": task_id, "topic": topic, "hour": hour, "minute": minute, "active": True}
    scheduled_tasks[chat_id].append(task)
    save_tasks(scheduled_tasks)

    # إضافة الوظيفة للـ scheduler
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
    tasks = scheduled_tasks.get(chat_id, [])
    active = [t for t in tasks if t["active"]]

    if not active:
        await update.message.reply_text("📭 لا توجد مهام مجدولة حالياً.\nاستخدم /schedule لإضافة مهمة.")
        return

    lines = ["📋 *مهامك المجدولة:*\n"]
    for t in active:
        lines.append(f"🔢 المهمة {t['id']}: *{t['topic']}* — ⏰ {t['hour']:02d}:{t['minute']:02d} يومياً")

    lines.append("\nلحذف مهمة: `/deltask [رقم_المهمة]`")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def deltask_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("❌ الاستخدام: `/deltask [رقم_المهمة]`", parse_mode="Markdown")
        return

    try:
        task_id = int(args[0])
    except:
        await update.message.reply_text("❌ رقم المهمة غير صحيح")
        return

    chat_id = str(update.effective_chat.id)
    tasks = scheduled_tasks.get(chat_id, [])
    found = False

    for t in tasks:
        if t["id"] == task_id and t["active"]:
            t["active"] = False
            found = True
            # إلغاء الوظيفة من الـ scheduler
            job_id = f"{chat_id}_{task_id}"
            if scheduler.get_job(job_id):
                scheduler.remove_job(job_id)
            break

    if found:
        save_tasks(scheduled_tasks)
        await update.message.reply_text(f"✅ تم حذف المهمة رقم {task_id}")
    else:
        await update.message.reply_text("❌ لم يتم إيجاد المهمة")


# ===== وظيفة إرسال التقرير الدوري =====
def _add_job(app, chat_id: str, task: dict):
    job_id = f"{chat_id}_{task['id']}"

    async def send_report():
        topic = task["topic"]
        await app.bot.send_message(chat_id=int(chat_id), text=f"⏰ *تقريرك اليومي عن: {topic}*\n\n🔍 جاري البحث...", parse_mode="Markdown")
        try:
            response = agent_executor.invoke({"input": f"ابحث عن أحدث أخبار وتطورات {topic} اليوم وقدم ملخصاً شاملاً"})
            reply = response["output"]
        except Exception as e:
            reply = f"❌ خطأ: {str(e)}"
        await app.bot.send_message(chat_id=int(chat_id), text=reply)

    scheduler.add_job(
        send_report,
        trigger="cron",
        hour=task["hour"],
        minute=task["minute"],
        id=job_id,
        replace_existing=True
    )


# ===== معالج الرسائل العامة =====
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    await update.message.reply_text("🤔 جاري المعالجة...")
    try:
        response = agent_executor.invoke({"input": user_text})
        reply = response["output"]
    except Exception as e:
        reply = f"❌ خطأ داخلي: {str(e)}"
    await update.message.reply_text(reply)


# ===== خادم الصحة =====
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Hermes Bot is running")
    def log_message(self, format, *args):
        pass  # تعطيل logs الخادم

def run_server():
    port = int(os.getenv("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()


# ===== الدالة الرئيسية =====
def main():
    threading.Thread(target=run_server, daemon=True).start()

    app = Application.builder().token(TOKEN).build()

    # تسجيل الأوامر
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("time", time_command))
    app.add_handler(CommandHandler("schedule", schedule_command))
    app.add_handler(CommandHandler("mytasks", mytasks_command))
    app.add_handler(CommandHandler("deltask", deltask_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # تحميل المهام المحفوظة عند التشغيل
    for chat_id, tasks in scheduled_tasks.items():
        for task in tasks:
            if task["active"]:
                _add_job(app, chat_id, task)

    scheduler.start()
    print("✅ Hermes Agent started with Scheduler!")
    app.run_polling()


if __name__ == "__main__":
    main()
