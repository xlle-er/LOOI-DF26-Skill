# LOOI-DF26-Skill

用一句话让 Codex 或其他 Agent 部署 LOOI ESP32-S3 底盘；也可直接使用跨平台 Python 工具。支持 N16R8、N8R8 的 DevKitC-1 兼容开发板，官方默认接线和自定义 GPIO 共用同一份固件，接线保存在设备中。

**当前需要配套固件 2.1.0 或更新版本。工具不会回退安装 2.0.x。2.1.0 尚未发布时，在线安装会报告没有兼容版本；维护者可以使用本地构建资产测试。** 固件、独立网页安装页和发布产物在 [LOOI-DF26-Firmware](https://github.com/xlle-er/LOOI-DF26-Firmware)。本仓库不包含固件二进制。

## 一句话安装 skill

把下面这一句话发给 Codex，Agent 会安装 skill，无需手动下载或复制目录：

> 请从 https://github.com/xlle-er/LOOI-DF26-Skill/tree/main/skills/looi-deploy 安装 looi-deploy skill。

安装完成后，在下一条消息中开始部署：

> 帮我通过 USB 部署 LOOI 底盘，先检查开发板，再询问我的接线。

Agent 会列出串口，确认模块型号和实际接线，执行检查、下载校验、烧录、配置和回读。依赖安装在项目独立环境中。安装 skill 本身不会烧录硬件；部署时不会自动点动电机、擦除 NVS 或覆盖未知分区。

## 手动使用

Python 3.10+。macOS/Linux：

```sh
git clone https://github.com/xlle-er/LOOI-DF26-Skill.git
cd LOOI-DF26-Skill
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m looi_deploy.cli --json doctor
.venv/bin/python -m looi_deploy.cli --json inspect --port /dev/cu.YOUR_DEVICE
.venv/bin/python -m looi_deploy.cli --json install --port /dev/cu.YOUR_DEVICE --board n16r8 --use-default-pins
```

Windows PowerShell：

```powershell
git clone https://github.com/xlle-er/LOOI-DF26-Skill.git
cd LOOI-DF26-Skill
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m looi_deploy.cli --json doctor
.\.venv\Scripts\python.exe -m looi_deploy.cli --json inspect --port COM3
.\.venv\Scripts\python.exe -m looi_deploy.cli --json install --port COM3 --board n8r8 --use-default-pins
```

以上串口仅为示例。始终使用 `doctor` 中实际属于目标开发板的串口；多个设备时不能猜测。`--use-default-pins` 仅在实际接线符合下表时使用。已有配置的重装省略该参数即可保留；未配置设备需要明确选择默认接线或提供配置文件。

| L298N | GPIO |
|---|---:|
| ENA（左） | 17 |
| IN1 | 16 |
| IN2 | 15 |
| IN3 | 7 |
| IN4 | 6 |
| ENB（右） | 5 |

使用 GPIO 编号，不是排针序号。ESP32 与 L298N 共地，拔掉 ENA/ENB 跳帽，安装和配置时断开电机电源。模块型号和板载占用关系必须人工确认；Flash 检测无法判断 PSRAM 或排针布局。首次配置前 GPIO 不启用输出；若电机驱动输入无下拉，不能依赖浮空引脚保证电机电气状态，需保持电机断电或使用适当的使能下拉。

自定义配置文件示例 `my-wiring.json`：

```json
{"version":1,"board":"n16r8","pins":{"ena":17,"in1":16,"in2":15,"in3":7,"in4":6,"enb":5}}
```

```sh
.venv/bin/python -m looi_deploy.cli --json configure --port /dev/cu.YOUR_DEVICE --board n16r8 --profile my-wiring.json
.venv/bin/python -m looi_deploy.cli --json verify --port /dev/cu.YOUR_DEVICE --board n16r8 --profile my-wiring.json --version 2.1.0
# 维护者使用已构建的配套 USB 清单和分段文件：
.venv/bin/python -m looi_deploy.cli --json install --port /dev/cu.YOUR_DEVICE --board n16r8 --profile my-wiring.json --assets ../LOOI-DF26-Firmware/dist
```

`install`、`configure` 会安全询问设备管理密码，初始密码为 `12345678`。自动化环境可使用 `--password-stdin` 从标准输入提供，勿把密码放进命令参数、配置文件、日志或 Git。`.looi-deploy/` 仅保存设备 ID、固件版本、接线和验证时间，默认忽略。

退出码：`0` 成功；`2` 参数、配置或兼容性错误；`3` 依赖、文件或网络错误；`4` USB 传输错误；`5` 设备拒绝或回读失败。所有命令 stdout 均为 JSON；`--json` 为显式机器输出标记，放在子命令之前。

## 连接故障和升级

- macOS：优先 `/dev/cu.*`，关闭 Arduino 串口监视器及其他占用工具。
- Windows：确认设备管理器中出现 COM 口；仅从开发板或桥接芯片厂商安装对应 USB 驱动。
- Linux：确认当前用户有串口设备权限；按发行版要求加入串口组后重新登录，不使用 `chmod 777`。
- 连接失败：检查数据线，按住 BOOT、按一下 RST，再松开 BOOT。原生 USB 可能重新枚举；重新 `doctor` 并确认同一块板后使用新串口继续 `configure` / `verify`，不要反复烧录。
- 未知分区：工具停止且不写入。先单独调查并备份 NVS，再决定迁移方式；工具不提供绕过检查的参数。
- 保留接线的兼容官方 OTA 可继续使用。擦除 NVS 后需要重新确认接线。旧自定义固件不能可靠读出其 GPIO 常量，第一次迁移必须重新填写。
- 安装后连接 `LOOI-Setup-XXXXXX`，访问 `http://192.168.4.1/` 配网、核对接线并在车轮架空时进行短时方向校准。

## 开发与验证

```sh
.venv/bin/python -m unittest discover -s tests -v
```

`looi_deploy/boards.json` 来自固件仓库 `hardware/boards.json`；修改硬件支持范围时同步生成，固件仓库的 contracts 检查两者一致。.github/workflows/test.yml 在 macOS、Windows、Linux 上运行 Python 3.10/3.12 的测试和 doctor。CI 不能替代各系统的真实 USB、两种模块、供电、电机和 OTA 验收。本次本地验证为 macOS，Windows/Linux 真机 USB 与电机测试仍待完成。

## English

Send this sentence to Codex to install the skill:

> Install the looi-deploy skill from https://github.com/xlle-er/LOOI-DF26-Skill/tree/main/skills/looi-deploy.

Then send a new message: “Deploy my LOOI robot over USB; inspect the board first and ask me how the motors are wired.” Installing the skill itself does not flash hardware.

USB deployment and installable agent skill for LOOI DF26, supporting ESP32-S3 N16R8 and N8R8 DevKitC-1-compatible boards. Requires Python 3.10+ and matching firmware 2.1.0+. Install in a project virtual environment with `pip install -e .`, run `python -m looi_deploy.cli --json doctor`, then inspect an explicit port. Install with `--board n16r8` or `--board n8r8` and confirmed `--use-default-pins` or `--profile FILE`. Existing valid wiring is preserved when neither option is supplied. `configure` updates persistent wiring without recompiling or flashing; `verify` checks firmware, physical memory and all six GPIOs. Compatible official OTA retains wiring. Unknown partitions, incompatible boards and invalid/reserved GPIOs fail closed. No motor commands are sent by this tool.
