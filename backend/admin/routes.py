from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from backend.database import (
    get_db, get_pending_queue, get_current_playing, delete_queue_item,
    add_to_queue, get_active_providers, save_provider, delete_provider,
    get_all_settings, set_setting
)
from backend.radio.player_engine import radio_engine, stream_hub
from backend.radio.downloader import quick_search
from backend.radio.locutor import synthesize_voice

router = APIRouter(prefix="/api", tags=["admin"])

class ProviderCreate(BaseModel):
    name: str
    provider_type: str
    api_key: str
    model_name: str
    priority: int = 1
    base_url: Optional[str] = ""

class SettingsUpdate(BaseModel):
    settings: dict

class ManualSongAdd(BaseModel):
    query: str

class TestVoiceReq(BaseModel):
    text: str
    voice: Optional[str] = "es-ES-AlvaroNeural"

@router.get("/stats")
async def get_stats():
    async with get_db() as db:
        async with db.execute("SELECT COUNT(*) as c FROM queue WHERE status = 'finished'") as cursor:
            played_count = (await cursor.fetchone())["c"]
        async with db.execute("SELECT COUNT(DISTINCT requester_chat_id) as c FROM queue") as cursor:
            users_count = (await cursor.fetchone())["c"]

    pending = await get_pending_queue()
    providers = await get_active_providers()

    return {
        "listeners": stream_hub.get_listener_count(),
        "played_today": played_count,
        "queue_count": len(pending),
        "total_users": users_count,
        "active_providers_count": len(providers),
        "current_state": stream_hub.current_state
    }

@router.get("/queue")
async def get_queue():
    current = await get_current_playing()
    pending = await get_pending_queue()
    return {
        "current": current,
        "pending": pending
    }

@router.post("/queue/add")
async def add_manual_song(body: ManualSongAdd):
    try:
        info = await quick_search(body.query)
        track_id = await add_to_queue(
            title=info["title"],
            artist=info["artist"],
            youtube_url=info["url"],
            requester_username="admin",
            requester_name="Admin Cabina",
            requester_chat_id="0"
        )
        return {"success": True, "track_id": track_id, "title": info["title"]}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/queue/{track_id}")
async def remove_from_queue(track_id: int):
    await delete_queue_item(track_id)
    return {"success": True}

@router.post("/queue/skip")
async def skip_current():
    radio_engine.request_skip()
    return {"success": True, "message": "Saltando a la siguiente pista o locutor"}

@router.get("/providers")
async def list_providers():
    async with get_db() as db:
        async with db.execute("SELECT * FROM ai_providers ORDER BY priority ASC, id ASC") as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

@router.post("/providers")
async def add_provider(prov: ProviderCreate):
    await save_provider(
        name=prov.name,
        provider_type=prov.provider_type,
        api_key=prov.api_key,
        model_name=prov.model_name,
        priority=prov.priority,
        base_url=prov.base_url or ""
    )
    return {"success": True}

@router.delete("/providers/{provider_id}")
async def remove_provider(provider_id: int):
    await delete_provider(provider_id)
    return {"success": True}

@router.get("/settings")
async def fetch_settings():
    return await get_all_settings()

@router.post("/settings")
async def update_settings(data: SettingsUpdate):
    for k, v in data.settings.items():
        await set_setting(k, str(v))
    return {"success": True}

@router.post("/locutor/test")
async def test_locutor(body: TestVoiceReq):
    try:
        audio_path = await synthesize_voice(body.text, body.voice)
        return {"success": True, "audio_url": f"/media/tts/{audio_path.split('/')[-1]}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
