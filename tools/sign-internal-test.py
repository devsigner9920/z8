#!/usr/bin/env python3
"""Sign a private internal-test copy; never approve, upload or promote a release.

Internal testing is not a policy/license waiver. Production still requires the
unchanged promote-release.py contract, using the original unsigned candidate.
Retained QA may contain private observations: never publish this output folder.
"""
import argparse
import base64
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bundletool
import release_config
import signing_identity

ROOT = Path(__file__).resolve().parents[1]
CHECKS = ('freshInstall', 'updatePreservesProjects', 'projectDeletion', 'runtimeAndChildProcesses',
          'codexAuthenticatedTask', 'claudeAuthenticatedTask', 'physicalDevice', 'pageSize16KiB',
          'previewDataDeletion', 'backAndKeyboard', 'foregroundStopAndNotifications')
CHECK_STATUSES = {'PASS', 'FAIL', 'NOT_TESTED', 'BLOCKED'}
QA_STATUSES = {'PASS', 'PARTIAL', 'INCOMPLETE', 'FAIL', 'BLOCKED'}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def no_redirect(path):
    path = Path(os.path.abspath(path))
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        raise ValueError('Input/output paths cannot contain symlinks')
    return path


def regular(path):
    path = no_redirect(path)
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError('Expected a regular input file')
    return path


def sibling(metadata_path, name, suffix):
    if (not isinstance(name, str) or not name or Path(name).name != name
            or '/' in name or '\\' in name or not name.endswith(suffix)):
        raise ValueError('Candidate artifacts must be beside their metadata')
    return regular(metadata_path.parent / name)


def validate_evidence(metadata, candidate_hash, apk_hash, config_hash, config, compliance, qa):
    if any(not isinstance(value, dict) for value in (metadata, config, compliance, qa)):
        raise ValueError('Evidence must be JSON objects')
    if (metadata.get('variant') != 'candidate' or metadata.get('mode') != 'runtime'
            or metadata.get('debuggable') is not False or metadata.get('uploadReady') is not False
            or metadata.get('targetSdk') != release_config.TARGET_SDK
            or metadata.get('aabSigning') != 'unsigned' or metadata.get('bundleValidated') is not True
            or metadata.get('bootstrapIncluded') is not True or metadata.get('guestImageIncluded') is not True):
        raise ValueError('A complete, validated, unsigned runtime candidate is required')
    if (metadata.get('aabSha256') != candidate_hash or metadata.get('sha256') != apk_hash
            or metadata.get('releaseConfigSha256') != config_hash
            or metadata.get('versionCode') != config['versionCode']
            or metadata.get('versionName') != config['versionName']):
        raise ValueError('Candidate/config/artifact identity differs from the retained evidence')
    inputs = compliance.get('inputs')
    if (compliance.get('kind') != 'z8-release-compliance-verification'
            or compliance.get('status') != 'VERIFIED' or compliance.get('blockers') != []
            or not isinstance(inputs, dict) or inputs.get('artifactSha256') != candidate_hash
            or inputs.get('sourceUrlVerified') != config['sourceUrl']):
        raise ValueError('Exact corresponding-source and public-URL verification is required')
    checks = qa.get('checks')
    unresolved = qa.get('unresolved')
    if (qa.get('kind') != 'z8-release-qa' or not isinstance(qa.get('status'), str)
            or qa['status'] not in QA_STATUSES
            or qa.get('aabSha256') != candidate_hash or qa.get('apkSha256') != apk_hash
            or not isinstance(checks, dict) or not isinstance(unresolved, list)
            or any(not isinstance(item, str) or not item.strip() for item in unresolved)):
        raise ValueError('Actual QA must identify both candidate artifacts and retain unresolved findings')
    if any(name not in checks for name in CHECKS):
        raise ValueError('Every production QA check needs an explicit observed or NOT_TESTED status')
    if any(not isinstance(value, dict) or not isinstance(value.get('status'), str)
           or value['status'] not in CHECK_STATUSES
           for value in checks.values()):
        raise ValueError('Unsupported QA check status')
    incomplete = any(value['status'] != 'PASS' for value in checks.values())
    if (not any(value['status'] == 'PASS' for value in checks.values())
            or (incomplete and not unresolved)
            or (qa['status'] == 'PASS' and (incomplete or unresolved))):
        raise ValueError('QA must record actual successful checks without concealing unfinished work')


def signature_entry(name):
    return bool(re.fullmatch(r'META-INF/(MANIFEST\.MF|[^/]+\.(SF|RSA|DSA|EC)|SIG-[^/]+)', name, re.I))


def payloads(path, unsigned=False):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate ZIP members are not allowed')
        result = {}
        for info in archive.infolist():
            name = info.filename
            if (name.startswith('/') or '\\' in name or '..' in name.split('/')
                    or stat.S_ISLNK(info.external_attr >> 16) or info.flag_bits & 1):
                raise ValueError('Unsafe ZIP member')
            if signature_entry(name):
                if unsigned and name.upper() != 'META-INF/MANIFEST.MF':
                    raise ValueError('The original candidate must be unsigned')
                continue
            # META-INF resources are payload too; only JAR signature records may change.
            result[name] = (hashlib.sha256(archive.read(info)).hexdigest(), info.external_attr)
        return result


def verify_payloads(before, after):
    if payloads(before, unsigned=True) != payloads(after):
        raise ValueError('Signing changed app/runtime payload membership, bytes or modes')
    with zipfile.ZipFile(after) as archive:
        names = {name.upper() for name in archive.namelist()}
        if (not any(name.endswith('.SF') and signature_entry(name) for name in names)
                or not any(name.endswith(('.RSA', '.DSA', '.EC')) and signature_entry(name) for name in names)):
            raise ValueError('Signed bundle is missing a JAR signature')


def verify_signed_certificate(output, expected):
    """Our upload identity is one self-signed certificate, not an unverified alias."""
    certificates = re.findall(r'-----BEGIN CERTIFICATE-----\s*([A-Za-z0-9+/=\s]+?)\s*-----END CERTIFICATE-----', output)
    if len(certificates) != 1:
        raise ValueError('Expected one upload signer certificate')
    der = base64.b64decode(re.sub(r'\s+', '', certificates[0]), validate=True)
    if hashlib.sha256(der).hexdigest() != expected:
        raise ValueError('Signed bundle certificate differs from the verified upload identity')


def run(argv, env):
    try:
        return subprocess.run([str(arg) for arg in argv], env=env, check=True,
                              capture_output=True, text=True).stdout
    except subprocess.CalledProcessError:
        # Child output/argv may contain private paths. Never include them in an error.
        raise ValueError('Internal-test signing/verification command failed; no output was published') from None


def signing_env():
    env = os.environ.copy()
    required = ('Z8_UPLOAD_KEYSTORE', 'Z8_UPLOAD_KEY_ALIAS', 'Z8_UPLOAD_STORE_PASSWORD', 'Z8_UPLOAD_KEY_PASSWORD')
    if any(not env.get(key) for key in required):
        raise ValueError('A dedicated upload signing identity is required')
    key = regular(Path(env['Z8_UPLOAD_KEYSTORE']).expanduser())
    info = key.stat()
    if info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError('Upload key must be owner-only')
    if (env['Z8_UPLOAD_KEY_ALIAS'] in ('z8-debug', 'androiddebugkey')
            or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', env['Z8_UPLOAD_KEY_ALIAS'])):
        raise ValueError('Provide a dedicated upload alias, not a development identity')
    env['Z8_UPLOAD_KEYSTORE'] = str(key)
    jdk = Path(env.get('JAVA_HOME', ROOT / '.local/jdk/Contents/Home'))
    env['JAVA_HOME'] = str(jdk)
    env['PATH'] = str(jdk / 'bin') + os.pathsep + env.get('PATH', '')
    return env, jdk


def sign(args):
    paths = {name: regular(path) for name, path in (
        ('candidate-metadata.json', args.candidate_metadata), ('release-config.json', args.release_config),
        ('compliance-report.json', args.compliance_report), ('qa-report.json', args.qa_report))}
    # Preserve the exact evidence read, under fixed names; never publish user-selected basenames.
    raw = {name: path.read_bytes() for name, path in paths.items()}
    evidence = {name: json.loads(data) for name, data in raw.items()}
    config = release_config.load(paths['release-config.json'], production=True)
    if config != evidence['release-config.json']:
        raise ValueError('Release configuration changed while reading it')
    metadata = evidence['candidate-metadata.json']
    if not isinstance(metadata, dict):
        raise ValueError('Candidate metadata must be an object')
    candidate = sibling(paths['candidate-metadata.json'], metadata.get('aab'), '.aab')
    apk = sibling(paths['candidate-metadata.json'], metadata.get('apk'), '.apk')
    candidate_hash, apk_hash = sha256(candidate), sha256(apk)
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in raw.items()}
    qa = evidence['qa-report.json']
    validate_evidence(metadata, candidate_hash, apk_hash, hashes['release-config.json'], config,
                      evidence['compliance-report.json'], qa)
    payloads(candidate, unsigned=True)
    destination = no_redirect(ROOT / 'artifacts/internal-tests' / str(config['versionCode']))
    if destination.exists():
        raise ValueError('Internal-test output already exists; never overwrite it')
    env, jdk = signing_env()
    sdk = Path(env.get('ANDROID_HOME', ROOT / '.local/android-sdk'))
    bundle = bundletool.ensure(ROOT)
    old_mask = os.umask(0o077)
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.internal-sign-', dir=destination.parent) as temporary:
            stage = Path(temporary)
            # Sign a frozen copy, not a path that another build can replace during signing.
            frozen = stage / 'unsigned.aab'
            shutil.copyfile(candidate, frozen)
            if sha256(frozen) != candidate_hash:
                raise ValueError('Candidate changed while staging')
            certificate = stage / 'upload-certificate.der'
            run([jdk / 'bin/keytool', '-exportcert', '-keystore', env['Z8_UPLOAD_KEYSTORE'],
                 '-alias', env['Z8_UPLOAD_KEY_ALIAS'], '-storepass:env', 'Z8_UPLOAD_STORE_PASSWORD',
                 '-file', certificate], env)
            observed = run([sdk / 'build-tools/36.0.0/apksigner', 'verify', '--verbose', '--print-certs', apk], env)
            signing_identity.verify_test_certificate(signing_identity.certificate_sha256(observed),
                metadata.get('testSigningCertificateSha256'), sha256(certificate))
            signed = stage / ('z8-' + config['versionName'] + '-internal-test.aab')
            run([jdk / 'bin/jarsigner', '-keystore', env['Z8_UPLOAD_KEYSTORE'],
                 '-storepass:env', 'Z8_UPLOAD_STORE_PASSWORD', '-keypass:env', 'Z8_UPLOAD_KEY_PASSWORD',
                 '-signedjar', signed, frozen, env['Z8_UPLOAD_KEY_ALIAS']], env)
            # The trusted keystore + explicit alias makes a wrong/untrusted signer fail strict verification.
            run([jdk / 'bin/jarsigner', '-verify', '-strict', '-keystore', env['Z8_UPLOAD_KEYSTORE'],
                 '-storepass:env', 'Z8_UPLOAD_STORE_PASSWORD', signed, env['Z8_UPLOAD_KEY_ALIAS']], env)
            verify_signed_certificate(run([jdk / 'bin/keytool', '-printcert', '-jarfile', signed, '-rfc'], env),
                                      sha256(certificate))
            run([jdk / 'bin/java', '-jar', bundle, 'validate', '--bundle=' + str(signed)], env)
            verify_payloads(frozen, signed)
            if (sha256(candidate) != candidate_hash or sha256(apk) != apk_hash
                    or any(sha256(path) != hashes[name] for name, path in paths.items())):
                raise ValueError('Candidate or evidence changed during signing')
            record = {'schemaVersion': 1, 'kind': 'z8-internal-test-candidate', 'intendedTrack': 'internal',
                'productionReady': False, 'readyForConsoleUpload': False, 'submission': 'NOT_SUBMITTED',
                'versionCode': config['versionCode'], 'versionName': config['versionName'],
                'aab': signed.name, 'sha256': sha256(signed), 'candidateSha256': candidate_hash,
                'testedApkSha256': apk_hash, 'uploadCertificateSha256': sha256(certificate),
                'createdAtUtc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'evidence': {name: {'path': 'evidence/' + name, 'sha256': digest} for name, digest in hashes.items()},
                'qa': {'status': qa['status'], 'checks': {name: value['status'] for name, value in qa['checks'].items()},
                       'unresolvedCount': len(qa['unresolved']), 'originalReportPreserved': True},
                'gates': {'correspondingSource': 'VERIFIED', 'productionPromotion': 'NOT_GRANTED',
                          'operatorPolicyDecisions': 'NOT_GRANTED_BY_THIS_TOOL',
                          'playAccountAndDeclarations': 'NOT_VERIFIED_BY_THIS_TOOL',
                          'productionQa': 'USE_UNCHANGED_PRODUCTION_VALIDATOR'},
                'limitations': ['Private local signing only; no upload, distribution or Google approval.',
                               'Internal testing is not a policy or license waiver.',
                               'Use the original unsigned candidate and complete evidence for production promotion.',
                               'Retained evidence may be private; do not publish this directory.']}
            ready = stage / 'ready'
            (ready / 'evidence').mkdir(parents=True)
            shutil.copyfile(signed, ready / signed.name)
            for name, data in raw.items():
                (ready / 'evidence' / name).write_bytes(data)
            (ready / 'internal-test.json').write_text(json.dumps(record, indent=2) + '\n')
            no_redirect(destination)
            # Reserve the final directory exclusively: rename() could overwrite a racing empty directory.
            destination.mkdir()
            try:
                # The manifest is the completion marker and is installed last.
                for name in ('evidence', signed.name, 'internal-test.json'):
                    (ready / name).rename(destination / name)
            except BaseException:
                shutil.rmtree(destination)
                raise
            return record
    finally:
        os.umask(old_mask)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate-metadata', type=Path, required=True)
    parser.add_argument('--release-config', type=Path, default=ROOT / 'release/config.json')
    parser.add_argument('--compliance-report', type=Path, required=True)
    parser.add_argument('--qa-report', type=Path, required=True)
    record = sign(parser.parse_args())
    # Never echo raw QA, account information, local paths or key subprocess output.
    print(json.dumps({name: record[name] for name in (
        'kind', 'intendedTrack', 'productionReady', 'readyForConsoleUpload', 'submission',
        'versionCode', 'versionName', 'aab', 'sha256', 'candidateSha256')}, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, zipfile.BadZipFile):
        sys.exit('sign-internal-test: validation or signing failed; no approval granted. Check private inputs locally.')
