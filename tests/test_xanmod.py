#!/usr/bin/env python3
"""Offline integration tests: real Bash + upstream installer, no real installs."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

PARSER = argparse.ArgumentParser()
PARSER.add_argument('--installer', type=Path, required=True)
PARSER.add_argument('--bash', default=shutil.which('bash'))
ARGS, REST = PARSER.parse_known_args()
INSTALLER = ARGS.installer.resolve()
BASH = ARGS.bash
ROOT = Path(__file__).resolve().parents[1]
V2 = 'lm fpu cx8 cmov mmx fxsr sse sse2 cx16 lahf_lm popcnt pni ssse3 sse4_1 sse4_2'
V3 = V2 + ' avx avx2 bmi1 bmi2 f16c fma movbe xsave abm'


def cpu(vendor='GenuineIntel', flags=V3, index=0):
    return f'processor : {index}\nvendor_id : {vendor}\nflags : {flags}\n\n'


def release(version, profile='v3-intel', rid=1, kinds=('image', 'headers'), **kw):
    tail = f'{version}-x64{profile.split("-")[0]}-cloud-{profile}-xanmod1_1_amd64.deb'
    return dict(id=rid, tag_name=f'xanmod-cloud-{version}-{profile}-{rid}',
                published_at=f'2026-11-{rid % 28 + 1:02}T00:00:00Z',
                assets=[dict(name=f'linux-{kind}-{tail}',
                             browser_download_url=f'https://fixtures.invalid/{rid}/linux-{kind}-{tail}')
                        for kind in kinds], **kw)


BOOTSTRAP = r'''
import io, json, os, sys, urllib.request
from urllib.parse import parse_qs, urlsplit
# Match Linux Python output even when this harness runs on Windows.
sys.stdout.reconfigure(newline='\n')
sys.stderr.reconfigure(newline='\n')

def urlopen(req, timeout=None):
    url = req.full_url
    with open(os.environ['TRACE'], 'a', encoding='utf-8') as f:
        f.write('api ' + url + '\n')
    if os.environ.get('API_ERROR') == '1':
        raise OSError('simulated API outage')
    if not url.startswith('https://api.github.com/repos/avsba001/kernel-build/releases?'):
        raise AssertionError('Unexpected network request: ' + url)
    page = int(parse_qs(urlsplit(url).query)['page'][0])
    with open(os.environ['FAKE_RELEASES'], encoding='utf-8') as f:
        data = json.load(f)
    return io.BytesIO(json.dumps(data[(page-1)*100:page*100]).encode())
urllib.request.urlopen = urlopen
if sys.argv[1] != '-':
    raise AssertionError('Only embedded installer Python is permitted')
sys.argv = sys.argv[1:]
exec(compile(sys.stdin.read(), '<upstream-installer>', 'exec'), {'__name__': '__main__'})
'''

CURL = r'''#!/usr/bin/env bash
set -eu
printf 'curl %s\n' "$*" >> "$TRACE"
output=''
while (( $# )); do
  case "$1" in
    -o) output="$2"; shift 2 ;;
    *) url="$1"; shift ;;
  esac
done
if [[ "$url" == https://raw.githubusercontent.com/avsba001/kernel-build/main/install.sh ]]; then
  case "${DOWNLOAD_MODE:-ok}" in
    fail) printf 'echo must-not-run\n' > "$output"; exit 22 ;;
    empty) : > "$output" ;;
    invalid) printf 'if then\n' > "$output" ;;
    exit37) printf 'exit 37\n' > "$output" ;;
    args) printf 'printf "args:%%s\\n" "$@"\n' > "$output" ;;
    *) cp "$TEST_INSTALLER" "$output" ;;
  esac
elif [[ "$url" == https://fixtures.invalid/* ]]; then
  [[ "${ASSET_ERROR:-0}" != 1 ]] || exit 22
  printf 'fake deb; must never reach real dpkg\n' > "$output"
else
  echo "Unexpected curl URL: $url" >&2
  exit 99
fi
'''
DPKG = r'''#!/usr/bin/env bash
set -eu
if [[ "${1:-}" == --print-architecture ]]; then
  echo "${FAKE_ARCH:-amd64}"
else
  printf 'dpkg %s\n' "$*" >> "$TRACE"
  exit "${DPKG_STATUS:-0}"
fi
'''


class XanmodTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='xanmod-test-')
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.bin = self.base / 'bin'
        self.bin.mkdir()
        (self.base / 'tmp').mkdir()
        (self.base / 'bootstrap.py').write_text(BOOTSTRAP, encoding='utf-8')
        self.env = os.environ.copy()
        self.env.update(PATH=str(self.bin) + os.pathsep + os.environ['PATH'],
                        TEST_PYTHON=Path(sys.executable).as_posix(),
                        TEST_BOOTSTRAP=(self.base / 'bootstrap.py').as_posix(),
                        TEST_INSTALLER=INSTALLER.as_posix(), TEST_BIN=self.bin.as_posix(),
                        TRACE=(self.base / 'trace').as_posix(),
                        CPU_INFO=(self.base / 'cpuinfo').as_posix(),
                        FAKE_RELEASES=(self.base / 'releases.json').as_posix(),
                        TMPDIR=(self.base / 'tmp').as_posix(),
                        PYTHONUTF8='1', MSYS_NO_PATHCONV='1')
        self.stub('python3', '#!/usr/bin/env bash\nexec "$TEST_PYTHON" "$TEST_BOOTSTRAP" "$@"\n')
        self.stub('curl', CURL)
        self.stub('dpkg', DPKG)
        self.stub('uname', '#!/usr/bin/env bash\ncase "$1" in -s) echo "${FAKE_OS:-Linux}";; -m) echo "${FAKE_MACHINE:-x86_64}";; *) exit 99;; esac\n')
        self.stub('sudo', '#!/usr/bin/env bash\nif [[ "$1" == -v ]]; then exit 0; fi\n[[ "$1" == dpkg ]] || exit 99\nexec dpkg "${@:2}"\n')
        for cmd in ('reboot', 'shutdown', 'systemctl', 'apt', 'apt-get'):
            self.stub(cmd, '#!/usr/bin/env bash\nprintf "FORBIDDEN\\n" >> "$TRACE"\nexit 99\n')
        # Fail closed before running the installer if a shell launcher resets PATH.
        check = subprocess.run([BASH, '-c',
            'for cmd in curl dpkg uname sudo python3 reboot shutdown systemctl apt apt-get; do '
            '[[ "$(command -v "$cmd")" -ef "$TEST_BIN/$cmd" ]] || exit 99; done'],
            env=self.env, capture_output=True, timeout=10)
        self.assertEqual(check.returncode, 0, 'Mock PATH validation failed; refusing to run installer')

    def stub(self, name, text):
        path = self.bin / name
        path.write_text(text, encoding='utf-8', newline='\n')
        path.chmod(0o755)

    def run_case(self, releases=None, info=None, stdin='latest\nn\n', **env):
        (self.base / 'cpuinfo').write_text(info if info is not None else cpu(), encoding='utf-8')
        (self.base / 'releases.json').write_text(json.dumps(releases if releases is not None else [release('7.3.1')]), encoding='utf-8')
        (self.base / 'trace').write_text('', encoding='utf-8')
        # Binary stdin avoids Windows translating LF to CRLF in Bash prompts.
        result = subprocess.run([BASH, (ROOT / 'xanmod.sh').as_posix()], input=stdin.encode('utf-8'),
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                env=dict(self.env, **env), timeout=20)
        result.stdout = result.stdout.decode('utf-8', errors='replace')
        trace = (self.base / 'trace').read_text(encoding='utf-8')
        self.assertNotIn('FORBIDDEN', trace)
        self.assertEqual(list((self.base / 'tmp').iterdir()), [], result.stdout)
        return result, trace

    def assert_cancelled(self, r, trace, version, profile):
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn(f'XanMod {version} ({profile})', r.stdout)
        self.assertIn('已取消', r.stdout)
        self.assertNotIn('dpkg -i', trace)
        self.assertNotIn('curl -fL --retry 5 --retry-delay 2 --retry-all-errors -o linux-', trace)

    def test_cpu_and_series_matrix(self):
        for vendor, name in [('GenuineIntel', 'intel'), ('AuthenticAMD', 'amd')]:
            for flags, level in [(V2, 'v2'), (V3, 'v3')]:
                for series, expected in [('6.12', '6.12.99'), ('6.18', '6.18.25'), ('7.3', '7.3.1'), ('latest', '7.3.1')]:
                    with self.subTest(profile=f'{level}-{name}', series=series):
                        releases = [release(v, f'{l}-{n}', i + 1)
                                    for i, (v, l, n) in enumerate((v, l, n) for v in ['6.12.99', '6.18.25', '7.3.1'] for l in ['v2', 'v3'] for n in ['intel', 'amd'])]
                        r, trace = self.run_case(releases, cpu(vendor, flags), f'{series}\nn\n')
                        self.assert_cancelled(r, trace, expected, f'{level}-{name}')

    def test_published_731_release_metadata(self):
        # Reduced public GitHub API snapshot, fetched 2026-11-08; no network in test.
        releases = json.loads((ROOT / 'tests/fixtures/release-7.3-v3-intel.json').read_text(encoding='utf-8'))
        r, t = self.run_case(releases, stdin='7.3\nn\n')
        self.assert_cancelled(r, t, '7.3.1', 'v3-intel')
        self.assertIn('7.3.1-gc26b507b7580-1_amd64.deb', r.stdout)
        self.assertNotIn('config-7.3', r.stdout)

    def test_missing_curl_dependency(self):
        env = dict(self.env, PATH='')
        r = subprocess.run([BASH, (ROOT / 'xanmod.sh').as_posix()],
                           capture_output=True, env=env, timeout=10)
        self.assertEqual(r.returncode, 1)
        self.assertIn('curl', r.stderr.decode('utf-8'))
        self.assertEqual(list((self.base / 'tmp').iterdir()), [])

    def test_same_version_uses_newest_complete_release(self):
        r, t = self.run_case([release('7.3.1', rid=2), release('7.3.1', rid=9),
                             release('7.3.1', rid=15, kinds=('image',))], stdin='7.3\ny\n')
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn('https://fixtures.invalid/9/', t)
        self.assertNotIn('https://fixtures.invalid/2/', t)
        self.assertNotIn('https://fixtures.invalid/15/', t)

    def test_numeric_version_before_publication_date(self):
        r, t = self.run_case([release('7.3.9', rid=27), release('7.3.10', rid=1)])
        self.assert_cancelled(r, t, '7.3.10', 'v3-intel')

    def test_newest_complete_fallback(self):
        r, t = self.run_case([release('7.3.2', kinds=('image',)), release('7.3.1', rid=2)])
        self.assert_cancelled(r, t, '7.3.1', 'v3-intel')

    def test_no_cross_release_or_package_revision_pairing(self):
        a = release('7.3.1', kinds=('image',))
        b = release('7.3.1', rid=2, kinds=('headers',))
        for releases in ([a, b], [release('7.3.1', kinds=('headers',))], [a]):
            with self.subTest(releases=releases):
                r, t = self.run_case(releases)
                self.assertNotEqual(r.returncode, 0, r.stdout)
                self.assertNotIn('dpkg -i', t)
        a = release('7.3.1')
        a['assets'][1]['name'] = a['assets'][1]['name'].replace('_1_', '_2_')
        r, t = self.run_case([a])
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn('dpkg -i', t)

    def test_draft_prerelease_and_wrong_profile_filtered(self):
        assets = [release('7.3.1'), release('7.3.2', rid=2, draft=True),
                  release('7.3.3', rid=3, prerelease=True), release('7.3.4', 'v3-amd', rid=4)]
        bad = release('7.3.5', rid=5)
        for a in bad['assets']:
            a['name'] = a['name'].replace('x64v3', 'x64v2')
        assets.append(bad)
        wrong_vendor = release('7.3.6', rid=6)
        for a in wrong_vendor['assets']:
            a['name'] = a['name'].replace('cloud-v3-intel', 'cloud-v3-amd')
        assets.append(wrong_vendor)
        r, t = self.run_case(assets)
        self.assert_cancelled(r, t, '7.3.1', 'v3-intel')

    def test_all_core_intersection_and_lzcnt_alias(self):
        r, t = self.run_case([release('7.3.1', 'v2-intel')], cpu() + cpu(flags=V2, index=1))
        self.assert_cancelled(r, t, '7.3.1', 'v2-intel')
        r, t = self.run_case(info=cpu(flags=V3.replace('abm', 'lzcnt')))
        self.assert_cancelled(r, t, '7.3.1', 'v3-intel')
        r, t = self.run_case([release('7.3.1', 'v2-intel')], cpu(flags=V3.replace(' abm', '')))
        self.assert_cancelled(r, t, '7.3.1', 'v2-intel')

    def test_unsupported_or_incomplete_cpu(self):
        for info in [cpu(flags='lm sse2'), cpu('UnknownVendor'), '',
                     cpu() + cpu('AuthenticAMD', index=1), 'processor : 0\nvendor_id : GenuineIntel\n']:
            with self.subTest(info=info):
                r, t = self.run_case(info=info)
                self.assertNotEqual(r.returncode, 0)
                self.assertNotIn('api ', t)
                self.assertNotIn('dpkg -i', t)

    def test_invalid_series_and_empty_catalog(self):
        for series in ['5.15', '6.1', '7.x', '7.3;reboot']:
            with self.subTest(series=series):
                r, t = self.run_case(stdin=series + '\ny\n')
                self.assertNotEqual(r.returncode, 0)
                self.assertNotIn('api ', t)
        r, t = self.run_case([])
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn('dpkg -i', t)

    def test_pagination(self):
        releases = [release('9.9.9', 'v3-amd', rid=i+1) for i in range(100)] + [release('7.3.1', rid=101)]
        r, t = self.run_case(releases)
        self.assert_cancelled(r, t, '7.3.1', 'v3-intel')
        self.assertIn('per_page=100&page=2', t)

    def test_confirmation_default_cancel_and_eof(self):
        for stdin in ['\n\n', '7.3\n', '']:
            with self.subTest(stdin=stdin):
                r, t = self.run_case(stdin=stdin)
                self.assertEqual(r.returncode, 0, r.stdout)
                self.assertNotIn('dpkg -i', t)
                self.assertNotIn('-o linux-', t)

    def test_confirmed_install_uses_only_paired_packages(self):
        r, t = self.run_case(stdin='7.3\ny\n')
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(t.count('curl '), 3, t)
        self.assertEqual(t.count('dpkg -i'), 1, t)
        self.assertIn('linux-image-7.3.1', t)
        self.assertIn('linux-headers-7.3.1', t)
        self.assertNotIn('linux-modules-', t)

    def test_download_and_child_failures_cleanup(self):
        for mode in ['fail', 'empty', 'invalid', 'exit37']:
            with self.subTest(mode=mode):
                r, t = self.run_case(DOWNLOAD_MODE=mode)
                self.assertEqual(r.returncode, 37 if mode == 'exit37' else 1, r.stdout)
                self.assertNotIn('api ', t)
                self.assertNotIn('must-not-run', r.stdout)
        for env in [dict(API_ERROR='1'), dict(ASSET_ERROR='1'), dict(DPKG_STATUS='42')]:
            with self.subTest(env=env):
                r, t = self.run_case(stdin='7.3\ny\n', **env)
                self.assertNotEqual(r.returncode, 0)
                if 'DPKG_STATUS' in env:
                    self.assertEqual(r.returncode, 42, r.stdout)
                else:
                    self.assertNotIn('dpkg -i', t)

    def test_wrong_platform(self):
        for env in [dict(FAKE_OS='Darwin'), dict(FAKE_MACHINE='aarch64'), dict(FAKE_ARCH='arm64')]:
            with self.subTest(env=env):
                r, t = self.run_case(**env)
                self.assertNotEqual(r.returncode, 0)
                self.assertNotIn('api ', t)

    def test_argument_forwarding(self):
        env = dict(self.env, DOWNLOAD_MODE='args')
        r = subprocess.run([BASH, (ROOT / 'xanmod.sh').as_posix(), 'with space', '--test'],
                           text=True, encoding='utf-8', capture_output=True, env=env, timeout=20)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('args:with space\nargs:--test', r.stdout)
        self.assertEqual(list((self.base / 'tmp').iterdir()), [])

    def test_existing_menu_calls_preserved(self):
        menu = (ROOT / 'vps-secure.sh').read_text(encoding='utf-8')
        self.assertEqual(menu.count('run_script_without_backup "xanmod.sh"'), 2)
        self.assertIn('4)\n', menu)
        self.assertNotIn('resolve_release_assets', (ROOT / 'xanmod.sh').read_text(encoding='utf-8'))


if __name__ == '__main__':
    if not BASH or not INSTALLER.is_file():
        PARSER.error('Bash and an existing --installer source file are required')
    print(f'Upstream installer: {INSTALLER}', flush=True)
    unittest.main(argv=[sys.argv[0]] + REST, verbosity=2)
