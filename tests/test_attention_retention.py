"""Run the real intake transaction against a full inbox, with Android I/O stubbed."""
from pathlib import Path
import shutil
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


class AttentionRetentionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        jdk = ROOT / '.local/jdk/Contents/Home/bin'
        javac = str(jdk / 'javac') if (jdk / 'javac').is_file() else shutil.which('javac')
        cls.java = str(jdk / 'java') if (jdk / 'java').is_file() else shutil.which('java')
        if not javac or not cls.java:
            raise unittest.SkipTest('A JDK is required')
        production = (ROOT / 'overlay/app/src/main/java/com/termux/app/Z8AttentionBridge.java').read_text()
        actual = '\n'.join(method(production, signature) for signature in (
            'private synchronized String accept(JSONObject event)',
            'private JSONObject oldestDiscardableItem()',
            'private static String id(JSONObject object, String name, boolean optional)'))
        cls.temporary = tempfile.TemporaryDirectory(prefix='z8-retention-')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.directory = Path(cls.temporary.name)
        path = cls.directory / 'RetentionProbe.java'
        path.write_text(PREFIX + actual + SUFFIX)
        result = subprocess.run([javac, '-encoding', 'UTF-8', '-d', str(cls.directory), str(path)],
                                capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)

    def probe(self, scenario):
        result = subprocess.run([self.java, '-cp', str(self.directory), 'RetentionProbe', scenario],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_long_running_inbox_retains_unread_requests_and_accepts_new_ones(self):
        self.probe('replace')

    def test_full_unread_live_requests_are_never_evicted(self):
        self.probe('protected')

    def test_invalid_and_duplicate_intake_never_trim_history(self):
        self.probe('validation')

    def test_storage_failure_restores_history_and_notifications_before_retry(self):
        self.probe('rollback')

    def test_notification_cleanup_failure_does_not_lose_committed_request(self):
        self.probe('notification')


PREFIX = r'''
import java.util.*; import java.io.*; import java.security.MessageDigest; import java.nio.charset.StandardCharsets;
public class RetentionProbe {
    static class JSONException extends Exception {}
    static class JSONObject {
        final Map<String,Object> values = new LinkedHashMap<>();
        JSONObject put(String key,Object value){ values.put(key,value); return this; }
        Object opt(String key){ return values.get(key); }
        boolean has(String key){ return values.containsKey(key); }
        Iterator<String> keys(){ return values.keySet().iterator(); }
        String optString(String key){ Object value=values.get(key); return value instanceof String?(String)value:""; }
        long optLong(String key){ Object value=values.get(key); return value instanceof Number?((Number)value).longValue():0; }
        double getDouble(String key){ return ((Number)values.get(key)).doubleValue(); }
    }
    static class TerminalSession { String mHandle="terminal-1"; boolean running=true; boolean isRunning(){return running;} }
    static class Launch { String token="a".repeat(64); TerminalSession session=new TerminalSession(); }
    static class NotificationManager {
        boolean fail; final List<String> cancelled=new ArrayList<>();
        void cancel(String id,int value){ if(fail)throw new SecurityException(); cancelled.add(id); }
    }
    static class Context {
        final NotificationManager manager=new NotificationManager();
        <T> T getSystemService(Class<T> type){return type.cast(manager);}
    }
    final Context context=new Context();
    final List<JSONObject> items=new ArrayList<>(), delivered=new ArrayList<>();
    final Map<String,Launch> launches=new HashMap<>();
    final int MAX_ITEMS=256;
    boolean failSave; int saves;
    void pruneLaunches(){} // Records supplied below have already reconciled session state.
    void saveState() throws IOException {saves++;if(failSave)throw new IOException("synthetic disk error");}
    void postNotification(JSONObject item){delivered.add(item);}
    void attachSessionLabels(JSONObject item,TerminalSession session){item.put("projectId","fixture-project");}
    String acceptBrowser(JSONObject event){throw new AssertionError();}
    String acceptPreviewCheck(JSONObject event){throw new AssertionError();}
'''

SUFFIX = r'''
    static JSONObject request(String nonce) {
        return new JSONObject().put("schemaVersion",1).put("eventId",nonce).put("launchId","launch-1")
            .put("token","a".repeat(64)).put("provider","codex").put("kind","permission");
    }
    static RetentionProbe full() {
        RetentionProbe p=new RetentionProbe();p.launches.put("launch-1",new Launch());
        for(int i=0;i<256;i++)p.items.add(new JSONObject().put("id","old-"+i).put("eventId","nonce-"+i)
            .put("launchId","launch-1").put("provider","codex").put("kind","permission")
            .put("observedAt",1000+i).put("seenAt",0).put("state","OBSERVED"));
        return p;
    }
    static void check(boolean value,String label){if(!value)throw new AssertionError(label);}
    static boolean has(RetentionProbe p,String id){return p.items.stream().anyMatch(i->id.equals(i.optString("id")));}
    public static void main(String[] args)throws Exception {
        RetentionProbe p=full();List<JSONObject> original=new ArrayList<>(p.items);
        switch(args[0]) {
        case "replace":
            p.items.get(7).put("seenAt",100);p.items.get(4).put("state","STALE");p.items.get(11).put("kind","finished");
            check("accepted".equals(p.accept(request("new-1"))),"full history must accept new request");
            check(p.items.size()==256&&!has(p,"old-4")&&has(p,"old-0"),"oldest eligible record only; unread survives");
            check(p.context.manager.cancelled.equals(List.of("old-4")),"retired notification cancelled");
            check("accepted".equals(p.accept(request("new-2")))&&!has(p,"old-7"),"read item next");
            check("accepted".equals(p.accept(request("new-3")))&&!has(p,"old-11"),"completed record next");
            check("full".equals(p.accept(request("new-4")))&&p.items.size()==256,"only unread requests now remain");
            break;
        case "protected":
            check("full".equals(p.accept(request("new"))),"all unread live requests protected");
            check(p.items.equals(original)&&p.saves==0&&p.context.manager.cancelled.isEmpty(),"rejection changes nothing");
            break;
        case "validation":
            p.items.get(4).put("state","STALE");
            check("duplicate".equals(p.accept(request("nonce-2"))),"duplicate before retention");
            check("unauthorized".equals(p.accept(request("new").put("token","b".repeat(64)))),"bad credential");
            check("invalid".equals(p.accept(request("new").put("private","not allowed"))),"bad schema");
            check(p.items.equals(original)&&p.saves==0&&p.context.manager.cancelled.isEmpty(),"no trim on rejected intake");
            break;
        case "rollback":
            p.items.get(4).put("state","STALE");p.failSave=true;
            check("storage-failed".equals(p.accept(request("new"))),"failure surfaced");
            check(p.items.equals(original)&&p.delivered.isEmpty()&&p.context.manager.cancelled.isEmpty(),"history and order restored; notices intact");
            p.failSave=false;check("accepted".equals(p.accept(request("new"))),"same event retry works");
            check(!has(p,"old-4")&&p.delivered.size()==1&&p.context.manager.cancelled.equals(List.of("old-4")),"only durable retry publishes");
            break;
        case "notification":
            p.items.get(4).put("seenAt",12);p.context.manager.fail=true;
            check("accepted".equals(p.accept(request("new"))),"cleanup failure does not abort intake");
            check(p.delivered.size()==1&&!has(p,"old-4"),"new notification still published");
            break;
        default:throw new AssertionError(args[0]);
        }
        System.out.println("PASS attention retention "+args[0]);
    }
}
'''
