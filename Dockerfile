
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
# not optimized for caching
COPY poetry.lock /app
COPY pyproject.toml /app
COPY README.md README.md
COPY src/ src/

# Configure poetry to use base Python
RUN poetry config virtualenvs.create false \
    && poetry env use system \
    && poetry env info

# Install package
RUN poetry install --only main

ARG STREAMLIT_SERVER_PORT=8501
EXPOSE ${STREAMLIT_SERVER_PORT}

CMD ["poetry", "run", "germanki"]
