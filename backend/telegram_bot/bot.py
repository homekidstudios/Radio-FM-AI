import asyncio
import logging
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes
)
from backend.config import TELEGRAM_BOT_TOKEN, ADMIN_USER_ID
from backend.database import (
    add_to_queue, count_user_active_requests, get_pending_queue, 
    get_current_playing, get_setting, delete_queue_item
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
        "Solo escribe el nombre de la canción y el artista (o envía un enlace de YouTube).\n"
        "Ejemplo: `Queen Bohemian Rhapsody`\n\n"
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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_song_request))

    return app
