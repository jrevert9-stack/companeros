"""El mundo real alrededor del personaje: hora, rutina, tiempo, festivos y estado de ánimo."""
import os
import random
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

ZONA = ZoneInfo(os.getenv("ZONA_HORARIA", "Europe/Madrid"))
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]

FESTIVOS = {(1, 1): "Año Nuevo", (6, 1): "Reyes", (1, 5): "Día del Trabajo",
            (15, 8): "la Asunción", (12, 10): "el Día de la Hispanidad", (1, 11): "Todos los Santos",
            (6, 12): "el Día de la Constitución", (8, 12): "la Inmaculada", (24, 12): "Nochebuena",
            (25, 12): "Navidad", (31, 12): "Nochevieja", (14, 2): "San Valentín",
            (31, 10): "Halloween", (5, 1): "la noche de Reyes"}

ANIMOS = ["de muy buen humor", "con calma, tranquilidad total", "con algo de cansancio",
          "con un poco de nostalgia", "con muchísima energía", "con algo de agobio por cosas suyas",
          "con ganas de bromear y picar al usuario"]


def ahora():
    return datetime.now(ZONA)


def fecha_texto(d=None):
    d = d or ahora()
    return f"{DIAS[d.weekday()]} {d.day} de {MESES[d.month - 1]} de {d.year}"


def festivo(d=None):
    d = d or ahora()
    return FESTIVOS.get((d.day, d.month))


def momento_del_dia(d=None):
    """(nombre en español, luz para las fotos)."""
    h = (d or ahora()).hour
    if 7 <= h < 13:
        return "por la mañana", "morning daylight"
    if 13 <= h < 20:
        return "por la tarde", "afternoon light"
    if 20 <= h < 24:
        return "por la noche", "evening, night time, warm artificial lights"
    return "de madrugada", "late night, dim warm lamp light"


# ---------- Rutina ----------
def _minutos(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _toca_dia(regla, weekday):
    return regla == "todos" or (regla == "laborables" and weekday < 5) or (regla == "finde" and weekday >= 5)


def franja(p, d=None):
    """Qué está haciendo el personaje según su rutina (dict de la rutina o None)."""
    d = d or ahora()
    m = d.hour * 60 + d.minute
    for f in p.get("rutina", []):
        ini, fin = _minutos(f["de"]), _minutos(f["a"])
        if ini <= fin:
            if _toca_dia(f["dias"], d.weekday()) and ini <= m < fin:
                return f
        else:  # cruza la medianoche: la parte de después de las 00:00 pertenece al día anterior
            if _toca_dia(f["dias"], d.weekday()) and m >= ini:
                return f
            if _toca_dia(f["dias"], (d.weekday() - 1) % 7) and m < fin:
                return f
    return None


def franjas_de_hoy_hasta_ahora(p):
    """Franjas de hoy ya empezadas (para las historias)."""
    d = ahora()
    m = d.hour * 60 + d.minute
    hoy = [f for f in p.get("rutina", []) if _toca_dia(f["dias"], d.weekday())
           and _minutos(f["de"]) <= m and not f.get("dormido") and _minutos(f["de"]) >= 6 * 60]
    return sorted(hoy, key=lambda f: _minutos(f["de"]))


# ---------- Tiempo real (Open-Meteo, gratis y sin clave) ----------
_CACHE = {}
CODIGOS = [((0,), "despejado", "clear sky, sunny"), ((1, 2, 3), "con nubes", "partly cloudy"),
           ((45, 48), "con niebla", "foggy"), (tuple(range(51, 58)), "con llovizna", "light drizzle"),
           (tuple(range(61, 68)), "lloviendo", "rainy, wet streets"),
           (tuple(range(71, 78)), "nevando", "snowing"), ((80, 81, 82), "con chubascos", "rain showers"),
           ((95, 96, 99), "con tormenta", "thunderstorm")]


def tiempo(p):
    """(texto en español, texto en inglés) o None si no se puede saber."""
    if p.get("clima_fijo"):
        return tuple(p["clima_fijo"])
    c = p.get("ciudad")
    if not c:
        return None
    clave = (c["nombre"], int(time.time() // 1800))  # se actualiza cada 30 min
    if clave in _CACHE:
        return _CACHE[clave]
    try:
        import requests
        r = requests.get("https://api.open-meteo.com/v1/forecast", timeout=5, params={
            "latitude": c["lat"], "longitude": c["lon"], "current": "temperature_2m,weather_code"})
        actual = r.json()["current"]
        cod, temp = actual["weather_code"], round(actual["temperature_2m"])
        es, en = next(((e, i) for cods, e, i in CODIGOS if cod in cods), ("variable", "overcast"))
        resultado = (f"{c['nombre']}: {es}, {temp} °C", en)
    except Exception:
        resultado = None
    _CACHE[clave] = resultado
    return resultado


# ---------- Estado de ánimo del día ----------
def animo_del_dia(p, d=None):
    d = d or ahora()
    return random.Random(f"{p['id']}-{d.date()}").choice(ANIMOS)


def parsear_fecha(texto):
    try:
        return date.fromisoformat(texto.strip())
    except ValueError:
        return None


def rango_fechas_cercanas():
    hoy = ahora().date()
    return hoy - timedelta(days=3), hoy + timedelta(days=7)
