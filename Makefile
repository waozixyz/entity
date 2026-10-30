ZIRAN ?= ./scripts/ziran.sh
LOCK_FLAGS := $(if $(wildcard ziran.local.toml),,--locked)
KRYON_DIR = $(shell $(ZIRAN) pkg path kryon $(LOCK_FLAGS))
ZIRAN_ROOT = $(shell $(ZIRAN) pkg path ziran $(LOCK_FLAGS))
QRCODE_DIR = $(shell $(ZIRAN) pkg path qrcode $(LOCK_FLAGS))
DAOCHI_CLIENT_DIR = $(shell $(ZIRAN) pkg path daochi_client $(LOCK_FLAGS))
CRYPTO_DIR = $(shell $(ZIRAN) pkg path crypto $(LOCK_FLAGS))
OQS_DIR = $(shell $(ZIRAN) pkg path oqs $(LOCK_FLAGS))
LIBOQS_DIR = $(shell $(ZIRAN) pkg path liboqs $(LOCK_FLAGS))
MONOCYPHER_DIR = $(shell $(ZIRAN) pkg path monocypher $(LOCK_FLAGS))
# Device keys sign with Monocypher's standard Ed25519.
MONOCYPHER_SOURCES = $(MONOCYPHER_DIR)/src/monocypher.c $(MONOCYPHER_DIR)/src/optional/monocypher-ed25519.c
LIBOQS_LIBRARY ?= build/liboqs/lib/liboqs.a
MODULE_PATHS = --module-path src --module-path kryon=$(KRYON_DIR)/src/backend \
	--module-path $(KRYON_DIR)/src/backend --module-path kryon=$(KRYON_DIR)/src/ui \
	--module-path $(KRYON_DIR)/src/ui --module-path $(ZIRAN_ROOT)/std \
	--module-path qrcode=$(QRCODE_DIR)/src --module-path daochi_client=$(DAOCHI_CLIENT_DIR) \
	--module-path $(DAOCHI_CLIENT_DIR) --module-path crypto=$(CRYPTO_DIR)/src --module-path oqs=$(OQS_DIR)/src
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
test: build/entity.zx native-test records-test alias-test model-test picture-publish-test dew-play-test dew-packs-test achievement-view-test
	$(ZIRAN) fmt --check src/*.zi tests/*.zi
model-test:
	rm -rf build/model-test
	$(ZIRAN) build --root . $(MODULE_PATHS) --target=c --entry model_test:main -o build/model-test tests/model_test.zi
	$(CC) -std=c99 -O2 -I$(ZIRAN_ROOT)/include -Ibuild/model-test $$(rg --files build/model-test -g '*.c') -o build/model-test/test
	env -u DISPLAY -u WAYLAND_DISPLAY build/model-test/test

# Profile pictures reach the node from every app through one publisher.
.PHONY: picture-publish-test
picture-publish-test:
	rm -rf build/picture-publish-test
	$(ZIRAN) build --root . $(MODULE_PATHS) --target=c --entry picture_publish_test:main -o build/picture-publish-test tests/picture_publish_test.zi
	$(CC) -std=c99 -O2 -I$(ZIRAN_ROOT)/include -Ibuild/picture-publish-test $$(rg --files build/picture-publish-test -g '*.c') -o build/picture-publish-test/test
	env -u DISPLAY -u WAYLAND_DISPLAY build/picture-publish-test/test

.PHONY: premium-alias-test
premium-alias-test:
	mkdir -p build/premium-alias-test
	$(ZIRAN) build --root . $(MODULE_PATHS) --target=c --entry premium_alias_test:main -o build/premium-alias-test tests/premium_alias_test.zi
	$(CC) -std=c99 -O2 -I$(ZIRAN_ROOT)/include -Ibuild/premium-alias-test $$(rg --files build/premium-alias-test -g '*.c') -o build/premium-alias-test/test
	env -u DISPLAY -u WAYLAND_DISPLAY -u XAUTHORITY -u DBUS_SESSION_BUS_ADDRESS -u SESSION_MANAGER build/premium-alias-test/test

# Google Play Dew purchases are forgotten only after the node credits them.
.PHONY: dew-play-test
dew-play-test: dew-play-savings-test
	rm -rf build/dew-play-test
	$(ZIRAN) build --root . $(MODULE_PATHS) --target=c --entry dew_play_test:main -o build/dew-play-test tests/dew_play_test.zi
	$(CC) -std=c99 -O2 -I$(ZIRAN_ROOT)/include -Ibuild/dew-play-test $$(rg --files build/dew-play-test -g '*.c') -o build/dew-play-test/test
	env -u DISPLAY -u WAYLAND_DISPLAY build/dew-play-test/test

# The Dew shop's packs, their Monero prices and the custom amount.
.PHONY: dew-packs-test
dew-packs-test:
	rm -rf build/dew-packs-test
	$(ZIRAN) build --root . $(MODULE_PATHS) --target=c --entry dew_packs_test:main -o build/dew-packs-test tests/dew_packs_test.zi
	$(CC) -std=c99 -O2 -I$(ZIRAN_ROOT)/include -Ibuild/dew-packs-test $$(rg --files build/dew-packs-test -g '*.c') -o build/dew-packs-test/test
	env -u DISPLAY -u WAYLAND_DISPLAY build/dew-packs-test/test

.PHONY: dew-play-savings-test
dew-play-savings-test:
	rm -rf build/dew-play-savings-test
	$(ZIRAN) build --root . $(MODULE_PATHS) --target=c --entry dew_play_savings_test:main -o build/dew-play-savings-test tests/dew_play_savings_test.zi
	$(CC) -std=c99 -O2 -I$(ZIRAN_ROOT)/include -Ibuild/dew-play-savings-test $$(rg --files build/dew-play-savings-test -g '*.c') -o build/dew-play-savings-test/test
	env -u DISPLAY -u WAYLAND_DISPLAY build/dew-play-savings-test/test
	$(ZIRAN) bundle --root . $(MODULE_PATHS) --entry dew_play_savings_test:main -o build/dew-play-savings-test/test.zx tests/dew_play_savings_test.zi
	env -u DISPLAY -u WAYLAND_DISPLAY $(ZIRAN) run build/dew-play-savings-test/test.zx

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
		-I$(MONOCYPHER_DIR)/src $$(rg --files build/generated/native -g '*.c') $(MONOCYPHER_SOURCES) build/ziran/libziran.a $(LIBOQS_LIBRARY) \
		$$(pkg-config --libs sdl2 cairo freetype2 fontconfig pangocairo gtk+-3.0) -lX11 -l:libcurl.so.4 -lm -lpthread -lz -o $@
native: build/entity
# Publishes a JSON document as a public Daochi publication; see tools/publication.zi.
publication: build/publication
build/publication: tools/publication.zi src/publications_read.zi $(UI_SOURCES) build/ziran/libziran.a $(LIBOQS_LIBRARY) ziran.lock Makefile
	rm -rf build/publication-c
	$(ZIRAN) build --root . $(MODULE_PATHS) --target=c --entry publication:main -o build/publication-c tools/publication.zi
	$(CC) -std=c11 -O2 -ffunction-sections -fdata-sections -Wl,--gc-sections -I$(ZIRAN_ROOT)/include -Ibuild/publication-c $$(find build/publication-c -type d -printf ' -iquote %p') \
		-I$(MONOCYPHER_DIR)/src $$(rg --files build/publication-c -g '*.c') $(MONOCYPHER_SOURCES) build/ziran/libziran.a $(LIBOQS_LIBRARY) -l:libcurl.so.4 -lm -lpthread -lz -o $@
# The entity.records service alone and between two devices through a
# private local Daochi node (DAOCHI_BIN, by default the checkout's build).
.PHONY: records-test
records-test: $(LIBOQS_LIBRARY)
	ZIRAN_BIN=$(ZIRAN) ZIRAN_ROOT=$(ZIRAN_ROOT) KRYON_DIR=$(KRYON_DIR) DAOCHI_CLIENT_DIR=$(DAOCHI_CLIENT_DIR) CRYPTO_DIR=$(CRYPTO_DIR) \
		OQS_DIR=$(OQS_DIR) MONOCYPHER_DIR=$(MONOCYPHER_DIR) LIBOQS_LIBRARY=$(abspath $(LIBOQS_LIBRARY)) python3 scripts/records_test.py
# Account aliases set the way the Alias page does, through a private local
# Daochi node (DAOCHI_BIN, by default the checkout's build).
.PHONY: alias-test
alias-test: $(LIBOQS_LIBRARY)
	ZIRAN_BIN=$(ZIRAN) ZIRAN_ROOT=$(ZIRAN_ROOT) KRYON_DIR=$(KRYON_DIR) DAOCHI_CLIENT_DIR=$(DAOCHI_CLIENT_DIR) CRYPTO_DIR=$(CRYPTO_DIR) \
		OQS_DIR=$(OQS_DIR) MONOCYPHER_DIR=$(MONOCYPHER_DIR) LIBOQS_LIBRARY=$(abspath $(LIBOQS_LIBRARY)) python3 scripts/alias_test.py
.PHONY: premium-alias-node-test
premium-alias-node-test: $(LIBOQS_LIBRARY)
	ZIRAN_BIN=$(ZIRAN) ZIRAN_ROOT=$(ZIRAN_ROOT) KRYON_DIR=$(KRYON_DIR) DAOCHI_CLIENT_DIR=$(DAOCHI_CLIENT_DIR) CRYPTO_DIR=$(CRYPTO_DIR) \
		OQS_DIR=$(OQS_DIR) MONOCYPHER_DIR=$(MONOCYPHER_DIR) LIBOQS_LIBRARY=$(abspath $(LIBOQS_LIBRARY)) python3 scripts/premium_alias_test.py
native-test: $(LIBOQS_LIBRARY)
	ZIRAN_BIN=$(ZIRAN) ZIRAN_ROOT=$(ZIRAN_ROOT) KRYON_DIR=$(KRYON_DIR) DAOCHI_CLIENT_DIR=$(DAOCHI_CLIENT_DIR) CRYPTO_DIR=$(CRYPTO_DIR) \
		OQS_DIR=$(OQS_DIR) MONOCYPHER_DIR=$(MONOCYPHER_DIR) LIBOQS_LIBRARY=$(LIBOQS_LIBRARY) python3 scripts/native_test.py
run: all
	./build/entity build/entity.zx

.PHONY: game-progress-test
game-progress-test:
	$(ZIRAN) check --root src src/game_progress_laws.zi
	mkdir -p build/game-progress-test
	$(ZIRAN) build --root . $(MODULE_PATHS) --target=c --entry game_progress_test:main -o build/game-progress-test tests/game_progress_test.zi
	$(CC) -std=c11 -O1 -ffunction-sections -fdata-sections -Wl,--gc-sections -I$(ZIRAN_ROOT)/include -Ibuild/game-progress-test $$(rg --files build/game-progress-test -g '*.c') -lm -o build/game-progress-test/test
	env -u DISPLAY -u WAYLAND_DISPLAY build/game-progress-test/test

test: game-progress-test

.PHONY: public-identity-test
public-identity-test: build/entity.zx build/ziran/libziran.a
	LDLIBS='$(abspath build/ziran/libziran.a) -lpthread' $(ZIRAN) build --project $(LOCK_FLAGS) --target=c --entry public_identity_test:main --exe -o build/public-identity-test tests/public_identity_test.zi
	env -u DISPLAY -u WAYLAND_DISPLAY -u XAUTHORITY -u DBUS_SESSION_BUS_ADDRESS build/public-identity-test/public_identity_test

test: public-identity-test

.PHONY: profile-refresh-test
profile-refresh-test:
	python3 scripts/profile-refresh-test.py

test: profile-refresh-test

.PHONY: profile-shared-test
profile-shared-test:
	LDLIBS='-l:libcurl.so.4 -lm -lpthread' $(ZIRAN) build --project $(LOCK_FLAGS) --target=c --entry profile_shared_test:main --exe -o build/profile-shared-test tests/profile_shared_test.zi
	env -u DISPLAY -u WAYLAND_DISPLAY -u XAUTHORITY -u DBUS_SESSION_BUS_ADDRESS build/profile-shared-test/profile_shared_test

test: profile-shared-test

# Portable collection protocol and owner-bound service lifecycle, no accounts.
.PHONY: collection-client-test
collection-client-test:
	mkdir -p build/collection-client-test build/level-collections-test
	$(ZIRAN) build --root . --module-path src --target=c --entry collection_client_test:main -o build/collection-client-test tests/collection_client_test.zi
	$(CC) -std=c99 -O2 -I$(ZIRAN_ROOT)/include -Ibuild/collection-client-test $$(rg --files build/collection-client-test -g '*.c') -o build/collection-client-test/test
	env -u DISPLAY -u WAYLAND_DISPLAY build/collection-client-test/test
	$(ZIRAN) build --root . --module-path src --target=c --entry level_collections_test:main -o build/level-collections-test tests/level_collections_test.zi
	$(CC) -std=c99 -O2 -I$(ZIRAN_ROOT)/include -Ibuild/level-collections-test $$(rg --files build/level-collections-test -g '*.c') -o build/level-collections-test/test
	env -u DISPLAY -u WAYLAND_DISPLAY build/level-collections-test/test
	$(ZIRAN) bundle --root . --module-path src --entry collection_client_portable_test:main -o build/collection-client-test/test.zx tests/collection_client_portable_test.zi
	env -u DISPLAY -u WAYLAND_DISPLAY $(ZIRAN) run build/collection-client-test/test.zx

test: collection-client-test

.PHONY: game-progress-client-test
game-progress-client-test:
	mkdir -p build/game-progress-client-test
	$(ZIRAN) build --root . --module-path src --target=c --entry game_progress_client_test:main -o build/game-progress-client-test tests/game_progress_client_test.zi
	$(CC) -std=c99 -O2 -I$(ZIRAN_ROOT)/include -Ibuild/game-progress-client-test $$(rg --files build/game-progress-client-test -g '*.c') -o build/game-progress-client-test/test
	env -u DISPLAY -u WAYLAND_DISPLAY build/game-progress-client-test/test
	$(ZIRAN) bundle --root . --module-path src --entry game_progress_client_test:main -o build/game-progress-client-test/test.zx tests/game_progress_client_test.zi
	env -u DISPLAY -u WAYLAND_DISPLAY $(ZIRAN) run build/game-progress-client-test/test.zx

test: game-progress-client-test

# Dependency-owned native artifacts: keep stdout for the generic descriptor.
build/bin/artifacts: tools/artifacts.zi ziran.lock artifact-tool-force
	mkdir -p build/bin
	CC=cc CFLAGS=-O2 LDFLAGS= LDLIBS=-lcrypto taskset -c $$(python3 -c 'import os; print(min(os.sched_getaffinity(0)))') $(or $(ZIRAN_DIR),$(ZIRAN_ROOT))/build/bin/zi2c --exe --root tools --module-path $(or $(ZIRAN_DIR),$(ZIRAN_ROOT))/cmd --module-path $(or $(ZIRAN_DIR),$(ZIRAN_ROOT))/std --entry artifacts:main -o build/bin tools/artifacts.zi

.PHONY: artifact-test artifact-tool-force
artifact-tool-force:
artifact-test:
	python3 tests/native_artifacts.py

.PHONY: game-reward-client-test
game-reward-client-test:
	ZIRAN_BIN=$(ZIRAN) python3 scripts/game_reward_client_test.py

test: game-reward-client-test
