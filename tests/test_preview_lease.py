"""Execute the production preview lease validator; no notification/browser stubs exist."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def method(source, signature):
    start = source.index(signature)
    end = source.index('{', start) + 1
    depth = 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


class PreviewLeaseTests(unittest.TestCase):
    def test_only_authenticated_live_project_launch_can_keep_preview_alive(self):
        production = (ROOT / 'overlay/app/src/main/java/com/termux/app/Z8AttentionBridge.java').read_text()
        self.assertIn('if ("preview-check".equals(event.optString("kind"))) return acceptPreviewCheck(event);', production)
        methods = '\n'.join(method(production, signature) for signature in (
            'private String acceptPreviewCheck(JSONObject event)',
            'private static String id(JSONObject object, String name, boolean optional)'))
        source = r'''import java.util.*; import java.security.MessageDigest; import java.nio.charset.StandardCharsets;
public class LeaseProbe {
    static class JSONException extends Exception {}
    static class JSONObject {
        final Map<String,Object> values=new HashMap<>();
        JSONObject put(String k,Object v){values.put(k,v);return this;}
        Iterator<String> keys(){return values.keySet().iterator();}
        Object opt(String k){return values.get(k);}
        boolean has(String k){return values.containsKey(k);}
        double getDouble(String k){return ((Number)values.get(k)).doubleValue();}
    }
    static class Session {boolean running=true,owned=true;boolean isRunning(){return running;}}
    static class Launch {String token="a".repeat(64);Session session=new Session();}
    static class Z8SessionOrigin {static Object of(Session s){return s.owned?s:null;}}
    Map<String,Launch> launches=new HashMap<>();
''' + methods + r'''
    static JSONObject event(){return new JSONObject().put("schemaVersion",1).put("eventId","probe-1")
        .put("launchId","launch-1").put("token","a".repeat(64)).put("kind","preview-check");}
    static void expect(String expected,String actual){if(!expected.equals(actual))throw new AssertionError(expected+" != "+actual);}
    public static void main(String[] args)throws Exception {
        LeaseProbe p=new LeaseProbe();Launch launch=new Launch();p.launches.put("launch-1",launch);
        expect("accepted",p.acceptPreviewCheck(event()));
        expect("accepted",p.acceptPreviewCheck(event())); // checks do not consume or queue an event ID
        expect("unauthorized",p.acceptPreviewCheck(event().put("token","b".repeat(64))));
        expect("unauthorized",p.acceptPreviewCheck(event().put("token",1)));
        expect("unauthorized",p.acceptPreviewCheck(event().put("launchId","other")));
        expect("invalid",p.acceptPreviewCheck(event().put("url","http://127.0.0.1/")));
        expect("invalid",p.acceptPreviewCheck(event().put("schemaVersion","1")));
        expect("invalid",p.acceptPreviewCheck(event().put("schemaVersion",2)));
        try {p.acceptPreviewCheck(event().put("eventId","bad id"));throw new AssertionError("Bad ID accepted");}
        catch(IllegalArgumentException expected){}
        launch.session.running=false;expect("stale",p.acceptPreviewCheck(event()));
        launch.session.running=true;launch.session.owned=false;expect("stale",p.acceptPreviewCheck(event()));
        launch.session=null;expect("stale",p.acceptPreviewCheck(event()));
        p.launches.clear();expect("unauthorized",p.acceptPreviewCheck(event()));
        System.out.println("PASS preview lease");
    }
}'''
        with tempfile.TemporaryDirectory(prefix='z8-preview-lease-') as directory:
            path = Path(directory)
            (path / 'LeaseProbe.java').write_text(source)
            jdk = ROOT / '.local/jdk/Contents/Home/bin'
            result = subprocess.run([str(jdk / 'javac'), '-d', str(path), str(path / 'LeaseProbe.java')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(jdk / 'java'), '-cp', str(path), 'LeaseProbe'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('PASS preview lease', result.stdout)
