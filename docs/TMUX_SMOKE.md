# Native tmux continuity probe

`tools/smoke-tmux.py` is an explicit verification tool for the dedicated
`emulator-5580` / `z8-api37-arm64-16k` emulator. It requires the runtime APK and its
matching bootstrap to have already been installed. Run it after the native
runtime smoke and after other UI tests have finished:

```sh
python3 tools/smoke-tmux.py
```

The probe checks the local artifact SHA-256, installed APK SHA-256, embedded
runtime manifest, installed bootstrap marker and kernel page size. It refuses
a different APK, emulator or page size. It does not install an APK, update a
prefix, force-stop the app or run on a physical device.

It opens **실행 진단 → Linux 런타임 터미널 열기** to create a fresh native
app-owned terminal, even if a guest terminal was previously selected. It then
creates exactly one tmux server on a random private socket below
`files/z8/tmux-smoke/<id>`, with configuration loading disabled and the own-prefix
bash as the test pane. No existing tmux socket or session is targeted.

Commands entered through the actual terminal create an unexported variable and
record the pane's bash PID. A separate `run-as` client detaches this one session.
Another terminal command proves that the original outer bash returned. The
terminal reattaches to the same tmux session, where a final typed command must
read the same PID and unexported value. Client TTY observations verify actual
PTY attachment instead of merely checking that a tmux process exists.

The tool writes `reports/compatibility/tmux-continuity.json` and captures
`emulator-tmux-resumed.png` only after the comparison succeeds. It always attempts
to kill only its owned server via the unique socket. The fresh outer native
shell and small private proof directory remain for inspection; existing native,
guest and user tmux sessions remain untouched. No attention token, complete
environment, conversation or arbitrary terminal output is read into the report.

A passing report proves a manual native tmux detach/reattach cycle on that APK
and emulator. It does not prove product-managed project sessions, the Ctrl-B d
gesture, PRoot persistence, AI authentication/workflows, screen-off behavior,
process-death recovery or Galaxy hardware compatibility. Those acceptance tests
remain separate.

Review-only validation uses Python compilation and shell syntax checks of the
generated fixed probe; these do not execute ADB or establish device evidence.
