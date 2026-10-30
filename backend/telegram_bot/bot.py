import asyncio
import logging
import os
import tempfile
import httpx
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes
)
from backend.config import TELEGRAM_BOT_TOKEN, ADMIN_USER_ID
from backend.database import (
    add_to_queue, count_user_active_requests, get_pending_queue, 
    get_current_playing, get_setting, delete_queue_item, get_active_providers
)
from backend.radio.player_engine import radio_engine
from backend.radio.downloader import quick_search

logger = logging.getLogger(__name__)

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.first_name
    chat_id = str(update.effective_chat.id)
    is_admin = (ADMIN_USER_ID and chat_id == str(ADMIN_USER_ID))

    admin_extra = "\n👑 **Modo Administrador Activo:**\n• `/saltar` — Saltar pista o locutor actual\n• `/limpiar` — Vaciar cola de espera\n" if is_admin else ""

    await update.message.reply_text(
        f"👋 ¡Hola {user}! Bienvenido a la cabina de **Radio FM** 📻✨\n\n"
        "Aquí puedes pedir tu música favorita para que suene al aire en la radio web.\n\n"
        "📌 **¿Cómo pedir una canción?**\n"
        "• Escribe el nombre de la canción y el artista.\n"
        "  Ejemplo: `Queen Bohemian Rhapsody`\n"
        "• Pega un enlace de YouTube.\n"
        "• 🎙️ **¡Envía una nota de voz!** Di o tararea la canción y la IA la identificará.\n\n"
        "📋 **Comandos útiles:**\n"
        "• `/cola` — Ver canciones en espera y turnos\n"
        "• `/mipedido` — Estado de tu turno actual\n"
        "• `/ayuda` — Instrucciones de uso\n"
        f"{admin_extra}",
        parse_mode="Markdown"
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start_cmd(update, context)

async def cola_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current = await get_current_playing()
    pending = await get_pending_queue()

    msg = "📻 **ESTADO DE LA RADIO** 📻\n\n"
    if current:
        msg += f"▶️ **Al Aire:** {current['title']} — {current.get('artist', '')}\n"
        msg += f"👤 Pedida por: @{current.get('requester_username') or current.get('requester_name')}\n\n"
    else:
        msg += "⏸️ **Al Aire:** Ninguna canción sonando en este momento.\n\n"

    msg += "📋 **Próximos Turnos:**\n"
    if not pending:
        msg += "La cola está vacía. ¡Sé el primero en pedir una canción!\n"
    else:
        for i, item in enumerate(pending[:7], start=1):
            user_lbl = f"@{item['requester_username']}" if item.get('requester_username') else item.get('requester_name', 'Oyente')
            status_icon = "⏳" if item['status'] == 'queued' else "⬇️"
            msg += f"#{i} {status_icon} **{item['title']}** ({user_lbl})\n"

        if len(pending) > 7:
            msg += f"\n... y {len(pending) - 7} temas más en espera."

    await update.message.reply_text(msg, parse_mode="Markdown")

async def mipedido_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    pending = await get_pending_queue()
    current = await get_current_playing()

    if current and str(current.get("requester_chat_id")) == chat_id:
        await update.message.reply_text(
            f"🎉 ¡Tu canción **{current['title']}** está sonando **AHORA MISMO** al aire en la radio! 📻🎶",
            parse_mode="Markdown"
        )
        return

    user_item = None
    position = 0
    for idx, item in enumerate(pending, start=1):
        if str(item.get("requester_chat_id")) == chat_id:
            user_item = item
            position = idx
            break

    if user_item:
        await update.message.reply_text(
            f"⏳ Tu canción **{user_item['title']}** está en el **Turno #{position}** de la cola.\n"
            f"Apenas termine la música anterior y el locutor dé su comentario, sonará la tuya.",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "No tienes ninguna canción en espera. Escribe el nombre de un tema para solicitarlo.",
            parse_mode="Markdown"
        )

async def handle_song_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text:
        return

    chat_id = str(update.effective_chat.id)
    user = update.effective_user
    username = user.username or ""
    display_name = user.first_name or "Oyente"

    # Anti-Flood / Fair Turn Check
    turn_active = await get_setting("turn_system_active", "true") == "true"
    max_per_user = int(await get_setting("max_queue_per_user", "1"))

    if turn_active:
        active_count = await count_user_active_requests(chat_id)
        if active_count >= max_per_user:
            await update.message.reply_text(
                "⏳ **Ya tienes un turno activo en la cola.**\n\n"
                "Para que todos los oyentes tengan oportunidad de escuchar su música, "
                "debes esperar a que termine tu tema actual antes de pedir otro. ¡Gracias por tu comprensión! 🙌",
                parse_mode="Markdown"
            )
            return

    status_msg = await update.message.reply_text(f"🔍 Buscando `'{text}'` en el catálogo...")

    try:
        # Search metadata
        info = await quick_search(text)
        title = info["title"]
        artist = info["artist"]
        url = info["url"]

        # Insert to DB queue
        track_id = await add_to_queue(
            title=title,
            artist=artist,
            youtube_url=url,
            requester_username=username,
            requester_name=display_name,
            requester_chat_id=chat_id
        )

        pending = await get_pending_queue()
        position = len(pending)

        await status_msg.edit_text(
            f"✅ **¡Canción agregada con éxito!**\n\n"
            f"🎵 **{title}**\n"
            f"🎤 {artist}\n"
            f"📋 **Turno:** #{position} en la cola\n\n"
            f"📻 Sintoniza la radio web. ¡El locutor IA anunciará tu tema cuando llegue el turno!",
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.error(f"Error procesando pedido: {e}")
        await status_msg.edit_text(
            "❌ No pudimos encontrar esa canción. Intenta ser más específico con el nombre del artista y título."
        )

async def saltar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if ADMIN_USER_ID and chat_id != str(ADMIN_USER_ID):
        await update.message.reply_text("⛔ Este comando es exclusivo para el administrador de la radio.")
        return
    radio_engine.request_skip()
    await update.message.reply_text("⏭️ **Comando recibido:** Saltando a la siguiente pista o locutor.", parse_mode="Markdown")

async def limpiar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if ADMIN_USER_ID and chat_id != str(ADMIN_USER_ID):
        await update.message.reply_text("⛔ Este comando es exclusivo para el administrador de la radio.")
        return
    pending = await get_pending_queue()
    for item in pending:
        await delete_queue_item(item["id"])
    await update.message.reply_text(f"🗑️ Se han eliminado {len(pending)} canciones de la cola.")

# ==========================================
# VOICE MESSAGE HANDLER (Notas de Voz)
# ==========================================

async def _transcribe_audio_groq(audio_path: str) -> str:
    """Transcribes audio to text using Groq Whisper (free & fast)."""
    providers = await get_active_providers()
    groq_key = None
    for p in providers:
        if p["provider_type"] == "groq":
            groq_key = p["api_key"]
            break
    if not groq_key:
        groq_key = os.getenv("GROQ_API_KEY", "")
    if not groq_key:
        return ""

    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    async with httpx.AsyncClient(timeout=30.0) as client:
        with open(audio_path, "rb") as f:
            res = await client.post(
                url,
                headers={"Authorization": f"Bearer {groq_key}"},
                files={"file": ("audio.ogg", f, "audio/ogg")},
                data={"model": "whisper-large-v3-turbo", "language": "es"}
            )
        res.raise_for_status()
        return res.json().get("text", "").strip()

async def _ai_identify_song(description: str) -> str:
    """Uses AI to identify a song from a vague description or humming transcript."""
    providers = await get_active_providers()
    groq_key = None
    for p in providers:
        if p["provider_type"] == "groq":
            groq_key = p["api_key"]
            break
    if not groq_key:
        groq_key = os.getenv("GROQ_API_KEY", "")
    if not groq_key:
        return description

    prompt = (
        f"El usuario describió o tarareó una canción así: \"{description}\"\n"
        "Identifica la canción más probable. Responde SOLO con: Artista - Título\n"
        "Si no puedes identificarla, responde exactamente el texto original del usuario."
    )
    url = "https://api.groq.com/openai/v1/chat/completions"
    async with httpx.AsyncClient(timeout=15.0) as client:
        res = await client.post(
            url,
            headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
            json={
                "model": "qwen/qwen3.8-27b",
                "messages": [
                    {"role": "system", "content": "Eres un experto en música. Identifica canciones a partir de descripciones vagas, letras parciales o tarareos. Responde SOLO con: Artista - Título"},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.1,
                "max_tokens": 60
            }
        )
        res.raise_for_status()
        result = res.json()["choices"][0]["message"]["content"].strip()
        # Limpiar marcadores de pensamiento si los hay
        if "</think>" in result:
            result = result.split("</think>")[-1].strip()
        return result if result else description

async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles voice messages: transcribes audio and searches for the song."""
    voice = update.message.voice or update.message.audio
    if not voice:
        return

    chat_id = str(update.effective_chat.id)
    user = update.effective_user
    username = user.username or ""
    display_name = user.first_name or "Oyente"

    # Anti-Flood check
    turn_active = await get_setting("turn_system_active", "true") == "true"
    max_per_user = int(await get_setting("max_queue_per_user", "1"))
    if turn_active:
        active_count = await count_user_active_requests(chat_id)
        if active_count >= max_per_user:
            await update.message.reply_text(
                "⏳ **Ya tienes un turno activo en la cola.**\n"
                "Espera a que termine tu tema actual antes de pedir otro. 🙌",
                parse_mode="Markdown"
            )
            return

    status_msg = await update.message.reply_text("🎙️ Escuchando tu audio... un momento.")

    try:
        # Download the voice file from Telegram
        file = await voice.get_file()
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp_path = tmp.name
        await file.download_to_drive(tmp_path)

        # Transcribe with Groq Whisper
        transcript = await _transcribe_audio_groq(tmp_path)

        # Clean up temp file
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

        if not transcript:
            await status_msg.edit_text(
                "❌ No pude entender el audio. Intenta hablar más claro o escribe el nombre de la canción."
            )
            return

        await status_msg.edit_text(
            f"🎙️ Escuché: *\"{transcript}\"*\n🔍 Buscando la canción...",
            parse_mode="Markdown"
        )

        # Use AI to identify the song if the transcript seems like humming or vague
        search_query = await _ai_identify_song(transcript)

        # Search and enqueue
        info = await quick_search(search_query)
        title = info["title"]
        artist = info["artist"]
        url = info["url"]

        track_id = await add_to_queue(
            title=title,
            artist=artist,
            youtube_url=url,
            requester_username=username,
            requester_name=display_name,
            requester_chat_id=chat_id
        )

        pending = await get_pending_queue()
        position = len(pending)

        await status_msg.edit_text(
            f"✅ **¡Canción identificada y agregada!**\n\n"
            f"🎙️ Escuché: *\"{transcript}\"*\n"
            f"🎵 **{title}**\n"
            f"🎤 {artist}\n"
            f"📋 **Turno:** #{position} en la cola\n\n"
            f"📻 ¡El locutor IA anunciará tu tema cuando llegue el turno!",
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.error(f"Error procesando nota de voz: {e}")
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        await status_msg.edit_text(
            "❌ No pude procesar tu audio. Intenta enviarlo de nuevo o escribe el nombre de la canción."
        )

def setup_bot_application() -> Application | None:
    if not TELEGRAM_BOT_TOKEN:
        print("ℹ️ Telegram Bot Token no configurado aún. El bot se iniciará cuando se ingrese en el .env o Panel Admin.")
        return None

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("ayuda", help_cmd))
    app.add_handler(CommandHandler("cola", cola_cmd))
    app.add_handler(CommandHandler("mipedido", mipedido_cmd))
    app.add_handler(CommandHandler("saltar", saltar_cmd))
    app.add_handler(CommandHandler("limpiar", limpiar_cmd))
    app.add_handler(CommandHandler("pedir", handle_song_request))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice_message))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_song_request))

    return app
