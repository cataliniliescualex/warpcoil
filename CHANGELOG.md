# Changelog

## Standalone binary packaging (additional v1.3.2 distribution)

- Added native Windows x64 and Linux x64 one-file builds via PyInstaller and GitHub Actions.
- Each binary bundles Python, the HTML/CSS/JavaScript UI, MPL-2.0 license and security documentation.
- Added HTTP/API upload smoke tests against compiled binaries on both operating systems.
- No changes to the v1.3.2 transfer protocol, resume mechanism, or receiving folder.

## 1.3.2 — English interface update

- Translated the web UI, diagnostics, console output, and messages into English.
- Preserved the same transfer engine, pairing protocol, and resume metadata.


## 1.3.1 — WarpCoil rebranding

- Changed visible product name and landing-page identity from LocalDrop to WarpCoil.
- Preserved transfer protocol, browser storage keys, legacy script entry point, and existing video destination to support interrupted transfers.
- Kept original LocalDrop v1.3.0 release in project history.


## 1.3.0 — Initial public beta candidate

- Local-network transfers from iPhone Safari to Windows and Ubuntu.
- Chunked and resumable uploads, PIN pairing and transfer diagnostics.
- Reduced disk synchronization frequency for better performance.
- First MPL-2.0 source release preparation, English documentation and notices.
