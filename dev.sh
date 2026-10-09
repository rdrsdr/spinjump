#!/usr/bin/env bash
# Executa um comando dentro da imagem de desenvolvimento, montando o repositório.
exec docker run --rm -i --entrypoint "" -u "$(id -u):$(id -g)" -v "$PWD":/app -v "$PWD/out":/app/out -w /app -e PYTHONPATH=/app -e FAST -e LP_NUM_THREADS spinrapel-sim:dev "$@"
