from pathlib import Path
import asyncio
import os
import re
import yt_dlp
from backend.config import MUSIC_DIR, BASE_DIR

def sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()

def get_base_ydl_opts():
    opts = {
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'match_filter': yt_dlp.utils.match_filter_func("!is_live & duration < 900"),
    }
    
    # 1. Verificar cookies en diferentes ubicaciones
    cookie_local = BASE_DIR / "cookies.txt"
    cookie_render_secret = Path("/etc/secrets/cookies.txt")
    
    found_cookie = None
    if cookie_render_secret.exists():
        found_cookie = cookie_render_secret
    elif cookie_local.exists():
        found_cookie = cookie_local
    elif os.getenv("YOUTUBE_COOKIES"):
        try:
            with open(cookie_local, "w", encoding="utf-8") as f:
                f.write(os.getenv("YOUTUBE_COOKIES"))
            found_cookie = cookie_local
        except Exception:
            pass

    if found_cookie:
        opts['cookiefile'] = str(found_cookie)
        # Con cookies de sesión web, permitir web y clientes compatibles
        opts['extractor_args'] = {
            'youtube': {
                'player_client': ['web', 'tv_embedded', 'android']
            }
        }
    else:
        # Sin cookies, intentar clientes móviles
        opts['extractor_args'] = {
            'youtube': {
                'player_client': ['android', 'ios', 'tv_embedded']
            }
        }

    return opts

def _extract_and_download_sync(query: str, track_id: int):
    out_tmpl = str(MUSIC_DIR / f"{track_id}_%(id)s.%(ext)s")
    
    ydl_opts = get_base_ydl_opts()
    ydl_opts.update({
        'format': 'bestaudio/best',
        'default_search': 'ytsearch1',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'outtmpl': out_tmpl,
    })

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
    ydl_opts = get_base_ydl_opts()
    ydl_opts.update({
        'default_search': 'ytsearch1',
        'skip_download': True,
    })
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
