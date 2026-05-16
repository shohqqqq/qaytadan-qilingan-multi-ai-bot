#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════╗
║         Telegram Multi-AI Bot: Groq + Gemini         ║
║                                                      ║
║  📝 /groq   → Groq  (LLaMA 3, tez)                  ║
║  ✨ /gemini → Gemini (yangi bilim, text)             ║
║  🖼 Rasm / 🎤 Audio → Gemini (multimodal)            ║
╚══════════════════════════════════════════════════════╝

O'rnatish:
    pip install python-telegram-bot groq google-generativeai

Render uchun environment variables:
    TELEGRAM_BOT_TOKEN
    GROQ_API_KEY
    GEMINI_API_KEY
"""
from flask import Flask
from threading import Thread

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

Thread(target=run, daemon=True).start()

import os
import io
import logging
import tempfile

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# ─────────────────────────────────────────────────────
# 🔑 API KALITLARI
# Render da Environment Variables orqali qo'ying!
# Lokal test uchun to'g'ridan-to'g'ri yozsa ham bo'ladi.
# ─────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
GROQ_API_KEY       = os.environ.get("GROQ_API_KEY",       "YOUR_GROQ_API_KEY")
GEMINI_API_KEY     = os.environ.get("GEMINI_API_KEY",     "YOUR_GEMINI_API_KEY")

# ─────────────────────────────────────────────────────
# 📋 MODELLAR
# ─────────────────────────────────────────────────────
GROQ_MODEL   = "llama3-8b-8192"    # Groq bepul modeli (tez, barqaror)
GEMINI_MODEL = "gemini-2.0-flash"  # Gemini bepul modeli (yangi bilim)

# ─────────────────────────────────────────────────────
# 📝 SYSTEM PROMPT (ikkala AI uchun bir xil)
# ─────────────────────────────────────────────────────
SYSTEM_PROMPT = (
    "Siz foydali, aqlli va do'stona AI yordamchisiz. "
    "Foydalanuvchi qaysi tilda yozsa, o'sha tilda javob bering. "
    "Qisqa va aniq javob bering."
)

# ─────────────────────────────────────────────────────
# 🗂 LOGGING
# ─────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────
# 💾 FOYDALANUVCHI TARIXI
# Groq va Gemini tarixi ALOHIDA saqlanadi — aralashmaydi!
#
# groq_histories  : { user_id: [ {"role": "user/assistant", "content": "..."} ] }
# gemini_histories: { user_id: [ {"role": "user/assistant", "content": "..."} ] }
# ─────────────────────────────────────────────────────
groq_histories:   dict[int, list[dict]] = {}
gemini_histories: dict[int, list[dict]] = {}
MAX_HISTORY = 20  # Token tejash uchun maksimal xabar soni


def get_groq_history(user_id: int) -> list[dict]:
    """Groq suhbat tarixini qaytaradi."""
    if user_id not in groq_histories:
        groq_histories[user_id] = []
    return groq_histories[user_id]


def get_gemini_history(user_id: int) -> list[dict]:
    """Gemini suhbat tarixini qaytaradi."""
    if user_id not in gemini_histories:
        gemini_histories[user_id] = []
    return gemini_histories[user_id]


def save_to_groq_history(user_id: int, role: str, content: str) -> None:
    """Groq tarixiga xabar qo'shadi."""
    history = get_groq_history(user_id)
    history.append({"role": role, "content": content})
    if len(history) > MAX_HISTORY:
        groq_histories[user_id] = history[-MAX_HISTORY:]


def save_to_gemini_history(user_id: int, role: str, content: str) -> None:
    """Gemini tarixiga xabar qo'shadi."""
    history = get_gemini_history(user_id)
    history.append({"role": role, "content": content})
    if len(history) > MAX_HISTORY:
        gemini_histories[user_id] = history[-MAX_HISTORY:]


# ══════════════════════════════════════════════════════
# 🤖 AI FUNKSIYALARI
# ══════════════════════════════════════════════════════

def ask_groq(user_id: int, user_message: str) -> str:
    """
    📝 GROQ — Faqat text savollar uchun.

    - LLaMA 3 modeli ishlatadi (tez va bepul)
    - Faqat groq_histories dan tarix oladi
    - Gemini tarixi bilan ARALASHMAYDI
    """
    from groq import Groq

    client = Groq(api_key=GROQ_API_KEY)

    # Faqat Groq tarixi (Gemini tarixi yo'q bu yerda)
    history = get_groq_history(user_id)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *history,
        {"role": "user", "content": user_message},
    ]

    logger.info("Groq ga so'rov yuborildi | user_id=%s", user_id)

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=messages,
        max_tokens=1024,
        temperature=0.7,
    )

    reply = response.choices[0].message.content
    logger.info("Groq javob berdi | user_id=%s", user_id)
    return reply


def ask_gemini_text(user_id: int, user_message: str) -> str:
    """
    ✨ GEMINI — Text savollar uchun MUSTAQIL funksiya.

    - Gemini 2.0 Flash ishlatadi (yangi bilim, internet ma'lumoti)
    - Faqat gemini_histories dan tarix oladi
    - Groq tarixi bilan ARALASHMAYDI
    - Bu funksiya fallback EMAS — to'liq mustaqil!

    Groq va Gemini farqi:
      Groq  → LLaMA 3 (tez, training data eski bo'lishi mumkin)
      Gemini → Google modeli (yangi ma'lumotlar, keng bilim)
    """
    import google.generativeai as genai

    genai.configure(api_key=GEMINI_API_KEY)

    model = genai.GenerativeModel(
        model_name=GEMINI_MODEL,
        system_instruction=SYSTEM_PROMPT,
    )

    # Faqat Gemini tarixi (Groq tarixi yo'q bu yerda)
    history = get_gemini_history(user_id)

    # Gemini o'z formatini talab qiladi:
    # "assistant" → "model" deb o'zgartiriladi
    gemini_history = [
        {
            "role": "user" if msg["role"] == "user" else "model",
            "parts": [msg["content"]],
        }
        for msg in history
    ]

    logger.info("Gemini (text) ga so'rov yuborildi | user_id=%s", user_id)

    chat = model.start_chat(history=gemini_history)
    response = chat.send_message(user_message)

    logger.info("Gemini (text) javob berdi | user_id=%s", user_id)
    return response.text


def ask_gemini(user_id: int, file_bytes: bytes, file_mime: str, caption: str = "") -> str:
    """
    🖼🎤 GEMINI — Rasm, audio, va murakkab analiz uchun.

    - Fayl (rasm/audio/PDF) + izoh ni Gemini ga yuboradi
    - Bu multimodal so'rov, tarix saqlanmaydi (har safar yangi)
    - Gemini fayl kontentini to'g'ridan-to'g'ri tushunadi

    :param user_id:    Foydalanuvchi ID (loglash uchun)
    :param file_bytes: Faylning binary ma'lumotlari
    :param file_mime:  Fayl turi: "image/jpeg", "audio/ogg", "application/pdf"
    :param caption:    Foydalanuvchi yozgan izoh (ixtiyoriy)
    """
    import google.generativeai as genai

    genai.configure(api_key=GEMINI_API_KEY)

    model = genai.GenerativeModel(
        model_name=GEMINI_MODEL,
        system_instruction=SYSTEM_PROMPT,
    )

    prompt_text = caption if caption else "Bu fayl haqida batafsil aytib ber."

    # Gemini inline data + matn birgalikda yuboriladi
    response = model.generate_content([
        {"mime_type": file_mime, "data": file_bytes},
        prompt_text,
    ])

    logger.info("Gemini (multimodal) javob berdi | user_id=%s | mime=%s", user_id, file_mime)
    return response.text


# ══════════════════════════════════════════════════════
# 📨 TELEGRAM HANDLER FUNKSIYALARI
# ══════════════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/start buyrug'i — foydalanuvchini qabul qiladi."""
    name = update.effective_user.first_name
    await update.message.reply_text(
        f"Salom, {name}! 👋\n\n"
        "Ikki AI — bir bot:\n\n"
        "🤖 /groq `savol` — Groq (LLaMA 3, tez)\n"
        "✨ /gemini `savol` — Gemini (yangi bilim)\n\n"
        "Oddiy matn yozsangiz → Groq javob beradi\n"
        "🖼 Rasm / 🎤 Audio → Gemini javob beradi\n\n"
        "*/clear\\_groq* – Groq tarixini tozalash\n"
        "*/clear\\_gemini* – Gemini tarixini tozalash\n"
        "*/clear* – Ikkalasini tozalash",
        parse_mode="Markdown",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/help buyrug'i."""
    await update.message.reply_text(
        "🆘 *Yordam*\n\n"
        "*Text savollar:*\n"
        "• Oddiy yozsangiz → 🤖 Groq (LLaMA 3)\n"
        "• /groq `savol` → 🤖 Groq\n"
        "• /gemini `savol` → ✨ Gemini (yangi bilim)\n\n"
        "*Fayl yuborish:*\n"
        "• 🖼 Rasm → Gemini tahlil qiladi\n"
        "• 🎤 Voice/Audio → Gemini eshitadi\n"
        "• 📄 PDF → Gemini o'qiydi\n\n"
        "*Tarix tozalash:*\n"
        "• /clear\\_groq – Groq tarixi\n"
        "• /clear\\_gemini – Gemini tarixi\n"
        "• /clear – Hammasi",
        parse_mode="Markdown",
    )


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/clear — ikkala AI tarixini tozalaydi."""
    user_id = update.effective_user.id
    groq_histories[user_id]   = []
    gemini_histories[user_id] = []
    await update.message.reply_text("✅ Groq va Gemini tarixi tozalandi!")


async def clear_groq_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/clear_groq — faqat Groq tarixini tozalaydi."""
    user_id = update.effective_user.id
    groq_histories[user_id] = []
    await update.message.reply_text("✅ Groq tarixi tozalandi!")


async def clear_gemini_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/clear_gemini — faqat Gemini tarixini tozalaydi."""
    user_id = update.effective_user.id
    gemini_histories[user_id] = []
    await update.message.reply_text("✅ Gemini tarixi tozalandi!")


async def handle_groq_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /groq <savol> — Foydalanuvchi aniq Groq dan javob so'raydi.
    Misol: /groq Python nima?
    """
    user_id  = update.effective_user.id
    # Buyruqdan keyingi matnni olish
    user_msg = " ".join(context.args) if context.args else ""

    if not user_msg:
        await update.message.reply_text(
            "❗ Savol kiriting.\nMisol: `/groq Python nima?`",
            parse_mode="Markdown",
        )
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        reply = ask_groq(user_id, user_msg)
        save_to_groq_history(user_id, "user", user_msg)
        save_to_groq_history(user_id, "assistant", reply)
        await update.message.reply_text(f"{reply}\n\n🤖 _Groq • LLaMA 3_", parse_mode="Markdown")
    except Exception as e:
        logger.error("Groq xatosi: %s", e)
        await update.message.reply_text(f"⚠️ Groq xatosi:\n`{e}`", parse_mode="Markdown")


async def handle_gemini_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /gemini <savol> — Foydalanuvchi aniq Gemini dan javob so'raydi.
    Misol: /gemini 2025 yilda nima yangiliklar bor?

    Gemini Groq dan farqli — yangi ma'lumotlar bilan o'qitilgan,
    shuning uchun dolzarb savollar uchun yaxshiroq.
    """
    user_id  = update.effective_user.id
    user_msg = " ".join(context.args) if context.args else ""

    if not user_msg:
        await update.message.reply_text(
            "❗ Savol kiriting.\nMisol: `/gemini Hozirgi AI modellari qaysilar?`",
            parse_mode="Markdown",
        )
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        # ask_gemini_text — Gemini text funksiyasi (mustaqil, Groq bilan aloqasi yo'q)
        reply = ask_gemini_text(user_id, user_msg)
        save_to_gemini_history(user_id, "user", user_msg)
        save_to_gemini_history(user_id, "assistant", reply)
        await update.message.reply_text(f"{reply}\n\n✨ _Gemini 2.0 Flash_", parse_mode="Markdown")
    except Exception as e:
        logger.error("Gemini text xatosi: %s", e)
        await update.message.reply_text(f"⚠️ Gemini xatosi:\n`{e}`", parse_mode="Markdown")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    📝 Oddiy matn → Groq ga yuboradi (default).
    Groq ishlamasa → Gemini ga fallback.
    """
    user_id  = update.effective_user.id
    user_msg = update.message.text

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        reply = ask_groq(user_id, user_msg)
        save_to_groq_history(user_id, "user", user_msg)
        save_to_groq_history(user_id, "assistant", reply)
        await update.message.reply_text(f"{reply}\n\n🤖 _Groq • LLaMA 3_", parse_mode="Markdown")

    except Exception as e:
        logger.error("Groq xatosi: %s", e)
        # Groq ishlamasa Gemini ga fallback (Gemini tarixiga SAQLANMAYDI)
        try:
            logger.info("Groq ishlamadi → Gemini fallback")
            reply = ask_gemini_text(user_id, user_msg)
            save_to_groq_history(user_id, "user", user_msg)
            save_to_groq_history(user_id, "assistant", reply)
            await update.message.reply_text(
                f"{reply}\n\n✨ _Gemini (fallback)_",
                parse_mode="Markdown",
            )
        except Exception as e2:
            logger.error("Gemini fallback xatosi: %s", e2)
            await update.message.reply_text(
                "⚠️ Ikkala AI ham javob bera olmadi.\n"
                "API kalitlarini tekshiring yoki keyinroq urinib ko'ring."
            )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    🖼 Rasm xabarlarni qabul qiladi → Gemini ga yuboradi.
    """
    user_id = update.effective_user.id
    caption = update.message.caption or ""

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        # Eng yuqori sifatli rasmni olish (oxirgi element = katta hajm)
        photo = update.message.photo[-1]
        photo_file = await context.bot.get_file(photo.file_id)

        # Rasmni xotiraga yuklab olish (diskka saqlamasdan)
        file_bytes = await photo_file.download_as_bytearray()

        # ── Gemini ga yuborish ─────────────────────────
        reply = ask_gemini(user_id, bytes(file_bytes), "image/jpeg", caption)

        await update.message.reply_text(f"{reply}\n\n✨ _Gemini • Rasm tahlili_", parse_mode="Markdown")

    except Exception as e:
        logger.error("Gemini rasm xatosi: %s", e)
        await update.message.reply_text(
            f"⚠️ Rasmni tahlil qila olmadim.\nXato: `{e}`",
            parse_mode="Markdown",
        )


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    🎤 Ovozli xabarlarni qabul qiladi → Gemini ga yuboradi.
    Gemini audio ni to'g'ridan-to'g'ri eshitib tahlil qiladi.
    """
    user_id = update.effective_user.id

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        voice_file = await context.bot.get_file(update.message.voice.file_id)
        file_bytes = await voice_file.download_as_bytearray()

        # ── Gemini ga yuborish (audio OGG format) ─────
        reply = ask_gemini(
            user_id,
            bytes(file_bytes),
            "audio/ogg",
            "Bu ovozli xabarni eshit va mazmunini tushuntir. So'ng javob ber.",
        )

        await update.message.reply_text(f"{reply}\n\n✨ _Gemini • Audio tahlili_", parse_mode="Markdown")

    except Exception as e:
        logger.error("Gemini audio xatosi: %s", e)
        await update.message.reply_text(
            f"⚠️ Ovozni tahlil qila olmadim.\nXato: `{e}`",
            parse_mode="Markdown",
        )


async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    🎵 Audio fayllarni (mp3, wav va h.k.) → Gemini ga yuboradi.
    """
    user_id = update.effective_user.id
    caption = update.message.caption or "Bu audio haqida aytib ber."

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        audio_file = await context.bot.get_file(update.message.audio.file_id)
        file_bytes = await audio_file.download_as_bytearray()

        # MIME turini aniqlash
        mime = update.message.audio.mime_type or "audio/mpeg"

        reply = ask_gemini(user_id, bytes(file_bytes), mime, caption)

        await update.message.reply_text(f"{reply}\n\n✨ _Gemini • Audio tahlili_", parse_mode="Markdown")

    except Exception as e:
        logger.error("Gemini audio fayl xatosi: %s", e)
        await update.message.reply_text(
            f"⚠️ Audio faylni tahlil qila olmadim.\nXato: `{e}`",
            parse_mode="Markdown",
        )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    📄 Hujjat (PDF, rasm fayl va h.k.) → Gemini ga yuboradi.
    """
    user_id  = update.effective_user.id
    caption  = update.message.caption or "Bu hujjat haqida batafsil aytib ber."
    doc      = update.message.document
    mime     = doc.mime_type or "application/octet-stream"

    # Faqat qo'llab-quvvatlanadigan formatlar
    SUPPORTED = ("image/", "audio/", "application/pdf")
    if not any(mime.startswith(s) for s in SUPPORTED):
        await update.message.reply_text(
            "⚠️ Bu fayl turi qo'llab-quvvatlanmaydi.\n"
            "Rasm, audio yoki PDF yuboring."
        )
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        doc_file   = await context.bot.get_file(doc.file_id)
        file_bytes = await doc_file.download_as_bytearray()

        reply = ask_gemini(user_id, bytes(file_bytes), mime, caption)

        await update.message.reply_text(f"{reply}\n\n✨ _Gemini • Hujjat tahlili_", parse_mode="Markdown")

    except Exception as e:
        logger.error("Gemini hujjat xatosi: %s", e)
        await update.message.reply_text(
            f"⚠️ Hujjatni tahlil qila olmadim.\nXato: `{e}`",
            parse_mode="Markdown",
        )


# ══════════════════════════════════════════════════════
# 🚀 MAIN — Botni ishga tushirish
# ══════════════════════════════════════════════════════

def main() -> None:
    """Botni ishga tushiradi."""

    # Token tekshiruvi
    if TELEGRAM_BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN":
        logger.error("❌ TELEGRAM_BOT_TOKEN o'rnatilmagan!")
        return

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # ── Buyruqlar ────────────────────────────────────
    app.add_handler(CommandHandler("start",        start))
    app.add_handler(CommandHandler("help",         help_command))
    app.add_handler(CommandHandler("clear",        clear_command))
    app.add_handler(CommandHandler("clear_groq",   clear_groq_command))
    app.add_handler(CommandHandler("clear_gemini", clear_gemini_command))
    app.add_handler(CommandHandler("groq",         handle_groq_command))
    app.add_handler(CommandHandler("gemini",       handle_gemini_command))

    # ── Media handler lar ────────────────────────────
    app.add_handler(MessageHandler(filters.PHOTO,   handle_photo))
    app.add_handler(MessageHandler(filters.VOICE,   handle_voice))
    app.add_handler(MessageHandler(filters.AUDIO,   handle_audio))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    # ── Text handler (eng oxirida!) ──────────────────
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("✅ Bot ishga tushdi! Ctrl+C bilan to'xtatish mumkin.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
