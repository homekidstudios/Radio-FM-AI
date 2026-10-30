#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "📻 ========================================="
echo "   INICIANDO RADIO FM GLASS + LOCUTOR IA   "
echo "========================================="

if [ ! -d "venv" ]; then
    echo "⚙️ Creando entorno virtual Python..."
    python3 -m venv venv
    ./venv/bin/pip install -r requirements.txt
fi

if [ ! -f ".env" ]; then
    echo "ℹ️ Creando archivo .env a partir de .env.example..."
    cp .env.example .env
fi

echo "🚀 Iniciando servidor FastAPI y motor de radio..."
echo "🌐 Página de la Radio: http://localhost:8000"
echo "🛠️ Panel de Control:   http://localhost:8000/admin"
echo "========================================="

exec ./venv/bin/python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
