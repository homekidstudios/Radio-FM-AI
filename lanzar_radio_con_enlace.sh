#!/bin/bash
# ==============================================================
# LANZADOR AUTOMÁTICO DE RADIO FM GLASS IA + ENLACE PÚBLICO
# ==============================================================

cd "$(dirname "$0")"

echo "=========================================================="
echo "          INICIANDO RADIO FM GLASS IA (MODO ONLINE)       "
echo "=========================================================="

# Activar entorno virtual
source venv/bin/activate

# Matar procesos previos en puerto 8000 si existieran
fuser -k 8000/tcp 2>/dev/null

# 1. Iniciar servidor FastAPI y Telegram Bot en segundo plano
echo "1. Encendiendo Servidor de Radio y Bot de Telegram..."
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 > radio_server.log 2>&1 &
SERVER_PID=$!

sleep 3

# Verificar si el servidor levantó
if ! ps -p $SERVER_PID > /dev/null; then
    echo "❌ Error iniciando el servidor. Revisa radio_server.log"
    exit 1
fi

echo "✅ Servidor y Bot funcionando correctamente en local."
echo ""
echo "2. Generando enlace público mundial con Cloudflare..."

# Limpiar log previo
rm -f tunnel.log

# 2. Iniciar Cloudflare Tunnel
./cloudflared tunnel --url http://localhost:8000 > tunnel.log 2>&1 &
TUNNEL_PID=$!

# Esperar a que Cloudflare asigne la URL pública
TUNNEL_URL=""
for i in {1..30}; do
    sleep 1
    TUNNEL_URL=$(grep -o 'https://[-a-zA-Z0-9@:%._\+~#=]*\.trycloudflare\.com' tunnel.log | head -n 1)
    if [ -n "$TUNNEL_URL" ]; then
        break
    fi
done

echo ""
echo "=========================================================="
if [ -n "$TUNNEL_URL" ]; then
    echo "🎉 ¡TU RADIO YA ESTÁ EN VIVO PARA TODO EL MUNDO!"
    echo "=========================================================="
    echo ""
    echo "📻 Enlace del Reproductor Web:"
    echo "   $TUNNEL_URL"
    echo ""
    echo "⚙️ Enlace del Panel de Control (Admin):"
    echo "   $TUNNEL_URL/admin/"
    echo ""
    echo "🤖 Bot de Telegram activo:"
    echo "   https://t.me/UniRFMbot"
    echo ""
    echo "=========================================================="
    echo "Consejo: Comparte el enlace de la radio con tus amigos."
    echo "Para detener la radio, presiona CTRL + C en esta ventana."
    echo "=========================================================="
else
    echo "⚠️ No se pudo obtener la URL de Cloudflare automáticamente."
    echo "Puedes ver el log en 'tunnel.log' o entrar en local a: http://localhost:8000"
fi

# Mantener el script en ejecución y atrapar CTRL+C para limpiar procesos
trap "echo 'Apagando radio...'; kill $SERVER_PID $TUNNEL_PID 2>/dev/null; exit 0" INT TERM
wait $SERVER_PID
