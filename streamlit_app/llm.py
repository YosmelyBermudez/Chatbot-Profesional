"""
Cliente Groq para LLM y transcripción de voz (Whisper).
"""

import os
from typing import List, Iterator
from groq import Groq

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

MODELOS_GROQ = {
    "🐪 Llama 3.3 70B (potente)": "llama-3.3-70b-versatile",
    "⚡ Llama 3.1 8B (rápido)": "llama-3.1-8b-instant",
    "🦙 Llama 4 Maverick 17B": "meta-llama/llama-4-maverick-17b-128e-instruct",
    "🚀 Llama 4 Scout 17B (contexto 131K)": "meta-llama/llama-4-scout-17b-16e-instruct",
    "🧠 Qwen QwQ 32B (razonamiento)": "qwen-qwq-32b",
}

MODELO_DEFAULT = "🐪 Llama 3.3 70B (potente)"
MODELO_RESUMEN = "llama-3.3-70b-versatile"
MODELO_WHISPER = "whisper-large-v3"


def _client() -> Groq:
    if not GROQ_API_KEY:
        raise RuntimeError("Falta GROQ_API_KEY en las variables de entorno")
    return Groq(api_key=GROQ_API_KEY)


def chat_stream(modelo_id: str, mensajes: List[dict], temperature: float = 0.7) -> Iterator[str]:
    """Stream de tokens del modelo. mensajes = [{role, content}, ...]"""
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


def chat_completo(modelo_id: str, mensajes: List[dict], temperature: float = 0.5) -> str:
    """Llamada no-stream, devuelve texto completo."""
    client = _client()
    res = client.chat.completions.create(
        model=modelo_id,
        messages=mensajes,
        temperature=temperature,
    )
    return res.choices[0].message.content or ""


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
        MODELO_RESUMEN,
        [{"role": "user", "content": prompt_resumen}],
        temperature=0.3,
    )
