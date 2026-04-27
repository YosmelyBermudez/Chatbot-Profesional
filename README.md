# Workspace

## Overview

Aplicación principal: **Asistentes Profesionales** — chatbot Streamlit con 4 agentes
especializados para profesionales (Procedimientos, Cargos, KPIs, LOPCYMAT) usando
Groq (LLMs Llama/Qwen + Whisper para voz) y RAG ligero con TF-IDF.

## Estructura

- `streamlit_app/` — aplicación Streamlit principal
  - `app.py` — UI principal y enrutamiento de pestañas
  - `agents.py` — definición de los 4 agentes y sus system prompts
  - `db.py` — capa SQLite (usuarios, conversaciones, resúmenes, documentos, memoria)
  - `rag.py` — extracción de PDF/Word/TXT, chunking y recuperación TF-IDF
  - `llm.py` — cliente Groq (chat, streaming, transcripción Whisper, resúmenes)
  - `data/agentes.db` — base de datos SQLite (creada en runtime)
  - `.streamlit/config.toml` — puerto 5000, sin telemetría
- `artifacts/` — artefactos pre-existentes del workspace pnpm (no relacionados con la app)
- `lib/` — librerías compartidas pre-existentes

## Funcionalidades clave

- **4 agentes especializados** con system prompts ricos (ISO 9001, BSC, LOPCYMAT, etc.)
- **Multi-usuario** (login simple por email + perfil de profesión y área)
- **RAG por agente** — los documentos subidos quedan persistidos y se inyectan en cada
  consulta como contexto para que el agente "recuerde" sin que el usuario repita info
- **Memoria persistente del usuario** — bloque libre que se inyecta en todos los agentes
- **Botón Finalizar** → genera resumen estructurado, lo guarda en biblioteca, marca
  conversación como finalizada
- **Integración de conversaciones/resúmenes** → arma contexto compuesto e inicia
  nueva conversación con el contexto cargado
- **Entrada por voz** vía Web/Streamlit → transcripción con Groq Whisper-large-v3

## Stack

- Python 3.11
- Streamlit 1.56
- Groq SDK (LLMs Llama/Qwen y Whisper)
- google-generativeai (Gemini 2.0/2.5 Flash, 1.5 Pro como alternativa cuando Groq esté bloqueado)
- LangChain core (no se usa la cadena, solo conceptos)
- scikit-learn (TF-IDF vectorizer + cosine similarity)
- pypdf, python-docx (extracción de texto)
- streamlit-mic-recorder (captura de audio en navegador)
- SQLite (persistencia local)

## Comandos

- App: `streamlit run streamlit_app/app.py --server.port 5000`
- Workflow configurado: **Streamlit App** (auto-start)

## Variables de entorno requeridas

- `GROQ_API_KEY` — clave de Groq (se obtiene en https://console.groq.com/keys)
- `GEMINI_API_KEY` — clave de Google Gemini (https://aistudio.google.com/app/apikey) — usada como alternativa automática cuando Groq devuelve 403 (bloqueo regional Venezuela)
