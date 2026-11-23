"""Pantalla inmersiva para la videollamada y para quedar en persona.

- La imagen nueva se carga por detrás y aparece con un fundido (sin pantallazos en negro).
- Mientras habla, la imagen reacciona a su voz.
- En modo 'quedada' se ve como con tus propios ojos, con viñeta y narración de lo que hace.
"""
import base64
import html
import json

import streamlit.components.v1 as components

PLANTILLA = r"""
<style>
* {box-sizing:border-box; margin:0; padding:0; font-family:-apple-system,Segoe UI,Roboto,sans-serif;}
#marco {position:relative; width:100%; height:__ALTO__px; border-radius:22px; overflow:hidden; background:#111;}
.capa {position:absolute; inset:0; width:100%; height:100%; object-fit:cover; transform-origin:50% 40%;
       animation:respira 6s ease-in-out infinite; transition:opacity 1.2s ease;}
@keyframes respira {0%,100%{transform:scale(1.03) translate(0,0)} 50%{transform:scale(1.05) translate(-2px,-3px)}}
.quedada .capa {animation:mirar 9s ease-in-out infinite;}
@keyframes mirar {0%,100%{transform:scale(1.06) translate(0,0) rotate(0)} 33%{transform:scale(1.07) translate(-6px,-2px) rotate(-.3deg)}
                  66%{transform:scale(1.065) translate(5px,-4px) rotate(.3deg)}}
#vineta {position:absolute; inset:0; pointer-events:none; display:none;
         background:radial-gradient(ellipse at center, transparent 55%, rgba(0,0,0,.55) 100%);}
.quedada #vineta {display:block;}
#aro {position:absolute; inset:0; border-radius:22px; pointer-events:none; opacity:0; transition:opacity .08s;
      box-shadow:inset 0 0 0 4px #4ade80, inset 0 0 40px rgba(74,222,128,.4);}
.quedada #aro {box-shadow:inset 0 0 80px rgba(255,220,180,.35);}
#arriba {position:absolute; top:0; left:0; right:0; padding:14px 16px; color:#fff; display:flex;
         justify-content:space-between; background:linear-gradient(rgba(0,0,0,.55),transparent); font-size:13px;}
#arriba b {font-size:16px; max-width:45%;} #arriba > span {max-width:52%; text-align:right; line-height:1.3;}
.vivo {display:inline-block; width:8px; height:8px; border-radius:50%; background:#ef4444; margin-right:6px;
       animation:parpadeo 1.4s infinite;} @keyframes parpadeo {50%{opacity:.25}}
.quedada .vivo {display:none;}
#abajo {position:absolute; left:12px; right:12px; bottom:14px; display:flex; flex-direction:column; gap:8px;}
#narra, #sub {color:#fff; padding:9px 13px; border-radius:14px; backdrop-filter:blur(6px); line-height:1.35; white-space:pre-line; max-height:45%; overflow-y:auto;}
#narra {font-style:italic; font-size:14px; background:rgba(0,0,0,.35); opacity:.95;}
#sub {font-size:16px; background:rgba(0,0,0,.55); display:__SUBS__;}
#narra:empty, #sub:empty {display:none;}
#play {position:absolute; top:45%; left:50%; transform:translate(-50%,-50%); display:none; padding:16px 26px;
       font-size:18px; border:0; border-radius:40px; color:#fff; background:rgba(34,197,94,.92); cursor:pointer;}
#cargando {position:absolute; inset:0; display:flex; align-items:center; justify-content:center; color:#fff; opacity:.8;}
</style>
<div id="marco" class="__MODO__">
  <div id="cargando">__CARGANDO__</div>
  <img id="a" class="capa" style="opacity:0">
  <img id="b" class="capa" style="opacity:0">
  <div id="vineta"></div><div id="aro"></div>
  <div id="arriba"><b>__NOMBRE__</b><span><i class="vivo"></i>__ETIQUETA__ <span id="reloj"></span></span></div>
  <div id="abajo"><div id="narra">__NARRA__</div><div id="sub">__TEXTO__</div></div>
  <button id="play">▶ Escuchar</button>
</div>
<script>
const anterior = __ANTERIOR__, nueva = __NUEVA__, modo = "__MODO__";
const A = document.getElementById('a'), B = document.getElementById('b');
function mostrar(img, url, alCargar) {
  const pre = new Image();
  pre.onload = () => { img.src = url; img.style.opacity = 1; const c = document.getElementById('cargando'); if (c) c.remove(); alCargar && alCargar(); };
  pre.src = url;
}
if (anterior && anterior !== nueva) {           // fundido de la imagen anterior a la nueva
  mostrar(A, anterior);
  mostrar(B, nueva, () => setTimeout(() => A.style.opacity = 0, 1200));
} else if (nueva) { mostrar(A, nueva); }

if (modo === 'llamada') {
  const inicio = __INICIO__ * 1000, reloj = document.getElementById('reloj');
  setInterval(() => { const s = Math.max(0, Math.floor((Date.now() - inicio) / 1000));
    reloj.textContent = String(Math.floor(s/60)).padStart(2,'0') + ':' + String(s%60).padStart(2,'0'); }, 500);
}

const audioB64 = __AUDIO__, AMBIENTE = "__AMBIENTE__", LLUVIA = __LLUVIA__;
const aro = document.getElementById('aro'), play = document.getElementById('play');
const audio = audioB64 ? new Audio('data:audio/mp3;base64,' + audioB64) : null;
let ctx, an, datos, ambienteOn = false;
const espera = ms => new Promise(r => setTimeout(r, ms));

// ---------- Sonido ambiente generado (sin archivos): bar, calle, parque, gimnasio, casa, lluvia ----------
function ambiente() {
  if (ambienteOn || !ctx || !AMBIENTE) return; ambienteOn = true;
  const master = ctx.createGain(); master.gain.value = 0; master.connect(ctx.destination);
  master.gain.linearRampToValueAtTime(1, ctx.currentTime + 2.5);
  function ruido(color) {
    const n = ctx.sampleRate * 3, b = ctx.createBuffer(1, n, ctx.sampleRate), d = b.getChannelData(0); let ult = 0;
    for (let i = 0; i < n; i++) { const w = Math.random() * 2 - 1;
      if (color === 'brown') { ult = (ult + 0.02 * w) / 1.02; d[i] = ult * 3.5; } else d[i] = w; }
    const s = ctx.createBufferSource(); s.buffer = b; s.loop = true; s.start(); return s;
  }
  function capa(color, tipo, freq, q, vol) {
    const s = ruido(color), f = ctx.createBiquadFilter(), g = ctx.createGain();
    f.type = tipo; f.frequency.value = freq; f.Q.value = q; g.gain.value = vol;
    s.connect(f); f.connect(g); g.connect(master); return g;
  }
  function ping(f0, f1, dur, vol) {
    const o = ctx.createOscillator(), g = ctx.createGain(), t = ctx.currentTime;
    o.frequency.setValueAtTime(f0, t); o.frequency.exponentialRampToValueAtTime(f1, t + dur * 0.8);
    g.gain.setValueAtTime(vol, t); g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(g); g.connect(master); o.start(t); o.stop(t + dur + 0.02);
  }
  if (AMBIENTE === 'bar') {
    const murmullo = capa('white', 'bandpass', 480, 0.7, 0.05);
    setInterval(() => murmullo.gain.setTargetAtTime(0.03 + Math.random() * 0.05, ctx.currentTime, 0.4), 800);
    setInterval(() => { if (Math.random() < 0.45) { const f = 2400 + Math.random() * 1800; ping(f, f, 0.4, 0.015); } }, 2200);
  } else if (AMBIENTE === 'calle') {
    capa('brown', 'lowpass', 350, 0.5, 0.22);
    setInterval(() => { if (Math.random() < 0.15) ping(700, 680, 0.35, 0.01); }, 4000);
  } else if (AMBIENTE === 'parque') {
    capa('white', 'highpass', 2500, 0.3, 0.006); capa('brown', 'lowpass', 200, 0.5, 0.08);
    setInterval(() => { if (Math.random() < 0.6) { const f = 3000 + Math.random() * 1500; ping(f, f * 1.5, 0.14, 0.012);
      setTimeout(() => ping(f * 1.1, f * 1.6, 0.12, 0.01), 160); } }, 1700);
  } else if (AMBIENTE === 'gym') {
    capa('brown', 'lowpass', 180, 0.5, 0.16);
    setInterval(() => { if (Math.random() < 0.3) ping(90, 60, 0.25, 0.05); }, 2500);
  } else if (AMBIENTE === 'casa') {
    capa('brown', 'lowpass', 120, 0.5, 0.05);
  }
  if (LLUVIA) capa('white', 'highpass', 1200, 0.4, 0.03);
}

async function activarAudio(porClic) {
  try { if (!ctx) ctx = new (window.AudioContext || window.webkitAudioContext)();
        await Promise.race([ctx.resume(), espera(400)]); } catch (e) {}
  const activo = ctx && ctx.state === 'running';
  if (activo) ambiente();
  return activo || porClic;
}

function animar() {
  if (an) {
    an.getByteFrequencyData(datos);
    let v = 0; for (let i = 2; i < 40; i++) v += datos[i]; v /= 38 * 255;
    for (const img of [A, B]) { img.style.filter = `brightness(${1 + v * 0.15})`; img.style.marginTop = (-v * 6) + 'px'; }
    aro.style.opacity = Math.min(1, v * 3);
  }
  requestAnimationFrame(animar);
}

async function empezar(porClic) {
  play.style.display = 'none';
  const ok = await activarAudio(porClic);
  if (!audio) return;
  if (!ok) { play.style.display = 'block'; return; }  // el móvil pide un toque
  if (ctx && ctx.state === 'running' && !an) {
    try { const f = ctx.createMediaElementSource(audio); an = ctx.createAnalyser(); an.fftSize = 256;
      datos = new Uint8Array(an.frequencyBinCount); f.connect(an); an.connect(ctx.destination); } catch (e) {}
  }
  try { await audio.play(); animar(); } catch (e) { play.style.display = 'block'; }
}
play.onclick = (ev) => { ev.stopPropagation(); empezar(true); };
document.getElementById('marco').addEventListener('click', () => activarAudio(true));  // un toque activa el ambiente
empezar(false);
</script>
"""


def mostrar(nombre, foto, modo="llamada", foto_anterior=None, inicio=0, audio=None,
            texto="", narracion="", subtitulos=True, etiqueta="", alto=560, ambiente="", lluvia=False):
    cargando = f"Conectando con {nombre}…" if modo == "llamada" else f"Llegando… {nombre} te espera"
    reemplazos = {
        "__ALTO__": str(alto), "__MODO__": modo, "__NOMBRE__": html.escape(nombre),
        "__ETIQUETA__": html.escape(etiqueta), "__CARGANDO__": html.escape(cargando),
        "__TEXTO__": html.escape(texto or "") if subtitulos else "",
        "__NARRA__": html.escape(narracion or ""), "__SUBS__": "block" if subtitulos else "none",
        "__INICIO__": str(int(inicio)), "__ANTERIOR__": json.dumps(foto_anterior or ""),
        "__NUEVA__": json.dumps(foto),
        "__AUDIO__": json.dumps(base64.b64encode(audio).decode() if audio else ""),
        "__AMBIENTE__": ambiente or "", "__LLUVIA__": "true" if lluvia else "false",
    }
    pagina = PLANTILLA
    for k, v in reemplazos.items():
        pagina = pagina.replace(k, v)
    components.html(pagina, height=alto + 8)
