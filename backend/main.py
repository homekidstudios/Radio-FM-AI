import asyncio
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import StreamingResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from backend.config import MEDIA_DIR, BASE_DIR
from backend.database import init_db
from backend.radio.player_engine import radio_engine, stream_hub
from backend.telegram_bot.bot import setup_bot_application
from backend.admin.routes import router as admin_router

active_websockets: list[WebSocket] = []

async def broadcast_ws_state(message: dict):
    disconnected = []
    for ws in active_websockets:
        try:
            await ws.send_json(message)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        if ws in active_websockets:
            active_websockets.remove(ws)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Initialize SQLite Database
    await init_db()
    print("✅ Base de datos inicializada.")

    # 2. Register WebSocket Broadcaster with Radio Engine
    radio_engine.register_ws_notifier(broadcast_ws_state)

    # 3. Start Radio Playback Engine
    engine_task = asyncio.create_task(radio_engine.start())

    # 4. Start Telegram Bot
    bot_app = setup_bot_application()
    bot_task = None
    if bot_app:
        await bot_app.initialize()
        await bot_app.start()
        bot_task = asyncio.create_task(bot_app.updater.start_polling())
        print("🤖 Bot de Telegram en línea y escuchando pedidos.")

    yield

    # Shutdown
    radio_engine.is_running = False
    engine_task.cancel()
    if bot_app:
        await bot_app.updater.stop()
        await bot_app.stop()
        await bot_app.shutdown()

app = FastAPI(title="Radio FM IA", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def admin_slash_redirect(request: Request, call_next):
    if request.url.path == "/admin":
        return RedirectResponse(url="/admin/")
    return await call_next(request)

# Admin API
app.include_router(admin_router)

@app.get("/admin")
async def admin_redirect():
    return RedirectResponse(url="/admin/")

# Audio Streaming Endpoint
@app.get("/api/stream")
async def audio_stream():
    q = stream_hub.add_listener()
    
    async def stream_generator():
        try:
            # Yield initial silence or sync header if needed
            while True:
                chunk = await q.get()
                yield chunk
        except asyncio.CancelledError:
            pass
        finally:
            stream_hub.remove_listener(q)

    return StreamingResponse(
        stream_generator(),
        media_type="audio/mpeg",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
            "X-Content-Type-Options": "nosniff"
        }
    )

# WebSocket for Realtime State
@app.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_websockets.append(websocket)
    # Send immediate initial state
    await websocket.send_json({
        "type": "initial_state",
        "state": stream_hub.current_state,
        "listeners": stream_hub.get_listener_count()
    })
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in active_websockets:
            active_websockets.remove(websocket)

# Static media mount
app.mount("/media", StaticFiles(directory=str(MEDIA_DIR)), name="media")

# Static frontend mounts
radio_frontend_dir = BASE_DIR / "frontend" / "radio"
admin_frontend_dir = BASE_DIR / "frontend" / "admin"

radio_frontend_dir.mkdir(parents=True, exist_ok=True)
admin_frontend_dir.mkdir(parents=True, exist_ok=True)

app.mount("/admin", StaticFiles(directory=str(admin_frontend_dir), html=True), name="admin")
app.mount("/", StaticFiles(directory=str(radio_frontend_dir), html=True), name="radio")
