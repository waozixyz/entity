ZIRAN ?= ziran
LOCK_FLAGS := $(if $(wildcard ziran.local.toml),,--locked)
KRYON_DIR = $(shell $(ZIRAN) pkg path kryon $(LOCK_FLAGS))
ZIRAN_ROOT = $(shell $(ZIRAN) pkg path ziran $(LOCK_FLAGS))
SOURCES := $(wildcard src/*.zi)
ASSETS := $(shell rg --files assets)
RUNTIME_SOURCES = $(wildcard $(ZIRAN_ROOT)/cmd/zir/*.[ch] $(ZIRAN_ROOT)/include/*.h $(ZIRAN_ROOT)/build/bin/ziran)
UI_SOURCES = $(wildcard $(KRYON_DIR)/src/ui/*.zi $(KRYON_DIR)/src/backend/*.zi $(ZIRAN_ROOT)/std/*.zi)
.PHONY: all test run
all: build/self.zib
build/self.zib: $(SOURCES) $(UI_SOURCES) $(RUNTIME_SOURCES) $(ASSETS) ziran.lock Makefile
	mkdir -p build
	$(ZIRAN) bundle --root . --module-path src --module-path kryon=$(KRYON_DIR)/src/backend \
		--module-path kryon=$(KRYON_DIR)/src/ui --module-path $(KRYON_DIR)/src/ui --module-path $(ZIRAN_ROOT)/std \
		--define KRYON_HOSTED_UI --asset-dir assets=assets --entry self:Main -o $@ src/self.zi
test: build/self.zib
	$(ZIRAN) fmt --check src/*.zi tests/*.zi
	$(ZIRAN) build --project --target=c --entry model_test:main -o build/model-test tests/model_test.zi
	$(CC) -std=c99 -O2 -I$(ZIRAN_ROOT)/include -Ibuild/model-test build/model-test/*.c -o build/model-test/test
	env -u DISPLAY -u WAYLAND_DISPLAY build/model-test/test
run: build/self.zib
	$(KRYON_DIR)/build/bin/zib build/self.zib
