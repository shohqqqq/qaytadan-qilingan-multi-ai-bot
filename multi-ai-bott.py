from flask import Flask
from threading import Thread

import os
import logging
import asyncio

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ─────────────────────────────────────────────
# Flask (Render keep alive)
# ─────────────────────────────────────────────
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return 'Bot is alive!'


def run_web():
    web_app.run(host='0.0.0.0', port=8080)


Thread(target=run_web, daemon=True).start()

# ─────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────
logging.basicConfig(
    format='%(asctime)s | %(levelname)s | %(message)s',
    level=logging.INFO,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# API Keys
# ─────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# ─────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────
GROQ_MODEL = 'llama3-8b-8192'
GEMINI_MODEL = 'gemini-2.0-flash'

SYSTEM_PROMPT = (
    "Sen aqlli va foydali AI yordamchisan. "
    "Foydalanuvchi qaysi tilda yozsa o‘sha tilda javob ber."
)

# ─────────────────────────────────────────────
# Groq
# ─────────────────────────────────────────────
def ask_groq(text: str) -> str:
    from groq import Groq

    client = Groq(api_key=GROQ_API_KEY)

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {
                'role': 'system',
                'content': SYSTEM_PROMPT,
            },
            {
                'role': 'user',
                'content': text,
            },
        ],
        max_tokens=1024,
        temperature=0.7,
    )

    return response.choices[0].message.content

# ─────────────────────────────────────────────
# Gemini
# ─────────────────────────────────────────────
def ask_gemini(text: str) -> str:
    import google.generativeai as genai

    genai.configure(api_key=GEMINI_API_KEY)

    model = genai.GenerativeModel(
        model_name=GEMINI_MODEL,
        system_instruction=SYSTEM_PROMPT,
    )

    response = model.generate_content(text)

    return response.text

# ─────────────────────────────────────────────
# Smart Fallback
# ─────────────────────────────────────────────
async def smart_ai(text: str):

    # 1️⃣ Avval Groq
    try:
        logger.info('Groq ishlatilmoqda...')

        response = await asyncio.to_thread(ask_groq, text)

        return response, '🤖 Groq'

    except Exception as groq_error:
        logger.error(f'Groq xatosi: {groq_error}')

    # 2️⃣ Keyin Gemini
    try:
        logger.info('Gemini fallback ishlatilmoqda...')

        response = await asyncio.to_thread(ask_gemini, text)

        return response, '✨ Gemini'

    except Exception as gemini_error:
        logger.error(f'Gemini xatosi: {gemini_error}')

    # 3️⃣ Ikkalasi ham ishlamasa
    return (
        '⚠️ Hozircha AI javob bera olmayapti. Keyinroq urinib ko‘ring.',
        '❌ Error',
    )

# ─────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        'Salom 👋\n\n'
        'Bot ishlayapti!\n'
        'Text yuboring.'
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action='typing'
    )

    response, ai_name = await smart_ai(text)

    await update.message.reply_text(
        f'{response}\n\n{ai_name}'
    )

# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────
def main():

    if not TELEGRAM_BOT_TOKEN:
        logger.error('TOKEN topilmadi!')
        return

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler('start', start))

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_text,
        )
    )

    logger.info('Bot ishga tushdi ✅')

    import asyncio

async def run_bot():
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    
    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(run_bot())


