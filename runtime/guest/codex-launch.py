#!/usr/bin/python3
"""Project-scoped, explicit Codex local-mode consent; never edits Codex configuration."""
import fcntl
import json
import os
from pathlib import Path
import platform
import re
import selectors
import signal
import stat
import subprocess
import sys
import time
import uuid

HOME = Path('/z8/home')
MARKER = Path('/etc/z8/guest-target')
STATE = 'codex-local.json'
CHOICE = 'allow-local-without-codex-sandbox'
MAX_STATE = 4096
MAX_HELP = 128 * 1024
HELP_TIMEOUT = 3.0
RESET = '--z8-reset-local-mode'
# These do not change the approval/sandbox/configuration policy. Unknown options,
# short bundles and attached short values deliberately bypass this adapter.
VALUE_OPTIONS = {'--model', '-m', '--image', '-i'}
BOOL_OPTIONS = {'--search', '--no-alt-screen'}
SUBCOMMANDS = {'exec', 'e', 'review', 'login', 'logout', 'completion', 'mcp', 'mcp-server',
               'app-server', 'app', 'sandbox', 'debug', 'apply', 'a', 'cloud', 'remote',
               'server', 'help', 'version', 'status', 'doctor', 'update', 'features',
               'internal-ssh-serve'}


class UnsafeState(ValueError):
    pass


def interactive_args(args):
    """Classify conservatively before doing any probe, consent read or mutation."""
    command = None
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == '--':
            break
        if arg.startswith('-'):
            option = arg.split('=', 1)[0]
            if option in VALUE_OPTIONS:
                if '=' in arg:
                    if not option.startswith('--') or not arg.split('=', 1)[1]:
                        return False
                else:
                    index += 1
                    if index >= len(args) or args[index].startswith('-'):
                        return False
            elif arg in BOOL_OPTIONS:
                pass
            elif command in {'resume', 'fork'} and arg == '--last':
                pass
            else:
                return False
        elif command is None:
            if arg in SUBCOMMANDS:
                return False
            command = arg if arg in {'resume', 'fork'} else 'prompt'
        index += 1
    return True


def open_directory(path):
    """Walk every directory component without following links, including parents."""
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise UnsafeState('invalid absolute state path')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        return fd
    except BaseException:
        os.close(fd)
        raise


def read_regular(directory, name, maximum, private=False):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
            raise UnsafeState('state is not an owned regular file')
        if private and (stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
            raise UnsafeState('state must be a private, single-link file')
        if info.st_size > maximum:
            raise UnsafeState('state exceeds size limit')
        data = os.read(fd, maximum + 1)
        if len(data) > maximum:
            raise UnsafeState('state exceeds size limit')
        return data
    finally:
        os.close(fd)


def guest_context():
    project = os.environ.get('Z8_PROJECT_ID', '')
    try:
        valid_project = str(uuid.UUID(project)) == project and uuid.UUID(project).int != 0
    except ValueError:
        valid_project = False
    if platform.system() != 'Linux' or os.environ.get('HOME') != str(HOME) or not valid_project:
        raise UnsafeState('not a marked z8 project environment')
    directory = open_directory(MARKER.parent)
    try:
        if read_regular(directory, MARKER.name, 64).rstrip(b'\n') != b'z8-guest-v1':
            raise UnsafeState('unexpected guest marker')
    finally:
        os.close(directory)
    return HOME, project


def open_store(home, create=False):
    fd = open_directory(home)
    try:
        home_info = os.fstat(fd)
        if home_info.st_uid != os.geteuid():
            raise UnsafeState('project HOME is not owned by this user')
        for part in ('.config', 'z8'):
            if create:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=fd)
                except FileExistsError:
                    pass
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = next_fd
            info = os.fstat(fd)
            if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o022:
                raise UnsafeState('state directory ownership or permissions are unsafe')
            # Android app/cache parents can propagate SGID to new directories.
            # Those inheritance bits grant no access; require owner-only rwx.
            if part == 'z8' and stat.S_IMODE(info.st_mode) & 0o777 != 0o700:
                raise UnsafeState('z8 state directory must be private')
        return fd
    except BaseException:
        os.close(fd)
        raise


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise UnsafeState('duplicate consent key')
        result[key] = value
    return result


def parse_approval(raw, project):
    record = json.loads(raw.decode('utf-8'), object_pairs_hook=unique_object)
    if not isinstance(record, dict) or set(record) != {'schemaVersion', 'projectId', 'choice'}:
        raise UnsafeState('unexpected consent schema')
    if type(record['schemaVersion']) is not int or record['schemaVersion'] != 1:
        raise UnsafeState('unsupported consent version')
    if record['projectId'] != project or record['choice'] != CHOICE:
        raise UnsafeState('consent belongs to another project or mode')
    return True


def approved(home, project):
    try:
        directory = open_store(home)
    except FileNotFoundError:
        return False
    try:
        try:
            raw = read_regular(directory, STATE, MAX_STATE, private=True)
        except FileNotFoundError:
            return False
    finally:
        os.close(directory)
    return parse_approval(raw, project)


def save_approval(home, project):
    directory = open_store(home, create=True)
    temporary = '.codex-local.' + uuid.uuid4().hex + '.tmp'
    created = False
    try:
        # Lock the owned directory itself: no extra lock file or hardlinks. PRoot's
        # --link2symlink makes link-based publication unsuitable in this guest.
        fcntl.flock(directory, fcntl.LOCK_EX)
        try:
            existing = read_regular(directory, STATE, MAX_STATE, private=True)
        except FileNotFoundError:
            existing = None
        if existing is not None:
            parse_approval(existing, project)
            return
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        created = True
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'wb') as output:
            output.write(json.dumps({'schemaVersion': 1, 'projectId': project, 'choice': CHOICE},
                                    separators=(',', ':')).encode('utf-8') + b'\n')
            output.flush()
            os.fsync(output.fileno())
        # Atomic rename publishes only the completed private receipt. The checked,
        # locked directory is not a security boundary against same-UID processes.
        os.replace(temporary, STATE, src_dir_fd=directory, dst_dir_fd=directory)
        created = False
        os.fsync(directory)
    finally:
        if created:
            os.unlink(temporary, dir_fd=directory)
        os.close(directory)


def reset_approval(home):
    try:
        directory = open_store(home)
    except FileNotFoundError:
        return
    try:
        fcntl.flock(directory, fcntl.LOCK_EX)
        try:
            # Only remove the owned regular app receipt, never a link or directory.
            read_regular(directory, STATE, MAX_STATE, private=True)
        except FileNotFoundError:
            return
        os.unlink(STATE, dir_fd=directory)
        os.fsync(directory)
    finally:
        os.close(directory)


def capabilities(binary):
    process = None
    try:
        process = subprocess.Popen([binary, '--help'], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        data = bytearray()
        deadline = time.monotonic() + HELP_TIMEOUT
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                if not selector.select(remaining):
                    return False
                chunk = os.read(process.stdout.fileno(), min(8192, MAX_HELP + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > MAX_HELP:
                    return False
        remaining = deadline - time.monotonic()
        if remaining <= 0 or process.wait(timeout=remaining) != 0:
            return False
        help_text = data.decode('utf-8', errors='replace')
        return bool(re.search(r'(?<!\w)--no-daemon\b', help_text)
                    and re.search(r'(?<!\w)--sandbox\b', help_text)
                    and 'danger-full-access' in help_text)
    except (OSError, subprocess.TimeoutExpired):
        return False
    finally:
        if process is not None:
            # A launcher can exit while a descendant keeps the output pipe open.
            # The process group is ours even after the leader exits.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            if process.stdout is not None:
                process.stdout.close()


def confirm():
    print('''z8 · Codex 로컬 실행 설정

이 프로젝트에서 Codex의 Linux sandbox 없이 실행하도록 허용할까요?
일반 파일 수정·셸 명령·네트워크 작업이 추가 승인 없이 실행될 수 있습니다.
Android 앱 권한은 유지되지만, 다른 z8 프로젝트를 보호한다고 보장하지 않습니다.
Codex의 기존 승인 설정은 변경하지 않습니다.

동의는 이 프로젝트에만 저장됩니다.
해제: codex --z8-reset-local-mode
계속하려면 yes 또는 동의를 입력하세요. Enter는 나중에입니다.''', flush=True)
    print('선택: ', end='', flush=True)
    answer = sys.stdin.readline(64)
    return answer.endswith('\n') and answer.rstrip('\r\n') in {'yes', '동의'}


def launch(binary, args):
    os.execv(binary, [binary, *args])


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv or not os.path.isabs(argv[0]) or '\0' in argv[0]:
        print('z8: absolute Codex executable path required', file=sys.stderr)
        return 64
    binary, args = argv[0], argv[1:]
    try:
        if args == [RESET]:
            try:
                home, unused_project = guest_context()
            except (OSError, ValueError):
                print('z8: 프로젝트 정보를 확인할 수 없습니다. 새 터미널을 열어 다시 실행해 주세요.', file=sys.stderr)
                return 1
            reset_approval(home)
            print('z8: 이 프로젝트의 Codex 로컬 실행 동의를 해제했습니다.')
            return 0
        if not sys.stdin.isatty() or not sys.stdout.isatty() or not interactive_args(args):
            launch(binary, args)
            return 0
        try:
            home, project = guest_context()
        except (OSError, ValueError):
            print('z8: 프로젝트 정보를 확인할 수 없습니다. 새 터미널을 열어 다시 실행해 주세요.', file=sys.stderr)
            return 1
        if not capabilities(binary):
            launch(binary, args)
            return 0
        if not approved(home, project):
            if not confirm():
                print('z8: 이번 실행을 취소했습니다. 설정은 바뀌지 않았습니다.')
                return 130
            save_approval(home, project)
        print('z8 · 프로젝트 로컬 모드 · Codex sandbox 꺼짐 · 해제: codex --z8-reset-local-mode', flush=True)
        launch(binary, ['--no-daemon', '--sandbox', 'danger-full-access', *args])
        return 0
    except KeyboardInterrupt:
        print('\nz8: 실행을 취소했습니다.', file=sys.stderr)
        return 130
    except (OSError, ValueError):
        # Never fall back to unsandboxed execution when receipt validation fails.
        print('z8: 로컬 실행 설정을 확인할 수 없어 실행을 중단했습니다. '
              'codex --z8-reset-local-mode 로 동의를 초기화할 수 있습니다.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
