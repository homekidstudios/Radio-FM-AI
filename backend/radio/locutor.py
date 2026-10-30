import asyncio
import os
import random
import time
import httpx
import edge_tts
from backend.config import TTS_DIR, ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID
from backend.database import get_active_providers, get_all_settings, get_db

FALLBACK_SCRIPTS = [
    "¡Qué buen tema acabamos de escuchar en Radio FM Glass! Gracias a todos los que están conectados en la sintonía. Ya viene la siguiente canción.",
    "¡Seguimos con buena música en el aire! Recuerda que puedes pedir tu canción favorita directamente por nuestro bot de Telegram. ¡Continuamos!",
    "¡Tremendo temazo! En cabina seguimos recibiendo sus pedidos. A continuación, prepárense para lo que viene en la lista.",
    "¡Música sin parar aquí en Radio FM! Gracias a nuestra comunidad por armar la mejor programación. ¡Vamos con el siguiente turno!"
]

async def call_groq_or_openai_compatible(api_key: str, model_name: str, prompt: str, base_url: str = "https://api.groq.com/openai/v1"):
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": "Eres un locutor de radio en vivo profesional y carismático. Responde con naturalidad, en 2 a 4 oraciones cortas, listas para ser leídas al aire en español latino."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 200
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        res = await client.post(url, headers=headers, json=payload)
        res.raise_for_status()
        data = res.json()
        return data["choices"][0]["message"]["content"].strip()

async def call_gemini(api_key: str, model_name: str, prompt: str):
    # Google AI Studio Gemini generateContent API
    model = model_name if model_name else "gemini-3.8-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [{
            "parts": [{"text": f"Actúa como un locutor de radio ameno y dinámico. Genera un comentario breve para decir al aire (máximo 3 oraciones, sin asteriscos ni acotaciones):\n{prompt}"}]
        }]
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        res = await client.post(url, json=payload)
        res.raise_for_status()
        data = res.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        return text

async def generate_commentary_script(finished_track: dict, next_track: dict = None) -> tuple[str, str]:
    """Generates the DJ script with automatic failover across configured AI providers."""
    settings = await get_all_settings()
    locutor_name = settings.get("locutor_name", "DJ Neon")
    custom_prompt = settings.get("locutor_prompt", "")
    mention_user = settings.get("mention_user", "true") == "true"

    title = finished_track.get("title", "Canción")
    artist = finished_track.get("artist", "Artista")
    requester = finished_track.get("requester_name", "un oyente") if mention_user else "nuestra audiencia"

    next_info = ""
    if next_track:
        next_info = f" y luego anunciaremos '{next_track.get('title')}' de {next_track.get('artist')}"

    user_prompt = (
        f"Tu nombre artístico es {locutor_name}. "
        f"Acaba de terminar de sonar la canción '{title}' de {artist}, pedida por {requester}. "
        f"{custom_prompt}. "
        f"Haz una intervención radial amena, da algún dato breve o saludo{next_info}. "
        f"Máximo 3 oraciones breves para leer de corrido."
    )

    providers = await get_active_providers()
    provider_used = "Fallback"

    for prov in providers:
        try:
            p_type = prov["provider_type"].lower()
            key = prov["api_key"]
            model = prov["model_name"]
            base_url = prov.get("base_url")

            if p_type == "groq":
                text = await call_groq_or_openai_compatible(key, model or "qwen/qwen3.8-27b", user_prompt, base_url or "https://api.groq.com/openai/v1")
                return text, f"Groq ({model})"
            elif p_type == "gemini":
                text = await call_gemini(key, model or "gemini-3.8-flash", user_prompt)
                return text, f"Gemini ({model})"
            elif p_type in ("cerebras", "openrouter", "custom"):
                default_url = "https://api.cerebras.ai/v1" if p_type == "cerebras" else "https://openrouter.ai/api/v1"
                text = await call_groq_or_openai_compatible(key, model, user_prompt, base_url or default_url)
                return text, f"{prov['name']} ({model})"
        except Exception as e:
            print(f"⚠️ Provider {prov.get('name')} falló ({e}). Probando siguiente respaldo...")
            continue

    # If no provider worked, use clean fallback
    fallback = random.choice(FALLBACK_SCRIPTS)
    if mention_user and finished_track.get("requester_name"):
        fallback = f"¡Un saludo especial para {finished_track['requester_name']} que nos pidió '{title}'! " + fallback
    return fallback, provider_used

async def synthesize_elevenlabs(text: str, voice_id: str, filepath: str) -> bool:
    """Generates audio using ElevenLabs API."""
    settings = await get_all_settings()
    api_key = settings.get("elevenlabs_api_key", ELEVENLABS_API_KEY)
    v_id = voice_id or settings.get("elevenlabs_voice_id", ELEVENLABS_VOICE_ID)

    if not api_key:
        return False

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{v_id}"
    headers = {"xi-api-key": api_key, "Content-Type": "application/json"}
    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}
    }
    async with httpx.AsyncClient(timeout=25.0) as client:
        res = await client.post(url, headers=headers, json=payload)
        if res.status_code == 200:
            with open(filepath, "wb") as f:
                f.write(res.content)
            return True
        else:
            print(f"⚠️ ElevenLabs error {res.status_code}: {res.text}")
            return False

async def synthesize_voice(text: str, voice: str = "elevenlabs:IKne3meq5aSn9XLyUdCD") -> str:
    """Uses ElevenLabs as primary ultra-realistic voice with automatic Edge-TTS / gTTS fallbacks."""
    filename = f"locutor_{int(time.time())}_{random.randint(100, 999)}.mp3"
    filepath = str(TTS_DIR / filename)

    # 1. Try ElevenLabs
    if voice.startswith("elevenlabs:") or (ELEVENLABS_API_KEY and not voice.startswith("edge:")):
        voice_id = voice.split(":")[-1] if ":" in voice else ELEVENLABS_VOICE_ID
        try:
            ok = await synthesize_elevenlabs(text, voice_id, filepath)
            if ok:
                return filepath
        except Exception as e:
            print(f"⚠️ Error en ElevenLabs ({e}), saltando a Edge-TTS...")

    # 2. Try Edge-TTS (Fallback)
    edge_voice = "es-ES-AlvaroNeural" if not voice.startswith("edge:") else voice.split(":")[-1]
    try:
        communicate = edge_tts.Communicate(text, edge_voice)
        await communicate.save(filepath)
        return filepath
    except Exception as e:
        print(f"⚠️ Edge-TTS falló ({e}), utilizando gTTS de respaldo...")

    # 3. Try gTTS (Final fallback)
    from gtts import gTTS
    def _gtts_run():
        tts = gTTS(text=text, lang="es", slow=False)
        tts.save(filepath)
    await asyncio.to_thread(_gtts_run)
    return filepath

async def produce_locutor_intervention(finished_track: dict, next_track: dict = None) -> dict:
    """Full pipeline: generates script + converts to voice mp3 + logs to DB"""
    settings = await get_all_settings()
    voice = settings.get("locutor_voice", "es-ES-AlvaroNeural")

    script_text, provider = await generate_commentary_script(finished_track, next_track)
    audio_file = await synthesize_voice(script_text, voice)

    # Save log to database
    try:
        async with get_db() as db:
            await db.execute("""
                INSERT INTO locutor_logs (track_id, comment_text, voice_file, provider_used)
                VALUES (?, ?, ?, ?)
            """, (finished_track.get("id"), script_text, audio_file, provider))
            await db.commit()
    except Exception as e:
        print(f"Error logging locutor: {e}")

    return {
        "text": script_text,
        "audio_file": audio_file,
        "provider": provider
    }
