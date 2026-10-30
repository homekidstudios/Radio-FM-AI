# 📻 Radio FM Glass — Sistema de Radio Online con IA y Bot de Telegram

Un sistema integral de transmisión de radio online con estética **Linux Glassmorphism**, donde los oyentes piden música a través de un **Bot de Telegram**, las canciones se transmiten en un orden estricto de turnos justos, y un **agente de voz IA (Locutor en cabina)** interviene al finalizar cada canción antes de dar paso a la siguiente.

---

## 🌟 Características Principales

* 🎨 **Diseño Linux Glassmorphism:** Interfaz moderna con paneles translúcidos (`backdrop-filter: blur`), fondo blanco/gris con ondas fluidas animadas en escala de grises y frecuencias de sonido.
* 🔄 **Ciclo Secuencial Estricto:**
  1. Suena la canción solicitada.
  2. Al terminar la pista (segundo final), **la música se detiene por completo**.
  3. El **Locutor IA entra al aire**, comenta datos curiosos del tema/artista y saluda al oyente que la pidió.
  4. Al concluir la voz de la IA, **arranca inmediatamente la siguiente canción**.
* 📱 **Bot de Telegram Interactivo:**
  - Los oyentes piden música escribiendo el nombre o enlace de YouTube (`/pedir` o mensaje directo).
  - **Sistema de turnos justos anti-saturación:** Límite configurable de 1 pedido activo por usuario a la vez para evitar que un solo oyente monopolice la radio.
  - Comandos: `/cola` (ver turnos), `/mipedido` (estado del turno propio), `/ayuda`.
* 🧠 **Soporte Multi-Proveedor de IA (Estilo FreeLLM):**
  - Conecta APIs gratuitas de **Groq** (Llama 3.3 ultra rápido), **Google AI Studio** (Gemini Flash), **Cerebras** u **OpenRouter**.
  - **Failover automático:** Si un proveedor se satura o supera límites (HTTP 429), salta sin interrupciones al proveedor de respaldo.
* 🗣️ **Voz Ultra-Realista Gratuita:** Síntesis de voz con `edge-tts` en español neutro, mexicano, argentino o español sin costo ni límites de cuotas.
* 🛠️ **Panel de Administración Dedicado (`/admin`):**
  - Estadísticas en tiempo real (oyentes conectados, canciones emitidas, pedidos en cola).
  - Gestión visual de la cola (saltar canción, eliminar turnos, añadir canciones manualmente).
  - Configuración del locutor (nombre, voz, personalidad/prompt y botón para probar la voz en vivo).
  - Gestión de APIs y claves sin necesidad de reiniciar el servidor.

---

## 🗂️ Estructura del Proyecto

```
Proyecto de Gestion y Radio IA/
├── backend/
│   ├── main.py                # Servidor FastAPI, WebSocket y streaming
│   ├── config.py              # Variables de entorno y rutas
│   ├── database.py            # Base de datos SQLite (cola, turnos, logs, APIs)
│   ├── radio/
│   │   ├── player_engine.py   # Motor de emisión y secuencia (Canción -> Voz IA -> Canción)
│   │   ├── downloader.py      # Búsqueda y descarga con yt-dlp
│   │   └── locutor.py         # Generación del guion con failover + síntesis Edge-TTS
│   ├── telegram_bot/
│   │   └── bot.py             # Bot de Telegram con cola de turnos justos
│   └── admin/
│       └── routes.py          # Endpoints REST para el panel de administración
├── frontend/
│   ├── radio/                 # Web pública de la radio (oyentes)
│   │   ├── index.html         # Reproductor Glassmorphism
│   │   ├── style.css          # Estilos translúcidos y animaciones
│   │   └── app.js             # WebSocket y sincronización en tiempo real
│   └── admin/                 # Panel de control (administrador)
│       ├── index.html         # Dashboard administrativo
│       ├── style.css          # Estilos del panel
│       └── admin.js           # Lógica y gestión de APIs/turnos
├── media/                     # Directorio de audio generado (música y voces TTS)
├── start.sh                   # Script de arranque en 1 solo paso
├── requirements.txt           # Dependencias Python
└── .env.example               # Plantilla de variables de entorno
```

---

## 🚀 Puesta en Marcha Rápida (Local)

### 1. Requisitos previos
* Linux / macOS / Windows (WSL)
* Python 3.10+
* `ffmpeg` instalado en tu sistema (`sudo apt install ffmpeg` en Ubuntu/Debian)

### 2. Ejecutar la radio
En tu terminal, ejecuta:
```bash
./start.sh
```

Abre en tu navegador:
* 📻 **Radio Web:** [http://localhost:8000](http://localhost:8000)
* 🎛️ **Panel Admin:** [http://localhost:8000/admin](http://localhost:8000/admin)

---

## 📱 Configurar el Bot de Telegram (en 2 minutos)

1. Abre Telegram y busca **`@BotFather`**.
2. Envía `/newbot`, escribe el nombre que desees para tu radio y un username que termine en `bot`.
3. BotFather te responderá con tu **Token** (ej: `7123456789:AAHxxxxxxxx...`).
4. Abre el archivo `.env` en la raíz del proyecto y colócalo:
   ```env
   TELEGRAM_BOT_TOKEN="tu_token_aqui"
   ```
5. Al reiniciar `./start.sh`, el bot se conectará automáticamente.

---

## 🧠 Configurar las APIs de IA Gratuitas

Puedes agregar tus claves gratuitas directamente desde el **Panel Admin** (`/admin` -> pestaña **APIs FreeLLM**) sin tocar archivos de configuración:
1. **Groq (Recomendado):** Regístrate gratis en [console.groq.com](https://console.groq.com), genera una API Key y colócala en el panel con el modelo `llama-3.3-70b-versatile`.
2. **Google AI Studio (Gemini):** Obtén tu key en [aistudio.google.com](https://aistudio.google.com) y añádela como respaldo con el modelo `gemini-2.0-flash`.
