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

# ---------- Partida guardada en tu GitHub: recuperar al arrancar y guardar los cambios ----------
if memoria.nube_activa():
    with st.spinner("Recuperando tu partida…"):
        memoria.cargar_de_nube()
    memoria.guardar_si_hay_cambios()

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
def voz_cache(texto, voz, tono=None):
    return motor.voz_mp3(texto, voz, tono)


def foto(url, aviso=None):
    """Ruta local de una imagen generada (la descarga el servidor), o None si no ha cargado."""
    if not url:
        return None
    if aviso:
        with st.spinner(aviso):
            return motor.imagen_local(url)
    return motor.imagen_local(url)


@st.fragment(run_every=4)
def foto_que_llega(url, texto_espera, pie=None):
    """Muestra la foto cuando esté lista; mientras, un aviso. No bloquea el chat."""
    ruta = motor.imagen_en_segundo_plano(url)
    if ruta:
        st.image(ruta, caption=pie)
    else:
        st.caption(texto_espera)


def data_uri(ruta):
    with open(ruta, "rb") as f:
        return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()


def preparar_imagen(datos):
    """Reduce la foto que mandas para que no pese (y la pasa a JPEG)."""
    from PIL import Image, ImageOps
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(datos))).convert("RGB")
    img.thumbnail((768, 768))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=75)
    return buf.getvalue()


# ---------- Menú lateral ----------
with st.sidebar:
    st.title("💬 Compañeros IA")
    nombre_usuario = st.text_input("Tu nombre", value=ss.get("nombre", "Jugador"))
    ss.nombre = nombre_usuario
    contactos = [motor.HILO_WHATSAPP] + [k for k, q in PERSONAJES.items() if motor.es_conocido(q)]
    if "cambiar_contacto" in ss:  # p. ej. al irte con alguien desde una salida
        ss.contacto = ss.pop("cambiar_contacto")
    pid = st.radio(f"Tus contactos ({len(contactos) - 1})", contactos, key="contacto",
                   format_func=lambda k: "👥 Los de siempre · grupo de WhatsApp" if k == motor.HILO_WHATSAPP
                   else f"{PERSONAJES[k]['nombre']} · {PERSONAJES[k]['resumen']}")
    ss.voz = st.toggle("🔊 Leer sus mensajes en voz alta", value=ss.get("voz", False))
    with st.expander(f"🌍 Ampliar el mundo · {motor.faltan_por_conocer()} personas por conocer"):
        st.caption("Conoce gente saliendo (🗺️ Salir), en quedadas o porque tus amigos te la presentan. "
                   "Cuando conozcas a casi todos, crea más:")
        deseo = st.text_input("¿Qué tipo de gente? (opcional)", placeholder="p. ej. gente de la noche, deportistas, artistas…")
        if st.button("✨ Crear 5 personas nuevas en Madrid", use_container_width=True):
            with st.spinner("Creando gente nueva…"):
                nuevos = None
                try:
                    nuevos = motor.crear_gente(5, deseo)
                    ss.avisos = [f"✨ Han llegado al barrio: {', '.join(nuevos)}"]
                except Exception as e:
                    st.error(f"No se pudo crear gente ahora: {e}")
                if nuevos:
                    st.rerun()
    with st.expander("🧠 Cerebros de IA (mensajes ilimitados)"):
        for nombre_c, estado_c in motor.estado_cerebros():
            st.write(f"- {nombre_c}: {estado_c}")
        st.caption(f"Último en responder: {motor.ESTADO_CEREBRO['ultimo'] or '—'}")
    es_grupo_wa = pid == motor.HILO_WHATSAPP
    if not es_grupo_wa:
        with st.expander("🧠 Lo que recuerda de ti"):
            rs = memoria.recuerdos(pid)
            st.write("\n".join(f"- {r}" for r in rs) if rs else "Todavía nada.")
        with st.expander("💫 Momentos que habéis vivido"):
            ms = memoria.momentos(pid, 20)
            st.write("\n".join(f"- {f}: {t}" for f, t in ms) if ms else "Todavía ninguno.")
        with st.expander("📅 Fechas que tiene apuntadas"):
            fs = memoria.fechas(pid)
            st.write("\n".join(f"- {f}: {t}" for f, t in fs) if fs else "Ninguna.")
    with st.expander("🗞️ Lo que pasa en vuestro mundo"):
        ev = memoria.sucesos("madrid" if es_grupo_wa else PERSONAJES[pid].get("mundo", pid), 20)
        st.write("\n".join(f"- {f}: {t}" for f, t in reversed(ev)) if ev else "Aún no ha pasado nada.")
    with st.expander("📷 Tu aspecto (para fotos juntos)"):
        st.caption("Sube un selfie: solo se guarda una descripción en texto (pelo, barba, estilo…), no la foto.")
        if motor.aspecto_usuario():
            st.write(f"Ahora: _{motor.aspecto_usuario()}_")
        selfie = st.file_uploader("Tu selfie", type=["jpg", "jpeg", "png", "webp"], key="selfie")
        if selfie and st.button("Guardar mi aspecto", use_container_width=True):
            with st.spinner("Mirando tu foto…"):
                hecho = False
                try:
                    motor.describir_usuario(preparar_imagen(selfie.getvalue()))
                    hecho = True
                except Exception as e:
                    st.error(f"No pude analizar la foto: {e}")
                if hecho:
                    st.rerun()
    with st.expander("💾 Partida guardada"):
        if memoria.nube_activa():
            st.write(f"Guardado automático en tu GitHub: {memoria.estado_nube()}")
        else:
            st.warning("Guardado automático desactivado: añade GITHUB_TOKEN en Secrets (ver README). "
                       "Mientras tanto, descarga la partida de vez en cuando.")
        st.caption("Copia de seguridad manual:")
        st.download_button("⬇️ Descargar partida", memoria.exportar(), "partida.json", "application/json",
                           use_container_width=True)
        subida = st.file_uploader("Cargar partida", type="json")
        if subida and st.button("⬆️ Cargar", use_container_width=True):
            memoria.importar(subida.read().decode("utf-8"))
            st.rerun()
    if not es_grupo_wa and st.button("🗑️ Reiniciar relación", use_container_width=True):
        memoria.reiniciar(pid)
        st.rerun()

for a_ in ss.pop("avisos", []):
    st.toast(a_)
if ss.pop("globos", False):
    st.balloons()

# ---------- El mundo vive solo: una vez al día pasan cosas entre ellos ----------
if not ss.get("mundo_simulado"):
    ss.mundo_simulado = True
    try:
        with st.spinner("El mundo se despierta…"):
            motor.simular_mundo(nombre_usuario)
    except Exception:
        pass


# =====================================================================
#               GRUPO DE WHATSAPP "LOS DE SIEMPRE"
# =====================================================================
if es_grupo_wa:
    miembros = motor.miembros_whatsapp()
    por_nombre = {q["nombre"]: q for q in miembros}
    st.markdown(f"### 👥 Los de siempre\n<small>{', '.join(q['nombre'] for q in miembros)} y tú</small>",
                unsafe_allow_html=True)
    if not ss.get("wa_revisado"):
        ss.wa_revisado = True
        hubo = False
        try:
            with st.spinner("Están escribiendo en el grupo…"):
                hubo = motor.whatsapp_vivo(nombre_usuario)
        except Exception:
            pass
        if hubo:
            st.rerun()
    for m in memoria.historial(motor.HILO_WHATSAPP)[-80:]:
        if m["role"] == "user":
            with st.chat_message("user", avatar="🙂"):
                st.markdown(m["content"])
            continue
        quien, _, texto_m = m["content"].partition(": ")
        q = por_nombre.get(quien)
        av = (motor.imagen_en_segundo_plano(motor.url_avatar(q)) if q else None) or "💬"
        with st.chat_message("assistant", avatar=av):
            st.markdown(f"**{quien}**  \n{texto_m}")
    escrito = st.chat_input("Escribe al grupo…")
    if escrito:
        with st.chat_message("user", avatar="🙂"):
            st.markdown(escrito)
        with st.spinner("Escribiendo…"):
            try:
                r = motor.turno_whatsapp(escrito, nombre_usuario)
                av = [f"{'❤️ +' if d > 0 else '💔 '}{d} con {n.capitalize()}" for n, d in r["deltas"].items() if d]
                av += [f"🤝 Te han pasado el contacto de {n}" for n in r["nuevos_contactos"]]
                ss.avisos = av
            except Exception as e:
                st.error(f"No se pudo obtener respuesta: {e}")
                st.stop()
        st.rerun()
    st.stop()

p = PERSONAJES[pid]
# El avatar se descarga por detrás: mientras tanto se ve un emoji y el chat no espera
AVATAR = motor.imagen_en_segundo_plano(motor.url_avatar(p)) or ("👩" if p.get("genero") == "f" else "🧑")
modo = ss.get("modo") if ss.get("modo_pid") == pid else None

# ---------- Cabecera ----------
puntos = memoria.afinidad(pid)
num, nombre_nivel, base, sig = motor.nivel(puntos)
clima = mundo.tiempo(p)
img_cab = f'<img src="{data_uri(AVATAR)}">' if os.path.exists(AVATAR) else f'<span style="font-size:44px">{AVATAR}</span>'
st.markdown(f"""<div class="cab">{img_cab}<div><h2>{p['nombre']}</h2>
<small>{motor.conexion(p)} · ❤️ Nivel {num} {nombre_nivel}{' · ' + motor.RELACIONES[motor.relacion(p)] if motor.relacion(p) != 'amistad' else ''}<br>
📍 {p['lugares'][motor.lugar_actual(p)]['nombre']} · {mundo.momento_del_dia()[0]}{' · ' + clima[0] if clima else ''}</small>
</div></div>""", unsafe_allow_html=True)
st.progress((puntos - base) / (sig - base) if sig else 1.0,
            text=f"{puntos} / {sig} puntos" if sig else f"{puntos} puntos · ¡nivel máximo!")



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
    if r.get("cambio_relacion"):
        avisos.append(f"Vuestra relación ahora: {r['cambio_relacion']}")
    if r.get("fundido"):
        avisos.append("🌙 Fundido a negro…")
    avisos += [f"🤝 {p['nombre']} te ha pasado el contacto de {n}: ya está en tus contactos" for n in r.get("nuevos_contactos", [])]
    if r["subio"]:
        avisos.append("🎉 ¡Nivel nuevo! Historia desbloqueada y foto de regalo.")
    ss.avisos, ss.globos = avisos, r["subio"]

    if modo_envio == "chat":
        # Efecto de escribir mensaje a mensaje
        for parte in r["partes"]:
            with st.chat_message("assistant", avatar=AVATAR):
                hueco = st.empty()
                hueco.markdown("_escribiendo…_" if not r["audio"] else "_grabando audio…_")
                time.sleep(min(0.3 + len(parte) / 90, 1.0))
                hueco.markdown(parte if not r["audio"] else "🎤 Nota de voz")
        if ss.voz and not r["audio"]:
            ss.audio_chat = voz_cache(r["texto"], p["voz"], p.get("tono"))
    else:
        ss.ultima_narracion, ss.ultima_habla = r["narracion"], r["habla"]
        if r["vista"] and motor.escena_apta(r["vista"]):
            ss.vista_n = ss.get("vista_n", 0) + 1
            ss.vista_anterior = ss.get("vista")
            ss.vista = motor.url_vista(p, r["vista"], modo_envio, ss.vista_n)
            motor.imagen_en_segundo_plano(ss.vista)  # se descarga mientras se genera la voz
        try:
            ss.audio_escena = motor.voz_de(r["habla"], p) if r["habla"] else None
        except Exception:
            ss.audio_escena = None
    st.rerun()


def salir_de_escena():
    for k in ("modo", "modo_pid", "vista", "vista_anterior", "vista_ok", "audio_escena", "ultima_narracion",
              "ultima_habla", "inicio_llamada", "grupo", "salida"):
        ss.pop(k, None)
    st.rerun()


def poner_vista(url):
    ss.vista_anterior = ss.get("vista")
    ss.vista = url
    motor.imagen_en_segundo_plano(url)  # se descarga mientras se genera la voz


TIPO_AMBIENTE = {"bar_dani": "bar", "terraza": "bar", "sala_conciertos": "bar", "cafeteria": "bar", "mercado": "bar",
                 "taberna": "bar", "escenario": "bar", "calle": "calle", "madrid_rio": "parque", "retiro": "parque",
                 "parque": "parque", "parque_perros": "parque", "canal": "calle", "crossfit": "gym", "gimnasio": "gym",
                 "rocodromo": "gym", "padel": "parque", "salsa": "bar", "universidad": "parque", "hospital": "casa",
                 "discoteca": "bar", "fiesta_casa": "bar", "protectora": "parque", "libreria": "casa", "biblioteca": "casa",
                 "coworking": "casa", "yoga": "casa"}


def anfitrion_actual():
    return motor.anfitrion_salida(ss.salida) if ss.get("salida") else p


def enviar_grupo(texto, personas):
    anf = anfitrion_actual()
    with st.spinner("Están hablando…"):
        try:
            r = motor.turno_grupo(personas, anf, texto, nombre_usuario)
        except Exception as e:
            st.error(f"No se pudo obtener respuesta ({motor.BACKEND}): {e}")
            st.stop()
    avisos = [f"{'❤️ +' if d > 0 else '💔 '}{d} con {n.capitalize()}" for n, d in r["deltas"].items() if d]
    avisos += [f"🎉 ¡Nivel nuevo con {n}!" for n in r["subidas"]]
    if r["cambio_lugar"]:
        avisos.append(f"📍 Ahora: {r['cambio_lugar']}")
    avisos += [f"🤝 Has conocido a {n}: ya está en tus contactos" for n in r["nuevos_contactos"]]
    avisos += [f"{n}: vuestra relación ahora es {t}" for n, t in r.get("cambios_relacion", [])]
    ss.avisos, ss.globos = avisos, bool(r["subidas"] or r["nuevos_contactos"])
    if r.get("irse_con") and r["irse_con"] in PERSONAJES:
        # Os vais juntos a solas: la escena pasa a ser solo vosotros dos
        q = PERSONAJES[r["irse_con"]]
        if ss.get("salida") or ss.get("grupo"):
            motor.terminar_grupo(personas, anf, nombre_usuario)
        for k in ("grupo", "salida", "vista", "vista_anterior", "vista_ok"):
            ss.pop(k, None)
        destino = "casa_usuario" if "casa_usuario" in q["lugares"] else "casa"
        motor.cambiar_lugar(q, destino)
        ss.cambiar_contacto, ss.modo, ss.modo_pid = q["id"], "quedada", q["id"]
        ss.pendiente_quedada = "*Nos vamos juntos de allí, solos, charlando por el camino*"
        ss.avisos = ss.avisos + [f"🚶 Te vas con {q['nombre']}…"]
        st.rerun()
    ss.ultima_narracion = " ".join(f"{n}: {narr}" if n != "Narrador" else narr for n, narr, _ in r["lineas"] if narr)
    ss.ultima_habla = "\n".join(f"{n}: {h}" for n, _, h in r["lineas"] if h)
    if r["vista"] and motor.escena_apta(r["vista"]):
        ss.vista_n = ss.get("vista_n", 0) + 1
        poner_vista(motor.url_foto_grupo(personas, "first person point of view, the viewer is there with them. "
                                         + r["vista"], anf, ancho=720, alto=1080, extra=ss.vista_n))
    ss.audio_escena = motor.audio_grupo(r["lineas"], personas)
    st.rerun()


# =====================================================================
#          VIDEOLLAMADA, QUEDAR EN PERSONA y QUEDADA EN GRUPO
# =====================================================================
if modo == "quedada" and ss.get("pendiente_quedada"):
    enviar(ss.pop("pendiente_quedada"), "quedada")

if modo in ("llamada", "quedada", "grupo"):
    personas = [PERSONAJES[k] for k in ss.get("grupo", [pid]) if k in PERSONAJES]
    anf = anfitrion_actual() if modo == "grupo" else p
    lugar_nombre = anf["lugares"][motor.lugar_actual(anf)]["nombre"]
    audio = ss.pop("audio_escena", None)
    if modo == "grupo":
        url_actual = ss.get("vista") or motor.url_foto_grupo(personas, "people in the place, some noticing the viewer arriving", anf, 720, 1080)
        espera = "Llegando… os estáis saludando"
    else:
        url_actual = ss.get("vista") or motor.url_vista(p, "smiling, happy to see you", modo, 0)
        espera = f"{p['nombre']} {'conectando la cámara' if modo == 'llamada' else 'está llegando'}…"
    ruta_actual = foto(url_actual, espera)
    if not ruta_actual:  # si la nueva no carga, se queda la anterior
        ruta_actual = foto(ss.get("vista_ok")) if ss.get("vista_ok") else None
    else:
        ss.vista_ok = url_actual
    url_prev = ss.pop("vista_anterior", None)
    ruta_prev = motor.imagen_lista(url_prev) if url_prev else None
    if not ruta_actual:
        st.warning("Las imágenes tardan en cargar ahora mismo. Puedes seguir hablando y lo reintento en el siguiente mensaje.")
    con = ", ".join(q["nombre"] if motor.es_conocido(q) else "gente nueva" for q in personas) or "Madrid"
    con = ", ".join(dict.fromkeys(con.split(", ")))
    escena.mostrar(
        con if modo == "grupo" else p["nombre"], data_uri(ruta_actual) if ruta_actual else "",
        modo="quedada" if modo == "grupo" else modo,
        foto_anterior=data_uri(ruta_prev) if ruta_prev and ruta_prev != ruta_actual else None,
        inicio=ss.setdefault("inicio_llamada", time.time()), audio=audio,
        texto=ss.get("ultima_habla", ""),
        narracion=ss.get("ultima_narracion", "") if modo != "llamada" else "",
        subtitulos=ss.get("subs", True),
        etiqueta="en directo" if modo == "llamada" else f"📍 {lugar_nombre}",
        ambiente=TIPO_AMBIENTE.get(motor.lugar_actual(anf), "casa") if ss.get("ambiente", True) else "",
        lluvia=any(w in ((mundo.tiempo(anf) or ("", ""))[1]) for w in ("rain", "drizzle", "shower", "thunder")))
    if audio:
        # Respaldo: en iPhone, si la voz no suena sola en la escena, dale al play aquí
        st.audio(audio, format="audio/mp3")
    elif ss.get("ultima_habla") and motor.ESTADO_VOZ["error"]:
        st.caption(f"🔇 No se pudo generar la voz ahora ({motor.ESTADO_VOZ['error']}). Tienes el texto en los subtítulos.")

    def responder(texto):
        if modo == "grupo":
            enviar_grupo(texto, personas)
        else:
            enviar(texto, modo)

    if modo == "quedada":
        acciones = {"🥂 Pedir algo": "*Pido algo de beber para los dos*",
                    "🚶 Paseo": "*Te propongo salir a dar un paseo juntos*",
                    "🤗 Abrazo": "*Te doy un abrazo*",
                    "🤳 Foto juntos": None}
    elif modo == "grupo":
        acciones = {"🥂 Ronda": "*Pido una ronda para todos*",
                    "🎲 Juego": "*Propongo jugar a algo todos juntos (yo nunca, verdad o atrevimiento suave, adivinanzas...)*",
                    "🚶 Otro sitio": "*Propongo que nos vayamos todos a otro sitio*",
                    "📸 Foto grupo": None}
    else:
        acciones = {}
    if acciones:
        cols = st.columns(len(acciones))
        for col, (etiqueta, accion) in zip(cols, acciones.items()):
            if col.button(etiqueta, use_container_width=True):
                if accion:
                    responder(accion)
                else:  # foto juntos / foto de grupo: se guarda en vuestro chat
                    if modo == "grupo":
                        url = motor.url_foto_grupo(personas, "everyone posing together for a group selfie, laughing",
                                                   anf, con_usuario=True, extra=time.time())
                    else:
                        url = motor.url_foto_juntos(p)
                    for q in personas:
                        memoria.guardar_mensaje(q["id"], "foto", url)
                    poner_vista(url)
                    ss.avisos = ["📸 ¡Foto guardada en vuestro chat!" +
                                 ("" if motor.aspecto_usuario() else " (Sube un selfie en ☰ → Tu aspecto para salir tú)")]
                    st.rerun()

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
                responder(dicho)
            else:
                st.warning("No se te ha oído bien. Prueba otra vez más cerca del micro.")

    escrito = st.chat_input("…o escribe. Usa *asteriscos* para acciones" if modo != "llamada" else "…o escribe aquí")
    if escrito:
        responder(escrito)

    c1, c2 = st.columns(2)
    ss.subs = c1.toggle("Subtítulos", value=ss.get("subs", True))
    ss.ambiente = c1.toggle("Sonido ambiente", value=ss.get("ambiente", True))
    if c2.button("📕 Colgar" if modo == "llamada" else "👋 Despedirse", type="primary", use_container_width=True):
        if modo == "quedada":
            memoria.guardar_mensaje(pid, "user", "*Nos despedimos y cada uno se va a su casa*")
        elif modo == "grupo":
            motor.terminar_grupo(personas, anf, nombre_usuario)
        salir_de_escena()
    st.stop()


# =====================================================================
#                                CHAT
# =====================================================================
# ¿Tenía que contestarte algo que dejó pendiente?
contesto = False
try:
    with st.spinner(f"{p['nombre']} está mirando el móvil…"):
        contesto = motor.revisar_pendientes(p, nombre_usuario)
except Exception:
    pass
if contesto:
    st.rerun()


@st.fragment(run_every=30)
def vigilar_respuesta():
    """Cada 30 s mira si ya le toca contestarte (sin recargar todo)."""
    if memoria.leer(pid, "pendiente_hasta"):
        listo = False
        try:
            listo = motor.revisar_pendientes(p, nombre_usuario)
        except Exception:
            pass
        if listo:
            st.rerun(scope="app")


vigilar_respuesta()

# Te escribe primero si llevas horas sin aparecer
if not ss.get(f"proactivo_{pid}") and not memoria.leer(pid, "pendiente_hasta"):
    ss[f"proactivo_{pid}"] = True
    escribio = False
    try:
        with st.spinner(f"{p['nombre']} te está escribiendo…"):
            escribio = motor.mensaje_proactivo(p, nombre_usuario)
    except Exception:
        pass
    if escribio:
        st.rerun()

# Historias de hoy
hist = motor.historias(p)
if hist and st.toggle(f"📖 Ver historias de hoy ({len(hist)})", key=f"hist_{pid}"):
    for url, texto in reversed(hist):
        foto_que_llega(url, f"⏳ {texto} · cargando…", pie=texto)

historial = memoria.historial(pid)
if not historial:
    with st.chat_message("assistant", avatar=AVATAR):
        st.markdown(p["saludo"])

ultimo_user = max((i for i, m in enumerate(historial) if m["role"] in ("user", "foto_usuario")), default=-1)
for i, m in enumerate(historial):
    rol, contenido = m["role"], m["content"]
    if rol == "lugar":
        st.caption(contenido if contenido.startswith("🌙") else f"📍 Cambio de escena: {contenido}")
        continue
    if rol in ("user", "foto_usuario"):
        with st.chat_message("user", avatar="🙂"):
            if rol == "foto_usuario":
                st.image(base64.b64decode(contenido.split(",", 1)[1]), width=260)
            else:
                st.markdown(contenido)
        if i == ultimo_user:
            marca = motor.estado_entrega(p) or ("✓✓ Leído" if i < len(historial) - 1 else None)
            if marca:
                st.markdown(f'<div class="leido">{marca}</div>', unsafe_allow_html=True)
        continue
    with st.chat_message("assistant", avatar=AVATAR):
        if rol == "foto":
            foto_que_llega(contenido, f"📷 {p['nombre']} te está enviando una foto…")
        elif rol == "nota_voz":
            audio = voz_cache(contenido, p["voz"], p.get("tono"))
            if audio:
                st.audio(audio, format="audio/mp3")
            with st.expander("🎤 Nota de voz · ver texto"):
                st.write(contenido)
        else:
            st.markdown(contenido)

if ss.get("audio_chat"):
    st.audio(ss.pop("audio_chat"), format="audio/mp3", autoplay=True)

# ---------- Botones ----------
c1, c2, c3, c4 = st.columns(4)
if c1.button("📸 Foto", use_container_width=True):
    ss.pendiente = "¿Me mandas una foto de lo que estás haciendo ahora?"
if c2.button("📹 Llamar", use_container_width=True):
    ss.modo, ss.modo_pid = "llamada", pid
    saludo = f"¡Hola, {nombre_usuario}! Qué bien verte."
    ss.ultima_habla = saludo
    try:
        ss.audio_escena = motor.voz_de(saludo, p)
    except Exception:
        pass
    st.rerun()
if p.get("mundo") == "madrid":
    with c4.popover("🗺️ Salir", use_container_width=True):
        st.markdown("**Salir por Madrid y conocer gente**")
        sitio_s = st.selectbox("¿Adónde?", list(motor.SITIOS), key="salir_sitio",
                               format_func=lambda k: motor.SITIOS[k]["nombre"].removeprefix("en ").capitalize())
        amigos_s = st.multiselect("¿Con alguien?", [k for k, q in PERSONAJES.items()
                                                    if motor.es_conocido(q) and q.get("mundo") == "madrid"],
                                  format_func=lambda k: PERSONAJES[k]["nombre"], placeholder="Voy solo/a", key="salir_con")
        if st.button("Salir", type="primary", use_container_width=True, key="salir_ir"):
            personas_s, anf_s = motor.empezar_salida(sitio_s, [PERSONAJES[k] for k in amigos_s])
            if not personas_s:
                st.warning("Ya conoces a la gente que suele ir ahí. Prueba otro sitio o crea gente nueva (menú ☰).")
            else:
                ss.modo, ss.modo_pid, ss.grupo, ss.salida = "grupo", pid, [q["id"] for q in personas_s], sitio_s
                acompanado = f" con {', '.join(PERSONAJES[k]['nombre'] for k in amigos_s)}" if amigos_s else " solo/a"
                enviar_grupo(f"*Llego{acompanado} a {motor.SITIOS[sitio_s]['nombre'].removeprefix('en ')} y miro a mi alrededor*",
                             personas_s)

with c3.popover("💞 Quedar", use_container_width=True):
    st.markdown(f"**Quedar con {p['nombre']}**")
    amigos = [k for k, q in PERSONAJES.items() if k != pid and q.get("mundo") == p.get("mundo") and motor.es_conocido(q)]
    con_quien = st.multiselect("¿Viene alguien más?", amigos, format_func=lambda k: PERSONAJES[k]["nombre"],
                               placeholder="Solo vosotros dos") if amigos else []
    claves = [k for k in p["lugares"] if k != "habitacion"]
    sitio = st.selectbox("Lugar", claves, format_func=lambda k: p["lugares"][k]["nombre"],
                         index=claves.index(motor.lugar_actual(p)) if motor.lugar_actual(p) in claves else 0)
    if st.button("Ir ahora", type="primary", use_container_width=True):
        ss.pop("salida", None)
        if con_quien:
            grupo = [PERSONAJES[k] for k in [pid] + con_quien]
            motor.empezar_grupo(grupo, p, sitio)
            ss.modo, ss.modo_pid, ss.grupo = "grupo", pid, [pid] + con_quien
            enviar_grupo(f"*Llego al sitio donde habíamos quedado ({p['lugares'][sitio]['nombre']}) y os veo*", grupo)
        else:
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
    if motor.debe_esperar(p, texto):
        # Está trabajando o durmiendo: tu mensaje le llega, pero contestará más tarde
        if not memoria.historial(pid):
            memoria.guardar_mensaje(pid, "assistant", p["saludo"])
        if imagen:
            memoria.guardar_mensaje(pid, "foto_usuario", "data:image/jpeg;base64," + base64.b64encode(imagen).decode())
        if texto:
            memoria.guardar_mensaje(pid, "user", texto)
        motor.programar_respuesta(p)
        f = motor.actividad(p)
        ss.avisos = [f"⏳ {p['nombre']} está {f['actividad'] if f else 'ocupado/a'}. Te contestará más tarde."]
        st.rerun()
    enviar(texto, "chat", imagen=imagen)
