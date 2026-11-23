"""Memoria persistente con SQLite."""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

DB = Path(__file__).parent / "partida.db"
CAMPOS_ESTADO = {"afinidad": "INTEGER DEFAULT 0", "lugar": "TEXT", "lugar_fecha": "TEXT",
                 "animo": "TEXT", "animo_fecha": "TEXT"}

# Roles de mensajes:
#   user, assistant          -> texto normal
#   nota_voz                 -> mensaje del personaje que se escucha como audio
#   foto                     -> foto que manda el personaje (URL)
#   foto_usuario             -> foto que mandas tú (data URL)
#   lugar                    -> aviso de cambio de escena


def _ahora():
    return datetime.now().isoformat(timespec="seconds")


def _con():
    con = sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS mensajes(
        id INTEGER PRIMARY KEY, personaje TEXT, rol TEXT, texto TEXT, fecha TEXT)""")
    con.execute("CREATE TABLE IF NOT EXISTS recuerdos(id INTEGER PRIMARY KEY, personaje TEXT, texto TEXT)")
    con.execute("CREATE TABLE IF NOT EXISTS fechas(id INTEGER PRIMARY KEY, personaje TEXT, fecha TEXT, texto TEXT)")
    con.execute("CREATE TABLE IF NOT EXISTS estado(personaje TEXT PRIMARY KEY)")
    existentes = [c[1] for c in con.execute("PRAGMA table_info(estado)")]
    for campo, tipo in CAMPOS_ESTADO.items():
        if campo not in existentes:
            con.execute(f"ALTER TABLE estado ADD COLUMN {campo} {tipo}")
    return con


# ---------- Mensajes ----------
def guardar_mensaje(personaje, rol, texto):
    with _con() as con:
        con.execute("INSERT INTO mensajes(personaje, rol, texto, fecha) VALUES (?,?,?,?)",
                    (personaje, rol, texto, _ahora()))


def historial(personaje):
    with _con() as con:
        filas = con.execute("SELECT rol, texto, fecha FROM mensajes WHERE personaje=? ORDER BY id",
                            (personaje,)).fetchall()
    return [{"role": r, "content": t, "fecha": f} for r, t, f in filas]


def historial_para_ia(personaje, limite=40):
    """Convierte el historial al formato del modelo, uniendo mensajes seguidos del mismo lado."""
    salida = []
    for m in historial(personaje)[-limite:]:
        r, t = m["role"], m["content"]
        if r in ("user", "foto_usuario"):
            rol, texto = "user", (t if r == "user" else "(te envía una foto)")
        elif r in ("assistant", "nota_voz"):
            rol, texto = "assistant", t
        elif r == "foto":
            rol, texto = "assistant", "(le mandas una foto)"
        else:
            continue
        if salida and salida[-1]["role"] == rol:
            salida[-1]["content"] += "\n" + texto
        else:
            salida.append({"role": rol, "content": texto})
    while salida and salida[0]["role"] != "user":
        salida.pop(0)
    return salida


def segundos_desde_ultimo(personaje):
    with _con() as con:
        fila = con.execute("SELECT fecha FROM mensajes WHERE personaje=? ORDER BY id DESC LIMIT 1",
                           (personaje,)).fetchone()
    if not fila:
        return None
    return (datetime.now() - datetime.fromisoformat(fila[0])).total_seconds()


# ---------- Recuerdos y fechas ----------
def añadir_recuerdo(personaje, texto):
    texto = texto.strip()
    if not texto:
        return
    with _con() as con:
        if not con.execute("SELECT 1 FROM recuerdos WHERE personaje=? AND lower(texto)=lower(?)",
                           (personaje, texto)).fetchone():
            con.execute("INSERT INTO recuerdos(personaje, texto) VALUES (?,?)", (personaje, texto))


def recuerdos(personaje):
    with _con() as con:
        return [t for (t,) in con.execute("SELECT texto FROM recuerdos WHERE personaje=? ORDER BY id",
                                          (personaje,))]


def añadir_fecha(personaje, fecha_iso, texto):
    with _con() as con:
        if not con.execute("SELECT 1 FROM fechas WHERE personaje=? AND fecha=? AND lower(texto)=lower(?)",
                           (personaje, fecha_iso, texto.strip())).fetchone():
            con.execute("INSERT INTO fechas(personaje, fecha, texto) VALUES (?,?,?)",
                        (personaje, fecha_iso, texto.strip()))


def fechas(personaje, desde=None, hasta=None):
    with _con() as con:
        filas = con.execute("SELECT fecha, texto FROM fechas WHERE personaje=? ORDER BY fecha",
                            (personaje,)).fetchall()
    return [(f, t) for f, t in filas
            if (desde is None or f >= desde.isoformat()) and (hasta is None or f <= hasta.isoformat())]


# ---------- Estado (afinidad, lugar, ánimo) ----------
def leer(personaje, campo):
    with _con() as con:
        fila = con.execute(f"SELECT {campo} FROM estado WHERE personaje=?", (personaje,)).fetchone()
    return fila[0] if fila else None


def escribir(personaje, **valores):
    with _con() as con:
        con.execute("INSERT OR IGNORE INTO estado(personaje) VALUES (?)", (personaje,))
        for campo, valor in valores.items():
            assert campo in CAMPOS_ESTADO
            con.execute(f"UPDATE estado SET {campo}=? WHERE personaje=?", (valor, personaje))


def afinidad(personaje):
    return leer(personaje, "afinidad") or 0


def sumar_afinidad(personaje, delta):
    nueva = max(0, afinidad(personaje) + delta)
    escribir(personaje, afinidad=nueva)
    return nueva


def reiniciar(personaje):
    with _con() as con:
        for tabla in ("mensajes", "recuerdos", "fechas", "estado"):
            con.execute(f"DELETE FROM {tabla} WHERE personaje=?", (personaje,))


# ---------- Guardar / cargar partida ----------
TABLAS = {"mensajes": ["personaje", "rol", "texto", "fecha"],
          "recuerdos": ["personaje", "texto"],
          "fechas": ["personaje", "fecha", "texto"],
          "estado": ["personaje"] + list(CAMPOS_ESTADO)}


def exportar():
    with _con() as con:
        return json.dumps({t: [dict(zip(cols, fila)) for fila in
                               con.execute(f"SELECT {', '.join(cols)} FROM {t}")]
                           for t, cols in TABLAS.items()}, ensure_ascii=False)


def importar(texto_json):
    datos = json.loads(texto_json)
    with _con() as con:
        for t, cols in TABLAS.items():
            con.execute(f"DELETE FROM {t}")
            for fila in datos.get(t, []):
                if isinstance(fila, list):  # partidas de versiones anteriores
                    fila = dict(zip(cols, fila))
                presentes = [c for c in cols if c in fila]
                con.execute(f"INSERT INTO {t}({', '.join(presentes)}) VALUES ({', '.join('?' * len(presentes))})",
                            [fila[c] for c in presentes])
