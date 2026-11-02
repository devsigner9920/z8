#!/usr/bin/env python3
"""Prepare a pinned Termux fork in .local/build-src without altering upstream.

Only tracked files from the verified clean revision are copied. A diagnostic APK
contains no Linux bootstrap; runtime builds require a separately verified z8 ZIP.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import stat
import tempfile
import xml.etree.ElementTree as ET
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import release_config

ROOT = Path(__file__).resolve().parents[1]
ANDROID = "{http://schemas.android.com/apk/res/android}"
TOOLS = "{http://schemas.android.com/tools}"
CLASS_CONSTANTS = (
    "BUILD_CONFIG_CLASS_NAME", "FILE_SHARE_RECEIVER_ACTIVITY_CLASS_NAME",
    "FILE_VIEW_RECEIVER_ACTIVITY_CLASS_NAME", "TERMUX_ACTIVITY_NAME",
    "TERMUX_SETTINGS_ACTIVITY_NAME", "TERMUX_SERVICE_NAME", "RUN_COMMAND_SERVICE_NAME",
)
PERMISSIONS = {
    "android.permission.INTERNET", "android.permission.ACCESS_NETWORK_STATE",
    "android.permission.WAKE_LOCK", "android.permission.VIBRATE",
    "android.permission.FOREGROUND_SERVICE", "android.permission.POST_NOTIFICATIONS",
    "android.permission.FOREGROUND_SERVICE_SPECIAL_USE",
}


class PrepareError(ValueError):
    pass


def replace_exact(text, old, new, count=1):
    actual = text.count(old)
    if actual != count:
        raise PrepareError(f"Patch anchor changed: expected {count}, found {actual}: {old[:100]!r}")
    return text.replace(old, new)


def edit(path, old, new, count=1):
    path.write_text(replace_exact(path.read_text(), old, new, count))


def validate_lock(lock):
    app_id = lock.get("applicationId", "")
    if not isinstance(app_id, str) or not re.fullmatch(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*){2,}", app_id):
        raise PrepareError("Invalid applicationId in source lock")
    if app_id != "dev.devsigner.z8":
        raise PrepareError("This overlay is scoped to applicationId dev.devsigner.z8")
    if lock.get("prefix") != f"/data/data/{app_id}/files/usr":
        raise PrepareError("Locked prefix must match applicationId")
    if not re.fullmatch(r"[a-f0-9]{40}", lock.get("termuxApp", {}).get("commit", "")):
        raise PrepareError("Source commit must be a full lowercase SHA-1")


def checked_local(root, output_name="build-src"):
    local = root / ".local"
    if local.is_symlink() or (local.exists() and not local.is_dir()):
        raise PrepareError(".local must be an actual directory inside the project")
    local.mkdir(exist_ok=True)
    if not re.fullmatch(r"build-[a-z0-9-]+", output_name):
        raise PrepareError("Invalid generated build directory name")
    output = local / output_name
    if output.is_symlink() or (output.exists() and not output.is_dir()):
        raise PrepareError("Refusing to replace a symlink or non-directory build-src")
    if local.resolve().parent != root.resolve():
        raise PrepareError("Build output escapes the project")
    return local, output


def git_output(git, source, *args):
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    try:
        return subprocess.check_output([git, "-C", str(source), *args], env=env, text=True, stderr=subprocess.PIPE)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise PrepareError("Cannot verify upstream using Git; set Z8_GIT to a working Git executable") from exc


def verify_source(source, commit, git):
    if source.is_symlink() or not source.is_dir():
        raise PrepareError("Pinned upstream source is missing or is a symlink")
    if git_output(git, source, "rev-parse", "HEAD").strip() != commit:
        raise PrepareError("Upstream HEAD differs from tools/sources.lock.json")
    if git_output(git, source, "status", "--porcelain", "--untracked-files=all").strip():
        raise PrepareError("Upstream is not pristine; preserve changes outside the generated fork")
    names = git_output(git, source, "ls-files", "-z").split("\0")
    return [name for name in names if name]


def copy_tracked(source, destination, names):
    for name in names:
        parts = PurePosixPath(name).parts
        if not parts or PurePosixPath(name).is_absolute() or ".." in parts:
            raise PrepareError("Unsafe tracked source path")
        if any(part in {".git", "build", ".gradle", ".cxx"} for part in parts):
            continue
        original = source / name
        if original.is_symlink() or not original.is_file() or not original.resolve().is_relative_to(source.resolve()):
            raise PrepareError(f"Unsupported tracked symlink or missing file: {name}")
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, target)


def patch_gradle(tree, lock, mode, bootstrap_sha, config=None):
    config = config or release_config.load()
    app_id, commit = lock["applicationId"], lock["termuxApp"]["commit"]
    path = tree / "app/build.gradle"
    text = path.read_text()
    text = replace_exact(text, '        implementation "androidx.core:core:1.13.1"',
        '        implementation "androidx.core:core:1.13.1"\n        implementation "androidx.browser:browser:1.8.0"\n        implementation "androidx.webkit:webkit:1.13.0"')
    # Source revision and these anchors must match; do not retain ANY downloader.
    marker = "def downloadBootstrap(String arch, String expectedChecksum, String version) {"
    if text.count(marker) != 1 or text.count("task downloadBootstraps() {") != 1:
        raise PrepareError("Upstream bootstrap build task changed")
    text = text.split(marker)[0] + "// z8: bootstrap is supplied only by the verified preparer. No network fallback.\n"
    text = replace_exact(text, '    defaultConfig {\n', f'''    defaultConfig {{
        applicationId "{app_id}"
        ndk {{ abiFilters 'arm64-v8a' }}
        buildConfigField "boolean", "Z8_HAS_BOOTSTRAP", "{str(mode == 'runtime').lower()}"
        buildConfigField "String", "Z8_BOOTSTRAP_SHA256", '\"{bootstrap_sha}\"'
        buildConfigField "String", "Z8_UPSTREAM_COMMIT", '\"{commit}\"'
{release_config.gradle_public_fields(config)}
''')
    text = replace_exact(text, 'manifestPlaceholders.TERMUX_PACKAGE_NAME = "com.termux"', f'manifestPlaceholders.TERMUX_PACKAGE_NAME = "{app_id}"')
    text = replace_exact(text, 'manifestPlaceholders.TERMUX_APP_NAME = "Termux"', 'manifestPlaceholders.TERMUX_APP_NAME = "z8"')
    text = replace_exact(text, '        versionCode 118\n        versionName "0.118.0"',
        f'        versionCode {config["versionCode"]}\n        versionName {json.dumps(config["versionName"])}')
    text = replace_exact(text, '    def appVersionName = System.getenv("TERMUX_APP_VERSION_NAME") ?: ""',
        '    def appVersionName = "" // Version comes only from the validated z8 release config.')
    text = replace_exact(text, '''                enable ((gradle.startParameter.taskNames.any { it.contains("Debug") } && splitAPKsForDebugBuilds == "1") ||
                    (gradle.startParameter.taskNames.any { it.contains("Release") } && splitAPKsForReleaseBuilds == "1"))''', '                enable false')
    text = replace_exact(text, "include 'x86', 'x86_64', 'armeabi-v7a', 'arm64-v8a'", "include 'arm64-v8a'")
    text = replace_exact(text, """            storeFile file('testkey_untrusted.jks')
            keyAlias 'alias'
            storePassword 'xrj45yWGLbsO7W0v'
            keyPassword 'xrj45yWGLbsO7W0v'""", """            storeFile file(System.getenv('Z8_KEYSTORE') ?: rootProject.file('../keys/z8-debug.jks'))
            keyAlias 'z8-debug'
            storePassword 'android'
            keyPassword 'android'""")
    text = replace_exact(text, '    signingConfigs {\n', '''    signingConfigs {
        if (System.getenv('Z8_RELEASE_BUILD') == '1') {
            release {
                storeFile file(System.getenv('Z8_UPLOAD_KEYSTORE'))
                keyAlias System.getenv('Z8_UPLOAD_KEY_ALIAS')
                storePassword System.getenv('Z8_UPLOAD_STORE_PASSWORD')
                keyPassword System.getenv('Z8_UPLOAD_KEY_PASSWORD')
            }
        }
''')
    text = replace_exact(text, '        release {\n            minifyEnabled true', '''        release {
            signingConfig System.getenv('Z8_RELEASE_BUILD') == '1' ? signingConfigs.release : null
            debuggable false
            minifyEnabled true''')
    path.write_text(text)
    edit(tree / "gradle/wrapper/gradle-wrapper.properties", "validateDistributionUrl=true\n", "validateDistributionUrl=true\ndistributionSha256Sum=72f44c9f8ebcb1af43838f45ee5c4aa9c5444898b3468ab3f4af7b6076c5bc3f\n")
    edit(tree / "gradle.properties", "minSdkVersion=21", "minSdkVersion=28")
    props = (tree / "gradle.properties").read_text()
    if "targetSdkVersion=28\n" not in props or "compileSdkVersion=36\n" not in props:
        raise PrepareError("Unexpected SDK configuration")
    edit(tree / "gradle.properties", "targetSdkVersion=28\n", "targetSdkVersion=36\n")
    publishing = '''    publishing {
        multipleVariants {
            withSourcesJar()
            withJavadocJar()
            allVariants()
        }
    }
'''
    for module in ("terminal-emulator", "terminal-view", "termux-shared"):
        path = tree / module / "build.gradle"
        text = replace_exact(path.read_text(), "apply plugin: 'maven-publish'\n", "")
        text = replace_exact(text, publishing, "")
        tail = '''task sourceJar(type: Jar) {'''
        if text.count(tail) != 1 or text.count("from components.default") != 1:
            raise PrepareError(f"Publication task changed for {module}")
        text = text.split(tail)[0] + "// z8: generated application build does not publish Maven artifacts.\n"
        if module == "terminal-emulator":
            text = replace_exact(text, "abiFilters 'x86', 'x86_64', 'armeabi-v7a', 'arm64-v8a'", "abiFilters 'arm64-v8a'")
        elif module == "termux-shared":
            text = replace_exact(text, "    defaultConfig {\n", "    defaultConfig {\n        ndk { abiFilters 'arm64-v8a' }\n")
        path.write_text(text)


def patch_identity(tree, lock):
    app_id = lock["applicationId"]
    path = tree / "termux-shared/src/main/java/com/termux/shared/termux/TermuxConstants.java"
    text = replace_exact(path.read_text(), 'TERMUX_PACKAGE_NAME = "com.termux";', f'TERMUX_PACKAGE_NAME = "{app_id}";')
    text = replace_exact(text, 'TERMUX_APP_NAME = "Termux";', 'TERMUX_APP_NAME = "z8";')
    for constant in CLASS_CONSTANTS:
        text = replace_exact(text, constant + " = TERMUX_PACKAGE_NAME +", constant + ' = "com.termux" +')
    path.write_text(text)
    for module in ("app", "termux-shared"):
        path = tree / module / "src/main/res/values/strings.xml"
        text = replace_exact(path.read_text(), '<!ENTITY TERMUX_PACKAGE_NAME "com.termux">', f'<!ENTITY TERMUX_PACKAGE_NAME "{app_id}">')
        text = replace_exact(text, '<!ENTITY TERMUX_APP_NAME "Termux">', '<!ENTITY TERMUX_APP_NAME "z8">')
        if module == "termux-shared":
            text = replace_exact(text, '<!ENTITY TERMUX_PREFIX_DIR_PATH "/data/data/com.termux/files/usr">', f'<!ENTITY TERMUX_PREFIX_DIR_PATH "{lock["prefix"]}">')
        path.write_text(text)
    path = tree / "app/src/main/res/xml/shortcuts.xml"
    text = replace_exact(path.read_text(), 'android:targetPackage="com.termux"', f'android:targetPackage="{app_id}"', 3)
    path.write_text(replace_exact(text, 'android:name="com.termux.app.failsafe_session"', f'android:name="{app_id}.app.failsafe_session"'))


def patch_manifest(tree):
    ET.register_namespace("android", ANDROID[1:-1])
    ET.register_namespace("tools", TOOLS[1:-1])
    path = tree / "app/src/main/AndroidManifest.xml"
    document = ET.parse(path)
    manifest = document.getroot()
    for attribute in ("sharedUserId", "sharedUserLabel"):
        if ANDROID + attribute not in manifest.attrib:
            raise PrepareError(f"Missing expected manifest attribute {attribute}")
        del manifest.attrib[ANDROID + attribute]
    for permission in list(manifest.findall("uses-permission")):
        if permission.get(ANDROID + "name") not in PERMISSIONS:
            manifest.remove(permission)
    present = {e.get(ANDROID + "name") for e in manifest.findall("uses-permission")}
    for name in sorted(PERMISSIONS - present):
        manifest.insert(0, ET.Element("uses-permission", {ANDROID + "name": name}))
    application = manifest.find("application")
    if application is None:
        raise PrepareError("Expected one application")
    application.attrib.pop(ANDROID + "requestLegacyExternalStorage", None)
    application.set(ANDROID + "extractNativeLibs", "true")
    application.set(ANDROID + "enableOnBackInvokedCallback", "true")
    application.set(ANDROID + "networkSecurityConfig", "@xml/z8_network_security")
    # Every class stays in the existing Java namespace. Explicit names prevent
    # applicationId substitution from accidentally changing component lookups.
    for node in application:
        for attr in ("name", "targetActivity", "parentActivityName"):
            value = node.get(ANDROID + attr)
            if value and value.startswith("."):
                node.set(ANDROID + attr, "com.termux" + value)
        if node.tag in {"activity", "activity-alias", "provider", "receiver", "service"}:
            node.set(ANDROID + "exported", "false")
        if node.tag in {"activity-alias", "provider"} or node.get(ANDROID + "name") == "com.termux.app.RunCommandService":
            node.set(ANDROID + "enabled", "false")
        if node.tag == "service" and node.get(ANDROID + "name") == "com.termux.app.TermuxService":
            node.set(ANDROID + "foregroundServiceType", "specialUse")
            ET.SubElement(node, "property", {
                ANDROID + "name": "android.app.PROPERTY_SPECIAL_USE_FGS_SUBTYPE",
                ANDROID + "value": "User-started local terminal sessions and Linux development environment preparation. "
                    "Commands and child processes continue while the user switches apps with an ongoing notification. "
                    "Users can stop terminals in the app or notification and stop preparation using Android app controls. "
                    "The service stops when idle.",
            })
    application.set(ANDROID + "name", "com.termux.app.TermuxApplication")
    terminals = [e for e in application.findall("activity") if e.get(ANDROID + "name") == "com.termux.app.TermuxActivity"]
    if len(terminals) != 1:
        raise PrepareError("TermuxActivity manifest entry changed")
    for child in list(terminals[0]):
        if child.tag in {"intent-filter", "meta-data"}:
            terminals[0].remove(child)
    launcher = terminals[0]
    launcher.set(ANDROID + "exported", "true")
    launcher.set(ANDROID + "resizeableActivity", "true")
    launcher.set(ANDROID + "label", "z8")
    # Keep historical app-owned intents/back stacks navigable, without a second home.
    ET.SubElement(application, "activity", {
        ANDROID + "name": "com.termux.app.Z8WorkspaceActivity",
        ANDROID + "exported": "false", ANDROID + "resizeableActivity": "true",
        ANDROID + "label": "z8",
    })
    intent = ET.SubElement(launcher, "intent-filter")
    ET.SubElement(intent, "action", {ANDROID + "name": "android.intent.action.MAIN"})
    ET.SubElement(intent, "category", {ANDROID + "name": "android.intent.category.LAUNCHER"})
    ET.SubElement(application, "activity", {
        ANDROID + "name": "com.termux.app.Z8ThemeActivity",
        ANDROID + "exported": "false", ANDROID + "resizeableActivity": "true",
        ANDROID + "label": "z8 · Theme",
    })
    for name, label in (("Z8DiagnosticsActivity", "z8 · Diagnostics"), ("Z8AttentionActivity", "z8 · Notifications"),
                        ("Z8SetupActivity", "z8 · Setup"),
                        ("Z8SettingsActivity", "z8 · Settings"),
                        ("Z8AboutActivity", "z8 · About"),
                        ("Z8EnvironmentActivity", "z8 · Linux environment")):
        ET.SubElement(application, "activity", {
            ANDROID + "name": "com.termux.app." + name,
            ANDROID + "exported": "false", ANDROID + "resizeableActivity": "true",
            ANDROID + "label": label,
        })
    ET.indent(document, space="    ")
    document.write(path, encoding="utf-8", xml_declaration=True)


ACTIVITY_SESSION_BLOCK = '''        if (Z8AttentionBridge.routeRequestedSession(this, intent)) {
            mTermuxService.setTermuxTerminalSessionClient(mTermuxTerminalSessionActivityClient);
            z8ShowSessionsIfReady();
            return;
        }
        if (Z8GuestSessionLauncher.observe(this) && !z8IsSessionRequest(intent)) {
            mTermuxService.setTermuxTerminalSessionClient(mTermuxTerminalSessionActivityClient);
            z8ShowSessionsIfReady();
            return;
        }
        if (mTermuxService.isTermuxSessionsEmpty()) {
            if (mIsVisible) {
                z8OpenRequestedSession(intent);
            } else {
                finishActivityIfNotFinishing();
            }
        } else if (z8IsSessionRequest(intent) && (!mIsActivityRecreated || Z8GuestSessionLauncher.isPendingIntent(intent))) {
            z8OpenRequestedSession(intent);
        } else {
            z8RestoreSessionSelection();
        }

'''

ACTIVITY_HELPERS = '''    private boolean mZ8ShowSessionsPending;
    private String mZ8FocusProjectPending;
    private boolean mZ8Resumed;
    private boolean mZ8ServiceBound;
    private boolean mZ8ServiceConnectQueued;
    private boolean mZ8ServiceNavigationPending;
    private boolean mZ8ServiceDisposed;
    private final Runnable mZ8ConnectService = () -> {
        mZ8ServiceConnectQueued = false;
        z8ConnectServiceIfReady();
    };
    private static final String Z8_INTERNAL_SESSION_KEY = "dev.devsigner.z8.INTERNAL_SESSION";
    private static final String Z8_INTERNAL_SESSION_TOKEN = java.util.UUID.randomUUID().toString();

    /** Startup can arrive behind the keyguard. Retry only on a foreground event or user action. */
    public void z8RequestServiceConnection() {
        if (mIsInvalidState || mZ8ServiceDisposed || !mZ8Resumed || mZ8ServiceConnectQueued) return;
        mZ8ServiceConnectQueued = true;
        getWindow().getDecorView().post(mZ8ConnectService);
    }

    private void z8ConnectServiceIfReady() {
        if (mIsInvalidState || mZ8ServiceDisposed || !mZ8Resumed || !mIsVisible
                || isFinishing() || isDestroyed() || !hasWindowFocus()) return;
        android.app.KeyguardManager keyguard =
            (android.app.KeyguardManager) getSystemService(Context.KEYGUARD_SERVICE);
        if (keyguard != null && keyguard.isKeyguardLocked()) return;
        if (mTermuxService != null) {
            if (mZ8ServiceNavigationPending) {
                mZ8ServiceNavigationPending = false;
                z8DispatchConnectedService();
            }
            return;
        }
        if (mZ8ServiceBound) return;
        Intent serviceIntent = new Intent(this, TermuxService.class);
        try {
            // Idle navigation uses the normal bound service. Execution owns FGS lifetime.
            startService(serviceIntent);
            mZ8ServiceBound = bindService(serviceIntent, this, Context.BIND_AUTO_CREATE);
            if (!mZ8ServiceBound) throw new RuntimeException("bindService() failed");
        } catch (IllegalStateException deferred) {
            // Android may revoke foreground eligibility between the checks and the
            // binder call. Keep the Activity usable; the next focus/resume can retry.
            mZ8ServiceBound = false;
            Logger.logStackTraceWithMessage(LOG_TAG, "z8 terminal service connection deferred", deferred);
        } catch (Exception error) {
            mZ8ServiceBound = false;
            Logger.logStackTraceWithMessage(LOG_TAG, "z8 terminal service connection failed", error);
            Logger.showToast(this, getString(R.string.error_termux_service_start_failed_general), true);
        }
    }

    /** Only an explicit action inside this process can create a PTY through the exported launcher. */
    public static Intent z8SessionIntent(android.content.Context context) {
        return new Intent(context, TermuxActivity.class).putExtra(Z8_INTERNAL_SESSION_KEY, Z8_INTERNAL_SESSION_TOKEN);
    }

    public void z8CreateProjectSession(String name) {
        if (mZ8SessionChrome != null) mZ8SessionChrome.createForCurrent(name);
    }

    public void z8OnSessionSelected(TerminalSession session) {
        if (mZ8SessionChrome != null) mZ8SessionChrome.onSessionSelected(session);
    }

    public void z8RestoreSessionSelection() {
        if (mZ8SessionChrome == null) return;
        if (mZ8FocusProjectPending != null) {
            String projectId = mZ8FocusProjectPending;
            mZ8FocusProjectPending = null;
            mZ8SessionChrome.selectProject(projectId);
        } else mZ8SessionChrome.restoreSelection();
    }

    @Override public boolean dispatchKeyEvent(android.view.KeyEvent event) {
        if (Z8ShortcutHelp.dispatch(this, event)) return true;
        if (mZ8SessionChrome != null && mZ8SessionChrome.dispatchKeyEvent(event)) return true;
        return super.dispatchKeyEvent(event);
    }

    @Override protected void onPause() {
        mZ8Resumed = false;
        Z8ShortcutHelp.dismiss(this);
        if (mZ8SessionChrome != null) mZ8SessionChrome.onPause();
        super.onPause();
    }

    @Override public void onConfigurationChanged(android.content.res.Configuration configuration) {
        Z8ShortcutHelp.dismiss(this);
        super.onConfigurationChanged(configuration);
        if (mZ8SessionChrome != null) mZ8SessionChrome.restoreTerminalInput();
    }

    @Override public void onWindowFocusChanged(boolean hasFocus) {
        if (!hasFocus) {
            Z8ShortcutHelp.dismiss(this);
            if (mZ8SessionChrome != null) mZ8SessionChrome.onFocusLost();
        }
        super.onWindowFocusChanged(hasFocus);
        if (hasFocus) z8RequestServiceConnection();
        if (hasFocus && mZ8SessionChrome != null) mZ8SessionChrome.restoreTerminalInput();
    }

    private Z8SessionChrome mZ8SessionChrome;
    private Z8BackNavigation mZ8BackNavigation;

    public void z8RefreshSessionChrome() {
        if (mZ8SessionChrome != null) mZ8SessionChrome.refresh();
    }

    public void z8OpenSessions() {
        if (mZ8SessionChrome != null) mZ8SessionChrome.openSessions();
        else getDrawer().openDrawer(Gravity.LEFT);
    }

    public void z8SetSessionCopyMode(boolean copying) {
        if (mZ8SessionChrome != null) mZ8SessionChrome.setCopyMode(copying);
        else getDrawer().setDrawerLockMode(copying ? DrawerLayout.LOCK_MODE_LOCKED_CLOSED : DrawerLayout.LOCK_MODE_UNLOCKED);
    }

    private void z8RememberSessionDrawerRequest(Intent intent) {
        if (intent == null) return;
        if (intent.getBooleanExtra(Z8WorkspaceActivity.EXTRA_SHOW_SESSIONS, false)) mZ8ShowSessionsPending = true;
        if (intent.hasExtra(Z8WorkspaceActivity.EXTRA_FOCUS_PROJECT_ID))
            mZ8FocusProjectPending = intent.getStringExtra(Z8WorkspaceActivity.EXTRA_FOCUS_PROJECT_ID);
    }

    /** An explicit navigation request; this method never creates a session. */
    public void z8ShowSessionsIfReady() {
        if (mZ8FocusProjectPending != null && mTermuxService != null) z8RestoreSessionSelection();
        if (!mZ8ShowSessionsPending || mTerminalView == null) return;
        // New-session clients close the drawer after selection. Run after that
        // callback, including an asynchronous first bootstrap installation.
        mTerminalView.post(() -> {
            if (!mZ8ShowSessionsPending || !mIsVisible || isFinishing() || isDestroyed()
                    || mTermuxService == null || mTermuxService.wantsToStop()) return;
            mZ8ShowSessionsPending = false;
            z8OpenSessions();
        });
    }

    private static boolean z8IsSessionRequest(Intent intent) {
        return intent != null && Z8_INTERNAL_SESSION_TOKEN.equals(intent.getStringExtra(Z8_INTERNAL_SESSION_KEY))
            && (intent.hasExtra(Z8DiagnosticsActivity.EXTRA_DIAGNOSTIC_SHELL)
            || intent.hasExtra(Z8WorkspaceActivity.EXTRA_PROJECT_ID)
            || intent.hasExtra(Z8Guest.EXTRA_GUEST_SESSION));
    }

    private void z8OpenRequestedSession(Intent intent) {
        if (!z8IsSessionRequest(intent)) {
            // Opening the app restores navigation; it does not authorize a shell.
            z8RestoreSessionSelection();
            z8OpenSessions();
            return;
        }
        final boolean guest = intent != null && (intent.hasExtra(Z8WorkspaceActivity.EXTRA_PROJECT_ID)
            || intent.getBooleanExtra(Z8Guest.EXTRA_GUEST_SESSION, false));
        final boolean setupTools = guest && intent.getBooleanExtra(Z8Guest.EXTRA_SETUP_TOOLS, false);
        String toolAction = guest ? intent.getStringExtra(Z8Guest.EXTRA_TOOL_ACTION) : null;
        if (guest && intent.hasExtra("dev.devsigner.z8.GITHUB_AUTH_SESSION")) {
            if (!java.util.Objects.equals(intent.getStringExtra("dev.devsigner.z8.GITHUB_AUTH_SESSION"),
                    intent.getStringExtra(Z8WorkspaceActivity.EXTRA_PROJECT_ID))) return;
            toolAction = "github-auth";
        }
        if (setupTools) toolAction = "setup-tools";
        if (toolAction != null && !Z8Guest.validAction(toolAction)) {
            Toast.makeText(this, com.termux.app.Z8Text.text("Unknown terminal action.", "등록되지 않은 터미널 작업입니다."), Toast.LENGTH_LONG).show();
            return;
        }
        final String requestedAction = toolAction;
        final boolean diagnostic = !BuildConfig.Z8_HAS_BOOTSTRAP || (intent != null &&
            (intent.getBooleanExtra(Z8DiagnosticsActivity.EXTRA_DIAGNOSTIC_SHELL, false)
            || intent.getBooleanExtra(TERMUX_ACTIVITY.EXTRA_FAILSAFE_SESSION, false)));
        String projectDirectory = null;
        String projectName = null;
        if (intent != null && intent.hasExtra(Z8WorkspaceActivity.EXTRA_PROJECT_ID)) {
            try {
                Z8Projects.Project project = new Z8Projects(this).open(intent.getStringExtra(Z8WorkspaceActivity.EXTRA_PROJECT_ID));
                String relative = intent.getStringExtra(Z8WorkspaceActivity.EXTRA_PROJECT_CWD);
                projectDirectory = Z8Files.directory(project.source, relative == null ? "" : relative).getAbsolutePath();
                projectName = project.name;
            } catch (Exception invalid) {
                Toast.makeText(this, com.termux.app.Z8Text.text("Could not open the project. Check its storage location.", "프로젝트를 열 수 없습니다. 저장 위치를 확인해 주세요."), Toast.LENGTH_LONG).show();
                return;
            }
        }
        final String requestedDirectory = projectDirectory;
        final String requestedName = projectName;
        final String requestedProjectId = intent == null ? null : intent.getStringExtra(Z8WorkspaceActivity.EXTRA_PROJECT_ID);
        final String requestedGuestDirectory = intent == null ? null : intent.getStringExtra(Z8WorkspaceActivity.EXTRA_PROJECT_CWD);
        if (guest && requestedProjectId == null) {
            Toast.makeText(this, com.termux.app.Z8Text.text("Select a project with a Linux environment.", "Linux 환경의 프로젝트를 선택해 주세요."), Toast.LENGTH_LONG).show();
            return;
        }
        java.io.File home = new java.io.File(TermuxConstants.TERMUX_HOME_DIR_PATH);
        if (!home.isDirectory() && !home.mkdirs()) {
            Toast.makeText(this, com.termux.app.Z8Text.text("Could not create the shell HOME directory.", "셸 HOME 디렉터리를 만들 수 없습니다."), Toast.LENGTH_LONG).show();
            return;
        }
        Runnable createSession = () -> {
            if (mTermuxService == null || isFinishing()) return;
            try {
                if (guest) {
                    mTermuxTerminalSessionActivityClient.addGuestSession(requestedProjectId, requestedGuestDirectory, requestedName, requestedAction,
                        Z8GuestSessionLauncher.requestId(intent));
                } else if (requestedDirectory == null) {
                    mTermuxTerminalSessionActivityClient.addNewSession(diagnostic,
                        diagnostic ? com.termux.app.Z8Text.text("Android diagnostic shell", "Android 진단 셸") : null);
                } else {
                    mTermuxTerminalSessionActivityClient.addNewSessionInDirectory(diagnostic,
                        requestedName, requestedDirectory);
                }
            } catch (WindowManager.BadTokenException ignored) {
                // Activity was destroyed while the bootstrap installer was open.
            }
        };
        createSession.run();
    }

    public void z8EnsureBootstrap(Runnable whenDone) {
        new Thread(() -> {
            try {
                Z8Bootstrap.ensure(getApplicationContext(), (percent, message) -> {});
                runOnUiThread(() -> { if (!isFinishing() && !isDestroyed()) whenDone.run(); });
            } catch (Exception failure) {
                runOnUiThread(() -> {
                    if (!isFinishing() && !isDestroyed())
                        new android.app.AlertDialog.Builder(this).setTitle(com.termux.app.Z8Text.text("Runtime setup failed", "실행 기반 준비 실패"))
                            .setMessage(failure.getMessage()).setPositiveButton(android.R.string.ok, null).show();
                });
            }
        }, "z8-bootstrap").start();
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        // A singleTask Activity may already be bound when the diagnostic launcher
        // asks for a different session. Rotation itself must not create sessions.
        z8RememberSessionDrawerRequest(intent);
        if (z8IsSessionRequest(intent)) Z8GuestSessionLauncher.prepareIntent(intent);
        setIntent(intent);
        if (mTermuxService != null) {
            if (!Z8GuestSessionLauncher.isPendingIntent(intent)) setIntent(null);
            Z8GuestSessionLauncher.observe(this);
            if (Z8AttentionBridge.routeRequestedSession(this, intent)) {
                z8ShowSessionsIfReady();
                return;
            }
            if (z8IsSessionRequest(intent)) z8OpenRequestedSession(intent);
            else if (mZ8FocusProjectPending != null) z8RestoreSessionSelection();
            z8ShowSessionsIfReady();
        }
    }

'''


def patch_sessions(tree):
    shell_utils = tree / "termux-shared/src/main/java/com/termux/shared/termux/shell/TermuxShellUtils.java"
    edit(shell_utils, '        return result.toArray(new String[0]);', '''        // Android host ELF/interpreters in our private prefix use the system linker.
        // PRoot guest ELF paths and /system binaries must never receive this prefix.
        if (android.os.Build.VERSION.SDK_INT >= 29 && !result.isEmpty()
                && result.get(0).startsWith(TermuxConstants.TERMUX_PREFIX_DIR_PATH + "/"))
            result.add(0, "/system/bin/linker64");
        return result.toArray(new String[0]);''')
    root_view = tree / "app/src/main/java/com/termux/app/terminal/TermuxActivityRootView.java"
    edit(root_view, '        if (mActivity == null || !mActivity.isVisible()) return;', '''        if (mActivity == null || !mActivity.isVisible()) return;
        // API 35+ has one explicit owner for system/IME insets (Z8WindowInsets).
        // The legacy keyboard-candidate margin heuristic would apply them twice.
        if (android.os.Build.VERSION.SDK_INT >= 35) return;''')
    session = tree / "termux-shared/src/main/java/com/termux/shared/termux/shell/command/runner/terminal/TermuxSession.java"
    edit(session, '        executionCommand.executable = commandArgs[0];', '''        if (isLoginShell && commandArgs.length > 1 && "/system/bin/linker64".equals(commandArgs[0])) {
            // The linker's argv[0] is not bash's argv[0]. Preserve login startup explicitly.
            java.util.ArrayList<String> login = new java.util.ArrayList<>(java.util.Arrays.asList(commandArgs));
            login.add(2, "-l");
            commandArgs = login.toArray(new String[0]);
        }
        executionCommand.executable = commandArgs[0];''')
    edit(session, '        List<String> environmentList = ShellEnvironmentUtils.convertEnvironmentToEnviron(environment);', '''        if (commandArgs.length > 1 && "/system/bin/linker64".equals(commandArgs[0])
                && environment.getOrDefault("LD_PRELOAD", "").contains("/libtermux-exec-linker-ld-preload.so")) {
            // The first Java/JNI launch has not passed through termux-exec's exec interceptor.
            environment.put("TERMUX_EXEC__PROC_SELF_EXE", commandArgs[1]);
        }
        List<String> environmentList = ShellEnvironmentUtils.convertEnvironmentToEnviron(environment);''')
    # Hook authentication lives in process environment. Never copy environment
    # values into Android logs, even when the upstream verbose mode is enabled.
    for relative, label in (
        ("termux-shared/src/main/java/com/termux/shared/termux/shell/command/runner/terminal/TermuxSession.java", "TermuxSession"),
        ("termux-shared/src/main/java/com/termux/shared/shell/command/runner/app/AppShell.java", "AppShell"),
    ):
        log_path = tree / relative
        lines = log_path.read_text().splitlines(keepends=True)
        indices = [i for i, line in enumerate(lines) if label + " Environment:" in line]
        if len(indices) != 1 or lines[indices[0] + 1].strip() != 'Joiner.on("\\n").join(environmentArray));':
            raise PrepareError("Environment logging anchor changed")
        index = indices[0]
        lines[index:index + 2] = ["        // z8: environment values are intentionally excluded from logs.\n"]
        log_path.write_text("".join(lines))
    # Keep the optional toolbar toggle, but reserve the screen for the terminal
    # unless the user explicitly enables the extra keys.
    edit(tree / "termux-shared/src/main/java/com/termux/shared/termux/settings/preferences/TermuxPreferenceConstants.java",
         "DEFAULT_VALUE_SHOW_TERMINAL_TOOLBAR = true;",
         "DEFAULT_VALUE_SHOW_TERMINAL_TOOLBAR = false;")
    edit(tree / "app/src/main/java/com/termux/app/TermuxService.java",
         "this, new TermuxShellEnvironment(), null, executionCommand.isPluginExecutionCommand);",
         "this, new TermuxShellEnvironment(), Z8AttentionBridge.prepareLaunch(executionCommand, Z8ShellProfile.environment(this, executionCommand)), executionCommand.isPluginExecutionCommand);")
    service = tree / "app/src/main/java/com/termux/app/TermuxService.java"
    for method, intent in (("getActivity", "notificationIntent"), ("getService", "exitIntent"), ("getService", "toggleWakeLockIntent")):
        edit(service, f'PendingIntent.{method}(this, 0, {intent}, 0)',
             f'PendingIntent.{method}(this, 0, {intent}, PendingIntent.FLAG_IMMUTABLE)')
    for relative in ("plugins/TermuxPluginUtils.java", "crash/TermuxCrashUtils.java"):
        edit(tree / "termux-shared/src/main/java/com/termux/shared/termux" / relative,
             'PendingIntent.FLAG_UPDATE_CURRENT);', 'PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);', 2)
    edit(service, '''        TermuxSession newTermuxSession = TermuxSession.execute(this, executionCommand, getTermuxTerminalSessionClient(),
            this, new TermuxShellEnvironment(), Z8AttentionBridge.prepareLaunch(executionCommand, Z8ShellProfile.environment(this, executionCommand)), executionCommand.isPluginExecutionCommand);''', '''        TermuxSession newTermuxSession;
        synchronized (Z8RuntimeLauncher.EXECUTION_LOCK) {
            newTermuxSession = TermuxSession.execute(this, executionCommand, getTermuxTerminalSessionClient(),
                this, new TermuxShellEnvironment(), Z8AttentionBridge.prepareLaunch(executionCommand, Z8ShellProfile.environment(this, executionCommand)), executionCommand.isPluginExecutionCommand);
        }''')
    edit(service, '        startForeground(TermuxConstants.TERMUX_APP_NOTIFICATION_ID, buildNotification());', '''        if (android.os.Build.VERSION.SDK_INT >= 34) {
            startForeground(TermuxConstants.TERMUX_APP_NOTIFICATION_ID, buildNotification(),
                android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);
        } else startForeground(TermuxConstants.TERMUX_APP_NOTIFICATION_ID, buildNotification());''')
    edit(service, "    private synchronized void updateNotification() {", "    public synchronized void updateNotification() {")
    edit(service, '    boolean mWantsToStop = false;',
        '    boolean mWantsToStop = false;\n    private boolean mZ8Idle;\n    private volatile boolean mZ8StopRequested;\n    private String mZ8StopMessage;\n    public boolean z8IsStopRequested() { return mZ8StopRequested; }')
    edit(service, "        SystemEventReceiver.registerPackageUpdateEvents(this);",
        "        Z8AttentionBridge.start(this);\n        Z8GuestSessionLauncher.start(this);\n        SystemEventReceiver.registerPackageUpdateEvents(this);")
    edit(service, '    public void onDestroy() {\n        Logger.logVerbose(LOG_TAG, "onDestroy");',
        '    public void onDestroy() {\n        Z8InitialSetup.stop(this);\n        Z8GuestSessionLauncher.stop(this);\n        Z8AttentionBridge.stop();\n        Logger.logVerbose(LOG_TAG, "onDestroy");')
    edit(service, '    private void requestStopService() {',
        '''    /** Hold started/foreground lifetime only while execution owns work. */
    public synchronized void z8AcquireExecution() {
        if (mWantsToStop || !mZ8Idle) return;
        mZ8Idle = false;
        startService(new Intent(this, TermuxService.class));
        runStartForeground();
    }

    private void z8IdleService() {
        mZ8Idle = true;
        runStopForeground();
        stopSelf();
        // The visible Activity's binding retains navigation and launcher state.
        // Once that binding ends, Android destroys this idle service normally.
    }

    private void requestStopService() {
        Z8GuestSessionLauncher.stop(this);
        if (mWantsToStop && mTermuxTerminalSessionActivityClient != null)
            mTermuxTerminalSessionActivityClient.z8OnServiceStopped();''')
    edit(service, 'if (mWakeLock == null && mShellManager.mTermuxSessions.isEmpty() && mShellManager.mTermuxTasks.isEmpty()) {',
        'if (mWakeLock == null && mShellManager.mTermuxSessions.isEmpty() && mShellManager.mTermuxTasks.isEmpty()\n            && !Z8GuestSessionLauncher.hasServiceWork(this) && !Z8ProjectRemoval.hasWork()) {')
    edit(service, '    public synchronized void updateNotification() {',
        '    public synchronized void updateNotification() {\n        if (mWantsToStop) return;')
    edit(service, '''            // Exit if we are updating after the user disabled all locks with no sessions or tasks running.
            requestStopService();
        } else {
            ((NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE)).notify''',
        '''            z8IdleService();
        } else {
            z8AcquireExecution();
            ((NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE)).notify''')
    edit(service, '        return Service.START_NOT_STICKY;',
        '        updateNotification();\n        return Service.START_NOT_STICKY;')
    edit(service, '''    private void actionStopService() {
        mWantsToStop = true;
        killAllTermuxExecutionCommands();
        requestStopService();
    }''', '''    private void actionStopService() {
        if (mWantsToStop || mZ8StopRequested) return;
        if (!mShellManager.mTermuxTasks.isEmpty() || !mShellManager.mPendingPluginExecutionCommands.isEmpty()) {
            mZ8StopMessage = com.termux.app.Z8Text.text("Background work is running. Try exiting after it finishes.", "백그라운드 작업이 진행 중입니다. 완료 후 다시 종료해 주세요.");
            updateNotification();
            return;
        }
        mZ8StopRequested = true;
        mZ8StopMessage = com.termux.app.Z8Text.text("Waiting for terminals to close…", "터미널 종료를 확인하는 중…");
        Z8ProjectRemoval.stopAllSessions(this, error -> {
            mZ8StopRequested = false;
            if (error != null) {
                mZ8StopMessage = error;
                updateNotification();
                return;
            }
            mZ8StopMessage = null;
            mWantsToStop = true;
            requestStopService();
        });
        updateNotification();
    }''')
    edit(service, '    public synchronized TermuxSession createTermuxSession(ExecutionCommand executionCommand) {',
        '    public synchronized TermuxSession createTermuxSession(ExecutionCommand executionCommand) {\n        if (mWantsToStop || mZ8StopRequested) return null;')
    edit(service, '        final boolean wakeLockHeld = mWakeLock != null;',
        '        if (mZ8StopMessage != null) notificationText = mZ8StopMessage;\n        final boolean wakeLockHeld = mWakeLock != null;')
    edit(service, '        builder.setOngoing(true);',
        '''        builder.setOngoing(true);

        // First preparation owns the existing foreground card and its scoped
        // CPU lock. Avoid unrelated Exit/Wake lock controls during installation.
        if (Z8PreparationNotification.decorate(builder, this)) return builder.build();''')
    edit(service, '        if (newTermuxSession == null) {\n            Logger.logError',
        '        if (newTermuxSession == null) {\n            Z8AttentionBridge.discardLaunch(executionCommand);\n            Logger.logError')
    edit(service, '        mShellManager.mTermuxSessions.add(newTermuxSession);',
        '        mShellManager.mTermuxSessions.add(newTermuxSession);\n        Z8AttentionBridge.registerLaunch(executionCommand, newTermuxSession.getTerminalSession());')
    path = tree / "app/src/main/java/com/termux/app/TermuxActivity.java"
    text = replace_exact(path.read_text(), "import com.termux.R;", "import com.termux.R;\nimport com.termux.BuildConfig;")
    text = replace_exact(text, '        super.onActivityResult(requestCode, resultCode, data);',
        '''        super.onActivityResult(requestCode, resultCode, data);
        // Browser results can contain authentication URLs. Their payload is
        // neither needed nor logged; onResume restores the originating terminal.
        if (requestCode == Z8BrowserPane.REQUEST_EXTERNAL_BROWSER) return;''')
    start = text.index('        try {\n            // Start the {@link TermuxService}')
    end = text.index('        // Send the {@link TermuxConstants#BROADCAST_TERMUX_OPENED}', start)
    text = text[:start] + '''        // Connect after resumed/window-focus eligibility, never from creation behind the keyguard.

''' + text[end:]
    text = replace_exact(text, '        mTermuxService = ((TermuxService.LocalBinder) service).service;',
        '''        if (mZ8ServiceDisposed || isFinishing() || isDestroyed()) return;
        mTermuxService = ((TermuxService.LocalBinder) service).service;
        if (mTermuxService.wantsToStop()) { finishActivityIfNotFinishing(); return; }''')
    text = replace_exact(text, '        super.onCreate(savedInstanceState);',
        '''        super.onCreate(savedInstanceState);
        if (!Z8Theme.isSetupComplete(this)) {
            mIsInvalidState = true;
            startActivity(new Intent(this, Z8ThemeActivity.class).putExtra(Z8ThemeActivity.EXTRA_FIRST_SETUP, true));
            finish();
            return;
        }
        if (!Z8InitialSetup.isReady(this)) {
            mIsInvalidState = true;
            startActivity(new Intent(this, Z8SetupActivity.class));
            finish();
            return;
        }
        // Reject external action extras before the launcher can allocate a guest request ticket.
        if (savedInstanceState == null && !z8IsSessionRequest(getIntent()) && getIntent() != null) {
            Intent navigation = new Intent(getIntent());
            navigation.removeExtra(Z8WorkspaceActivity.EXTRA_PROJECT_ID);
            navigation.removeExtra(Z8Guest.EXTRA_GUEST_SESSION);
            setIntent(navigation);
        }
        Z8GuestSessionLauncher.restoreIntent(this, savedInstanceState);
        mZ8ShowSessionsPending = savedInstanceState != null && savedInstanceState.getBoolean("z8_show_sessions", false);
        mZ8FocusProjectPending = savedInstanceState == null ? null : savedInstanceState.getString("z8_focus_project");
        z8RememberSessionDrawerRequest(getIntent());''')
    text = replace_exact(text, '        super.onSaveInstanceState(savedInstanceState);',
        '        super.onSaveInstanceState(savedInstanceState);\n        if (mIsInvalidState) return;')
    text = replace_exact(text, '        saveTerminalToolbarTextInput(savedInstanceState);',
        '        saveTerminalToolbarTextInput(savedInstanceState);\n        Z8GuestSessionLauncher.saveIntent(this, savedInstanceState);\n        savedInstanceState.putBoolean("z8_show_sessions", mZ8ShowSessionsPending);\n        savedInstanceState.putString("z8_focus_project", mZ8FocusProjectPending);')
    text = replace_exact(text, '    public void onBackPressed() {',
        '    public void onBackPressed() {\n        if (mZ8SessionChrome != null && mZ8SessionChrome.onBackPressed()) return;')
    text = replace_exact(text, '    public void onBackPressed() {\n',
        '    public void onBackPressed() { z8HandleBack(); }\n\n    private void z8HandleBack() {\n')
    text = replace_exact(text, '        registerReceiver(mTermuxActivityBroadcastReceiver, intentFilter);',
        '        androidx.core.content.ContextCompat.registerReceiver(this, mTermuxActivityBroadcastReceiver, intentFilter, androidx.core.content.ContextCompat.RECEIVER_NOT_EXPORTED);')
    text = replace_exact(text, '        registerForContextMenu(mTerminalView);',
        '        registerForContextMenu(mTerminalView);\n        mZ8SessionChrome = new Z8SessionChrome(this);\n        mZ8SessionChrome.install();\n        mZ8BackNavigation = Z8BackNavigation.install(this, this::z8HandleBack);')
    text = replace_exact(text, '        mIsOnResumeAfterOnCreate = false;',
        '        Z8GuestSessionLauncher.observe(this);\n        if (mZ8SessionChrome != null) mZ8SessionChrome.onResume();\n        z8ShowSessionsIfReady();\n        mIsOnResumeAfterOnCreate = false;')
    text = replace_exact(text, '''        Logger.logVerbose(LOG_TAG, "onResume");

        if (mIsInvalidState) return;''', '''        Logger.logVerbose(LOG_TAG, "onResume");

        if (mIsInvalidState) return;
        mZ8Resumed = true;
        z8RequestServiceConnection();''')
    text = replace_exact(text, '        Logger.logDebug(LOG_TAG, "onStop");',
        '        Logger.logDebug(LOG_TAG, "onStop");\n        if (mZ8SessionChrome != null) mZ8SessionChrome.onStop();')
    text = replace_exact(text, '        Logger.logDebug(LOG_TAG, "onDestroy");',
        '        Logger.logDebug(LOG_TAG, "onDestroy");\n        if (mZ8BackNavigation != null) mZ8BackNavigation.close();\n        mZ8ServiceDisposed = true;\n        mZ8Resumed = false;\n        getWindow().getDecorView().removeCallbacks(mZ8ConnectService);\n        mZ8ServiceConnectQueued = false;\n        Z8GuestSessionLauncher.forget(this);\n        if (mZ8SessionChrome != null) {\n            mZ8SessionChrome.dispose();\n            mZ8SessionChrome = null;\n        }')
    text = replace_exact(text, '            unbindService(this);', '''            if (mZ8ServiceBound) {
                mZ8ServiceBound = false;
                unbindService(this);
            }''')
    text = replace_exact(text, '        mTermuxSessionListViewController.notifyDataSetChanged();',
        '        mTermuxSessionListViewController.notifyDataSetChanged();\n        z8RefreshSessionChrome();')
    text = replace_exact(text, '        final Intent intent = getIntent();\n        setIntent(null);',
        '        final Intent intent = getIntent();\n        if (!Z8GuestSessionLauncher.isPendingIntent(intent)) setIntent(null);')
    start = "        if (mTermuxService.isTermuxSessionsEmpty()) {"
    end = "        // Update the {@link TerminalSession} and {@link TerminalEmulator} clients."
    if text.count(start) != 1 or text.count(end) != 1:
        raise PrepareError("Activity service lifecycle changed")
    before, remainder = text.split(start)
    _, after = remainder.split(end)
    text = before + ACTIVITY_SESSION_BLOCK + end + after
    text = replace_exact(text, end + '\n        mTermuxService.setTermuxTerminalSessionClient(mTermuxTerminalSessionActivityClient);',
        end + '\n        mTermuxService.setTermuxTerminalSessionClient(mTermuxTerminalSessionActivityClient);\n        z8ShowSessionsIfReady();')
    # A connection may arrive after pause. Keep its navigation intent untouched
    # until the same foreground/keyguard gate permits dispatch, then consume once.
    start = text.index('        setTermuxSessionsListView();', text.index('public void onServiceConnected('))
    end = text.index('\n    }', start)
    dispatch_body = replace_exact(text[start:end], '        setTermuxSessionsListView();\n\n', '')
    dispatch = '    private void z8DispatchConnectedService() {\n' + dispatch_body + '\n    }\n\n'
    text = text[:start] + '''        // onStart may observe the service before the next onResume. Wire its
        // list/client dependencies now; only intent consumption needs deferral.
        setTermuxSessionsListView();
        mZ8ServiceNavigationPending = true;
        z8RequestServiceConnection();''' + text[end:]
    text = replace_exact(text, "    @Override\n    public void onServiceDisconnected(ComponentName name) {", ACTIVITY_HELPERS + dispatch + "    @Override\n    public void onServiceDisconnected(ComponentName name) {")
    text = replace_exact(text,
        'newSessionButton.setOnClickListener(v -> mTermuxTerminalSessionActivityClient.addNewSession(false, null));',
        'newSessionButton.setOnClickListener(v -> mTermuxTerminalSessionActivityClient.addProjectSession(null));')
    text = replace_exact(text,
        'R.string.action_create_named_session_confirm, text -> mTermuxTerminalSessionActivityClient.addNewSession(false, text),',
        'R.string.action_create_named_session_confirm, text -> mTermuxTerminalSessionActivityClient.addProjectSession(text),')
    text = replace_exact(text,
        'menu.add(Menu.NONE, CONTEXT_MENU_STYLING_ID, Menu.NONE, R.string.action_style_terminal);',
        'menu.add(Menu.NONE, CONTEXT_MENU_STYLING_ID, Menu.NONE, com.termux.app.Z8Text.text("Theme settings", "테마 설정"));')
    text = replace_exact(text, '                showStylingDialog();',
        '                startActivity(new Intent(this, Z8ThemeActivity.class));')
    text = replace_exact(text, '    private static final int CONTEXT_MENU_REPORT_ID = 9;',
        '    private static final int CONTEXT_MENU_REPORT_ID = 9;\n    private static final int CONTEXT_MENU_Z8_PROJECTS = 12;\n    private static final int CONTEXT_MENU_Z8_ATTENTION = 13;\n    private static final int CONTEXT_MENU_Z8_SESSIONS = 14;')
    text = replace_exact(text,
        '        menu.add(Menu.NONE, CONTEXT_MENU_SELECT_URL_ID, Menu.NONE, R.string.action_select_url);',
        '        menu.add(Menu.NONE, CONTEXT_MENU_Z8_SESSIONS, Menu.NONE, com.termux.app.Z8Text.text("Sessions / New session", "세션 목록 / 새 세션"));\n        menu.add(Menu.NONE, CONTEXT_MENU_SELECT_URL_ID, Menu.NONE, R.string.action_select_url);')
    text = replace_exact(text, '        menu.add(Menu.NONE, CONTEXT_MENU_STYLING_ID, Menu.NONE, com.termux.app.Z8Text.text("Theme settings", "테마 설정"));',
        '        menu.add(Menu.NONE, CONTEXT_MENU_Z8_PROJECTS, Menu.NONE, com.termux.app.Z8Text.text("Projects", "프로젝트"));\n        menu.add(Menu.NONE, CONTEXT_MENU_Z8_ATTENTION, Menu.NONE, com.termux.app.Z8Text.text("Notifications", "응답 확인"));\n        menu.add(Menu.NONE, CONTEXT_MENU_STYLING_ID, Menu.NONE, com.termux.app.Z8Text.text("Theme settings", "테마 설정"));')
    text = replace_exact(text, '        switch (item.getItemId()) {',
        '        switch (item.getItemId()) {\n            case CONTEXT_MENU_Z8_SESSIONS:\n                z8OpenSessions();\n                return true;\n            case CONTEXT_MENU_Z8_PROJECTS:\n                z8OpenSessions();\n                return true;\n            case CONTEXT_MENU_Z8_ATTENTION:\n                startActivity(new Intent(this, Z8AttentionActivity.class));\n                return true;')
    path.write_text(text)
    path = tree / "app/src/main/java/com/termux/app/terminal/TermuxTerminalSessionActivityClient.java"
    text = replace_exact(path.read_text(), "import com.termux.R;", "import com.termux.R;\nimport com.termux.BuildConfig;")
    text = replace_exact(text, "    public void addNewSession(boolean isFailSafe, String sessionName) {\n", '''    public void addNewSession(boolean isFailSafe, String sessionName) {
        final boolean diagnostic = isFailSafe || !BuildConfig.Z8_HAS_BOOTSTRAP;
        if (diagnostic) addNewSessionChecked(true, sessionName);
        else mActivity.z8EnsureBootstrap(() -> addNewSessionChecked(false, sessionName));
    }

    private void addNewSessionChecked(boolean isFailSafe, String sessionName) {
        addNewSessionInDirectoryChecked(isFailSafe, sessionName, null);
    }

    public void addNewSessionInDirectory(boolean isFailSafe, String sessionName, String directory) {
        final boolean diagnostic = isFailSafe || !BuildConfig.Z8_HAS_BOOTSTRAP;
        if (diagnostic) addNewSessionInDirectoryChecked(true, sessionName, directory);
        else mActivity.z8EnsureBootstrap(() -> addNewSessionInDirectoryChecked(false, sessionName, directory));
    }

    public void addProjectSession(String name) {
        mActivity.z8CreateProjectSession(name);
    }

    public void addGuestSession(String projectId, String directory, String name, String action) {
        TermuxService service = mActivity.getTermuxService();
        addGuestSession(projectId, directory, name, action,
            com.termux.app.Z8GuestSessionLauncher.newRequest(service));
    }

    public void addGuestSession(String projectId, String directory, String name, String action, String requestId) {
        final TermuxService service = mActivity.getTermuxService();
        if (service == null || requestId == null) return;
        com.termux.app.Z8GuestSessionLauncher.observe(mActivity);
        // Bootstrap, environment and tool preparation belong to the service worker.
        com.termux.app.Z8GuestSessionLauncher.request(service, requestId, projectId, directory, name, action);
    }

    private void addNewSessionInDirectoryChecked(boolean isFailSafe, String sessionName, String directory) {
''')
    text = replace_exact(text,
        '            TermuxSession newTermuxSession = service.createTermuxSession(null, null, null, workingDirectory, isFailSafe, sessionName);',
        '            if (directory != null) workingDirectory = directory;\n            TermuxSession newTermuxSession = service.createTermuxSession(null, null, null, workingDirectory, isFailSafe, sessionName);')
    text = replace_exact(text, '    public void onSessionFinished(@NonNull TerminalSession finishedSession) {',
        '    public void onSessionFinished(@NonNull TerminalSession finishedSession) {\n        if (com.termux.app.Z8ProjectRemoval.protects(finishedSession)) {\n            mActivity.z8RefreshSessionChrome();\n            return;\n        }')
    text = replace_exact(text, '    public void removeFinishedSession(TerminalSession finishedSession) {',
        '    public void z8OnServiceStopped() { mActivity.finishActivityIfNotFinishing(); }\n\n    public void removeFinishedSession(TerminalSession finishedSession) {')
    text = replace_exact(text, '    public void removeFinishedSession(TerminalSession finishedSession) {',
        '    public void removeFinishedSession(TerminalSession finishedSession) {\n        if (com.termux.app.Z8ProjectRemoval.protects(finishedSession)) return;')
    text = replace_exact(text, '        if (mActivity.getPackageManager().hasSystemFeature(PackageManager.FEATURE_LEANBACK)) {', '''        com.termux.app.Z8SessionOrigin origin = com.termux.app.Z8SessionOrigin.of(finishedSession);
        if (origin != null && origin.action != null && !isPluginExecutionCommandWithPendingResult) {
            // Project task output remains reviewable until the user explicitly removes the stopped tab.
            com.termux.app.Z8Guest.invalidateReadiness(origin.projectId);
            mActivity.z8RefreshSessionChrome();
            return;
        }
        if (mActivity.getPackageManager().hasSystemFeature(PackageManager.FEATURE_LEANBACK)) {''')
    text = replace_exact(text, '            TerminalColors.COLOR_SCHEME.updateWith(props);',
        '            TerminalColors.COLOR_SCHEME.updateWith(props);\n            com.termux.app.Z8Theme.applyDefaults(mActivity);')
    text = replace_exact(text, '    public void updateBackgroundColor() {\n        if (!mActivity.isVisible()) return;',
        '    public void updateBackgroundColor() {\n        if (!mActivity.isVisible()) return;\n        if (com.termux.app.Z8Theme.applyToTerminal(mActivity)) return;')
    text = replace_exact(text, '            setCurrentSession(getCurrentStoredSessionOrLast());',
        '            mActivity.z8RestoreSessionSelection();')
    text = replace_exact(text, '''        int size = service.getTermuxSessionsSize();
        if (size == 0) {
            // There are no sessions to show, so finish the activity.
            mActivity.finishActivityIfNotFinishing();
        } else {
            if (index >= size) {
                index = size - 1;
            }
            TermuxSession termuxSession = service.getTermuxSession(index);
            if (termuxSession != null)
                setCurrentSession(termuxSession.getTerminalSession());
        }''', '''        // Removing the last session leaves the terminal home open. Reconnect
        // within the chosen project only; never jump to another project or create work.
        if (mActivity.getCurrentSession() == finishedSession)
            mActivity.getTerminalView().attachSession(null);
        mActivity.z8RestoreSessionSelection();
        mActivity.z8RefreshSessionChrome();''')
    text = replace_exact(text, '    public void onResume() {\n',
        '    public void onResume() {\n        com.termux.app.Z8Theme.applyToTerminal(mActivity);\n')
    text = replace_exact(text, '        checkAndScrollToSession(session);\n        updateBackgroundColor();',
        '        checkAndScrollToSession(session);\n        updateBackgroundColor();\n        mActivity.z8OnSessionSelected(session);\n        mActivity.z8RefreshSessionChrome();\n        mActivity.z8ShowSessionsIfReady();')
    text = replace_exact(text, '        }\n    }\n\n    @Override\n    public void onCopyTextToClipboard',
        '        }\n        mActivity.z8RefreshSessionChrome();\n    }\n\n    @Override\n    public void onCopyTextToClipboard')
    path.write_text(text)
    edit(tree / "app/src/main/java/com/termux/app/terminal/TermuxTerminalViewClient.java",
        '    public void onEmulatorSet() {\n',
        '    public void onEmulatorSet() {\n        com.termux.app.Z8Theme.applyToTerminal(mActivity);\n')
    view_client = tree / "app/src/main/java/com/termux/app/terminal/TermuxTerminalViewClient.java"
    view_text = view_client.read_text()
    view_text = replace_exact(view_text,
        '        mActivity.getDrawer().setDrawerLockMode(copyMode ? DrawerLayout.LOCK_MODE_LOCKED_CLOSED : DrawerLayout.LOCK_MODE_UNLOCKED);',
        '        mActivity.z8SetSessionCopyMode(copyMode);')
    view_text = replace_exact(view_text, '                mActivity.getDrawer().openDrawer(Gravity.LEFT);',
        '                mActivity.z8OpenSessions();')
    old_new_session = 'mTermuxTerminalSessionActivityClient.addNewSession(false, null);'
    if view_text.count(old_new_session) != 2:
        raise PrepareError("Terminal new-session keyboard bindings changed")
    view_client.write_text(view_text.replace(old_new_session, 'mTermuxTerminalSessionActivityClient.addProjectSession(null);'))


def patch_installer(tree):
    path = tree / "app/src/main/java/com/termux/app/TermuxInstaller.java"
    text = replace_exact(path.read_text(), "import com.termux.R;", "import com.termux.R;\nimport com.termux.BuildConfig;")
    text = replace_exact(text, "    static void setupBootstrapIfNeeded(final Activity activity, final Runnable whenDone) {\n", '''    static void setupBootstrapIfNeeded(final Activity activity, final Runnable whenDone) {
        if (!BuildConfig.Z8_HAS_BOOTSTRAP) {
            new AlertDialog.Builder(activity).setTitle(com.termux.app.Z8Text.text("Linux runtime not included", "Linux 런타임 미포함"))
                .setMessage(com.termux.app.Z8Text.text("This APK does not include a Z8 Linux bootstrap. Only the Android diagnostic shell is available.", "이 APK에는 z8용 Linux bootstrap이 없습니다. Android 진단 셸만 사용할 수 있습니다."))
                .setPositiveButton(android.R.string.ok, null).show();
            return;
        }
''')
    text = replace_exact(text, '''            } else {
                whenDone.run();
                return;
            }
        } else if (FileUtils.fileExists(TERMUX_PREFIX_DIR_PATH, false)) {''', '''            } else {
                try {
                    File bash = new File(TERMUX_PREFIX_DIR, "bin/bash");
                    File marker = new File(TERMUX_PREFIX_DIR, ".z8-bootstrap.sha256");
                    String installedHash = marker.isFile() ? new String(java.nio.file.Files.readAllBytes(marker.toPath()),
                        java.nio.charset.StandardCharsets.UTF_8).trim() : "";
                    if (!bash.isFile() || !bash.canExecute() || !BuildConfig.Z8_BOOTSTRAP_SHA256.equals(installedHash)) {
                        throw new IllegalStateException(com.termux.app.Z8Text.text("The existing Linux prefix is incomplete or uses a different bootstrap. Files have been preserved; automatic replacement has stopped.", "기존 Linux prefix가 불완전하거나 다른 bootstrap입니다. 파일을 보존했으며 자동 덮어쓰기를 중단했습니다."));
                    }
                    whenDone.run();
                } catch (Exception e) {
                    new AlertDialog.Builder(activity).setTitle(com.termux.app.Z8Text.text("Linux runtime verification failed", "Linux 런타임 확인 실패"))
                        .setMessage(e.getMessage()).setPositiveButton(android.R.string.ok, null).show();
                }
                return;
            }
        } else if (FileUtils.fileExists(TERMUX_PREFIX_DIR_PATH, false)) {''')
    text = replace_exact(text, '''                    Logger.logInfo(LOG_TAG, "Bootstrap packages installed successfully.");''', '''                    File installedBash = new File(TERMUX_PREFIX_DIR, "bin/bash");
                    if (!installedBash.isFile() || !installedBash.canExecute())
                        throw new IllegalStateException("Bootstrap has no executable bin/bash");
                    java.nio.file.Files.write(new File(TERMUX_PREFIX_DIR, ".z8-bootstrap.sha256").toPath(),
                        (BuildConfig.Z8_BOOTSTRAP_SHA256 + "\\n").getBytes(java.nio.charset.StandardCharsets.UTF_8));
                    Logger.logInfo(LOG_TAG, "Bootstrap packages installed successfully.");''')
    path.write_text(text)


def copy_overlay(root, tree):
    overlay = root / "overlay"
    for original in sorted(overlay.rglob("*")):
        if original.is_symlink():
            raise PrepareError("Overlay symlinks are unsupported")
        if original.is_file():
            target = tree / original.relative_to(overlay)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, target)
    # Managed guest scripts ship with every APK, including upgrades of existing guests.
    managed = tree / "app/src/main/assets/z8/guest-managed"
    managed.mkdir(parents=True, exist_ok=True)
    for name in ("provision.sh", "debian-base-packages.txt", "shellrc", "welcome.sh", "setup-tools.sh",
                 "guest-task.sh", "install-ai.sh", "ai-tools.lock.json", "install-node.py", "node.lock.json", "probe-tools.sh", "browser-open.py", "html-preview.py", "xdg-open", "browser-profile.sh", "cli-profile.sh", "codex-launch.py"):
        source = root / "runtime/guest" / name
        if source.is_symlink() or not source.is_file():
            raise PrepareError("Managed guest asset missing: " + name)
        shutil.copy2(source, managed / name)
    if not (tree / "app/src/main/java/com/termux/app/Z8DiagnosticsActivity.java").is_file():
        raise PrepareError("Diagnostic Activity overlay is missing")
    patch_language(tree)


def patch_language(tree):
    java = tree / "app/src/main/java/com/termux/app"
    wrapper = '''    @Override protected void attachBaseContext(android.content.Context base) {
        super.attachBaseContext(com.termux.app.Z8Language.wrap(base));
    }

'''
    activities = [java / "TermuxApplication.java", java / "TermuxActivity.java",
                  java / "activities/SettingsActivity.java", java / "activities/HelpActivity.java",
                  java / "api/file/FileReceiverActivity.java", *sorted(java.glob("Z8*Activity.java"))]
    for path in activities:
        text = path.read_text()
        if "attachBaseContext(" in text:
            raise PrepareError("Language context anchor changed: " + path.name)
        match = re.search(r"public (?:final )?class \w+ extends [^{]+\{\n", text)
        if not match:
            raise PrepareError("Activity declaration missing: " + path.name)
        text = text[:match.end()] + "\n" + wrapper + text[match.end():]
        if path.name == "TermuxApplication.java":
            text = replace_exact(text, "        super.onCreate();", "        super.onCreate();\n        Z8Language.initialize(this);")
        path.write_text(text)

    # The shared module cannot depend on app classes. Its report screen follows the
    # application locale established by Z8Language, without changing shared APIs.
    report = tree / "termux-shared/src/main/java/com/termux/shared/activities/ReportActivity.java"
    text = report.read_text()
    marker = re.search(r"public (?:final )?class ReportActivity extends [^{]+\{\n", text)
    if not marker or "attachBaseContext(" in text:
        raise PrepareError("Report activity locale anchor changed")
    report_wrapper = '''
    @Override protected void attachBaseContext(android.content.Context base) {
        android.content.res.Configuration configuration = new android.content.res.Configuration(base.getResources().getConfiguration());
        configuration.setLocales(new android.os.LocaleList(java.util.Locale.getDefault()));
        super.attachBaseContext(base.createConfigurationContext(configuration));
    }
'''
    report.write_text(text[:marker.end()] + report_wrapper + text[marker.end():])


def apply_patches(tree, lock, mode, bootstrap_sha="", bootstrap=None, manifest=None, config=None):
    patch_gradle(tree, lock, mode, bootstrap_sha, config)
    patch_identity(tree, lock)
    patch_manifest(tree)
    patch_sessions(tree)
    patch_installer(tree)
    import importlib.util
    input_spec = importlib.util.spec_from_file_location("z8_terminal_input", ROOT / "tools/patch-terminal-input.py")
    input_patch = importlib.util.module_from_spec(input_spec)
    input_spec.loader.exec_module(input_patch)
    input_patch.patch(tree, replace_exact)
    links_spec = importlib.util.spec_from_file_location("z8_terminal_links", ROOT / "tools/patch-terminal-links.py")
    links_patch = importlib.util.module_from_spec(links_spec)
    links_spec.loader.exec_module(links_patch)
    links_patch.patch(tree, replace_exact)
    if mode == "diagnostic":
        edit(tree / "app/src/main/cpp/Android.mk", "LOCAL_SRC_FILES := termux-bootstrap-zip.S termux-bootstrap.c", "LOCAL_SRC_FILES := termux-bootstrap.c")
        (tree / "app/src/main/cpp/termux-bootstrap.c").write_text('''#include <jni.h>
// Diagnostic-only APK: deliberately contains no bootstrap bytes.
JNIEXPORT jbyteArray JNICALL Java_com_termux_app_TermuxInstaller_getZip(
    JNIEnv *env, __attribute__((__unused__)) jobject This) {
    return (*env)->NewByteArray(env, 0);
}
''')
    elif bootstrap and manifest:
        target = tree / "app/src/main/cpp/bootstrap-aarch64.zip"
        shutil.copyfile(bootstrap, target)
        if file_sha256(target) != bootstrap_sha:
            raise PrepareError("Runtime archive changed during preparation")
        assets = tree / "app/src/main/assets"
        assets.mkdir(exist_ok=True)
        shutil.copyfile(manifest, assets / "z8-runtime.json")
        copy_runtime_loader(tree, bootstrap)
    else:
        raise PrepareError("Runtime mode requires a verified bootstrap and manifest")


def copy_runtime_loader(tree, bootstrap):
    """Install the PRoot trampoline where Android permits direct execution."""
    with zipfile.ZipFile(bootstrap) as archive:
        try:
            data = archive.read("libexec/proot/loader")
        except KeyError as exc:
            raise PrepareError("Runtime is missing the source-built PRoot loader") from exc
    if len(data) < 64 or data[:6] != b"\x7fELF\x02\x01" or int.from_bytes(data[18:20], "little") != 183:
        raise PrepareError("PRoot loader must be a 64-bit little-endian ARM64 ELF")
    destination = tree / "app/src/main/jniLibs/arm64-v8a/libproot-loader.so"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    destination.chmod(0o755)


def file_sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def archive_member_path(name):
    path = PurePosixPath(name)
    if (not name or "\\" in name or "\0" in name or path.is_absolute()
            or any(part in {"", ".", ".."} for part in name.rstrip("/").split("/"))):
        raise PrepareError(f"Unsafe bootstrap entry: {name!r}")
    return str(path)


def validate_bootstrap_zip(archive, prefix):
    """Verify extraction safety and obvious ABI/prefix mistakes, not build provenance.

    The signed APK still needs the actual-device G0 execution tests. Merely
    passing ZIP inspection cannot establish Android or CLI compatibility.
    """
    if archive.stat().st_size > 512 * 1024 * 1024:
        raise PrepareError("Bootstrap ZIP exceeds the G0 512 MiB archive limit")
    try:
        with zipfile.ZipFile(archive) as bundle:
            infos = bundle.infolist()
            if len(infos) > 100000 or sum(i.file_size for i in infos) > 2 * 1024**3:
                raise PrepareError("Bootstrap exceeds G0 entry or expanded-size limits")
            names, regulars, links_text, bash_elf = set(), set(), None, False
            forbidden = (b"/data/data/com.termux/files", b"/data/user/0/com.termux/files")
            for info in infos:
                name = archive_member_path(info.filename)
                if name in names or name == ".z8-bootstrap.sha256":
                    raise PrepareError(f"Duplicate or reserved bootstrap entry: {name}")
                names.add(name)
                mode = info.external_attr >> 16
                kind = stat.S_IFMT(mode)
                if kind not in (0, stat.S_IFREG, stat.S_IFDIR) or info.flag_bits & 1:
                    raise PrepareError("ZIP links, special files and encrypted entries are unsupported; use SYMLINKS.txt")
                if info.is_dir():
                    continue
                regulars.add(name)
                if name == "SYMLINKS.txt":
                    if info.file_size > 16 * 1024 * 1024:
                        raise PrepareError("SYMLINKS.txt is too large")
                    links_text = bundle.read(info).decode("utf-8")
                    continue
                with bundle.open(info) as stream:
                    header, tail = b"", b""
                    while chunk := stream.read(128 * 1024):
                        if not header:
                            header = chunk[:64]
                            if header.startswith(b"\x7fELF"):
                                if len(header) < 20 or header[4:6] != b"\x02\x01" or int.from_bytes(header[18:20], "little") != 183:
                                    raise PrepareError(f"Expected aarch64 ELF in {name}")
                                if name == "bin/bash":
                                    bash_elf = True
                        joined = tail + chunk
                        if any(stock_prefix in joined for stock_prefix in forbidden):
                            raise PrepareError(f"Stock com.termux prefix remains in {name}; rebuild the runtime for z8")
                        tail = joined[-64:]
            if not bash_elf:
                raise PrepareError("Bootstrap must include a regular aarch64 ELF bin/bash")
            if not links_text:
                raise PrepareError("Bootstrap requires non-empty SYMLINKS.txt for the retained installer")
            destinations = set()
            for line in links_text.splitlines():
                if not line or line.count("←") != 1:
                    raise PrepareError("Malformed SYMLINKS.txt line")
                target, destination = line.split("←")
                destination = archive_member_path(destination)
                if destination in names or destination in destinations:
                    raise PrepareError("Symlink destination overlaps an archive member or another symlink")
                destinations.add(destination)
                if not target or "\\" in target or "\0" in target:
                    raise PrepareError("Invalid symlink target")
                if target.startswith("/"):
                    if not target.startswith(prefix + "/"):
                        raise PrepareError("Absolute bootstrap symlinks must remain within the z8 prefix")
                    parts = target[len(prefix) + 1:].split("/")
                else:
                    parts = [*PurePosixPath(destination).parent.parts, *target.split("/")]
                depth = 0
                for part in parts:
                    if part == "..":
                        depth -= 1
                    elif part not in {"", "."}:
                        depth += 1
                    if depth < 0:
                        raise PrepareError("Symlink target escapes the bootstrap prefix")
            for destination in destinations:
                if any(str(parent) in destinations for parent in PurePosixPath(destination).parents):
                    raise PrepareError("Symlink destination has a symlink parent")
    except (zipfile.BadZipFile, UnicodeError, RuntimeError) as exc:
        raise PrepareError(f"Invalid bootstrap ZIP: {exc}") from exc


def verify_runtime(manifest, lock):
    manifest = Path(manifest)
    if not manifest.is_file() or manifest.stat().st_size > 64 * 1024:
        raise PrepareError("Runtime manifest is missing or exceeds 64 KiB")
    data = json.loads(manifest.read_text())
    fields = {"schemaVersion", "applicationId", "prefix", "architecture", "archive", "sha256", "termuxPackagesCommit"}
    if not isinstance(data, dict) or set(data) != fields or type(data["schemaVersion"]) is not int or data["schemaVersion"] != 1:
        raise PrepareError("Unsupported runtime manifest schema")
    for field in ("applicationId", "prefix"):
        if data[field] != lock[field]:
            raise PrepareError(f"Runtime {field} does not match the z8 source lock")
    if data["architecture"] != "aarch64":
        raise PrepareError("Only aarch64 runtime archives are supported in G0")
    sha = data["sha256"]
    if not isinstance(sha, str) or not re.fullmatch(r"[a-f0-9]{64}", sha) or sha == "0" * 64:
        raise PrepareError("Runtime SHA-256 must be real; placeholder values are not installable")
    expected_commit = lock.get("termuxPackages", {}).get("commit")
    if not expected_commit or data["termuxPackagesCommit"] != expected_commit:
        raise PrepareError("Runtime termux-packages source commit does not match sources.lock.json")
    if not isinstance(data["archive"], str):
        raise PrepareError("Runtime archive must be a relative ZIP path")
    name = archive_member_path(data["archive"])
    archive = manifest.parent / name
    if (archive.suffix != ".zip" or archive.is_symlink() or not archive.is_file()
            or not archive.resolve().is_relative_to(manifest.parent.resolve())):
        raise PrepareError("Runtime archive must be a ZIP inside the manifest directory")
    if file_sha256(archive) != sha:
        raise PrepareError("Runtime archive SHA-256 mismatch")
    validate_bootstrap_zip(archive, data["prefix"])
    return archive, sha


def copy_guest(root, tree, manifest):
    # The guest image has a different archive contract from the native bootstrap:
    # Linux symlinks and file modes are normalized and checked by its own preparer.
    import importlib.util
    import sys
    specification = importlib.util.spec_from_file_location("z8_guest_preparer", root / "tools/prepare-guest.py")
    helper = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = helper
    specification.loader.exec_module(helper)
    try:
        archive, data = helper.verify_manifest(manifest)
    except Exception as exc:
        raise PrepareError("Guest archive verification failed: " + str(exc)) from exc
    assets = tree / "app/src/main/assets/z8/guest"
    assets.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(archive, assets / "rootfs.zip")
    if file_sha256(assets / "rootfs.zip") != data["archiveSha256"]:
        raise PrepareError("Guest archive changed during preparation")
    (assets / "manifest.json").write_text(json.dumps(data, indent=2) + "\n")


def prepare(root, mode, runtime_manifest=None, guest_manifest=None, release_config_path=None, variant="debug", output_name="build-src"):
    if mode not in {"diagnostic", "runtime"} or (mode == "runtime") != bool(runtime_manifest):
        raise PrepareError("Runtime mode requires --runtime-manifest; diagnostic mode must not supply one")
    lock = json.loads((root / "tools/sources.lock.json").read_text())
    config = release_config.load(release_config_path, production=variant == "release")
    validate_lock(lock)
    git = os.environ.get("Z8_GIT") or shutil.which("git")
    if not git:
        raise PrepareError("Git is required; set Z8_GIT")
    source = root / "upstream/termux-app"
    if not source.resolve().is_relative_to(root.resolve()):
        raise PrepareError("Upstream source must remain inside the project")
    names = verify_source(source, lock["termuxApp"]["commit"], git)
    bootstrap, sha = None, ""
    if mode == "runtime":
        bootstrap, sha = verify_runtime(runtime_manifest, lock)
    local, output = checked_local(root, output_name)
    staging = Path(tempfile.mkdtemp(prefix="prepare-app-", dir=local))
    try:
        copy_tracked(source, staging, names)
        apply_patches(staging, lock, mode, sha, bootstrap, runtime_manifest, config)
        copy_overlay(root, staging)
        if guest_manifest:
            copy_guest(root, staging, guest_manifest)
        (staging / "z8-prepared.json").write_text(json.dumps({
            "schemaVersion": 1, "applicationId": lock["applicationId"],
            "upstreamCommit": lock["termuxApp"]["commit"], "mode": mode,
            "bootstrapSha256": sha, "deviceGateStatus": "NOT_TESTED",
        }, indent=2) + "\n")
        # All validation and patching succeeded before replacing generated files.
        if output.exists():
            shutil.rmtree(output)
        staging.rename(output)
        return output
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("diagnostic", "runtime"), default="diagnostic")
    parser.add_argument("--runtime-manifest", type=Path)
    parser.add_argument("--guest-manifest", type=Path)
    parser.add_argument("--release-config", type=Path)
    parser.add_argument("--variant", choices=("debug", "candidate", "release"), default="debug")
    parser.add_argument("--output-name", default="build-src")
    args = parser.parse_args()
    try:
        output = prepare(ROOT, args.mode, args.runtime_manifest, args.guest_manifest, args.release_config, args.variant, args.output_name)
    except (PrepareError, OSError, json.JSONDecodeError) as exc:
        parser.exit(1, f"prepare-app: {exc}\n")
    print(f"Prepared {args.mode} source: {output}")


if __name__ == "__main__":
    main()
