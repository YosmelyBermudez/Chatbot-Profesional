"""
Capa de base de datos SQLite.
Maneja: usuarios, conversaciones, resúmenes, documentos para RAG y memoria del usuario.
"""

import sqlite3
import json
import os
import secrets
from datetime import datetime
from typing import Optional
import bcrypt

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "agentes.db")


def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        nombre TEXT NOT NULL,
        profesion TEXT,
        area TEXT,
        fecha_registro TEXT,
        password_hash TEXT
    )""")

    try:
        c.execute("ALTER TABLE usuarios ADD COLUMN password_hash TEXT")
    except sqlite3.OperationalError:
        pass

    c.execute("""CREATE TABLE IF NOT EXISTS sesiones (
        token TEXT PRIMARY KEY,
        usuario_id INTEGER NOT NULL,
        fecha_creacion TEXT,
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS conversaciones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario_id INTEGER NOT NULL,
        agente TEXT NOT NULL,
        session_id TEXT NOT NULL,
        titulo TEXT,
        estado TEXT DEFAULT 'activa',
        fecha_creacion TEXT,
        fecha_actualizacion TEXT,
        mensajes TEXT,
        modelo_usado TEXT,
        ultimo_mensaje TEXT,
        UNIQUE(usuario_id, session_id),
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS resumenes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario_id INTEGER NOT NULL,
        conversacion_id INTEGER,
        agente TEXT,
        titulo TEXT,
        contenido TEXT,
        fecha_creacion TEXT,
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS documentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        agente TEXT NOT NULL,
        nombre_archivo TEXT,
        contenido TEXT,
        subido_por INTEGER,
        fecha_subida TEXT,
        FOREIGN KEY (subido_por) REFERENCES usuarios(id)
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS chunks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        documento_id INTEGER NOT NULL,
        agente TEXT,
        chunk_index INTEGER,
        texto TEXT,
        FOREIGN KEY (documento_id) REFERENCES documentos(id) ON DELETE CASCADE
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS memoria_usuario (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario_id INTEGER UNIQUE NOT NULL,
        contenido TEXT,
        fecha_actualizacion TEXT,
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
    )""")

    conn.commit()
    conn.close()


# ---------- Usuarios ----------

def buscar_usuario_por_email(email: str) -> Optional[dict]:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM usuarios WHERE email = ?", (email.lower().strip(),)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def crear_usuario(email: str, nombre: str, profesion: str, area: str,
                  password: str) -> dict:
    conn = get_conn()
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    conn.execute(
        """INSERT INTO usuarios (email, nombre, profesion, area, fecha_registro, password_hash)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (email.lower().strip(), nombre.strip(), profesion.strip(), area.strip(),
         ahora, pw_hash),
    )
    conn.commit()
    conn.close()
    user = buscar_usuario_por_email(email)
    if user is None:
        raise RuntimeError("No se pudo crear el usuario")
    return user

def verificar_password(email: str, password: str) -> Optional[dict]:
    user = buscar_usuario_por_email(email)
    if not user or not user.get("password_hash"):
        return None
    try:
        if bcrypt.checkpw(password.encode("utf-8"),
                          user["password_hash"].encode("utf-8")):
            return user
    except (ValueError, TypeError):
        return None
    return None


def crear_sesion(usuario_id: int) -> str:
    token = secrets.token_urlsafe(32)
    conn = get_conn()
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "INSERT INTO sesiones (token, usuario_id, fecha_creacion) VALUES (?, ?, ?)",
        (token, usuario_id, ahora),
    )
    conn.commit(); conn.close()
    return token


def usuario_por_token(token: str) -> Optional[dict]:
    if not token:
        return None
    conn = get_conn()
    row = conn.execute(
        """SELECT u.* FROM usuarios u
           JOIN sesiones s ON s.usuario_id = u.id
           WHERE s.token = ?""", (token,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def eliminar_sesion(token: str):
    if not token:
        return
    conn = get_conn()
    conn.execute("DELETE FROM sesiones WHERE token = ?", (token,))
    conn.commit(); conn.close()


def listar_usuarios() -> list:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM usuarios ORDER BY nombre").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------- Conversaciones ----------

def guardar_conversacion(
    usuario_id: int,
    agente: str,
    session_id: str,
    mensajes_serializados: list,
    modelo: str,
):
    if not mensajes_serializados:
        return
    conn = get_conn()
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    titulo = "Nueva conversación"
    for m in mensajes_serializados:
        if m["role"] == "user":
            titulo = m["content"][:60].strip() or titulo
            break

    ultimo_raw = mensajes_serializados[-1]["content"]
    ultimo = ultimo_raw[:80] + "..." if len(ultimo_raw) > 80 else ultimo_raw
    contenido = json.dumps(mensajes_serializados, ensure_ascii=False)

    existente = conn.execute(
        "SELECT id, estado FROM conversaciones WHERE usuario_id=? AND session_id=?",
        (usuario_id, session_id),
    ).fetchone()

    if existente:
        conn.execute(
            """UPDATE conversaciones
               SET fecha_actualizacion=?, mensajes=?, modelo_usado=?, ultimo_mensaje=?, titulo=?
               WHERE usuario_id=? AND session_id=?""",
            (ahora, contenido, modelo, ultimo, titulo, usuario_id, session_id),
        )
    else:
        conn.execute(
            """INSERT INTO conversaciones
               (usuario_id, agente, session_id, titulo, fecha_creacion,
                fecha_actualizacion, mensajes, modelo_usado, ultimo_mensaje)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (usuario_id, agente, session_id, titulo, ahora, ahora,
             contenido, modelo, ultimo),
        )

    conn.commit()
    conn.close()


def cargar_conversacion(usuario_id: int, session_id: str) -> dict:
    conn = get_conn()
    row = conn.execute(
        """SELECT * FROM conversaciones WHERE usuario_id=? AND session_id=?""",
        (usuario_id, session_id),
    ).fetchone()
    conn.close()
    if not row:
        return {"mensajes": [], "estado": "activa", "agente": None}
    data = dict(row)
    data["mensajes"] = json.loads(data["mensajes"]) if data.get("mensajes") else []
    return data


def listar_conversaciones(usuario_id: int, agente: Optional[str] = None) -> list:
    conn = get_conn()
    if agente:
        rows = conn.execute(
            """SELECT id, session_id, agente, titulo, estado, fecha_actualizacion,
                      ultimo_mensaje
               FROM conversaciones
               WHERE usuario_id=? AND agente=?
               ORDER BY fecha_actualizacion DESC""",
            (usuario_id, agente),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT id, session_id, agente, titulo, estado, fecha_actualizacion,
                      ultimo_mensaje
               FROM conversaciones
               WHERE usuario_id=?
               ORDER BY fecha_actualizacion DESC""",
            (usuario_id,),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def eliminar_conversacion(usuario_id: int, session_id: str):
    conn = get_conn()
    conn.execute(
        "DELETE FROM conversaciones WHERE usuario_id=? AND session_id=?",
        (usuario_id, session_id),
    )
    conn.commit()
    conn.close()


def marcar_conversacion_finalizada(usuario_id: int, session_id: str):
    conn = get_conn()
    conn.execute(
        "UPDATE conversaciones SET estado='finalizada' WHERE usuario_id=? AND session_id=?",
        (usuario_id, session_id),
    )
    conn.commit()
    conn.close()


# ---------- Resúmenes ----------

def guardar_resumen(usuario_id: int, conversacion_id: int, agente: str,
                    titulo: str, contenido: str) -> int:
    conn = get_conn()
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur = conn.execute(
        """INSERT INTO resumenes
           (usuario_id, conversacion_id, agente, titulo, contenido, fecha_creacion)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (usuario_id, conversacion_id, agente, titulo, contenido, ahora),
    )
    rid = cur.lastrowid
    conn.commit()
    conn.close()
    return rid or 0


def listar_resumenes(usuario_id: int) -> list:
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM resumenes WHERE usuario_id=?
           ORDER BY fecha_creacion DESC""",
        (usuario_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def obtener_resumen(resumen_id: int) -> Optional[dict]:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM resumenes WHERE id=?", (resumen_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def eliminar_resumen(usuario_id: int, resumen_id: int):
    conn = get_conn()
    conn.execute(
        "DELETE FROM resumenes WHERE usuario_id=? AND id=?", (usuario_id, resumen_id)
    )
    conn.commit()
    conn.close()


# ---------- Documentos / RAG ----------

def guardar_documento(agente: str, nombre_archivo: str, contenido: str,
                      subido_por: int) -> int:
    conn = get_conn()
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur = conn.execute(
        """INSERT INTO documentos (agente, nombre_archivo, contenido, subido_por, fecha_subida)
           VALUES (?, ?, ?, ?, ?)""",
        (agente, nombre_archivo, contenido, subido_por, ahora),
    )
    doc_id = cur.lastrowid
    conn.commit()
    conn.close()
    return doc_id or 0


def guardar_chunks(documento_id: int, agente: str, chunks: list):
    conn = get_conn()
    conn.executemany(
        """INSERT INTO chunks (documento_id, agente, chunk_index, texto)
           VALUES (?, ?, ?, ?)""",
        [(documento_id, agente, i, c) for i, c in enumerate(chunks)],
    )
    conn.commit()
    conn.close()


def listar_documentos(agente: str) -> list:
    conn = get_conn()
    rows = conn.execute(
        """SELECT d.id, d.nombre_archivo, d.fecha_subida, u.nombre as autor,
                  (SELECT COUNT(*) FROM chunks WHERE documento_id=d.id) as n_chunks
           FROM documentos d
           LEFT JOIN usuarios u ON u.id = d.subido_por
           WHERE d.agente=?
           ORDER BY d.fecha_subida DESC""",
        (agente,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def listar_chunks(agente: str) -> list:
    conn = get_conn()
    rows = conn.execute(
        """SELECT c.id, c.texto, c.documento_id, d.nombre_archivo
           FROM chunks c
           LEFT JOIN documentos d ON d.id = c.documento_id
           WHERE c.agente=?""",
        (agente,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def eliminar_documento(documento_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM chunks WHERE documento_id=?", (documento_id,))
    conn.execute("DELETE FROM documentos WHERE id=?", (documento_id,))
    conn.commit()
    conn.close()


# ---------- Memoria del usuario ----------

def obtener_memoria(usuario_id: int) -> str:
    conn = get_conn()
    row = conn.execute(
        "SELECT contenido FROM memoria_usuario WHERE usuario_id=?", (usuario_id,)
    ).fetchone()
    conn.close()
    return row["contenido"] if row else ""


def guardar_memoria(usuario_id: int, contenido: str):
    conn = get_conn()
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    existente = conn.execute(
        "SELECT id FROM memoria_usuario WHERE usuario_id=?", (usuario_id,)
    ).fetchone()
    if existente:
        conn.execute(
            "UPDATE memoria_usuario SET contenido=?, fecha_actualizacion=? WHERE usuario_id=?",
            (contenido, ahora, usuario_id),
        )
    else:
        conn.execute(
            """INSERT INTO memoria_usuario (usuario_id, contenido, fecha_actualizacion)
               VALUES (?, ?, ?)""",
            (usuario_id, contenido, ahora),
        )
    conn.commit()
    conn.close()
