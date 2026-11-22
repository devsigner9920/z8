"""Run the patched platform helpers without ART internals or a bypass dependency."""
import hashlib
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('public_api_preparer', ROOT / 'tools/prepare-app.py')
prepare = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare)
RELATIVE = 'termux-shared/src/main/java/com/termux/shared'


class PublicPlatformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = ROOT / 'upstream/termux-app'
        if not (source / RELATIVE).is_dir():
            raise unittest.SkipTest('Pinned upstream is required')
        jdk = ROOT / '.local/jdk/Contents/Home/bin'
        javac = str(jdk / 'javac') if (jdk / 'javac').is_file() else shutil.which('javac')
        cls.java = str(jdk / 'java') if (jdk / 'java').is_file() else shutil.which('java')
        if not javac or not cls.java:
            raise unittest.SkipTest('A JDK is required')
        temporary = tempfile.TemporaryDirectory(prefix='z8-public-platform-')
        cls.addClassCleanup(temporary.cleanup)
        cls.root = Path(temporary.name)
        cls.tree = cls.root / 'generated'
        shutil.copytree(source / RELATIVE, cls.tree / RELATIVE)
        cls.original_hashes = {p: hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in (source / RELATIVE).rglob('*.java')}
        prepare.patch_public_android_api(cls.tree)
        cls.shared = cls.tree / RELATIVE
        sources = []
        for name, content in STUBS.items():
            path = cls.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            sources.append(str(path))
        probe = cls.root / 'PlatformProbe.java'
        probe.write_text(PROBE)
        actual = [cls.shared / name for name in (
            'reflection/ReflectionUtils.java', 'android/UserUtils.java',
            'android/SELinuxUtils.java', 'android/FeatureFlagUtils.java',
            'net/socket/local/PeerCred.java')]
        # Compile production helpers against the real SDK separately. Android test
        # doubles must never make an invented/non-SDK API appear publicly usable.
        sdk = ROOT / '.local/android-sdk/platforms/android-36/android.jar'
        cls.sdk_checked = sdk.is_file()
        if cls.sdk_checked:
            sdk_classes = cls.root / 'sdk-classes'
            sdk_classes.mkdir()
            own_stubs = [p for p in sources if not Path(p).relative_to(cls.root).parts[0] == 'android'
                         and not Path(p).relative_to(cls.root).parts[0] == 'libcore']
            checked = subprocess.run([javac, '-encoding', 'UTF-8', '-classpath', str(sdk),
                                      '-d', str(sdk_classes), *map(str, actual), *own_stubs],
                                     capture_output=True, text=True, timeout=30)
            if checked.returncode:
                raise AssertionError('Public SDK compile failed:\n' + checked.stdout + checked.stderr)
        cls.classes = cls.root / 'classes'
        cls.classes.mkdir()
        compiled = subprocess.run([javac, '-encoding', 'UTF-8', '-d', str(cls.classes),
                                   *map(str, actual), str(probe), *sources],
                                  capture_output=True, text=True, timeout=30)
        if compiled.returncode:
            raise AssertionError(compiled.stdout + compiled.stderr)

    def probe(self, scenario):
        result = subprocess.run([self.java, '-cp', str(self.classes), 'PlatformProbe', scenario],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('PASS ' + scenario, result.stdout)

    def test_bypass_entry_point_never_claims_to_exempt_hidden_apis(self):
        self.probe('no-bypass')

    def test_optional_selinux_and_feature_diagnostics_are_unavailable_without_probing(self):
        self.probe('unavailable')

    def test_public_package_manager_result_has_priority_and_uid_suffix_is_preserved_correctly(self):
        self.probe('package-name')

    def test_unknown_uid_and_gid_keep_the_real_numeric_peer_identity(self):
        self.probe('numeric-peer')

    def test_invalid_uid_does_not_call_the_platform(self):
        self.probe('invalid-uid')

    def test_unknown_or_denied_package_name_does_not_break_callers(self):
        self.probe('lookup-failures')

    def test_helpers_compile_against_actual_public_android_sdk(self):
        if not self.sdk_checked:
            self.skipTest('Android SDK 36 is unavailable')
        self.assertTrue((self.root / 'sdk-classes/com/termux/shared/android/UserUtils.class').is_file())

    def test_ordinary_app_owned_reflection_is_not_removed(self):
        self.probe('app-reflection')

    def test_private_application_diagnostics_cannot_invoke_reflection(self):
        text = (self.shared / 'android/PackageUtils.java').read_text()
        for signature in ('getApplicationInfoPrivateFlagsForPackage',
                          'getApplicationInfoSeInfoForPackage',
                          'getApplicationInfoSeInfoUserForPackage',
                          'getApplicationInfoStaticIntFieldValue'):
            declaration = prepare.re.search(r'^    public static [^\n]+ ' + signature + r'\([^\n]+\{\n.*?^    }',
                                            text, prepare.re.M | prepare.re.S)
            self.assertIsNotNone(declaration, signature)
            body = declaration.group()
            self.assertIn('return null;', body)
            self.assertNotIn('ReflectionUtils.', body)
            self.assertNotIn('Class.forName', body)
        self.assertNotIn('"SE_INFO",', (self.shared / 'android/AndroidUtils.java').read_text())

    def test_changed_patch_anchor_fails_instead_of_leaving_a_partial_bypass(self):
        with tempfile.TemporaryDirectory() as temporary:
            tree = Path(temporary)
            original = ROOT / 'upstream/termux-app' / RELATIVE
            shutil.copytree(original, tree / RELATIVE)
            path = tree / RELATIVE / 'reflection/ReflectionUtils.java'
            path.write_text(path.read_text().replace('HiddenApiBypass.addHiddenApiExemptions("")',
                                                     'HiddenApiBypass.addHiddenApiExemptions("changed")'))
            with self.assertRaisesRegex(prepare.PrepareError, 'Public API patch anchor changed'):
                prepare.patch_public_android_api(tree)

    def test_pinned_upstream_was_not_modified(self):
        for path, digest in self.original_hashes.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest, str(path))


STUBS = {
    'androidx/annotation/NonNull.java': 'package androidx.annotation;public @interface NonNull {}',
    'androidx/annotation/Nullable.java': 'package androidx.annotation;public @interface Nullable {}',
    'androidx/annotation/Keep.java': 'package androidx.annotation;public @interface Keep {}',
    'android/content/Context.java': '''package android.content;public class Context {
        public final android.content.pm.PackageManager pm=new android.content.pm.PackageManager();
        public android.content.pm.PackageManager getPackageManager(){return pm;}}''',
    'android/content/pm/PackageManager.java': '''package android.content.pm;public class PackageManager {
        public String answer;public boolean fail;public int calls;
        public String getNameForUid(int uid){calls++;if(fail)throw new SecurityException("fixture");return answer;}}''',
    'libcore/io/Libcore.java': '''package libcore.io;public class Libcore {
        static {if(true)throw new AssertionError("Hidden Libcore must not be initialized");}}''',
    'android/os/SELinux.java': '''package android.os;public class SELinux {
        static {if(true)throw new AssertionError("Hidden SELinux API must not be initialized");}}''',
    'android/util/FeatureFlagUtils.java': '''package android.util;public class FeatureFlagUtils {
        static {if(true)throw new AssertionError("Hidden feature API must not be initialized");}}''',
    'com/termux/shared/logger/Logger.java': '''package com.termux.shared.logger;public class Logger {
        public static void logError(String tag,String message){}
        public static void logStackTraceWithMessage(String tag,String message,Throwable failure){}
        public static void logDebug(String tag,String message){}
        public static String getSingleLineLogStringEntry(String key,String value,String fallback){return value;}
        public static String getMultiLineLogStringEntry(String key,String value,String fallback){return value;}}''',
    'com/termux/shared/markdown/MarkdownUtils.java': '''package com.termux.shared.markdown;public class MarkdownUtils {
        public static String getSingleLineMarkdownStringEntry(String key,String value,String fallback){return value;}
        public static String getMultiLineMarkdownStringEntry(String key,String value,String fallback){return value;}}''',
    'com/termux/shared/android/ProcessUtils.java': '''package com.termux.shared.android;public class ProcessUtils {
        public static String getAppProcessNameForPid(android.content.Context context,int pid){return null;}}''',
}

PROBE = r'''import android.content.Context;
import com.termux.shared.android.UserUtils;
import com.termux.shared.android.SELinuxUtils;
import com.termux.shared.android.FeatureFlagUtils;
import com.termux.shared.reflection.ReflectionUtils;
import com.termux.shared.net.socket.local.PeerCred;

public class PlatformProbe {
    static void check(boolean condition){if(!condition)throw new AssertionError();}
    public static class Owned {private String value="owned";private String read(){return value;}}
    public static void main(String[] args)throws Exception {
        Context context=new Context();
        switch(args[0]) {
            case "no-bypass":
                check(!ReflectionUtils.areHiddenAPIReflectionRestrictionsBypassed());
                ReflectionUtils.bypassHiddenAPIReflectionRestrictions();
                ReflectionUtils.bypassHiddenAPIReflectionRestrictions();
                check(!ReflectionUtils.areHiddenAPIReflectionRestrictionsBypassed());break;
            case "unavailable":
                check(SELinuxUtils.getContext()==null);check(SELinuxUtils.getPidContext(123)==null);
                check(SELinuxUtils.getFileContext("/inert")==null);
                check(FeatureFlagUtils.getAllFeatureFlags()==null);
                check(FeatureFlagUtils.isFeatureEnabled(context,"inert")==null);
                check(FeatureFlagUtils.featureFlagExists("inert")==null);
                check(FeatureFlagUtils.getFeatureFlagValueString(context,"inert")==FeatureFlagUtils.FeatureFlagValue.UNKNOWN);break;
            case "package-name":
                context.pm.answer="example.app:10001";
                check("example.app".equals(UserUtils.getNameForUid(context,10001)));
                context.pm.answer="name:other";
                check("name:other".equals(UserUtils.getNameForUid(context,10001)));break;
            case "numeric-peer":
                java.lang.reflect.Constructor<PeerCred> ctor=PeerCred.class.getDeclaredConstructor();
                ctor.setAccessible(true);PeerCred peer=ctor.newInstance();
                peer.uid=0;peer.gid=99;peer.fillUnameAndGname(context);
                check(peer.uname==null);check(peer.gname==null);
                check("0".equals(peer.getUserString()));check("99".equals(peer.getGroupString()));
                check(peer.uid==0);check(peer.gid==99);break;
            case "invalid-uid":
                check(UserUtils.getNameForUid(context,-1)==null);
                check(UserUtils.getNameForUidFromLibcore(-1)==null);
                check(context.pm.calls==0);break;
            case "lookup-failures":
                check(UserUtils.getNameForUid(context,12)==null);
                context.pm.fail=true;check(UserUtils.getNameForUid(context,12)==null);
                check(UserUtils.getNameForUidFromLibcore(0)==null);break;
            case "app-reflection":
                Owned object=new Owned();
                check("owned".equals(ReflectionUtils.getDeclaredField(Owned.class,"value").get(object)));
                check("owned".equals(ReflectionUtils.invokeMethod(ReflectionUtils.getDeclaredMethod(Owned.class,"read"),object).value));
                check(ReflectionUtils.getDeclaredMethod(Owned.class,"missing")==null);break;
            default:throw new AssertionError(args[0]);
        }
        System.out.println("PASS "+args[0]);
    }
}'''


if __name__ == '__main__':
    unittest.main()
