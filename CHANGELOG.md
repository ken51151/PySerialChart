# Changelog

Historical version labels and dates are preserved. New changes remain under Unreleased until a release version is assigned.

## 0.4 (2026/10/21)

- Added a main-window TX/RX terminal with ASCII, ASCII + HEX and HEX display, ending/fixed-length framing and idle flushing.
- Moved receive processing into a threaded, batched pipeline with separate terminal and plot consumers.
- Split Plot into an independent window with pause/resume, retained curves on hide, and separate clear behavior.
- Added COM and plot settings dialogs; plot settings include a live parsing preview for ASCII and binary data.
- Centralized settings in `AppConfig` and added APIs for applying configuration snapshots.
- Added toolbar/menu actions, updated icons, and a shared application icon.
- Added About / Licenses and bundled license/source information.
- Added automated configuration, preview and packaging tests.
- Added the Windows onedir build workflow under `packaging/`, including pinned dependencies, ZIP output, SHA256 checksums and EXE smoke tests.
- Reorganized documentation into a screenshot-focused README, TODO list and changelog.

## 0.3 (2026/05/28)

- Added editable TX command history with Up/Down navigation and mouse-selectable history.
- Added Tab completion for TX history commands.
- Added raw HEX transmit mode using the `hex:` prefix, such as `hex: 01 02 0A FF`.
- Prevented empty TX input from sending only a line ending.
- Moved TX handling into `serial_tx.py`, including TX input widgets, HEX parsing, and TX worker/controller logic.
- Added non-blocking TX thread/controller so serial writes do not freeze the UI.
- Added TX timeout/error reporting with the original TX string.
- Added a status bar with COM state and TX status messages.
- Updated UI sizing, font family, TX row layout, and plot minimum height.
- Added `.gitignore` for Python cache and local environment files.

## 0.2 (2026/05/27)

- Added version constants and versioned window title.
- Added configurable X-axis follow mode.
- Added text transmit input with selectable line ending.
- Optimized multi-line ASCII updates by batching new values per curve before updating buffers.
- Changed Y-axis auto-scaling to apply once instead of continuously auto-ranging.
- Added README documentation.

## 0.1

- Initial serial plotting tool.
- Added COM port reading, packet parsing, single-line mode, multi-line ASCII mode, cursor inspection, and basic plot controls.
