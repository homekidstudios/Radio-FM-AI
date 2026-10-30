import os
from pathlib import Path
from dotenv import load_dotenv

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent
MEDIA_DIR = BASE_DIR / "media"
MUSIC_DIR = MEDIA_DIR / "music"
TTS_DIR = MEDIA_DIR / "tts"
STATION_DIR = MEDIA_DIR / "station"
DATA_DIR = BASE_DIR / "data"

for directory in [MEDIA_DIR, MUSIC_DIR, TTS_DIR, STATION_DIR, DATA_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# Load environment
ENV_PATH = BASE_DIR / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)

# Settings
DB_PATH = DATA_DIR / "radio.db"
PORT = int(os.getenv("PORT", "8000"))
HOST = os.getenv("HOST", "0.0.0.0")

# Telegram Bot
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ADMIN_USER_ID = os.getenv("ADMIN_USER_ID", "")

# Radio Branding
STATION_NAME = os.getenv("STATION_NAME", "Radio FM")
STATION_TAGLINE = os.getenv("STATION_TAGLINE", "Online Glass Station")

# Fallback Station Tone / Default Audio
FALLBACK_STREAM_URL = os.getenv("FALLBACK_STREAM_URL", "")
