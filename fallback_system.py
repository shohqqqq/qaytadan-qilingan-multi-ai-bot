#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════╗
║          PROFESSIONAL FALLBACK SYSTEM                    ║
║                                                          ║
║  Groq  ishlamasa → Gemini ishlatadi                      ║
║  Gemini ishlamasa → Groq ishlatadi                       ║
║  Ikkalasi ishlamasa → foydalanuvchiga xabar beradi       ║
╚══════════════════════════════════════════════════════════╝
"""

import asyncio
import logging
from enum import Enum
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────
# ⚙️ TIMEOUT SOZLAMALARI
# ─────────────────────────────────────────────────────
GROQ_TIMEOUT   = 15   # sekund — Groq tez bo'lishi kerak
GEMINI_TIMEOUT = 20   # sekund — Gemini biroz sekin

# ─────────────────────────────────────────────────────
# 📊 AI NATIJALARI — kim javob berdi, kim xato berdi
# ─────────────────────────────────────────────────────
class AIStatus(Enum):
    SUCCESS  = "success"
    TIMEOUT  = "timeout"
    QUOTA    = "quota"       # Rate limit / quota tugagan
    ERROR    = "error"       # Boshqa xato


@dataclass
class AIResult:
    """Har bir AI urinishining natijasi."""
    status:   AIStatus
    reply:    Optional[str] = None
    provider: Optional[str] = None   # "Groq" yoki "Gemini"
    error:    Optional[str] = None


# ══════════════════════════════════════════════════════
# 🔒 XAVFSIZ AI CHAQIRUVLARI (timeout + try/except)
# ══════════════════════════════════════════════════════

async def safe_ask_groq(user_id: int, message: str) -> AIResult:
    """
    Groq ni xavfsiz chaqiradi.
    - Timeout bor
    - Quota/rate limit xatolarini ajratadi
    - Hech qachon exception tashlamaydi
    """
    try:
        # asyncio.wait_for → timeout uchun
        reply = await asyncio.wait_for(
            asyncio.to_thread(ask_groq, user_id, message),
            timeout=GROQ_TIMEOUT,
        )
        return AIResult(status=AIStatus.SUCCESS, reply=reply, provider="Groq")

    except asyncio.TimeoutError:
        logger.warning("⏱ Groq timeout (%ss) | user_id=%s", GROQ_TIMEOUT, user_id)
        return AIResult(status=AIStatus.TIMEOUT, provider="Groq", error="Timeout")

    except Exception as e:
        error_msg = str(e).lower()

        # Quota / rate limit xatolarini aniqlash
        if any(word in error_msg for word in ["rate_limit", "quota", "429", "limit exceeded", "too many"]):
            logger.warning("🚫 Groq quota limit | user_id=%s | xato=%s", user_id, e)
            return AIResult(status=AIStatus.QUOTA, provider="Groq", error=str(e))

        logger.error("❌ Groq xatosi | user_id=%s | xato=%s", user_id, e)
        return AIResult(status=AIStatus.ERROR, provider="Groq", error=str(e))


async def safe_ask_gemini_text(user_id: int, message: str) -> AIResult:
    """
    Gemini ni xavfsiz chaqiradi (text uchun).
    - Timeout bor
    - Quota/rate limit xatolarini ajratadi
    - Hech qachon exception tashlamaydi
    """
    try:
        reply = await asyncio.wait_for(
            asyncio.to_thread(ask_gemini_text, user_id, message),
            timeout=GEMINI_TIMEOUT,
        )
        return AIResult(status=AIStatus.SUCCESS, reply=reply, provider="Gemini")

    except asyncio.TimeoutError:
        logger.warning("⏱ Gemini timeout (%ss) | user_id=%s", GEMINI_TIMEOUT, user_id)
        return AIResult(status=AIStatus.TIMEOUT, provider="Gemini", error="Timeout")

    except Exception as e:
        error_msg = str(e).lower()

        # Gemini quota xatolarini aniqlash
        if any(word in error_msg for word in ["quota", "429", "resource_exhausted", "rate limit", "too many"]):
            logger.warning("🚫 Gemini quota limit | user_id=%s | xato=%s", user_id, e)
            return AIResult(status=AIStatus.QUOTA, provider="Gemini", error=str(e))

        logger.error("❌ Gemini xatosi | user_id=%s | xato=%s", user_id, e)
        return AIResult(status=AIStatus.ERROR, provider="Gemini", error=str(e))


async def safe_ask_gemini_media(
    user_id: int,
    file_bytes: bytes,
    file_mime: str,
    caption: str = "",
) -> AIResult:
    """
    Gemini ni xavfsiz chaqiradi (rasm/audio/PDF uchun).
    """
    try:
        reply = await asyncio.wait_for(
            asyncio.to_thread(ask_gemini, user_id, file_bytes, file_mime, caption),
            timeout=GEMINI_TIMEOUT,
        )
        return AIResult(status=AIStatus.SUCCESS, reply=reply, provider="Gemini")

    except asyncio.TimeoutError:
        logger.warning("⏱ Gemini media timeout | user_id=%s | mime=%s", user_id, file_mime)
        return AIResult(status=AIStatus.TIMEOUT, provider="Gemini", error="Timeout")

    except Exception as e:
        error_msg = str(e).lower()
        if any(word in error_msg for word in ["quota", "429", "resource_exhausted", "rate limit"]):
            logger.warning("🚫 Gemini media quota | user_id=%s | xato=%s", user_id, e)
            return AIResult(status=AIStatus.QUOTA, provider="Gemini", error=str(e))

        logger.error("❌ Gemini media xatosi | user_id=%s | xato=%s", user_id, e)
        return AIResult(status=AIStatus.ERROR, provider="Gemini", error=str(e))


# ══════════════════════════════════════════════════════
# 🔄 FALLBACK ENGINE — asosiy mantiq
# ══════════════════════════════════════════════════════

async def ask_with_fallback(
    user_id: int,
    message: str,
    primary: str = "groq",   # "groq" yoki "gemini"
) -> tuple[str, str]:
    """
    Asosiy AI ishlamasa, ikkinchisiga o'tadi.

    Returns:
        (reply_text, provider_label)
        Masalan: ("Python — dasturlash tili...", "🤖 Groq • LLaMA 3")

    Raises:
        RuntimeError — ikkala AI ham javob bera olmasa
    """

    # Qaysi biri birinchi, qaysi biri fallback
    if primary == "groq":
        first_call  = lambda: safe_ask_groq(user_id, message)
        second_call = lambda: safe_ask_gemini_text(user_id, message)
        first_label  = "🤖 Groq • LLaMA 3"
        second_label = "✨ Gemini 2.0 Flash"
    else:
        first_call  = lambda: safe_ask_gemini_text(user_id, message)
        second_call = lambda: safe_ask_groq(user_id, message)
        first_label  = "✨ Gemini 2.0 Flash"
        second_label = "🤖 Groq • LLaMA 3"

    # ── 1-urinish: asosiy AI ────────────────────────
    logger.info("🚀 1-urinish: %s | user_id=%s", primary.upper(), user_id)
    result = await first_call()

    if result.status == AIStatus.SUCCESS:
        logger.info("✅ %s muvaffaqiyatli | user_id=%s", result.provider, user_id)
        return result.reply, first_label

    # Xato sababini log qilish
    logger.warning(
        "⚠️ %s ishlamadi [%s] → fallback ga o'tilmoqda | user_id=%s",
        result.provider, result.status.value, user_id,
    )

    # ── 2-urinish: fallback AI ───────────────────────
    logger.info("🔄 Fallback urinish | user_id=%s", user_id)
    result2 = await second_call()

    if result2.status == AIStatus.SUCCESS:
        logger.info(
            "✅ Fallback %s muvaffaqiyatli | user_id=%s",
            result2.provider, user_id,
        )
        # Foydalanuvchiga qaysi AI javob berganini bildirish (fallback bo'lgani uchun)
        fallback_note = f"_(asosiy AI band, {second_label} ishlatildi)_"
        return result2.reply, fallback_note

    # ── Ikkala AI ham ishlamadi ───────────────────────
    logger.error(
        "💥 Ikkala AI ham ishlamadi | user_id=%s | 1:%s 2:%s",
        user_id, result.status.value, result2.status.value,
    )

    # Xato sababiga qarab xabar tanlash
    both_quota = (
        result.status  == AIStatus.QUOTA and
        result2.status == AIStatus.QUOTA
    )
    both_timeout = (
        result.status  == AIStatus.TIMEOUT and
        result2.status == AIStatus.TIMEOUT
    )

    if both_quota:
        raise RuntimeError("quota")
    elif both_timeout:
        raise RuntimeError("timeout")
    else:
        raise RuntimeError("error")


# ══════════════════════════════════════════════════════
# 📨 HANDLER FUNKSIYALARI
# ══════════════════════════════════════════════════════

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    📝 Oddiy matn → Groq (asosiy) → Gemini (fallback).
    """
    user_id  = update.effective_user.id
    user_msg = update.message.text

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        reply, label = await ask_with_fallback(user_id, user_msg, primary="groq")

        # Tarixga saqlash
        save_to_groq_history(user_id, "user",      user_msg)
        save_to_groq_history(user_id, "assistant", reply)

        await update.message.reply_text(
            f"{reply}\n\n{label}",
            parse_mode="Markdown",
        )

    except RuntimeError as e:
        # Foydalanuvchiga tushunarli xabar
        msg = _user_error_message(str(e))
        await update.message.reply_text(msg, parse_mode="Markdown")


async def handle_groq_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /groq <savol> → Groq (asosiy) → Gemini (fallback).
    """
    user_id  = update.effective_user.id
    user_msg = " ".join(context.args) if context.args else ""

    if not user_msg:
        await update.message.reply_text(
            "❗ Savol kiriting.\nMisol: `/groq Python nima?`",
            parse_mode="Markdown",
        )
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        reply, label = await ask_with_fallback(user_id, user_msg, primary="groq")
        save_to_groq_history(user_id, "user",      user_msg)
        save_to_groq_history(user_id, "assistant", reply)
        await update.message.reply_text(f"{reply}\n\n{label}", parse_mode="Markdown")

    except RuntimeError as e:
        await update.message.reply_text(_user_error_message(str(e)), parse_mode="Markdown")


async def handle_gemini_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /gemini <savol> → Gemini (asosiy) → Groq (fallback).
    """
    user_id  = update.effective_user.id
    user_msg = " ".join(context.args) if context.args else ""

    if not user_msg:
        await update.message.reply_text(
            "❗ Savol kiriting.\nMisol: `/gemini Hozirgi AI modellari?`",
            parse_mode="Markdown",
        )
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        reply, label = await ask_with_fallback(user_id, user_msg, primary="gemini")
        save_to_gemini_history(user_id, "user",      user_msg)
        save_to_gemini_history(user_id, "assistant", reply)
        await update.message.reply_text(f"{reply}\n\n{label}", parse_mode="Markdown")

    except RuntimeError as e:
        await update.message.reply_text(_user_error_message(str(e)), parse_mode="Markdown")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    🖼 Rasm → Gemini (asosiy) → xato xabari.
    Rasm faqat Gemini tushunadi, Groq ga fallback yo'q.
    """
    user_id = update.effective_user.id
    caption = update.message.caption or ""

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        photo      = update.message.photo[-1]
        photo_file = await context.bot.get_file(photo.file_id)
        file_bytes = await photo_file.download_as_bytearray()

        result = await safe_ask_gemini_media(user_id, bytes(file_bytes), "image/jpeg", caption)

        if result.status == AIStatus.SUCCESS:
            await update.message.reply_text(
                f"{result.reply}\n\n✨ _Gemini • Rasm tahlili_",
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(_user_error_message(result.status.value))

    except Exception as e:
        logger.error("❌ handle_photo kutilmagan xato | user_id=%s | %s", user_id, e)
        await update.message.reply_text("⚠️ Rasmni tahlil qila olmadim. Keyinroq urinib ko'ring.")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """🎤 Ovozli xabar → Gemini."""
    user_id = update.effective_user.id

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        voice_file = await context.bot.get_file(update.message.voice.file_id)
        file_bytes = await voice_file.download_as_bytearray()

        result = await safe_ask_gemini_media(
            user_id, bytes(file_bytes), "audio/ogg",
            "Bu ovozli xabarni eshit va mazmunini tushuntir. So'ng javob ber.",
        )

        if result.status == AIStatus.SUCCESS:
            await update.message.reply_text(
                f"{result.reply}\n\n✨ _Gemini • Audio tahlili_",
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(_user_error_message(result.status.value))

    except Exception as e:
        logger.error("❌ handle_voice kutilmagan xato | user_id=%s | %s", user_id, e)
        await update.message.reply_text("⚠️ Ovozni tahlil qila olmadim. Keyinroq urinib ko'ring.")


async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """🎵 Audio fayl → Gemini."""
    user_id = update.effective_user.id
    caption = update.message.caption or "Bu audio haqida aytib ber."

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        audio_file = await context.bot.get_file(update.message.audio.file_id)
        file_bytes = await audio_file.download_as_bytearray()
        mime       = update.message.audio.mime_type or "audio/mpeg"

        result = await safe_ask_gemini_media(user_id, bytes(file_bytes), mime, caption)

        if result.status == AIStatus.SUCCESS:
            await update.message.reply_text(
                f"{result.reply}\n\n✨ _Gemini • Audio tahlili_",
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(_user_error_message(result.status.value))

    except Exception as e:
        logger.error("❌ handle_audio kutilmagan xato | user_id=%s | %s", user_id, e)
        await update.message.reply_text("⚠️ Audioni tahlil qila olmadim. Keyinroq urinib ko'ring.")


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """📄 Hujjat (PDF, rasm) → Gemini."""
    user_id = update.effective_user.id
    caption = update.message.caption or "Bu hujjat haqida batafsil aytib ber."
    doc     = update.message.document
    mime    = doc.mime_type or "application/octet-stream"

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

        result = await safe_ask_gemini_media(user_id, bytes(file_bytes), mime, caption)

        if result.status == AIStatus.SUCCESS:
            await update.message.reply_text(
                f"{result.reply}\n\n✨ _Gemini • Hujjat tahlili_",
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(_user_error_message(result.status.value))

    except Exception as e:
        logger.error("❌ handle_document kutilmagan xato | user_id=%s | %s", user_id, e)
        await update.message.reply_text("⚠️ Hujjatni tahlil qila olmadim. Keyinroq urinib ko'ring.")


# ══════════════════════════════════════════════════════
# 🗣 FOYDALANUVCHIGA XABAR — xato turiga qarab
# ══════════════════════════════════════════════════════

def _user_error_message(error_type: str) -> str:
    """Xato turiga qarab foydalanuvchiga tushunarli xabar qaytaradi."""
    messages = {
        "quota": (
            "⏳ Hozir AI lar band.\n"
            "Bepul limitga yetildi. Bir oz kutib qayta yuboring."
        ),
        "timeout": (
            "🐢 AI lar hozir sekin ishlayapti.\n"
            "Iltimos, qayta yuboring."
        ),
        "error": (
            "⚠️ Texnik xato yuz berdi.\n"
            "Keyinroq urinib ko'ring yoki /help bosing."
        ),
    }
    return messages.get(error_type, messages["error"])
