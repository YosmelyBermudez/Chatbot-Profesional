"""
Cliente Groq + OpenRouter + Gemini para LLM y transcripción de voz (Whisper).
Si Groq falla (p.ej. 403 desde Venezuela), cae automáticamente a OpenRouter.
"""

import os
from typing import List, Iterator
from groq import Groq

try:
    import google.generativeai as genai
except Exception:
    genai = None


def _leer_clave(*nombres: str) -> str:
    """Lee de os.environ y, si está disponible, de st.secrets."""
    for n in nombres:
        v = os.environ.get(n, "")
        if v:
            return v
    try:
        import streamlit as st
        for n in nombres:
            v = st.secrets.get(n, "")
            if v:
                return v
    except Exception:
        pass
    return ""


GROQ_API_KEY = _leer_clave("GROQ_API_KEY")
GEMINI_API_KEY = _leer_clave("GEMINI_API_KEY", "GOOGLE_API_KEY")
OPENROUTER_API_KEY = _leer_clave("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


MODELOS_OPENROUTER = {
    "🆓 Nemotron 120B (OpenRouter gratis)": "nvidia/nemotron-3-super-120b-a12b:free",
    "🆓 GPT-OSS 120B (OpenRouter gratis)": "openai/gpt-oss-120b:free",
    "🆓 Qwen3 Coder (OpenRouter gratis)": "qwen/qwen3-coder:free",
    "🆓 Llama 3.3 70B (OpenRouter gratis)": "meta-llama/llama-3.3-70b-instruct:free",
    "🆓 Gemma 3 27B (OpenRouter gratis)": "google/gemma-3-27b-it:free",
    "🆓 GLM 4.5 Air (OpenRouter gratis)": "z-ai/glm-4.5-air:free",
}

MODELOS_GROQ = {
    "🐪 Llama 3.3 70B (Groq)": "llama-3.3-70b-versatile",
    "⚡ Llama 3.1 8B (Groq rápido)": "llama-3.1-8b-instant",
    "🦙 Llama 4 Maverick 17B (Groq)": "meta-llama/llama-4-maverick-17b-128e-instruct",
    "🚀 Llama 4 Scout 17B (Groq)": "meta-llama/llama-4-scout-17b-16e-instruct",
    "🧠 Qwen QwQ 32B (Groq)": "qwen-qwq-32b",
}

MODELOS_GEMINI = {
    "💎 Gemini 2.0 Flash (Google)": "gemini-2.0-flash",
    "💎 Gemini 2.5 Flash (Google)": "gemini-2.5-flash",
    "💎 Gemini 1.5 Pro (Google)": "gemini-1.5-pro",
}

MODELOS = {**MODELOS_OPENROUTER}

MODELO_DEFAULT = "🆓 Nemotron 120B (OpenRouter gratis)"
MODELO_RESUMEN_OPENROUTER = "nvidia/nemotron-3-super-120b-a12b:free"
OPENROUTER_FALLBACKS = [
    "nvidia/nemotron-3-super-120b-a12b:free",
    "openai/gpt-oss-120b:free",
    "z-ai/glm-4.5-air:free",
]
MODELO_WHISPER = "whisper-large-v3"


def _es_modelo_gemini(modelo_id: str) -> bool:
    return modelo_id.startswith("gemini")


def _es_modelo_openrouter(modelo_id: str) -> bool:
    return ":free" in modelo_id or modelo_id in set(MODELOS_OPENROUTER.values())


def _es_error_region(err: Exception) -> bool:
    """Detecta error 403/region/permiso típico del bloqueo a Venezuela."""
    msg = str(err).lower()
    return any(k in msg for k in [
        "403", "forbidden", "region", "country", "unsupported_country", "permission"
    ])


# ---------- Groq ----------

def _client() -> Groq:
    if not GROQ_API_KEY:
        raise RuntimeError("Groq no disponible")
    return Groq(api_key=GROQ_API_KEY)


# ---------- OpenRouter ----------

def _openrouter_disponible() -> bool:
    return bool(OPENROUTER_API_KEY)


def _openrouter_client():
    if not OPENROUTER_API_KEY:
        raise RuntimeError("Falta OPENROUTER_API_KEY. Obténla gratis en https://openrouter.ai/keys")
    from openai import OpenAI
    return OpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url=OPENROUTER_BASE_URL,
        default_headers={
            "HTTP-Referer": "https://replit.com",
            "X-Title": "Asistentes Profesionales",
        },
    )


def _openrouter_stream(modelo_id: str, mensajes: List[dict], temperature: float) -> Iterator[str]:
    intentos = [modelo_id] + [m for m in OPENROUTER_FALLBACKS if m != modelo_id]
    for modelo in intentos:
        try:
            client = _openrouter_client()
            # Primero hace la llamada completa (no stream) para verificar que responde
            res = client.chat.completions.create(
                model=modelo,
                messages=mensajes,
                temperature=temperature,
                stream=False,  # sin stream para poder capturar el error
            )
            texto = res.choices[0].message.content or ""
            yield texto
            return
        except Exception:
            continue
    yield "⚠️ Todos los modelos están saturados en este momento. Intenta de nuevo en unos segundos."

def _openrouter_completo(modelo_id: str, mensajes: List[dict], temperature: float) -> str:
    intentos = [modelo_id] + [m for m in OPENROUTER_FALLBACKS if m != modelo_id]
    ultimo_error = None
    for modelo in intentos:
        try:
            client = _openrouter_client()
            res = client.chat.completions.create(
                model=modelo,
                messages=mensajes,
                temperature=temperature,
            )
            return res.choices[0].message.content or ""
        except Exception as e:
            ultimo_error = e
            continue
    raise ultimo_error


# ---------- Gemini ----------

def _gemini_disponible() -> bool:
    return bool(GEMINI_API_KEY) and genai is not None


def _gemini_config():
    if not _gemini_disponible():
        raise RuntimeError("Gemini no disponible. Configura GEMINI_API_KEY.")
    genai.configure(api_key=GEMINI_API_KEY)


def _convertir_a_gemini(mensajes: List[dict]):
    """Convierte mensajes OpenAI-style a formato Gemini."""
    system_parts = []
    historial = []
    for m in mensajes:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "system":
            system_parts.append(content)
        elif role == "assistant":
            historial.append({"role": "model", "parts": [content]})
        else:
            historial.append({"role": "user", "parts": [content]})
    system_instruction = "\n\n".join(system_parts) if system_parts else None
    return system_instruction, historial


def _gemini_stream(modelo_id: str, mensajes: List[dict], temperature: float) -> Iterator[str]:
    _gemini_config()
    system_instruction, historial = _convertir_a_gemini(mensajes)
    model = genai.GenerativeModel(
        model_name=modelo_id,
        system_instruction=system_instruction,
        generation_config={"temperature": temperature},
    )
    if historial and historial[-1]["role"] == "user":
        ultimo = historial[-1]["parts"][0]
        chat = model.start_chat(history=historial[:-1])
        resp = chat.send_message(ultimo, stream=True)
    else:
        resp = model.generate_content(historial, stream=True)
    for chunk in resp:
        texto = getattr(chunk, "text", None)
        if texto:
            yield texto


def _gemini_completo(modelo_id: str, mensajes: List[dict], temperature: float) -> str:
    _gemini_config()
    system_instruction, historial = _convertir_a_gemini(mensajes)
    model = genai.GenerativeModel(
        model_name=modelo_id,
        system_instruction=system_instruction,
        generation_config={"temperature": temperature},
    )
    resp = model.generate_content(historial)
    return getattr(resp, "text", "") or ""


# ---------- API pública ----------

def chat_stream(modelo_id: str, mensajes: List[dict], temperature: float = 0.7) -> Iterator[str]:
    """Stream de tokens. Auto-fallback a OpenRouter si Groq da 403/region."""
    if _es_modelo_gemini(modelo_id):
        yield from _gemini_stream(modelo_id, mensajes, temperature)
        return
    if _es_modelo_openrouter(modelo_id):
        yield from _openrouter_stream(modelo_id, mensajes, temperature)
        return
    try:
        client = _client()
        stream = client.chat.completions.create(
            model=modelo_id,
            messages=mensajes,
            temperature=temperature,
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta
    except Exception as e:
        if _es_error_region(e) and _openrouter_disponible():
            yield "\n\n⚠️ _Groq bloqueado en tu región, usando OpenRouter…_\n\n"
            yield from _openrouter_stream(MODELO_RESUMEN_OPENROUTER, mensajes, temperature)
        elif _es_error_region(e) and _gemini_disponible():
            yield "\n\n⚠️ _Groq bloqueado, usando Gemini…_\n\n"
            yield from _gemini_stream("gemini-2.0-flash", mensajes, temperature)
        else:
            raise


def chat_completo(modelo_id: str, mensajes: List[dict], temperature: float = 0.5) -> str:
    """Llamada no-stream. Auto-fallback a OpenRouter si Groq da 403/region."""
    if _es_modelo_gemini(modelo_id):
        return _gemini_completo(modelo_id, mensajes, temperature)
    if _es_modelo_openrouter(modelo_id):
        return _openrouter_completo(modelo_id, mensajes, temperature)
    try:
        client = _client()
        res = client.chat.completions.create(
            model=modelo_id,
            messages=mensajes,
            temperature=temperature,
        )
        return res.choices[0].message.content or ""
    except Exception as e:
        if _es_error_region(e) and _openrouter_disponible():
            return _openrouter_completo(MODELO_RESUMEN_OPENROUTER, mensajes, temperature)
        if _es_error_region(e) and _gemini_disponible():
            return _gemini_completo("gemini-2.0-flash", mensajes, temperature)
        raise


def transcribir_audio(audio_bytes: bytes, nombre: str = "audio.wav") -> str:
    """Transcribe audio usando Whisper-large-v3 de Groq (gratis)."""
    client = _client()
    res = client.audio.transcriptions.create(
        file=(nombre, audio_bytes),
        model=MODELO_WHISPER,
        response_format="text",
        language="es",
    )
    return res if isinstance(res, str) else getattr(res, "text", "")


def generar_resumen(agente_nombre: str, mensajes: List[dict]) -> str:
    """Genera un resumen estructurado de la conversación."""
    historial = "\n".join(
        f"{'USUARIO' if m['role'] == 'user' else 'ASISTENTE'}: {m['content']}"
        for m in mensajes
    )
    prompt_resumen = f"""Eres un asistente experto en sintetizar conversaciones técnicas.
Resume la siguiente conversación que tuvo lugar con el agente "{agente_nombre}".

Estructura el resumen así (usa Markdown):

## Tema central
Una sola frase clara.

## Contexto y necesidad del usuario
2-4 líneas con el contexto que dio el usuario.

## Aportes y entregables del agente
Lista de los puntos, recomendaciones, plantillas o documentos clave que entregó el agente.

## Decisiones y acuerdos
Qué quedó decidido o acordado, si algo.

## Siguientes pasos sugeridos
Lista corta de acciones recomendadas.

CONVERSACIÓN:
{historial}

Resumen:"""
    return chat_completo(
        MODELO_RESUMEN_OPENROUTER,
        [{"role": "user", "content": prompt_resumen}],
        temperature=0.3,
    )


def generar_resumen_reunion(transcripcion: str, contexto: str = "") -> str:
    """Genera un resumen estructurado a partir de la transcripción de una reunión."""
    bloque_ctx = f"\nCONTEXTO ADICIONAL:\n{contexto}\n" if contexto.strip() else ""
    prompt = f"""Eres un asistente experto en redactar minutas de reuniones profesionales.
A partir de la siguiente transcripción (puede tener errores de reconocimiento de voz),
genera una minuta estructurada en Markdown.{bloque_ctx}

ESTRUCTURA OBLIGATORIA:

## Resumen ejecutivo
Un párrafo de 3-5 líneas con lo más importante.

## Asistentes y roles
Lista de personas mencionadas (si se identifican). Si no, escribe "No se identificaron explícitamente".

## Temas tratados
Lista con los puntos principales discutidos.

## Decisiones tomadas
Lista clara de cada decisión. Si no hubo, escribe "No se tomaron decisiones formales".

## Acuerdos y próximos pasos
Lista en formato: **Acción** — Responsable (si se mencionó) — Plazo (si se mencionó).

## Pendientes y temas abiertos
Asuntos que quedaron sin cerrar.

## Riesgos u observaciones
Cualquier alerta, riesgo o nota relevante mencionada.

Sé fiel a la transcripción, no inventes datos. Si algo no se mencionó, dilo.

TRANSCRIPCIÓN:
{transcripcion}

MINUTA:"""
    return chat_completo(
        MODELO_RESUMEN_OPENROUTER,
        [{"role": "user", "content": prompt}],
        temperature=0.3,
    )
