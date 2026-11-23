"""Compañeros IA – interfaz para móvil.  Ejecuta con:  streamlit run app.py"""
import base64
import hashlib
import io
import os
import time

import streamlit as st

st.set_page_config(page_title="Compañeros IA", page_icon="💬", layout="centered",
                   initial_sidebar_state="collapsed")

# Claves guardadas en los "Secrets" de Streamlit Cloud -> variables de entorno
try:
    for k, v in st.secrets.items():
        if isinstance(v, str):
            os.environ.setdefault(k, v)
except Exception:
    pass

import escena   # noqa: E402
import memoria  # noqa: E402
import motor    # noqa: E402
import mundo    # noqa: E402

ss = st.session_state

# ---------- Contraseña ----------
if os.getenv("CLAVE_APP") and not ss.get("dentro"):
    st.title("💬 Compañeros IA")
    if st.text_input("Contraseña", type="password") == os.getenv("CLAVE_APP"):
        ss.dentro = True
        st.rerun()
    st.stop()

st.markdown("""<style>
.block-container {padding-top:.8rem; padding-bottom:5rem; max-width:720px;}
[data-testid="stChatMessage"] img {border-radius:14px;}
.cab {display:flex; align-items:center; gap:12px;}
.cab img {width:58px; height:58px; border-radius:50%; object-fit:cover; border:2px solid #4ade80;}
.cab h2 {margin:0; font-size:1.35rem;} .cab small {opacity:.75; line-height:1.4;}
.leido {text-align:right; font-size:.75rem; color:#38bdf8; margin-top:-.6rem;}
</style>""", unsafe_allow_html=True)

PERSONAJES = motor.cargar_personajes()


@st.cache_data(show_spinner=False, max_entries=200)
def voz_cache(texto, voz):
    return motor.voz_mp3(texto, voz)


def foto(url, aviso=None):
    """Ruta local de una imagen generada (la descarga el servidor), o None si no ha cargado."""
    if not url:
        return None
    if aviso:
        with st.spinner(aviso):
            return motor.imagen_local(url)
    return motor.imagen_local(url)


def data_uri(ruta):
    with open(ruta, "rb") as f:
        return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()


def preparar_imagen(datos):
    """Reduce la foto que mandas para que no pese (y la pasa a JPEG)."""
    from PIL import Image, ImageOps
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(datos))).convert("RGB")
    img.thumbnail((1024, 1024))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=82)
    return buf.getvalue()


# ---------- Menú lateral ----------
with st.sidebar:
    st.title("💬 Compañeros IA")
    nombre_usuario = st.text_input("Tu nombre", value=ss.get("nombre", "Jugador"))
    ss.nombre = nombre_usuario
    pid = st.radio("Con quién quieres hablar", list(PERSONAJES),
                   format_func=lambda k: f"{PERSONAJES[k]['nombre']} · {PERSONAJES[k]['resumen']}")
    ss.voz = st.toggle("🔊 Leer sus mensajes en voz alta", value=ss.get("voz", False))
    with st.expander("🧠 Lo que recuerda de ti"):
        rs = memoria.recuerdos(pid)
        st.write("\n".join(f"- {r}" for r in rs) if rs else "Todavía nada.")
    with st.expander("📅 Fechas que tiene apuntadas"):
        fs = memoria.fechas(pid)
        st.write("\n".join(f"- {f}: {t}" for f, t in fs) if fs else "Ninguna.")
    with st.expander("💾 Guardar / cargar partida"):
        st.caption("En la nube la partida puede borrarse si la app se reinicia. Descárgala de vez en cuando.")
        st.download_button("⬇️ Descargar partida", memoria.exportar(), "partida.json", "application/json",
                           use_container_width=True)
        subida = st.file_uploader("Cargar partida", type="json")
        if subida and st.button("⬆️ Cargar", use_container_width=True):
            memoria.importar(subida.read().decode("utf-8"))
            st.rerun()
    if st.button("🗑️ Reiniciar relación", use_container_width=True):
        memoria.reiniciar(pid)
        st.rerun()
    st.caption(f"Motor IA: {motor.BACKEND}")

p = PERSONAJES[pid]
AVATAR = foto(motor.url_avatar(p), f"Cargando a {p['nombre']}…") or ("👩" if p.get("genero") == "f" else "🧑")
modo = ss.get("modo") if ss.get("modo_pid") == pid else None

# ---------- Cabecera ----------
puntos = memoria.afinidad(pid)
num, nombre_nivel, base, sig = motor.nivel(puntos)
clima = mundo.tiempo(p)
img_cab = f'<img src="{data_uri(AVATAR)}">' if os.path.exists(AVATAR) else f'<span style="font-size:44px">{AVATAR}</span>'
st.markdown(f"""<div class="cab">{img_cab}<div><h2>{p['nombre']}</h2>
<small>{motor.conexion(p)} · ❤️ Nivel {num} {nombre_nivel}<br>
📍 {p['lugares'][motor.lugar_actual(p)]['nombre']} · {mundo.momento_del_dia()[0]}{' · ' + clima[0] if clima else ''}</small>
</div></div>""", unsafe_allow_html=True)
st.progress((puntos - base) / (sig - base) if sig else 1.0,
            text=f"{puntos} / {sig} puntos" if sig else f"{puntos} puntos · ¡nivel máximo!")

for a in ss.pop("avisos", []):
    st.toast(a)
if ss.pop("globos", False):
    st.balloons()


# ---------- Enviar un mensaje (chat, llamada o quedada) ----------
def enviar(texto, modo_envio="chat", imagen=None):
    if not memoria.historial(pid):  # el saludo inicial pasa a formar parte de la conversación
        memoria.guardar_mensaje(pid, "assistant", p["saludo"])
    with st.spinner(f"{p['nombre']} está {'escribiendo' if modo_envio == 'chat' else 'pensando'}…"):
        try:
            r = motor.turno(p, texto, nombre_usuario, modo=modo_envio, imagen=imagen)
        except Exception as e:
            st.error(f"No se pudo obtener respuesta ({motor.BACKEND}): {e}")
            st.stop()

    avisos = []
    if r["delta"]:
        avisos.append(f"{'❤️ +' if r['delta'] > 0 else '💔 '}{r['delta']} afinidad")
    avisos += [f"🧠 Recordará: {x}" for x in r["recuerdos"]]
    avisos += [f"📅 Apuntado: {q} ({f})" for f, q in r["fechas"]]
    if r["cambio_lugar"]:
        avisos.append(f"📍 Ahora: {r['cambio_lugar']}")
    if r["subio"]:
        avisos.append("🎉 ¡Nivel nuevo! Historia desbloqueada y foto de regalo.")
    ss.avisos, ss.globos = avisos, r["subio"]

    if modo_envio == "chat":
        # Efecto de escribir mensaje a mensaje
        for parte in r["partes"]:
            with st.chat_message("assistant", avatar=AVATAR):
                hueco = st.empty()
                hueco.markdown("_escribiendo…_" if not r["audio"] else "_grabando audio…_")
                time.sleep(min(0.6 + len(parte) / 45, 2.5))
                hueco.markdown(parte if not r["audio"] else "🎤 Nota de voz")
        if ss.voz and not r["audio"]:
            ss.audio_chat = voz_cache(r["texto"], p["voz"])
    else:
        ss.ultima_narracion, ss.ultima_habla = r["narracion"], r["habla"]
        if r["vista"]:
            ss.vista_n = ss.get("vista_n", 0) + 1
            ss.vista_anterior = ss.get("vista")
            ss.vista = motor.url_vista(p, r["vista"], modo_envio, ss.vista_n)
        try:
            ss.audio_escena = motor.voz_mp3(r["habla"], p["voz"]) if r["habla"] else None
        except Exception:
            ss.audio_escena = None
    st.rerun()


def salir_de_escena():
    for k in ("modo", "modo_pid", "vista", "vista_anterior", "audio_escena", "ultima_narracion",
              "ultima_habla", "inicio_llamada"):
        ss.pop(k, None)
    st.rerun()


# =====================================================================
#                 VIDEOLLAMADA  y  QUEDAR EN PERSONA
# =====================================================================
if modo in ("llamada", "quedada"):
    lugar_nombre = p["lugares"][motor.lugar_actual(p)]["nombre"]
    audio = ss.pop("audio_escena", None)
    url_actual = ss.get("vista") or motor.url_vista(p, "smiling, happy to see you", modo, 0)
    ruta_actual = foto(url_actual, f"{p['nombre']} {'conectando la cámara' if modo == 'llamada' else 'está llegando'}…")
    if not ruta_actual:  # si la nueva no carga, se queda la anterior
        ruta_actual = foto(ss.get("vista_ok")) if ss.get("vista_ok") else None
    else:
        ss.vista_ok = url_actual
    url_prev = ss.pop("vista_anterior", None)
    ruta_prev = foto(url_prev) if url_prev else None
    if not ruta_actual:
        st.warning("Las imágenes tardan en cargar ahora mismo. Puedes seguir hablando y lo reintento en el siguiente mensaje.")
    escena.mostrar(
        p["nombre"], data_uri(ruta_actual) if ruta_actual else "",
        modo=modo, foto_anterior=data_uri(ruta_prev) if ruta_prev and ruta_prev != ruta_actual else None,
        inicio=ss.setdefault("inicio_llamada", time.time()), audio=audio,
        texto=ss.get("ultima_habla", "") if audio else "",
        narracion=ss.get("ultima_narracion", "") if modo == "quedada" else "",
        subtitulos=ss.get("subs", True),
        etiqueta="en directo" if modo == "llamada" else f"📍 {lugar_nombre}")

    if modo == "quedada":
        acciones = {"🥂 Pedir algo": "*Llamo al camarero / busco algo de beber para los dos*",
                    "🚶 Dar un paseo": "*Te propongo salir a dar un paseo juntos*",
                    "🤗 Abrazo": "*Te doy un abrazo*",
                    "😂 Contar algo": "*Te cuento algo gracioso que me ha pasado hoy*"}
        cols = st.columns(len(acciones))
        for col, (etiqueta, accion) in zip(cols, acciones.items()):
            if col.button(etiqueta, use_container_width=True):
                enviar(accion, "quedada")

    grabacion = st.audio_input("🎙️ Pulsa, habla y vuelve a pulsar", key=f"mic_{pid}_{modo}")
    if grabacion:
        datos = grabacion.getvalue()
        huella = hashlib.md5(datos).hexdigest()
        if ss.get("ultimo_audio") != huella:
            ss.ultimo_audio = huella
            with st.spinner("Escuchándote…"):
                try:
                    dicho = motor.transcribir(datos, grabacion.type or "audio/wav")
                except Exception as e:
                    st.error(f"No pude entender el audio: {e}")
                    dicho = ""
            if dicho:
                enviar(dicho, modo)
            else:
                st.warning("No se te ha oído bien. Prueba otra vez más cerca del micro.")

    escrito = st.chat_input("…o escribe. Usa *asteriscos* para acciones" if modo == "quedada" else "…o escribe aquí")
    if escrito:
        enviar(escrito, modo)

    c1, c2 = st.columns(2)
    ss.subs = c1.toggle("Subtítulos", value=ss.get("subs", True))
    if c2.button("📕 Colgar" if modo == "llamada" else "👋 Despedirse", type="primary", use_container_width=True):
        if modo == "quedada":
            memoria.guardar_mensaje(pid, "user", "*Nos despedimos y cada uno se va a su casa*")
        salir_de_escena()
    st.stop()


# =====================================================================
#                                CHAT
# =====================================================================
# Te escribe primero si llevas horas sin aparecer
if not ss.get(f"proactivo_{pid}"):
    ss[f"proactivo_{pid}"] = True
    try:
        with st.spinner(f"{p['nombre']} te está escribiendo…"):
            if motor.mensaje_proactivo(p, nombre_usuario):
                st.rerun()
    except Exception:
        pass

# Historias de hoy
hist = motor.historias(p)
if hist and st.toggle(f"📖 Ver historias de hoy ({len(hist)})", key=f"hist_{pid}"):
    for url, texto in reversed(hist):
        ruta = foto(url, "Cargando historia…")
        if ruta:
            st.image(ruta, caption=texto)
        else:
            st.caption(f"{texto} · (la imagen no ha cargado)")

historial = memoria.historial(pid)
if not historial:
    with st.chat_message("assistant", avatar=AVATAR):
        st.markdown(p["saludo"])

ultimo_user = max((i for i, m in enumerate(historial) if m["role"] in ("user", "foto_usuario")), default=-1)
for i, m in enumerate(historial):
    rol, contenido = m["role"], m["content"]
    if rol == "lugar":
        st.caption(f"📍 Cambio de escena: {contenido}")
        continue
    if rol in ("user", "foto_usuario"):
        with st.chat_message("user", avatar="🙂"):
            if rol == "foto_usuario":
                st.image(base64.b64decode(contenido.split(",", 1)[1]), width=260)
            else:
                st.markdown(contenido)
        if i == ultimo_user and i < len(historial) - 1:
            st.markdown('<div class="leido">✓✓ Leído</div>', unsafe_allow_html=True)
        continue
    with st.chat_message("assistant", avatar=AVATAR):
        if rol == "foto":
            ruta = foto(contenido, f"{p['nombre']} te está enviando una foto…")
            if ruta:
                st.image(ruta)
            else:
                st.caption("📷 Foto (no ha cargado; recarga la página en un momento)")
        elif rol == "nota_voz":
            audio = voz_cache(contenido, p["voz"])
            if audio:
                st.audio(audio, format="audio/mp3")
            with st.expander("🎤 Nota de voz · ver texto"):
                st.write(contenido)
        else:
            st.markdown(contenido)

if ss.get("audio_chat"):
    st.audio(ss.pop("audio_chat"), format="audio/mp3", autoplay=True)

# ---------- Botones ----------
c1, c2, c3 = st.columns(3)
if c1.button("📸 Foto", use_container_width=True):
    ss.pendiente = "¿Me mandas una foto de lo que estás haciendo ahora?"
if c2.button("📹 Llamar", use_container_width=True):
    ss.modo, ss.modo_pid = "llamada", pid
    saludo = f"¡Hola, {nombre_usuario}! Qué bien verte."
    ss.ultima_habla = saludo
    try:
        ss.audio_escena = motor.voz_mp3(saludo, p["voz"])
    except Exception:
        pass
    st.rerun()
with c3.popover("💞 Quedar", use_container_width=True):
    st.markdown(f"**¿Dónde quedas con {p['nombre']}?**")
    claves = [k for k in p["lugares"] if k != "habitacion"]
    sitio = st.selectbox("Lugar", claves, format_func=lambda k: p["lugares"][k]["nombre"],
                         index=claves.index(motor.lugar_actual(p)) if motor.lugar_actual(p) in claves else 0)
    if st.button("Ir ahora", type="primary", use_container_width=True):
        motor.cambiar_lugar(p, sitio)
        ss.modo, ss.modo_pid = "quedada", pid
        enviar(f"*Llego al sitio donde habíamos quedado ({p['lugares'][sitio]['nombre']}) y te veo*", "quedada")

entrada = st.chat_input(f"Mensaje para {p['nombre']}…", accept_file=True, file_type=["jpg", "jpeg", "png", "webp"])
texto, imagen = ss.pop("pendiente", None), None
if entrada:
    texto = entrada.text or ""
    if entrada.files:
        try:
            imagen = preparar_imagen(entrada.files[0].getvalue())
        except Exception:
            st.error("No he podido abrir esa imagen.")
if texto or imagen:
    with st.chat_message("user", avatar="🙂"):
        if imagen:
            st.image(imagen, width=260)
        if texto:
            st.markdown(texto)
    enviar(texto, "chat", imagen=imagen)
