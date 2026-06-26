import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from langchain_openai import ChatOpenAI
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate
from langchain.memory import ConversationBufferWindowMemory

from tools import web_search, calculator

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

if not TOKEN or not OPENROUTER_API_KEY:
    raise ValueError("Missing environment variables!")

# Improved LLM + Tools + Memory
llm = ChatOpenAI(
    model="openai/gpt-4o-mini",
    openai_api_key=OPENROUTER_API_KEY,
    openai_api_base="https://openrouter.ai/api/v1",
    temperature=0.6
)

tools = [web_search, calculator]

memory = ConversationBufferWindowMemory(
    k=12,
    return_messages=True,
    memory_key="chat_history"
)

prompt = ChatPromptTemplate.from_messages([
    ("system", """You are Hermes Agent, a very intelligent and helpful assistant.
Always use tools when the user asks for current information, news, search, calculations, or anything that needs up-to-date data.
Never rely only on your internal knowledge for recent events.
Answer in Arabic unless the user asks in English."""),
    ("placeholder", "{chat_history}"),
    ("human", "{input}"),
    ("placeholder", "{agent_scratchpad}"),
])

agent = create_tool_calling_agent(llm, tools, prompt)
agent_executor = AgentExecutor(agent=agent, tools=tools, memory=memory, verbose=True)

# Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hermes Agent is ready! ✅")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    await update.message.reply_text("🤔 جاري التفكير...")

    try:
        response = agent_executor.invoke({"input": user_text})
        reply = response["output"]
    except Exception as e:
        reply = f"حصل خطأ: {str(e)}"

    await update.message.reply_text(reply)

# Keep-alive
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")

def run_server():
    port = int(os.getenv("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

def main():
    threading.Thread(target=run_server, daemon=True).start()

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Hermes Agent started...")
    app.run_polling()

if __name__ == "__main__":
    main()
