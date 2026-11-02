# Project Git workflow

> 역사적 구현 문서: 2026-10-05 사용자 요청으로 이 네이티브 화면의 앱 진입점과 Activity 등록을 제거했다. 현재는 터미널에서 파일·git·gh 도구를 사용한다. 아래 내용은 제거 전 구현과 검증 기록이며 현재 제공 UI가 아니다.

The private `Z8GitActivity` presents real repository state for one z8 project. The integration entry point is `Z8GitActivity.intent(context, projectId)`. Register the Activity with `exported="false"` and open it explicitly from the project browser.

## Execution environment

An installed project rootfs selects **LOCAL · 프로젝트 Linux Git**. `Z8GuestGit` uses the same validated `Z8Guest.commandFor()` PRoot launch, project source bind, `/z8/home`, temporary directory, guest system configuration, user configuration, hooks and toolchain as the project terminal. Git runs as `/usr/bin/git -C /workspace`, with fixed `GIT_DIR=/workspace/.git` and `GIT_WORK_TREE=/workspace`. The actual guest Git executable and own-prefix PRoot must be available. A missing, broken or incomplete guest never falls back to Android Git. Returning from the environment screen refreshes this selection.

Projects without a rootfs have an explicitly labeled **LOCAL · Android Git (진단)** path. It checks only `TermuxConstants.TERMUX_PREFIX_DIR_PATH + "/bin/git"`. There is no fallback to Android system commands, desktop Git, another installed app, or fabricated repository results. If the selected executable is absent or cannot execute, the screen explains the prerequisite, links to the Linux environment screen and offers no Git mutation buttons. A guest Git read failure keeps the guest selection and removes stale mutation controls.

The Android diagnostic adapter uses a separate per-project `git-home` and `git-tmp`. The guest adapter instead preserves normal `/etc/gitconfig`, `/z8/home/.gitconfig` and `/z8/home/.config/git` discovery; it never passes the diagnostic adapter's `GIT_CONFIG_NOSYSTEM` or `GIT_CONFIG_GLOBAL` overrides. Neither adapter copies credentials or settings from other projects. Existing repository configuration and commit hooks remain active. The UI asks for a commit author; name/email are per-command `-c` values and do not write identity settings. Configured signing is not bypassed, so an unavailable signer can fail with an actionable Git error.

## Actual workflow

1. Open Git from a project. With Git available, show whether a repository exists and read its branch and changed files.
2. A project without `.git` may explicitly create a local repository on `main`. This action keeps source files and performs no automatic stage or commit.
3. Select a change to read the working-tree or staged diff. An untracked file uses an actual `git diff --no-index` comparison with `/dev/null`; binary differences are reported by Git.
4. Stage only the selected path, plus its original path for a rename. A global `--literal-pathspecs` option and a separate `--` ensure that leading dashes and pathspec-looking names stay literal.
5. Unstage via `git reset HEAD -- <paths>` when HEAD exists. Before the first commit, use `git rm --cached --force --ignore-unmatch -- <paths>`. Both preserve working files.
6. The commit dialog lists staged files, takes a message and author, and requires a user press of “커밋”. It rechecks the index digest and HEAD before invoking `git commit --file=-`. New terminal changes to the staged set reject a stale confirmation. No `--no-verify`, signing bypass, forced push, or automatic push is used.

7. The branch menu lists up to 500 local branches and supports creating or switching to an explicit branch. It validates the branch name, expected HEAD/index and a clean working tree; it never forces a checkout or auto-stashes files.
8. The remote menu requires selection of a registered remote and a concrete confirmation. Fetch updates remote refs. Pull targets the current named branch with `--ff-only --no-rebase`, disables automatic stashing and requires clean files. Push sends `HEAD` to the same named remote branch with an explicit refspec and no force option. Remote configuration is rechecked before execution; a changed destination rejects the pending confirmation. Multi-URL remotes are left to the terminal. Displayed destination labels omit URL credentials and query strings; failed network operations expose a generic exit status, not credential-bearing remote output.

The parser uses Git's stable porcelain v1 `-z` format; rename records contain destination then source, each NUL-delimited. Paths are decoded as strict UTF-8. See the official [git-status format](https://git-scm.com/docs/git-status) and [Git literal pathspec options](https://git-scm.com/docs/git).

## Bounds and failure behavior

- Work runs on a background executor. Each subprocess has a 30-second limit and stdout/stderr are each capped at 1 MiB. The status list is capped at 2,000 entries, with a virtualized native list; the index digest is capped at 32 MiB.
- `ProcessBuilder` receives an argv list. File paths, author values and commit messages are never interpolated into a shell command. Commit messages travel through stdin.
- The guest adapter rewrites only the internally constructed executable, `-C` and explicit `init` destination. User filenames and identity values stay literal arguments. PRoot receives no shell `-c` command. Guest launch credentials, if present in a process environment, are never copied into argv. The guest process clears Android preload/prefix overrides and uses its own `PATH`.
- Inherited `GIT_*` redirections are cleared and known project `GIT_DIR`/`GIT_WORK_TREE` are set explicitly. Interactive credential prompting and pagers are disabled. State refresh performs no network request. Fetch/pull/push are separate explicit actions; no operation automatically retries after an ambiguous timeout. A user-supplied repository hook or filter can still run its own programs under normal Git semantics.
- Per-process fsmonitor integration is disabled for predictable bounded reads; repository hooks for commit are preserved. Color/external diff/textconv helpers are disabled for the plain native diff view.
- Project and selected paths reject traversal, metadata staging and symlink escapes. This increment supports a normal `.git` directory contained in the project. Linked worktrees, Gitfiles, symlink entries and arbitrary external repositories require the terminal or a later adapter.
- Timeout/error reports do not claim that Git made no change. Refresh to inspect actual state. The adapter terminates the Git process, but cannot promise to stop detached descendants started by repository hooks. It never deletes `index.lock` automatically.
- The index/HEAD check narrows accidental commit races; it is not a cross-process transaction. Another process can still mutate the repository after that check. Same-UID hostile processes are outside this app-level containment guarantee.

## Evidence and remaining validation

`tests/test_git.py` compiles the actual Java helpers and invokes a test-only host Git executable in temporary repositories. It verifies explicit init, unborn branch, real status/diffs, stage/unstage/commit, filenames with spaces and leading dashes, literal pathspec handling, nonpersistent author overrides, stale index rejection, NUL rename/conflict parsing, path/link rejection, literal argv, blocked-stdin timeout, and output caps. A capture runner separately verifies the real guest wrapper's PRoot arguments, fixed guest paths, preserved normal configuration, environment-only nonce handling, unchanged literal filenames/stdin/limits, rejected unexpected command shapes, and unavailable-guest behavior.

The test-only constructor is package-private and is not an executable selection feature in the Android app. The capture runner does not execute PRoot, and host tests do not establish Android or guest compatibility. APK validation must separately confirm the unavailable-runtime screen, then repeat the real workflow after Git is installed in that project's guest, including a normal guest user configuration and commit hook.

The host test also creates an isolated bare remote and a peer clone, verifies branch creation/switching, real push/fetch/fast-forward pull, remote file updates, dirty-tree rejection, stale remote rejection and credential-free confirmation labels. These tests contact no external server. GitHub login/reads are provided by the separate GitHub screen. Stash, forced resets and linked worktrees remain terminal workflows. Guest execution and authenticated network operations require device verification after guest Git installation.

## Recoverable commit draft (2026-10-05)

Commit messages and author fields are retained per project in app-private preferences when the form closes or the Activity pauses, and in instance state during recreation. A visible commit form reopens after fresh Git status is read following rotation. Failed commits retain their message for correction; a successful commit clears the matching message. Reopening still re-reads staged files and author settings and requires an explicit commit action. Saved fields never auto-commit or auto-push. Dialogs and primary/secondary actions share the native Z8 palette and 48 dp controls.
