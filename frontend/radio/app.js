// ====== CANVAS BACKGROUND WAVES ======
const canvas = document.getElementById('waveBg');
const ctx = canvas.getContext('2d');
let w, h, t = 0;

function resizeCanvas() {
  w = canvas.width = window.innerWidth;
  h = canvas.height = window.innerHeight;
}
resizeCanvas();
window.addEventListener('resize', resizeCanvas);

function drawWaves() {
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = '#f4f5f8';
  ctx.fillRect(0, 0, w, h);

  const waveCount = 5;
  for (let i = 0; i < waveCount; i++) {
    const baseY = h * 0.28 + (i * h * 0.12);
    const amp = 20 + i * 8;
    const freq = 0.0025 + i * 0.0006;
    const speed = 0.008 + i * 0.002;
    const alpha = 0.03 + (i * 0.015);

    ctx.beginPath();
    ctx.moveTo(0, h);
    ctx.lineTo(0, baseY);

    for (let x = 0; x <= w; x += 3) {
      const y = baseY +
        Math.sin(x * freq + t * speed) * amp +
        Math.sin(x * freq * 2.2 + t * speed * 1.4) * (amp * 0.4);
      ctx.lineTo(x, y);
    }

    ctx.lineTo(w, h);
    ctx.closePath();

    ctx.fillStyle = (i % 2 === 0) ? `rgba(20, 20, 20, ${alpha})` : `rgba(255, 255, 255, ${alpha * 2.2})`;
    ctx.fill();
  }

  t++;
  requestAnimationFrame(drawWaves);
}
drawWaves();

// ====== FREQUENCY BARS VISUALIZER ======
const waveBarsContainer = document.getElementById('waveBarsContainer');
for (let i = 0; i < 50; i++) {
  const bar = document.createElement('div');
  bar.className = 'w-bar';
  const center = Math.abs(i - 25) / 25;
  const h1 = 4 + (1 - center) * 6;
  const h2 = 8 + (1 - center) * 36 + Math.random() * 12;
  const h3 = 4 + (1 - center) * 10;
  const spd = 0.35 + Math.random() * 0.5;
  const del = (i * 0.02) + Math.random() * 0.2;

  bar.style.setProperty('--h1', h1 + 'px');
  bar.style.setProperty('--h2', h2 + 'px');
  bar.style.setProperty('--h3', h3 + 'px');
  bar.style.setProperty('--spd', spd + 's');
  bar.style.setProperty('--del', del + 's');
  waveBarsContainer.appendChild(bar);
}

// ====== AUDIO PLAYBACK CONTINUO (SIN PAUSA PARA OYENTES) ======
const audio = document.getElementById('radioAudio');
let isAudioActive = false;

function startAudioImmediate() {
  if (!audio) return;
  audio.volume = parseFloat(document.getElementById('volSlider')?.value || 0.8);

  if (!audio.src || audio.src === '' || audio.src.endsWith('/')) {
    audio.src = '/api/stream?t=' + Date.now();
  }

  const p = audio.play();
  if (p !== undefined) {
    p.then(() => {
      isAudioActive = true;
      document.body.classList.add('audio-playing');
      const banner = document.getElementById('tapToListen');
      if (banner) banner.style.display = 'none';
    }).catch(() => {
      // Si el navegador bloquea autoplay en frío, mostrar aviso amigable
      const banner = document.getElementById('tapToListen');
      if (banner) banner.style.display = 'flex';
    });
  }
}

if (audio) {
  audio.volume = 0.8;

  audio.addEventListener('playing', () => {
    isAudioActive = true;
    document.body.classList.add('audio-playing');
    const banner = document.getElementById('tapToListen');
    if (banner) banner.style.display = 'none';
  });

  audio.addEventListener('error', (e) => {
    console.warn("Reconectando audio stream...", e);
    setTimeout(() => {
      if (audio) {
        audio.src = '/api/stream?t=' + Date.now();
        audio.play().catch(() => {});
      }
    }, 2000);
  });
}

// Activar audio automáticamente al cargar
window.addEventListener('DOMContentLoaded', () => {
  startAudioImmediate();
});

// Cualquier toque o interacción en la pantalla asegura que el audio empiece si el navegador lo retuvo
['click', 'touchstart', 'scroll', 'keydown'].forEach(evt => {
  document.addEventListener(evt, () => {
    if (audio && (audio.paused || !isAudioActive)) {
      startAudioImmediate();
    }
  }, { passive: true });
});

function changeVolume(val) {
  if (audio) {
    audio.volume = parseFloat(val);
  }
}

function setVolume(val) {
  const slider = document.getElementById('volSlider');
  if (slider) slider.value = val;
  changeVolume(val);
}

// ====== STATE & WEBSOCKET SYNC ======
let ws = null;
let currentDuration = 0;
let currentStartedAt = 0;
let progressTimer = null;

function connectWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws/live`;

  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    document.getElementById('liveStatusText').textContent = 'EN VIVO';
  };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.state) {
        updateRadioUI(data.state, data.listeners);
      }
    } catch (e) {
      console.error("WS error:", e);
    }
  };

  ws.onclose = () => {
    document.getElementById('liveStatusText').textContent = 'RECONECTANDO';
    setTimeout(connectWebSocket, 3000);
  };
}

function updateRadioUI(state, listeners) {
  if (listeners !== undefined) {
    document.getElementById('listenerCount').textContent = Math.max(1, listeners);
  }

  const badge = document.getElementById('streamModeBadge');
  const songTitle = document.getElementById('songTitle');
  const songArtist = document.getElementById('songArtist');
  const songReq = document.getElementById('songRequester');
  const reqUser = document.getElementById('requesterUser');
  const aiCard = document.getElementById('aiCard');
  const aiSpeakingBadge = document.getElementById('aiSpeakingBadge');
  const aiText = document.getElementById('aiCommentaryText');

  currentStartedAt = state.started_at || Date.now() / 1000;
  currentDuration = state.duration || 0;

  if (state.status === 'playing_music' && state.track) {
    badge.textContent = '▶ REPRODUCIENDO AHORA';
    badge.style.color = '#111';
    songTitle.textContent = state.track.title || 'Canción en curso';
    songArtist.textContent = state.track.artist || 'Artista';

    if (state.track.requester_name || state.track.requester_username) {
      songReq.style.display = 'inline-flex';
      reqUser.textContent = state.track.requester_username ? `@${state.track.requester_username}` : state.track.requester_name;
    } else {
      songReq.style.display = 'none';
    }

    aiCard.classList.remove('speaking');
    aiSpeakingBadge.style.display = 'none';

  } else if (state.status === 'locutor_speaking') {
    badge.textContent = '🎙️ LOCUTOR IA AL AIRE';
    badge.style.color = '#0070f3';
    songTitle.textContent = 'DJ Neon en cabina';
    songArtist.textContent = 'Comentando la canción anterior y presentando el próximo tema';
    songReq.style.display = 'none';

    aiCard.classList.add('speaking');
    aiSpeakingBadge.style.display = 'inline-block';
    if (state.locutor_text) {
      aiText.textContent = `"${state.locutor_text}"`;
    }

  } else {
    badge.textContent = '⏸️ ESTACIÓN EN ESPERA';
    songTitle.textContent = 'Esperando pedidos';
    songArtist.textContent = 'Escribe por Telegram para poner tu música favorita';
    songReq.style.display = 'none';
    aiCard.classList.remove('speaking');
    aiSpeakingBadge.style.display = 'none';
  }

  // Refresh Queue from API
  fetchQueue();
}

function updateProgress() {
  if (!currentDuration || currentDuration <= 0) {
    document.getElementById('progressBar').style.width = '0%';
    document.getElementById('timeDisplay').textContent = '0:00';
    return;
  }

  const elapsed = Math.max(0, (Date.now() / 1000) - currentStartedAt);
  const pct = Math.min(100, (elapsed / currentDuration) * 100);
  document.getElementById('progressBar').style.width = `${pct}%`;

  const m = Math.floor(elapsed / 60);
  const s = Math.floor(elapsed % 60).toString().padStart(2, '0');
  document.getElementById('timeDisplay').textContent = `${m}:${s}`;
}

async function fetchQueue() {
  try {
    const res = await fetch('/api/queue');
    const data = await res.json();
    const container = document.getElementById('queueListContainer');
    const countBadge = document.getElementById('queueCountBadge');

    const pending = data.pending || [];
    countBadge.textContent = `${pending.length} en espera`;

    if (pending.length === 0) {
      container.innerHTML = '<div class="queue-empty-msg">No hay canciones en la lista. ¡Sé el primero en pedir una!</div>';
      return;
    }

    container.innerHTML = pending.map((item, idx) => `
      <div class="queue-item">
        <div class="qi-turn">#${idx + 1}</div>
        <div class="qi-info">
          <div class="qi-title">${escapeHtml(item.title)}</div>
          <div class="qi-artist">${escapeHtml(item.artist || 'Artista')}</div>
        </div>
        <div class="qi-user">${escapeHtml(item.requester_username ? `@${item.requester_username}` : item.requester_name)}</div>
      </div>
    `).join('');

  } catch (e) {
    console.warn("Error fetching queue:", e);
  }
}

async function fetchStats() {
  try {
    const res = await fetch('/api/stats');
    const data = await res.json();
    document.getElementById('playedCount').textContent = data.played_today || 0;
  } catch (e) {
    console.warn("Error fetching stats:", e);
  }
}

function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// Start polling & timers
connectWebSocket();
setInterval(updateProgress, 500);
setInterval(fetchStats, 15000);
fetchQueue();
fetchStats();
