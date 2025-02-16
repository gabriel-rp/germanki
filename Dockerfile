
ARG PYTHON_VERSION="3.11.11"
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

# Configure poetry to use base Python
RUN poetry init --python ${PYTHON_VERSION}
RUN poetry config virtualenvs.create false \
    && poetry env use system \
    && poetry env info


WORKDIR /app
# Cache dependencies
COPY poetry.lock /app
COPY pyproject.toml /app
RUN poetry install --only main --no-root

# Install package
COPY src/ src/
# needed for package install
COPY README.md README.md
RUN poetry install --only main
