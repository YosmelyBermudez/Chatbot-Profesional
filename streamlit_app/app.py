"""
App principal - 4 agentes especializados con RAG, resúmenes,
integración de conversaciones y entrada por voz.
"""

import os
from datetime import datetime

import streamlit as st

import db
import llm
import rag
from agents import AGENTES, listar_agentes, get_agente

st.set_page_config(
    page_title="Asistentes Profesionales",
    page_icon="🎯",
    layout="wide",
)

db.init_db()


# ============================================================
# AUTENTICACIÓN SIMPLE (multi-usuario)
# ============================================================

def pantalla_login():
    st.title("🎯 Asistentes Profesionales")
    st.caption("4 agentes especializados para profesionales: Procedimientos, Cargos, KPIs y LOPCYMAT")

    tab_login, tab_registro = st.tabs(["Iniciar sesión", "Registrarme"])

    with tab_login:
        st.subheader("Selecciona tu perfil")
        usuarios = db.listar_usuarios()
        if not usuarios:
            st.info("No hay usuarios registrados todavía. Pasa a la pestaña *Registrarme*.")
        else:
            opciones = {f"{u['nombre']} ({u['email']})": u for u in usuarios}
            seleccion = st.selectbox("Usuario", list(opciones.keys()))
            if st.button("Entrar", type="primary", use_container_width=True):
                st.session_state.usuario = opciones[seleccion]
                st.rerun()

    with tab_registro:
        st.subheader("Crear perfil nuevo")
        with st.form("registro"):
            email = st.text_input("Email *", placeholder="tu@empresa.com")
            nombre = st.text_input("Nombre completo *")
            profesion = st.text_input(
                "Profesión",
                placeholder="Ingeniero industrial, civil, mecánico, abogado, médico, etc.",
            )
            area = st.text_input(
                "Área / departamento",
                placeholder="Producción, RRHH, Calidad, Mantenimiento, Seguridad, etc.",
            )
            submitted = st.form_submit_button("Crear y entrar", type="primary",
                                              use_container_width=True)
            if submitted:
                if not email or not nombre:
                    st.error("Email y nombre son obligatorios")
                elif db.buscar_usuario_por_email(email):
                    st.error("Ya existe un usuario con ese email — usa la pestaña *Iniciar sesión*.")
                else:
                    user = db.crear_usuario(email, nombre, profesion, area)
                    st.session_state.usuario = user
                    st.success(f"¡Bienvenido, {nombre}!")
                    st.rerun()


# ============================================================
# Helpers de sesión
# ============================================================

def nueva_session_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def init_chat_state(agente_key: str, *, force_new: bool = False):
    """Asegura que exista una sesión activa para el agente actual."""
    key_session = f"session_{agente_key}"
    key_msgs = f"mensajes_{agente_key}"
    if force_new or key_session not in st.session_state:
        st.session_state[key_session] = nueva_session_id()
        st.session_state[key_msgs] = []


def get_msgs(agente_key: str) -> list:
    return st.session_state.get(f"mensajes_{agente_key}", [])


def set_msgs(agente_key: str, mensajes: list):
    st.session_state[f"mensajes_{agente_key}"] = mensajes


def get_session_id(agente_key: str) -> str:
    return st.session_state[f"session_{agente_key}"]


def cambiar_a_conversacion(agente_key: str, session_id: str):
    data = db.cargar_conversacion(st.session_state.usuario["id"], session_id)
    st.session_state[f"session_{agente_key}"] = session_id
    st.session_state[f"mensajes_{agente_key}"] = data["mensajes"]


def auto_guardar(agente_key: str):
    msgs = get_msgs(agente_key)
    if msgs:
        db.guardar_conversacion(
            st.session_state.usuario["id"],
            agente_key,
            get_session_id(agente_key),
            msgs,
            st.session_state.modelo_seleccionado,
        )


# ============================================================
# Construcción del prompt del agente con RAG + memoria
# ============================================================

def construir_mensajes(agente_key: str, mensajes_chat: list, ultima_pregunta: str,
                        contexto_extra: str = "") -> list:
    agente = get_agente(agente_key)
    user = st.session_state.usuario

    contexto_rag = rag.recuperar_contexto(agente_key, ultima_pregunta, top_k=4)
    memoria = db.obtener_memoria(user["id"])

    bloques_sistema = [agente["system_prompt"]]

    perfil = (
        f"PERFIL DEL USUARIO ACTUAL:\n"
        f"- Nombre: {user['nombre']}\n"
        f"- Profesión: {user.get('profesion') or 'no indicada'}\n"
        f"- Área: {user.get('area') or 'no indicada'}\n"
        "Adapta tus respuestas a este contexto profesional."
    )
    bloques_sistema.append(perfil)

    if memoria:
        bloques_sistema.append(
            "MEMORIA PERSISTENTE DEL USUARIO (info que ya compartió antes, no le preguntes de nuevo):\n"
            + memoria
        )

    if contexto_rag:
        bloques_sistema.append(
            "CONTEXTO RECUPERADO DE LOS DOCUMENTOS DEL USUARIO "
            "(úsalo como fuente principal y cita el nombre del archivo):\n"
            + contexto_rag
        )

    if contexto_extra:
        bloques_sistema.append(
            "CONTEXTO INTEGRADO DE CONVERSACIONES O RESÚMENES PREVIOS:\n" + contexto_extra
        )

    mensajes = [{"role": "system", "content": "\n\n".join(bloques_sistema)}]
    # Últimos 12 mensajes para no inflar el contexto
    for m in mensajes_chat[-12:]:
        mensajes.append(m)
    return mensajes


# ============================================================
# UI: Chat de un agente
# ============================================================

def render_chat(agente_key: str):
    agente = get_agente(agente_key)
    init_chat_state(agente_key)
    mensajes = get_msgs(agente_key)

    st.subheader(f"{agente['icono']} {agente['nombre']}")
    st.caption(agente["descripcion"])

    # Mostrar contexto integrado activo, si existe
    ctx_extra = st.session_state.get(f"contexto_extra_{agente_key}", "")
    if ctx_extra:
        with st.expander("📎 Contexto integrado activo (clic para ver)", expanded=False):
            st.markdown(ctx_extra)
            if st.button("Quitar contexto integrado", key=f"clear_ctx_{agente_key}"):
                st.session_state[f"contexto_extra_{agente_key}"] = ""
                st.rerun()

    # Historial
    if not mensajes:
        with st.chat_message("assistant"):
            st.markdown(
                f"Hola, soy **{agente['nombre']}**. {agente['descripcion']}\n\n"
                "Cuéntame qué necesitas y, si tienes documentos relacionados, "
                "súbelos en la barra lateral para que pueda usarlos como referencia."
            )
    for m in mensajes:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    # Entrada por voz
    audio_text = render_voice_input(agente_key)

    pregunta = st.chat_input("Escribe tu mensaje o usa el micrófono arriba…")
    if not pregunta and audio_text:
        pregunta = audio_text

    if pregunta:
        procesar_pregunta(agente_key, pregunta, ctx_extra)


def render_voice_input(agente_key: str) -> str:
    """Devuelve el texto transcrito si el usuario grabó algo nuevo."""
    try:
        from streamlit_mic_recorder import mic_recorder
    except Exception:
        return ""

    col1, col2 = st.columns([1, 4])
    with col1:
        audio = mic_recorder(
            start_prompt="🎤 Grabar voz",
            stop_prompt="⏹️ Detener",
            just_once=True,
            use_container_width=True,
            key=f"mic_{agente_key}",
        )

    if not audio:
        return ""

    audio_bytes = audio["bytes"] if isinstance(audio, dict) else None
    if not audio_bytes:
        return ""

    try:
        with col2:
            with st.spinner("Transcribiendo audio..."):
                texto = llm.transcribir_audio(audio_bytes, nombre="grabacion.wav")
        return (texto or "").strip()
    except Exception as e:
        st.warning(f"No se pudo transcribir: {e}")
        return ""


def procesar_pregunta(agente_key: str, pregunta: str, ctx_extra: str):
    mensajes = get_msgs(agente_key)
    mensajes.append({"role": "user", "content": pregunta})
    set_msgs(agente_key, mensajes)

    with st.chat_message("user"):
        st.markdown(pregunta)

    modelo_id = llm.MODELOS_GROQ[st.session_state.modelo_seleccionado]
    payload = construir_mensajes(agente_key, mensajes, pregunta, ctx_extra)

    with st.chat_message("assistant"):
        placeholder = st.empty()
        full = ""
        try:
            for tok in llm.chat_stream(modelo_id, payload,
                                       temperature=st.session_state.temperatura):
                full += tok
                placeholder.markdown(full + "▌")
            placeholder.markdown(full)
        except Exception as e:
            placeholder.error(f"Error del modelo: {e}")
            return

    mensajes.append({"role": "assistant", "content": full})
    set_msgs(agente_key, mensajes)
    auto_guardar(agente_key)
    st.rerun()


# ============================================================
# UI: Sidebar
# ============================================================

def sidebar_principal():
    user = st.session_state.usuario
    with st.sidebar:
        st.markdown(f"### 👋 Hola, {user['nombre']}")
        st.caption(f"{user.get('profesion') or '—'} | {user.get('area') or '—'}")
        if st.button("Cerrar sesión", use_container_width=True):
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()

        st.divider()

        st.markdown("### ⚙️ Modelo")
        st.session_state.modelo_seleccionado = st.selectbox(
            "Modelo de IA",
            list(llm.MODELOS_GROQ.keys()),
            index=list(llm.MODELOS_GROQ.keys()).index(
                st.session_state.get("modelo_seleccionado", llm.MODELO_DEFAULT)
            ),
            label_visibility="collapsed",
        )
        st.session_state.temperatura = st.slider(
            "Creatividad", 0.0, 1.0,
            st.session_state.get("temperatura", 0.7), 0.1,
        )


def sidebar_chat(agente_key: str):
    """Sidebar contextual para la pestaña de chat de un agente."""
    user = st.session_state.usuario
    with st.sidebar:
        st.divider()
        st.markdown(f"### 💬 Conversaciones de este agente")

        if st.button("➕ Nueva conversación", use_container_width=True, type="primary",
                     key=f"new_{agente_key}"):
            auto_guardar(agente_key)
            init_chat_state(agente_key, force_new=True)
            st.rerun()

        convs = db.listar_conversaciones(user["id"], agente_key)
        if not convs:
            st.caption("Aún no tienes conversaciones aquí.")
        for c in convs:
            actual = c["session_id"] == get_session_id(agente_key)
            etiqueta = ("👉 " if actual else "") + (c["titulo"] or "Sin título")[:38]
            estado = "🏁" if c["estado"] == "finalizada" else ""
            cols = st.columns([5, 1])
            with cols[0]:
                if st.button(f"{etiqueta} {estado}",
                             key=f"open_{agente_key}_{c['session_id']}",
                             use_container_width=True):
                    if not actual:
                        auto_guardar(agente_key)
                        cambiar_a_conversacion(agente_key, c["session_id"])
                    st.rerun()
            with cols[1]:
                if st.button("🗑️", key=f"del_{agente_key}_{c['session_id']}",
                             help="Eliminar conversación"):
                    db.eliminar_conversacion(user["id"], c["session_id"])
                    if actual:
                        init_chat_state(agente_key, force_new=True)
                    st.rerun()
            st.caption(f"📅 {c['fecha_actualizacion'][:16]}")


# ============================================================
# Pestaña: Documentos / Base de conocimiento (RAG)
# ============================================================

def pantalla_conocimiento():
    st.header("📚 Base de conocimiento (memoria del agente)")
    st.caption(
        "Sube documentos (PDF, Word, TXT, MD) por agente. "
        "Cada agente recordará y citará estos documentos en sus respuestas — "
        "no tendrás que repetir la información en cada conversación."
    )

    user = st.session_state.usuario
    tabs = st.tabs([f"{a['icono']} {a['nombre']}" for _, a in listar_agentes()])

    for tab, (key, agente) in zip(tabs, listar_agentes()):
        with tab:
            st.markdown(f"**{agente['descripcion']}**")

            archivos = st.file_uploader(
                f"Subir documentos para {agente['nombre']}",
                type=["pdf", "docx", "txt", "md"],
                accept_multiple_files=True,
                key=f"upload_{key}",
            )
            if archivos and st.button("Procesar e indexar", key=f"proc_{key}",
                                       type="primary"):
                exitos = 0
                with st.spinner("Procesando documentos..."):
                    for f in archivos:
                        try:
                            doc_id, n = rag.indexar_documento(
                                key, f.name, f.read(), user["id"]
                            )
                            st.success(f"✅ {f.name} — {n} fragmentos indexados")
                            exitos += 1
                        except Exception as e:
                            st.error(f"❌ {f.name}: {e}")
                if exitos:
                    st.balloons()

            st.divider()
            st.subheader("Documentos cargados")
            docs = db.listar_documentos(key)
            if not docs:
                st.info("Todavía no hay documentos para este agente.")
            for d in docs:
                cols = st.columns([5, 2, 1])
                with cols[0]:
                    st.markdown(f"**{d['nombre_archivo']}**")
                    st.caption(
                        f"Subido por {d['autor'] or '—'} el {d['fecha_subida'][:16]} · "
                        f"{d['n_chunks']} fragmentos"
                    )
                with cols[1]:
                    st.write("")
                with cols[2]:
                    if st.button("🗑️", key=f"del_doc_{d['id']}",
                                 help="Eliminar documento"):
                        db.eliminar_documento(d["id"])
                        st.rerun()


# ============================================================
# Pestaña: Resúmenes
# ============================================================

def pantalla_resumenes():
    st.header("📑 Biblioteca de resúmenes")
    st.caption(
        "Cuando finalices una conversación, su resumen aparece aquí. "
        "Puedes usar varios resúmenes como contexto para una nueva conversación."
    )

    user = st.session_state.usuario

    # Generar resumen desde conversaciones activas
    st.subheader("🏁 Finalizar una conversación")
    convs_activas = [
        c for c in db.listar_conversaciones(user["id"]) if c["estado"] == "activa"
    ]
    if not convs_activas:
        st.info("No tienes conversaciones activas para finalizar.")
    else:
        opts = {
            f"[{AGENTES[c['agente']]['icono']} {AGENTES[c['agente']]['nombre']}] "
            f"{c['titulo'][:50]} — {c['fecha_actualizacion'][:16]}": c
            for c in convs_activas
        }
        sel = st.selectbox("Conversación a finalizar y resumir", list(opts.keys()),
                            key="sel_finalizar")
        if st.button("🏁 Finalizar y generar resumen", type="primary"):
            conv = opts[sel]
            data = db.cargar_conversacion(user["id"], conv["session_id"])
            if not data["mensajes"]:
                st.warning("La conversación está vacía.")
            else:
                with st.spinner("Generando resumen..."):
                    try:
                        resumen = llm.generar_resumen(
                            AGENTES[conv["agente"]]["nombre"], data["mensajes"]
                        )
                        db.guardar_resumen(
                            user["id"], conv["id"], conv["agente"],
                            conv["titulo"], resumen,
                        )
                        db.marcar_conversacion_finalizada(
                            user["id"], conv["session_id"]
                        )
                        st.success("Resumen generado y guardado.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error generando resumen: {e}")

    st.divider()

    st.subheader("📚 Tus resúmenes guardados")
    resumenes = db.listar_resumenes(user["id"])
    if not resumenes:
        st.info("Aún no has generado resúmenes.")
        return

    for r in resumenes:
        ag = AGENTES.get(r["agente"], {"nombre": r["agente"], "icono": "💬"})
        with st.expander(
            f"{ag['icono']} **{r['titulo'] or 'Sin título'}** — {ag['nombre']} · "
            f"{r['fecha_creacion'][:16]}"
        ):
            st.markdown(r["contenido"])
            cols = st.columns([1, 1, 4])
            with cols[0]:
                st.download_button(
                    "⬇️ Descargar",
                    r["contenido"],
                    file_name=f"resumen_{r['id']}.md",
                    mime="text/markdown",
                    key=f"dl_{r['id']}",
                )
            with cols[1]:
                if st.button("🗑️ Eliminar", key=f"delr_{r['id']}"):
                    db.eliminar_resumen(user["id"], r["id"])
                    st.rerun()


# ============================================================
# Pestaña: Integrar conversaciones
# ============================================================

def pantalla_integrar():
    st.header("🔗 Integrar conversaciones")
    st.caption(
        "Combina varias conversaciones y/o resúmenes en un solo contexto "
        "para iniciar una nueva conversación con un agente."
    )

    user = st.session_state.usuario
    convs = db.listar_conversaciones(user["id"])
    resumenes = db.listar_resumenes(user["id"])

    if not convs and not resumenes:
        st.info("Aún no tienes conversaciones ni resúmenes para integrar.")
        return

    st.subheader("1. Selecciona qué quieres incluir")
    opts_convs = {
        f"💬 [{AGENTES[c['agente']]['icono']} {AGENTES[c['agente']]['nombre']}] "
        f"{c['titulo'][:45]} — {c['fecha_actualizacion'][:16]}": c
        for c in convs
    }
    opts_res = {
        f"📑 [{AGENTES.get(r['agente'], {}).get('icono', '💬')} "
        f"{AGENTES.get(r['agente'], {}).get('nombre', r['agente'])}] "
        f"{r['titulo'][:45]} — {r['fecha_creacion'][:16]}": r
        for r in resumenes
    }

    convs_sel = st.multiselect("Conversaciones", list(opts_convs.keys()))
    res_sel = st.multiselect("Resúmenes", list(opts_res.keys()))

    st.subheader("2. Elige el agente destino")
    agente_dest = st.selectbox(
        "Agente para la nueva conversación",
        list(AGENTES.keys()),
        format_func=lambda k: f"{AGENTES[k]['icono']} {AGENTES[k]['nombre']}",
    )

    if st.button("🚀 Crear conversación con contexto integrado", type="primary",
                 disabled=not (convs_sel or res_sel)):
        partes = []
        for label in convs_sel:
            c = opts_convs[label]
            data = db.cargar_conversacion(user["id"], c["session_id"])
            ag = AGENTES.get(c["agente"], {"nombre": c["agente"]})
            transcripcion = "\n".join(
                f"{'Usuario' if m['role'] == 'user' else 'Asistente'}: {m['content']}"
                for m in data["mensajes"]
            )
            partes.append(
                f"### Conversación con {ag['nombre']}: {c['titulo']}\n{transcripcion}"
            )
        for label in res_sel:
            r = opts_res[label]
            ag = AGENTES.get(r["agente"], {"nombre": r["agente"]})
            partes.append(
                f"### Resumen de conversación con {ag['nombre']}: {r['titulo']}\n"
                + r["contenido"]
            )

        contexto = "\n\n---\n\n".join(partes)
        # Iniciar nueva conversación en el agente destino con este contexto cargado
        init_chat_state(agente_dest, force_new=True)
        st.session_state[f"contexto_extra_{agente_dest}"] = contexto
        st.session_state.agente_actual = agente_dest
        st.session_state.tab_actual = "chat"
        st.success(
            f"Contexto integrado y listo. Cambiando a {AGENTES[agente_dest]['nombre']}..."
        )
        st.rerun()


# ============================================================
# Pestaña: Memoria del usuario
# ============================================================

def pantalla_memoria():
    st.header("🧠 Tu memoria persistente")
    st.caption(
        "Anota aquí información sobre ti, tu empresa, tus procesos o cualquier contexto "
        "que TODOS los agentes deban tener presente sin que lo repitas en cada conversación."
    )
    user = st.session_state.usuario
    actual = db.obtener_memoria(user["id"])
    nuevo = st.text_area(
        "Información persistente",
        value=actual,
        height=300,
        placeholder=(
            "Ejemplos:\n"
            "- Trabajo en una planta de manufactura textil de 80 empleados en Maracay.\n"
            "- Mi cargo es Coordinador de Calidad.\n"
            "- Estamos certificando ISO 9001.\n"
            "- El área crítica es tintorería, con 3 turnos.\n"
        ),
    )
    if st.button("Guardar memoria", type="primary"):
        db.guardar_memoria(user["id"], nuevo.strip())
        st.success("Memoria actualizada — todos los agentes la tendrán presente.")


# ============================================================
# Layout principal
# ============================================================

def app():
    if "usuario" not in st.session_state:
        pantalla_login()
        return

    if "modelo_seleccionado" not in st.session_state:
        st.session_state.modelo_seleccionado = llm.MODELO_DEFAULT
    if "temperatura" not in st.session_state:
        st.session_state.temperatura = 0.7
    if "agente_actual" not in st.session_state:
        st.session_state.agente_actual = "procedimientos"
    if "tab_actual" not in st.session_state:
        st.session_state.tab_actual = "chat"

    sidebar_principal()

    st.title("🎯 Asistentes Profesionales")

    # Selector principal de pestañas
    secciones = {
        "chat": "💬 Chat con agentes",
        "conocimiento": "📚 Documentos",
        "resumenes": "📑 Resúmenes",
        "integrar": "🔗 Integrar",
        "memoria": "🧠 Memoria",
    }
    cols = st.columns(len(secciones))
    for col, (key, label) in zip(cols, secciones.items()):
        with col:
            if st.button(label, use_container_width=True,
                         type="primary" if st.session_state.tab_actual == key else "secondary",
                         key=f"tab_{key}"):
                st.session_state.tab_actual = key
                st.rerun()

    st.divider()

    if st.session_state.tab_actual == "chat":
        # Selector de agente
        cols = st.columns(len(AGENTES))
        for col, (key, ag) in zip(cols, listar_agentes()):
            with col:
                if st.button(
                    f"{ag['icono']} {ag['nombre']}",
                    use_container_width=True,
                    type="primary" if st.session_state.agente_actual == key else "secondary",
                    key=f"agente_{key}",
                ):
                    st.session_state.agente_actual = key
                    st.rerun()

        st.write("")
        render_chat(st.session_state.agente_actual)
        sidebar_chat(st.session_state.agente_actual)

    elif st.session_state.tab_actual == "conocimiento":
        pantalla_conocimiento()
    elif st.session_state.tab_actual == "resumenes":
        pantalla_resumenes()
    elif st.session_state.tab_actual == "integrar":
        pantalla_integrar()
    elif st.session_state.tab_actual == "memoria":
        pantalla_memoria()


if __name__ == "__main__":
    if not os.environ.get("GROQ_API_KEY"):
        st.error("Falta la variable de entorno GROQ_API_KEY")
    else:
        app()
