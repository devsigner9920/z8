#!/usr/bin/env python3
"""Explicit, isolated reconstruction of the pinned coroutines 1.6.4 probe.

Collection never executes upstream code. This separate command compiles one
verified source file with a pinned, unmodified compiler and compares all bytes.
It does not approve a release or claim a complete coroutines/library rebuild.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request

import maven_upstream_supplements as supplements
from release_compliance import atomic_write, json_bytes, maven_source_inventory, read_json, sha256

COORDINATE = 'maven:org.jetbrains.kotlinx:kotlinx-coroutines-core-jvm:1.6.4'
SOURCE = 'integration-testing/src/debugAgentTest/kotlin/DebugProbes.kt'
SOURCE_SHA256 = '79f87242798d6b8643d5994462f7a74629e34784fc263f5fa4024f62f37d9285'
RESOURCE = 'kotlinx-coroutines-core/jvm/resources/DebugProbesKt.bin'
RESOURCE_SHA256 = '158a19eb94aa2f3e2f459db69ee10276c73b945dd6c5f8fc223cf2d85e2b5e33'
COMMIT = '81e17dd37003a7105e542eb725f51ee0dc353354'
MODULE = 'kotlinx-coroutines-integration-testing_debugAgentTest'
# General-purpose compiler inputs, not components added to the Z8 application.
TOOLCHAIN = [
    ('org.jetbrains.kotlin', 'kotlin-compiler-embeddable', '1.6.21', 51977168, '5f96503cd822aa6c20eda6c716a553c414d800ed0c6e7d655fa1b1fbfd4fec2b'),
    ('org.jetbrains.kotlin', 'kotlin-stdlib', '1.6.21', 1509405, '739c526672bb337573b28f63afa8306eb088b0c3a0967f56d6c89f4a3012a492'),
    ('org.jetbrains.kotlin', 'kotlin-script-runtime', '1.6.21', 42319, '606c34a7e6e8e439e9208765e7d75b1dbcf80f38353f3e29bb27456d7b371171'),
    ('org.jetbrains.kotlin', 'kotlin-reflect', '1.6.21', 3058829, '1e1f57209f7238c3fd1735a1b9339a56565507dca249f8371bf59d91f601aeaa'),
    ('org.jetbrains.kotlin', 'kotlin-daemon-embeddable', '1.6.21', 724994, '51c3ec1c32c36d6570d83142eafe2a242934f165f0b78c3861376905f90f2e12'),
    ('org.jetbrains.intellij.deps', 'trove4j', '1.0.20200330', 572985, 'c5fd725bffab51846bf3c77db1383c60aaaebfe1b7fe2f00d23fe1b7df0a439d'),
    ('net.java.dev.jna', 'jna', '5.6.0', 1509440, '5557e235a8aa2f9766d5dc609d67948f2a8832c2d796cea9ef1d6cbe0b3b7eaf'),
    ('org.jetbrains', 'annotations', '13.0', 17536, 'ace2a10dc8e2d5fd34925ecac03e4988b2c0f851650c94b8cef49ba1bd111478'),
]


def toolchain(directory, fetch):
    directory.mkdir(parents=True, exist_ok=True)
    paths, records = {}, []
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            raise ValueError('Compiler download must remain at its exact Maven Central URL')
    for group, name, version, size, digest in TOOLCHAIN:
        filename = name + '-' + version + '.jar'
        path = directory / filename
        url = 'https://repo.maven.apache.org/maven2/' + group.replace('.', '/') + '/' + name + '/' + version + '/' + filename
        if path.is_symlink():
            raise ValueError('Compiler input is a symlink: ' + filename)
        if not path.exists():
            if not fetch:
                raise ValueError('Missing compiler input; explicitly use --fetch-toolchain: ' + filename)
            request = urllib.request.Request(url, headers={'User-Agent': 'Z8-source-rebuild/1'})
            with urllib.request.build_opener(NoRedirect()).open(request, timeout=60) as response:
                if response.geturl() != url:
                    raise ValueError('Compiler response URL changed')
                data = response.read(size + 1)
            if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
                raise ValueError('Compiler download hash/size mismatch: ' + filename)
            atomic_write(path, data)
        if not path.is_file() or path.stat().st_size != size or sha256(path) != digest:
            raise ValueError('Compiler input hash/size mismatch: ' + filename)
        paths[name] = path
        records.append({'coordinate': ':'.join((group, name, version)), 'url': url, 'bytes': size, 'sha256': digest})
    return paths, records


def retained_inputs(inventory):
    report = maven_source_inventory(inventory)
    components = [c for c in report['components'] if c['id'] == COORDINATE and not c['unresolved']]
    if len(components) != 1:
        raise ValueError('Exact coroutines component with complete retained inputs is required')
    snapshot = components[0].get('upstreamSnapshot', {})
    lock = read_json(inventory.parent / report['upstreamSupplements']['path'])
    specs, _ = supplements.validate_lock(lock)
    originals = [x for x in snapshot.get('inputs', [])
                 if specs[x['archiveId']]['repository'] == 'https://github.com/Kotlin/kotlinx.coroutines'
                 and specs[x['archiveId']]['commit'] == COMMIT]
    if len(originals) != 1 or len(snapshot.get('binaryInputs', [])) != 1:
        raise ValueError('Exact upstream and runtime JAR evidence is required')
    original = originals[0]
    tree, _ = supplements.read_members(specs[original['archiveId']], (inventory.parent / original['path']).read_bytes())
    source, resource = tree.get(SOURCE), tree.get(RESOURCE)
    if (source is None or resource is None or hashlib.sha256(source).hexdigest() != SOURCE_SHA256
            or hashlib.sha256(resource).hexdigest() != RESOURCE_SHA256):
        raise ValueError('Probe source or expected resource differs from the reviewed version')
    binary = snapshot['binaryInputs'][0]
    return source, resource, inventory.parent / binary['path'], {
        'mavenSourcesSha256': sha256(inventory), 'upstreamCommit': COMMIT,
        'upstreamArchiveSha256': original['sha256'], 'runtimeJarSha256': binary['sha256'],
        'sourceMember': SOURCE, 'sourceSha256': SOURCE_SHA256,
        'expectedResource': RESOURCE, 'expectedResourceSha256': RESOURCE_SHA256}


def verify(args):
    inventory = args.maven_sources.resolve()
    source, expected, core, provenance = retained_inputs(inventory)
    paths, tools = toolchain(args.toolchain_dir.resolve(), args.fetch_toolchain)
    java = args.java_home.resolve() / 'bin/java'
    if not java.is_file():
        raise ValueError('--java-home must contain a usable JDK bin/java')
    output = args.output.absolute()
    # Never overwrite a prior verification result or an existing output symlink.
    output.mkdir(parents=True, exist_ok=False)
    source_path = output / 'DebugProbes.kt'
    source_path.write_bytes(source)
    compiler_classpath = os.pathsep.join(str(paths[name]) for _, name, *_ in TOOLCHAIN)
    compile_classpath = os.pathsep.join(str(x) for x in (core, paths['kotlin-stdlib'], paths['annotations']))
    argv = [str(java), '-cp', compiler_classpath, 'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler',
            '-no-stdlib', '-no-reflect', '-jvm-target', '1.8', '-Xallow-kotlin-package',
            '-module-name', MODULE, '-classpath', compile_classpath,
            '-d', str(output / 'classes'), str(source_path)]
    env = {key: value for key, value in os.environ.items()
           if key not in ('JAVA_TOOL_OPTIONS', 'JDK_JAVA_OPTIONS', '_JAVA_OPTIONS', 'CLASSPATH')}
    java_version = subprocess.run([str(java), '-version'], env=env, capture_output=True, text=True, timeout=10)
    if java_version.returncode:
        raise ValueError('Selected JDK could not report its version')
    result = subprocess.run(argv, cwd=output, env=env, capture_output=True, text=True, timeout=90)
    if result.returncode:
        raise ValueError('Pinned compiler failed; no successful reconstruction is recorded')
    generated = output / 'classes/kotlin/coroutines/jvm/internal/DebugProbesKt.class'
    if not generated.is_file() or generated.read_bytes() != expected:
        raise ValueError('Compiled probe does not match the complete expected class bytes')
    report = {'schemaVersion': 1, 'kind': 'z8-coroutines-probe-reconstruction', 'status': 'PASS',
              'inputs': provenance, 'compilerToolchain': tools,
              'javaVersion': (java_version.stdout + java_version.stderr).strip(),
              'compilerOptions': ['-no-stdlib', '-no-reflect', '-jvm-target', '1.8',
                                  '-Xallow-kotlin-package', '-module-name', MODULE],
              'output': {'member': 'kotlin/coroutines/jvm/internal/DebugProbesKt.class',
                         'bytes': len(expected), 'sha256': sha256(generated), 'byteIdentical': True},
              'sourceClosureReviewed': False,
              'scope': 'Only this compiled probe resource was reconstructed, not the full coroutines library or Android app.'}
    atomic_write(output / 'probe-rebuild.json', json_bytes(report))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--maven-sources', required=True, type=Path)
    parser.add_argument('--java-home', required=True, type=Path)
    parser.add_argument('--toolchain-dir', required=True, type=Path)
    parser.add_argument('--fetch-toolchain', action='store_true', help='Explicitly fetch exact hash-pinned compiler inputs from Maven Central')
    parser.add_argument('--output', required=True, type=Path, help='A new output directory; existing paths are refused')
    args = parser.parse_args()
    try:
        report = verify(args)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps({'status': report['status'], 'bytes': report['output']['bytes'], 'sha256': report['output']['sha256']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
