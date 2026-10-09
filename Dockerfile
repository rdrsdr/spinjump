# Simulador 3D de corda e chaminé — física e renderização no servidor (CPU/OSMesa por padrão).
FROM python:3.11-slim-bookworm

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONWARNINGS=ignore::DeprecationWarning \
    MUJOCO_GL=osmesa \
    PYOPENGL_PLATFORM=osmesa \
    LP_NUM_THREADS=2 \
    MPLBACKEND=Agg \
    MPLCONFIGDIR=/tmp/matplotlib \
    NUMBA_CACHE_DIR=/tmp/numba_cache \
    SPINJUMP_OUT=/app/out \
    PORT=8000

# OSMesa (padrão, CPU, sem GPU) + bibliotecas EGL/GL (opcionais, GPU no servidor)
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libosmesa6 libgl1 libegl1 libgles2 libglvnd0 libglx0 libopengl0 fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

RUN useradd --create-home --uid 1000 sim
COPY --chown=sim:sim . /app
RUN mkdir -p /app/out /tmp/numba_cache && chown -R sim:sim /app/out /tmp/numba_cache && chmod 1777 /tmp/numba_cache
USER sim
# pré-compila o kernel da corda encostada (numba); o cache vale para qualquer UID do contêiner
RUN python -c "from spinjump._chain_kernel import warmup; warmup()" && chmod -R a+rwX /tmp/numba_cache

VOLUME ["/app/out"]
EXPOSE 8000

# Entrada única: a CLI. Sem argumentos, sobe a interface web.
ENTRYPOINT ["python", "-m", "spinjump"]
CMD ["serve", "--host", "0.0.0.0"]
