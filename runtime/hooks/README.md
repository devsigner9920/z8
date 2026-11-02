# Local attention bridge (G1 foundation)

This is a working Android event receiver plus **candidate** provider adapters. A
successful synthetic notification is not evidence that Claude Code or Codex is
installed or compatible with Android/PRoot. Actual CLI permission/question tests
remain required for every supported CLI version.

## Current behavior

`TermuxService` owns `Z8AttentionBridge`. Each app-created terminal launch gets a
random `Z8_LAUNCH_ID`, a 256-bit `Z8_EVENT_TOKEN`, and `Z8_EVENT_SOCKET`. After the
terminal object exists, the service registers that exact object against the
launch. The filesystem Unix socket is under the app-private `files/z8/attention`
directory (0700); the socket lives in its `transport` subdirectory (0700; socket 0600), accepts only the app UID, and validates its launch
nonce. This prevents accidental cross-session routing; it is not a security
boundary against code already running as the same Android UID.

The receiver accepts one newline-delimited JSON frame per connection, at most
16 KiB, with a one-second whole-frame deadline and 300 ms idle timeout. Example
(the token shown is a placeholder, not a working credential):

```json
{"schemaVersion":1,"eventId":"a-unique-event-id","launchId":"registered-launch-id","token":"64-lowercase-hex-characters-from-the-launcher","provider":"claude","providerSessionId":"optional-provider-session","kind":"permission"}
```

Only these fields plus optional `requestId` are accepted. Kinds are `permission`,
`question`, `plan`, `finished`; providers are `claude`, `codex`, `diagnostic`.
Payloads cannot contain arbitrary URLs, commands, paths, prompt text or tool
input. Identifiers are limited to 160 ASCII letters/digits/`_.:-` characters.
Frames are not logged. Tokens are never persisted to the event journal. The
prepared fork also omits upstream shell environment dumps, including verbose
logging, because those otherwise expose launch credentials.

Validated observations are saved atomically before ACK. Event ID replay is
suppressed within the registered launch and retained journal. A known provider
request ID can also suppress retransmission. The built-in adapters do not invent
such IDs: matching command text is not evidence that two approvals are the same.
The journal holds up to 256 observations; when full it returns `full` rather than
dropping unseen requests. The inbox has explicit cleanup for read/ended history;
cleanup also ends that history's deduplication retention. There is no unbounded
retry queue. Ending a process discards its registration/nonce and marks its
observations stale when next reconciled. Process/service restart marks all
previous observations stale; it never guesses that a new shell is the old one.

Notification text stays generic even on the unlocked screen. Tapping an immutable
PendingIntent opens the registered live terminal, or the inbox's interrupted
state if that session no longer exists. No notification action approves, denies,
sends `y`, submits Enter, or restarts a command. Reading an observation does not
resolve the provider request. Turn-finished observations are stored but their
notifications are suppressed. Notification permission/channel blocking is
recorded as `BLOCKED`; observations remain available in **알림**, opened from the
bell beside the z8 logo or a terminal's context menu. The inbox groups records by
project and terminal identity and shows event type, provider, observation date
and read/ended state. Live registrations supply the project and terminal names;
older records without a project ID remain separate history groups. Ended
terminals have disabled rows. Opening a live row revalidates its registration and
routes to that existing PTY; it never creates a replacement terminal.

The inbox refreshes on resume and every two seconds while visible, reading its
journal off the UI thread. **기록 정리** removes read or ended history. Unread
request counts represent observed permission/question/plan events, not a claim
that the CLI is still waiting. Reading or clearing an observation never supplies
a provider response or resolves its request.

The header gear opens **설정**, with theme, Android notification settings and app
version. Debug builds also expose **개발자 → 훅 수신 테스트**, which exercises the
actual socket, framing, UID, nonce, journal and notification path with
`provider=diagnostic`; the inbox labels those events **진단 테스트**. Runtime
diagnostics and the selected project's environment tools are also debug-only
settings entries. The normal inbox has no diagnostic-test or manual-refresh
controls.

Current limits: pre-events are observations, not confirmed ongoing waits;
automatic provider resolution, foreground-session notification suppression and
notification replies are not implemented. Remote transport is outside this MVP.

## Candidate CLI adapters (not live CLI tested)

`z8_event.py` needs Python 3 in the guest. Project preparation installs it with
the standard development tools before opening the first terminal; an
unprovisioned base image cannot run this adapter. Place
the reviewed helper at `/opt/z8/hooks/z8_event.py`, bind only the
`attention/transport` directory into `/run/z8/attention` in the guest, and supply
that launch's three environment variables with the socket path set to
`/run/z8/attention/events.sock`. Never bind the parent attention directory (it
contains the app-wide journal), all of app HOME, or another project's source.
Keep the nonce in the process environment; never interpolate it into generated
shell source, a persistent settings file, command arguments or log messages.
The current registration is per **terminal launch**. A future direct CLI launcher
must register the precise CLI attempt and retire its nonce when that attempt ends;
it must not reuse another tool's finished launch. Verify actual PRoot
socket access before reporting support.

The offline image preparation tooling can call `deploy.py --rootfs PATH` for a dry run and
add `--apply` to stage these three reviewed assets into a **stopped/offline**,
`z8-guest-v1`-marked rootfs. Its `stage(rootfs, apply=False)` Python API returns
content hashes. It refuses symlink traversal, the host root, and replacement of
modified existing assets. It never installs packages, enables provider settings,
writes credentials or changes hook trust; the manager must report those steps
separately. Do not run staging concurrently with processes modifying that rootfs.

Merge the corresponding template's `hooks` entries into the user's existing
provider settings; never replace their complete settings file or remove existing
hooks. `claude.hooks.json` is a fragment for Claude's settings; `codex.hooks.json`
is a Codex hooks file fragment. These files are deliberately not auto-installed
into the host's CLI settings. Preserve normal tool hook review/trust. There are
no trust bypass or automatic permission flags.

### Explicit guest enablement

The guest image also includes `enable.py` at `/opt/z8/hooks/enable.py`. Run it
inside the marked ARM64 Linux environment, with `HOME=/z8/home`, after installing
the basic tools. Preview is the default and does not create files:

```sh
/usr/bin/python3 /opt/z8/hooks/enable.py claude
/usr/bin/python3 /opt/z8/hooks/enable.py codex
```

Apply only the selected provider's reviewed observer entries:

```sh
/usr/bin/python3 /opt/z8/hooks/enable.py --apply claude
/usr/bin/python3 /opt/z8/hooks/enable.py --apply codex
```

Claude uses `/z8/home/.claude/settings.json`; Codex uses
`/z8/home/.codex/hooks.json`. These are user-level provider settings inside this
project's dedicated HOME, so they are separate from repository source and other
projects. The installer rejects a `CLAUDE_CONFIG_DIR` or `CODEX_HOME` override
that would redirect the selected provider elsewhere.

Existing JSON values, unknown fields, event order and unrelated hooks survive
the merge. Exact existing z8 groups are unchanged on a second run. An edited
copy of a z8 group, malformed/duplicate-key JSON, a symlink, nonregular file,
oversized file or modified bundled helper/template stops the operation for
review. Original bytes are retained in a unique adjacent
`*.z8-backup-<id>` file with mode 0600 before a changed existing file is saved.
The new file is flushed and atomically renamed in the same directory. Its
original ordinary permission bits are retained; new settings use 0600.

The installer serializes its own concurrent invocations and compares the disk
file again immediately before publication. Provider processes and editors do
not share that lock: a same-UID writer can still race the final comparison and
rename. Close provider settings editors while applying. This is conflict
detection and recovery, not a security boundary against another process in the
same guest. JSON whitespace is normalized only when new entries are added.

Codex still requires the user to review and trust the exact new definitions in
`/hooks`. The installer does not write trust records or feature flags. It reports
disabled hook preferences and leaves them intact. Existing inline TOML hooks
are preserved; unrelated inline hooks can coexist with a startup warning, while
an inline z8 observer stops the merge to avoid duplicate delivery. These paths
and the separate trust step follow the [Codex hooks documentation](https://learn.chatgpt.com/docs/hooks).

Claude's `/hooks` shows configured entries. Its existing workspace trust,
`disableAllHooks` and managed policies remain authoritative; this installer does
not weaken them. Current versions normally watch settings edits. These behavior
and path details follow the [Claude hook configuration reference](https://code.claude.com/docs/en/hooks#hook-locations).
Restarting the CLI and inspecting `/hooks` is a useful compatibility check for
the pinned binary. A successful merge reports configuration only; it does not
claim that a live approval/question reached Android or that Android notification
permission was granted.

The helper takes provider JSON on stdin, emits no stdout/stderr, returns zero on
all ordinary validation/connection failures, and makes one attempt bounded by
450 ms including input reads. Provider timeout is two seconds. It discards tool
inputs, descriptions, cwd, transcript paths and questions, transmitting only the
provider's session identifier and the observed event kind. Delivery failure
never returns a provider permission decision.

| Provider | Template observation | Limit |
| --- | --- | --- |
| Claude | `PermissionRequest` → permission | Does not cover sandbox network permission; this event has no guaranteed request ID. |
| Claude | `PreToolUse` for `AskUserQuestion`/`ExitPlanMode` → question/plan | Pre-event may not become a visible waiting prompt. |
| Claude | elicitation notifications → question | Provider inactivity/mode gates apply. |
| Claude | `Stop` → finished | Does not mean the overall task or tests succeeded. |
| Codex | `PermissionRequest` → permission | Requires a version with this hook and normal hook trust. |
| Codex | `Stop` → finished | No generic `Notification` adapter or untested question-tool inference. |

Claude's delayed `permission_prompt` can be normalized by the helper but is not
in the default template: without an exact shared request ID, subscribing to both
that event and `PermissionRequest` would create duplicate observations. This
tradeoff leaves Claude's sandbox network permission notifications uncovered for
now and must be displayed in eventual CLI capability UI.

Sources checked 2026-10-04:
[Claude hooks](https://code.claude.com/docs/en/hooks),
[Codex hooks](https://learn.chatgpt.com/docs/hooks).

## Verification

Run `python3 -m unittest discover -s tests -p test_attention_inbox.py -v` for the
native inbox model's project/terminal grouping, unread-observation semantics,
ended-session behavior and existing-event route validation, including a session
ending between rendering and tapping. These host tests compile the actual inbox
model with an Android/bridge stub; they do not establish a real Android PTY jump
or provider-hook compatibility. Device routing evidence belongs in
`reports/compatibility`.

Run `python3 -m unittest discover -s tests -p test_attention_hooks.py -v`.
The nine tests include a real local Unix socket and cover private-payload omission,
silent delivery, absent/malformed/oversized input, deadline while stdin remains
open, distinct request identities and unsupported Codex question events, plus safe dry-run/staging, user-asset
preservation and symlink/marker rejection. They do
not claim Android, PRoot or actual provider execution. Android integration evidence
belongs in `reports/compatibility` after the parent APK smoke run.

Run `python3 -m unittest discover -s tests -p test_hook_enable.py -v` for the
eight enablement tests: dry run and host rejection, unknown-setting preservation,
exact backups and modes, idempotence, malformed/edited entries, asset integrity,
symlink/FIFO/size rejection, concurrent editor detection, installer lock, and
preservation of disabled hooks, inline TOML and provider trust files. These tests
use temporary directories and never touch the host's actual CLI settings.
