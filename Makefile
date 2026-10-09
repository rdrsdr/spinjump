# Atalhos (tudo roda dentro do container).
COMPOSE ?= docker compose
RUN = $(COMPOSE) run --rm cli
PY = $(COMPOSE) run --rm --entrypoint python cli

.PHONY: build up down selftest test test-fast run convergence sweep ui-flow ui-layout clean hf-space

build:            ## constrói a imagem
	$(COMPOSE) build ui

up:               ## sobe a interface web (http://localhost:8000)
	$(COMPOSE) up --build -d ui

down:
	$(COMPOSE) down

selftest:
	$(RUN) selftest

test:             ## todos os testes físicos e de interface (alguns minutos)
	$(PY) -m pytest -q

test-fast:        ## testes rápidos (sem cenário completo/convergência/UI)
	$(PY) -m pytest -q tests/test_config.py tests/test_isolated_physics.py

run:              ## cenário padrão completo com estudo de convergência
	$(RUN) run --convergence

sweep:            ## varredura curta (azimute × velocidade)
	$(RUN) sweep --name azimute_velocidade --param launch.azimuth_deg=-60,0,90 --param launch.speed_ms=2,6

ui-flow:          ## fluxo da interface contra o serviço "ui" em execução
	docker run --rm --network container:spinjump-ui --entrypoint python spinjump:1.0.0 tools/ui_flow.py http://localhost:8000

ui-layout:        ## capturas e verificação de sobreposição com Chromium (baixa imagem do Playwright)
	tools/ui_layout.sh spinjump-ui 8000

clean:
	rm -rf out/*

hf-space:         ## monta o repositório do Hugging Face Space em ../spinjump-space (ou SPACE_DIR=...)
	deploy/huggingface/make_space.sh $${SPACE_DIR:-../spinjump-space}
