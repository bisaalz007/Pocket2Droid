# Pocket2Droid

A Windows Mobile emulator for Android that runs the complete OS, including applications and games.

Pocket2Droid is under active development. Compatibility and performance vary by device, ROM and game.

## Download

APKs will be available on the [Releases page](https://github.com/samsixx6/Pocket2Droid/releases).

## Features

- ROM library with individual ROM settings
- Persistent internal storage for each ROM
- Shared or custom storagecard folders
- Guest resolution presets and screen fitting
- Fullscreen mode
- On-screen keys and display FPS overlay

The FPS overlay reports display presentations, not necessarily the game's actual frame rate.

## Requirements

- ARM64 Android device
- Android 7.0 or newer
- A compatible `.bin` ROM image

ROMs, games and applications are not included.

## Getting started

1. Download and install the APK from Releases.
2. Grant the requested storage access.
3. Tap **+** to import a `.bin` ROM.
4. Tap the ROM to start it.

Known ROM filenames select a resolution preset automatically. Check the guest resolution in ROM settings if the display looks incorrect.

## Storage

The default shared folder is `Internal storage/pocket2droid`:

- `Roms` — imported ROM images
- `data` — ROM settings and persistent internal storage
- `storagecard` — files accessible to the guest

Use a dedicated storagecard folder. The guest OS can modify or delete files inside it.

## Reporting problems

Please open an issue with:

- Phone model and Android version
- Pocket2Droid version
- ROM filename and selected guest resolution
- Application or game name, if relevant
- Steps to reproduce the problem

## Community and download links

- [Discord](https://discord.com/invite/33DtX7HcxA)
- [YouTube](https://www.youtube.com/@Pocket2Droid)
