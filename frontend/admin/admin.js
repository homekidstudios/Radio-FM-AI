// ====== CANVAS BACKGROUND WAVES ======
const canvas = document.getElementById('waveCanvas');
const ctx = canvas.getContext('2d');
let w, h, t = 0;

function resize() {
  w = canvas.width = window.innerWidth;
  h = canvas.height = window.innerHeight;
}
resize();
window.addEventListener('resize', resize);

function loop() {
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = '#f4f5f8';
  ctx.fillRect(0, 0, w, h);

  for (let i = 0; i < 4; i++) {
    const yBase = h * 0.35 + (i * 90);
    ctx.beginPath();
    ctx.moveTo(0, h);
    ctx.lineTo(0, yBase);

    for (let x = 0; x <= w; x += 3) {
      const y = yBase + Math.sin(x * 0.0025 + t * 0.01 + i) * (20 + i * 8) + Math.cos(x * 0.005 - t * 0.008) * 10;
      ctx.lineTo(x, y);
    }
    ctx.lineTo(w, h);
    ctx.closePath();

    ctx.fillStyle = (i % 2 === 0) ? 'rgba(15, 23, 42, 0.025)' : 'rgba(255, 255, 255, 0.4)';
    ctx.fill();
  }

  t++;
  requestAnimationFrame(loop);
}
loop();

// ====== TAB SWITCHER ======
function switchTab(tabId, el) {
  document.querySelectorAll('.tab-content').forEach(tc => tc.classList.remove('active'));
  document.querySelectorAll('.nav-btn').forEach(btn => btn.classList.remove('active'));
  
  const target = document.getElementById(`tab-${tabId}`);
  if (target) target.classList.add('active');
  if (el) el.classList.add('active');

  if (tabId === 'queue') loadQueue();
  if (tabId === 'providers') loadProviders();
  if (tabId === 'locutor') loadSettings();
  if (tabId === 'settings') loadSettings();
}

// ====== DASHBOARD & STATS ======
async function loadStats() {
  try {
    const res = await fetch('/api/stats');
    const data = await res.json();

    document.getElementById('statListeners').textContent = data.listeners || 0;
    document.getElementById('statPlayed').textContent = data.played_today || 0;
    document.getElementById('statQueue').textContent = data.queue_count || 0;
    document.getElementById('statProviders').textContent = data.active_providers_count || 0;

    const state = data.current_state;
    if (state) {
      const npTitle = document.getElementById('npTitle');
      const npSub = document.getElementById('npSub');

      if (state.status === 'playing_music' && state.track) {
        npTitle.textContent = `▶ ${state.track.title} — ${state.track.artist || ''}`;
        npSub.textContent = `Pedida por: ${state.track.requester_username ? '@' + state.track.requester_username : state.track.requester_name || 'Anónimo'}`;
      } else if (state.status === 'locutor_speaking') {
        npTitle.textContent = `🎙️ DJ Neon hablando al aire`;
        npSub.textContent = state.locutor_text || 'Comentario de voz en curso';
      } else {
        npTitle.textContent = `⏸️ Radio en espera de pedidos`;
        npSub.textContent = `Sin canciones en la cola`;
      }
    }
  } catch (e) {
    console.warn("Error cargando stats:", e);
  }
}

async function skipSong() {
  if (!confirm("¿Deseas saltar la pista actual?")) return;
  try {
    const res = await fetch('/api/queue/skip', { method: 'POST' });
    const data = await res.json();
    alert(data.message || "Saltado");
    loadStats();
    loadQueue();
  } catch (e) {
    alert("Error al saltar: " + e);
  }
}

async function addManualSong() {
  const input = document.getElementById('manualSongInput');
  const query = input.value.trim();
  if (!query) return;

  try {
    const res = await fetch('/api/queue/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query })
    });
    const data = await res.json();
    if (data.success) {
      alert(`✅ Canción encolada: ${data.title}`);
      input.value = '';
      loadStats();
      loadQueue();
    } else {
      alert("Error: " + data.detail);
    }
  } catch (e) {
    alert("Error conectando con API: " + e);
  }
}

// ====== QUEUE MANAGEMENT ======
async function loadQueue() {
  try {
    const res = await fetch('/api/queue');
    const data = await res.json();
    const tbody = document.getElementById('queueTableBody');

    const pending = data.pending || [];
    if (pending.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; padding:20px; color:#888;">No hay canciones en cola</td></tr>`;
      return;
    }

    tbody.innerHTML = pending.map((item, idx) => `
      <tr>
        <td><strong>#${idx + 1}</strong></td>
        <td>
          <div style="font-weight:600;">${escapeHtml(item.title)}</div>
          <div style="font-size:12px; color:#777;">${escapeHtml(item.artist || 'Desconocido')}</div>
        </td>
        <td><span class="user-tag">${escapeHtml(item.requester_username ? '@' + item.requester_username : item.requester_name)}</span></td>
        <td><span style="font-size:11px; font-weight:700; color:#555;">${item.status.toUpperCase()}</span></td>
        <td>
          <button class="btn-action" style="padding:4px 8px; font-size:11px; color:#c00;" onclick="deleteTrack(${item.id})">Eliminar</button>
        </td>
      </tr>
    `).join('');
  } catch (e) {
    console.warn("Error cargando cola:", e);
  }
}

async function deleteTrack(trackId) {
  if (!confirm("¿Eliminar este tema de la lista?")) return;
  try {
    await fetch(`/api/queue/${trackId}`, { method: 'DELETE' });
    loadQueue();
    loadStats();
  } catch (e) {
    alert("Error eliminando: " + e);
  }
}

// ====== PROVIDERS MANAGEMENT ======
function onProviderTypeChange() {
  const type = document.getElementById('newProvType').value;
  const modelInput = document.getElementById('newProvModel');
  const nameInput = document.getElementById('newProvName');
  if (type === 'groq') {
    modelInput.value = 'llama-3.3-70b-versatile';
    nameInput.value = 'Groq Llama 3.3';
  } else if (type === 'gemini') {
    modelInput.value = 'gemini-2.0-flash';
    nameInput.value = 'Google Gemini Flash';
  } else if (type === 'cerebras') {
    modelInput.value = 'llama-3.3-70b';
    nameInput.value = 'Cerebras AI';
  } else if (type === 'openrouter') {
    modelInput.value = 'meta-llama/llama-3.3-70b-instruct:free';
    nameInput.value = 'OpenRouter Free';
  }
}

async function loadProviders() {
  try {
    const res = await fetch('/api/providers');
    const list = await res.json();
    const container = document.getElementById('providersList');

    if (list.length === 0) {
      container.innerHTML = `<div style="padding:16px; color:#888; text-align:center;">No hay APIs configuradas. El sistema utilizará respuestas radiales predefinidas.</div>`;
      return;
    }

    container.innerHTML = list.map((p, idx) => `
      <div class="provider-item" style="border: 1px solid rgba(0,0,0,0.08); padding: 16px 20px;">
        <div>
          <div style="font-weight:700; font-size:15px; display:flex; align-items:center; gap:8px;">
            ${escapeHtml(p.name)} 
            <span style="font-weight:500; font-size:12px; color:#666; background:rgba(0,0,0,0.05); padding:2px 8px; border-radius:4px;">${p.model_name}</span>
          </div>
          <div style="font-size:12px; color:#888; margin-top:4px;">Prioridad #${idx + 1} · Proveedor: <strong>${p.provider_type.toUpperCase()}</strong></div>
        </div>
        <div style="display:flex; align-items:center; gap:12px;">
          <span class="prov-badge">${p.is_active ? '● ACTIVO' : 'PAUSADO'}</span>
          <button class="btn-action" style="padding:6px 12px; font-size:12px; background:#ffeef0; color:#cf222e; border:1px solid rgba(207,34,46,0.2);" onclick="removeProvider(${p.id})">🗑️ Eliminar</button>
        </div>
      </div>
    `).join('');
  } catch (e) {
    console.warn("Error cargando proveedores:", e);
  }
}

async function addProvider() {
  const name = document.getElementById('newProvName').value.trim();
  const provider_type = document.getElementById('newProvType').value;
  const api_key = document.getElementById('newProvKey').value.trim();
  const model_name = document.getElementById('newProvModel').value.trim();

  if (!name || !api_key) {
    alert("Por favor ingresa un nombre y la API Key.");
    return;
  }

  try {
    await fetch('/api/providers', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, provider_type, api_key, model_name, priority: 1 })
    });
    alert("✅ Proveedor guardado con éxito.");
    document.getElementById('newProvName').value = '';
    document.getElementById('newProvKey').value = '';
    loadProviders();
    loadStats();
  } catch (e) {
    alert("Error guardando proveedor: " + e);
  }
}

async function removeProvider(id) {
  if (!confirm("¿Eliminar este proveedor de IA?")) return;
  try {
    await fetch(`/api/providers/${id}`, { method: 'DELETE' });
    loadProviders();
    loadStats();
  } catch (e) {
    alert("Error eliminando proveedor: " + e);
  }
}

// ====== SETTINGS & LOCUTOR ======
async function loadSettings() {
  try {
    const res = await fetch('/api/settings');
    const settings = await res.json();

    if (settings.locutor_name) document.getElementById('cfgLocutorName').value = settings.locutor_name;
    if (settings.locutor_voice) document.getElementById('cfgLocutorVoice').value = settings.locutor_voice;
    if (settings.locutor_prompt) document.getElementById('cfgLocutorPrompt').value = settings.locutor_prompt;
    if (settings.station_name) document.getElementById('cfgStationName').value = settings.station_name;
    if (settings.max_queue_per_user) document.getElementById('cfgMaxQueue').value = settings.max_queue_per_user;
  } catch (e) {
    console.warn("Error cargando ajustes:", e);
  }
}

async function saveLocutorSettings() {
  const locutor_name = document.getElementById('cfgLocutorName').value;
  const locutor_voice = document.getElementById('cfgLocutorVoice').value;
  const locutor_prompt = document.getElementById('cfgLocutorPrompt').value;

  try {
    await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        settings: { locutor_name, locutor_voice, locutor_prompt }
      })
    });
    alert("✅ Ajustes del Locutor IA guardados.");
  } catch (e) {
    alert("Error guardando: " + e);
  }
}

async function saveGeneralSettings() {
  const station_name = document.getElementById('cfgStationName').value;
  const max_queue_per_user = document.getElementById('cfgMaxQueue').value;

  try {
    await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        settings: { station_name, max_queue_per_user }
      })
    });
    alert("✅ Ajustes de la estación guardados.");
  } catch (e) {
    alert("Error guardando: " + e);
  }
}

async function testVoice() {
  const text = document.getElementById('testVoiceInput').value.trim();
  const voice = document.getElementById('cfgLocutorVoice').value;
  if (!text) return;

  try {
    const res = await fetch('/api/locutor/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, voice })
    });
    const data = await res.json();
    if (data.audio_url) {
      const player = document.getElementById('testAudioPlayer');
      player.src = data.audio_url;
      player.style.display = 'block';
      player.play();
    }
  } catch (e) {
    alert("Error probando voz: " + e);
  }
}

function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// Initial load
loadStats();
setInterval(loadStats, 5000);
