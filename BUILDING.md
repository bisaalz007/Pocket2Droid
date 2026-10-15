# Building Pocket2Droid

The v1.0.1 APK was built with an Android Java frontend and an ARM64 QEMU engine compiled for Android's Bionic runtime. This snapshot contains the corresponding source, build recipes and recorded dependency identities.

The archived recipes currently depend on the maintainer's workspace and Linux caches. Building from a fresh checkout requires the portability changes listed below; the source snapshot alone does not yet provide a complete setup command.

## Source layout

| Path | Purpose |
| --- | --- |
| `android/src/com/samsixx/pocket2droid/` | Android activities, library, controls, input mapping and emulator lifecycle |
| `android/native/storage_publish.c` | Native helper for verified file publication |
| `android/res/` | Launcher icon, ROM icons, control artwork and loading GIF |
| `android/tests/` | Frontend, settings, filesystem, input and lifecycle checks |
| `android/build-tooling/` | Shared build-cache and APK-manifest verification helpers |
| `qemu-android-exact/` | QEMU source used by the Android native build, including the Android adaptations |
| `qemu-canonical-changes/` | Pocket2Droid's canonical QEMU changes |
| `tests/` | Native emulation and device correctness checks |
| `sources.lock.json` | Upstream revisions and development provenance |

`qemu-android-exact` already contains the Android adaptations. Applying those adaptations a second time is not part of reconstructing the recorded Android source.

## Toolchain used for v1.0.1

| Component | Configuration |
| --- | --- |
| Host | Ubuntu 24.04 under WSL, x86_64 |
| Python | Python 3.12 in the working host environment |
| Java | OpenJDK 17 |
| Android SDK | API 36 platform and Build Tools 36.0.0 |
| Android NDK | r30, Linux x86_64 toolchain |
| Native target | `aarch64-linux-android24` |
| App SDK settings | Minimum API 24; target API 36 |
| Native build | QEMU `arm-softmmu` with the Pocket2Droid device configuration |
| Alignment | 16 KiB ELF load segments and APK native-library alignment |

The build also uses Git, a host C compiler, Ninja, Make, pkg-config, patch, unzip, patchelf and binutils. QEMU configuration manages its Python build dependencies.

The recorded Android dependency identities are in `android/build/bionic-tools.json`. Selected runtime package inputs are in `android/dependency-inputs/`; they are not a complete SDK or development sysroot. Component license files are retained in `android/dependency-licenses/` and the source trees.

## Current maintainer build process

The following scripts describe the existing working pipeline. Their current workspace assumptions must be resolved before using the same pipeline in a fresh checkout.

1. `android/prepare_tools.py` prepares the Android SDK platform/build tools and Java compiler environment.
2. `android/prepare_bionic.py` prepares the NDK and Android library sysroot.
3. `android/build_bionic.py` compiles the Android QEMU engine from the canonical development checkout and applies the Android adaptations.
4. `android/package_runtime.py` collects the native dependency closure, assigns private library names and checks ELF alignment.
5. `android/build_storage.py` compiles the storage publication helper.
6. `android/build.py` compiles the Java classes and DEX, links Android resources, packages the runtime, aligns the APK and signs it.
7. `android/seal_v1_0_1.py` verifies the clock-fix release and archives its exact source and integrity records. This is a maintainer release tool, not a general contributor build entry point.

`prepare_bionic.py` reads a live Termux package index. Its output should not be assumed to reconstruct the recorded v1.0 dependency versions; those versions and hashes are in `bionic-tools.json`.

## Portability work needed before a fresh-checkout build

### Workspace paths and source synchronization

`sync_source.py` expects a `qemu` Git checkout and a specific upstream revision. `build_bionic.py` also expects Linux caches under `/opt/pocket2droid-tcg-build` and `/opt/pocket2droid-android-tools`. This snapshot provides the exact Android source tree and canonical changes, but no development `.git` history or ready-made `qemu` checkout.

A public build needs an explicit way to select the supplied Android tree or reconstruct the pinned canonical checkout, with configurable toolchain/cache locations.

### Shared helper paths and baseline checks

`android/build.py` imports helpers from a historical sibling source folder and checks a protected previous APK. The helpers are included under `android/build-tooling`, but the script does not yet load them from that location. Contributor builds need checkout-relative helper paths and independent validation, without requiring a previous maintainer APK.

### Signing

The current packaging script requires the maintainer's signing configuration and verifies the official signing certificate. That private key and password are excluded from this source snapshot.

Contributor builds need their own signing configuration. An APK signed with a different key cannot replace the official app as an ordinary update. Build testing should use a separate application ID to preserve official app data.

### Pinned development dependencies

The NDK and dependency records retain their hashes, but the setup recipe still relies on external caches and a live package index. A fresh setup needs the recorded dependencies, including development inputs beyond the bundled runtime packages, and an explicit source-verification step.

## Local checks

With the SDK path and host dependencies configured, the Android filesystem/settings suite is run from the source root with:

```sh
python3 android/tests/run_library_tests.py --settings
python3 android/tests/run_library_tests.py --settings --fallback
```

These checks use temporary local files and the host version of the JNI publication helper. They do not install an APK or operate on phone ROMs and saves. The runner currently expects `android.jar` at `/opt/pocket2droid-android-tools/android-36/android.jar`.

The v1.0 source passed 122 repository assertions and 71 settings/geometry assertions in each filesystem mode. These host checks do not establish Android gameplay speed or a fresh-checkout build.

The native clock correction has two calendar/timing regressions and 17 existing device checks. With a host QEMU built from this source, the clock tests can be run with:

```sh
P2D_QEMU=/path/to/host/qemu-system-arm python3 tests/test_rtc_clock.py
```

Big Range Hunting 2 startup was also confirmed on Android using the 1.0.1-test build; the public build retains the same frontend and native runtime.

## Version and release identity

- App name: `Pocket2Droid`
- Application ID: `com.samsixx.pocket2droid`
- Public version: `1.0.1`
- Internal Android version code: `671`

The internal version code continues from the development builds. Version 1.0.1 installs as an update to public 1.0 and 1.0.1-test, retaining the application ID, signing certificate and existing data. Exit the running ROM normally before updating. Future updates must keep the application ID/signing identity and increase the code.

For this maintainer release, `android/seal_v1_0_1.py` validates the built candidate and produces a separate `apk/1.0.1` folder. Public 1.0 and the test build are preserved. Earlier sealing recipes remain historical; they are not the current package-release workflow.

The sealed v1.0.1 source archive contains its own `SOURCE_SHA256.json` inventory, including the unchanged dependency sources and notices retained from v1.0.
