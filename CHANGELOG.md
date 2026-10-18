# Changes

## 1.0.2 (682)

Changes since v1.0.1:

- Add support for compatible Windows Mobile 5 Device Emulator images, with persistent retained RAM where required by the ROM.
- Add Restart above Exit in the session menu. Restart saves persistent guest storage before starting the emulator again.
- Add custom guest width and height alongside resolution presets. ROM-specific display glitches and touchscreen calibration requirements remain possible.
- Add per-ROM Internet access using an NE2000 PC Card and native IPv4 NAT/DHCP/DNS through libslirp. New profiles default to On; saved Off settings remain Off.
- Add guarded automatic Work-to-Internet setup for supported stock Windows Mobile configurations. The helper is also supplied to existing Internet-On profiles, including profiles created before the feature was added.
- Fix Android helper delivery by retaining mandatory memory seals without requiring the redundant host chmod that Android rejected.
- Allow each ROM to select its own StorageCard folder through a Cancel/Continue warning while keeping the general folder and import destination fixed. The row includes a tap-to-change hint and the warning uses a red icon.
- Hide the virtual `2577` and `autorun.exe` helper entries from normal File Explorer views while keeping their required autorun paths. Real user folders are unchanged; Show all files can reveal hidden entries.

The automatic setup helper preserves custom guest configuration, prior attempts and successful setup markers. Unsupported or previously failed configurations can still require manual setup. Old browsers' modern website/TLS limitations remain. Full phone browsing confirmation of the test10 existing-profile correction is pending.

This source snapshot matches the final signed 1.0.2 APK, which promotes test10 without behavior changes. Documentation and Git ignore rules were refreshed for the GitHub source update. No new performance improvement is claimed.

## 1.0.1 (671)

- Correct guest calendar/timing behavior that prevented some games from progressing past startup.
- Preserve the v1.0 application identity, storage and controls.
