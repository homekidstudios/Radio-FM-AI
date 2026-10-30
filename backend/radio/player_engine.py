import asyncio
import os
import subprocess
import time
from typing import Set
from backend.config import MUSIC_DIR, TTS_DIR, STATION_DIR
from backend.database import (
    get_pending_queue, get_current_playing, update_track_status, 
    get_all_settings, get_db
)
from backend.radio.downloader import search_and_download
from backend.radio.locutor import produce_locutor_intervention

class BroadcastStream:
    """Manages audio streaming to multiple web clients simultaneously."""
    def __init__(self):
        self.listeners: Set[asyncio.Queue] = set()
        self.current_state = {
            "status": "idle", # "playing_music", "locutor_speaking", "idle"
            "track": None,
            "locutor_text": None,
            "started_at": 0,
            "duration": 0
        }

    def add_listener(self) -> asyncio.Queue:
        q = asyncio.Queue(maxsize=100)
        self.listeners.add(q)
        return q

    def remove_listener(self, q: asyncio.Queue):
        self.listeners.discard(q)

    async def broadcast_chunk(self, chunk: bytes):
        disconnected = []
        for q in self.listeners:
            try:
                if q.full():
                    try:
                        q.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                q.put_nowait(chunk)
            except Exception:
                disconnected.append(q)
        for q in disconnected:
            self.remove_listener(q)

    def get_listener_count(self) -> int:
        return len(self.listeners)

stream_hub = BroadcastStream()

class RadioEngine:
    def __init__(self):
        self.is_running = False
        self.skip_requested = False
        self.current_track = None
        self.websocket_callbacks = []

    def register_ws_notifier(self, callback):
        self.websocket_callbacks.append(callback)

    async def notify_clients(self):
        data = {
            "type": "state_update",
            "state": stream_hub.current_state,
            "listeners": stream_hub.get_listener_count()
        }
        for cb in self.websocket_callbacks:
            try:
                await cb(data)
            except Exception:
                pass

    def request_skip(self):
        self.skip_requested = True

    async def get_audio_duration(self, file_path: str) -> float:
        """Uses ffprobe to obtain exact audio duration in seconds"""
        try:
            cmd = [
                "ffprobe", "-v", "error", "-show_entries",
                "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
                file_path
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            return float(stdout.decode().strip())
        except Exception:
            return 180.0 # Default 3 mins fallback

    async def stream_audio_file(self, file_path: str):
        """Paces and streams audio file bytes into stream_hub for real-time radio broadcast"""
        # We read the file and stream at ~192kbps (24,000 bytes per second) in 0.5s chunks
        chunk_size = 12000 # 12KB
        delay = 0.5 # 500ms

        if not os.path.exists(file_path):
            await asyncio.sleep(2)
            return

        with open(file_path, "rb") as f:
            while self.is_running:
                if self.skip_requested:
                    self.skip_requested = False
                    break

                chunk = f.read(chunk_size)
                if not chunk:
                    break

                await stream_hub.broadcast_chunk(chunk)
                await asyncio.sleep(delay)

    async def start(self):
        self.is_running = True
        print("📻 Radio Engine Iniciado: Esperando canciones en la cola...")

        while self.is_running:
            # 1. Check for next queued song
            queue = await get_pending_queue()
            
            if not queue:
                stream_hub.current_state = {
                    "status": "idle",
                    "track": None,
                    "locutor_text": "Cabina en espera de canciones. ¡Pide tu tema por Telegram!",
                    "started_at": time.time(),
                    "duration": 0
                }
                await self.notify_clients()
                await asyncio.sleep(3)
                continue

            next_item = queue[0]
            track_id = next_item["id"]

            # 2. Check if downloaded, if not download now
            if next_item["status"] == "queued" or not next_item.get("file_path") or not os.path.exists(next_item.get("file_path", "")):
                await update_track_status(track_id, "downloading")
                await self.notify_clients()

                try:
                    query = next_item["youtube_url"] if next_item.get("youtube_url") else f"{next_item['title']} {next_item.get('artist', '')}"
                    dl_result = await search_and_download(query, track_id)
                    await update_track_status(
                        track_id, "ready", 
                        file_path=dl_result["file_path"], 
                        duration=int(dl_result["duration"])
                    )
                    next_item["file_path"] = dl_result["file_path"]
                    next_item["title"] = dl_result["title"]
                    next_item["artist"] = dl_result["artist"]
                except Exception as e:
                    print(f"❌ Error descargando {next_item['title']}: {e}")
                    await update_track_status(track_id, "failed")
                    await self.notify_clients()
                    continue

            # 3. PLAY THE SONG
            await update_track_status(track_id, "playing")
            self.current_track = next_item
            duration = await self.get_audio_duration(next_item["file_path"])

            stream_hub.current_state = {
                "status": "playing_music",
                "track": {
                    "id": track_id,
                    "title": next_item["title"],
                    "artist": next_item.get("artist", "Desconocido"),
                    "requester_name": next_item.get("requester_name", "Oyente"),
                    "requester_username": next_item.get("requester_username", ""),
                    "duration": duration
                },
                "locutor_text": None,
                "started_at": time.time(),
                "duration": duration
            }
            await self.notify_clients()
            print(f"▶️ Reproduciendo: {next_item['title']} (Duración: {int(duration)}s)")

            # Stream the track to listeners until end
            await self.stream_audio_file(next_item["file_path"])

            # 4. TRACK HAS FINISHED! Stop music completely.
            await update_track_status(track_id, "finished")
            print(f"⏹️ Terminó la música: {next_item['title']}")

            # Peek next song in queue if any
            upcoming_queue = await get_pending_queue()
            next_in_line = upcoming_queue[0] if upcoming_queue else None

            # 5. LOCUTOR IA SPEAKS
            print("🎙️ Entrada del Locutor IA al aire...")
            try:
                intervention = await produce_locutor_intervention(next_item, next_in_line)
                speech_duration = await self.get_audio_duration(intervention["audio_file"])

                stream_hub.current_state = {
                    "status": "locutor_speaking",
                    "track": next_item,
                    "locutor_text": intervention["text"],
                    "started_at": time.time(),
                    "duration": speech_duration
                }
                await self.notify_clients()

                # Stream the locutor voice audio
                await self.stream_audio_file(intervention["audio_file"])
                print(f"🎙️ Locutor IA finalizó comentario ({int(speech_duration)}s)")

            except Exception as e:
                print(f"⚠️ Error en locutor IA: {e}")

            # 6. Loop will now automatically proceed to the next song!

radio_engine = RadioEngine()
