
ARG PYTHON_VERSION="3.11"
FROM python:${PYTHON_VERSION}-slim-buster

# OS dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        git \
    && rm -rf /var/lib/apt/lists/*

# Install poetry
RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH="${PATH}:/root/.local/bin"

WORKDIR /app

# Copies package
COPY poetry.lock /app
COPY pyproject.toml /app
COPY README.md README.md
COPY src/ src/

# Configure poetry to use base Python and installs package
RUN poetry config virtualenvs.create false \
    && poetry env use system \
    && poetry env info \
    && poetry install

# Run Streamlit
WORKDIR /app/src
EXPOSE 8501
HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health
ENTRYPOINT ["streamlit", "run", "germanki/app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.enableStaticServing=true"]
