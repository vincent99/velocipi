# liveatc / intercom-stt — build & dev tasks.
# Run `make` or `make help` to list targets.

BIN        := intercom-stt
PKG        := ./cmd/intercom-stt
DIST       := dist

# Pure Go (gpiocdev talks to /dev/gpiochip via ioctl, no cgo), so we build
# static binaries and can cross-compile freely.
export CGO_ENABLED := 0

# --- deploy / model / venv knobs (override on the command line) ---------------
PI         ?= pi@raspberrypi.local   # ssh target for `make deploy`
PI_DEST    ?= ~/liveatc              # remote dir for `make deploy`
MODEL      ?= base.en               # whisper model for `make model` (tiny.en, base.en, small.en, small.en-q5_1, ...)
MODELS_DIR ?= data/liveatc/models   # where `make model` writes (matches storage.liveatc-relative `whisper.model`)
VENV       ?= .venv                 # python venv for the Silero sidecar

GO         ?= go
# Prepend a Node toolchain to PATH for the UI build (macOS dev box); override or
# set to an existing dir on the Pi.
NODE_BIN   ?= /opt/homebrew/opt/node@24/bin
YARN        = PATH="$(NODE_BIN):$$PATH" yarn

.DEFAULT_GOAL := help

## ---- build -----------------------------------------------------------------

.PHONY: all
all: build ## Build the native binary

.PHONY: build
build: ## Build intercom-stt for the host platform (./intercom-stt)
	$(GO) build -o $(BIN) $(PKG)

.PHONY: build-pi
build-pi: ## Cross-compile for a Raspberry Pi 5 (linux/arm64 -> dist/)
	GOOS=linux GOARCH=arm64 $(GO) build -o $(DIST)/$(BIN)-linux-arm64 $(PKG)

.PHONY: build-linux-amd64
build-linux-amd64: ## Cross-compile for linux/amd64 (-> dist/)
	GOOS=linux GOARCH=amd64 $(GO) build -o $(DIST)/$(BIN)-linux-amd64 $(PKG)

.PHONY: build-all
build-all: build build-pi build-linux-amd64 ## Build host + all cross targets

## ---- quality ---------------------------------------------------------------

.PHONY: test
test: ## Run tests
	$(GO) test ./...

.PHONY: vet
vet: ## go vet
	$(GO) vet ./...

.PHONY: fmt
fmt: ## Format all Go sources in place
	gofmt -w .

.PHONY: fmt-check
fmt-check: ## Fail if any Go source is not gofmt-clean
	@out="$$(gofmt -l .)"; if [ -n "$$out" ]; then echo "not gofmt-clean:"; echo "$$out"; exit 1; fi

.PHONY: tidy
tidy: ## go mod tidy
	$(GO) mod tidy

.PHONY: check
check: fmt-check vet test build-pi ## Everything CI should run (fmt, vet, test, cross-build for Pi)

## ---- run -------------------------------------------------------------------

.PHONY: run
run: build ## Build + run. Pass flags via ARGS, e.g. `make run ARGS='--file clip.wav'`
	./$(BIN) $(ARGS)

## ---- Silero sidecar (python) ----------------------------------------------

.PHONY: venv
venv: $(VENV)/.stamp ## Create the Silero sidecar venv (onnxruntime backend)

$(VENV)/.stamp:
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install --upgrade pip
	$(VENV)/bin/pip install numpy onnxruntime
	@touch $@
	@echo "venv ready. Point liveatc.vad.sileroPython at $(VENV)/bin/python3"
	@echo "For the torch.hub backend instead: $(VENV)/bin/pip install torch"

## ---- UI (Vue + Vite) -------------------------------------------------------

.PHONY: ui
ui: ## Install deps + build the Vue UI into ui/dist (served by the Go binary)
	cd ui && $(YARN) install && $(YARN) build

.PHONY: ui-dev
ui-dev: ## Run the Vite dev server (proxies /api + /ws to a running backend)
	cd ui && $(YARN) dev

## ---- whisper model ---------------------------------------------------------

.PHONY: model
model: ## Download a whisper GGML model (MODEL=base.en) into MODELS_DIR
	@mkdir -p $(MODELS_DIR)
	curl -L --fail -o $(MODELS_DIR)/ggml-$(MODEL).bin \
		https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-$(MODEL).bin
	@echo "wrote $(MODELS_DIR)/ggml-$(MODEL).bin"

## ---- deploy ----------------------------------------------------------------

.PHONY: deploy
deploy: build-pi ## rsync the Pi binary + sidecar + systemd unit + built UI to PI:PI_DEST
	rsync -avz $(DIST)/$(BIN)-linux-arm64 $(PI):$(PI_DEST)/$(BIN)
	rsync -avz sidecar systemd $(PI):$(PI_DEST)/
	@if [ -d ui/dist ]; then rsync -avz --delete ui/dist $(PI):$(PI_DEST)/ui/; \
	 else echo "note: ui/dist missing -- run 'make ui' to include the web UI"; fi
	@echo "Deployed to $(PI):$(PI_DEST). On the Pi: install systemd/$(BIN).service (see README)."

## ---- housekeeping ----------------------------------------------------------

.PHONY: clean
clean: ## Remove build artifacts
	rm -f $(BIN)
	rm -rf $(DIST)

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
