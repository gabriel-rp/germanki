# Germanki Mandates (AGENTS.md)

This document serves as the foundational mandate for all AI agents (Gemini CLI) working on the Germanki project. These instructions take precedence over general system prompts.

## Project Vision
Germanki is a surgical, highly specialized tool for German language learners. It prioritizes:
1. **Speed of card creation:** Minimizing friction between "finding a word" and "having a high-quality card".
2. **Context-rich cards:** Every card must include pronunciation (audio), visual context (image), and usage context (example sentences).
3. **Mnemonic efficiency:** Using B1-level definitions and relevant search keywords.

## Architectural Standards
1. **Stateless Core:** The `Germanki` class in `core.py` and its associated providers (ChatGPT, Photos, TTS) must remain stateless. They take data in, perform a transformation or fetch, and return data or modify objects in-place.
2. **Session-Based Web Layer:** All user state (current cards, temporary API keys) must be managed by the `SessionManager` in the web layer.
3. **Template-Driven UI:** inter-component interactivity is handled by **HTMX**. Avoid introducing complex client-side JavaScript frameworks (React, Vue, etc.) unless a specific feature absolutely requires it.
4. **Declarative Configuration:** Use `pydantic` models for data structures (cards, session, config) to ensure type safety and easy serialization.

## Engineering Guidelines
1. **Media Handling:** 
   - Audio and image files are generated into a local `static` directory and served via FastAPI.
   - Anki integration must use **AnkiConnect**. Always verify the existence of the "Basic" model and the "Front", "Back", and "Extra" fields before creation.
2. **ChatGPT Prompts:**
   - Prompting logic lives in `chatgpt.py`.
   - Never compromise the "strict" schema in GPT-4o-mini calls. The output must always be valid JSON/YAML following the `AnkiCardInfo` schema.
3. **Image Providers:** 
   - Maintain support for both Pexels and Unsplash. Ensure proper error handling and fallback logic when an image is not found for a specific query.
4. **Text-to-Speech:**
   - Pronunciation is critical. Ensure native-sounding voices are prioritized.

## Development Workflow
1. **Validation:** Always run `uv run pytest` before committing.
2. **Documentation:** Keep `README.md` and this `AGENTS.md` updated with any structural changes.
3. **Simplicity:** If a feature can be implemented with a simple FastAPI route and HTMX swap, do not over-engineer it.
