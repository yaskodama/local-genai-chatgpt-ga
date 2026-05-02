# ABCL/c+ — top-level Makefile
#
# Two implementations of the same language live under src/:
#   * OCaml interpreter:  src/*.ml, src/lexer.mll, src/parser.mly  (dune build)
#   * Browser JS engine:  src/browser-abcl/src/{ast,runtime,interpreter}.js
#                         plus a jison-generated parser under src/browser-abcl/src/parser/
#
# Sample .abcl programs live under abclc/ and are meant to be executed by the
# OCaml REPL (_build/default/src/repl_thread.exe). The JS build keeps its own
# demo .abcl sources inlined in its HTML pages.

OCAML_REPL   = _build/default/src/repl_thread.exe
BROWSER_DIR  = src/browser-abcl
JS_GRAMMAR   = $(BROWSER_DIR)/src/parser/grammar.jison
JS_PARSER    = $(BROWSER_DIR)/src/parser/parser.js
SERVE_PORT  ?= 3000
PY          ?= /usr/bin/python3
PYDIR       := src/python-abcl
DOCKER      ?= docker
IMAGE       ?= abcl-cp:latest

.PHONY: all ocaml js clean cleanall samples \
        run-philosophers run-rotate4 run-hello \
        serve-js help \
        smoke smoke-dynamic repl dist-smoke \
        docker-build docker-run

all: ocaml js

help:
	@echo 'ABCL/c+ build targets:'
	@echo '  make / make all        Build both implementations (OCaml + JS)'
	@echo '  make ocaml             Build the OCaml interpreter via dune'
	@echo '  make js                Regenerate the JS parser from jison grammar'
	@echo '  make clean             Remove dune build artifacts'
	@echo '  make cleanall          clean + also remove generated JS parser'
	@echo '  make samples           List sample programs under abclc/'
	@echo '  make run-hello         Run abclc/Hello.abcl through the OCaml REPL'
	@echo '  make run-philosophers  Run the 5-philosopher dinner sample'
	@echo '  make run-rotate4       Run the Rotate4Lines sample'
	@echo '  make serve-js          Serve the browser build at http://localhost:$(SERVE_PORT)'
	@echo ''
	@echo 'Python runtime + smoke:'
	@echo '  make smoke             Run every smoke test (OCaml + JS + Python + 3-node mock)'
	@echo '  make smoke-dynamic     Smoke + headless Chrome JS run'
	@echo '  make repl              Launch the Python REPL'
	@echo '  make dist-smoke        Run the 3-node distributed smoke (mock provider)'
	@echo ''
	@echo 'Docker:'
	@echo '  make docker-build      Build the Docker image ($(IMAGE))'
	@echo '  make docker-run        Launch the default container on port 8080'

# ---------------- OCaml implementation ----------------

ocaml: $(OCAML_REPL)

$(OCAML_REPL): $(wildcard src/*.ml) src/lexer.mll src/parser.mly src/dune dune-project
	dune build src

# ---------------- Browser JS implementation ----------------

js: $(JS_PARSER)

$(JS_PARSER): $(JS_GRAMMAR) $(BROWSER_DIR)/package.json
	cd $(BROWSER_DIR) && npx jison src/parser/grammar.jison -o src/parser/parser.js

# ---------------- Clean ----------------

clean:
	dune clean

cleanall: clean
	rm -f $(JS_PARSER)

# ---------------- Samples ----------------

samples:
	@ls -1 abclc/*.abcl

run-hello: ocaml
	@printf 'load abclc/Hello.abcl\ncompile\nquit\n' | $(OCAML_REPL)

run-philosophers: ocaml
	./run_philosophers.sh

run-rotate4: ocaml
	./run_rotate4lines.sh

# ---------------- Browser serve ----------------

serve-js: js
	@echo ''
	@echo '  Open one of:'
	@echo '    http://localhost:$(SERVE_PORT)/rotate4lines.html'
	@echo '    http://localhost:$(SERVE_PORT)/philosophers.html'
	@echo '    http://localhost:$(SERVE_PORT)/drone_simulator.html'
	@echo ''
	cd $(BROWSER_DIR) && npx serve -l $(SERVE_PORT) .

# ---------------- Python runtime + smoke ----------------

smoke:
	./run_all_smoke_tests.sh

smoke-dynamic:
	./run_all_smoke_tests.sh --dynamic

repl:
	$(PY) $(PYDIR)/abcl_main.py

dist-smoke:
	$(PY) $(PYDIR)/_smoke_dist.py

# ---------------- Docker ----------------

docker-build:
	$(DOCKER) build -t $(IMAGE) .

docker-run:
	$(DOCKER) run --rm -it -p 8080:8080 $(IMAGE)
