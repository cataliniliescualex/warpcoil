# WarpCoil — standalone Windows and Linux builds (beta)

The bundled executables include a private Python runtime. **You do not need to install Python**.

## Windows (64-bit)

1. Download `WarpCoil-Windows-x64.zip`, then extract it.
2. Double-click `WarpCoil.exe` **from the extracted folder**. Keep its terminal window open while transferring.
3. If Windows Firewall prompts you, allow access on **private networks only**, not public networks.
4. Open the address displayed in the terminal in Safari on your iPhone, and enter the six-digit pairing PIN.
5. Transfer files. Close the terminal or press Ctrl+C when finished.

A new unsigned executable may trigger a Windows SmartScreen warning. Verify that you downloaded it from the project's official GitHub release; do not disable antivirus protection. A code-signing certificate is not included.

## Ubuntu/Linux (64-bit x86_64)

1. Download `WarpCoil-Linux-x64.tar.gz` and extract it.
2. In a terminal, `cd` into the extracted folder and run `./WarpCoil`.
3. If necessary, run `chmod +x WarpCoil` once. Keep the terminal open to see the pairing code.
4. Open the displayed address in Safari on your iPhone, enter the PIN, and select files.
5. Press Ctrl+C to stop the server when finished.

The Linux build targets Ubuntu 22.04+ x86_64 (glibc-based distributions). It is not an Android APK or an AppImage, and may not run on ARM/Raspberry Pi, Alpine Linux, or older glibc versions.

## Compatibility and security

- Transfers stay in `~/Videos/LocalDrop` by default, for compatibility with earlier versions.
- Existing browser pairing keys, upload metadata and `.localdrop-parts` are unchanged.
- You can change the destination by launching `WarpCoil --folder /your/path` (or `WarpCoil.exe --folder ...`).
- The app uses **HTTP without TLS encryption**. Only use it on a private, trusted home or office LAN. Never forward port 8765 to the internet.
- It serves incoming files to the receiving computer; it is not a peer-to-peer file sync tool.
- MPL-2.0, copyright and third-party packaging notices are distributed with the binaries.
