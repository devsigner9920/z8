#!/usr/bin/env python3
"""Build verified debug APKs or unsigned release AAB candidates from pinned inputs."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bundletool
import release_config
import native_alignment
import signing_identity

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / '.local'


def run(argv, **kwargs):
    return subprocess.run([str(arg) for arg in argv], check=True, **kwargs)


def capture(argv, **kwargs):
    return subprocess.check_output([str(arg) for arg in argv], text=True, **kwargs)


def manifest_facts(badging):
    def field(pattern):
        found = re.search(pattern, badging, re.MULTILINE)
        if not found:
            raise ValueError('Missing APK manifest field: ' + pattern)
        return found.group(1)
    return {
        'applicationId': field(r"^package: name='([^']+)'"),
        'versionCode': int(field(r"^package: .*?versionCode='(\d+)'")),
        'versionName': field(r"^package: .*?versionName='([^']+)'"),
        'minSdk': int(field(r"^sdkVersion:'(\d+)'")),
        'targetSdk': int(field(r"^targetSdkVersion:'(\d+)'")),
        'compileSdk': int(field(r"^package: .*?compileSdkVersion='(\d+)'")),
        'debuggable': 'application-debuggable' in badging.splitlines(),
        'abis': re.findall(r"'([^']+)'", field(r'^native-code: (.+)$')),
    }


def validate_facts(facts, config, debug):
    expected = {'applicationId': 'dev.devsigner.z8', 'versionCode': config['versionCode'],
                'versionName': config['versionName'], 'minSdk': release_config.MIN_SDK,
                'targetSdk': release_config.TARGET_SDK, 'compileSdk': release_config.COMPILE_SDK,
                'debuggable': debug, 'abis': ['arm64-v8a']}
    if facts != expected:
        raise ValueError('Final APK differs from requested identity/SDK/build type: ' + json.dumps(facts))


def main():
    if sys.version_info < (3, 12):
        sys.exit('Python 3.12 or newer is required.')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['diagnostic', 'runtime'], default='diagnostic')
    parser.add_argument('--runtime-manifest', type=Path)
    parser.add_argument('--guest-manifest', type=Path, help='Optional verified project Linux image to embed')
    parser.add_argument('--variant', choices=['debug', 'candidate'], default='debug',
                        help='candidate builds an unsigned, non-debuggable release AAB and a local-test APK')
    parser.add_argument('--release-config', type=Path, default=ROOT / 'release/config.json')
    args = parser.parse_args()
    if (args.mode == 'runtime') != bool(args.runtime_manifest):
        parser.error('runtime mode requires --runtime-manifest; diagnostic mode must not supply it')
    config = release_config.load(args.release_config)
    lock = json.loads((ROOT / 'tools/sources.lock.json').read_text())
    env = os.environ.copy()
    # Only promote-release.py may use an upload key. Ambient variables cannot sign a candidate.
    env.pop('Z8_RELEASE_BUILD', None)
    jdk = Path(env.get('JAVA_HOME', LOCAL / 'jdk/Contents/Home'))
    sdk = Path(env.get('ANDROID_HOME', LOCAL / 'android-sdk'))
    if not (jdk / 'bin/java').is_file() or not (sdk / 'platform-tools/adb').is_file():
        sys.exit('Build tools missing. Run tools/setup-toolchain.py or set JAVA_HOME and ANDROID_HOME.')
    git = env.get('Z8_GIT') or shutil.which('git')
    if not git:
        sys.exit('git is required. Set Z8_GIT to a working Git executable.')
    run([git, '--version'])
    source = ROOT / 'upstream/termux-app'
    if not source.exists():
        source.parent.mkdir(exist_ok=True)
        run([git, 'init', source])
        run([git, '-C', source, 'remote', 'add', 'origin', lock['termuxApp']['url']])
        run([git, '-C', source, 'fetch', '--depth=1', 'origin', lock['termuxApp']['commit']])
        run([git, '-C', source, 'checkout', '--detach', 'FETCH_HEAD'])
    actual = subprocess.check_output([git, '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if actual != lock['termuxApp']['commit']:
        sys.exit('Upstream HEAD does not match tools/sources.lock.json; checkout the pinned source explicitly.')
    if subprocess.check_output([git, '-C', str(source), 'status', '--porcelain'], text=True).strip():
        sys.exit('Upstream has local modifications. Preserve them before building; patches belong in overlay/preparer.')
    keys = LOCAL / 'keys'
    keys.mkdir(parents=True, exist_ok=True, mode=0o700)
    keystore = Path(env.get('Z8_KEYSTORE', keys / 'z8-debug.jks')).resolve()
    if not keystore.exists():
        run([jdk / 'bin/keytool', '-genkeypair', '-keystore', keystore, '-storepass', 'android',
             '-keypass', 'android', '-alias', 'z8-debug', '-keyalg', 'RSA', '-keysize', '3072',
             '-validity', '3650', '-dname', 'CN=z8 Local Development, OU=Development, O=z8, C=KR'])
        keystore.chmod(0o600)
    env.update(JAVA_HOME=str(jdk), ANDROID_HOME=str(sdk), ANDROID_SDK_ROOT=str(sdk),
               ANDROID_USER_HOME=str(LOCAL / 'android-user'),
               GRADLE_USER_HOME=str(LOCAL / 'gradle'), Z8_KEYSTORE=str(keystore), Z8_GIT=git)
    env['PATH'] = str(jdk / 'bin') + os.pathsep + str(sdk / 'platform-tools') + os.pathsep + env.get('PATH', '')
    output_name = 'build-src' if args.variant == 'debug' else 'build-candidate'
    prepare = [sys.executable, ROOT / 'tools/prepare-app.py', '--mode', args.mode,
               '--variant', args.variant, '--release-config', args.release_config.resolve(), '--output-name', output_name]
    if args.runtime_manifest:
        prepare += ['--runtime-manifest', args.runtime_manifest.resolve()]
    if args.guest_manifest:
        prepare += ['--guest-manifest', args.guest_manifest.resolve()]
    run(prepare, env=env)
    build = LOCAL / output_name
    (build / 'local.properties').write_text('sdk.dir=' + str(sdk).replace('\\', '\\\\') + '\n')
    gradle = ['sh', './gradlew', '--no-daemon', '--console=plain', '--max-workers=4']
    work = LOCAL / ('verify-' + args.variant + '-' + args.mode)
    work.mkdir(parents=True, exist_ok=True)
    inventory = work / 'dependencies.json'
    init = ROOT / 'tools/release-license.init.gradle'
    tasks = [':app:assembleDebug' if args.variant == 'debug' else ':app:bundleRelease',
             ':terminal-emulator:testDebugUnitTest']
    if init.is_file() and args.variant == 'candidate':
        gradle += ['--init-script', init, '-Pz8ComplianceOutput=' + str(inventory)]
        tasks.append(':app:z8ReleaseArtifacts')
    run(gradle + tasks, cwd=build, env=env)
    artifacts = ROOT / 'artifacts'
    artifacts.mkdir(exist_ok=True)
    stem = ('z8-g0-' if args.variant == 'debug' else 'z8-candidate-') + args.mode + '-arm64'
    apk = artifacts / (stem + '.apk')
    bundle = None
    if args.variant == 'debug':
        apks = list((build / 'app/build/outputs/apk/debug').glob('*.apk'))
        if len(apks) != 1:
            raise ValueError('Expected exactly one ARM64 debug APK')
        candidate = apks[0]
    else:
        bundles = list((build / 'app/build/outputs/bundle/release').glob('*.aab'))
        if len(bundles) != 1:
            raise ValueError('Expected exactly one release AAB')
        bundle = bundles[0]
        with zipfile.ZipFile(bundle) as archive:
            if any(name.startswith('META-INF/') and name.upper().endswith(('.RSA', '.DSA', '.EC', '.SF'))
                   for name in archive.namelist()):
                raise ValueError('Candidate AAB unexpectedly contains a signing identity')
        java = [jdk / 'bin/java', '-jar', bundletool.ensure(ROOT)]
        run(java + ['validate', '--bundle=' + str(bundle)], env=env)
        dumped = capture(java + ['dump', 'manifest', '--bundle=' + str(bundle), '--module=base'], env=env)
        document = ET.fromstring(dumped)
        android = '{http://schemas.android.com/apk/res/android}'
        if document.find('application').get(android + 'debuggable', 'false') != 'false':
            raise ValueError('Release AAB is debuggable')
        if int(document.find('uses-sdk').get(android + 'targetSdkVersion')) != release_config.TARGET_SDK:
            raise ValueError('Release AAB has the wrong target SDK')
        (work / 'bundle-manifest.xml').write_text(dumped)
        (work / 'bundle-config.json').write_text(capture(java + ['dump', 'config', '--bundle=' + str(bundle)], env=env))
        apks = work / 'candidate.apks'
        run(java + ['build-apks', '--bundle=' + str(bundle), '--output=' + str(apks), '--overwrite', '--mode=universal',
                    '--ks=' + str(keystore), '--ks-key-alias=z8-debug', '--ks-pass=pass:android', '--key-pass=pass:android'], env=env)
        candidate = work / 'universal.apk'
        with zipfile.ZipFile(apks) as archive:
            candidate.write_bytes(archive.read('universal.apk'))
    build_tools = sdk / 'build-tools/36.0.0'
    signature = subprocess.check_output([str(build_tools / 'apksigner'), 'verify', '--verbose', '--print-certs', str(candidate)], env=env, text=True)
    test_certificate = signing_identity.certificate_sha256(signature)
    badging = subprocess.check_output([str(build_tools / 'aapt'), 'dump', 'badging', str(candidate)], env=env, text=True)
    facts = manifest_facts(badging)
    validate_facts(facts, config, args.variant == 'debug')
    run([build_tools / 'zipalign', '-c', '-P', '16', '4', candidate], env=env)
    native_libraries = native_alignment.inspect_apk(candidate, runtime=args.mode == 'runtime')
    test_summary = {'tests': 0, 'failures': 0, 'errors': 0, 'skipped': 0}
    for report in (build / 'terminal-emulator/build/test-results/testDebugUnitTest').glob('TEST-*.xml'):
        suite = ET.parse(report).getroot()
        for key in test_summary:
            test_summary[key] += int(suite.attrib.get(key, 0))
    if not test_summary['tests'] or test_summary['failures'] or test_summary['errors']:
        raise ValueError('Terminal tests did not complete successfully')
    record = {
        'schemaVersion': 2, 'builtAtUtc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'mode': args.mode, 'variant': args.variant, **facts, 'upstreamCommit': actual,
        'apk': apk.name, 'sha256': hashlib.file_digest(candidate.open('rb'), 'sha256').hexdigest(),
        'sizeBytes': candidate.stat().st_size, 'bootstrapIncluded': args.mode == 'runtime',
        'guestImageIncluded': bool(args.guest_manifest),
        'guestImageSha256': json.loads((build / 'app/src/main/assets/z8/guest/manifest.json').read_text())['archiveSha256'] if args.guest_manifest else None,
        'terminalEmulatorUnitTests': test_summary, 'deviceGateStatus': 'NOT_TESTED',
        'abi': 'arm64-v8a', 'uploadReady': False,
        'releaseConfigSha256': hashlib.file_digest(args.release_config.open('rb'), 'sha256').hexdigest(),
        'testSigningCertificateSha256': test_certificate,
        'publicMetadataMissing': release_config.missing_public_fields(config),
        'zipalign16KiB': 'PASS',
        'nativeElf16KiB': {'status': 'PASS', 'libraries': native_libraries},
        'runtimeManifestSha256': hashlib.file_digest(args.runtime_manifest.open('rb'), 'sha256').hexdigest() if args.runtime_manifest else None,
    }
    if bundle:
        record.update(aab=stem + '.aab', aabSha256=hashlib.file_digest(bundle.open('rb'), 'sha256').hexdigest(),
                      bundleValidated=True, aabSigning='unsigned', apkSigning='development-key-for-local-verification')
    # Do not overwrite the previous successful artifact if verification failed.
    with tempfile.TemporaryDirectory(prefix='.verified-', dir=artifacts) as directory:
        staging = Path(directory)
        shutil.copy2(candidate, staging / apk.name)
        if bundle:
            shutil.copy2(bundle, staging / (stem + '.aab'))
            for name in ('bundle-manifest.xml', 'bundle-config.json', 'dependencies.json'):
                if (work / name).is_file():
                    shutil.copy2(work / name, staging / (stem + '-' + name))
        (staging / (apk.stem + '-signature.txt')).write_text(signature)
        (staging / (apk.stem + '-manifest.txt')).write_text(badging)
        metadata = staging / (apk.stem + '.json')
        metadata.write_text(json.dumps(record, indent=2) + '\n')
        for item in staging.iterdir():
            if item != metadata:
                item.replace(artifacts / item.name)
        metadata.replace(artifacts / metadata.name)
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as failure:
        sys.exit('build-app: ' + str(failure))
