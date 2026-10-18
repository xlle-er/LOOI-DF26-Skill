---
name: looi-deploy
description: Guide activity participants through their first LOOI DF26 firmware installation, using Agent-assisted USB flashing or the web installer, with recommended-board defaults or custom wiring.
---

# First installation

Help beginners and experienced participants install the latest official stable firmware. Do not ask participants to choose a firmware version or require a fixed version number. Reuse information they already supplied and skip answered questions.

First ask: “你使用的是活动方推荐的开发板吗？” (是 / 否 / 不确定).
- Yes: use N16R8 and official default wiring. Say “请按文档接线，烧录时断开电机电源” and link the [wiring documentation](https://github.com/xlle-er/LOOI-DF26-Firmware#官方接线). This confirmation is sufficient: do not additionally ask for module markings or each GPIO.
- No / unsure: help identify an ESP32-S3 N16R8 or N8R8 module with a DevKitC-1-compatible pinout. Flash capacity alone cannot establish PSRAM or wiring. Do not guess unsupported pinouts. Ask whether they use documented official wiring or custom wiring; only custom wiring needs all six GPIOs, collected in one question.

Ask once: “你想给 LOOI 起什么名字？支持中文，也可以保留默认识别码。” Reuse any name already provided. Names must contain visible text and fit 24 UTF-8 bytes (up to 8 common Chinese characters). Never truncate a character. The firmware derives both the robot's BLE name and hotspot as `LOOI-名字`; skipped naming keeps the current name or the default `LOOI-识别码`.

Then ask whether they prefer Agent-assisted USB installation or the web installer, unless their request already makes this clear. Choosing a route does not require a second deployment approval.

## Agent-assisted USB installation

Fetch the latest `main` source directly from the [LOOI-DF26-Skill repository](https://github.com/xlle-er/LOOI-DF26-Skill): `git clone --branch main https://github.com/xlle-er/LOOI-DF26-Skill.git`. Install or refresh the skill from `skills/looi-deploy/` in that checkout and use its matching `looi_deploy/` tool. Do not require a tutorial attachment or use a bundled snapshot as the source of updates. If reusing a clean checkout, fetch `origin main` and update with `git pull --ff-only origin main`; preserve local edits and stop on divergence rather than resetting them. Use a fresh checkout when updating would conflict with local work. Create a project `.venv` and run `python -m pip install -e .` there. Python 3.10+ is required; do not install system-wide packages. Use `.venv/bin/python` on macOS/Linux or `.venv\Scripts\python.exe` on Windows.

Run `python -m looi_deploy.cli --json doctor`, identify the target USB port, then `inspect --port PORT`. Ask which port belongs to LOOI if there are multiple candidates. Disconnect motor power before inspection, which can reset an older board. Never start motor tests automatically.

For a first installation on the recommended board, run `python -m looi_deploy.cli --json install --port PORT --board n16r8 --use-default-pins`. Add `--name NAME` only when the participant chose a name; the tool writes it over USB and verifies both BLE/status name and hotspot after reboot. Omit `--release`: the tool downloads and verifies the latest official stable assets. If unavailable or incompatible, explain the failure; do not silently use a prerelease or bypass compatibility checks. Only use an explicit `--release TAG` or `--assets DIRECTORY` when requested by a maintainer.

Inspect existing wiring before choosing installation options. Preserve an existing valid hardware profile by omitting both profile options. If it differs from the recommended board/default pins, explain that briefly and ask whether to keep it or switch to official wiring; default to preservation. Actual hardware conflicting with the selected board must stop installation for clarification, never trigger automatic reflashing with another board profile.

For custom wiring, write a local JSON profile with `version: 1`, `board: "n16r8"` or `"n8r8"`, and `pins: {ena,in1,in2,in3,in4,enb}` containing integers. Validate with the package's `validate_profile`, show the resulting table, then use `--profile FILE`. GPIO numbers differ from header positions. Official pins are ENA=17, IN1=16, IN2=15, IN3=7, IN4=6, ENB=5; A=left, B=right. Share GND and remove ENA/ENB PWM jumpers. Do not rebuild firmware to change wiring.

First-time participants have not set a personal device password. Do not ask them to create or enter one, and do not add a password-choice step. The Python tool automatically supplies the firmware’s built-in initial credential for wiring and naming; run the normal install command without `--password-stdin`. If an existing device rejects initial authentication, stop and explain that it was previously configured; do not reset its credentials or erase NVS. Only in that existing-device recovery flow may the owner supply their current credential through `--password-stdin`; never put personal credentials in argv, files, logs, reports or Git.

Success requires the tool's verified result: device version matches the downloaded manifest dynamically, board/physical memory/all six pins match, and `hardware_ready=true`. An independent `verify --port PORT --board BOARD` does not need `--version`; never add a fixed version gate. Keep the password-free `.looi-deploy` record local. Report the installed version as a result, not a prerequisite.

## Web installation

The [installer source](https://github.com/xlle-er/LOOI-DF26-Firmware/tree/main/installer) exists, but the public installer is not yet deployed. Say so explicitly; do not present the planned Pages URL as usable. Offer Agent-assisted installation, or local hosting when requested. Once deployment is confirmed, direct participants to the verified live URL.

The web route uses the same recommended-board question and N16R8/default-wiring shortcut. Other boards expose model/wiring controls; existing configurations are preserved unless the participant chooses to replace them. Participants select the USB device and click Install in desktop Chrome/Edge over HTTPS or localhost. Do not ask them to select a firmware version. First-time installation has no device-password field: the wizard handles the initial credential internally. If an older published installer still requires that field, use the updated installer source or the Agent route instead of adding a password question for participants.

## Recovery and next steps

Never erase-flash, overwrite unknown partitions or bypass hardware/OTA checks. Unknown layouts require a separate migration investigation and NVS backup. If native USB re-enumerates, run doctor, identify the same physical board, and resume inspect/configure/verify instead of flashing repeatedly. Check occupied ports and data cables first; driver, serial permission and BOOT/RST guidance is in the repository README.

For wiring-only changes use `configure` with the same profile options without reflashing. After installation direct participants to the hotspot name returned in `ap_ssid` (now `LOOI-名字` or `LOOI-识别码`) and `http://192.168.4.1/` for Wi-Fi and direction calibration with wheels lifted. Distinguish software verification from real motor testing. Compatible official OTA preserves wiring; clearing NVS requires configuring it again.
