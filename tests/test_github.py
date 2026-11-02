"""GitHub reads and confirmed-clone contracts with fixtures; no account/network."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class GitHubReadTests(unittest.TestCase):
    def test_guest_runner_and_response_fixtures(self):
        jdk = ROOT / ".local/jdk/Contents/Home/bin"
        javac = str(jdk / "javac") if (jdk / "javac").is_file() else shutil.which("javac")
        java = str(jdk / "java") if (jdk / "java").is_file() else shutil.which("java")
        # Gson is a test decoder already shipped in the Gradle dependency cache.
        # Android production uses its platform org.json parser, not this jar.
        jars = list((ROOT / ".local/gradle/caches/modules-2/files-2.1/com.google.code.gson/gson").glob("*/*/gson-*.jar"))
        if not jars:
            jars = list((Path.home() / ".gradle/caches/modules-2/files-2.1/com.google.code.gson/gson").glob("*/*/gson-*.jar"))
        if not javac or not java or not jars:
            self.skipTest("Requires the configured JDK and Gradle's cached Gson fixture decoder; does not download dependencies")
        gson = str(sorted(jars)[-1])
        with tempfile.TemporaryDirectory(prefix="z8-github-tests-") as directory:
            output = Path(directory).resolve()
            probe = output / "GitHubProbe.java"
            probe.write_text(JAVA_PROBE)
            sources = ROOT / "overlay/app/src/main/java/com/termux/app"
            compiled = subprocess.run([javac, str(ROOT / 'overlay/app/src/main/java/com/termux/app/Z8Text.java'), "-encoding", "UTF-8", "-cp", gson, "-d", str(output),
                str(sources / "Z8Files.java"), str(sources / "Z8Git.java"), str(sources / "Z8GitHub.java"), str(probe)],
                capture_output=True, text=True, timeout=45)
            self.assertEqual(0, compiled.returncode, compiled.stdout + compiled.stderr)
            tested = subprocess.run([java, "-cp", str(output) + ":" + gson, "com.termux.app.GitHubProbe", java, str(output)],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(0, tested.returncode, tested.stdout + tested.stderr)
            self.assertIn("PASS: GitHub read contracts", tested.stdout)


JAVA_PROBE = r'''
package com.termux.app;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import com.google.gson.Gson;

public final class GitHubProbe {
    interface Action { void run() throws Exception; }
    static int checks;
    static void check(boolean good, String label) { if (!good) throw new AssertionError(label); checks++; }
    static void denied(Action work, String label) throws Exception {
        try { work.run(); } catch (IOException expected) { checks++; return; }
        throw new AssertionError(label);
    }
    static byte[] bytes(String value) { return value.getBytes(StandardCharsets.UTF_8); }
    static Object decode(String json) { return new Gson().fromJson(json, Object.class); }
    static Z8GitHub.Page parse(Z8GitHub.View view, String json) throws Exception { return Z8GitHub.parse(view, "octo/work", decode(json), 1); }
    static Z8GitHub.CloneState completed(String id) throws Exception {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
        while (System.nanoTime() < deadline) {
            Z8GitHub.CloneState state = Z8GitHub.cloneState(id);
            if (state != null && state.phase != Z8GitHub.ClonePhase.RUNNING) return state;
            Thread.sleep(10);
        }
        throw new AssertionError("clone worker did not complete");
    }
    static Z8GitHub.DraftState drafted(String id) throws Exception {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
        while (System.nanoTime() < deadline) {
            Z8GitHub.DraftState state = Z8GitHub.draftState(id);
            if (state != null && !state.running()) return state;
            Thread.sleep(10);
        }
        throw new AssertionError("draft worker did not complete");
    }
    static final class DraftFixture implements Z8Git.Runner {
        final String mode; final Z8GitHub.DraftRequest expected;
        final AtomicInteger posts = new AtomicInteger();
        final CountDownLatch postEntered = new CountDownLatch(1), postRelease = new CountDownLatch(1);
        DraftFixture(String mode, Z8GitHub.DraftRequest expected) { this.mode = mode; this.expected = expected; }
        String response() {
            return "{\"number\":42,\"state\":\"open\",\"draft\":true,\"html_url\":\"https://"
                + (mode.equals("bad_url") ? "evil.invalid" : "github.com") + "/octo/work/pull/42\","
                + "\"head\":{\"label\":\"octo:feature/review\"},\"base\":{\"ref\":\"main\",\"repo\":{\"full_name\":\"octo/work\"}}}";
        }
        @Override public Z8Git.Result run(List<String> argv, File cwd, Map<String,String> env, byte[] input, int timeout, int limit) throws IOException {
            check(timeout == 30 && limit == Z8GitHub.MAX_OUTPUT, "draft/read process limits retained");
            check(!argv.contains("auth"), "authentication must not trust gh auth status");
            String endpoint = argv.get(argv.size()-1), method = argv.get(argv.indexOf("--method") + 1);
            if (method.equals("POST")) {
                posts.incrementAndGet();
                check(endpoint.equals("repos/octo/work/pulls") && argv.contains("--input") && argv.get(argv.indexOf("--input")+1).equals("-"), "draft is fixed POST endpoint with stdin JSON");
                check(!String.join(" ", argv).contains(expected.title) && !String.join(" ", argv).contains(expected.body), "PR title/body never appear in argv");
                Map<?,?> payload = (Map<?,?>) decode(new String(input, StandardCharsets.UTF_8));
                check(Boolean.TRUE.equals(payload.get("draft")) && payload.get("title").equals(expected.title)
                    && payload.get("body").equals(expected.body) && payload.get("head").equals(expected.head)
                    && payload.get("base").equals(expected.base), "stdin preserves exact reviewed draft fields");
                check(!env.containsKey("GH_TOKEN") && !env.containsKey("GITHUB_TOKEN"), "draft uses project auth, never host token");
                postEntered.countDown();
                if (mode.equals("hold")) try { if (!postRelease.await(5,TimeUnit.SECONDS)) throw new IOException("fixture timeout"); }
                catch (InterruptedException interrupted) { throw new IOException("fixture interrupted"); }
                if (mode.equals("unknown")) throw new IOException("network response lost secret-token");
                if (mode.equals("validation")) return new Z8Git.Result(1,new byte[0],bytes("Validation Failed (HTTP 422) secret-token"));
                return new Z8Git.Result(0,bytes(response()),new byte[0]);
            }
            check(method.equals("GET") && input.length == 0, "preflight never writes");
            if (endpoint.equals("user")) return new Z8Git.Result(mode.equals("auth_fail") ? 1 : 0,bytes("{\"id\":42,\"login\":\"" + (mode.equals("account_changed") ? "another" : "octo") + "\"}"),bytes("HTTP 401 secret-token"));
            if (endpoint.equals("repos/octo/work")) return new Z8Git.Result(0,
                bytes("{\"full_name\":\"octo/work\",\"default_branch\":\"main\",\"permissions\":{\"pull\":true},\"archived\":false}"),new byte[0]);
            check(endpoint.equals(Z8GitHub.duplicateEndpoint(expected)), "duplicate query uses exact qualified head and base");
            if (mode.equals("read_fail")) return new Z8Git.Result(1,new byte[0],bytes("HTTP 403 secret-token"));
            return new Z8Git.Result(0,bytes(mode.equals("duplicate") ? "[" + response() + "]" : "[]"),new byte[0]);
        }
    }
    static Z8GitHub.ReviewState reviewed(String id) throws Exception {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
        while (System.nanoTime() < deadline) {
            Z8GitHub.ReviewState state = Z8GitHub.reviewState(id);
            if (state != null && !state.running) return state;
            Thread.sleep(10);
        }
        throw new AssertionError("review worker did not complete");
    }
    static final class ReviewFixture implements Z8Git.Runner {
        final String mode; final Z8GitHub.ReviewRequest request;
        int posts; final CountDownLatch entered = new CountDownLatch(1), release = new CountDownLatch(1);
        ReviewFixture(String mode, Z8GitHub.ReviewRequest request) { this.mode = mode; this.request = request; }
        @Override public Z8Git.Result run(List<String> argv, File cwd, Map<String,String> env, byte[] input, int timeout, int limit) throws IOException {
            check(timeout == 30 && limit == Z8GitHub.MAX_OUTPUT, "review execution remains bounded");
            check(!env.containsKey("GH_TOKEN") && !env.containsKey("GITHUB_TOKEN"), "review uses project auth only");
            String endpoint = argv.get(argv.size()-1), method = argv.get(argv.indexOf("--method")+1);
            if (endpoint.equals("user")) return new Z8Git.Result(0,bytes("{\"login\":\"" + (mode.equals("account") ? "other" : "octo") + "\",\"id\":42}"),new byte[0]);
            if (method.equals("GET")) {
                check(input.length == 0 && endpoint.equals("repos/octo/work/pulls/7"), "review reads selected PR before write");
                return new Z8Git.Result(0, bytes("{\"number\":7,\"title\":\"Review\",\"state\":\"" + (mode.equals("closed") ? "closed" : "open")
                    + "\",\"head\":{\"sha\":\"" + (mode.equals("head") ? String.join("",Collections.nCopies(40,"b")) : request.commit) + "\"}}"),new byte[0]);
            }
            posts++;
            check(method.equals("POST") && endpoint.equals("repos/octo/work/pulls/7/reviews") && argv.contains("--input"), "review fixed endpoint and JSON stdin");
            check(!String.join(" ",argv).contains(request.body), "review body is never shell or argv data");
            Map<?,?> payload = (Map<?,?>) decode(new String(input,StandardCharsets.UTF_8));
            check(payload.get("body").equals(request.body) && payload.get("commit_id").equals(request.commit) && payload.get("event").equals(request.event), "exact inspected review and HEAD submitted");
            if (mode.equals("hold")) {
                entered.countDown(); try { if (!release.await(5,TimeUnit.SECONDS)) throw new IOException("fixture timeout"); }
                catch (InterruptedException failure) { throw new IOException("interrupted"); }
            }
            if (mode.equals("unknown")) throw new IOException("response lost secret-token");
            if (mode.equals("reject")) return new Z8Git.Result(1,new byte[0],bytes("HTTP 422 secret-token"));
            String state = request.event.equals("APPROVE") ? "APPROVED" : request.event.equals("REQUEST_CHANGES") ? "CHANGES_REQUESTED" : "COMMENTED";
            return new Z8Git.Result(0,bytes("{\"id\":99,\"state\":\""+state+"\",\"commit_id\":\""+request.commit+"\",\"user\":{\"login\":\"octo\"},\"pull_request_url\":\"https://api.github.com/repos/octo/"
                + (mode.equals("wrong_target") ? "other" : "work") + "/pulls/7\"}"),new byte[0]);
        }
    }
    public static void main(String[] args) throws Exception {
        String commit = String.join("", Collections.nCopies(40, "a"));
        String work = "{\"number\":7,\"title\":\"한글 <script> text\",\"body\":\"literal `$(touch never)`\",\"state\":\"open\",\"user\":{\"login\":\"octo\"}}";
        Z8GitHub.Page issue = parse(Z8GitHub.View.ISSUE, work);
        check(issue.rows.get(0).number == 7 && issue.rows.get(0).title.contains("<script>"), "remote markup remains display text");
        check(issue.rows.get(0).body.contains("$(touch never)"), "remote commands remain body text");
        String pull = work.substring(0, work.length() - 1) + ",\"draft\":true,\"head\":{\"sha\":\"" + commit + "\"},\"merged_at\":null}";
        Z8GitHub.Row pr = parse(Z8GitHub.View.PULL, pull).rows.get(0);
        check(pr.kind == Z8GitHub.Kind.PULL && pr.sha.equals(commit) && pr.detail.startsWith("open · draft"), "PR head and draft state");
        check(parse(Z8GitHub.View.PULL, pull.replace("\"merged_at\":null", "\"merged_at\":\"2026-10-01\"")).rows.get(0).detail.startsWith("merged"), "merged differs from closed");
        check(parse(Z8GitHub.View.ISSUES, "[" + work + "," + work.substring(0, work.length()-1) + ",\"pull_request\":{}}]").rows.size() == 1, "REST issue list excludes PR entries");
        StringBuilder fullPullPage = new StringBuilder("[");
        for (int i=0;i<30;i++) { if(i>0) fullPullPage.append(','); fullPullPage.append(work.substring(0,work.length()-1)).append(",\"pull_request\":{}}"); }
        fullPullPage.append(']');
        Z8GitHub.Page emptyIssuePage = parse(Z8GitHub.View.ISSUES, fullPullPage.toString());
        check(emptyIssuePage.rows.isEmpty() && emptyIssuePage.mayHaveNext, "filtered empty page still allows next server page");
        Z8GitHub.Page checksPage = parse(Z8GitHub.View.CHECKS, "{\"check_runs\":[{\"name\":\"unit\",\"status\":\"in_progress\",\"conclusion\":null},{\"name\":\"lint\",\"status\":\"completed\",\"conclusion\":\"failure\"}]}");
        check(checksPage.rows.get(0).detail.equals("in_progress") && checksPage.rows.get(1).detail.equals("failure"), "pending and failed checks are not successful");
        check(parse(Z8GitHub.View.STATUSES, "{\"state\":\"pending\",\"statuses\":[]}").rows.isEmpty(), "empty statuses do not fabricate a green aggregate");
        check(parse(Z8GitHub.View.ACTIONS, "{\"workflow_runs\":[{\"name\":\"Build\",\"status\":\"completed\",\"conclusion\":\"cancelled\",\"head_branch\":\"main\"}]}").rows.get(0).detail.endsWith("cancelled"), "Actions cancellation preserved");
        String repo = "{\"full_name\":\"octo/work\",\"private\":true,\"description\":null,\"default_branch\":\"main\"}";
        check(parse(Z8GitHub.View.REPOSITORY, repo).rows.get(0).detail.equals("Private"), "private repository metadata");
        check(parse(Z8GitHub.View.SEARCH, "{\"items\":[" + repo + "],\"incomplete_results\":true}").summary.contains("Partial"), "incomplete search explicitly labeled");
        denied(() -> parse(Z8GitHub.View.ISSUE, "{\"number\":1.5,\"title\":\"bad\"}"), "fractional issue number rejected");
        denied(() -> parse(Z8GitHub.View.REPOSITORY, "{\"full_name\":\"https://evil.invalid/a\"}"), "remote repository cannot select another host");
        denied(() -> parse(Z8GitHub.View.CHECKS, "{\"check_runs\":{}}"), "wrong JSON list shape rejected");
        denied(() -> Z8GitHub.repository("../other"), "repository traversal");
        denied(() -> Z8GitHub.repository("octo/../other"), "nested repository traversal");
        denied(() -> Z8GitHub.endpoint(Z8GitHub.View.PULL, "octo/work", "--web", 1), "no issue flag injection");
        denied(() -> Z8GitHub.endpoint(Z8GitHub.View.CHECKS, "octo/work", "../secret", 1), "no arbitrary commit endpoint");
        denied(() -> Z8GitHub.endpoint(Z8GitHub.View.SEARCH, "", "ok", 35), "search bounds");
        denied(() -> Z8GitHub.endpoint(Z8GitHub.View.ISSUES, "octo/work", "", 0), "negative page rejected");
        String query = "--hostname evil.invalid &x=y $(secret)";
        String endpoint = Z8GitHub.endpoint(Z8GitHub.View.SEARCH, "", query, 1);
        check(endpoint.contains("%26x%3Dy") && !endpoint.contains(" ") && !endpoint.contains("&x="), "search endpoint encodes query as data");
        check(Z8GitHub.endpoint(Z8GitHub.View.PULL, "octo/work", "7", 1).equals("repos/octo/work/pulls/7"), "fixed PR endpoint");

        for (String remote : Arrays.asList("https://github.com/octo/work.git", "git@github.com:octo/work.git", "ssh://git@github.com/octo/work.git"))
            check(Z8GitHub.repositoryFromRemote(remote).equals("octo/work"), "GitHub origin forms resolve repository context");
        for (String remote : Arrays.asList("https://github.com.evil.invalid/octo/work.git", "https://token@github.com/octo/work.git", "https://github.com/octo/work.git?token=secret", "git@other.host:octo/work", "file:///secret", "https://github.com/octo/%2e%2e", "https://github.com/octo/work.git\nsecret"))
            check(Z8GitHub.repositoryFromRemote(remote).isEmpty(), "foreign/credential/query/traversal origin never leaks or selects repository");
        check(Z8GitHub.endpoint(Z8GitHub.View.PULL_FILES,"octo/work","7",2).equals("repos/octo/work/pulls/7/files?per_page=30&page=2"), "PR files retain explicit bounded pagination");
        Z8GitHub.Row file = parse(Z8GitHub.View.PULL_FILES, "[{\"filename\":\"src/x.java\",\"status\":\"modified\",\"patch\":\"@@ -1 +1 @@\\n-old\\n+$(not executed)\"}]").rows.get(0);
        check(file.kind == Z8GitHub.Kind.FILE && file.body.contains("$(not executed)"), "patch remains literal display text");
        check(parse(Z8GitHub.View.PULL_FILES,"[{\"filename\":\"image.png\",\"status\":\"added\"}]").rows.get(0).body.contains("patch"), "missing binary/oversize patch is explicitly explained");
        check(parse(Z8GitHub.View.REVIEWS,"[{\"user\":{\"login\":\"octo\"},\"state\":\"CHANGES_REQUESTED\",\"body\":\"fix this\"}]").rows.get(0).detail.contains("CHANGES_REQUESTED"), "review decisions retained independently of checks");

        File source = new File(args[1], "source"); source.mkdir();
        File executable = new File(args[0]);
        File temp = new File(args[1], "tmp"); temp.mkdir();
        List<String> template = Arrays.asList("/private/usr/bin/proot", "--kill-on-exit", "-r", "/guest", "/usr/bin/env", "HOME=/z8/home", "/usr/bin/gh");
        List<String> captured = new ArrayList<>();
        String[] response = { "{\"items\":[" + repo + "]}" };
        int[] code = {0}; int[] decoded = {0}; String[] diagnostic = {"HTTP 401 secret-token-this-must-not-be-displayed"};
        Z8Git.Runner recorder = (argv, cwd, environment, input, timeout, limit) -> {
            captured.clear(); captured.addAll(argv);
            check(cwd.equals(source) && timeout == 30 && limit == Z8GitHub.MAX_OUTPUT && input.length == 0, "bounded read process");
            check(environment.get("HOME").equals("/z8/home") && environment.get("GH_HOST").equals("github.com"), "same guest auth home and fixed GitHub host");
            check(!environment.containsKey("GH_TOKEN") && !environment.containsKey("GITHUB_TOKEN") && !environment.containsKey("GH_CONFIG_DIR")
                && !environment.containsKey("SSH_AUTH_SOCK") && !environment.containsKey("LD_PRELOAD") && !environment.containsKey("XDG_CONFIG_HOME"), "host credentials and config never forwarded");
            return new Z8Git.Result(code[0], bytes(response[0]), bytes(diagnostic[0]));
        };
        Z8GitHub.Decoder decoder = json -> { decoded[0]++; return decode(json); };
        Z8GitHub github = new Z8GitHub(executable, source, executable, temp, template, template.size()-1, recorder, decoder);
        Z8GitHub.Page found = github.load(Z8GitHub.View.SEARCH, "", query, 1);
        check(found.rows.size() == 1 && captured.get(0).equals(executable.getAbsolutePath()), "real guest wrapper dispatches fixture read");
        check(captured.get(1).equals("/private/usr/bin/proot"), "target36 linker prefix survives gh command insertion");
        check(captured.get(captured.indexOf("--method") + 1).equals("GET") && captured.get(captured.size()-2).equals("--"), "explicit GET and endpoint delimiter");
        check(captured.get(captured.size()-1).equals(endpoint) && !captured.contains(query), "query never shell or CLI flags");
        response[0] = "masked-or-secret-auth-output";
        check(github.authStatus().phase == Z8GitHub.AuthPhase.INVALID_RESPONSE, "gh exit zero with unvalidated output is never authenticated");
        for (String invalid : Arrays.asList("{}", "{\"login\":\"octo\"}", "{\"login\":\"octo\",\"id\":0}", "{\"login\":\"octo\",\"id\":1.5}")) {
            response[0] = invalid; check(!github.authStatus().authenticated(), "a complete current-account response is required");
        }
        response[0] = "{\"login\":\"octo\",\"id\":42}";
        check(github.authenticated() && github.authStatus().account.equals("octo"), "authenticated GET user supplies verified account");
        check(!captured.contains("--show-token") && !captured.contains("auth") && captured.get(captured.size()-1).equals("user")
            && captured.get(captured.indexOf("--method")+1).equals("GET"), "never request tokens or rely on gh auth status");
        code[0] = 1; check(!github.authenticated(), "failed auth is not success");
        try { github.load(Z8GitHub.View.REPOSITORY, "octo/work", "", 1); throw new AssertionError("error expected"); }
        catch (IOException error) { check(!error.getMessage().contains("secret-token"), "raw command error never displayed"); }
        diagnostic[0] = "HTTP 403 secret-token"; check(github.authStatus().phase == Z8GitHub.AuthPhase.FORBIDDEN, "permission/rate limit is not login success");
        diagnostic[0] = "dial tcp timeout secret-token"; check(github.authStatus().phase == Z8GitHub.AuthPhase.NETWORK_ERROR, "network uncertainty differs from logout");
        diagnostic[0] = "HTTP 401 secret-token";
        code[0] = 0; response[0] = String.join("", Collections.nCopies(33, "[")) + "0" + String.join("", Collections.nCopies(33, "]"));
        int before = decoded[0]; denied(() -> github.load(Z8GitHub.View.REPOSITORY, "octo/work", "", 1), "nesting rejected before decoder");
        check(decoded[0] == before, "deep payload does not reach JSON decoder");
        response[0] = String.join("", Collections.nCopies(Z8GitHub.MAX_OUTPUT + 1, "x"));
        denied(() -> github.load(Z8GitHub.View.REPOSITORY, "octo/work", "", 1), "response cap");
        denied(() -> new Z8GitHub(executable, source, executable, temp, template, template.size()-2, recorder, decoder), "changed command boundary fails closed");
        Z8GitHub missing = new Z8GitHub(executable, source, new File(args[1], "missing-gh"), temp, template, template.size()-1, recorder, decoder);
        check(!missing.available(), "missing guest gh never uses host fallback");
        denied(missing::authenticated, "unavailable guest fails before command");

        Z8GitHub.emptySource(source);
        Path hidden = new File(source, ".keep").toPath(); Files.write(hidden, bytes("keep"));
        denied(() -> Z8GitHub.emptySource(source), "hidden file prevents clone");
        check(Files.readAllBytes(hidden).length == 4, "empty check preserves existing hidden file"); Files.delete(hidden);
        Path dangling = new File(source, ".dangling").toPath(); Files.createSymbolicLink(dangling, Paths.get("missing-target"));
        denied(() -> Z8GitHub.emptySource(source), "dangling symlink counts as nonempty without following"); Files.delete(dangling);
        Path linkedSource = new File(args[1], "linked-source").toPath(); Files.createSymbolicLink(linkedSource, source.toPath());
        denied(() -> Z8GitHub.emptySource(linkedSource.toFile()), "linked source root rejected");
        List<String> cloneArgs = Z8GitHub.cloneCommand("octo/work");
        check(cloneArgs.equals(Arrays.asList("/usr/bin/git", "-c", "credential.https://github.com.helper=", "-c",
            "credential.https://github.com.helper=!/usr/bin/gh auth git-credential", "clone", "--no-recurse-submodules", "--", "https://github.com/octo/work.git", "/workspace")), "clone uses fixed Git argv and guest gh helper");
        denied(() -> Z8GitHub.cloneCommand("octo/work;touch x"), "clone repository cannot inject command");
        denied(() -> Z8GitHub.cloneCommand("https://evil.invalid/repo"), "clone cannot select arbitrary URL");
        File bin = new File(args[1], "fixture-bin"); bin.mkdir();
        File fakeGh = new File(bin, "gh"); Files.write(fakeGh.toPath(), bytes("fixture only")); fakeGh.setExecutable(true);
        File fakeGit = new File(bin, "git"); Files.write(fakeGit.toPath(), bytes("fixture only")); fakeGit.setExecutable(true);
        CountDownLatch entered = new CountDownLatch(1), release = new CountDownLatch(1);
        AtomicInteger calls = new AtomicInteger();
        Z8Git.Runner cloneRecorder = (argv, cwd, environment, input, timeout, limit) -> {
            int call = calls.incrementAndGet();
            check(environment.get("HOME").equals("/z8/home") && !environment.containsKey("GH_TOKEN") && !environment.containsKey("GIT_CONFIG_GLOBAL"), "clone retains guest home/config without a token override");
            check(limit == Z8GitHub.MAX_OUTPUT && input.length == 0, "clone output remains bounded");
            if (call == 1) {
                check(argv.subList(argv.size()-cloneArgs.size(), argv.size()).equals(cloneArgs) && timeout == 110, "clone command has bounded real worker execution");
                entered.countDown();
                try { if (!release.await(5, TimeUnit.SECONDS)) throw new IOException("test latch timeout"); }
                catch (InterruptedException error) { throw new IOException("interrupted"); }
                Files.createDirectories(new File(source, ".git/objects").toPath());
                Files.write(new File(source, ".git/HEAD").toPath(), bytes("ref: refs/heads/main\n"));
                Files.write(new File(source, ".git/config").toPath(), bytes("[core]\n bare = false\n"));
                return new Z8Git.Result(0, new byte[0], new byte[0]);
            }
            check(call == 2 && timeout == 10 && argv.get(argv.size()-1).equals("--is-inside-work-tree"), "post-clone verifies actual project Git after host metadata checks");
            return new Z8Git.Result(0, bytes("true\n"), new byte[0]);
        };
        Z8GitHub cloneClient = new Z8GitHub(executable, source, fakeGh, temp, template, template.size()-1, cloneRecorder, decoder);
        String id = UUID.randomUUID().toString();
        denied(() -> cloneClient.startClone("invalid-project", "octo/work"), "clone project identity must be valid");
        cloneClient.startClone(id, "octo/work");
        check(Z8GitHub.cloneState(id) != null, "clone acceptance publishes state before returning to confirmation callback");
        check(entered.await(5, TimeUnit.SECONDS), "accepted clone starts shared worker");
        Z8GitHub recreated = new Z8GitHub(executable, source, fakeGh, temp, template, template.size()-1, cloneRecorder, decoder);
        denied(() -> recreated.startClone(id, "octo/work"), "recreated Activity/client cannot duplicate active project clone");
        check(Z8GitHub.cloneState(id).phase == Z8GitHub.ClonePhase.RUNNING, "clone state reattaches across Activity instances");
        release.countDown();
        check(completed(id).phase == Z8GitHub.ClonePhase.SUCCEEDED && calls.get() == 2, "successful exit plus actual repository verification completes clone");
        denied(() -> recreated.startClone(id, "octo/work"), "completed nonempty clone cannot overwrite source");

        File publicSource = new File(args[1], "public-source"); publicSource.mkdir();
        File gitOnlyBin = new File(args[1], "git-only-bin"); gitOnlyBin.mkdir();
        File onlyGit = new File(gitOnlyBin, "git"); Files.write(onlyGit.toPath(), bytes("fixture only")); onlyGit.setExecutable(true);
        AtomicInteger publicCalls = new AtomicInteger();
        List<String> publicArgs = Arrays.asList("/usr/bin/git", "clone", "--no-recurse-submodules", "--", "https://github.com/octo/work.git", "/workspace");
        check(Z8GitHub.cloneCommand("octo/work", false).equals(publicArgs), "Git-only clone never installs a nonexistent gh helper");
        Z8GitHub publicClone = new Z8GitHub(executable, publicSource, new File(gitOnlyBin, "gh"), temp, template, template.size()-1,
            (argv,cwd,environment,input,timeout,limit) -> {
                int call = publicCalls.incrementAndGet();
                check(!argv.contains("/usr/bin/gh") && !argv.contains("auth"), "public clone never invokes gh or auth preflight");
                check(environment.get("GIT_TERMINAL_PROMPT").equals("0"), "missing credentials cannot hang on a terminal prompt");
                if (call == 1) {
                    check(argv.subList(argv.size()-publicArgs.size(),argv.size()).equals(publicArgs), "no-gh clone dispatches exact Git-only argv");
                    Files.createDirectories(new File(publicSource, ".git/objects").toPath());
                    Files.write(new File(publicSource, ".git/HEAD").toPath(), bytes("ref: refs/heads/main\n"));
                    Files.write(new File(publicSource, ".git/config").toPath(), bytes("[core]\n bare = false\n"));
                    return new Z8Git.Result(0,new byte[0],new byte[0]);
                }
                check(call == 2 && timeout == 10, "Git-only clone still verifies actual worktree");
                return new Z8Git.Result(0,bytes("true\n"),new byte[0]);
            },decoder);
        check(!publicClone.available() && publicClone.cloneAvailable(), "Git-only runtime permits clone while gh reads remain unavailable");
        denied(publicClone::authenticated, "Git-only runtime cannot fake GitHub authentication");
        String publicId = UUID.randomUUID().toString(); publicClone.startClone(publicId,"octo/work");
        check(completed(publicId).phase == Z8GitHub.ClonePhase.SUCCEEDED && publicCalls.get() == 2, "no installed gh and no login are required by clone adapter");

        File partial = new File(args[1], "partial"); partial.mkdir();
        Z8Git.Runner partialRunner = (argv, cwd, environment, input, timeout, limit) -> {
            Files.write(new File(partial, "partial.txt").toPath(), bytes("recover me"));
            return new Z8Git.Result(128, new byte[0], bytes("secret-token-do-not-display"));
        };
        Z8GitHub failing = new Z8GitHub(executable, partial, fakeGh, temp, template, template.size()-1, partialRunner, decoder);
        String failedId = UUID.randomUUID().toString(); failing.startClone(failedId, "octo/work");
        Z8GitHub.CloneState failedClone = completed(failedId);
        check(failedClone.phase == Z8GitHub.ClonePhase.FAILED && !failedClone.message.contains("secret-token"), "failure retains an honest sanitized unknown/partial state");
        check(new File(partial, "partial.txt").isFile(), "failed clone preserves partial files without cleanup");
        denied(() -> failing.startClone(failedId, "octo/work"), "partial clone is never automatically overwritten on retry");
        File unverified = new File(args[1], "unverified"); unverified.mkdir();
        Z8GitHub falseSuccess = new Z8GitHub(executable, unverified, fakeGh, temp, template, template.size()-1,
            (argv,cwd,environment,input,timeout,limit) -> new Z8Git.Result(0,new byte[0],new byte[0]), decoder);
        String unverifiedId = UUID.randomUUID().toString(); falseSuccess.startClone(unverifiedId, "octo/work");
        check(completed(unverifiedId).phase == Z8GitHub.ClonePhase.FAILED, "zero exit without real .git is not completed clone");

        Z8GitHub.DraftRequest draft = new Z8GitHub.DraftRequest("octo/work", "octo", "feature/review", "main", "Reviewed \"title\" 한글", "line 1\n$(never execute) \\ literal\t한글");
        Map<?,?> payload = (Map<?,?>) decode(new String(Z8GitHub.draftPayload(draft), StandardCharsets.UTF_8));
        check(payload.get("body").equals(draft.body) && payload.get("title").equals(draft.title) && Boolean.TRUE.equals(payload.get("draft")), "JSON escaping roundtrip exact user content");
        check(Z8GitHub.duplicateEndpoint(draft).contains("head=octo%3Afeature%2Freview&base=main"), "unqualified head resolves to target owner for duplicate check");
        Z8GitHub.DraftRequest fork = new Z8GitHub.DraftRequest("octo/work","octo","contributor:topic/one","main","fork draft","");
        check(Z8GitHub.duplicateEndpoint(fork).contains("head=contributor%3Atopic%2Fone"), "explicit fork owner is preserved");
        denied(() -> new Z8GitHub.DraftRequest("octo/work","octo","topic:extra:bad","main","title",""), "extra head colon rejected");
        denied(() -> new Z8GitHub.DraftRequest("octo/work","octo","../bad","main","title",""), "invalid branch traversal rejected");
        denied(() -> new Z8GitHub.DraftRequest("octo/work","octo","topic.lock","main","title",""), "Git lock branch rejected");
        denied(() -> new Z8GitHub.DraftRequest("octo/work","octo","topic","main","title\nextra",""), "title must be one line");
        denied(() -> new Z8GitHub.DraftRequest("octo/work","octo","topic","main","title",String.join("",Collections.nCopies(5500,"한"))), "body size measured in UTF8 bytes");
        denied(() -> new Z8GitHub.DraftRequest("octo/work","octo","topic","main","title","bad\uD800"), "invalid surrogate rejected before serialization");
        DraftFixture success = new DraftFixture("hold", draft);
        Z8GitHub prClient = new Z8GitHub(executable, unverified, fakeGh, temp, template, template.size()-1,success,decoder);
        Z8GitHub.DraftContext context = prClient.draftContext("octo/work");
        check(context.defaultBranch.equals("main") && context.account.equals("octo") && success.posts.get()==0, "form preflight populates base/account without write");
        String draftId = UUID.randomUUID().toString(); prClient.startDraft(draftId,draft);
        check(Z8GitHub.draftState(draftId) != null, "draft acceptance publishes state before returning to confirmation callback");
        check(success.postEntered.await(5,TimeUnit.SECONDS), "accepted draft reaches one POST after reads");
        denied(() -> prClient.startDraft(draftId,draft), "recreated client cannot duplicate active draft");
        denied(() -> prClient.startClone(draftId,"octo/work"), "clone and draft share project operation lease");
        success.postRelease.countDown();
        Z8GitHub.DraftState created = drafted(draftId);
        check(created.phase==Z8GitHub.DraftPhase.CREATED && created.number==42 && created.url.equals("https://github.com/octo/work/pull/42") && success.posts.get()==1, "created state requires verified matching result");
        for (String invalidUrl : Arrays.asList("https://github.com@evil.invalid/octo/work/pull/42", "https://github.com:443/octo/work/pull/42",
                "https://github.com/octo/other/pull/42", "https://github.com/octo/work/pull/42?token=unexpected", "https://github.com/octo/work/pull/42\n")) {
            Map<String,Object> badResult = (Map<String,Object>) decode(success.response()); badResult.put("html_url",invalidUrl);
            denied(() -> Z8GitHub.verifiedDraft(Z8GitHub.DraftPhase.CREATED,draft,badResult), "result URL authority/path/query/control validation");
        }
        Map<String,Object> notDraft = (Map<String,Object>) decode(success.response()); notDraft.put("draft",false);
        denied(() -> Z8GitHub.verifiedDraft(Z8GitHub.DraftPhase.CREATED,draft,notDraft), "non-draft response cannot count as created draft");
        for (String mode : Arrays.asList("duplicate","read_fail","account_changed","auth_fail","unknown","validation","bad_url")) {
            DraftFixture fixture = new DraftFixture(mode,draft);
            Z8GitHub feature = new Z8GitHub(executable,unverified,fakeGh,temp,template,template.size()-1,fixture,decoder);
            String operation = UUID.randomUUID().toString(); feature.startDraft(operation,draft);
            Z8GitHub.DraftState state = drafted(operation);
            Z8GitHub.DraftPhase expectedPhase = mode.equals("duplicate") ? Z8GitHub.DraftPhase.EXISTS
                : mode.equals("unknown") || mode.equals("bad_url") ? Z8GitHub.DraftPhase.UNKNOWN : Z8GitHub.DraftPhase.FAILED;
            check(state.phase==expectedPhase && !state.message.contains("secret-token"), "draft failure class and sanitized state: " + mode);
            int wantedPosts = Arrays.asList("unknown","validation","bad_url").contains(mode) ? 1 : 0;
            check(fixture.posts.get()==wantedPosts, "failed reads/identity/duplicates never allow blind write: " + mode);
            if (mode.equals("unknown") || mode.equals("bad_url")) {
                check(state.url.isEmpty() && state.number==0, "unknown response cannot advertise result URL/number");
                Z8GitHub.DraftState reattached = Z8GitHub.draftState(operation);
                check(reattached==state && fixture.posts.get()==1, "state reattachment never replays POST");
            }
        }
        Z8GitHub.ReviewRequest review = new Z8GitHub.ReviewRequest("octo/work",7,"octo",commit,"COMMENT","Reviewed 한글\n$(never) \\\" literal");
        denied(() -> new Z8GitHub.ReviewRequest("octo/work",7,"octo",commit,"COMMENT",""), "comment review requires body");
        denied(() -> new Z8GitHub.ReviewRequest("octo/work",7,"octo",commit,"PENDING","text"), "review must be explicit event, never invisible pending");
        denied(() -> new Z8GitHub.ReviewRequest("octo/work",7,"octo","bad-head","APPROVE",""), "review must name inspected commit");
        for (String mode : Arrays.asList("hold","head","closed","account","unknown","reject","wrong_target")) {
            ReviewFixture fixture = new ReviewFixture(mode,review);
            Z8GitHub reviewClient = new Z8GitHub(executable,unverified,fakeGh,temp,template,template.size()-1,fixture,decoder);
            String operation = UUID.randomUUID().toString(); reviewClient.startReview(operation,review);
            check(Z8GitHub.reviewState(operation) != null, "accepted review immediately publishes operation state");
            if (mode.equals("hold")) {
                check(fixture.entered.await(5,TimeUnit.SECONDS), "review reaches one POST after all reads");
                denied(() -> reviewClient.startReview(operation,review), "rotation cannot duplicate active review");
                denied(() -> reviewClient.startDraft(operation,draft), "review shares project lease with other mutations");
                fixture.release.countDown();
            }
            Z8GitHub.ReviewState state = reviewed(operation);
            check(state.succeeded == mode.equals("hold") && !state.message.contains("secret-token"), "only matching verified response succeeds: " + mode);
            check(state.uncertain == Arrays.asList("unknown","wrong_target").contains(mode), "unknown write outcome stays uncertain: " + mode);
            check(fixture.posts == (Arrays.asList("head","closed","account").contains(mode) ? 0 : 1), "changed account/head/closed PR blocked before POST: " + mode);
            Z8GitHub.reviewState(operation); check(fixture.posts <= 1, "reattach never retransmits review");
        }
        System.out.println("PASS: GitHub read contracts (" + checks + " checks)");
    }
}

class Z8RuntimeLauncher { static final Object EXECUTION_LOCK = new Object(); }
'''


if __name__ == "__main__":
    unittest.main()
