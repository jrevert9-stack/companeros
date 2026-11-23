"""Memoria persistente con SQLite."""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

DB = Path(__file__).parent / "partida.db"
CAMPOS_ESTADO = {"afinidad": "INTEGER DEFAULT 0", "lugar": "TEXT", "lugar_fecha": "TEXT",
                 "animo": "TEXT", "animo_fecha": "TEXT",
                 "pendiente_hasta": "TEXT",   # contestará más tarde (está ocupado/durmiendo)
                 "inicio": "TEXT",            # día en que os conocisteis (para su historia propia)
                 "apodo": "TEXT",             # cómo te llama
                 "aspecto": "TEXT",           # (fila '_usuario') cómo eres tú, sacado de tu selfie
                 "conocido": "INTEGER",       # 1 si ya os conocéis
                 "conocido_en": "TEXT",       # dónde os conocisteis
                 "sim_fecha": "TEXT",         # (fila '_mundo') último día en que el mundo "vivió" solo
                 "relacion": "TEXT"}          # amistad, tonteo, rollo, pareja, ex
USUARIO = "_usuario"
MUNDO = "_mundo"

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
    con.execute("CREATE TABLE IF NOT EXISTS momentos(id INTEGER PRIMARY KEY, personaje TEXT, texto TEXT, fecha TEXT)")
    con.execute("CREATE TABLE IF NOT EXISTS mundo_eventos(id INTEGER PRIMARY KEY, mundo TEXT, texto TEXT, fecha TEXT)")
    con.execute("CREATE TABLE IF NOT EXISTS personajes_extra(id TEXT PRIMARY KEY, datos TEXT)")
    con.execute("CREATE TABLE IF NOT EXISTS vinculos(a TEXT, b TEXT, tipo TEXT, fecha TEXT, PRIMARY KEY(a, b))")
    con.execute("CREATE TABLE IF NOT EXISTS secretos(id INTEGER PRIMARY KEY, texto TEXT, sobre TEXT, saben TEXT, fecha TEXT, destapado INTEGER DEFAULT 0)")
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


# ---------- Personajes creados durante el juego ----------
def guardar_personaje_extra(datos):
    with _con() as con:
        con.execute("INSERT OR REPLACE INTO personajes_extra(id, datos) VALUES (?,?)",
                    (datos["id"], json.dumps(datos, ensure_ascii=False)))


def personajes_extra():
    with _con() as con:
        return [json.loads(d) for (d,) in con.execute("SELECT datos FROM personajes_extra")]


def relaciones_sentimentales():
    with _con() as con:
        return dict(con.execute("SELECT personaje, relacion FROM estado WHERE relacion IN ('tonteo','rollo','pareja','ex')"))


# ---------- Vida sentimental entre personajes y secretos ----------
def poner_vinculo(a, b, tipo):
    a, b = sorted([a, b])
    with _con() as con:
        if tipo in ("nada", "ninguno"):
            con.execute("DELETE FROM vinculos WHERE a=? AND b=?", (a, b))
        else:
            con.execute("INSERT OR REPLACE INTO vinculos(a, b, tipo, fecha) VALUES (?,?,?,?)", (a, b, tipo, _ahora()[:10]))


def vinculos_de(pid):
    with _con() as con:
        filas = con.execute("SELECT a, b, tipo FROM vinculos WHERE a=? OR b=?", (pid, pid)).fetchall()
    return [(b if a == pid else a, tipo) for a, b, tipo in filas]


def todos_los_vinculos():
    with _con() as con:
        return con.execute("SELECT a, b, tipo FROM vinculos").fetchall()


def añadir_secreto(texto, sobre, saben):
    """sobre: ids implicados (los que no deben enterarse si son la 'víctima'); saben: ids que ya lo saben."""
    with _con() as con:
        con.execute("INSERT INTO secretos(texto, sobre, saben, fecha) VALUES (?,?,?,?)",
                    (texto, json.dumps(sobre), json.dumps(sorted(set(saben))), _ahora()[:10]))


def secretos():
    with _con() as con:
        filas = con.execute("SELECT id, texto, sobre, saben, destapado FROM secretos ORDER BY id").fetchall()
    return [{"id": i, "texto": t, "sobre": json.loads(s), "saben": json.loads(sa), "destapado": d} for i, t, s, sa, d in filas]


def actualizar_secreto(sid, saben=None, destapado=None):
    with _con() as con:
        if saben is not None:
            con.execute("UPDATE secretos SET saben=? WHERE id=?", (json.dumps(sorted(set(saben))), sid))
        if destapado is not None:
            con.execute("UPDATE secretos SET destapado=? WHERE id=?", (destapado, sid))


def conocidos():
    with _con() as con:
        return {p for (p,) in con.execute("SELECT personaje FROM estado WHERE conocido=1")}


# ---------- Momentos compartidos y sucesos del mundo ----------
def añadir_momento(personaje, texto):
    with _con() as con:
        con.execute("INSERT INTO momentos(personaje, texto, fecha) VALUES (?,?,?)",
                    (personaje, texto.strip(), _ahora()[:10]))


def momentos(personaje, limite=8):
    with _con() as con:
        filas = con.execute("SELECT fecha, texto FROM momentos WHERE personaje=? ORDER BY id DESC LIMIT ?",
                            (personaje, limite)).fetchall()
    return list(reversed(filas))


def añadir_suceso(mundo, texto):
    with _con() as con:
        con.execute("INSERT INTO mundo_eventos(mundo, texto, fecha) VALUES (?,?,?)",
                    (mundo, texto.strip(), _ahora()[:16].replace("T", " ")))


def sucesos(mundo, limite=10):
    with _con() as con:
        filas = con.execute("SELECT fecha, texto FROM mundo_eventos WHERE mundo=? ORDER BY id DESC LIMIT ?",
                            (mundo, limite)).fetchall()
    return list(reversed(filas))


def borrar_mensajes(personaje):
    with _con() as con:
        con.execute("DELETE FROM mensajes WHERE personaje=?", (personaje,))


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
        for tabla in ("mensajes", "recuerdos", "fechas", "estado", "momentos"):
            con.execute(f"DELETE FROM {tabla} WHERE personaje=?", (personaje,))


# ---------- Guardar / cargar partida ----------
TABLAS = {"mensajes": ["personaje", "rol", "texto", "fecha"],
          "recuerdos": ["personaje", "texto"],
          "fechas": ["personaje", "fecha", "texto"],
          "momentos": ["personaje", "texto", "fecha"],
          "mundo_eventos": ["mundo", "texto", "fecha"],
          "personajes_extra": ["id", "datos"],
          "vinculos": ["a", "b", "tipo", "fecha"],
          "secretos": ["texto", "sobre", "saben", "fecha", "destapado"],
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
