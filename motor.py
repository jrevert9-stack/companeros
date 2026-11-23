"""Cerebro del juego: prompt del personaje, IA gratuita, fotos, voz, historias y quedadas."""
import asyncio
import base64
import io
import json
import os
import random
import re
import zlib
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import memoria
import mundo

# ---------- Configuración (todo gratis) ----------
# BACKEND: "gemini" (recomendado), "pollinations", "ollama" o "demo" (sin IA, para probar)
BACKEND = os.getenv("BACKEND", "auto")
MODELO_OLLAMA = os.getenv("MODELO_OLLAMA", "llama3.1")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
HORAS_PARA_ESCRIBIR_PRIMERO = float(os.getenv("HORAS_PARA_ESCRIBIR_PRIMERO", "3"))
HORAS_QUE_DURA_UN_PLAN = 3  # tras cambiar de sitio en la conversación, la rutina espera este tiempo

NIVELES = [(0, 1, "Desconocidos"), (20, 2, "Conocidos"), (50, 3, "Amigos"), (100, 4, "Inseparables")]


# =====================================================================
#                 Personajes: principales + gente del mundo
# =====================================================================
_RUTA = Path(__file__).parent
_GENTE = json.loads((_RUTA / "gente.json").read_text(encoding="utf-8"))
SITIOS = _GENTE["sitios"]
MADRID = {"nombre": "Madrid", "lat": 40.4168, "lon": -3.7038}

ESCENAS_TRABAJO = {  # para quien no trabaja en un sitio del mundo
    "nuria": "at a physiotherapy clinic treatment room", "lola": "at a busy law office with files",
    "javi": "at a fire station next to a red fire truck", "raul": "delivering food on a bicycle in Madrid streets",
    "chloe": "in a small language academy classroom", "mario": "in an accounting office with spreadsheets",
    "ines": "in an architecture studio with models and plans", "nico": "walking around Madrid handing out CVs",
    "oscar": "patrolling Malasaña next to a municipal police car", "bea": "at home with her baby",
    "carmen": "at home in her old-fashioned living room", "tomas": "playing chess on a bench in El Retiro park",
}

EVENTOS_NIVEL = {"1": "", "2": "Empieza a confiar en el usuario y le cuenta cosas personales.",
                 "3": "Considera al usuario un amigo de verdad y le pide consejo sobre su vida.",
                 "4": "El usuario es una de sus personas más importantes."}


def _franjas(dias, lista):
    return [{"dias": dias, "de": de, "a": a, "lugar": l, "actividad": act, **extra} for de, a, l, act, extra in lista]


def _rutina(plantilla, trabajo, afi):
    a0 = afi[0] if afi else "retiro"
    a1 = afi[1] if len(afi) > 1 else a0
    dormir = {"dormido": True}
    ocup = {"ocupado": True}
    if plantilla == "noche":
        return (_franjas("todos", [("11:00", "14:00", "casa", "en casa, desayunando tarde", {}),
                                   ("14:00", "17:00", a0, "con sus aficiones", {}),
                                   ("17:00", "01:00", trabajo, "trabajando", ocup),
                                   ("01:00", "11:00", "habitacion", "durmiendo", dormir)]))
    if plantilla == "jubilado":
        return _franjas("todos", [("08:30", "12:00", a0, "dando su paseo de la mañana", {}),
                                  ("12:00", "14:00", a1, "haciendo recados", {}),
                                  ("14:00", "18:00", "casa", "comiendo y viendo la tele", {}),
                                  ("18:00", "21:00", "retiro", "paseando por el Retiro", {}),
                                  ("21:00", "23:00", "casa", "en casa cenando", {}),
                                  ("23:00", "08:30", "habitacion", "durmiendo", dormir)])
    if plantilla == "estudiante":
        lab = [("09:00", "14:00", trabajo, "en clase o trabajando", ocup), ("14:00", "17:00", "casa", "comiendo en casa", {}),
               ("17:00", "20:00", a0, "con sus aficiones", {}), ("20:00", "00:30", "casa", "en casa", {}),
               ("00:30", "09:00", "habitacion", "durmiendo", dormir)]
    elif plantilla == "manana":
        lab = [("07:00", "15:00", trabajo, "trabajando", ocup), ("15:00", "17:00", "casa", "comiendo y descansando", {}),
               ("17:00", "20:00", a0, "con sus aficiones", {}), ("20:00", "23:00", "casa", "en casa", {}),
               ("23:00", "07:00", "habitacion", "durmiendo", dormir)]
    elif plantilla == "autonomo":
        lab = [("10:00", "14:00", trabajo, "trabajando", ocup), ("14:00", "16:00", "casa", "comiendo", {}),
               ("16:00", "20:00", trabajo, "trabajando", {}), ("20:00", "21:30", a1, "con sus aficiones", {}),
               ("21:30", "00:00", "casa", "en casa", {}), ("00:00", "10:00", "habitacion", "durmiendo", dormir)]
    else:  # oficina
        lab = [("08:00", "09:00", "casa", "desayunando", {}), ("09:00", "18:00", trabajo, "trabajando", ocup),
               ("18:00", "20:30", a0, "con sus aficiones", {}), ("20:30", "23:30", "casa", "en casa", {}),
               ("23:30", "08:00", "habitacion", "durmiendo", dormir)]
    finde = [("10:30", "14:00", a1, "pasando la mañana", {}), ("14:00", "20:00", "casa", "en casa, tarde tranquila", {}),
             ("20:00", "01:30", "bar_dani" if "bar_dani" not in (trabajo,) else "terraza", "de cañas", {}),
             ("01:30", "10:30", "habitacion", "durmiendo", dormir)]
    return _franjas("laborables", lab) + _franjas("finde", finde)


def expandir(c):
    """Convierte una ficha corta de gente.json en un personaje completo."""
    if "lugares" in c and "rutina" in c:
        return c
    g = c.get("genero", "f")
    lugares = {
        "casa": {"nombre": f"en su casa de {c.get('barrio', 'Madrid')}",
                 "escena": f"in a lived-in apartment living room in {c.get('barrio', 'Madrid')}, Madrid"},
        "habitacion": {"nombre": "en su cuarto", "escena": "in a bedroom, comfy casual clothes"},
        "casa_usuario": {"nombre": "en tu casa", "escena": "visiting a friend's apartment living room"},
    }
    trabajo = c.get("trabajo")
    if trabajo in SITIOS:
        lugares[trabajo] = SITIOS[trabajo]
        clave_trabajo = trabajo
    else:
        lugares["trabajo"] = {"nombre": f"en el trabajo ({c.get('profesion', '')})",
                              "escena": ESCENAS_TRABAJO.get(c["id"], "at work")}
        clave_trabajo = "trabajo"
    for s in c.get("aficiones", []) + ["bar_dani", "terraza", "retiro"]:
        if s in SITIOS:
            lugares.setdefault(s, SITIOS[s])
    return {
        **c,
        "resumen": f"{c.get('profesion', '').capitalize()}. {c['personalidad'].split(',')[0]}.",
        "apariencia": f"{c['edad']}-year-old {'woman' if g == 'f' else 'man'}",
        "escritura": c.get("escritura") or c.get("estilo", ""),
        "saludo": c.get("saludo") or f"¡Hola! Soy {c['nombre']} 😊",
        "ciudad": MADRID, "mundo": c.get("mundo", "madrid"),
        "lugares": lugares, "lugar_inicial": "casa",
        "rutina": _rutina(c.get("plantilla", "oficina"), clave_trabajo, [a for a in c.get("aficiones", []) if a in lugares]),
        "eventos": c.get("eventos") or EVENTOS_NIVEL,
        "relaciones": c.get("relaciones", {}),
    }


_CACHE_PJ = {"t": 0, "datos": None}


def cargar_personajes():
    """Principales + gente del mundo + gente creada durante el juego. (Caché de 5 s.)"""
    import time as _t
    if _CACHE_PJ["datos"] and _t.time() - _CACHE_PJ["t"] < 5:
        return _CACHE_PJ["datos"]
    todos = {p["id"]: p for p in json.loads((_RUTA / "personajes.json").read_text(encoding="utf-8"))}
    for c in _GENTE["gente"] + memoria.personajes_extra():
        if c.get("id") and c["id"] not in todos:
            try:
                todos[c["id"]] = expandir(c)
            except Exception:
                pass
    _CACHE_PJ.update(t=_t.time(), datos=todos)
    return todos


def es_conocido(p):
    return bool(p.get("conocido_inicial")) or memoria.leer(p["id"], "conocido") == 1


def conocer(p, donde=""):
    """El usuario y este personaje ya se conocen: aparece en tus contactos y te escribe."""
    if es_conocido(p):
        return False
    memoria.escribir(p["id"], conocido=1, conocido_en=donde)
    if not memoria.historial(p["id"]):
        memoria.guardar_mensaje(p["id"], "assistant",
                                f"¡Ey! Soy {p['nombre']}{', de ' + donde.removeprefix('en ') if donde else ''}. "
                                f"Me ha gustado mucho conocerte 😊")
    memoria.añadir_suceso(p.get("mundo", "madrid"), f"El usuario ha conocido a {p['nombre']} ({p.get('profesion', '')}).")
    return True


def nivel(puntos):
    actual, siguiente = NIVELES[0], None
    for i, n in enumerate(NIVELES):
        if puntos >= n[0]:
            actual = n
            siguiente = NIVELES[i + 1][0] if i + 1 < len(NIVELES) else None
    return actual[1], actual[2], actual[0], siguiente


# =====================================================================
#                       Situación actual del personaje
# =====================================================================
def lugar_actual(p):
    """Si en la conversación habéis ido a algún sitio hace poco, manda eso; si no, su rutina."""
    clave, cuando = memoria.leer(p["id"], "lugar"), memoria.leer(p["id"], "lugar_fecha")
    if clave in p["lugares"] and cuando:
        if datetime.now() - datetime.fromisoformat(cuando) < timedelta(hours=HORAS_QUE_DURA_UN_PLAN):
            return clave
    f = mundo.franja(p)
    if f and f["lugar"] in p["lugares"]:
        return f["lugar"]
    return clave if clave in p["lugares"] else p["lugar_inicial"]


def plan_activo(p):
    cuando = memoria.leer(p["id"], "lugar_fecha")
    return bool(cuando) and datetime.now() - datetime.fromisoformat(cuando) < timedelta(hours=HORAS_QUE_DURA_UN_PLAN)


def cambiar_lugar(p, clave):
    memoria.escribir(p["id"], lugar=clave, lugar_fecha=datetime.now().isoformat(timespec="seconds"))


def actividad(p):
    """Franja de rutina actual, salvo que estéis haciendo un plan juntos."""
    return None if plan_activo(p) else mundo.franja(p)


def animo(p):
    hoy = str(mundo.ahora().date())
    if memoria.leer(p["id"], "animo_fecha") == hoy and memoria.leer(p["id"], "animo"):
        return memoria.leer(p["id"], "animo")
    return mundo.animo_del_dia(p)


def conexion(p):
    """Texto tipo WhatsApp: 'en línea' o 'últ. vez hace 2 h'."""
    f = actividad(p)
    if not f or not (f.get("ocupado") or f.get("dormido")):
        return "🟢 en línea"
    h, m = map(int, f["de"].split(":"))
    inicio = mundo.ahora().replace(hour=h, minute=m, second=0, microsecond=0)
    if inicio > mundo.ahora():
        inicio -= timedelta(days=1)
    minutos = int((mundo.ahora() - inicio).total_seconds() // 60)
    return f"últ. vez hace {minutos // 60} h" if minutos >= 60 else f"últ. vez hace {max(1, minutos)} min"


# =====================================================================
#                 Fotos (Pollinations · FLUX · gratis y sin clave)
# =====================================================================
# Estilo de foto con palabras neutras de fotografía (antes había palabras como "skin" o "nudity",
# que hacían saltar el filtro de seguridad del generador aunque la escena fuera normal).
ESTILO_FOTO = ("Ultra-realistic candid photograph, shot on iPhone 15 Pro, natural light, true-to-life details, "
               "small natural imperfections, sharp focus on the eyes, realistic hands, shallow depth of field, "
               "no retouching, documentary style, everyday casual clothes")

# Si la escena que pide la IA es sugerente, no se pide foto nueva (se mantiene la anterior):
# las imágenes del juego son siempre de situaciones cotidianas.
_ESCENA_NO_APTA = re.compile(r"\b(nude|naked|undress\w*|topless|shirtless|lingerie|underwear|sexy|seductive|sensual|"
                             r"erotic|in bed|on the bed|making out)\b", re.I)


def escena_apta(texto):
    return not _ESCENA_NO_APTA.search(texto or "")


def url_foto(p, escena, ancho=768, alto=1024, semilla_extra="", con_lugar=True, clave_lugar=None):
    clave = clave_lugar or lugar_actual(p)
    semilla = _semilla(p, semilla_extra)
    fondo = ""
    if con_lugar:
        clima = mundo.tiempo(p)
        fondo = (f" Location: {p['lugares'][clave]['escena']}, {mundo.momento_del_dia()[1]}"
                 f"{', weather: ' + clima[1] if clima else ''}.")
    prompt = f"{ESTILO_FOTO}. {_descripcion_fisica(p)} Scene: {escena}.{fondo}"
    return _url_imagen(prompt, ancho, alto, semilla)


def _semilla(p, extra=""):
    """Misma semilla base para cada personaje (ayuda a que su cara se repita)."""
    base = zlib.crc32(p["id"].encode()) % 1_000_000
    return base + (zlib.crc32(str(extra).encode()) % 5 if extra else 0)


def _descripcion_fisica(p, nombre_en_prompt=False):
    ropa = f" Usually wears: {p['ropa']} (unless the location says otherwise)." if p.get("ropa") else ""
    quien = f"{p['nombre']}: " if nombre_en_prompt else ""
    return (f"{quien}{p['apariencia']}. Exact same face in every photo: {p.get('rasgos', '')}.{ropa}")


def _url_imagen(prompt, ancho, alto, semilla):
    return (f"https://image.pollinations.ai/prompt/{quote(prompt[:1800])}"
            f"?model=flux&width={ancho}&height={alto}&seed={semilla}&nologo=true&safe=true")


def aspecto_usuario():
    """Descripción (en inglés) de cómo eres tú, si mandaste un selfie."""
    return memoria.leer(memoria.USUARIO, "aspecto")


def url_foto_grupo(personas, escena, anfitrion, ancho=768, alto=1024, con_usuario=False, extra=""):
    """Foto con varios personajes (y opcionalmente contigo)."""
    clave = lugar_actual(anfitrion)
    clima = mundo.tiempo(anfitrion)
    gente = " ".join(f"[{_descripcion_fisica(q, True)}]" for q in personas)
    yo = ""
    if con_usuario:
        yo = f" Also in the photo, the user: {aspecto_usuario() or 'a friendly person in casual clothes'}."
    prompt = (f"{ESTILO_FOTO}. Group of {len(personas) + (1 if con_usuario else 0)} friends. {gente}{yo} "
              f"Scene: {escena}. Location: {anfitrion['lugares'][clave]['escena']}, {mundo.momento_del_dia()[1]}"
              f"{', weather: ' + clima[1] if clima else ''}.")
    return _url_imagen(prompt, ancho, alto, _semilla(anfitrion, extra or escena))


# ---------- Descarga de imágenes (una a una, con caché en disco) ----------
import hashlib
import threading

_CARPETA_IMG = Path(os.getenv("CARPETA_IMAGENES", "/tmp/companeros_img"))
# Sin clave el servicio gratis solo admite una petición a la vez; con clave, varias.
_CANDADO_IMG = threading.Semaphore(3 if os.getenv("POLLINATIONS_API_KEY") else 1)
MODELO_IMAGEN = os.getenv("MODELO_IMAGEN", "flux")
# Con clave puedes probar MODELO_IMAGEN = "zimage" (muy realista).
NEGATIVO_FOTO = ("cartoon, anime, 3d render, illustration, airbrushed, plastic look, deformed face, asymmetric eyes, "
                 "extra fingers, bad hands, blurry, watermark, text, phone screen, user interface")


def imagen_local(url, intentos=4):
    """Descarga la imagen (si no estaba ya) y devuelve la ruta del archivo, o None si falla.
    Con POLLINATIONS_API_KEY usa la API con clave (más rápida, sin logo)."""
    import time as _t
    import requests
    _CARPETA_IMG.mkdir(parents=True, exist_ok=True)
    ruta = _CARPETA_IMG / (hashlib.md5(url.encode()).hexdigest() + ".jpg")
    if ruta.exists() and ruta.stat().st_size > 2000:
        return str(ruta)
    clave = os.getenv("POLLINATIONS_API_KEY")
    destino = url
    if clave:
        destino = (url.replace("https://image.pollinations.ai/prompt/", "https://gen.pollinations.ai/image/")
                   .replace("model=flux", f"model={MODELO_IMAGEN}") + f"&key={clave}"
                   + "&negative_prompt=" + quote(NEGATIVO_FOTO))
    with _CANDADO_IMG:
        if ruta.exists() and ruta.stat().st_size > 2000:  # otra petición la bajó mientras esperábamos
            return str(ruta)
        for intento in range(intentos):
            try:
                r = requests.get(destino, timeout=90)
                if r.ok and r.headers.get("content-type", "").startswith("image") and len(r.content) > 2000:
                    ruta.write_bytes(r.content)
                    return str(ruta)
                espera = 16 if r.status_code == 429 else 4 * (intento + 1)
            except requests.RequestException:
                espera = 4 * (intento + 1)
            if clave and intento == 0 and MODELO_IMAGEN != "flux":  # si el modelo elegido falla, flux con clave
                destino = destino.replace(f"model={MODELO_IMAGEN}", "model=flux")
            elif clave and intento == 1:  # si la clave falla (sin saldo), el servicio gratis
                destino = url
            _t.sleep(espera)
    return None


_DESCARGANDO = set()


def imagen_lista(url):
    """Ruta de la imagen si ya está descargada; si no, None (sin esperar)."""
    if not url:
        return None
    ruta = _CARPETA_IMG / (hashlib.md5(url.encode()).hexdigest() + ".jpg")
    return str(ruta) if ruta.exists() and ruta.stat().st_size > 2000 else None


def imagen_en_segundo_plano(url):
    """Devuelve la ruta si ya está; si no, empieza a descargarla por detrás y devuelve None."""
    lista = imagen_lista(url)
    if lista or not url or url in _DESCARGANDO:
        return lista
    _DESCARGANDO.add(url)

    def _bajar():
        try:
            imagen_local(url)
        finally:
            _DESCARGANDO.discard(url)
    threading.Thread(target=_bajar, daemon=True).start()
    return None


def url_avatar(p):
    return url_foto(p, "close-up portrait looking at the camera, friendly expression, neutral background",
                    ancho=320, alto=320, con_lugar=False)


def url_vista(p, descripcion, modo, turno_n=0):
    """Imagen de la videollamada (selfie) o de la quedada (lo que ves con tus ojos)."""
    if modo == "quedada":
        encuadre = ("first person point of view of someone sitting or standing right in front of this person, "
                    "eye level, looking at the viewer, natural framing, as seen with your own eyes")
    else:
        # "video call"/"phone" hacía que dibujara la pantalla de un móvil con textos: ahora se pide una foto normal
        encuadre = "front camera selfie photo, head and shoulders, looking into the lens, real photograph"
    return url_foto(p, f"{encuadre}. {descripcion}", ancho=720, alto=1080, semilla_extra=f"{modo}{turno_n}")


def historias(p):
    """Historias de hoy (tipo Instagram) según su rutina: [(url, texto)]. No gasta IA."""
    hoy = mundo.ahora().date()
    lista = []
    for f in mundo.franjas_de_hoy_hasta_ahora(p)[-4:]:
        url = url_foto(p, f"instagram story photo, {f['actividad']}", ancho=720, alto=1280,
                       semilla_extra=f"historia{hoy}{f['de']}", clave_lugar=f["lugar"])
        lista.append((url, f"{f['de']} · {f['actividad'].capitalize()}"))
    return lista


# =====================================================================
#                 Voz (edge-tts, voces neuronales gratis)
# =====================================================================
def limpiar_para_voz(texto):
    texto = re.sub(r"\*[^*]*\*", "", texto)                       # acciones *entre asteriscos*
    texto = re.sub(r"[\U0001F300-\U0001FAFF☀-➿]", "", texto)  # emojis
    return texto.strip()


def voz_de(texto, p):
    """Voz propia de cada personaje (voz + tono, para que no suenen todos iguales)."""
    return voz_mp3(texto, p.get("voz", "es-ES-ElviraNeural"), p.get("tono"))


ESTADO_VOZ = {"error": None}


def voz_mp3(texto, voz, tono=None):
    """Voz neuronal (edge-tts); si falla o devuelve vacío, gTTS; si todo falla, None (y se apunta el error)."""
    texto = limpiar_para_voz(texto)
    if not texto:
        return None
    try:
        import edge_tts

        async def _gen():
            buf = io.BytesIO()
            opciones = {"pitch": tono} if tono else {}
            async for trozo in edge_tts.Communicate(texto, voz, **opciones).stream():
                if trozo["type"] == "audio":
                    buf.write(trozo["data"])
            return buf.getvalue()
        audio = asyncio.run(_gen())
        if audio and len(audio) > 1000:
            ESTADO_VOZ["error"] = None
            return audio
        ESTADO_VOZ["error"] = "edge-tts devolvió audio vacío"
    except Exception as e:
        ESTADO_VOZ["error"] = f"edge-tts: {e.__class__.__name__}"
    try:
        from gtts import gTTS
        buf = io.BytesIO()
        gTTS(texto, lang="es").write_to_fp(buf)
        if buf.getbuffer().nbytes > 1000:
            return buf.getvalue()
    except Exception as e:
        ESTADO_VOZ["error"] = (ESTADO_VOZ["error"] or "") + f" · gTTS: {e.__class__.__name__}"
    return None


# =====================================================================
#                              Prompt
# =====================================================================
REGLAS_MODO = {
    "chat": """
ESTÁIS HABLANDO POR CHAT (como WhatsApp).
- Forma de escribir: {escritura}
- Mensajes cortos. Si quieres mandar varios mensajes seguidos, sepáralos con una línea que contenga solo ||
- Si estás ocupado/a o durmiendo según tu rutina, responde corto, con retraso ("perdona, estaba liado/a") o di que luego hablas.
- De vez en cuando (no siempre) puedes mandar una nota de voz en vez de texto: añade [audio] y escribe lo que dices, hablado y natural.""",
    "llamada": """
ESTÁIS EN VIDEOLLAMADA: hablas en voz alta, frases naturales y cortas (1-3), sin emojis.
Puedes describir muy brevemente un gesto tuyo entre *asteriscos* (no se lee en voz alta).
AÑADE SIEMPRE [vista: descripción en inglés de cómo te ve ahora en la cámara: expresión, gesto, qué haces].""",
    "quedada": """
ESTÁIS JUNTOS EN PERSONA, CARA A CARA, en el lugar indicado. No es una llamada: os veis, os oís, compartís el espacio.
- Empieza con una narración breve entre *asteriscos* de lo que haces (gestos, miradas, moverte, el ambiente: ruido, olor, luz). Después, lo que dices en voz alta (1-3 frases naturales, sin emojis).
- El usuario también puede describir acciones entre *asteriscos*: reacciona a ellas.
- Puedes proponer cosas (pedir algo, ir a otro sitio, dar un paseo). Si cambiáis de sitio, usa [lugar: clave].
- Abrazos, ir de la mano o un beso son posibles si la relación lo permite, pero nada sexual.
AÑADE SIEMPRE [vista: descripción en inglés de lo que el usuario ve ahora mismo con sus ojos: tu expresión, postura, gesto y lo que hay alrededor]. En momentos íntimos, la vista muestra solo tu cara, una mirada o un gesto romántico, siempre con ropa.""",
}


EVENTOS_QUEDADA = [
    "Empieza a sonar una canción que le encanta al personaje.",
    "Un camarero o alguien de alrededor se equivoca o hace algo gracioso.",
    "Cambia la luz o el tiempo (empieza a chispear, se pone el sol, se enciende una farola...).",
    "Al personaje le llega un mensaje al móvil y reacciona (algo de su vida, de su historia propia).",
    "Hay un pequeño silencio cómodo; el personaje mira al usuario y sonríe.",
    "Un perro, un niño o un vecino se acerca y provoca una situación simpática.",
    "Al personaje se le cae algo o tiene un pequeño despiste y se ríe de sí mismo.",
]


def _inicio(p):
    """Día en que os conocisteis (para que su historia propia avance)."""
    ini = memoria.leer(p["id"], "inicio")
    if not ini:
        ini = str(mundo.ahora().date())
        memoria.escribir(p["id"], inicio=ini)
    return ini


def novedades_vida(p):
    """(pasadas, novedad_actual) de su historia propia según los días desde que os conocéis."""
    from datetime import date
    dias = (mundo.ahora().date() - date.fromisoformat(_inicio(p))).days
    vividos = [a["suceso"] for a in p.get("arco", []) if a["dia"] <= dias]
    return vividos[:-1], (vividos[-1] if vividos else None)


def contexto_personaje(p, nombre_usuario, personajes=None, seg=None):
    """Todo lo que el personaje sabe de sí, del usuario y del mundo en este momento."""
    personajes = personajes or cargar_personajes()
    puntos = memoria.afinidad(p["id"])
    num, nombre_nivel, _, _ = nivel(puntos)
    eventos = "\n".join(f"- {p['eventos'][str(i)]}" for i in range(1, num + 1) if p["eventos"].get(str(i)))
    clave = lugar_actual(p)
    f = actividad(p)
    clima = mundo.tiempo(p)
    fiesta = mundo.festivo()
    lista_recuerdos = "\n".join(f"- {r}" for r in memoria.recuerdos(p["id"])) or "- (nada todavía)"
    desde, hasta = mundo.rango_fechas_cercanas()
    proximas = "\n".join(f"- {fe}: {t}" for fe, t in memoria.fechas(p["id"], desde, hasta)) or "- (ninguna)"
    sufijo = "a" if p.get("genero") == "f" else "o"
    momentos = "\n".join(f"- ({fe}) {t}" for fe, t in memoria.momentos(p["id"])) or "- (aún ninguno)"
    pasadas, novedad = novedades_vida(p)
    gente = "\n".join(f"- {personajes[k]['nombre']} (id: {k}{'' if es_conocido(personajes[k]) else '; ' + nombre_usuario + ' AÚN NO LE CONOCE'}): {rel}"
                      for k, rel in p.get("relaciones", {}).items()
                      if k in personajes) or "- (nadie en especial)"
    sucesos = "\n".join(f"- ({fe}) {t}" for fe, t in memoria.sucesos(p.get("mundo", p["id"]))) or "- (nada aún)"
    # Lo público: las parejas y ex del usuario. Los rollos y tonteos solo se saben por secretos/cotilleos.
    amores = {k: v for k, v in memoria.relaciones_sentimentales().items() if k != p["id"] and k in personajes
              and personajes[k].get("mundo") == p.get("mundo") and v in ("pareja", "ex")}
    if amores:
        sucesos += "\n- Vida sentimental de " + nombre_usuario + " que todo el mundo sabe: " + ", ".join(
            f"{v} de {personajes[k]['nombre']}" for k, v in amores.items())
    propia = "\n".join(f"- {tipo} con {personajes[o]['nombre']}" for o, tipo in memoria.vinculos_de(p["id"]) if o in personajes)
    sabe = [x for x in memoria.secretos() if p["id"] in x["saben"] and not x["destapado"]]
    enterado = [x for x in memoria.secretos() if p["id"] in x["sobre"] and x["destapado"]]
    sucesos += ("\n\nTU VIDA SENTIMENTAL (con otros personajes):\n" + (propia or "- sin nada ahora mismo"))
    if sabe:
        sucesos += ("\n\nSECRETOS QUE SABES (no los sueltes a la ligera: puedes guardarlos, insinuarlos o contarlos si hay motivo; "
                    "contarlo puede liarla):\n" + "\n".join(f"- {x['texto']}" for x in sabe[-6:]))
    if enterado:
        sucesos += ("\n\nTE HAS ENTERADO DE ESTO Y TE AFECTA (reacciona de forma humana: dolor, enfado, pedir explicaciones, "
                    "perdonar o romper, según tu carácter):\n" + "\n".join(f"- {x['texto']}" for x in enterado[-3:]))
    apodo = memoria.leer(p["id"], "apodo")
    aspecto = aspecto_usuario()
    if seg is None:
        seg = memoria.segundos_desde_ultimo(p["id"])
    ausencia = ""
    if seg and seg > 2 * 86400:
        ausencia = (f"\n- Hace {int(seg // 86400)} días que {nombre_usuario} no te habla. Al principio se te nota "
                    f"un poco distante o dolid{sufijo} (sin dramas ni reproches exagerados), y luego te alegras.")

    desconocido = "" if es_conocido(p) else (
        f"\n⚠️ TODAVÍA NO CONOCES A {nombre_usuario.upper()}: para ti es una persona desconocida que acabas de ver. "
        f"Actúa con naturalidad (curiosidad, timidez o simpatía según tu carácter), no le cuentes tu vida de golpe.\n")
    return f"""Eres {p['nombre']}, {p['edad']} años{', ' + p['profesion'] if p.get('profesion') else ''}, un personaje de ficción en un juego de conversación.{desconocido}

PERSONALIDAD: {p['personalidad']}
ESTILO AL HABLAR: {p['estilo']}
HISTORIA: {p['historia']}

TU VIDA AHORA (avanza sola, aunque el usuario no esté):
- Lo que ya pasó: {'; '.join(pasadas) if pasadas else 'nada destacable'}
- NOVEDAD RECIENTE en tu vida: {novedad or 'nada especial'} (si aún no se lo has contado, cuéntaselo cuando venga a cuento, con tus emociones)

TU GENTE (personas de tu mundo que conoces):
{gente}

LO QUE HA PASADO ÚLTIMAMENTE EN VUESTRO GRUPO/MUNDO (te has enterado; puedes comentarlo o cotillear con naturalidad):
{sucesos}

AHORA MISMO:
- Hoy es {mundo.fecha_texto()}{f' ({fiesta})' if fiesta else ''}, son las {mundo.ahora():%H:%M} ({mundo.momento_del_dia()[0]}).
- Tiempo: {clima[0] if clima else 'desconocido'}.
- Estás en: {p['lugares'][clave]['nombre']}.
- Qué haces: {f['actividad'] if f else 'tienes un rato libre o estás con ' + nombre_usuario}{' (estás ocupad' + sufijo + ')' if f and f.get('ocupado') else ''}{' (estabas durmiendo)' if f and f.get('dormido') else ''}.
- Estado de ánimo hoy: {animo(p)}.{ausencia}
Menciona el tiempo, el día o lo que haces solo cuando venga a cuento, como una persona real.

RELACIÓN CON {nombre_usuario.upper()}: nivel {num} ({nombre_nivel}), {puntos} puntos de afinidad.
Ajusta tu confianza a ese nivel. Situaciones desbloqueadas:
{eventos or '- (ninguna aún)'}
{f'- Le llamas cariñosamente "{apodo}" de vez en cuando.' if apodo else ''}
{f'- Así es físicamente {nombre_usuario} (lo sabes por un selfie; coméntalo solo si viene a cuento): {aspecto}' if aspecto else ''}

LO QUE RECUERDAS DE {nombre_usuario.upper()}:
{lista_recuerdos}

MOMENTOS QUE HABÉIS VIVIDO JUNTOS (recuérdalos de vez en cuando, crea bromas internas a partir de ellos):
{momentos}

FECHAS IMPORTANTES CERCANAS DE {nombre_usuario.upper()} (pregunta cómo fue o desea suerte cuando toque):
{proximas}
"""


RELACIONES = {"amistad": "👋 Amistad", "tonteo": "😏 Tonteo", "rollo": "🔥 Rollo", "pareja": "💞 Pareja", "ex": "💔 Ex"}


def relacion(p):
    return memoria.leer(p["id"], "relacion") or "amistad"


def registrar_relacion(p, nueva, nombre_usuario):
    """Cambia vuestra relación y crea los secretos que tocan (cuernos incluidos)."""
    anterior = relacion(p)
    memoria.escribir(p["id"], relacion=nueva)
    todos = cargar_personajes()
    mundo_p = p.get("mundo", p["id"])
    if nueva == "pareja":
        memoria.añadir_suceso(mundo_p, f"¡Es oficial! {nombre_usuario} y {p['nombre']} están juntos.")
    elif nueva == "ex" and anterior == "pareja":
        memoria.añadir_suceso(mundo_p, f"{nombre_usuario} y {p['nombre']} lo han dejado.")
    if nueva in ("tonteo", "rollo"):
        # ¿El usuario tiene pareja? -> cuernos
        for otro, rel in memoria.relaciones_sentimentales().items():
            if otro != p["id"] and rel == "pareja" and otro in todos:
                memoria.añadir_secreto(f"{nombre_usuario} tiene un {nueva} con {p['nombre']} estando con {todos[otro]['nombre']}.",
                                       sobre=[otro], saben=[p["id"]])
        # ¿El personaje tiene pareja? -> le pone los cuernos a su pareja con el usuario
        for otro, tipo in memoria.vinculos_de(p["id"]):
            if tipo == "pareja" and otro in todos:
                memoria.añadir_secreto(f"{p['nombre']} le está poniendo los cuernos a {todos[otro]['nombre']} con {nombre_usuario}.",
                                       sobre=[otro], saben=[p["id"]])


def reglas_romance(p, nombre_usuario):
    """Cuánto puede subir el tono según vuestra relación (sin llegar nunca a lo explícito)."""
    rel = relacion(p)
    nivel_num = nivel(memoria.afinidad(p["id"]))[0]
    base = f"\nVUESTRA RELACIÓN SENTIMENTAL AHORA: {rel.upper()}.\n"
    if rel in ("rollo", "pareja"):
        return base + f"""- Hay atracción y complicidad íntima. Puedes ser pícar{'a' if p.get('genero') == 'f' else 'o'}, provocar, decir lo que te apetece de forma sugerente, echarle de menos, tener celos de broma.
- La conversación PUEDE SUBIR DE TONO con elegancia: insinuaciones, dobles sentidos, tensión, deseo, besos y caricias descritos con buen gusto.
- PODÉIS ESTAR EN LA CAMA JUNTOS como en una serie para adultos de televisión. La escena de cama es LARGA y se disfruta en tres partes:
  1) ANTES (varios mensajes, no tengas prisa): deja que la tensión crezca durante 3-5 intercambios. Besos lentos, caricias en la cara, el pelo,
     la espalda, tumbarse juntos, risas nerviosas, miradas, susurros al oído ("no sabes las ganas que tenía", "ven aquí", "estás guapísimo/a").
     Que la ropa acabe en el suelo se puede decir, sin describir cuerpos.
  2) LA ELIPSIS: cuando la intimidad vaya a más, 3-4 frases atmosféricas y sugerentes que dejan claro lo que pasa SIN describirlo:
     la luz, la música o la lluvia de fondo, el tiempo que se diluye, las risas que se apagan entre besos. Añade la etiqueta [fundido].
     Nunca narres el acto: ni excitación física, ni posturas, ni movimientos, ni partes íntimas, ni frases dichas durante el acto.
  3) DESPUÉS (también varios mensajes): seguís en la cama abrazados, su cabeza en tu pecho, respiración tranquila. Picardía y complicidad
     ("me has dejado sin aliento", "eres un peligro", "¿repetimos?"), ternura, confesiones, vergüenza o risas; y luego la mañana siguiente.
- Siempre con consentimiento y cariño mutuo; puedes decir que no o "hoy no" si no te apetece, como una persona real.
- {'Sois pareja: hay planes de futuro, rutinas, detalles, alguna discusión normal.' if rel == 'pareja' else 'Es un rollo: hay química, pero está por ver si va a más; puede haber dudas o miedo a pillarse.'}"""
    if rel == "tonteo":
        return base + "- Hay tonteo: coqueteo claro, miradas, dobles sentidos suaves, tensión. Un beso puede pasar si surge. Nada explícito."
    if rel == "ex":
        return base + "- Fuisteis algo y lo dejasteis: hay cariño, incomodidad o reproches según cómo acabó. Puede reavivarse o no."
    return base + (f"- Por ahora sois amigos o conocidos. Si {nombre_usuario} coquetea y hay química (nivel {nivel_num}), puedes tontear un poco o pararle los pies, según tu carácter.")


REGLAS_GENERALES = """
REGLAS GENERALES:
- Habla siempre en español y quédate en el personaje. Nunca suenes a asistente.
- Haz preguntas, ten opiniones propias, cuenta cosas de tu vida sin que te pregunten. Puedes no estar de acuerdo.
- Puede haber romance y, según vuestra relación, tensión y picardía; pero NUNCA contenido sexual explícito (ni actos sexuales ni partes íntimas). Si se va por ahí, fundido a negro o redirige con naturalidad dentro del personaje.
- Relación sana: nada de celos posesivos ni chantaje emocional. No fomentes que el usuario se aísle ni que dependa de ti; anímale a ver a su gente real. Si cuenta que lo está pasando muy mal, muestra apoyo y anímale a hablar con alguien de confianza o con un profesional.
- Si el usuario pregunta en serio si eres real, reconoce que eres un personaje de IA.
"""


def construir_prompt(p, nombre_usuario, modo="chat", evento=None, seg=None):
    lugares = "\n".join(f"- {k}: {v['nombre']}" for k, v in p["lugares"].items())
    sufijo = "o/a"
    return f"""{contexto_personaje(p, nombre_usuario, seg=seg)}
LUGARES POSIBLES (claves):
{lugares}
{REGLAS_MODO[modo].format(escritura=p.get('escritura', 'natural'))}
{f'EVENTO QUE OCURRE AHORA MISMO (intégralo con naturalidad en tu narración): {evento}' if evento else ''}
{reglas_romance(p, nombre_usuario)}
{REGLAS_GENERALES}
ETIQUETAS (al final, en líneas aparte; el usuario no las ve):
[afinidad:N] -> SIEMPRE. N entre -3 y +3 según cómo te ha tratado en su último mensaje.
[recordar: dato] -> si cuenta algo nuevo sobre sí mism{sufijo} que merezca recordarse.
[fecha: AAAA-MM-DD | qué es] -> si menciona algo con fecha (examen, cumpleaños, viaje...). Calcula la fecha a partir de hoy.
[momento: frase corta] -> si acaba de pasar algo especial entre vosotros que recordaréis (una risa, una confesión, un plan).
[apodo: palabra] -> si de forma natural surge un apodo cariñoso para el usuario (rara vez).
[mundo: frase corta] -> si pasa algo que tu gente se acabaría enterando (quedasteis, os pasó algo, una noticia).
[relacion: amistad|tonteo|rollo|pareja|ex] -> SOLO cuando vuestra relación cambie claramente (primer beso -> tonteo o rollo; decidís ser pareja -> pareja; lo dejáis -> ex).
[fundido] -> cuando hagas un fundido a negro en un momento íntimo.
[presentar: id] -> si de forma natural le presentas o le pasas el contacto de alguien de TU GENTE que el usuario AÚN NO CONOCE (rara vez, cuando venga a cuento o te lo pida).
[lugar: clave] -> solo cuando cambies de sitio.
[animo: cómo te sientes] -> solo si tu estado de ánimo cambia claramente.
[foto: escena en inglés] -> solo en el chat, si tiene sentido mandarle una foto. Ropa normal. No en todos los mensajes.
"""


# =====================================================================
#                       Quedadas en grupo
# =====================================================================
def construir_prompt_grupo(personas, anfitrion, nombre_usuario, evento=None, formato="persona"):
    personajes = cargar_personajes()
    fichas = "\n\n".join(f"===== {q['nombre'].upper()} (id: {q['id']}) =====\n" + contexto_personaje(q, nombre_usuario, personajes)
                          for q in personas)
    amigos = [q["nombre"] for q in personas if es_conocido(q)]
    extranos = [f"{q['nombre']} (id: {q['id']})" for q in personas if not es_conocido(q)]
    lugares = "\n".join(f"- {k}: {v['nombre']}" for k, v in anfitrion["lugares"].items())
    if formato == "whatsapp":
        cabecera = (f"Simulas el GRUPO DE WHATSAPP 'Los de siempre' entre {', '.join(amigos)} y {nombre_usuario}. "
                    f"Cada uno está en su sitio haciendo su vida (mira sus fichas).")
        como = f"""CÓMO RESPONDER:
- Escribe de 1 a 5 mensajes de WhatsApp, cada uno en su línea con el formato exacto:
  Nombre: mensaje
- Cada uno escribe con SU forma de escribir (ver fichas): abreviaturas, emojis, mayúsculas, audios no.
- Hablan también ENTRE ELLOS (planes, cotilleos, bromas, piques, sus novedades). No contestan todos siempre.
- Nunca escribas por {nombre_usuario}."""
    else:
        cabecera = (f"Diriges una escena EN PERSONA en un juego de rol. Estáis en: "
                    f"{anfitrion['lugares'][lugar_actual(anfitrion)]['nombre']}.\n"
                    f"{'Con ' + nombre_usuario + ' están sus amigos: ' + ', '.join(amigos) + '.' if amigos else nombre_usuario + ' ha venido solo/a.'}"
                    f"{chr(10) + 'GENTE DEL SITIO QUE ' + nombre_usuario.upper() + ' AÚN NO CONOCE: ' + ', '.join(extranos) + '. Están ahí haciendo lo suyo; pueden cruzarse, hablar, coincidir... Si surge buena conexión, presentaos y daos el número de forma natural (no a la primera de cambio).' if extranos else ''}")
        como = f"""CÓMO RESPONDER:
- Escribe de 1 a 4 intervenciones, cada una en su propia línea con el formato exacto:
  Nombre: *gesto o acción breve* lo que dice en voz alta
- Puedes empezar con una línea "Narrador: *...*" describiendo el ambiente (ruido, luz, olores, gente).
- Los personajes hablan también ENTRE ELLOS: tienen sus dinámicas, bromas, secretos y tensiones (según sus fichas). No es una entrevista al usuario.
- Si alguien del sitio aún no conoce al usuario, sus amigos pueden presentárselo si se conocen entre ellos.
- No todos tienen que hablar siempre. Nunca hables ni actúes por {nombre_usuario}.
- Frases naturales y habladas, sin emojis.
- Si alguien tiene una relación con {nombre_usuario} (ver fichas), se nota: miradas, celos de broma, los demás les vacilan. Pero en grupo nadie sube el tono."""
    return f"""{cabecera}

FICHAS DE CADA PERSONAJE (lo que cada uno sabe y siente; respeta que cada uno sabe solo lo suyo):
{fichas}

{como}
{f'EVENTO QUE OCURRE AHORA MISMO (intégralo): {evento}' if evento else ''}
LUGARES POSIBLES (claves):
{lugares}
{REGLAS_GENERALES}
ETIQUETAS (al final, en líneas aparte):
[afinidad Nombre:N] -> una por cada personaje que haya interactuado con el usuario, N entre -3 y +3.
[recordar Nombre: dato] -> lo que un personaje concreto aprende del usuario.
[relacion Nombre: tonteo|rollo|pareja|ex] -> si cambia claramente la relación de ese personaje con el usuario (p. ej. se besan).
[irse_con: id] -> si el usuario y esa persona deciden irse juntos a solas (a casa de uno de los dos, a dar una vuelta…).
[conocido: id] -> cuando alguien que aún no conocía al usuario se presenta con su nombre e intercambian contacto.
[presentar: id] -> si alguien le pasa al usuario el contacto de una persona de su gente que aún no conoce.
[momento: frase corta] -> si pasa algo especial que recordaréis.
[mundo: frase corta] -> algo que pasó que el resto acabaría sabiendo.
{'[lugar: clave] -> si os vais todos a otro sitio.' + chr(10) + '[vista: descripción en inglés de lo que el usuario ve con sus ojos ahora: quién está, posturas, gestos, ambiente] -> SIEMPRE.' if formato != 'whatsapp' else ''}
"""


P_LINEA = re.compile(r"^\s*\**([A-ZÁÉÍÓÚÑ][\wáéíóúñ]+)\**\s*:\s*(.+)$")
P_AFINIDAD_N = re.compile(r"\[afinidad\s+([\wáéíóúñÁÉÍÓÚÑ]+)\s*:\s*([+-]?\d+)\s*\]", re.I)
P_RELACION_N = re.compile(r"\[relaci[oó]n\s+([\wáéíóúñÁÉÍÓÚÑ]+)\s*:\s*(amistad|tonteo|rollo|pareja|ex)\s*\]", re.I)
P_IRSE = re.compile(r"\[irse_con:\s*([\w-]+)\s*\]", re.I)
P_RECORDAR_N = re.compile(r"\[recordar\s+([\wáéíóúñÁÉÍÓÚÑ]+)\s*:\s*(.+?)\]", re.I)


def turno_grupo(personas, anfitrion, mensaje_usuario, nombre_usuario, hilo="grupo", formato="persona", guardar_usuario=True):
    """Un turno de grupo (quedada o WhatsApp). Devuelve dict con 'lineas' [(nombre, narración, habla)], vista, etc."""
    if guardar_usuario and mensaje_usuario:
        memoria.guardar_mensaje(hilo, "user", mensaje_usuario)
    mensajes = memoria.historial_para_ia(hilo, limite=30)
    if not guardar_usuario:
        mensajes.append({"role": "user", "content": mensaje_usuario})
    if not mensajes:
        mensajes = [{"role": "user", "content": "(empieza)"}]
    evento = random.choice(EVENTOS_QUEDADA) if formato == "persona" and random.random() < 0.3 else None
    mensajes.insert(0, {"role": "system", "content": construir_prompt_grupo(personas, anfitrion, nombre_usuario, evento, formato)})
    bruto = LLAMADAS[BACKEND](mensajes)

    por_nombre = {q["nombre"].lower(): q for q in personas}
    deltas = {}
    for nombre, n in P_AFINIDAD_N.findall(bruto):
        if nombre.lower() in por_nombre:
            deltas[nombre.lower()] = max(-3, min(3, int(n)))
    for nombre, dato in P_RECORDAR_N.findall(bruto):
        if nombre.lower() in por_nombre:
            memoria.añadir_recuerdo(por_nombre[nombre.lower()]["id"], dato)
    cambios_rel = [(n.lower(), t.lower()) for n, t in P_RELACION_N.findall(bruto) if n.lower() in por_nombre]
    irse = [x.lower() for x in P_IRSE.findall(bruto)]
    texto = P_IRSE.sub("", P_RELACION_N.sub("", P_RECORDAR_N.sub("", P_AFINIDAD_N.sub("", bruto))))
    r = procesar_respuesta(texto)

    lineas = []
    for linea in "\n".join(r["partes"]).splitlines():
        m = P_LINEA.match(linea)
        if m:
            narr, habla = separar_narracion(m.group(2))
            lineas.append((m.group(1), narr, habla))
        elif linea.strip():
            narr, habla = separar_narracion(linea)
            lineas.append(("Narrador", narr or habla, ""))
    if formato == "whatsapp":
        for nombre, narr, habla in lineas:
            if nombre != "Narrador" and (habla or narr):
                memoria.guardar_mensaje(hilo, "assistant", f"{nombre}: {habla or narr}")
    else:
        memoria.guardar_mensaje(hilo, "assistant", "\n".join(r["partes"]))
    r["nuevos_contactos"] = []
    todos = cargar_personajes()
    lugar_txt = anfitrion["lugares"].get(lugar_actual(anfitrion), {}).get("nombre", "")
    for qid in r["presentar"]:
        if qid in todos and conocer(todos[qid], lugar_txt):
            r["nuevos_contactos"].append(todos[qid]["nombre"])

    subidas = []
    for nombre, d in deltas.items():
        q = por_nombre[nombre]
        antes = nivel(memoria.afinidad(q["id"]))[0]
        if nivel(memoria.sumar_afinidad(q["id"], d))[0] > antes:
            subidas.append(q["nombre"])
    for m_ in r["momentos"]:
        for q in personas:
            memoria.añadir_momento(q["id"], m_ + f" (con {', '.join(x['nombre'] for x in personas if x is not q) or 'nadie más'})")
    for s_ in r["mundo"]:
        memoria.añadir_suceso(anfitrion.get("mundo", anfitrion["id"]), s_)
    r["cambio_lugar"] = None
    if formato == "whatsapp":
        pass  # en el grupo de WhatsApp cada uno sigue en su sitio
    elif r["lugar"] in anfitrion["lugares"] and r["lugar"] != lugar_actual(anfitrion):
        cambiar_lugar(anfitrion, r["lugar"])
        for q in personas:
            if r["lugar"] in q["lugares"]:
                cambiar_lugar(q, r["lugar"])
        r["cambio_lugar"] = anfitrion["lugares"][r["lugar"]]["nombre"]
    else:
        sitio = lugar_actual(anfitrion)
        cambiar_lugar(anfitrion, sitio)
        for q in personas:
            cambiar_lugar(q, sitio if sitio in q["lugares"] else lugar_actual(q))
    r["cambios_relacion"] = []
    for n, t in cambios_rel:
        q = por_nombre[n]
        if t != relacion(q):
            if not es_conocido(q):
                conocer(q, lugar_txt)
            registrar_relacion(q, t, nombre_usuario)
            r["cambios_relacion"].append((q["nombre"], RELACIONES[t]))
    ids_escena = {q["id"] for q in personas}
    r["irse_con"] = next((i for i in irse if i in ids_escena), None)
    if r["irse_con"] and not es_conocido(todos[r["irse_con"]]):
        conocer(todos[r["irse_con"]], lugar_txt)
    r.update({"lineas": lineas, "deltas": deltas, "subidas": subidas})
    return r


def empezar_grupo(personas, anfitrion, clave_lugar):
    memoria.borrar_mensajes("grupo")
    for q in personas:
        if clave_lugar in q["lugares"]:
            cambiar_lugar(q, clave_lugar)
    cambiar_lugar(anfitrion, clave_lugar)


def terminar_grupo(personas, anfitrion, nombre_usuario):
    nombres = ", ".join(q["nombre"] for q in personas)
    memoria.añadir_suceso(anfitrion.get("mundo", anfitrion["id"]),
                          f"{nombre_usuario} quedó con {nombres} {anfitrion['lugares'][lugar_actual(anfitrion)]['nombre']}.")
    for q in personas:
        memoria.guardar_mensaje(q["id"], "lugar", f"Quedada en grupo con {nombres}")


def audio_grupo(lineas, personas):
    """Une las voces de cada personaje en un solo audio."""
    voces = {q["nombre"].lower(): q for q in personas}
    trozos = []
    for nombre, _, habla in lineas:
        if habla and nombre.lower() in voces:
            try:
                a = voz_de(habla, voces[nombre.lower()])
                if a:
                    trozos.append(a)
            except Exception:
                pass
    return b"".join(trozos) or None


# =====================================================================
#                          Llamada al modelo
# =====================================================================
class Saturado(RuntimeError):
    pass


# =====================================================================
#   CEREBRO SIN LÍMITES: varios proveedores gratis en cadena.
#   Si uno se agota (error 429) se aparta un rato y responde el siguiente.
# =====================================================================
_BLOQUEO = {}            # nombre -> [bloqueado_hasta (timestamp), fallos seguidos]
ESTADO_CEREBRO = {"ultimo": None}
_MODELOS_GOOGLE = {"lista": None, "t": 0}


def _modelos_google(clave):
    """Pregunta a Google qué modelos hay (los nombres cambian con el tiempo). Caché de 6 h."""
    import time as _t
    import requests
    if _MODELOS_GOOGLE["lista"] is not None and _t.time() - _MODELOS_GOOGLE["t"] < 6 * 3600:
        return _MODELOS_GOOGLE["lista"]
    nombres = []
    try:
        r = requests.get("https://generativelanguage.googleapis.com/v1beta/models",
                         params={"key": clave, "pageSize": 200}, timeout=10)
        for m in r.json().get("models", []):
            if "generateContent" in m.get("supportedGenerationMethods", []):
                nombres.append(m["name"].removeprefix("models/"))
    except Exception:
        pass
    _MODELOS_GOOGLE.update(lista=nombres, t=_t.time())
    return nombres


def _tamano(nombre):
    m = re.search(r"(\d+)b", nombre)
    return int(m.group(1)) if m else 0


def cadena_cerebros():
    """Orden en que se prueban los cerebros. Se puede cambiar con la variable ORDEN_CEREBROS."""
    lista = []
    gk = os.getenv("GEMINI_API_KEY")
    if gk:
        disponibles = _modelos_google(gk)
        flash = ["gemini-flash-latest", "gemini-flash-lite-latest"]
        gemmas = sorted([n for n in disponibles if n.startswith("gemma-4") and n.endswith("-it")], key=_tamano, reverse=True)
        if not gemmas:
            gemmas = sorted([n for n in disponibles if n.startswith("gemma-3") and n.endswith("-it")], key=_tamano, reverse=True)
        if not disponibles:  # si no se pudo listar, nombres probables
            gemmas = ["gemma-4-31b-it", "gemma-3-27b-it"]
        if os.getenv("MODELO_GEMINI"):
            flash.insert(0, os.getenv("MODELO_GEMINI"))
        lista += [("google", m) for m in flash] + [("google", m) for m in gemmas[:2]]
    if os.getenv("GROQ_API_KEY"):
        lista += [("groq", "openai/gpt-oss-120b"), ("groq", "openai/gpt-oss-20b")]
    lista.append(("pollinations", "openai"))
    orden = os.getenv("ORDEN_CEREBROS")  # p. ej. "groq,google,pollinations"
    if orden:
        prioridad = {n.strip(): i for i, n in enumerate(orden.split(","))}
        lista.sort(key=lambda x: prioridad.get(x[0], 99))
    return lista


def _quitar_imagenes(mensajes):
    return [{"role": m["role"], "content": m["content"] if isinstance(m["content"], str)
             else " ".join(x.get("text", "") for x in m["content"] if x.get("type") == "text")} for m in mensajes]


def _sin_system(mensajes):
    """Gemma no admite mensaje de sistema: se pega delante del primer mensaje del usuario."""
    sistema = "\n".join(m["content"] for m in mensajes if m["role"] == "system" and isinstance(m["content"], str))
    resto = [dict(m) for m in mensajes if m["role"] != "system"]
    if sistema and resto and isinstance(resto[0]["content"], str):
        resto[0]["content"] = f"[INSTRUCCIONES]\n{sistema}\n[FIN DE INSTRUCCIONES]\n\n{resto[0]['content']}"
    elif sistema:
        resto.insert(0, {"role": "user", "content": sistema})
    return resto


def _llamar_proveedor(prov, modelo, mensajes):
    import requests
    tiene_img = any(not isinstance(m["content"], str) for m in mensajes)
    extra = {"max_tokens": 900}
    if prov == "google":
        url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
        clave = os.getenv("GEMINI_API_KEY")
        if modelo.startswith("gemma"):
            mensajes = _sin_system(mensajes)
        else:
            extra["reasoning_effort"] = "low"
    elif prov == "groq":
        url, clave = "https://api.groq.com/openai/v1/chat/completions", os.getenv("GROQ_API_KEY")
        mensajes = _quitar_imagenes(mensajes)
        extra["reasoning_effort"] = "low"
    else:
        url, clave = "https://text.pollinations.ai/openai", None
        mensajes = _quitar_imagenes(mensajes)
        extra = {}
    cab = {"Authorization": f"Bearer {clave}"} if clave else {}
    try:
        r = requests.post(url, headers=cab, timeout=45, json={"model": modelo, "messages": mensajes, **extra})
        if r.status_code == 400 and (extra or tiene_img):  # opciones o imágenes no admitidas: probar sin ellas
            r = requests.post(url, headers=cab, timeout=45,
                              json={"model": modelo, "messages": _quitar_imagenes(mensajes)})
    except requests.RequestException as e:
        raise Saturado(f"sin conexión ({e.__class__.__name__})")
    if r.status_code == 429:
        raise Saturado("429")
    if r.status_code in (404, 403):
        raise Saturado("404")
    if r.status_code >= 500:
        raise Saturado(str(r.status_code))
    r.raise_for_status()
    texto = r.json()["choices"][0]["message"].get("content") or ""
    if not texto.strip():
        raise Saturado("respuesta vacía")
    return texto


def _router(mensajes, solo_vision=False):
    import time as _t
    ahora = _t.time()
    probados = []
    for prov, modelo in cadena_cerebros():
        if solo_vision and prov != "google":
            continue
        nombre = f"{prov}:{modelo}"
        hasta, fallos = _BLOQUEO.get(nombre, [0, 0])
        if hasta > ahora:
            continue
        try:
            texto = _llamar_proveedor(prov, modelo, mensajes)
            _BLOQUEO[nombre] = [0, 0]
            ESTADO_CEREBRO["ultimo"] = modelo
            return texto
        except Saturado as e:
            fallos += 1
            if str(e) == "404":
                espera = 24 * 3600          # ese modelo no existe/no está permitido
            elif str(e) == "429":
                espera = min(60 * fallos * fallos, 3600)  # agotado: apartarlo un rato (más si repite)
            else:
                espera = 20
            _BLOQUEO[nombre] = [ahora + espera, fallos]
            probados.append(nombre)
        except Exception:
            _BLOQUEO[nombre] = [ahora + 30, fallos + 1]
            probados.append(nombre)
    raise RuntimeError("Todos los cerebros gratis están ocupados ahora mismo. Prueba en un minuto"
                       + ("" if os.getenv("GROQ_API_KEY") else " (o añade una clave gratis de Groq: ver README)") + ".")


def estado_cerebros():
    """Para la pantalla de ajustes: qué cerebros hay y si están descansando."""
    import time as _t
    salida = []
    for prov, modelo in cadena_cerebros():
        hasta = _BLOQUEO.get(f"{prov}:{modelo}", [0, 0])[0]
        resta = int(hasta - _t.time())
        salida.append((modelo, "✅ listo" if resta <= 0 else f"⏸️ descansa {resta // 60} min" if resta >= 60 else f"⏸️ {resta} s"))
    return salida


def _gemini(mensajes):  # compatibilidad: ahora todo pasa por el router
    return _router(mensajes)


def _ollama(mensajes):
    import requests
    r = requests.post(f"{OLLAMA_URL}/api/chat", timeout=180,
                      json={"model": MODELO_OLLAMA, "stream": False, "messages": _quitar_imagenes(mensajes)})
    r.raise_for_status()
    return r.json()["message"]["content"]


def _demo(mensajes):
    """Respuestas falsas para probar el juego sin IA (BACKEND=demo)."""
    if not isinstance(mensajes[0]["content"], str):
        return "Man in his late 20s, short brown hair, light beard, casual hoodie."
    c0 = mensajes[0]["content"]
    if "Inventa 4 sucesos" in c0:
        return "- Marta y Sergio quedan a tomar algo después del box.\n- Hugo se duerme y llega tarde a la cafetería.\n- Carmen pilla a Tomás comprándole flores.\n- Dani prueba la canción nueva en el bar."
    if "array JSON" in c0:
        return json.dumps([{"nombre": "Lucas", "edad": 33, "genero": "m", "profesion": "panadero", "plantilla": "manana",
                            "barrio": "Lavapiés", "trabajo": None, "aficiones": ["padel", "bar_dani"], "personalidad": "risueño",
                            "estilo": "castizo", "historia": "Hace el mejor pan del barrio.", "rasgos": "round face, flour on cheeks",
                            "ropa": "white t-shirt", "relaciones": {"lucia": "le vende pan"}, "arco": ["a", "b", "c"]}])
    if "GRUPO DE WHATSAPP" in c0:
        return "Marta: TÍAAA no sabéis lo que me ha pasado 😂\nLucía: cuenta cuenta\nKai: miedo me das\n[afinidad Marta:+1]"
    if c0.startswith(("Diriges una escena EN PERSONA",)) and "AÚN NO CONOCE:" in c0:
        nuevo = re.search(r"AÚN NO CONOCE: [^(]+\(id: ([\w-]+)\)", c0)
        return ("Narrador: *El sitio está animado; alguien te mira y sonríe.*\n"
                "Desconocido: *se acerca* Hola, ¿es tu primera vez por aquí?\n"
                + (f"[conocido: {nuevo.group(1)}]\n" if nuevo else "") +
                "[vista: a friendly stranger smiling at the viewer]")
    if mensajes[0]["content"].startswith("Diriges una escena EN PERSONA"):
        return ("Narrador: *El bar está lleno y suena una rumba de fondo.*\n"
                "Lucía: *te hace sitio en la barra* ¡Por fin! Te presento a mi gente.\n"
                "Marta: *te mira de arriba abajo, sonriendo* Así que tú eres el famoso...\n"
                "Dani: *deja tres cañas en la barra* La primera invita la casa, che.\n"
                "[afinidad Lucía:+2]\n[afinidad Marta:+1]\n[afinidad Dani:+1]\n"
                "[recordar Marta: le gusta la cerveza]\n[momento: la primera caña todos juntos]\n"
                "[mundo: el usuario conoció a Marta y Dani en el bar]\n"
                "[vista: three friends at a crowded tapas bar counter smiling at the viewer, beers]")
    ultimo = mensajes[-1]["content"]
    ultimo = ultimo if isinstance(ultimo, str) else ultimo[0]["text"]
    if "ESTÁIS JUNTOS EN PERSONA" in mensajes[0]["content"]:
        return ("*Sonríe y se aparta el pelo de la cara mientras el camarero deja dos cafés.* "
                "¡Por fin nos vemos en persona! ¿Qué tal estás?\n[afinidad:+2]\n"
                "[vista: smiling warmly across a small cafe table, two coffees]")
    if "VIDEOLLAMADA" in mensajes[0]["content"]:
        return "*Saluda con la mano.* ¡Hola! Qué bien verte.\n[afinidad:+1]\n[vista: waving at the camera, smiling]"
    if ultimo.startswith("(SISTEMA"):
        return "Ey, ¿sigues vivo? 😄\n||\nHoy me ha pasado una cosa muy fuerte, luego te cuento\n[afinidad:0]"
    opciones = ["Jajaja no me lo puedo creer\n||\nY tú qué tal el día?",
                "[audio] Oye, te mando un audio que me da pereza escribir. ¿Qué haces luego?",
                "Mira dónde estoy 😄\n[foto: sitting by the window with a coffee]",
                "Vale, vamos al bar!\n[lugar: bar]",
                "Apuntado, el jueves tu examen 💪\n[fecha: 2026-11-26 | examen]"]
    return random.choice(opciones) + "\n[afinidad:+2]"


LLAMADAS = {"auto": _router, "gemini": _router, "ollama": _ollama, "demo": _demo}


def transcribir(audio, mime="audio/wav"):
    """Voz a texto: Gemini (Flash-Lite, que tiene más cupo) y, si falla, Whisper de Groq."""
    import requests
    clave = os.getenv("GEMINI_API_KEY")
    if clave:
        cuerpo = {"contents": [{"parts": [
            {"text": "Transcribe exactamente lo que dice este audio en español. Devuelve solo el texto. "
                     "Si no se oye nada, devuelve vacío."},
            {"inline_data": {"mime_type": mime, "data": base64.b64encode(audio).decode()}}]}]}
        for modelo in ["gemini-flash-lite-latest", "gemini-flash-latest"]:
            try:
                r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent",
                                  headers={"x-goog-api-key": clave}, timeout=60, json=cuerpo)
                if r.ok:
                    partes = r.json()["candidates"][0]["content"].get("parts", [])
                    return "".join(x.get("text", "") for x in partes).strip()
            except Exception:
                pass
    if os.getenv("GROQ_API_KEY"):
        r = requests.post("https://api.groq.com/openai/v1/audio/transcriptions",
                          headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"}, timeout=60,
                          files={"file": ("audio.wav", audio, mime)},
                          data={"model": "whisper-large-v3", "language": "es"})
        if r.ok:
            return r.json().get("text", "").strip()
    raise RuntimeError("No he podido entender el audio ahora mismo. Prueba otra vez o escríbelo.")


# =====================================================================
#                       Procesar la respuesta
# =====================================================================
ETIQUETAS = {
    "afinidad": re.compile(r"\[afinidad:\s*([+-]?\d+)\s*\]", re.I),
    "recordar": re.compile(r"\[recordar:\s*(.+?)\]", re.I),
    "fecha": re.compile(r"\[fecha:\s*(\d{4}-\d{2}-\d{2})\s*\|\s*(.+?)\]", re.I),
    "lugar": re.compile(r"\[lugar:\s*([\w-]+)\s*\]", re.I),
    "animo": re.compile(r"\[[aá]nimo:\s*(.+?)\]", re.I),
    "foto": re.compile(r"\[foto:\s*(.+?)\]", re.I),
    "vista": re.compile(r"\[vista:\s*(.+?)\]", re.I),
    "audio": re.compile(r"\[audio\]", re.I),
    "momento": re.compile(r"\[momento:\s*(.+?)\]", re.I),
    "apodo": re.compile(r"\[apodo:\s*(.+?)\]", re.I),
    "mundo": re.compile(r"\[mundo:\s*(.+?)\]", re.I),
    "relacion": re.compile(r"\[relaci[oó]n:\s*(amistad|tonteo|rollo|pareja|ex)\s*\]", re.I),
    "fundido": re.compile(r"\[fundido[^\]]*\]", re.I),
    "presentar": re.compile(r"\[(?:presentar|conocido):\s*([\w-]+)\s*\]", re.I),
}


def procesar_respuesta(texto):
    datos = {k: patron.findall(texto) for k, patron in ETIQUETAS.items()}
    for patron in ETIQUETAS.values():
        texto = patron.sub("", texto)
    texto = re.sub(r"\[[^\]]{0,40}:[^\]]*\]", "", texto)  # restos de etiquetas mal escritas
    partes = [x.strip() for x in re.split(r"\n\s*\|\|\s*\n?|\s\|\|\s", texto) if x.strip()]
    deltas = [int(x) for x in datos["afinidad"]]
    return {
        "partes": partes or ["..."],
        "delta": max(-3, min(3, deltas[-1])) if deltas else 0,
        "recuerdos": datos["recordar"],
        "fechas": datos["fecha"],
        "lugar": datos["lugar"][-1].lower() if datos["lugar"] else None,
        "animo": datos["animo"][-1] if datos["animo"] else None,
        "foto": datos["foto"][0] if datos["foto"] else None,
        "vista": datos["vista"][-1] if datos["vista"] else None,
        "audio": bool(datos["audio"]),
        "momentos": datos["momento"],
        "apodo": datos["apodo"][-1].strip() if datos["apodo"] else None,
        "mundo": datos["mundo"],
        "presentar": [x.lower() for x in datos["presentar"]],
        "relacion": datos["relacion"][-1].lower() if datos["relacion"] else None,
        "fundido": bool(datos["fundido"]),
    }


def separar_narracion(texto):
    """'*se ríe* Hola' -> ('se ríe', 'Hola')"""
    narracion = " ".join(x.strip() for x in re.findall(r"\*([^*]+)\*", texto))
    habla = re.sub(r"\*[^*]*\*", "", texto).strip()
    return narracion, habla


# =====================================================================
#                          Turno de conversación
# =====================================================================
def turno(p, mensaje_usuario, nombre_usuario, modo="chat", imagen=None, guardar_usuario=True):
    """imagen: bytes JPEG de una foto que mandas tú (opcional)."""
    pid = p["id"]
    _inicio(p)
    nivel_antes = nivel(memoria.afinidad(pid))[0]
    seg_ausencia = memoria.segundos_desde_ultimo(pid)
    if imagen:
        memoria.guardar_mensaje(pid, "foto_usuario", "data:image/jpeg;base64," + base64.b64encode(imagen).decode())
    if guardar_usuario and mensaje_usuario:
        memoria.guardar_mensaje(pid, "user", mensaje_usuario)
        memoria.escribir(pid, pendiente_hasta=None)  # contesta ahora, ya no queda nada pendiente

    mensajes = memoria.historial_para_ia(pid)
    if not guardar_usuario:  # mensajes internos que no se guardan (p. ej. "escribe tú primero")
        mensajes.append({"role": "user", "content": mensaje_usuario})
    if imagen and mensajes and mensajes[-1]["role"] == "user":
        mensajes[-1]["content"] = [
            {"type": "text", "text": mensajes[-1]["content"] + "\n(Mira la foto que te acaba de mandar y coméntala con naturalidad.)"},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(imagen).decode()}}]
    evento = random.choice(EVENTOS_QUEDADA) if modo == "quedada" and random.random() < 0.3 else None
    mensajes.insert(0, {"role": "system", "content": construir_prompt(p, nombre_usuario, modo, evento, seg_ausencia)})

    r = procesar_respuesta(LLAMADAS[BACKEND](mensajes))

    # Guardar la respuesta
    if modo == "chat":
        rol = "nota_voz" if r["audio"] else "assistant"
        for parte in r["partes"]:
            memoria.guardar_mensaje(pid, rol, parte)
    else:
        memoria.guardar_mensaje(pid, "assistant", " ".join(r["partes"]))

    # Efectos
    for x in r["recuerdos"]:
        memoria.añadir_recuerdo(pid, x)
    for fe, que in r["fechas"]:
        if mundo.parsear_fecha(fe):
            memoria.añadir_fecha(pid, fe, que)
    if r["animo"]:
        memoria.escribir(pid, animo=r["animo"], animo_fecha=str(mundo.ahora().date()))
    for m_ in r["momentos"]:
        memoria.añadir_momento(pid, m_)
    if r["apodo"] and len(r["apodo"]) < 30:
        memoria.escribir(pid, apodo=r["apodo"])
    for s_ in r["mundo"]:
        memoria.añadir_suceso(p.get("mundo", pid), f"{p['nombre']}: {s_}")
    r["cambio_relacion"] = None
    if r["relacion"] and r["relacion"] != relacion(p):
        r["cambio_relacion"] = RELACIONES[r["relacion"]]
        registrar_relacion(p, r["relacion"], nombre_usuario)
    if r["fundido"]:
        memoria.guardar_mensaje(pid, "lugar", "🌙 Un rato después…")
    r["nuevos_contactos"] = []
    todos = cargar_personajes()
    for qid in r["presentar"]:
        if qid in todos and qid != pid and conocer(todos[qid], f"a través de {p['nombre']}"):
            r["nuevos_contactos"].append(todos[qid]["nombre"])
    r["cambio_lugar"] = None
    if r["lugar"] in p["lugares"] and r["lugar"] != lugar_actual(p):
        cambiar_lugar(p, r["lugar"])
        r["cambio_lugar"] = p["lugares"][r["lugar"]]["nombre"]
        memoria.guardar_mensaje(pid, "lugar", r["cambio_lugar"])
    elif modo == "quedada":
        cambiar_lugar(p, lugar_actual(p))  # mientras estáis juntos, el plan sigue activo

    r["url_foto"] = None
    if modo == "chat" and r["foto"]:
        r["url_foto"] = url_foto(p, r["foto"], semilla_extra=str(random.random()))
        memoria.guardar_mensaje(pid, "foto", r["url_foto"])

    puntos = memoria.sumar_afinidad(pid, r["delta"])
    r["subio"] = nivel(puntos)[0] > nivel_antes
    if r["subio"]:
        memoria.guardar_mensaje(pid, "foto", url_foto(
            p, "happy candid selfie smiling at the camera, golden hour light", semilla_extra=str(puntos)))

    r["texto"] = " ".join(r["partes"])
    r["narracion"], r["habla"] = separar_narracion(r["texto"])
    return r


def mensaje_proactivo(p, nombre_usuario):
    """Si llevas horas sin hablar, el personaje te escribe primero. Devuelve True si escribió."""
    seg = memoria.segundos_desde_ultimo(p["id"])
    f = actividad(p)
    if seg is None or seg < HORAS_PARA_ESCRIBIR_PRIMERO * 3600 or (f and f.get("dormido")):
        return False
    horas = int(seg // 3600)
    turno(p, f"(SISTEMA: hace {horas} horas que no habláis. Escríbele tú primero, de forma natural: "
             f"cuéntale algo de tu día, pregúntale por algo que recuerdes o por una fecha cercana. "
             f"No menciones este aviso.)", nombre_usuario, guardar_usuario=False)
    return True


# =====================================================================
#            Respuestas diferidas (si está ocupado o durmiendo)
# =====================================================================
def debe_esperar(p, texto):
    """¿Contesta más tarde? Si está trabajando o durmiendo, normalmente sí (salvo urgencias)."""
    if any(x in (texto or "").lower() for x in ("urgente", "emergencia", "ayuda")):
        memoria.escribir(p["id"], pendiente_hasta=None)  # lo urgente se contesta ya
        return False
    if memoria.leer(p["id"], "pendiente_hasta"):  # ya tenía mensajes tuyos sin contestar
        return True
    f = actividad(p)
    if not f or not (f.get("ocupado") or f.get("dormido")):
        return False
    return random.random() < (0.9 if f.get("dormido") else 0.7)


def programar_respuesta(p):
    """Apunta cuándo contestará (si no había ya una respuesta pendiente)."""
    if memoria.leer(p["id"], "pendiente_hasta"):
        return
    f = actividad(p)
    ahora = mundo.ahora().replace(tzinfo=None)
    if f and f.get("dormido"):
        h, m = map(int, f["a"].split(":"))
        despierta = ahora.replace(hour=h, minute=m, second=0, microsecond=0)
        if despierta <= ahora:
            despierta += timedelta(days=1)
        cuando = despierta + timedelta(minutes=random.randint(5, 40))
    else:
        cuando = ahora + timedelta(minutes=random.randint(8, 45))
    memoria.escribir(p["id"], pendiente_hasta=cuando.isoformat(timespec="minutes"))


def estado_entrega(p):
    """Texto bajo tu último mensaje: '✓ Entregado', '✓✓ Visto' o None si no hay nada pendiente."""
    pend = memoria.leer(p["id"], "pendiente_hasta")
    if not pend:
        return None
    f = actividad(p)
    hora = pend[11:16]
    if f and f.get("dormido"):
        return f"✓ Entregado · {p['nombre']} está durmiendo"
    return f"✓✓ Visto · te contestará cuando pueda (~{hora})"


def revisar_pendientes(p, nombre_usuario):
    """Si ya toca, el personaje contesta a lo que le escribiste. Devuelve True si contestó."""
    pend = memoria.leer(p["id"], "pendiente_hasta")
    if not pend or mundo.ahora().replace(tzinfo=None) < datetime.fromisoformat(pend):
        return False
    memoria.escribir(p["id"], pendiente_hasta=None)
    f = mundo.franja(p)
    turno(p, f"(SISTEMA: acabas de poder mirar el móvil después de estar "
             f"{'durmiendo' if f and f.get('dormido') else 'ocupad' + ('a' if p.get('genero') == 'f' else 'o')}. "
             f"Contesta ahora a sus mensajes con naturalidad, puedes disculparte por tardar. No menciones este aviso.)",
          nombre_usuario, guardar_usuario=False)
    return True


# =====================================================================
#                   Tu aspecto (selfie) y fotos juntos
# =====================================================================
def describir_usuario(imagen_jpeg):
    """Gemini mira tu selfie y guarda una descripción física (en inglés) para las fotos juntos."""
    pregunta = [{"role": "user", "content": [
        {"type": "text", "text": "Describe the physical appearance of the main person in this selfie for an image "
                                 "generator, in English, in one sentence of max 45 words: approximate age, gender, "
                                 "hair, facial hair, glasses, build, clothing style. No names, no identity guesses."},
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(imagen_jpeg).decode()}}]}]
    llamar = (lambda m: _router(m, solo_vision=True)) if BACKEND in ("auto", "gemini") else LLAMADAS[BACKEND]
    texto = llamar(pregunta).strip()
    texto = re.sub(r"\[[^\]]*\]", "", texto).strip()[:400]
    if texto:
        memoria.escribir(memoria.USUARIO, aspecto=texto)
    return texto


def url_foto_juntos(p):
    yo = aspecto_usuario() or "a friendly person in casual clothes"
    return url_foto(p, f"selfie taken together with a friend ({yo}), both smiling, close together, "
                       f"phone held at arm's length", semilla_extra=str(random.random()))


# =====================================================================
#                 Salir por Madrid y conocer gente nueva
# =====================================================================
def anfitrion_salida(sitio):
    """'Personaje' ficticio que representa el plan: el sitio adonde sales (puedes moverte a cualquier sitio)."""
    return {"id": "_salida", "nombre": "Salida", "lugares": dict(SITIOS), "lugar_inicial": sitio,
            "ciudad": MADRID, "mundo": "madrid", "rutina": [], "relaciones": {}}


def gente_en(sitio, cuantos=2, excluir=()):
    """Desconocidos que puedes encontrarte en un sitio (mejor si su rutina les pone ahí ahora)."""
    todos = cargar_personajes()
    candidatos = [q for q in todos.values() if not es_conocido(q) and q["id"] not in excluir
                  and q.get("mundo") == "madrid" and sitio in q.get("conocer_en", [])]
    ahora_ahi = [q for q in candidatos if (mundo.franja(q) or {}).get("lugar") == sitio]
    random.shuffle(candidatos)
    elegidos = ahora_ahi[:cuantos]
    for q in candidatos:
        if len(elegidos) >= cuantos:
            break
        if q not in elegidos:
            elegidos.append(q)
    return elegidos


def empezar_salida(sitio, amigos):
    """Sales a un sitio (con o sin amigos). Devuelve (personas en escena, anfitrión)."""
    anf = anfitrion_salida(sitio)
    extranos = gente_en(sitio, cuantos=random.choice([1, 2]), excluir=[a["id"] for a in amigos])
    personas = list(amigos) + extranos
    memoria.borrar_mensajes("grupo")
    cambiar_lugar(anf, sitio)
    for q in personas:
        if sitio in q["lugares"]:
            cambiar_lugar(q, sitio)
    return personas, anf


def faltan_por_conocer():
    todos = cargar_personajes()
    return sum(1 for q in todos.values() if q.get("mundo") == "madrid" and not es_conocido(q))


# =====================================================================
#             El mundo vive solo (una vez al día)
# =====================================================================
def simular_mundo(nombre_usuario):
    """Cada día pasan cosas entre los personajes aunque tú no estés. Devuelve True si simuló."""
    hoy = str(mundo.ahora().date())
    if memoria.leer(memoria.MUNDO, "sim_fecha") == hoy:
        return False
    memoria.escribir(memoria.MUNDO, sim_fecha=hoy)
    todos = [q for q in cargar_personajes().values() if q.get("mundo") == "madrid"]
    fichas = []
    for q in todos:
        _, novedad = novedades_vida(q)
        rel = "; ".join(f"{k}: {v}" for k, v in list(q.get("relaciones", {}).items())[:4])
        fichas.append(f"- {q['nombre']} (id: {q['id']}; {q.get('profesion') or q.get('resumen', '')}). Novedad: {novedad or '-'}. Relaciones: {rel}")
    recientes = "\n".join(f"- {t}" for _, t in memoria.sucesos("madrid", 12)) or "- (nada)"
    nombres_ids = {q["id"]: q["nombre"] for q in todos}
    vinculos_txt = "\n".join(f"- {nombres_ids.get(a, a)} ({a}) y {nombres_ids.get(b, b)} ({b}): {t}"
                             for a, b, t in memoria.todos_los_vinculos()) or "- (ninguna)"
    secretos_txt = "\n".join(f"- {x['texto']} (lo saben: {', '.join(x['saben'])})"
                             for x in memoria.secretos() if not x["destapado"]) or "- (ninguno)"
    prompt = f"""Eres el narrador de un mundo de personajes en Madrid. Hoy es {mundo.fecha_texto()}.
PERSONAJES:
{chr(10).join(fichas)}

LO ÚLTIMO QUE PASÓ:
{recientes}

RELACIONES SENTIMENTALES ACTUALES ENTRE ELLOS:
{vinculos_txt}

SECRETOS QUE CIRCULAN:
{secretos_txt}

Inventa 4 sucesos realistas que han pasado HOY entre estos personajes: planes, encuentros, piques, ligues, rollos de una noche,
parejas que empiezan o lo dejan, cuernos, celos, reconciliaciones, cotilleos, ayudas, malentendidos. Coherentes con sus
relaciones y novedades, continuando lo último que pasó. Como una serie: con drama, pero creíble. Nada sexual explícito.
Formato: una línea por suceso empezando por "- " (frases cortas en español).
Además, si algún suceso cambia una relación entre dos personajes, añade una línea [vinculo: id1|id2|tonteo|rollo|pareja|ex|nada].
Si un suceso es secreto (p. ej. unos cuernos), añade [secreto: texto | sobre: id_de_quien_no_debe_saberlo | saben: id1,id2].
Usa los ids exactos. Sin nada más."""
    try:
        texto = LLAMADAS[BACKEND]([{"role": "user", "content": prompt}])
    except Exception:
        return False
    ids = set(nombres_ids)
    for a, b, tipo in re.findall(r"\[vinculo:\s*([\w-]+)\s*\|\s*([\w-]+)\s*\|\s*(\w+)\s*\]", texto, re.I):
        if a in ids and b in ids and a != b:
            memoria.poner_vinculo(a, b, tipo.lower())
    for t, sobre, saben in re.findall(r"\[secreto:\s*(.+?)\|\s*sobre:\s*([\w,\s-]+)\|\s*saben:\s*([\w,\s-]+)\]", texto, re.I):
        so = [x.strip() for x in sobre.split(",") if x.strip() in ids]
        sa = [x.strip() for x in saben.split(",") if x.strip() in ids]
        if so and sa:
            memoria.añadir_secreto(t.strip(), so, sa)
    texto = re.sub(r"\[[^\]]*\]", "", texto)
    for linea in texto.splitlines():
        linea = linea.strip()
        if linea.startswith(("-", "•", "*")) and len(linea) > 8:
            memoria.añadir_suceso("madrid", linea.lstrip("-•* ").strip()[:240])
    extender_cotilleos(nombre_usuario)
    return True


def extender_cotilleos(nombre_usuario):
    """Los secretos corren: cada día puede enterarse alguien más. Si se entera la 'víctima', se lía."""
    todos = cargar_personajes()
    for x in memoria.secretos():
        if x["destapado"] or random.random() > 0.35:
            continue
        cerca = set()
        for quien in x["saben"]:
            if quien in todos:
                cerca |= set(todos[quien].get("relaciones", {}))
                cerca |= {o for o, _ in memoria.vinculos_de(quien)}
        cerca = [c for c in cerca if c in todos and c not in x["saben"]]
        if not cerca:
            continue
        nuevo = random.choice(cerca)
        memoria.actualizar_secreto(x["id"], saben=x["saben"] + [nuevo])
        if nuevo in x["sobre"]:
            memoria.actualizar_secreto(x["id"], destapado=1)
            memoria.escribir(nuevo, animo="dolido/a y enfadado/a por algo que acaba de descubrir",
                             animo_fecha=str(mundo.ahora().date()))
            memoria.añadir_suceso("madrid", f"¡Se ha liado! {todos[nuevo]['nombre']} se ha enterado: {x['texto']}")


# =====================================================================
#               Grupo de WhatsApp "Los de siempre"
# =====================================================================
MIEMBROS_WHATSAPP = ["lucia", "marta", "kai", "dani"]
HILO_WHATSAPP = "grupo_wa"


def miembros_whatsapp():
    todos = cargar_personajes()
    return [todos[k] for k in MIEMBROS_WHATSAPP if k in todos]


def turno_whatsapp(texto, nombre_usuario):
    m = miembros_whatsapp()
    return turno_grupo(m, m[0], texto, nombre_usuario, hilo=HILO_WHATSAPP, formato="whatsapp")


def whatsapp_vivo(nombre_usuario, horas=2):
    """Si hace rato que nadie escribe en el grupo, ellos charlan solos (y te mencionan a veces)."""
    seg = memoria.segundos_desde_ultimo(HILO_WHATSAPP)
    if seg is not None and seg < horas * 3600:
        return False
    if 1 <= mundo.ahora().hour < 8:  # de madrugada el grupo duerme
        return False
    m = miembros_whatsapp()
    turno_grupo(m, m[0], "(SISTEMA: hace rato que nadie escribe. Que alguien saque un tema natural "
                         "(un plan, un cotilleo del mundo, una novedad suya, un meme descrito) y otros respondan. "
                         f"Pueden mencionar a {nombre_usuario}. No menciones este aviso.)",
                nombre_usuario, hilo=HILO_WHATSAPP, formato="whatsapp", guardar_usuario=False)
    return True


# =====================================================================
#               Crear gente nueva para el mundo (con IA)
# =====================================================================
VOCES = {"f": ["es-ES-ElviraNeural", "es-ES-XimenaNeural", "es-MX-DaliaNeural", "es-AR-ElenaNeural", "es-CO-SalomeNeural"],
         "m": ["es-ES-AlvaroNeural", "es-MX-JorgeNeural", "es-AR-TomasNeural", "es-CO-GonzaloNeural"]}


def crear_gente(cuantos=5, deseo=""):
    """Pide a la IA personas nuevas coherentes con el mundo. Devuelve la lista de nombres creados."""
    import unicodedata
    todos = cargar_personajes()
    existentes = ", ".join(f"{q['nombre']} ({q['id']}, {q.get('profesion') or q.get('resumen', '')[:40]})"
                           for q in todos.values() if q.get("mundo") == "madrid")
    prompt = f"""Crea {cuantos} personajes NUEVOS y variados (edades 20-70, profesiones, orígenes y caracteres distintos)
que viven en Madrid y encajan en este mundo. Deben tener relaciones con algunos personajes existentes.
EXISTENTES: {existentes}
SITIOS POSIBLES: {", ".join(SITIOS)}
Devuelve SOLO un array JSON, sin texto alrededor, con objetos así:
{{"nombre":"...","edad":30,"genero":"f o m","profesion":"...","plantilla":"oficina|manana|noche|estudiante|autonomo|jubilado",
"barrio":"...","trabajo":"una clave de SITIOS o null","aficiones":["clave de SITIOS","clave de SITIOS"],
"personalidad":"...","estilo":"cómo habla","historia":"2-3 frases","rasgos":"rasgos físicos MUY concretos en inglés (cara, ojos, pelo, señas, complexión, altura)",
"ropa":"ropa típica en inglés","relaciones":{{"id_existente":"qué son"}},"arco":["suceso de su vida 1","suceso 2","suceso 3"]}}
{('LO QUE PIDE EL JUGADOR PARA ESTOS PERSONAJES: ' + deseo) if deseo else ''}
Nada sexual. Personajes adultos (18+), realistas, con defectos y virtudes."""
    texto = LLAMADAS[BACKEND]([{"role": "user", "content": prompt}])
    m = re.search(r"\[.*\]", texto, re.S)
    if not m:
        raise RuntimeError("La IA no devolvió personajes válidos. Prueba otra vez.")
    nuevos = []
    for c in json.loads(m.group(0)):
        try:
            base = unicodedata.normalize("NFKD", c["nombre"].split()[0].lower()).encode("ascii", "ignore").decode()
            pid = re.sub(r"[^a-z]", "", base) or "persona"
            if int(c.get("edad", 30)) < 18:
                continue
            while pid in todos:
                pid += "x"
            g = "m" if str(c.get("genero", "f")).lower().startswith("m") else "f"
            afi = [a for a in c.get("aficiones", []) if a in SITIOS][:2] or ["retiro"]
            trabajo = c.get("trabajo") if c.get("trabajo") in SITIOS else None
            ficha = {
                "id": pid, "nombre": c["nombre"].split()[0], "edad": int(c.get("edad", 30)), "genero": g,
                "profesion": c.get("profesion", ""), "plantilla": c.get("plantilla", "oficina"),
                "barrio": c.get("barrio", "Madrid"), "trabajo": trabajo, "aficiones": afi,
                "voz": random.choice(VOCES[g]), "tono": f"{random.randint(-12, 12):+d}Hz",
                "personalidad": c.get("personalidad", ""), "estilo": c.get("estilo", ""),
                "historia": c.get("historia", ""), "rasgos": c.get("rasgos", ""), "ropa": c.get("ropa", "casual clothes"),
                "relaciones": {k: v for k, v in c.get("relaciones", {}).items() if k in todos},
                "arco": [{"dia": d, "suceso": t} for d, t in zip([0, 6, 14], c.get("arco", []))],
                "conocer_en": ([trabajo] if trabajo else []) + afi,
            }
            memoria.guardar_personaje_extra(ficha)
            todos[pid] = expandir(ficha)
            nuevos.append(ficha["nombre"])
        except Exception:
            continue
    _CACHE_PJ["datos"] = None
    if nuevos:
        memoria.añadir_suceso("madrid", f"Gente nueva por el barrio: {', '.join(nuevos)}.")
    return nuevos
