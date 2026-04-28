"""
Capa de base de datos.
Usa PostgreSQL (Supabase) si SUPABASE_URL está configurada, si no usa SQLite local.
"""

import json
import os
import secrets
from datetime import datetime
from typing import Optional
import bcrypt

# ─── Detectar backend ───────────────────────────────────────────────────────

def _leer_supabase_url() -> str:
    url = os.environ.get("SUPABASE_URL", "")
    if url:
        return url
    try:
        import streamlit as st
        url = st.secrets.get("SUPABASE_URL", "")
        if url:
            return url
    except Exception:
        pass
    return ""

SUPABASE_URL = _leer_supabase_url()
USAR_POSTGRES = bool(SUPABASE_URL)

# SQLite path (solo se usa si no hay Supabase)
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "agentes.db")

# ─── Conexión ────────────────────────────────────────────────────────────────

def get_conn():
    if USAR_POSTGRES:
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(SUPABASE_URL)
        return conn
    else:
        import sqlite3
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn


def _placeholder(n: int = 1) -> str:
    """Devuelve %s para Postgres o ? para SQLite."""
    if USAR_POSTGRES:
        return ", ".join(["%s"] * n)
    return ", ".join(["?"] * n)


def _ph() -> str:
    return "%s" if USAR_POSTGRES else "?"


def _fetchall(cursor) -> list[dict]:
    if USAR_POSTGRES:
        cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]
    return [dict(r) for r in cursor.fetchall()]


def _fetchone(cursor) -> Optional[dict]:
    if USAR_POSTGRES:
        if cursor.description is None:
            return None
        cols = [d[0] for d in cursor.description]
        row = cursor.fetchone()
        return dict(zip(cols, row)) if row else None
    row = cursor.fetchone()
    return dict(row) if row else None


# ─── Inicialización ──────────────────────────────────────────────────────────

def init_db():
    conn = get_conn()
    c = conn.cursor()
    ph = _ph()

    if USAR_POSTGRES:
        c.execute("""CREATE TABLE IF NOT EXISTS usuarios (
            id SERIAL PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            nombre TEXT NOT NULL,
            profesion TEXT,
            area TEXT,
            fecha_registro TEXT,
            password_hash TEXT
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS sesiones (
            token TEXT PRIMARY KEY,
            usuario_id INTEGER NOT NULL,
            fecha_creacion TEXT,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS conversaciones (
            id SERIAL PRIMARY KEY,
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
            id SERIAL PRIMARY KEY,
            usuario_id INTEGER NOT NULL,
            conversacion_id INTEGER,
            agente TEXT,
            titulo TEXT,
            contenido TEXT,
            fecha_creacion TEXT,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS documentos (
            id SERIAL PRIMARY KEY,
            agente TEXT NOT NULL,
            nombre_archivo TEXT,
            contenido TEXT,
            subido_por INTEGER,
            fecha_subida TEXT,
            FOREIGN KEY (subido_por) REFERENCES usuarios(id)
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS chunks (
            id SERIAL PRIMARY KEY,
            documento_id INTEGER NOT NULL,
            agente TEXT,
            chunk_index INTEGER,
            texto TEXT,
            FOREIGN KEY (documento_id) REFERENCES documentos(id) ON DELETE CASCADE
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS memoria_usuario (
            id SERIAL PRIMARY KEY,
            usuario_id INTEGER UNIQUE NOT NULL,
            contenido TEXT,
            fecha_actualizacion TEXT,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
        )""")

    else:
        import sqlite3
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
        except Exception:
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


# ─── Usuarios ────────────────────────────────────────────────────────────────

def buscar_usuario_por_email(email: str) -> Optional[dict]:
    conn = get_conn()
    c = conn.cursor()
    c.execute(f"SELECT * FROM usuarios WHERE email = {_ph()}", (email.lower().strip(),))
    row = _fetchone(c)
    conn.close()
    return row


def crear_usuario(email: str, nombre: str, profesion: str, area: str,
                  password: str) -> dict:
    conn = get_conn()
    c = conn.cursor()
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    ph = _ph()
    c.execute(
        f"""INSERT INTO usuarios (email, nombre, profesion, area, fecha_registro, password_hash)
           VALUES ({_placeholder(6)})""",
        (email.lower().strip(), nombre.strip(), profesion.strip(), area.strip(), ahora, pw_hash),
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
    c = conn.cursor()
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute(
        f"INSERT INTO sesiones (token, usuario_id, fecha_creacion) VALUES ({_placeholder(3)})",
        (token, usuario_id, ahora),
    )
    conn.commit()
    conn.close()
    return token


def usuario_por_token(token: str) -> Optional[dict]:
    if not token:
        return None
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        f"""SELECT u.* FROM usuarios u
           JOIN sesiones s ON s.usuario_id = u.id
           WHERE s.token = {_ph()}""", (token,)
    )
    row = _fetchone(c)
    conn.close()
    return row


def eliminar_sesion(token: str):
    if not token:
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute(f"DELETE FROM sesiones WHERE token = {_ph()}", (token,))
    conn.commit()
    conn.close()


def listar_usuarios() -> list:
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM usuarios ORDER BY nombre")
    rows = _fetchall(c)
    conn.close()
    return rows


# ─── Conversaciones ──────────────────────────────────────────────────────────

def guardar_conversacion(usuario_id: int, agente: str, session_id: str,
                         mensajes_serializados: list, modelo: str):
    if not mensajes_serializados:
        return
    conn = get_conn()
    c = conn.cursor()
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    titulo = "Nueva conversación"
    for m in mensajes_serializados:
        if m["role"] == "user":
            titulo = m["content"][:60].strip() or titulo
            break

    ultimo_raw = mensajes_serializados[-1]["content"]
    ultimo = ultimo_raw[:80] + "..." if len(ultimo_raw) > 80 else ultimo_raw
    contenido = json.dumps(mensajes_serializados, ensure_ascii=False)

    c.execute(
        f"SELECT id FROM conversaciones WHERE usuario_id={_ph()} AND session_id={_ph()}",
        (usuario_id, session_id),
    )
    existente = _fetchone(c)

    if existente:
        c.execute(
            f"""UPDATE conversaciones
               SET fecha_actualizacion={_ph()}, mensajes={_ph()}, modelo_usado={_ph()},
                   ultimo_mensaje={_ph()}, titulo={_ph()}
               WHERE usuario_id={_ph()} AND session_id={_ph()}""",
            (ahora, contenido, modelo, ultimo, titulo, usuario_id, session_id),
        )
    else:
        c.execute(
            f"""INSERT INTO conversaciones
               (usuario_id, agente, session_id, titulo, fecha_creacion,
                fecha_actualizacion, mensajes, modelo_usado, ultimo_mensaje)
               VALUES ({_placeholder(9)})""",
            (usuario_id, agente, session_id, titulo, ahora, ahora, contenido, modelo, ultimo),
        )

    conn.commit()
    conn.close()


def cargar_conversacion(usuario_id: int, session_id: str) -> dict:
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        f"SELECT * FROM conversaciones WHERE usuario_id={_ph()} AND session_id={_ph()}",
        (usuario_id, session_id),
    )
    data = _fetchone(c)
    conn.close()
    if not data:
        return {"mensajes": [], "estado": "activa", "agente": None}
    data["mensajes"] = json.loads(data["mensajes"]) if data.get("mensajes") else []
    return data


def listar_conversaciones(usuario_id: int, agente: Optional[str] = None) -> list:
    conn = get_conn()
    c = conn.cursor()
    if agente:
        c.execute(
            f"""SELECT id, session_id, agente, titulo, estado, fecha_actualizacion, ultimo_mensaje
               FROM conversaciones WHERE usuario_id={_ph()} AND agente={_ph()}
               ORDER BY fecha_actualizacion DESC""",
            (usuario_id, agente),
        )
    else:
        c.execute(
            f"""SELECT id, session_id, agente, titulo, estado, fecha_actualizacion, ultimo_mensaje
               FROM conversaciones WHERE usuario_id={_ph()}
               ORDER BY fecha_actualizacion DESC""",
            (usuario_id,),
        )
    rows = _fetchall(c)
    conn.close()
    return rows


def eliminar_conversacion(usuario_id: int, session_id: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        f"DELETE FROM conversaciones WHERE usuario_id={_ph()} AND session_id={_ph()}",
        (usuario_id, session_id),
    )
    conn.commit()
    conn.close()


def marcar_conversacion_finalizada(usuario_id: int, session_id: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        f"UPDATE conversaciones SET estado='finalizada' WHERE usuario_id={_ph()} AND session_id={_ph()}",
        (usuario_id, session_id),
    )
    conn.commit()
    conn.close()


# ─── Resúmenes ───────────────────────────────────────────────────────────────

def guardar_resumen(usuario_id: int, conversacion_id: int, agente: str,
                    titulo: str, contenido: str) -> int:
    conn = get_conn()
    c = conn.cursor()
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if USAR_POSTGRES:
        c.execute(
            f"""INSERT INTO resumenes
               (usuario_id, conversacion_id, agente, titulo, contenido, fecha_creacion)
               VALUES ({_placeholder(6)}) RETURNING id""",
            (usuario_id, conversacion_id, agente, titulo, contenido, ahora),
        )
        rid = c.fetchone()[0]
    else:
        c.execute(
            f"""INSERT INTO resumenes
               (usuario_id, conversacion_id, agente, titulo, contenido, fecha_creacion)
               VALUES ({_placeholder(6)})""",
            (usuario_id, conversacion_id, agente, titulo, contenido, ahora),
        )
        rid = c.lastrowid
    conn.commit()
    conn.close()
    return rid or 0


def listar_resumenes(usuario_id: int) -> list:
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        f"SELECT * FROM resumenes WHERE usuario_id={_ph()} ORDER BY fecha_creacion DESC",
        (usuario_id,),
    )
    rows = _fetchall(c)
    conn.close()
    return rows


def obtener_resumen(resumen_id: int) -> Optional[dict]:
    conn = get_conn()
    c = conn.cursor()
    c.execute(f"SELECT * FROM resumenes WHERE id={_ph()}", (resumen_id,))
    row = _fetchone(c)
    conn.close()
    return row


def eliminar_resumen(usuario_id: int, resumen_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        f"DELETE FROM resumenes WHERE usuario_id={_ph()} AND id={_ph()}",
        (usuario_id, resumen_id),
    )
    conn.commit()
    conn.close()


# ─── Documentos / RAG ────────────────────────────────────────────────────────

def guardar_documento(agente: str, nombre_archivo: str, contenido: str,
                      subido_por: int, archivo_bytes: bytes = None) -> int:
    conn = get_conn()
    c = conn.cursor()
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if USAR_POSTGRES:
        c.execute(
            f"""INSERT INTO documentos (agente, nombre_archivo, contenido, subido_por, fecha_subida, archivo_bytes)
               VALUES ({_placeholder(6)}) RETURNING id""",
            (agente, nombre_archivo, contenido, subido_por, ahora, archivo_bytes),
        )
        doc_id = c.fetchone()[0]
    else:
        c.execute(
            f"""INSERT INTO documentos (agente, nombre_archivo, contenido, subido_por, fecha_subida, archivo_bytes)
               VALUES ({_placeholder(6)})""",
            (agente, nombre_archivo, contenido, subido_por, ahora, archivo_bytes),
        )
        doc_id = c.lastrowid
    conn.commit()
    conn.close()
    return doc_id or 0


def guardar_chunks(documento_id: int, agente: str, chunks: list):
    conn = get_conn()
    c = conn.cursor()
    c.executemany(
        f"INSERT INTO chunks (documento_id, agente, chunk_index, texto) VALUES ({_placeholder(4)})",
        [(documento_id, agente, i, ch) for i, ch in enumerate(chunks)],
    )
    conn.commit()
    conn.close()


def listar_documentos(agente: str, usuario_id: Optional[int] = None) -> list:
    conn = get_conn()
    c = conn.cursor()
    if usuario_id:
        c.execute(
            f"""SELECT d.id, d.nombre_archivo, d.fecha_subida, u.nombre as autor,
                      (SELECT COUNT(*) FROM chunks WHERE documento_id=d.id) as n_chunks
               FROM documentos d
               LEFT JOIN usuarios u ON u.id = d.subido_por
               WHERE d.agente={_ph()} AND d.subido_por={_ph()}
               ORDER BY d.fecha_subida DESC""",
            (agente, usuario_id),
        )
    else:
        c.execute(
            f"""SELECT d.id, d.nombre_archivo, d.fecha_subida, u.nombre as autor,
                      (SELECT COUNT(*) FROM chunks WHERE documento_id=d.id) as n_chunks
               FROM documentos d
               LEFT JOIN usuarios u ON u.id = d.subido_por
               WHERE d.agente={_ph()}
               ORDER BY d.fecha_subida DESC""",
            (agente,),
        )
    rows = _fetchall(c)
    conn.close()
    return rows

def listar_chunks(agente: str, usuario_id: Optional[int] = None) -> list:
    conn = get_conn()
    c = conn.cursor()
    if usuario_id:
        c.execute(
            f"""SELECT c.id, c.texto, c.documento_id, d.nombre_archivo
               FROM chunks c
               LEFT JOIN documentos d ON d.id = c.documento_id
               WHERE c.agente={_ph()} AND d.subido_por={_ph()}""",
            (agente, usuario_id),
        )
    else:
        c.execute(
            f"""SELECT c.id, c.texto, c.documento_id, d.nombre_archivo
               FROM chunks c
               LEFT JOIN documentos d ON d.id = c.documento_id
               WHERE c.agente={_ph()}""",
            (agente,),
        )


def eliminar_documento(documento_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute(f"DELETE FROM chunks WHERE documento_id={_ph()}", (documento_id,))
    c.execute(f"DELETE FROM documentos WHERE id={_ph()}", (documento_id,))
    conn.commit()
    conn.close()

def obtener_contenido_documento(documento_id: int) -> Optional[dict]:
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        f"SELECT nombre_archivo, contenido FROM documentos WHERE id={_ph()}",
        (documento_id,),
    )
    row = _fetchone(c)
    conn.close()
    if not row:
        return None
    return {"nombre": row["nombre_archivo"], "contenido": row["contenido"] or ""}

def obtener_bytes_documento(documento_id: int) -> Optional[dict]:
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        f"SELECT nombre_archivo, archivo_bytes FROM documentos WHERE id={_ph()}",
        (documento_id,),
    )
    row = _fetchone(c)
    conn.close()
    if not row or not row.get("archivo_bytes"):
        return None
    return {
        "nombre": row["nombre_archivo"],
        "bytes": bytes(row["archivo_bytes"]),
    }

# ─── Memoria del usuario ─────────────────────────────────────────────────────

def obtener_memoria(usuario_id: int) -> str:
    conn = get_conn()
    c = conn.cursor()
    c.execute(f"SELECT contenido FROM memoria_usuario WHERE usuario_id={_ph()}", (usuario_id,))
    row = _fetchone(c)
    conn.close()
    return row["contenido"] if row else ""


def guardar_memoria(usuario_id: int, contenido: str):
    conn = get_conn()
    c = conn.cursor()
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute(f"SELECT id FROM memoria_usuario WHERE usuario_id={_ph()}", (usuario_id,))
    existente = _fetchone(c)
    if existente:
        c.execute(
            f"UPDATE memoria_usuario SET contenido={_ph()}, fecha_actualizacion={_ph()} WHERE usuario_id={_ph()}",
            (contenido, ahora, usuario_id),
        )
    else:
        c.execute(
            f"INSERT INTO memoria_usuario (usuario_id, contenido, fecha_actualizacion) VALUES ({_placeholder(3)})",
            (usuario_id, contenido, ahora),
        )
    conn.commit()
    conn.close()