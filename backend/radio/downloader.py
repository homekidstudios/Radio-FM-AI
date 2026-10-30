import asyncio
import os
import re
import yt_dlp
from backend.config import MUSIC_DIR

def sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()

def _extract_and_download_sync(query: str, track_id: int):
    out_tmpl = str(MUSIC_DIR / f"{track_id}_%(id)s.%(ext)s")
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'default_search': 'ytsearch1',
        'noplaylist': True,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'outtmpl': out_tmpl,
        'quiet': True,
        'no_warnings': True,
        'match_filter': yt_dlp.utils.match_filter_func("!is_live & duration < 900"), # Max 15 mins, no livestreams
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        # Search or direct URL
        info = ydl.extract_info(query, download=True)
        if 'entries' in info and info['entries']:
            info = info['entries'][0]

        title = info.get('title', 'Canción Desconocida')
        uploader = info.get('uploader', info.get('channel', 'Artista Desconocido'))
        duration = info.get('duration', 0)
        webpage_url = info.get('webpage_url', '')

        # Resolve final mp3 path
        raw_filename = ydl.prepare_filename(info)
        base, _ = os.path.splitext(raw_filename)
        final_mp3 = f"{base}.mp3"

        return {
            "title": title,
            "artist": uploader,
            "duration": duration,
            "youtube_url": webpage_url,
            "file_path": final_mp3
        }

async def search_and_download(query: str, track_id: int):
    """Executes yt-dlp in a background thread to prevent blocking asyncio loop"""
    return await asyncio.to_thread(_extract_and_download_sync, query, track_id)

def _quick_search_sync(query: str):
    """Performs quick metadata search without downloading"""
    ydl_opts = {
        'default_search': 'ytsearch1',
        'noplaylist': True,
        'quiet': True,
        'skip_download': True,
        'match_filter': yt_dlp.utils.match_filter_func("!is_live & duration < 900"),
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(query, download=False)
        if 'entries' in info and info['entries']:
            info = info['entries'][0]
        return {
            "title": info.get('title', 'Canción'),
            "artist": info.get('uploader', 'Artista'),
            "duration": info.get('duration', 0),
            "url": info.get('webpage_url', '')
        }

async def quick_search(query: str):
    return await asyncio.to_thread(_quick_search_sync, query)
