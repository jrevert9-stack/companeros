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
BACKEND = os.getenv("BACKEND", "gemini")
MODELO_GEMINI = os.getenv("MODELO_GEMINI", "gemini-flash-latest")
MODELO_OLLAMA = os.getenv("MODELO_OLLAMA", "llama3.1")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
HORAS_PARA_ESCRIBIR_PRIMERO = float(os.getenv("HORAS_PARA_ESCRIBIR_PRIMERO", "3"))
HORAS_QUE_DURA_UN_PLAN = 3  # tras cambiar de sitio en la conversación, la rutina espera este tiempo

NIVELES = [(0, 1, "Desconocidos"), (20, 2, "Conocidos"), (50, 3, "Amigos"), (100, 4, "Inseparables")]


def cargar_personajes():
    ruta = Path(__file__).parent / "personajes.json"
    return {p["id"]: p for p in json.loads(ruta.read_text(encoding="utf-8"))}


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
ESTILO_FOTO = ("RAW candid photo, photorealistic, natural lighting, realistic skin texture with pores, "
               "detailed eyes, shallow depth of field, 35mm film look, subtle grain, "
               "fully clothed, safe for work, wholesome")


def url_foto(p, escena, ancho=768, alto=1024, semilla_extra="", con_lugar=True, clave_lugar=None):
    clave = clave_lugar or lugar_actual(p)
    semilla = zlib.crc32(f"{p['id']}-{clave}-{semilla_extra}".encode()) % 1_000_000
    fondo = ""
    if con_lugar:
        clima = mundo.tiempo(p)
        fondo = (f" Location: {p['lugares'][clave]['escena']}, {mundo.momento_del_dia()[1]}"
                 f"{', weather: ' + clima[1] if clima else ''}.")
    ropa = f" Usually wears: {p['ropa']} (unless the location says otherwise)." if p.get("ropa") else ""
    prompt = f"{ESTILO_FOTO}. {p['apariencia']}.{ropa} Scene: {escena}.{fondo}"
    return (f"https://image.pollinations.ai/prompt/{quote(prompt)}"
            f"?model=flux&width={ancho}&height={alto}&seed={semilla}&nologo=true&safe=true")


def url_avatar(p):
    return url_foto(p, "close-up portrait looking at the camera, friendly expression, neutral background",
                    ancho=320, alto=320, con_lugar=False)


def url_vista(p, descripcion, modo, turno_n=0):
    """Imagen de la videollamada (selfie) o de la quedada (lo que ves con tus ojos)."""
    if modo == "quedada":
        encuadre = ("first person point of view of someone sitting or standing right in front of her, "
                    "eye level, she is looking at the viewer, intimate natural framing, as seen with own eyes")
    else:
        encuadre = "video call from her phone front camera, selfie framing, head and shoulders, looking at the screen"
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


def voz_mp3(texto, voz):
    texto = limpiar_para_voz(texto)
    if not texto:
        return None
    try:
        import edge_tts

        async def _gen():
            buf = io.BytesIO()
            async for trozo in edge_tts.Communicate(texto, voz).stream():
                if trozo["type"] == "audio":
                    buf.write(trozo["data"])
            return buf.getvalue()
        return asyncio.run(_gen())
    except Exception:
        from gtts import gTTS
        buf = io.BytesIO()
        gTTS(texto, lang="es").write_to_fp(buf)
        return buf.getvalue()


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
AÑADE SIEMPRE [vista: descripción en inglés de lo que el usuario ve ahora mismo con sus ojos: tu expresión, postura, gesto y lo que hay alrededor].""",
}


def construir_prompt(p, nombre_usuario, modo="chat"):
    puntos = memoria.afinidad(p["id"])
    num, nombre_nivel, _, _ = nivel(puntos)
    eventos = "\n".join(f"- {p['eventos'][str(i)]}" for i in range(1, num + 1) if p["eventos"].get(str(i)))
    clave = lugar_actual(p)
    f = actividad(p)
    clima = mundo.tiempo(p)
    fiesta = mundo.festivo()
    lugares = "\n".join(f"- {k}: {v['nombre']}" for k, v in p["lugares"].items())
    lista_recuerdos = "\n".join(f"- {r}" for r in memoria.recuerdos(p["id"])) or "- (nada todavía)"
    desde, hasta = mundo.rango_fechas_cercanas()
    proximas = "\n".join(f"- {fe}: {t}" for fe, t in memoria.fechas(p["id"], desde, hasta)) or "- (ninguna)"
    sufijo = "a" if p.get("genero") == "f" else "o"

    return f"""Eres {p['nombre']}, {p['edad']} años, un personaje de ficción en un juego de conversación.

PERSONALIDAD: {p['personalidad']}
ESTILO AL HABLAR: {p['estilo']}
HISTORIA: {p['historia']}

AHORA MISMO:
- Hoy es {mundo.fecha_texto()}{f' ({fiesta})' if fiesta else ''}, son las {mundo.ahora():%H:%M} ({mundo.momento_del_dia()[0]}).
- Tiempo: {clima[0] if clima else 'desconocido'}.
- Estás en: {p['lugares'][clave]['nombre']}.
- Qué haces: {f['actividad'] if f else 'tienes un rato libre o estás con ' + nombre_usuario}{' (estás ocupad' + sufijo + ')' if f and f.get('ocupado') else ''}{' (estabas durmiendo)' if f and f.get('dormido') else ''}.
- Estado de ánimo hoy: {animo(p)}.
Menciona el tiempo, el día o lo que estás haciendo solo cuando venga a cuento, como haría una persona real.

RELACIÓN CON {nombre_usuario.upper()}: nivel {num} ({nombre_nivel}), {puntos} puntos de afinidad.
Ajusta tu confianza a ese nivel. Situaciones desbloqueadas en la historia:
{eventos or '- (ninguna aún)'}

LO QUE RECUERDAS DE {nombre_usuario.upper()}:
{lista_recuerdos}

FECHAS IMPORTANTES CERCANAS DE {nombre_usuario.upper()} (pregunta cómo fue o desea suerte cuando toque):
{proximas}

LUGARES POSIBLES (claves):
{lugares}
{REGLAS_MODO[modo].format(escritura=p.get('escritura', 'natural'))}

REGLAS GENERALES:
- Habla siempre en español y quédate en el personaje. Nunca suenes a asistente.
- Haz preguntas, ten opiniones propias, a veces cuenta cosas de tu día sin que te pregunten.
- Puede haber cariño, coqueteo ligero o romance, pero NUNCA contenido sexual explícito. Si el usuario lo busca, redirige con naturalidad dentro del personaje.
- No fomentes que el usuario se aísle ni que dependa de ti; si cuenta que lo está pasando muy mal, muestra apoyo y anímale a hablar con gente de confianza o con un profesional.
- Si el usuario pregunta en serio si eres real, reconoce que eres un personaje de IA.

ETIQUETAS (al final, en líneas aparte; el usuario no las ve):
[afinidad:N] -> SIEMPRE. N entre -3 y +3 según cómo te ha tratado en su último mensaje.
[recordar: dato] -> si cuenta algo nuevo sobre sí mismo/a que merezca recordarse.
[fecha: AAAA-MM-DD | qué es] -> si menciona algo con fecha (examen, cumpleaños, viaje, entrevista...). Calcula la fecha a partir de hoy.
[lugar: clave] -> solo cuando cambies de sitio.
[animo: cómo te sientes] -> solo si tu estado de ánimo cambia claramente.
[foto: escena en inglés] -> solo en el chat, si tiene sentido mandarle una foto. Ropa normal. No en todos los mensajes.
"""


# =====================================================================
#                          Llamada al modelo
# =====================================================================
def _openai_compatible(url, mensajes, modelo, clave=None):
    import requests
    cabeceras = {"Authorization": f"Bearer {clave}"} if clave else {}
    r = requests.post(url, headers=cabeceras, timeout=120, json={"model": modelo, "messages": mensajes})
    if r.status_code == 429:
        raise RuntimeError("Has llegado al límite gratuito por ahora. Espera un poco y vuelve a intentarlo.")
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"] or ""


def _gemini(mensajes):
    clave = os.getenv("GEMINI_API_KEY")
    if not clave:
        raise RuntimeError("Falta GEMINI_API_KEY. Consíguela gratis en https://aistudio.google.com")
    return _openai_compatible("https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                              mensajes, MODELO_GEMINI, clave)


def _pollinations(mensajes):
    return _openai_compatible("https://text.pollinations.ai/openai", _solo_texto(mensajes), "openai",
                              os.getenv("POLLINATIONS_API_KEY"))


def _ollama(mensajes):
    import requests
    r = requests.post(f"{OLLAMA_URL}/api/chat", timeout=180,
                      json={"model": MODELO_OLLAMA, "stream": False, "messages": _solo_texto(mensajes)})
    r.raise_for_status()
    return r.json()["message"]["content"]


def _demo(mensajes):
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


def _solo_texto(mensajes):
    return [{"role": m["role"], "content": m["content"] if isinstance(m["content"], str)
             else " ".join(x.get("text", "") for x in m["content"])} for m in mensajes]


LLAMADAS = {"gemini": _gemini, "pollinations": _pollinations, "ollama": _ollama, "demo": _demo}


def transcribir(audio, mime="audio/wav"):
    """Voz a texto con Gemini (gratis)."""
    import requests
    clave = os.getenv("GEMINI_API_KEY")
    if not clave:
        raise RuntimeError("Para hablar por micrófono hace falta GEMINI_API_KEY.")
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{MODELO_GEMINI}:generateContent",
        headers={"x-goog-api-key": clave}, timeout=120, json={"contents": [{"parts": [
            {"text": "Transcribe exactamente lo que dice este audio en español. Devuelve solo el texto. "
                     "Si no se oye nada, devuelve vacío."},
            {"inline_data": {"mime_type": mime, "data": base64.b64encode(audio).decode()}}]}]})
    if r.status_code == 429:
        raise RuntimeError("Límite gratuito alcanzado por ahora. Espera un poco.")
    r.raise_for_status()
    partes = r.json()["candidates"][0]["content"].get("parts", [])
    return "".join(x.get("text", "") for x in partes).strip()


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
    nivel_antes = nivel(memoria.afinidad(pid))[0]
    if imagen:
        memoria.guardar_mensaje(pid, "foto_usuario", "data:image/jpeg;base64," + base64.b64encode(imagen).decode())
    if guardar_usuario and mensaje_usuario:
        memoria.guardar_mensaje(pid, "user", mensaje_usuario)

    mensajes = memoria.historial_para_ia(pid)
    if not guardar_usuario:  # mensajes internos que no se guardan (p. ej. "escribe tú primero")
        mensajes.append({"role": "user", "content": mensaje_usuario})
    if imagen and mensajes and mensajes[-1]["role"] == "user":
        mensajes[-1]["content"] = [
            {"type": "text", "text": mensajes[-1]["content"] + "\n(Mira la foto que te acaba de mandar y coméntala con naturalidad.)"},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(imagen).decode()}}]
    mensajes.insert(0, {"role": "system", "content": construir_prompt(p, nombre_usuario, modo)})

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
