# Third-party components and references

Pocket2Droid uses QEMU for full-system emulation.

## QEMU

Upstream: https://www.qemu.org/

QEMU is distributed under GPLv2, with component-specific licenses.
Original copyright and license notices are retained in
`qemu-android-exact/`.

Pinned revisions and source provenance are recorded in
`sources.lock.json`.

## Android native dependencies

The native runtime includes GLib, PCRE2, GNU libiconv, pixman,
zlib and libandroid-support.

Dependency versions and hashes are recorded in
`android/build/bionic-tools.json` and `android/build/runtime.json`.
These components retain their respective licenses.

## Microsoft Device Emulator references

Microsoft Device Emulator source was consulted for keyboard
scan codes and key sequences used for compatibility.

The downloaded reference source files, Microsoft emulator
executables and Windows Mobile ROM images are not bundled.

## License scope

The repository's main license does not replace third-party
copyright notices or component-specific licenses.
