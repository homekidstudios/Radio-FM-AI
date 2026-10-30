#!/bin/bash
echo "=========================================="
echo "    INICIANDO RADIO FM GLASS IA (LOCAL)   "
echo "=========================================="

cd "$(dirname "$0")"

# Activar entorno virtual
source venv/bin/activate

# Iniciar servidor FastAPI y el motor de radio
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
