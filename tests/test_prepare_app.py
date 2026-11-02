"""Contracts that prevent a z8 APK from silently becoming a stock Termux APK."""
import importlib.util
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("prepare_app", ROOT / "tools/prepare-app.py")
prepare = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare)


class PreparationContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.tree = Path(cls.temp.name) / "generated"
        cls.source = ROOT / "upstream/termux-app"
        if not (cls.source / "app/build.gradle").exists():
            cls.temp.cleanup()
            raise unittest.SkipTest("Pinned upstream checkout is required for fork contract tests")
        shutil.copytree(cls.source, cls.tree, ignore=shutil.ignore_patterns(".git", "build", ".gradle", ".cxx"))
        cls.lock = json.loads((ROOT / "tools/sources.lock.json").read_text())
        prepare.apply_patches(cls.tree, cls.lock, "diagnostic")
        prepare.copy_overlay(ROOT, cls.tree)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def read(self, path):
        return (self.tree / path).read_text()

    def test_no_official_bootstrap_or_unsigned_shared_key_fallback(self):
        gradle = self.read("app/build.gradle")
        self.assertNotIn("downloadBootstrap", gradle)
        self.assertNotIn("github.com/termux/termux-packages", gradle)
        self.assertNotIn("testkey_untrusted", gradle)
        self.assertIn("Z8_KEYSTORE", gradle)
        self.assertIn('"Z8_HAS_BOOTSTRAP", "false"', gradle)
        self.assertEqual(list((self.tree / "app/src/main/cpp").glob("bootstrap-*.zip")), [])
        self.assertNotIn("termux-bootstrap-zip.S", self.read("app/src/main/cpp/Android.mk"))
        self.assertIn("Java_com_termux_app_TermuxInstaller_getZip", self.read("app/src/main/cpp/termux-bootstrap.c"))

    def test_application_identity_does_not_rename_java_or_jni(self):
        gradle = self.read("app/build.gradle")
        self.assertIn('applicationId "dev.devsigner.z8"', gradle)
        public = prepare.release_config.load()
        self.assertIn(f'versionCode {public["versionCode"]}\n        versionName "{public["versionName"]}"', gradle)
        self.assertIn('namespace "com.termux"', gradle)
        constants = self.read("termux-shared/src/main/java/com/termux/shared/termux/TermuxConstants.java")
        self.assertIn('TERMUX_PACKAGE_NAME = "dev.devsigner.z8"', constants)
        for name in prepare.CLASS_CONSTANTS:
            self.assertIn(name + ' = "com.termux" +', constants)
        jni_path = "terminal-emulator/src/main/jni/termux.c"
        self.assertEqual((self.tree / jni_path).read_bytes(), (self.source / jni_path).read_bytes())

    def test_manifest_only_exports_terminal_home_and_limits_permissions(self):
        manifest = ET.parse(self.tree / "app/src/main/AndroidManifest.xml").getroot()
        self.assertNotIn(prepare.ANDROID + "sharedUserId", manifest.attrib)
        self.assertEqual({e.get(prepare.ANDROID + "name") for e in manifest.findall("uses-permission")}, prepare.PERMISSIONS)
        app = manifest.find("application")
        exported = [e.get(prepare.ANDROID + "name") for e in app if e.get(prepare.ANDROID + "exported") == "true"]
        self.assertEqual(exported, ["com.termux.app.TermuxActivity"])
        activities = {e.get(prepare.ANDROID + "name"): e for e in app.findall("activity")}
        launcher = activities["com.termux.app.TermuxActivity"]
        self.assertEqual([e.get(prepare.ANDROID + "name") for e in launcher.findall("intent-filter/category")],
                         ["android.intent.category.LAUNCHER"])
        self.assertEqual(activities["com.termux.app.Z8WorkspaceActivity"].findall("intent-filter"), [])
        for private_screen in ("Z8AttentionActivity", "Z8SettingsActivity", "Z8SetupActivity"):
            screen = activities["com.termux.app." + private_screen]
            self.assertEqual(screen.get(prepare.ANDROID + "exported"), "false")
            self.assertEqual(screen.findall("intent-filter"), [])
        for removed in ("Z8GitActivity", "Z8GitHubActivity", "Z8FileSearchActivity"):
            self.assertNotIn("com.termux.app." + removed, activities)
        command = [e for e in app.findall("service") if e.get(prepare.ANDROID + "name") == "com.termux.app.RunCommandService"][0]
        self.assertEqual(command.get(prepare.ANDROID + "enabled"), "false")
        terminal_service = [e for e in app.findall("service") if e.get(prepare.ANDROID + "name") == "com.termux.app.TermuxService"][0]
        self.assertEqual(terminal_service.get(prepare.ANDROID + "foregroundServiceType"), "specialUse")
        self.assertTrue(terminal_service.find("property").get(prepare.ANDROID + "value"))
        self.assertEqual(app.get(prepare.ANDROID + "extractNativeLibs"), "true")
        self.assertEqual(app.get(prepare.ANDROID + "enableOnBackInvokedCallback"), "true")
        self.assertEqual(activities["com.termux.app.Z8AboutActivity"].get(prepare.ANDROID + "exported"), "false")

    def test_language_context_covers_primary_and_auxiliary_screens(self):
        java = self.tree / 'app/src/main/java/com/termux/app'
        screens = [java / 'TermuxApplication.java', java / 'TermuxActivity.java',
                   java / 'activities/SettingsActivity.java', java / 'activities/HelpActivity.java',
                   java / 'api/file/FileReceiverActivity.java', *java.glob('Z8*Activity.java')]
        for path in screens:
            with self.subTest(screen=path.name):
                self.assertEqual(path.read_text().count('super.attachBaseContext(com.termux.app.Z8Language.wrap(base));'), 1)
        self.assertIn('Z8Language.initialize(this);', (java / 'TermuxApplication.java').read_text())
        report = self.read('termux-shared/src/main/java/com/termux/shared/activities/ReportActivity.java')
        self.assertIn('configuration.setLocales(new android.os.LocaleList(java.util.Locale.getDefault()));', report)
        self.assertNotIn('com.termux.app.Z8Language', report)

    def test_arm64_and_sdk_build_contracts(self):
        self.assertIn("minSdkVersion=28\n", self.read("gradle.properties"))
        self.assertIn("targetSdkVersion=36\n", self.read("gradle.properties"))
        self.assertIn("compileSdkVersion=36\n", self.read("gradle.properties"))
        self.assertIn("enable false", self.read("app/build.gradle"))
        for module in ("app", "terminal-emulator", "termux-shared"):
            self.assertIn("abiFilters 'arm64-v8a'", self.read(module + "/build.gradle"))
        for module in ("terminal-emulator", "termux-shared", "terminal-view"):
            self.assertNotIn("components.default", self.read(module + "/build.gradle"))
        self.assertIn("distributionSha256Sum=72f44c9f", self.read("gradle/wrapper/gradle-wrapper.properties"))

    def test_incomplete_linux_runtime_never_silently_counts_as_installed(self):
        installer = self.read("app/src/main/java/com/termux/app/TermuxInstaller.java")
        self.assertIn("if (!BuildConfig.Z8_HAS_BOOTSTRAP)", installer)
        self.assertIn('new File(TERMUX_PREFIX_DIR, "bin/bash")', installer)
        self.assertIn('new File(TERMUX_PREFIX_DIR, ".z8-bootstrap.sha256")', installer)
        self.assertIn("!BuildConfig.Z8_BOOTSTRAP_SHA256.equals(installedHash)", installer)
        activity = self.read("app/src/main/java/com/termux/app/TermuxActivity.java")
        self.assertIn("protected void onNewIntent(Intent intent)", activity)
        self.assertIn("!home.isDirectory() && !home.mkdirs()", activity)
        self.assertIn("public void z8EnsureBootstrap(Runnable whenDone)", activity)
        client = self.read("app/src/main/java/com/termux/app/terminal/TermuxTerminalSessionActivityClient.java")
        self.assertIn("isFailSafe || !BuildConfig.Z8_HAS_BOOTSTRAP", client)
        self.assertIn("else mActivity.z8EnsureBootstrap(() -> addNewSessionChecked(false, sessionName));", client)
        self.assertIn("private void addNewSessionChecked", client)

    def test_session_drawer_has_explicit_context_menu_without_an_extra_key_bar(self):
        activity = self.read("app/src/main/java/com/termux/app/TermuxActivity.java")
        self.assertIn("import android.view.Gravity;", activity)
        self.assertIn('CONTEXT_MENU_Z8_SESSIONS = 14;', activity)
        self.assertIn('menu.add(Menu.NONE, CONTEXT_MENU_Z8_SESSIONS, Menu.NONE, com.termux.app.Z8Text.text("Sessions / New session", "세션 목록 / 새 세션"));', activity)
        self.assertIn('case CONTEXT_MENU_Z8_SESSIONS:\n                z8OpenSessions();\n                return true;', activity)
        self.assertLess(activity.index('menu.add(Menu.NONE, CONTEXT_MENU_Z8_SESSIONS'),
                        activity.index('menu.add(Menu.NONE, CONTEXT_MENU_SELECT_URL_ID'))
        self.assertIn('newSessionButton.setOnClickListener(v -> mTermuxTerminalSessionActivityClient.addProjectSession(null));', activity)
        preferences = self.read("termux-shared/src/main/java/com/termux/shared/termux/settings/preferences/TermuxPreferenceConstants.java")
        self.assertIn('DEFAULT_VALUE_SHOW_TERMINAL_TOOLBAR = false;', preferences)
        layout = "app/src/main/res/layout/activity_termux.xml"
        self.assertEqual((self.tree / layout).read_bytes(), (self.source / layout).read_bytes())

    def test_legacy_workspace_and_empty_terminal_navigation_never_create_sessions(self):
        workspace = self.read("app/src/main/java/com/termux/app/Z8WorkspaceActivity.java")
        self.assertIn('EXTRA_SHOW_SESSIONS = "dev.devsigner.z8.SHOW_SESSIONS";', workspace)
        self.assertIn('EXTRA_FOCUS_PROJECT_ID = "dev.devsigner.z8.FOCUS_PROJECT_ID";', workspace)
        self.assertIn('new Intent(this, TermuxActivity.class)', workspace)
        self.assertIn('terminal.putExtra(EXTRA_FOCUS_PROJECT_ID, project)', workspace)
        self.assertNotIn('setContentView', workspace)
        activity = self.read("app/src/main/java/com/termux/app/TermuxActivity.java")
        route = activity.split('private static boolean z8IsSessionRequest(Intent intent) {', 1)[1].split('\n    }', 1)[0]
        self.assertNotIn('EXTRA_SHOW_SESSIONS', route)
        self.assertNotIn('EXTRA_FOCUS_PROJECT_ID', route)
        self.assertIn('Z8_INTERNAL_SESSION_TOKEN.equals(intent.getStringExtra(Z8_INTERNAL_SESSION_KEY))', route)
        drawer = activity.split('public void z8ShowSessionsIfReady() {', 1)[1].split('\n    }', 1)[0]
        self.assertIn('mTerminalView.post(() -> {', drawer)
        self.assertIn('mTermuxService == null || mTermuxService.wantsToStop()', drawer)
        self.assertNotIn('getCurrentSession() == null', drawer)
        self.assertIn('!mIsVisible || isFinishing() || isDestroyed()', drawer)
        for forbidden in ('addNewSession', 'addGuestSession', 'z8OpenRequestedSession'):
            self.assertNotIn(forbidden, drawer)
        self.assertIn('savedInstanceState.putBoolean("z8_show_sessions", mZ8ShowSessionsPending);', activity)
        self.assertIn('savedInstanceState.getBoolean("z8_show_sessions", false)', activity)
        self.assertIn('z8RememberSessionDrawerRequest(getIntent());', activity)
        self.assertIn('if (z8IsSessionRequest(intent)) Z8GuestSessionLauncher.prepareIntent(intent);', activity)
        restore = activity.split('public void z8RestoreSessionSelection() {', 1)[1].split('\n    }', 1)[0]
        self.assertIn('mZ8FocusProjectPending = null;', restore)
        self.assertIn('mZ8SessionChrome.selectProject(projectId);', restore)
        self.assertNotIn('addGuestSession', restore)

    def test_exported_launcher_authenticates_internal_actions_before_allocating_work(self):
        activity = self.read("app/src/main/java/com/termux/app/TermuxActivity.java")
        self.assertIn('public static Intent z8SessionIntent(android.content.Context context)', activity)
        self.assertIn('Z8_INTERNAL_SESSION_TOKEN = java.util.UUID.randomUUID().toString();', activity)
        create = activity.split('public void onCreate(Bundle savedInstanceState)', 1)[1].split('protected void onStart()', 1)[0]
        self.assertLess(create.index('!z8IsSessionRequest(getIntent())'), create.index('Z8GuestSessionLauncher.restoreIntent'))
        self.assertIn('navigation.removeExtra(Z8WorkspaceActivity.EXTRA_PROJECT_ID);', create)
        self.assertIn('navigation.removeExtra(Z8Guest.EXTRA_GUEST_SESSION);', create)
        self.assertLess(create.index('!Z8Theme.isSetupComplete(this)'), create.index('startService(serviceIntent);'))
        theme = self.read("app/src/main/java/com/termux/app/Z8ThemeActivity.java")
        self.assertIn('if (firstSetup) startActivity(new Intent(this, Z8SetupActivity.class)', theme)
        self.assertNotIn('Z8WorkspaceActivity.class', theme)

    def test_initial_download_is_gated_before_any_project_or_command_launch(self):
        activity = self.read('app/src/main/java/com/termux/app/TermuxActivity.java')
        create = activity.split('public void onCreate(Bundle savedInstanceState)', 1)[1].split('protected void onStart()', 1)[0]
        self.assertLess(create.index('!Z8Theme.isSetupComplete(this)'), create.index('!Z8InitialSetup.isReady(this)'))
        self.assertLess(create.index('!Z8InitialSetup.isReady(this)'), create.index('Z8GuestSessionLauncher.restoreIntent'))
        setup = self.read('app/src/main/java/com/termux/app/Z8SetupActivity.java')
        self.assertIn('meteredConsent.setChecked(false)', setup)
        self.assertIn('NET_CAPABILITY_VALIDATED', setup)
        self.assertIn('NET_CAPABILITY_NOT_METERED', setup)
        self.assertIn('NetworkCapabilities.TRANSPORT_CELLULAR', setup)
        self.assertIn('if (!network.online || network.metered && !meteredConsent.isChecked()) return;', setup)
        self.assertIn('if (!network.key.equals(previousNetwork)) { refresh(); return; }', setup)
        self.assertIn('foreground && service != null && Z8InitialSetup.hasConsent(this)', setup)
        request = setup.split('private void request() {', 1)[1].split('private void updateInstallEnabled()', 1)[0]
        self.assertIn('Z8InitialSetup.request(service, network.metered && meteredConsent.isChecked())', request)
        for destructive in ('stopService(', 'Z8Projects(', 'addGuestSession', 'EXTRA_GUEST_SESSION'):
            self.assertNotIn(destructive, setup)

    def test_project_selection_and_last_session_exit_preserve_terminal_home_without_launch(self):
        chrome = self.read("app/src/main/java/com/termux/app/Z8SessionChrome.java")
        select = chrome.split('private void selectProject(String id, boolean closeDrawer) {', 1)[1].split('private void clearTerminal()', 1)[0]
        for forbidden in ('addGuestSession', 'addNewSession', 'openShell(', 'startActivity('):
            self.assertNotIn(forbidden, select)
        self.assertIn('if (!entry.projectId.equals(id)) continue;', select)
        self.assertIn('else clearTerminal();', select)
        clear = chrome.split('private void clearTerminal() {', 1)[1].split('private void createForCurrent()', 1)[0]
        self.assertIn('attachSession(null)', clear)
        self.assertNotIn('finishIfRunning', clear)
        self.assertIn('emptyTerminal.setVisibility(hasSession || preparation != null || browserSelected ? View.GONE : View.VISIBLE);', chrome)
        for removed in ('openFiles', 'Z8WorkspaceActivity.class', 'Z8GitActivity.class', 'Z8GitHubActivity.class', '첫 세션 열기'):
            self.assertNotIn(removed, chrome)
        self.assertIn('Z8Text.text("Create project", "프로젝트 만들기"), this::createProject', chrome)
        self.assertNotIn('Z8EnvironmentActivity.intent(activity, created.id)', chrome)
        self.assertIn('Z8GuestSessionLauncher.request(service, request, created.id, null, created.name, null)', chrome)
        # File removal belongs to the service-backed coordinator, so rotating or
        # leaving this screen cannot skip stopping a project's live terminals.
        self.assertIn('Z8ProjectRemoval.begin(activity.getTermuxService(), projectId,', chrome)
        self.assertNotIn('Z8Guest.deleteProject(', chrome)
        self.assertIn('if (!canDeleteProject(projectId))', chrome)
        client = self.read("app/src/main/java/com/termux/app/terminal/TermuxTerminalSessionActivityClient.java")
        on_start = client.split('public void onStart() {', 1)[1].split('public void onResume()', 1)[0]
        self.assertIn('mActivity.z8RestoreSessionSelection();', on_start)
        self.assertNotIn('getCurrentStoredSessionOrLast()', on_start)
        remove = client.split('public void removeFinishedSession(', 1)[1].split('public void termuxSessionListNotifyUpdated()', 1)[0]
        self.assertNotIn('finishActivityIfNotFinishing', remove)
        self.assertNotIn('addNewSession', remove)
        self.assertIn('mActivity.z8RestoreSessionSelection();', remove)
        self.assertIn('Z8ProjectRemoval.protects(finishedSession)', remove)
        finished = client.split('public void onSessionFinished(', 1)[1].split('public void onCopyTextToClipboard', 1)[0]
        self.assertIn('Z8ProjectRemoval.protects(finishedSession)', finished)
        self.assertIn('mActivity.z8OnSessionSelected(session);', client)

    def test_local_mvp_navigation_exposes_settings_and_inbox_without_remote_routes(self):
        chrome = self.read("app/src/main/java/com/termux/app/Z8SessionChrome.java")
        self.assertIn('Z8SettingsActivity.intent(activity, selectedProject)', chrome)
        self.assertIn('new Intent(activity, Z8AttentionActivity.class)', chrome)
        for remote_entry in ('Z8Remote', 'remoteMode', 'remoteHosts', 'switchLocation', 'remote-shell'):
            self.assertNotIn(remote_entry, chrome)
        settings = self.read("app/src/main/java/com/termux/app/Z8SettingsActivity.java")
        normal, developer = settings.split('if (BuildConfig.DEBUG)', 1)
        self.assertIn('Z8ThemeActivity.class', normal)
        self.assertIn('Settings.ACTION_APP_NOTIFICATION_SETTINGS', normal)
        for diagnostic_route in ('Z8DiagnosticsActivity.class', 'Z8EnvironmentActivity.intent', 'Z8AttentionBridge.sendDiagnostic'):
            self.assertNotIn(diagnostic_route, normal)
            self.assertIn(diagnostic_route, developer)

    def test_project_intent_never_falls_back_to_native_and_empty_navigation_never_launches(self):
        activity = self.read("app/src/main/java/com/termux/app/TermuxActivity.java")
        launch = activity.split('private void z8OpenRequestedSession(Intent intent) {', 1)[1].split('public void z8EnsureBootstrap', 1)[0]
        self.assertIn('if (!z8IsSessionRequest(intent)) {', launch)
        self.assertLess(launch.index('z8OpenSessions();'), launch.index('final boolean guest'))
        self.assertIn('intent.hasExtra(Z8WorkspaceActivity.EXTRA_PROJECT_ID)\n            || intent.getBooleanExtra(Z8Guest.EXTRA_GUEST_SESSION, false)', launch)
        client = self.read("app/src/main/java/com/termux/app/terminal/TermuxTerminalSessionActivityClient.java")
        project_launch = client.split('public void addProjectSession(String name) {', 1)[1].split('public void addGuestSession(', 1)[0]
        self.assertNotIn('addNewSession(', project_launch)
        self.assertNotIn('Z8WorkspaceActivity.class', project_launch)
        self.assertIn('mActivity.z8CreateProjectSession(name);', project_launch)
        finished = client.split('public void onSessionFinished(', 1)[1].split('public void onCopyTextToClipboard', 1)[0]
        self.assertIn('origin != null && origin.action != null && !isPluginExecutionCommandWithPendingResult', finished)
        self.assertIn('Z8Guest.invalidateReadiness(origin.projectId)', finished)

    def test_session_chrome_follows_activity_lifecycle_and_keeps_terminal_clients(self):
        activity = self.read("app/src/main/java/com/termux/app/TermuxActivity.java")
        dispatch = activity.split('public boolean dispatchKeyEvent(', 1)[1].split('\n    }', 1)[0]
        self.assertLess(dispatch.index('Z8ShortcutHelp.dispatch'), dispatch.index('super.dispatchKeyEvent'))
        for method in ('protected void onPause()', 'public void onWindowFocusChanged(', 'public void onConfigurationChanged('):
            self.assertIn('Z8ShortcutHelp.dismiss(this)', activity.split(method, 1)[1].split('\n    }', 1)[0])
        self.assertIn('private Z8SessionChrome mZ8SessionChrome;', activity)
        self.assertIn('registerForContextMenu(mTerminalView);\n        mZ8SessionChrome = new Z8SessionChrome(this);\n'
                      '        mZ8SessionChrome.install();', activity)
        self.assertLess(activity.index('setToggleKeyboardView();'), activity.index('mZ8SessionChrome.install();'))
        self.assertLess(activity.index('mZ8SessionChrome.install();'), activity.index('startService(serviceIntent);'))
        self.assertIn('Z8GuestSessionLauncher.observe(this);\n        if (mZ8SessionChrome != null) mZ8SessionChrome.onResume();', activity)
        stopped = activity.split('protected void onStop() {', 1)[1].split('\n    }', 1)[0]
        self.assertIn('mZ8SessionChrome.onStop();', stopped)
        self.assertIn('mIsVisible = false;', stopped)
        self.assertIn('mTermuxTerminalSessionActivityClient.onStop();', stopped)
        destroyed = activity.split('public void onDestroy() {', 1)[1].split('\n    }', 1)[0]
        self.assertIn('mZ8SessionChrome.dispose();\n            mZ8SessionChrome = null;', destroyed)
        self.assertIn('mTermuxService.unsetTermuxTerminalSessionClient();', destroyed)
        self.assertIn('unbindService(this);', destroyed)
        refresh = activity.split('public void z8RefreshSessionChrome() {', 1)[1].split('\n    }', 1)[0]
        self.assertIn('if (mZ8SessionChrome != null) mZ8SessionChrome.refresh();', refresh)
        self.assertIn('mTermuxSessionListViewController.notifyDataSetChanged();\n        z8RefreshSessionChrome();', activity)
        drawer = activity.split('public void z8ShowSessionsIfReady() {', 1)[1].split('\n    }', 1)[0]
        self.assertIn('z8OpenSessions();', drawer)
        client = self.read("app/src/main/java/com/termux/app/terminal/TermuxTerminalSessionActivityClient.java")
        title_changed = client.split('public void onTitleChanged(', 1)[1].split('\n    }', 1)[0]
        self.assertIn('termuxSessionListNotifyUpdated();', title_changed)
        finished = client.split('public void onSessionFinished(', 1)[1].split('\n    }', 1)[0]
        self.assertIn('mActivity.z8RefreshSessionChrome();', finished)
        text_changed = client.split('public void onTextChanged(', 1)[1].split('\n    }', 1)[0]
        self.assertNotIn('z8RefreshSessionChrome', text_changed)
        self.assertIn('mActivity.getTerminalView().onScreenUpdated();', text_changed)

    def test_idle_service_keeps_bound_navigation_without_foreground_or_stopping_launcher(self):
        activity = self.read('app/src/main/java/com/termux/app/TermuxActivity.java')
        service = self.read('app/src/main/java/com/termux/app/TermuxService.java')
        client = self.read('app/src/main/java/com/termux/app/terminal/TermuxTerminalSessionActivityClient.java')
        self.assertIn('bindService(serviceIntent, this, Context.BIND_AUTO_CREATE)', activity)
        idle = service.split('private void z8IdleService() {', 1)[1].split('\n    }', 1)[0]
        self.assertIn('mZ8Idle = true;', idle)
        self.assertIn('runStopForeground();', idle)
        self.assertIn('stopSelf();', idle)
        self.assertNotIn('Z8GuestSessionLauncher.stop', idle)
        self.assertNotIn('mWantsToStop =', idle)
        resume = service.split('public synchronized void z8AcquireExecution() {', 1)[1].split('\n    }', 1)[0]
        self.assertIn('if (mWantsToStop || !mZ8Idle) return;', resume)
        self.assertLess(resume.index('mZ8Idle = false;'), resume.index('startService('))
        self.assertIn('runStartForeground();', resume)
        notification = service.split('public synchronized void updateNotification() {', 1)[1].split('\n    }', 1)[0]
        self.assertIn('if (mWantsToStop) return;', notification)
        self.assertIn('z8IdleService();', notification)
        self.assertIn('z8AcquireExecution();', notification)
        explicit = service.split('private void requestStopService() {', 1)[1].split('\n    }', 1)[0]
        self.assertIn('Z8GuestSessionLauncher.stop(this);', explicit)
        self.assertIn('mWantsToStop && mTermuxTerminalSessionActivityClient != null', explicit)
        self.assertIn('mTermuxTerminalSessionActivityClient.z8OnServiceStopped();', explicit)
        self.assertIn('public void z8OnServiceStopped() { mActivity.finishActivityIfNotFinishing(); }', client)

    def test_notification_stop_verifies_ptys_before_finishing_and_preserves_failures(self):
        service = self.read('app/src/main/java/com/termux/app/TermuxService.java')
        stop = service.split('private void actionStopService() {', 1)[1].split('\n    }', 1)[0]
        self.assertIn('if (mWantsToStop || mZ8StopRequested) return;', stop)
        self.assertIn('Z8ProjectRemoval.stopAllSessions(this, error -> {', stop)
        self.assertNotIn('killAllTermuxExecutionCommands', stop)
        self.assertNotIn('Z8GuestSessionLauncher.stop', stop)
        self.assertLess(stop.index('stopAllSessions'), stop.index('mWantsToStop = true;'))
        failure = stop.split('if (error != null) {', 1)[1].split('\n            }', 1)[0]
        self.assertIn('mZ8StopMessage = error;', failure)
        self.assertIn('updateNotification();', failure)
        self.assertIn('return;', failure)
        self.assertNotIn('requestStopService', failure)
        self.assertIn('if (mZ8StopMessage != null) notificationText = mZ8StopMessage;', service)
        creation = service.split('public synchronized TermuxSession createTermuxSession(ExecutionCommand executionCommand) {', 1)[1]
        self.assertTrue(creation.lstrip().startswith('if (mWantsToStop || mZ8StopRequested) return null;'))

    def test_first_preparation_uses_service_card_without_new_terminal_intent(self):
        service = self.read('app/src/main/java/com/termux/app/TermuxService.java')
        notification = service.split('private Notification buildNotification() {', 1)[1].split('private void setupNotificationChannel()', 1)[0]
        self.assertIn('if (Z8PreparationNotification.decorate(builder, this)) return builder.build();', notification)
        self.assertLess(notification.index('Z8PreparationNotification.decorate'), notification.index('builder.addAction('))
        helper = self.read('app/src/main/java/com/termux/app/Z8PreparationNotification.java')
        route = helper.split('private static PendingIntent projectIntent(', 1)[1].split('private static void postResult(', 1)[0]
        self.assertIn('Z8WorkspaceActivity.EXTRA_FOCUS_PROJECT_ID', route)
        for launch_extra in ('EXTRA_GUEST_SESSION', 'EXTRA_PROJECT_ID', 'z8SessionIntent'):
            self.assertNotIn(launch_extra, route)
        self.assertIn('PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE', route)
        self.assertIn('owner.wakeLock.acquire(WAKE_TIMEOUT_MS)', helper)
        self.assertNotIn('owner.wakeLock.acquire()', helper)
        result = helper.split('private static void postResult(', 1)[1].split('private static String label(', 1)[0]
        self.assertIn('!notifications.areNotificationsEnabled()', result)
        self.assertNotIn('detail', result)

    def test_copy_mode_and_open_shortcut_respect_session_chrome_layout(self):
        activity = self.read("app/src/main/java/com/termux/app/TermuxActivity.java")
        open_sessions = activity.split('public void z8OpenSessions() {', 1)[1].split('\n    }', 1)[0]
        self.assertIn('if (mZ8SessionChrome != null) mZ8SessionChrome.openSessions();', open_sessions)
        self.assertIn('else getDrawer().openDrawer(Gravity.LEFT);', open_sessions)
        copy_mode = activity.split('public void z8SetSessionCopyMode(boolean copying) {', 1)[1].split('\n    }', 1)[0]
        self.assertIn('if (mZ8SessionChrome != null) mZ8SessionChrome.setCopyMode(copying);', copy_mode)
        self.assertIn('else getDrawer().setDrawerLockMode(copying ? DrawerLayout.LOCK_MODE_LOCKED_CLOSED : DrawerLayout.LOCK_MODE_UNLOCKED);', copy_mode)
        client = self.read("app/src/main/java/com/termux/app/terminal/TermuxTerminalViewClient.java")
        copy_changed = client.split('public void copyModeChanged(boolean copyMode) {', 1)[1].split('\n    }', 1)[0]
        self.assertIn('mActivity.z8SetSessionCopyMode(copyMode);', copy_changed)
        self.assertNotIn('setDrawerLockMode', copy_changed)
        self.assertIn('keyCode == KeyEvent.KEYCODE_DPAD_RIGHT) {\n                mActivity.z8OpenSessions();', client)
        self.assertIn('keyCode == KeyEvent.KEYCODE_DPAD_LEFT) {\n                mActivity.getDrawer().closeDrawers();', client)
        self.assertNotIn('mActivity.getDrawer().openDrawer(', client)
        self.assertIn('mActivity.getTerminalView().requestFocus();', client)


class RejectionContracts(unittest.TestCase):
    def test_changed_patch_anchor_fails_closed(self):
        with self.assertRaises(prepare.PrepareError):
            prepare.replace_exact("changed", "original", "new")
        with self.assertRaises(prepare.PrepareError):
            prepare.replace_exact("original original", "original", "new")

    def test_source_revision_and_dirty_checkout_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp)
            with patch.object(prepare, "git_output", return_value="wrong\n"):
                with self.assertRaisesRegex(prepare.PrepareError, "HEAD differs"):
                    prepare.verify_source(source, "a" * 40, "git")
            with patch.object(prepare, "git_output", side_effect=["a" * 40 + "\n", " M app/build.gradle\n"]):
                with self.assertRaisesRegex(prepare.PrepareError, "not pristine"):
                    prepare.verify_source(source, "a" * 40, "git")

    def test_output_symlink_cannot_delete_another_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "outside").mkdir()
            sentinel = root / "outside/keep"
            sentinel.write_text("keep")
            (root / ".local").mkdir()
            (root / ".local/build-src").symlink_to(root / "outside", target_is_directory=True)
            with self.assertRaises(prepare.PrepareError):
                prepare.checked_local(root)
            self.assertEqual(sentinel.read_text(), "keep")

    def test_mismatched_prefix_or_stock_identity_rejected(self):
        lock = {"applicationId": "dev.devsigner.z8", "prefix": "/data/data/com.termux/files/usr", "termuxApp": {"commit": "a" * 40}}
        with self.assertRaises(prepare.PrepareError):
            prepare.validate_lock(lock)
        lock.update(applicationId="com.termux", prefix="/data/data/com.termux/files/usr")
        with self.assertRaises(prepare.PrepareError):
            prepare.validate_lock(lock)

    def test_traversal_and_symlink_source_not_copied(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ("source", "dest"):
                (root / name).mkdir()
            (root / "source/link").symlink_to(root / "dest")
            for name in ("../escape", "/absolute", "link"):
                with self.assertRaises(prepare.PrepareError):
                    prepare.copy_tracked(root / "source", root / "dest", [name])


class RuntimeArchiveContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.archive = self.root / "bootstrap-aarch64.zip"
        self.manifest = self.root / "manifest.json"
        self.lock = {
            "applicationId": "dev.devsigner.z8", "prefix": "/data/data/dev.devsigner.z8/files/usr",
            "termuxPackages": {"commit": "a" * 40},
        }
        self.metadata = dict(schemaVersion=1, applicationId=self.lock["applicationId"],
            prefix=self.lock["prefix"], architecture="aarch64", archive=self.archive.name,
            termuxPackagesCommit="a" * 40)
        # A synthetic ELF header exercises inspection only; it is not executable.
        self.elf = bytearray(64)
        self.elf[:6] = b"\x7fELF\x02\x01"
        self.elf[18:20] = (183).to_bytes(2, "little")

    def tearDown(self):
        self.temp.cleanup()

    def fixture(self, extra=None, links="bash←bin/sh\n", elf=None):
        with zipfile.ZipFile(self.archive, "w") as bundle:
            bundle.writestr("bin/bash", self.elf if elf is None else elf)
            bundle.writestr("SYMLINKS.txt", links)
            for name, content in (extra or {}).items():
                bundle.writestr(name, content)
        self.metadata["sha256"] = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        self.manifest.write_text(json.dumps(self.metadata))

    def test_matching_metadata_and_safe_archive_pass_inspection_only(self):
        self.fixture()
        path, sha = prepare.verify_runtime(self.manifest, self.lock)
        self.assertEqual(path, self.archive)
        self.assertEqual(sha, self.metadata["sha256"])

    def test_matching_hash_cannot_hide_stock_prefix(self):
        self.fixture(extra={"etc/config": b"prefix=/data/data/com.termux/files/usr"})
        with self.assertRaisesRegex(prepare.PrepareError, "Stock com.termux prefix"):
            prepare.verify_runtime(self.manifest, self.lock)

    def test_wrong_elf_architecture_rejected(self):
        self.elf[18:20] = (62).to_bytes(2, "little")
        self.fixture()
        with self.assertRaisesRegex(prepare.PrepareError, "Expected aarch64 ELF"):
            prepare.verify_runtime(self.manifest, self.lock)

    def test_traversal_or_escaping_symlink_rejected_even_with_matching_hash(self):
        self.fixture(extra={"../escape": b"bad"})
        with self.assertRaisesRegex(prepare.PrepareError, "Unsafe bootstrap entry"):
            prepare.verify_runtime(self.manifest, self.lock)
        self.fixture(links="../../escape←bin/sh\n")
        with self.assertRaisesRegex(prepare.PrepareError, "escapes"):
            prepare.verify_runtime(self.manifest, self.lock)

    def test_placeholder_mismatch_and_unpinned_provenance_rejected(self):
        for field, value in (("sha256", "0" * 64), ("sha256", "b" * 64),
                             ("termuxPackagesCommit", "b" * 40),
                             ("applicationId", "com.termux"), ("archive", "../outside.zip")):
            self.fixture()
            metadata = dict(self.metadata, **{field: value})
            self.manifest.write_text(json.dumps(metadata))
            with self.subTest(field=field, value=value):
                with self.assertRaises(prepare.PrepareError):
                    prepare.verify_runtime(self.manifest, self.lock)


if __name__ == "__main__":
    unittest.main()
