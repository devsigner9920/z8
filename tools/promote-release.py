#!/usr/bin/env python3
"""Sign an already tested candidate for upload; never rebuild it or invent missing release evidence."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bundletool
import release_config
import signing_identity

ROOT = Path(__file__).resolve().parents[1]
DECISIONS = ('dataSafetyReviewed', 'externalCodePolicyReviewed', 'claudeDistributionTermsReviewed',
             'guestDistributionTermsReviewed', 'storeListingReviewed', 'foregroundServiceDeclarationPrepared')


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def validate_evidence(metadata, candidate_hash, config_hash, config, compliance, qa, decisions):
    if (metadata.get('variant') != 'candidate' or metadata.get('debuggable') is not False
            or metadata.get('targetSdk') != release_config.TARGET_SDK
            or metadata.get('aabSigning') != 'unsigned' or metadata.get('bundleValidated') is not True
            or metadata.get('bootstrapIncluded') is not True or metadata.get('guestImageIncluded') is not True):
        raise ValueError('Only a complete, non-debuggable, validated runtime AAB candidate can be promoted')
    if metadata.get('aabSha256') != candidate_hash or metadata.get('releaseConfigSha256') != config_hash:
        raise ValueError('Candidate or public configuration changed; build and verify a new candidate')
    if metadata.get('versionCode') != config['versionCode'] or metadata.get('versionName') != config['versionName']:
        raise ValueError('Candidate version differs from release configuration')
    if (compliance.get('kind') != 'z8-release-compliance-verification' or compliance.get('status') != 'VERIFIED'
            or compliance.get('blockers') or compliance.get('inputs', {}).get('artifactSha256') != candidate_hash
            or compliance.get('inputs', {}).get('sourceUrlVerified') != config['sourceUrl']):
        raise ValueError('Source/license evidence must be verified for this exact candidate and public source URL')
    if (qa.get('kind') != 'z8-release-qa' or qa.get('status') != 'PASS'
            or qa.get('aabSha256') != candidate_hash or qa.get('unresolved')):
        raise ValueError('Final release QA must pass for this exact candidate without unresolved findings')
    required_checks = ('freshInstall', 'updatePreservesProjects', 'projectDeletion', 'runtimeAndChildProcesses',
                       'codexAuthenticatedTask', 'claudeAuthenticatedTask', 'physicalDevice', 'pageSize16KiB',
                       'previewDataDeletion', 'backAndKeyboard', 'foregroundStopAndNotifications')
    if any(qa.get('checks', {}).get(name, {}).get('status') != 'PASS' for name in required_checks):
        raise ValueError('Required final release QA checks are missing or incomplete')
    if (decisions.get('aabSha256') != candidate_hash or not decisions.get('reviewedBy')
            or not decisions.get('reviewedAt') or any(decisions.get(name) is not True for name in DECISIONS)):
        raise ValueError('Operator policy/provider decisions must explicitly cover this exact candidate')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate-metadata', type=Path, required=True)
    parser.add_argument('--release-config', type=Path, default=ROOT / 'release/config.json')
    parser.add_argument('--compliance-report', type=Path, required=True)
    parser.add_argument('--qa-report', type=Path, required=True)
    parser.add_argument('--decisions', type=Path, required=True)
    args = parser.parse_args()
    config = release_config.load(args.release_config, production=True)
    metadata = json.loads(args.candidate_metadata.read_text())
    name = metadata.get('aab', '')
    if Path(name).name != name or not name.endswith('.aab'):
        raise ValueError('Candidate AAB must be beside its metadata')
    candidate = args.candidate_metadata.parent / name
    candidate_hash = sha256(candidate)
    apk_name = metadata.get('apk', '')
    if Path(apk_name).name != apk_name or not apk_name.endswith('.apk'):
        raise ValueError('The tested APK must be beside the candidate metadata')
    tested_apk = args.candidate_metadata.parent / apk_name
    if sha256(tested_apk) != metadata.get('sha256'):
        raise ValueError('The candidate test APK changed; verify a new candidate')
    evidence = [json.loads(path.read_text()) for path in (args.compliance_report, args.qa_report, args.decisions)]
    validate_evidence(metadata, candidate_hash, sha256(args.release_config), config, *evidence)
    env = os.environ.copy()
    required = ('Z8_UPLOAD_KEYSTORE', 'Z8_UPLOAD_KEY_ALIAS', 'Z8_UPLOAD_STORE_PASSWORD', 'Z8_UPLOAD_KEY_PASSWORD')
    missing = [key for key in required if not env.get(key)]
    if missing:
        raise ValueError('Upload signing is not configured: ' + ', '.join(missing))
    key = Path(env['Z8_UPLOAD_KEYSTORE']).expanduser().resolve()
    if not key.is_file() or env['Z8_UPLOAD_KEY_ALIAS'] in ('z8-debug', 'androiddebugkey'):
        raise ValueError('Provide a dedicated upload key, not a development identity')
    destination = ROOT / 'artifacts/releases' / str(config['versionCode'])
    if destination.exists():
        raise ValueError('This version already has release output; do not overwrite a published version')
    jdk = Path(env.get('JAVA_HOME', ROOT / '.local/jdk/Contents/Home'))
    env['JAVA_HOME'] = str(jdk)
    env['PATH'] = str(jdk / 'bin') + os.pathsep + env.get('PATH', '')
    with tempfile.TemporaryDirectory(prefix='upload-sign-', dir=ROOT / '.local') as directory:
        stage = Path(directory)
        certificate = stage / 'upload-certificate.der'
        subprocess.run([str(jdk / 'bin/keytool'), '-exportcert', '-keystore', str(key),
                        '-alias', env['Z8_UPLOAD_KEY_ALIAS'], '-storepass:env', 'Z8_UPLOAD_STORE_PASSWORD',
                        '-file', str(certificate)], env=env, check=True, capture_output=True)
        sdk = Path(env.get('ANDROID_HOME', ROOT / '.local/android-sdk'))
        apk_verification = subprocess.check_output([str(sdk / 'build-tools/36.0.0/apksigner'),
            'verify', '--verbose', '--print-certs', str(tested_apk)], env=env, text=True)
        signing_identity.verify_test_certificate(signing_identity.certificate_sha256(apk_verification),
            metadata.get('testSigningCertificateSha256'), sha256(certificate))
        debug_key = ROOT / '.local/keys/z8-debug.jks'
        if debug_key.exists():
            debug_cert = stage / 'development-certificate.der'
            subprocess.run([str(jdk / 'bin/keytool'), '-exportcert', '-keystore', str(debug_key),
                            '-alias', 'z8-debug', '-storepass', 'android', '-file', str(debug_cert)],
                           check=True, capture_output=True)
            if sha256(certificate) == sha256(debug_cert):
                raise ValueError('Upload key certificate equals the development certificate')
        signed = stage / ('z8-' + config['versionName'] + '.aab')
        subprocess.run([str(jdk / 'bin/jarsigner'), '-keystore', str(key), '-storepass:env', 'Z8_UPLOAD_STORE_PASSWORD',
                        '-keypass:env', 'Z8_UPLOAD_KEY_PASSWORD', '-signedjar', str(signed), str(candidate),
                        env['Z8_UPLOAD_KEY_ALIAS']], env=env, check=True, capture_output=True)
        subprocess.run([str(jdk / 'bin/jarsigner'), '-verify', str(signed)], check=True, capture_output=True)
        subprocess.run([str(jdk / 'bin/java'), '-jar', str(bundletool.ensure(ROOT)), 'validate', '--bundle=' + str(signed)],
                       check=True, capture_output=True)
        # Signing may add META-INF records, but must not change any app or runtime payload.
        with zipfile.ZipFile(candidate) as before, zipfile.ZipFile(signed) as after:
            payloads = {n for n in before.namelist() if not n.startswith('META-INF/')}
            if payloads != {n for n in after.namelist() if not n.startswith('META-INF/')}:
                raise ValueError('Signing changed the candidate payload membership')
            if any(before.read(n) != after.read(n) for n in payloads):
                raise ValueError('Signing changed an app payload')
        record = {'schemaVersion': 1, 'kind': 'z8-upload-release', 'readyForConsoleUpload': True,
                  'versionCode': config['versionCode'], 'versionName': config['versionName'],
                  'aab': signed.name, 'sha256': sha256(signed), 'candidateSha256': candidate_hash,
                  'uploadCertificateSha256': sha256(certificate),
                  'createdAtUtc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  'evidence': {path.name: sha256(path) for path in
                               (args.release_config, args.compliance_report, args.qa_report, args.decisions)},
                  'playApproval': 'NOT_SUBMITTED'}
        ready = stage / 'ready'
        ready.mkdir()
        shutil.copy2(signed, ready / signed.name)
        (ready / 'release.json').write_text(json.dumps(record, indent=2) + '\n')
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise ValueError('Release output appeared during verification; preserve it')
        ready.rename(destination)
        print(json.dumps(record, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as failure:
        # CalledProcessError contains argv but no password values (only environment variable names).
        sys.exit('promote-release: ' + str(failure))
