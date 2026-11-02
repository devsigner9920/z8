# Native local workspace and files

> 역사적 구현 문서: 2026-10-05 사용자 요청으로 이 네이티브 화면의 앱 진입점과 Activity 등록을 제거했다. 현재는 터미널에서 파일·git·gh 도구를 사용한다. 아래 내용은 제거 전 구현과 검증 기록이며 현재 제공 UI가 아니다.

The diagnostic APK now has a working native project/file workflow. This screen uses the selected z8 palette and a two-pane layout from 720 dp; smaller windows show projects, files and the editor in sequence. It does not imply that PRoot, Git or an AI CLI is installed.

## Storage and session contract

- Each new project gets an opaque UUID and a dedicated `files/z8/projects/<UUID>/source` directory. Its display name and most recent open time are stored separately in `project.properties`.
- Linux environment images must use a different directory. Resetting or reinstalling an environment must never delete `source`.
- The file browser opens actual app-private source files. Navigation does not send `cd`, keystrokes or any other input to an existing terminal.
- “여기서 새 터미널 열기” sends a private explicit intent with `Z8WorkspaceActivity.EXTRA_PROJECT_ID` and `EXTRA_PROJECT_CWD`. The latter is relative to the project source root, with the empty string meaning the root. The receiving adapter must resolve the project and validate that directory again before starting a new PTY.
- Project source is mapped into its Linux guest at `/workspace`; HOME is `/z8/home`. Missing rootfs/PRoot opens the project environment preparation screen. Project requests never silently start a native Android shell.

## Supported operations

Create a named project, reopen a recent project, navigate folders, create files/folders, rename an entry without replacing another, and explicitly delete files or empty folders. Non-empty folders require terminal handling; there is no implicit recursive delete. Symlinks appear in the listing but are not followed, edited, renamed or removed through this UI.

The editor reads UTF-8 text up to 128 KiB and rejects binary/NUL content and invalid UTF-8. It keeps the draft, original baseline, disk version and cursor across folding or rotation. Every edited draft is checkpointed after a 350 ms debounce and on pause to an atomic app-private file outside source/rootfs. A new Activity restores it when the project opens; recovery does not change the source. The application-owned serial queue orders checkpoint/read/save/clear across Activity replacement. Abrupt termination before a pending checkpoint reaches disk can still lose the latest keystrokes. Every navigation route offers Save and continue, Discard and continue, or Keep editing. The original file is never automatically saved.

Saving compares the original content SHA-256, size, modification time and file identity with the current disk version. It checks again immediately before replacing the file, writes a temporary file in the same directory, flushes that file, preserves POSIX permissions and atomically replaces the original. A mismatch leaves both the current disk contents and the editor draft intact. The conflict dialog provides Copy draft and Save as a new file directly; automatic merging and forced overwrite are not offered.

Path components reject traversal and separators; roots and descendants are checked for symbolic links and canonical containment. These checks prevent ordinary path and symlink escapes. They are not a kernel security boundary against a hostile process with the same Android UID. A process can still race the final check and rename; cross-process locking or a descriptor-relative native filesystem layer is needed if that threat becomes part of scope.

## Validation

`tests/test_workspace.py` compiles the actual Java storage helpers and exercises 18 scenarios in temporary folders: project persistence, source layout, path validation, UTF-8 read/save, external-write and same-content replacement conflicts, directory/file/root symlink rejection, safe rename/delete, binary rejection and the size limit. It requires a JDK; the local toolchain is used when present.

APK checks remain separate: verify project creation, file editing, conflict handling after a terminal write, rotation draft retention, and that a new folder terminal has the correct `pwd` while an existing terminal retains its session and cwd. Host helper tests alone are not Android integration evidence.

`tests/test_drafts.py` exercises disk recovery, Unicode/cursor/baseline preservation, project separation, external-edit conflicts, atomic replacement, bounds and symlink rejection. Fresh API 37 integration evidence is in the correction report (비공개 내부 검증 기록: `reports/compatibility/2026-10-05-fixes/index.html`).

This file/editor increment does not itself implement cloning/importing repositories, syntax highlighting, recursive delete or project deletion. Git and Linux environment workflows are documented separately.

## Bounded filename search

`Z8FileSearchActivity.intent(context, projectId)` opens a native, read-only search
screen. Search runs only after pressing **검색** or **다시 검색**, on a worker
thread. It matches the filename or relative path using `Locale.ROOT` lowercasing;
it does not scan file contents or build an index. The query survives folding and
rotation. An interrupted screen asks the user to search again for fresh results
instead of restarting a scan while they type.

The traversal skips directories named `.git`, `node_modules`, `build`, and
`.gradle`, and skips all symbolic links. Other hidden directories remain eligible.
It stops at 200 results, 20,000 examined entries, depth 32, or a cooperative
three-second deadline. The UI displays those bounds, skipped counts and the
reason when a result set is incomplete. As with other filesystem calls, a single
blocked operating-system read cannot be interrupted by the Java deadline.
Paths that the existing editor cannot safely open, including components longer
than 120 characters or containing control characters/backslashes, are skipped
with an explicit incomplete-result reason. Search does not write any files.

The caller uses request code `Z8FileSearchActivity.REQUEST_OPEN` (8301). Selecting
a result returns `RESULT_OK` with `EXTRA_PROJECT_ID`, `EXTRA_PATH` (relative to the
source root), and `EXTRA_DIRECTORY`. The workspace must compare the returned
project ID with the current project and validate the path again through
`Z8Files.directory` or `Z8Files.read`; an AI CLI may have changed it since the
search. Existing dirty-editor confirmation remains in force. No terminal input
is emitted by search or result selection.

Root/ancestor/descendant links and canonical escapes are checked during traversal.
These are the same ordinary-containment guarantees and same-UID race limitations
as the existing file browser, not a stronger isolation boundary.
`tests/test_file_search.py` compiles the real Java helper and checks 16 cases,
including Unicode and device-locale behavior, relative matching, ignored and
hidden directories, root/ancestor/file/directory links, content exclusion,
result/entry/depth/time limits, cancellation and unsupported names. APK layout,
activity return handling and folding behavior require separate Android tests.
