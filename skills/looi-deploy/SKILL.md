---
name: looi-deploy
description: Install, inspect, configure or verify LOOI DF26 ESP32-S3 robot firmware over USB, including default or custom L298N wiring. Use for LOOI hardware deployment, not general ESP flashing or motor control.
---

Use the Python tool from the [LOOI-DF26-Skill repository](https://github.com/xlle-er/LOOI-DF26-Skill). If the tool is not installed, clone that repository into the user's workspace, create a project `.venv` and install it with `python -m pip install -e .`. Do not install system-wide packages. Python 3.10+ is required. Use `.venv/bin/python` on macOS/Linux and `.venv\Scripts\python.exe` on Windows.

Start with `python -m looi_deploy.cli --json doctor`. If several USB devices appear, ask the user which port belongs to LOOI. Inspect that explicit port. Inspection may reset an older device into its ROM bootloader; disconnect motor power first. Never start motor tests automatically.

Confirm the module marking and DevKitC-1-compatible board pinout. Supported modules are N16R8 (16MB Flash/8MB OPI PSRAM) and N8R8 (8MB Flash/8MB OPI PSRAM). Flash detection cannot establish PSRAM or board wiring. Do not guess an unsupported board's pinout.

Preserve an existing valid hardware profile unless the user asks to change it. For an unconfigured device, ask whether the actual wiring matches ENA=17, IN1=16, IN2=15, IN3=7, IN4=6, ENB=5 (A=left, B=right). For custom wiring, ask all six GPIO numbers in one question, validate with the tool, and show the resulting table before installing. Explain GPIO numbers differ from physical header positions. ESP32 and L298N share GND; remove ENA/ENB PWM jumpers; motor power is disconnected during installation.

For custom wiring write a local profile JSON with `version: 1`, `board: "n16r8"` or `"n8r8"`, and `pins: {ena,in1,in2,in3,in4,enb}` containing integers. Validate using the package's `validate_profile` function before hardware operations. Never edit firmware pin constants or rebuild just to change wiring.

Install with `python -m looi_deploy.cli --json install --port PORT --board BOARD --profile FILE`, or `--use-default-pins` only after confirmation. Omit both to preserve a profile read from an existing device. The tool downloads verified official USB assets; `--release v2.1.0` explicitly selects the 2.1.0 prerelease (hardware acceptance pending), while the default `latest` selects stable releases only. Use a prerelease only when requested or after explaining its unverified hardware status; `--assets DIRECTORY` allows a maintainer's locally prepared release. If no compatible release is published, report that; never silently install 2.0.x. Use `configure` with the same options to change wiring without reflashing, and `verify --port PORT --board BOARD --profile FILE --version VERSION` to verify an installation.

Device administration needs its password (initial password 12345678). Let the tool prompt securely or pass the password through stdin with `--password-stdin`; never put passwords in argv, files, logs, reports or Git. Existing authorization to deploy is sufficient; do not add a separate approval step before running the tool once wiring and target port are known.

Never use erase-flash, overwrite unknown partitions or bypass hardware/OTA compatibility checks. Unknown partition layouts require a separate migration investigation and NVS backup. If native USB re-enumerates, run doctor again, identify the same physical board, and resume inspect/configure/verify rather than flashing repeatedly. Troubleshoot occupied ports/cables first; Linux serial permissions, Windows bridge drivers and BOOT/RST are documented in the repository README.

Success requires the tool's verified result: matching version, board, physical memory and all six pins, with hardware_ready=true. Keep the password-free `.looi-deploy` record local. Report software checks separately from real motor tests. After installation point users to the LOOI-Setup hotspot/device panel for Wi-Fi and bounded wheel calibration with wheels lifted. Wiring survives compatible official OTA; clearing NVS requires confirming wiring again.
