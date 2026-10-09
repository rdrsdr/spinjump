#!/usr/bin/env bash
# Monta o repositório de um Hugging Face Space (SDK Docker) a partir deste projeto.
# Uso: deploy/huggingface/make_space.sh <pasta-destino>
#   A pasta pode ser um clone vazio de https://huggingface.co/spaces/<usuario>/<space>.
#   Arquivos existentes do projeto na pasta são substituídos; o diretório .git é preservado.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HERE="$ROOT/deploy/huggingface"
DEST="${1:?informe a pasta de destino}"
mkdir -p "$DEST"
DEST="$(cd "$DEST" && pwd)"
[ "$DEST" = "$ROOT" ] && { echo "destino não pode ser o próprio projeto" >&2; exit 1; }

# código e configuração (sem saídas, caches nem resultados de protótipos)
for d in spinjump configs tests tools prototypes; do
  rm -rf "${DEST:?}/$d"
  tar -C "$ROOT" --exclude='__pycache__' --exclude='*.pyc' --exclude='prototypes/results' -cf - "$d" | tar -C "$DEST" -xf -
done
cp "$ROOT/requirements.txt" "$ROOT/pytest.ini" "$ROOT/NOTES.md" "$ROOT/.dockerignore" "$DEST/"
sed "s#](../NOTES.md)#](NOTES.md)#g" "$ROOT/docs/DOCUMENTACAO.md" > "$DEST/DOCUMENTACAO.md"
cp "$HERE/README.md" "$DEST/README.md"

# Dockerfile do projeto + ajustes do Space: porta 7860 (app_port), 2 vCPUs (1 thread de render),
# no máximo 2 simulações simultâneas de até 180 s simulados, relatórios temporários limitados às
# 30 execuções mais recentes, sem VOLUME (disco efêmero)
grep -v '^VOLUME' "$ROOT/Dockerfile" > "$DEST/Dockerfile"
cat >> "$DEST/Dockerfile" <<'DOCKER'

# --- Hugging Face Spaces ---
ENV PORT=7860 \
    LP_NUM_THREADS=1 \
    SPINJUMP_KEEP_RUNS=30 \
    SPINJUMP_MAX_SESSIONS=2 \
    SPINJUMP_MAX_SIM_TIME_S=180
EXPOSE 7860
DOCKER

if [ ! -f "$DEST/.gitattributes" ]; then
  printf '*.png filter=lfs diff=lfs merge=lfs -text\n' > "$DEST/.gitattributes"
fi
echo "Space montado em $DEST"
echo "Próximos passos: cd \"$DEST\" && git add -A && git commit -m 'SpinJump' && git push"
