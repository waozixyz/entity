ZIRAN ?= ./scripts/ziran.sh
LOCK_FLAGS := $(if $(wildcard ziran.local.toml),,--locked)
KRYON_DIR = $(shell $(ZIRAN) pkg path kryon $(LOCK_FLAGS))
ZIRAN_ROOT = $(shell $(ZIRAN) pkg path ziran $(LOCK_FLAGS))
QRCODE_DIR = $(shell $(ZIRAN) pkg path qrcode $(LOCK_FLAGS))
DAOCHI_CLIENT_DIR = $(shell $(ZIRAN) pkg path daochi_client $(LOCK_FLAGS))
OQS_DIR = $(shell $(ZIRAN) pkg path oqs $(LOCK_FLAGS))
LIBOQS_DIR = $(shell $(ZIRAN) pkg path liboqs $(LOCK_FLAGS))
MONOCYPHER_DIR = $(shell $(ZIRAN) pkg path monocypher $(LOCK_FLAGS))
LIBOQS_LIBRARY ?= build/liboqs/lib/liboqs.a
MODULE_PATHS = --module-path src --module-path kryon=$(KRYON_DIR)/src/backend \
	--module-path $(KRYON_DIR)/src/backend --module-path kryon=$(KRYON_DIR)/src/ui \
	--module-path $(KRYON_DIR)/src/ui --module-path $(ZIRAN_ROOT)/std \
	--module-path qrcode=$(QRCODE_DIR)/src --module-path daochi_client=$(DAOCHI_CLIENT_DIR) \
	--module-path $(DAOCHI_CLIENT_DIR) --module-path oqs=$(OQS_DIR)/src
SOURCES := $(wildcard src/*.zi)
ASSETS := $(shell rg --files assets)
RUNTIME_SOURCES = $(wildcard $(ZIRAN_ROOT)/cmd/zir/*.[ch] $(ZIRAN_ROOT)/include/*.h $(ZIRAN_ROOT)/build/bin/ziran)
UI_SOURCES = $(wildcard $(KRYON_DIR)/src/ui/*.zi $(KRYON_DIR)/src/backend/*.zi $(ZIRAN_ROOT)/std/*.zi)
.PHONY: all test run native native-test model-test publication
all: build/entity.zx native
build/entity.zx: $(SOURCES) $(UI_SOURCES) $(RUNTIME_SOURCES) $(ASSETS) ziran.lock Makefile
	mkdir -p build
	$(ZIRAN) bundle --root . --module-path src --module-path kryon=$(KRYON_DIR)/src/backend \
		--module-path kryon=$(KRYON_DIR)/src/ui --module-path $(KRYON_DIR)/src/ui --module-path $(ZIRAN_ROOT)/std \
		--module-path qrcode=$(QRCODE_DIR)/src \
		--define KRYON_HOSTED_UI --asset-dir assets=assets --entry entity:Main -o $@ src/entity.zi
test: build/entity.zx native-test model-test achievement-view-test
	$(ZIRAN) fmt --check src/*.zi tests/*.zi
model-test:
	rm -rf build/model-test
	$(ZIRAN) build --root . $(MODULE_PATHS) --target=c --entry model_test:main -o build/model-test tests/model_test.zi
	$(CC) -std=c99 -O2 -I$(ZIRAN_ROOT)/include -Ibuild/model-test $$(rg --files build/model-test -g '*.c') -o build/model-test/test
	env -u DISPLAY -u WAYLAND_DISPLAY build/model-test/test

.PHONY: achievement-view-test
achievement-view-test:
	mkdir -p build/achievement-view-test
	$(ZIRAN) build --root . $(MODULE_PATHS) --target=c --entry achievement_view_test:main -o build/achievement-view-test tests/achievement_view_test.zi
	$(CC) -std=c11 -O1 -ffunction-sections -fdata-sections -Wl,--gc-sections -I$(ZIRAN_ROOT)/include -Ibuild/achievement-view-test $$(rg --files build/achievement-view-test -g '*.c') -lm -o build/achievement-view-test/test
	env -u DISPLAY -u WAYLAND_DISPLAY -u XAUTHORITY -u DBUS_SESSION_BUS_ADDRESS build/achievement-view-test/test
build/liboqs/lib/liboqs.a: ziran.lock
	cmake -S $(LIBOQS_DIR) -B build/liboqs -DCMAKE_BUILD_TYPE=MinSizeRel -DBUILD_SHARED_LIBS=OFF \
		-DOQS_BUILD_ONLY_LIB=ON -DOQS_USE_OPENSSL=OFF -DOQS_DIST_BUILD=OFF -DOQS_OPT_TARGET=generic -DOQS_MINIMAL_BUILD=SIG_ml_dsa_44
	cmake --build build/liboqs --target oqs
build/ziran/libziran.a: ziran.lock $(RUNTIME_SOURCES)
	env -u DISPLAY -u WAYLAND_DISPLAY $(MAKE) -C $(ZIRAN_ROOT) BUILD_DIR=$(abspath build/ziran) $(abspath $@)
build/generated/native/.complete: $(SOURCES) $(UI_SOURCES) ziran.lock Makefile
	rm -rf $(@D)
	mkdir -p $(@D)
	$(ZIRAN) build --project $(LOCK_FLAGS) --define PLATFORM_DESKTOP --target=c --entry desktop:main -o $(@D) src/desktop.zi
	touch $@
build/entity: build/generated/native/.complete build/ziran/libziran.a $(LIBOQS_LIBRARY) Makefile
	$(CC) -std=c11 -O2 -ffunction-sections -fdata-sections -Wl,--gc-sections -I$(ZIRAN_ROOT)/include -Ibuild/generated/native $$(find build/generated/native -type d -printf ' -iquote %p') \
		$$(rg --files build/generated/native -g '*.c') $(MONOCYPHER_DIR)/src/monocypher.c build/ziran/libziran.a $(LIBOQS_LIBRARY) \
		$$(pkg-config --libs sdl2 cairo freetype2 fontconfig pangocairo gtk+-3.0) -lX11 -l:libcurl.so.4 -lm -lpthread -o $@
native: build/entity
# Publishes a JSON document as a public Daochi publication; see tools/publication.zi.
publication: build/publication
build/publication: tools/publication.zi src/publications_read.zi $(UI_SOURCES) build/ziran/libziran.a $(LIBOQS_LIBRARY) ziran.lock Makefile
	rm -rf build/publication-c
	$(ZIRAN) build --root . $(MODULE_PATHS) --target=c --entry publication:main -o build/publication-c tools/publication.zi
	$(CC) -std=c11 -O2 -ffunction-sections -fdata-sections -Wl,--gc-sections -I$(ZIRAN_ROOT)/include -Ibuild/publication-c $$(find build/publication-c -type d -printf ' -iquote %p') \
		$$(rg --files build/publication-c -g '*.c') $(MONOCYPHER_DIR)/src/monocypher.c build/ziran/libziran.a $(LIBOQS_LIBRARY) -l:libcurl.so.4 -lm -lpthread -o $@
native-test: $(LIBOQS_LIBRARY)
	ZIRAN_BIN=$(ZIRAN) ZIRAN_ROOT=$(ZIRAN_ROOT) KRYON_DIR=$(KRYON_DIR) DAOCHI_CLIENT_DIR=$(DAOCHI_CLIENT_DIR) \
		OQS_DIR=$(OQS_DIR) MONOCYPHER_DIR=$(MONOCYPHER_DIR) LIBOQS_LIBRARY=$(LIBOQS_LIBRARY) python3 scripts/native_test.py
run: all
	./build/entity build/entity.zx
