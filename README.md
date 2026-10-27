# WarpCoil

**Big files. Local transfers. Zero cloud.**

[Website](https://cataliniliescualex.github.io/warpcoil/) · [Download latest beta](https://github.com/cataliniliescualex/warpcoil/releases/tag/v1.3.2) · [Report an issue](https://github.com/cataliniliescualex/warpcoil/issues/new) · [Contribute](CONTRIBUTING.md)

WarpCoil transfers original-quality videos and other files from an iPhone browser to a Windows or Ubuntu computer over a trusted local network. It is free and open source under the **Mozilla Public License 2.0**.

> **English UI beta — version 1.3.2.** Tested by the project creator on Windows, Ubuntu and an iPhone with files larger than 4 GB. This is community-tested beta software, not a security-audited release.

## Features

- Local network transfer; no cloud account or remote upload service.
- Upload large files in 2 MiB chunks without loading the entire file into memory.
- Resume interrupted uploads after reselecting a file in the same browser/session (provided the stored transfer metadata matches).
- Pair with a six-digit PIN shown on the computer.
- Built-in local-network speed test and diagnostic logs.
- Preserve the transmitted file bytes; WarpCoil itself does not re-encode videos.

## Requirements

- Python 3.9+ on the receiving computer (standard library only).
- Windows or Ubuntu/Linux; iPhone with Safari on the same trusted local network.
- Enough free storage for the incoming files.

## Getting started

### Windows

1. Download the source ZIP from the official GitHub release and extract it.
2. Open the extracted folder and double-click `start_windows.bat`.
3. If Windows Firewall asks, allow **private networks only**.
4. On your iPhone, open the displayed `http://COMPUTER_IP:8765` address in Safari.
5. Enter the PIN shown on the computer and choose your files.

### Ubuntu

```bash
python3 localdrop.py
# alternatively: bash start_ubuntu.sh
```

Connect the iPhone to the same trusted local network. Your laptop may use Ethernet while your iPhone uses Wi-Fi.

### Receiving folder

By default files are saved under `~/Videos/LocalDrop` (the historical default folder, retained for compatibility on Windows and Linux). To customize:

```bash
python3 localdrop.py --folder "/path/to/destination"
```

On Windows with Python launcher: `py -3 localdrop.py --folder "D:\Video"`.

**Do not remove `.localdrop-parts`** inside your chosen destination when you intend to resume incomplete transfers.

## Diagnostics

On the iPhone open **03 / DIAGNOSTIC** and run the 8 MB local speed test. The app also reports per-chunk read and network timings. If a transfer stalls, use the copy diagnostics control, and remove personal file names before filing an issue.

## Security and privacy

**Only use WarpCoil on networks you trust.** The current release uses **unencrypted HTTP**, even after PIN pairing. Users on the same network with sufficient access could intercept traffic, including authentication data and transferred files. Do **not** expose port 8765 to the public internet, forward your router's port, or use public/hotel/guest Wi-Fi. Keep the server running only while transferring files. See [SECURITY.md](SECURITY.md).

No telemetry, third-party server, or cloud service is used by the program. The included local networking speed test generates test data on the phone.

## Testing

```bash
python3 -m unittest -v test_localdrop.py
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## License

Source code is licensed under [MPL-2.0](LICENSE). See [NOTICE.md](NOTICE.md) for attribution. The WarpCoil name and any future logos are not granted as trademarks by the MPL license.

## Compatibility with LocalDrop v1.3.0

WarpCoil is the new name for the original LocalDrop project. The executable remains `localdrop.py`, the browser pairing state and `X-LocalDrop-Token` HTTP header are preserved, and the default receiving folder is still `~/Videos/LocalDrop`. Keep `.localdrop-parts` if you intend to resume an unfinished transfer. Existing LocalDrop releases remain accessible in the repository history.
