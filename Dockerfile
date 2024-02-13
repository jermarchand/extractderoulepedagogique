############ Stage ############
FROM python:3.11-buster as python-poetry-base

# https://python-poetry.org/docs#ci-recommendations
ENV POETRY_VERSION=1.3.2
ENV POETRY_HOME=/opt/poetry
ENV POETRY_VIRTUALENVS_IN_PROJECT=true
ENV POETRY_NO_INTERACTION=1
ENV PATH="$POETRY_HOME/bin:$PATH"


###############################################################################
# POETRY BUILDER IMAGE - Installs Poetry and dependencies
###############################################################################
FROM python-poetry-base AS python-poetry-builder
RUN apt-get update \
    && apt-get install --no-install-recommends --assume-yes curl
# Install Poetry via the official installer: https://python-poetry.org/docs/master/#installing-with-the-official-installer
# This script respects $POETRY_VERSION & $POETRY_HOME
RUN curl -sSL https://install.python-poetry.org | python3 -


###############################################################################
# POETRY RUNTIME IMAGE - Copies the poetry installation into a smaller image
###############################################################################
FROM python-poetry-base AS python-poetry
COPY --from=python-poetry-builder $POETRY_HOME $POETRY_HOME

# Copy Dependencies
COPY poetry.lock ./
COPY pyproject.toml ./

# [OPTIONAL] Validate the project is properly configured
RUN poetry check

# Install Dependencies
RUN poetry install --no-interaction --no-cache --without dev
RUN poetry env info

COPY . .

ENTRYPOINT ["poetry","run", "python", "/extractderoulepedagogique/main.py", "/github/workspace"]
