"""Cross-platform, explicit-port USB deployment. Never executes motor commands."""
import argparse
import getpass
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import ssl
import certifi
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import uuid

BOARDS = json.loads(Path(__file__).with_name('boards.json').read_text())
RELEASE = 'https://github.com/xlle-er/LOOI-DF26-Firmware/releases/'
PIN_NAMES = ('ena', 'in1', 'in2', 'in3', 'in4', 'enb')
MAX_APP = 0x300000

class DeployError(Exception):
    def __init__(self, message, code=2):
        super().__init__(message)
        self.code = code

def validate_profile(profile):
    if not isinstance(profile, dict) or profile.get('board') not in BOARDS:
        raise DeployError('Choose n16r8 or n8r8 and confirm the physical module marking')
    if type(profile.get('version')) is not int or profile['version'] != 1:
        raise DeployError('Unsupported hardware profile version')
    pins = profile.get('pins')
    if not isinstance(pins, dict) or set(pins) != set(PIN_NAMES):
        raise DeployError('Provide all six GPIO names: ENA, IN1, IN2, IN3, IN4, ENB')
    values = [pins[k] for k in PIN_NAMES]
    if any(type(v) is not int or v not in BOARDS[profile['board']]['allowed_gpio'] for v in values):
        raise DeployError('Invalid or reserved GPIO; use GPIO numbers, not header positions')
    if len(set(values)) != 6:
        raise DeployError('Motor GPIO numbers must be distinct')
    return profile

def trusted_url(url):
    parsed = urllib.parse.urlsplit(url)
    return (parsed.scheme == 'https' and not parsed.username and not parsed.password and
            ((parsed.hostname == 'github.com' and parsed.path.startswith('/xlle-er/LOOI-DF26-Firmware/releases/')) or
             parsed.hostname in ('release-assets.githubusercontent.com', 'objects.githubusercontent.com')))

class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not trusted_url(newurl):
            raise DeployError('Untrusted firmware redirect')
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def download(url, limit):
    if not trusted_url(url):
        raise DeployError('Only official firmware release URLs are allowed')
    req = urllib.request.Request(url, headers={'User-Agent': 'looi-deploy/0.1'})
    with urllib.request.build_opener(SafeRedirect, urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=certifi.where()))).open(req, timeout=30) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise DeployError('Release asset exceeds size limit')
    return data

def sha256(data):
    return hashlib.sha256(data).hexdigest()

def check_manifest(manifest, board):
    spec = BOARDS[board]
    for key in ('board', 'chip', 'flash_mb', 'psram', 'psram_mb', 'partition', 'hardware_protocol'):
        if manifest.get(key) != spec[key]:
            raise DeployError('Incompatible release manifest: ' + key)
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?', manifest.get('version', '')):
        raise DeployError('Invalid release version')
    builds = manifest.get('builds', [])
    if len(builds) != 1 or builds[0].get('chipFamily') != 'ESP32-S3':
        raise DeployError('Invalid USB manifest')
    parts = builds[0].get('parts', [])
    if len(parts) != 4 or {p.get('offset') for p in parts} != {0, 0x8000, 0xe000, 0x10000}:
        raise DeployError('Unexpected USB flash layout')
    for part in parts:
        if type(part.get('size')) is not int or not 0 < part['size'] <= MAX_APP:
            raise DeployError('Invalid USB segment size')
        if not re.fullmatch('[a-f0-9]{64}', part.get('sha256', '')) or not trusted_url(part.get('url', '')):
            raise DeployError('Invalid USB segment metadata')
    ordered = sorted(parts, key=lambda p: p['offset'])
    if any(a['offset'] + a['size'] > b['offset'] for a, b in zip(ordered, ordered[1:])):
        raise DeployError('Overlapping USB segments')
    if next(p['sha256'] for p in parts if p['offset'] == 0x8000) != manifest.get('partition_sha256'):
        raise DeployError('Partition digest mismatch')
    app = next(p for p in parts if p['offset'] == 0x10000)
    if app['size'] != manifest.get('size') or app['sha256'] != manifest.get('sha256'):
        raise DeployError('Application metadata mismatch')
    return parts

def load_release(board, local_dir=None, release="latest"):
    prefix = 'looi-s3' if board == 'n16r8' else 'looi-s3-n8r8'
    if release != 'latest' and not re.fullmatch(r'v?\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?', release):
        raise DeployError('Use latest or an explicit release tag such as v2.1.0')
    release_path = 'latest/download/' if release == 'latest' else 'download/' + ('v' + release.removeprefix('v')) + '/'
    manifest = json.loads((Path(local_dir) / (prefix + '-usb.json')).read_text() if local_dir else
                          download(RELEASE + release_path + prefix + '-usb.json', 65536))
    if release != "latest" and manifest.get("version") != release.removeprefix("v"):
        raise DeployError("Release tag and manifest version differ")
    parts = check_manifest(manifest, board)
    images = []
    for part in parts:
        if local_dir:
            name = part.get('path', '')
            if Path(name).name != name or not name:
                raise DeployError('Unsafe asset filename')
            data = (Path(local_dir) / name).read_bytes()
        else:
            data = download(part['url'], part['size'])
        if len(data) != part['size'] or sha256(data) != part['sha256']:
            raise DeployError('Incomplete or corrupt firmware asset')
        images.append((part['offset'], data))
    marker = f"LOOI_HW_V1|{board}|1|{BOARDS[board]['partition']}|END".encode()
    if marker not in next(data for offset, data in images if offset == 0x10000):
        raise DeployError('Application hardware descriptor missing')
    return manifest, images

def serial_request(port, request, timeout=6):
    import serial
    request = {**request, 'id': str(uuid.uuid4())}
    # Do not pulse DTR/RTS when reading an already running application.
    link = serial.Serial(port=None, baudrate=115200, timeout=0.2)
    link.dtr = False
    link.rts = False
    link.port = port
    link.open()
    try:
        link.reset_input_buffer()
        link.write((json.dumps(request, separators=(',', ':')) + '\n').encode())
        link.flush()
        deadline = time.monotonic() + timeout
        pending = b''
        while time.monotonic() < deadline:
            pending += link.read(256)
            if len(pending) > 16384:
                pending = b''
            while b'\n' in pending:
                line, pending = pending.split(b'\n', 1)
                try:
                    result = json.loads(line)
                except (ValueError, UnicodeDecodeError):
                    continue
                if not isinstance(result, dict) or result.get('id') != request['id']:
                    continue
                if result.get('accepted') is False or result.get('type') == 'error':
                    raise DeployError(result.get('message', 'Device rejected operation'), 5)
                return result
        raise DeployError('No matching USB reply. Check cable, port, firmware, BOOT/RST and serial monitor ownership.', 4)
    finally:
        link.close()

def esptool(port, args):
    completed = subprocess.run([sys.executable, '-m', 'esptool', '--chip', 'esp32s3', '--port', port,
                                '--baud', '460800', *args], capture_output=True, text=True)
    if completed.returncode:
        raise DeployError('USB ROM operation failed. Close serial monitors; check USB cable, permissions and BOOT/RST.\n' +
                          (completed.stdout + completed.stderr)[-2000:], 4)
    return completed.stdout

def inspect_rom(port, temp):
    output = esptool(port, ['flash-id'])
    found = re.search(r'Detected flash size:\s*(\d+)\s*MB', output, re.I)
    if not found:
        raise DeployError('Could not determine physical Flash capacity; refusing to write', 4)
    path = Path(temp) / 'partition.bin'
    esptool(port, ['read-flash', '0x8000', '0x1000', str(path)])
    return int(found[1]), path.read_bytes()

def profile_from_args(args, existing=None):
    if args.profile:
        return validate_profile(json.loads(Path(args.profile).read_text()))
    if args.use_default_pins:
        return validate_profile({'version': 1, 'board': args.board, 'pins': BOARDS[args.board]['default_pins']})
    if existing and existing.get('hardware_configured'):
        return validate_profile(existing['hardware_profile'])
    raise DeployError('Choose --use-default-pins or --profile FILE after confirming actual wiring')

def verify_state(state, board, profile=None, version=None):
    if state.get('hardware_profile', {}).get('board') != board:
        raise DeployError('Device board profile mismatch', 5)
    if (state.get('flash_mb') != BOARDS[board]['flash_mb'] or
            state.get('physical_flash_bytes') != BOARDS[board]['flash_mb'] * 1024 * 1024 or
            state.get('psram_bytes') != 8 * 1024 * 1024):
        raise DeployError('Physical Flash/PSRAM does not match selected module', 5)
    if not state.get('hardware_ready'):
        raise DeployError(state.get('hardware_error') or 'Motor hardware not ready', 5)
    if profile and state.get('hardware_profile') != profile:
        raise DeployError('Hardware readback mismatch', 5)
    if version and state.get('firmware_version') != version:
        raise DeployError('Firmware version readback mismatch', 5)
    return state

def wait_for_device(port, timeout=25):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            return serial_request(port, {'type': 'hardware_get'}, timeout=2)
        except (DeployError, OSError):
            time.sleep(0.5)
    raise DeployError('Device did not reconnect. Run inspect with its new port; native USB may enumerate again.', 4)

def record(state):
    dest = Path('.looi-deploy'); dest.mkdir(exist_ok=True)
    device = state.get('device_id', '')
    if not re.fullmatch(r'looi-[a-fA-F0-9]{12}', device):
        raise DeployError('Invalid device identity', 5)
    data = {k: state[k] for k in ('device_id', 'firmware_version', 'hardware_profile', 'hardware_ready')}
    data['verified_at_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    path = dest / (device + '.json')
    path.write_text(json.dumps(data, indent=2) + '\n')
    return str(path.resolve())

def run(args):
    import serial.tools.list_ports
    if args.command == 'doctor':
        return {'platform': sys.platform, 'python': sys.version.split()[0],
                'esptool': importlib.metadata.version('esptool'),
                'ports': [{'port': p.device, 'description': p.description} for p in serial.tools.list_ports.comports()],
                'help': 'Windows: close serial monitor/install board USB bridge driver if needed. Linux: obtain serial group permission, then log in again. macOS: use /dev/cu.* and close Arduino serial monitor.'}
    if not args.port:
        raise DeployError('Explicit --port required; run doctor to list devices')
    if args.command == 'inspect':
        try:
            return serial_request(args.port, {'type': 'hardware_get'})
        except DeployError as error:
            if error.code == 5:
                raise
            with tempfile.TemporaryDirectory() as temp:
                flash, partition = inspect_rom(args.port, temp)
            return {'chip': 'ESP32-S3', 'flash_mb': flash, 'partition_sha256': sha256(partition),
                    'blank_partition': all(v == 255 for v in partition), 'hardware_profile': None,
                    'note': 'PSRAM/module marking and old custom wiring require user confirmation'}
    if args.command == 'verify':
        profile = validate_profile(json.loads(Path(args.profile).read_text())) if args.profile else None
        state = verify_state(serial_request(args.port, {'type': 'hardware_get'}), args.board, profile, args.version)
        return {'verified': True, 'record': record(state), 'device': state}
    if args.command == 'install':
        manifest, images = load_release(args.board, args.assets, getattr(args, "release", "latest"))
        try:
            existing = serial_request(args.port, {'type': 'hardware_get'}, timeout=2)
        except DeployError as error:
            if error.code == 5:
                raise
            existing = None
        profile = profile_from_args(args, existing)
        if profile['board'] != args.board:
            raise DeployError('Selected profile and installation board differ')
        with tempfile.TemporaryDirectory() as temp:
            flash, current_partition = inspect_rom(args.port, temp)
            expected = next(data for offset, data in images if offset == 0x8000)
            if flash != BOARDS[args.board]['flash_mb']:
                raise DeployError('Physical Flash capacity differs from selected board')
            if current_partition[:len(expected)] != expected and not all(v == 255 for v in current_partition):
                raise DeployError('Unknown partition layout; nothing written. Preserve NVS and inspect before manual migration.')
            write_args = ['write-flash', '--flash-mode', 'keep', '--flash-size', 'keep']
            for offset, data in images:
                path = Path(temp) / f'{offset:x}.bin';path.write_bytes(data)
                write_args += [hex(offset), str(path)]
            esptool(args.port, write_args)
        state = wait_for_device(args.port)
        if state.get('firmware_version') != manifest['version']:
            raise DeployError('Installed version readback mismatch', 5)
    else:
        state = serial_request(args.port, {'type': 'hardware_get'})
        profile = profile_from_args(args, state)
        if profile['board'] != args.board:
            raise DeployError('Selected profile and configuration board differ')
    password = sys.stdin.readline().rstrip('\r\n') if args.password_stdin else getpass.getpass('Device admin password (initial: 12345678): ')
    serial_request(args.port, {'type': 'hardware_set', 'hardware_profile': profile, 'admin_password': password})
    time.sleep(2)
    state = verify_state(wait_for_device(args.port), args.board, profile,
                         manifest['version'] if args.command == 'install' else None)
    return {'verified': True, 'record': record(state), 'device': state}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', action='store_true', help='JSON stdout; no passwords are returned')
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ('doctor', 'inspect', 'install', 'configure', 'verify'):
        p = sub.add_parser(command)
        if command != 'doctor': p.add_argument('--port')
        if command in ('install', 'configure', 'verify'):
            p.add_argument('--board', choices=BOARDS, required=True)
            p.add_argument('--profile', help='JSON hardware profile file')
        if command in ('install', 'configure'):
            p.add_argument('--use-default-pins', action='store_true')
            p.add_argument('--password-stdin', action='store_true', help='Read admin password from stdin, not argv')
        if command == 'install':
            p.add_argument('--assets', help='Use locally prepared release directory')
            p.add_argument('--release', default='latest', help='Stable latest or explicit tag, e.g. v2.1.0 for a prerelease')
        if command == 'verify': p.add_argument('--version')
    args = parser.parse_args()
    try:
        result = run(args)
        print(json.dumps({'ok': True, **result}, ensure_ascii=False, indent=2))
    except Exception as error:
        code = error.code if isinstance(error, DeployError) else 3
        # Avoid echoing requests or secrets; transport errors contain only operation context.
        print(json.dumps({'ok': False, 'error': str(error), 'exit_code': code}, ensure_ascii=False))
        raise SystemExit(code)

if __name__ == '__main__':
    main()
