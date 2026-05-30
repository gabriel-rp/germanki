FROM python:3.12-slim-trixie

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Disable development dependencies
ENV UV_NO_DEV=1

WORKDIR /app

# Install dependencies
COPY pyproject.toml .
COPY uv.lock .
RUN uv sync --locked --no-install-project

# Activate project
ENV PATH="/app/.venv/bin:$PATH"

# Copies project
COPY README.md .
COPY src/ src/

# Install project
RUN uv sync --locked --no-install-project

# Run FastAPI
WORKDIR /app
EXPOSE 8000
HEALTHCHECK CMD curl --fail http://localhost:8000/ || exit 1
ENTRYPOINT ["uv", "run", "uvicorn", "germanki.web.app:app", "--host", "0.0.0.0", "--port", "8000"]
