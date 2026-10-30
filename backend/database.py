import aiosqlite
import json
from datetime import datetime
from contextlib import asynccontextmanager
from backend.config import DB_PATH, DATA_DIR

@asynccontextmanager
async def get_db():
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()

async def init_db():
    async with get_db() as db:
        # Table: Queue of Songs
        await db.execute("""
            CREATE TABLE IF NOT EXISTS queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                artist TEXT DEFAULT 'Desconocido',
                duration INTEGER DEFAULT 0,
                youtube_url TEXT,
                file_path TEXT,
                requester_username TEXT DEFAULT '',
                requester_name TEXT DEFAULT 'Oyente Anónimo',
                requester_chat_id TEXT DEFAULT '',
                status TEXT DEFAULT 'queued', -- queued, downloading, ready, playing, finished, failed
                position INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                played_at TIMESTAMP
            )
        """)

        # Table: FreeLLM AI Providers
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ai_providers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                provider_type TEXT NOT NULL, -- groq, gemini, cerebras, openrouter, custom
                api_key TEXT NOT NULL,
                model_name TEXT NOT NULL,
                base_url TEXT DEFAULT '',
                is_active INTEGER DEFAULT 1,
                priority INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Table: Station & Locutor Settings
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        # Table: Locutor Comments History
        await db.execute("""
            CREATE TABLE IF NOT EXISTS locutor_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                track_id INTEGER,
                comment_text TEXT NOT NULL,
                voice_file TEXT,
                provider_used TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Default Settings
        default_settings = {
            "locutor_name": "DJ Neon",
            "locutor_voice": "es-ES-AlvaroNeural", # es-MX-DaliaNeural, es-ES-AlvaroNeural, es-AR-ElenaNeural
            "locutor_prompt": "Eres un locutor de radio carismático, relajado y moderno. Comenta con emoción y estilo radial algo interesante sobre la canción que acaba de sonar y su artista, saluda al oyente que la pidió y genera expectativa para el siguiente tema. Sé breve (máximo 3 o 4 oraciones).",
            "mention_user": "true",
            "trivia_mode": "true",
            "station_name": "Radio FM Glass",
            "turn_system_active": "true",
            "max_queue_per_user": "1"
        }

        for k, v in default_settings.items():
            await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

        # Auto-load persistent providers from data/providers.json or environment variables
        providers_file = DATA_DIR / "providers.json"
        if providers_file.exists():
            try:
                with open(providers_file, "r", encoding="utf-8") as pf:
                    saved_provs = json.load(pf)
                    for sp in saved_provs:
                        await db.execute("""
                            INSERT OR IGNORE INTO ai_providers (name, provider_type, api_key, model_name, priority, base_url, is_active)
                            VALUES (?, ?, ?, ?, ?, ?, 1)
                        """, (sp["name"], sp["provider_type"], sp["api_key"], sp.get("model_name", ""), sp.get("priority", 1), sp.get("base_url", "")))
            except Exception as e:
                print(f"⚠️ Error cargando providers.json: {e}")

        # Check environment variables for automatic cloud persistence
        env_mappings = [
            ("GROQ_API_KEY", "Groq Llama 3.3", "groq", "llama-3.3-70b-versatile", 1, "https://api.groq.com/openai/v1"),
            ("GEMINI_API_KEY", "Google Gemini Flash", "gemini", "gemini-2.0-flash", 2, ""),
            ("CEREBRAS_API_KEY", "Cerebras AI", "cerebras", "llama-3.3-70b", 3, "https://api.cerebras.ai/v1"),
            ("OPENROUTER_API_KEY", "OpenRouter Free", "openrouter", "meta-llama/llama-3.3-70b-instruct:free", 4, "https://openrouter.ai/api/v1")
        ]

        import os
        for env_var, p_name, p_type, p_model, p_prio, p_url in env_mappings:
            val = os.getenv(env_var, "").strip()
            if val:
                async with db.execute("SELECT id FROM ai_providers WHERE provider_type = ?", (p_type,)) as cur:
                    exists = await cur.fetchone()
                if not exists:
                    await db.execute("""
                        INSERT INTO ai_providers (name, provider_type, api_key, model_name, priority, base_url, is_active)
                        VALUES (?, ?, ?, ?, ?, ?, 1)
                    """, (p_name, p_type, val, p_model, p_prio, p_url))

        await db.commit()

async def get_setting(key: str, default: str = "") -> str:
    async with get_db() as db:
        async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            return row["value"] if row else default

async def set_setting(key: str, value: str):
    async with get_db() as db:
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
        await db.commit()

async def get_all_settings():
    async with get_db() as db:
        async with db.execute("SELECT key, value FROM settings") as cursor:
            rows = await cursor.fetchall()
            return {row["key"]: row["value"] for row in rows}

# Queue helpers
async def add_to_queue(title: str, artist: str, youtube_url: str, requester_username: str, requester_name: str, requester_chat_id: str):
    async with get_db() as db:
        # Determine next position
        async with db.execute("SELECT COALESCE(MAX(position), 0) + 1 AS next_pos FROM queue WHERE status IN ('queued', 'downloading', 'ready')") as cursor:
            row = await cursor.fetchone()
            next_pos = row["next_pos"]

        async with db.execute("""
            INSERT INTO queue (title, artist, youtube_url, requester_username, requester_name, requester_chat_id, position, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'queued')
        """, (title, artist, youtube_url, requester_username, requester_name, str(requester_chat_id), next_pos)) as cursor:
            track_id = cursor.lastrowid
        await db.commit()
        return track_id

async def count_user_active_requests(chat_id: str) -> int:
    async with get_db() as db:
        async with db.execute("SELECT COUNT(*) as c FROM queue WHERE requester_chat_id = ? AND status IN ('queued', 'downloading', 'ready', 'playing')", (str(chat_id),)) as cursor:
            row = await cursor.fetchone()
            return row["c"] if row else 0

async def get_pending_queue():
    async with get_db() as db:
        async with db.execute("""
            SELECT * FROM queue 
            WHERE status IN ('queued', 'downloading', 'ready') 
            ORDER BY position ASC, id ASC
        """) as cursor:
            return [dict(r) for r in await cursor.fetchall()]

async def get_current_playing():
    async with get_db() as db:
        async with db.execute("SELECT * FROM queue WHERE status = 'playing' ORDER BY id DESC LIMIT 1") as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def update_track_status(track_id: int, status: str, file_path: str = None, duration: int = None):
    async with get_db() as db:
        updates = ["status = ?"]
        params = [status]
        if file_path:
            updates.append("file_path = ?")
            params.append(file_path)
        if duration is not None:
            updates.append("duration = ?")
            params.append(duration)
        if status == 'playing':
            updates.append("played_at = CURRENT_TIMESTAMP")
        
        params.append(track_id)
        await db.execute(f"UPDATE queue SET {', '.join(updates)} WHERE id = ?", params)
        await db.commit()

async def delete_queue_item(track_id: int):
    async with get_db() as db:
        await db.execute("DELETE FROM queue WHERE id = ?", (track_id,))
        await db.commit()

async def _sync_providers_file():
    """Keeps data/providers.json updated so configurations persist across restarts."""
    try:
        async with get_db() as db:
            async with db.execute("SELECT name, provider_type, api_key, model_name, priority, base_url, is_active FROM ai_providers") as cursor:
                rows = [dict(r) for r in await cursor.fetchall()]
        providers_file = DATA_DIR / "providers.json"
        with open(providers_file, "w", encoding="utf-8") as pf:
            json.dump(rows, pf, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"⚠️ Error sincronizando providers.json: {e}")

# Provider helpers
async def get_active_providers():
    async with get_db() as db:
        async with db.execute("SELECT * FROM ai_providers WHERE is_active = 1 ORDER BY priority ASC, id ASC") as cursor:
            return [dict(r) for r in await cursor.fetchall()]

async def save_provider(name: str, provider_type: str, api_key: str, model_name: str, priority: int = 1, base_url: str = ""):
    async with get_db() as db:
        await db.execute("""
            INSERT INTO ai_providers (name, provider_type, api_key, model_name, priority, base_url, is_active)
            VALUES (?, ?, ?, ?, ?, ?, 1)
        """, (name, provider_type, api_key, model_name, priority, base_url))
        await db.commit()
    await _sync_providers_file()

async def delete_provider(provider_id: int):
    async with get_db() as db:
        await db.execute("DELETE FROM ai_providers WHERE id = ?", (provider_id,))
        await db.commit()
    await _sync_providers_file()
