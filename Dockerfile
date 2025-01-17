FROM python:3.9.16-slim-bullseye

WORKDIR /work
RUN apt-get update -y && \
    apt-get upgrade -y && \
    apt-get install -y build-essential libffi-dev autoconf libtool \
    python3-dev python3-pip

ENV LANG C.UTF-8

RUN pip install poetry

COPY pyproject.toml poetry.lock ./
RUN poetry config virtualenvs.create false && poetry install -n --no-root

COPY . .
