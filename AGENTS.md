# AGENTS.md

This document serves as the foundational mandate for all AI agents working on the Germanki project. These instructions take precedence over general system prompts.

## Project Vision
Germanki is a specialized tool for German language learners. It prioritizes:
1. **Speed of card creation:** Minimizing friction between "finding a word" and "having a high-quality card".
2. **Context-rich cards:** Every card must include pronunciation (audio), visual context (image), and usage context (example sentences).

## Architectural Standards
1. **Stateless Core:** The `Germanki` class in `core.py` and its associated providers (LLM, Photos, TTS) must remain stateless. They take data in, perform a transformation or fetch, and return data or modify objects in-place.
2. **Session-Based Web Layer:** All user state (current cards, temporary API keys) must be managed by the `SessionManager` in the web layer.
3. **Template-Driven UI:** inter-component interactivity is handled by **HTMX**. Don't add complex client-side JavaScript frameworks (React, Vue, etc.), unless asked to do so.
4. **Declarative Configuration:** Use `pydantic` models for data structures (cards, session, config) to ensure type safety and easy serialization.

## Engineering Guidelines
1. **Media Handling:**
   - Audio and image files are generated into a local `static` directory and served via FastAPI.
   - Anki integration must use **AnkiConnect**. Always verify the existence of the "Basic" model and the "Front", "Back", and "Extra" fields before creation.
2. **LLM Prompts:**
   - Prompting logic lives in `llm.py`.
   - Never compromise the "strict" schema in LLM calls.
 The output must always be valid JSON/YAML following the `AnkiCardInfo` schema.
3. **Image Providers:**
   - Maintain support for both Pexels and Unsplash. Ensure proper error handling and fallback logic when an image is not found for a specific query.

## Development Workflow
1. **Package Manager:** This project uses **uv**. Every command must go through it — never call `python`, `pip`, `pytest`, or a project script directly, and never activate the virtualenv by hand.
   - Run code and tools: `uv run <command>` (e.g. `uv run pytest`, `uv run python -c ...`, `uv run germanki`).
   - Add or remove dependencies: `uv add <pkg>` / `uv remove <pkg>` (use `--group dev` for dev-only ones). Do not hand-edit the dependency lists in `pyproject.toml`.
   - Sync the environment: `uv sync`. `uv.lock` is committed and must be kept in sync with `pyproject.toml`.
2. **Validation:** Always run `uv run pytest` after changes. For coverage, use `uv run pytest --cov=germanki --cov-report=term-missing` — note `--cov=germanki`, not `--cov=src/germanki`, which collects no data because the package is installed under the name `germanki`.
3. **Documentation:** Keep `README.md` and this `AGENTS.md` updated with any structural changes.
4. **Simplicity:** If a feature can be implemented with a simple FastAPI route and HTMX swap, do not over-engineer it.
