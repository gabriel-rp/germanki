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

# Run Streamlit
WORKDIR /app/src
EXPOSE 8501
HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health
ENTRYPOINT ["uv", "run", "streamlit", "run", "--server.port=8501", "--server.address=0.0.0.0", "--server.enableStaticServing=true", "germanki/app.py"]
