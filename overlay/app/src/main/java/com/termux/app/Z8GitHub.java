package com.termux.app;

import java.io.File;
import java.io.IOException;
import java.net.URLEncoder;
import java.net.URI;
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.LinkedHashMap;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** GitHub reads, confirmed clones and draft PRs. All I/O belongs on a worker. */
public final class Z8GitHub {
    public static final int PAGE_SIZE = 30;
    public static final int MAX_OUTPUT = 1024 * 1024;
    public enum View { REPOSITORY, SEARCH, ISSUES, ISSUE, PULLS, PULL, PULL_FILES, REVIEWS, CHECKS, STATUSES, ACTIONS }
    public enum Kind { REPOSITORY, ISSUE, PULL, FILE, REVIEW, CHECK, RUN }
    interface Decoder { Object decode(String json) throws IOException; }
    private static final Map<String, CloneState> CLONES = new LinkedHashMap<>();
    private static final Map<String, DraftState> DRAFTS = new LinkedHashMap<>();
    private static final Map<String, ReviewState> REVIEWS = new LinkedHashMap<>();
    private static final ExecutorService OPERATION_WORKER = Executors.newFixedThreadPool(2, task -> {
        Thread worker = new Thread(task, "z8-github-operation"); worker.setDaemon(true); return worker;
    });
    public enum ClonePhase { RUNNING, SUCCEEDED, FAILED }
    public static final class CloneState {
        public final ClonePhase phase;
        public final String repository, message;
        public final long startedAt;
        CloneState(ClonePhase phase, String repository, String message, long startedAt) {
            this.phase = phase; this.repository = repository; this.message = message; this.startedAt = startedAt;
        }
    }

    public enum DraftPhase { CHECKING, CREATING, CREATED, EXISTS, FAILED, UNKNOWN }
    public static final class DraftState {
        public final DraftPhase phase;
        public final String repository, head, base, message, url;
        public final long number;
        DraftState(DraftPhase phase, DraftRequest request, String message, long number, String url) {
            this.phase = phase; this.repository = request.repository; this.head = request.head;
            this.base = request.base; this.message = message; this.number = number; this.url = url;
        }
        public boolean running() { return phase == DraftPhase.CHECKING || phase == DraftPhase.CREATING; }
    }
    public static final class DraftContext {
        public final String repository, account, defaultBranch;
        DraftContext(String repository, String account, String defaultBranch) {
            this.repository = repository; this.account = account; this.defaultBranch = defaultBranch;
        }
    }
    public static final class DraftRequest {
        public final String repository, account, head, base, title, body;
        public DraftRequest(String repository, String account, String head, String base, String title, String body) throws IOException {
            this.repository = repository(repository); this.account = owner(account);
            if (head == null) throw new IOException("head 브랜치를 입력해 주세요.");
            int colon = head.indexOf(':');
            this.head = colon < 0 ? branch(head) : owner(head.substring(0, colon)) + ":" + branch(head.substring(colon + 1));
            this.base = branch(base);
            if (title == null || title.trim().isEmpty() || title.length() > 256 || hasControls(title)) throw new IOException("PR 제목을 줄바꿈 없이 1~256자로 입력해 주세요.");
            this.title = title.trim(); checkedUtf8(this.title, 1024);
            if (body == null) body = "";
            checkedUtf8(body, 16384);
            for (int i = 0; i < body.length(); i++) {
                char c = body.charAt(i);
                if (Character.isISOControl(c) && c != '\n' && c != '\r' && c != '\t') throw new IOException("PR 본문에 지원하지 않는 제어 문자가 있습니다.");
            }
            this.body = body;
        }
        String qualifiedHead() { return head.indexOf(':') >= 0 ? head : repository.substring(0, repository.indexOf('/')) + ":" + head; }
    }

    public static final class ReviewRequest {
        public final String repository, account, commit, event, body;
        public final long number;
        public ReviewRequest(String repository, long number, String account, String commit, String event, String body) throws IOException {
            this.repository = repository(repository); this.number = number(Long.toString(number));
            this.account = owner(account); this.commit = sha(commit);
            if (!Arrays.asList("COMMENT", "APPROVE", "REQUEST_CHANGES").contains(event)) throw new IOException("리뷰 유형을 선택해 주세요.");
            if (body == null) body = "";
            if (!event.equals("APPROVE") && body.trim().isEmpty()) throw new IOException("리뷰 내용을 입력해 주세요.");
            checkedUtf8(body, 16384);
            for (int i = 0; i < body.length(); i++) if (Character.isISOControl(body.charAt(i)) && "\n\r\t".indexOf(body.charAt(i)) < 0)
                throw new IOException("리뷰 본문에 지원하지 않는 제어 문자가 있습니다.");
            this.event = event; this.body = body;
        }
    }
    public static final class ReviewState {
        public final String repository, message;
        public final long number;
        public final boolean running, succeeded, uncertain;
        ReviewState(ReviewRequest request, String message, boolean running, boolean succeeded, boolean uncertain) {
            this.repository = request.repository; this.number = request.number; this.message = message;
            this.running = running; this.succeeded = succeeded; this.uncertain = uncertain;
        }
    }

    /** Accepted only from an explicit preview confirmation. Never retries POST. */
    public ReviewState startReview(String projectId, ReviewRequest request) throws IOException {
        projectId(projectId);
        if (request == null || !available()) throw new IOException("리뷰 요청과 GitHub 도구를 확인해 주세요.");
        ReviewState accepted = new ReviewState(request, "계정과 PR HEAD를 다시 확인한 뒤 리뷰를 제출합니다…", true, false, false);
        synchronized (Z8GitHub.class) {
            availableOperation(projectId);
            if (REVIEWS.size() >= 64) REVIEWS.entrySet().removeIf(entry -> !entry.getValue().running);
            REVIEWS.put(projectId, accepted);
        }
        OPERATION_WORKER.execute(() -> {
            boolean attempted = false; ReviewState finished;
            try {
                AuthStatus auth = authStatus();
                if (!auth.authenticated() || !request.account.equalsIgnoreCase(auth.account)) throw new IOException("계정이 달라졌습니다.");
                Map<String, Object> pull = object(read("repos/" + request.repository + "/pulls/" + request.number));
                Row fresh = work(pull, true, request.repository);
                if (fresh.number != request.number || !request.commit.equalsIgnoreCase(fresh.sha) || !"open".equals(required(pull, "state", 20)))
                    throw new IOException("PR HEAD 또는 상태가 변경되었습니다.");
                byte[] payload = reviewPayload(request);
                attempted = true;
                Z8Git.Result response = execute(apiCommand("POST", "repos/" + request.repository + "/pulls/" + request.number + "/reviews", true), 30, payload);
                if (response.code != 0) {
                    String diagnostic = new String(response.stderr, StandardCharsets.UTF_8);
                    if (diagnostic.matches("(?s).*HTTP (400|401|403|404|409|422)(?:[^0-9].*)?"))
                        finished = new ReviewState(request, "GitHub가 리뷰를 거절했습니다. 권한과 PR 상태를 확인해 주세요. 작성한 초안은 남아 있습니다.", false, false, false);
                    else throw new IOException("리뷰 응답을 확인하지 못했습니다.");
                } else {
                    Map<String, Object> review = object(decode(response.stdout));
                    String state = request.event.equals("APPROVE") ? "APPROVED" : request.event.equals("REQUEST_CHANGES") ? "CHANGES_REQUESTED" : "COMMENTED";
                    Object id = review.get("id");
                    if (!(id instanceof Number) || ((Number) id).longValue() <= 0 || ((Number) id).doubleValue() != ((Number) id).longValue()
                            || !state.equals(required(review, "state", 100)) || !request.commit.equalsIgnoreCase(required(review, "commit_id", 64))
                            || !request.account.equalsIgnoreCase(required(object(review.get("user")), "login", 100))
                            || !("https://api.github.com/repos/" + request.repository + "/pulls/" + request.number).equalsIgnoreCase(required(review, "pull_request_url", 600)))
                        throw new IOException("리뷰 결과가 요청과 일치하지 않습니다.");
                    finished = new ReviewState(request, "검토한 HEAD에 리뷰를 제출했습니다.", false, true, false);
                }
            } catch (Exception failure) {
                finished = new ReviewState(request, attempted
                    ? "리뷰 제출 결과가 불확실합니다. 자동 재전송하지 않습니다. 리뷰 목록에서 결과를 확인해 주세요. 초안은 보관됩니다."
                    : "계정 또는 PR HEAD·상태를 확인하지 못해 리뷰를 보내지 않았습니다. PR을 새로고침해 주세요. 초안은 보관됩니다.", false, false, attempted);
            }
            synchronized (Z8GitHub.class) { REVIEWS.put(projectId, finished); }
        });
        return accepted;
    }

    static byte[] reviewPayload(ReviewRequest request) throws IOException {
        return checkedUtf8("{\"commit_id\":" + quote(request.commit) + ",\"event\":" + quote(request.event) + ",\"body\":" + quote(request.body) + "}", 128 * 1024);
    }

    public static final class Row {
        public final Kind kind;
        public final long number;
        public final String title, detail, body, repository, sha;
        Row(Kind kind, long number, String title, String detail, String body, String repository, String sha) {
            this.kind = kind; this.number = number; this.title = title; this.detail = detail;
            this.body = body; this.repository = repository; this.sha = sha;
        }
    }
    public static final class Page {
        public final List<Row> rows;
        public final String summary;
        public final boolean mayHaveNext;
        Page(List<Row> rows, String summary, boolean next) {
            this.rows = Collections.unmodifiableList(rows); this.summary = summary; this.mayHaveNext = next;
        }
    }

    private final File proot, source, gh, temp;
    private final List<String> prefix;
    private final Z8Git.Runner runner;
    private final Decoder decoder;

    Z8GitHub(File proot, File source, File gh, File temp, List<String> launchArguments,
            int commandOffset, Z8Git.Runner runner, Decoder decoder) throws IOException {
        if (commandOffset < 1 || commandOffset != launchArguments.size() - 1
                || !"/usr/bin/gh".equals(launchArguments.get(commandOffset)))
            throw new IOException("프로젝트 GitHub 실행 경로를 확인할 수 없습니다.");
        List<String> before = launchArguments.subList(0, commandOffset);
        if (!before.contains("/usr/bin/env") || !before.contains("HOME=/z8/home")
                || !before.contains("--kill-on-exit") || !before.contains("-r"))
            throw new IOException("프로젝트 Linux 실행 설정을 확인할 수 없습니다.");
        this.proot = proot; this.source = source; this.gh = gh; this.temp = temp;
        this.prefix = new ArrayList<>(before); this.runner = runner; this.decoder = decoder;
    }

    public boolean available() { return proot.isFile() && proot.canExecute() && gh.isFile() && gh.canExecute(); }
    public boolean cloneAvailable() {
        File git = new File(gh.getParentFile(), "git");
        return proot.isFile() && proot.canExecute() && git.isFile() && git.canExecute();
    }

    /** In-memory lease/state survives Activity destruction without retaining an Activity. */
    public static synchronized CloneState cloneState(String projectId) { return CLONES.get(projectId); }
    public static synchronized DraftState draftState(String projectId) { return DRAFTS.get(projectId); }
    public static synchronized ReviewState reviewState(String projectId) { return REVIEWS.get(projectId); }

    private static void projectId(String projectId) throws IOException {
        try { if (projectId == null || !UUID.fromString(projectId).toString().equals(projectId)) throw new IllegalArgumentException(); }
        catch (IllegalArgumentException invalid) { throw new IOException("프로젝트 ID를 확인해 주세요."); }
    }
    private static void availableOperation(String projectId) throws IOException {
        CloneState clone = CLONES.get(projectId); DraftState draft = DRAFTS.get(projectId); ReviewState review = REVIEWS.get(projectId);
        if ((clone != null && clone.phase == ClonePhase.RUNNING) || (draft != null && draft.running()) || (review != null && review.running))
            throw new IOException("이 프로젝트의 GitHub 작업이 이미 진행 중입니다.");
        int active = 0;
        for (CloneState state : CLONES.values()) if (state.phase == ClonePhase.RUNNING) active++;
        for (DraftState state : DRAFTS.values()) if (state.running()) active++;
        for (ReviewState state : REVIEWS.values()) if (state.running) active++;
        if (active >= 2) throw new IOException("다른 프로젝트의 GitHub 작업이 진행 중입니다. 완료된 뒤 다시 시도해 주세요.");
    }

    public void checkCloneReady(String selectedRepository) throws IOException {
        repository(selectedRepository);
        if (!cloneAvailable()) throw new IOException("프로젝트 Linux 환경에 Git과 z8 전용 PRoot가 필요합니다.");
        emptySource(source);
    }

    /** Call only after the UI confirms this exact repository/project pair. */
    public CloneState startClone(String projectId, String selectedRepository) throws IOException {
        projectId(projectId);
        checkCloneReady(selectedRepository);
        final CloneState accepted;
        synchronized (Z8GitHub.class) {
            availableOperation(projectId);
            if (CLONES.size() >= 64) CLONES.entrySet().removeIf(entry -> entry.getValue().phase != ClonePhase.RUNNING);
            accepted = new CloneState(ClonePhase.RUNNING, selectedRepository, "프로젝트에 clone 중… 최대 약 2분", System.currentTimeMillis());
            CLONES.put(projectId, accepted);
        }
        // This closure contains immutable paths/runner and no Activity or Context.
        OPERATION_WORKER.execute(() -> {
            CloneState completed;
            try {
                cloneIntoEmptySource(selectedRepository);
                completed = new CloneState(ClonePhase.SUCCEEDED, selectedRepository, "clone을 완료했고 프로젝트의 Git 저장소를 확인했습니다.", accepted.startedAt);
            } catch (Exception failure) {
                completed = new CloneState(ClonePhase.FAILED, selectedRepository,
                    "clone을 완료하지 못했거나 완료 상태를 확인하지 못했습니다. 일부 파일이 남아 있을 수 있습니다. 파일·Git 화면 또는 터미널에서 확인해 주세요. 자동 삭제나 재시도는 하지 않습니다.", accepted.startedAt);
            }
            synchronized (Z8GitHub.class) { CLONES.put(projectId, completed); }
        });
        return accepted;
    }

    /** Only read requests; token scopes and final write permission remain server-enforced. */
    public DraftContext draftContext(String selectedRepository) throws IOException {
        String selected = repository(selectedRepository);
        AuthStatus authentication = authStatus();
        if (!authentication.authenticated()) throw new IOException(authentication.message);
        String login = authentication.account;
        Map<String, Object> repo = object(read("repos/" + selected));
        String actual = repository(required(repo, "full_name", 160));
        if (!actual.equalsIgnoreCase(selected)) throw new IOException("저장소 이름이 변경되었습니다. 현재 저장소 이름을 확인해 주세요.");
        if (Boolean.TRUE.equals(repo.get("archived")) || Boolean.TRUE.equals(repo.get("disabled"))) throw new IOException("보관되었거나 비활성화된 저장소에는 PR을 만들 수 없습니다.");
        Map<String, Object> permissions = object(repo.get("permissions"));
        if (!Boolean.TRUE.equals(permissions.get("pull"))) throw new IOException("이 계정의 저장소 접근 권한을 확인하지 못했습니다.");
        return new DraftContext(actual, login, branch(required(repo, "default_branch", 255)));
    }

    /** User confirmation is the sole entry to this write path. Never invoke from resume. */
    public DraftState startDraft(String projectId, DraftRequest request) throws IOException {
        projectId(projectId);
        if (request == null || !available()) throw new IOException("PR 요청과 프로젝트 GitHub 도구를 확인해 주세요.");
        DraftState accepted = new DraftState(DraftPhase.CHECKING, request, "계정·저장소·기존 PR을 다시 확인하고 있습니다…", 0, "");
        synchronized (Z8GitHub.class) {
            availableOperation(projectId);
            if (DRAFTS.size() >= 64) DRAFTS.entrySet().removeIf(entry -> !entry.getValue().running());
            DRAFTS.put(projectId, accepted);
        }
        OPERATION_WORKER.execute(() -> createDraft(projectId, request));
        return accepted;
    }

    private void createDraft(String projectId, DraftRequest request) {
        boolean attempted = false;
        DraftState finished;
        try {
            DraftContext fresh = draftContext(request.repository);
            if (!fresh.account.equalsIgnoreCase(request.account)) throw new IOException("GitHub 계정이 작성 화면과 달라졌습니다. 계정을 확인한 뒤 새로 작성해 주세요.");
            List<?> existing = array(read(duplicateEndpoint(request)));
            if (existing.size() > PAGE_SIZE) throw new IOException("기존 PR 조회 결과가 너무 큽니다.");
            if (!existing.isEmpty()) {
                // The server query is exact. Unexpected rows fail closed, never permit a blind POST.
                DraftState found = verifiedDraft(DraftPhase.EXISTS, request, object(existing.get(0)));
                synchronized (Z8GitHub.class) { DRAFTS.put(projectId, found); }
                return;
            }
            synchronized (Z8GitHub.class) {
                DRAFTS.put(projectId, new DraftState(DraftPhase.CREATING, request, "검토한 내용으로 Draft PR 생성 요청 중…", 0, ""));
            }
            List<String> command = apiCommand("POST", "repos/" + request.repository + "/pulls", true);
            attempted = true;
            Z8Git.Result response = execute(command, 30, draftPayload(request));
            if (response.code != 0) {
                String diagnostic = new String(response.stderr, StandardCharsets.UTF_8);
                if (diagnostic.matches("(?s).*HTTP (400|401|403|404|409|422)(?:[^0-9].*)?")) {
                    finished = new DraftState(DraftPhase.FAILED, request, "GitHub가 생성 요청을 거절했습니다. 권한·브랜치·변경사항 또는 이미 열린 PR을 확인해 주세요. 생성 완료로 처리하지 않았습니다.", 0, "");
                } else finished = unknownDraft(request);
            } else finished = verifiedDraft(DraftPhase.CREATED, request, object(decode(response.stdout)));
        } catch (Exception failed) {
            finished = attempted ? unknownDraft(request)
                : new DraftState(DraftPhase.FAILED, request, "사전 확인에 실패해 생성 요청을 보내지 않았습니다. 로그인·저장소 접근·계정 변경·기존 PR 조회를 확인해 주세요.", 0, "");
        }
        synchronized (Z8GitHub.class) { DRAFTS.put(projectId, finished); }
    }

    private static DraftState unknownDraft(DraftRequest request) {
        return new DraftState(DraftPhase.UNKNOWN, request, "응답이 불확실해 생성 여부를 확인하지 못했습니다. 자동으로 다시 보내지 않습니다. 먼저 열린 PR에서 같은 head/base가 생성되었는지 확인해 주세요.", 0, "");
    }

    private Object read(String endpoint) throws IOException {
        Z8Git.Result response = execute(apiCommand("GET", endpoint, false), 30);
        if (response.code != 0) throw new IOException(failure(response));
        return decode(response.stdout);
    }

    private static List<String> apiCommand(String method, String endpoint, boolean input) {
        List<String> command = new ArrayList<>(Arrays.asList("/usr/bin/gh", "api", "--hostname", "github.com", "--method", method,
            "--header", "Accept: application/vnd.github+json", "--header", "X-GitHub-Api-Version: 2022-11-28"));
        if (input) command.addAll(Arrays.asList("--header", "Content-Type: application/json", "--input", "-"));
        command.add("--"); command.add(endpoint); return command;
    }

    static String duplicateEndpoint(DraftRequest request) throws IOException {
        return "repos/" + request.repository + "/pulls?state=open&head=" + query(request.qualifiedHead())
            + "&base=" + query(request.base) + "&per_page=" + PAGE_SIZE + "&page=1";
    }
    private static String query(String value) throws IOException { return URLEncoder.encode(value, "UTF-8").replace("+", "%20"); }

    static DraftState verifiedDraft(DraftPhase phase, DraftRequest request, Map<String, Object> response) throws IOException {
        Object rawNumber = response.get("number");
        if (!(rawNumber instanceof Number)) throw new IOException("PR 결과 번호를 확인하지 못했습니다.");
        long number = ((Number) rawNumber).longValue();
        if (number < 1 || number > 9999999999L || ((Number) rawNumber).doubleValue() != number) throw new IOException("PR 결과 번호가 올바르지 않습니다.");
        Map<String, Object> base = object(response.get("base")), head = object(response.get("head"));
        String actualRepository = repository(required(object(base.get("repo")), "full_name", 160));
        if (!actualRepository.equalsIgnoreCase(request.repository) || !request.base.equals(required(base, "ref", 255))
                || !sameHead(request.qualifiedHead(), required(head, "label", 300)) || !"open".equals(required(response, "state", 20)))
            throw new IOException("PR 응답이 요청한 저장소·브랜치와 일치하지 않습니다.");
        if (phase == DraftPhase.CREATED && !Boolean.TRUE.equals(response.get("draft"))) throw new IOException("Draft PR 상태를 확인하지 못했습니다.");
        Object rawUrl = response.get("html_url");
        if (!(rawUrl instanceof String) || ((String) rawUrl).length() > 600 || hasControls((String) rawUrl))
            throw new IOException("PR 결과 URL을 확인하지 못했습니다.");
        String url = (String) rawUrl;
        try {
            URI parsed = new URI(url);
            if (!"https".equals(parsed.getScheme()) || !"github.com".equalsIgnoreCase(parsed.getHost()) || parsed.getPort() != -1
                    || parsed.getUserInfo() != null || parsed.getRawQuery() != null || parsed.getRawFragment() != null
                    || !("/" + request.repository + "/pull/" + number).equalsIgnoreCase(parsed.getRawPath()))
                throw new IOException("PR 결과 URL을 확인하지 못했습니다.");
        } catch (java.net.URISyntaxException invalid) { throw new IOException("PR 결과 URL 형식이 올바르지 않습니다."); }
        return new DraftState(phase, request, phase == DraftPhase.CREATED ? "Draft PR을 생성했습니다." : "같은 head/base의 열린 PR이 이미 있어 새로 생성하지 않았습니다.", number, url);
    }
    private static boolean sameHead(String expected, String actual) {
        int left = expected.indexOf(':'), right = actual.indexOf(':');
        return left > 0 && right > 0 && expected.substring(0, left).equalsIgnoreCase(actual.substring(0, right))
            && expected.substring(left + 1).equals(actual.substring(right + 1));
    }

    static byte[] draftPayload(DraftRequest request) throws IOException {
        String json = "{\"title\":" + quote(request.title) + ",\"body\":" + quote(request.body)
            + ",\"head\":" + quote(request.head) + ",\"base\":" + quote(request.base) + ",\"draft\":true}";
        return checkedUtf8(json, 128 * 1024);
    }
    private static String quote(String value) {
        StringBuilder json = new StringBuilder("\"");
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            if (c == '"' || c == '\\') json.append('\\').append(c);
            else if (c < 0x20) json.append(String.format(java.util.Locale.ROOT, "\\u%04x", (int) c));
            else json.append(c);
        }
        return json.append('"').toString();
    }
    private static byte[] checkedUtf8(String value, int limit) throws IOException {
        try {
            java.nio.ByteBuffer bytes = StandardCharsets.UTF_8.newEncoder().onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT).encode(java.nio.CharBuffer.wrap(value));
            if (bytes.remaining() > limit) throw new IOException("입력 내용의 UTF-8 크기 제한을 초과했습니다. PR 본문은 최대 16 KiB입니다.");
            byte[] encoded = new byte[bytes.remaining()]; bytes.get(encoded); return encoded;
        } catch (java.nio.charset.CharacterCodingException invalid) { throw new IOException("입력 내용의 문자 인코딩을 확인해 주세요."); }
    }
    private static String owner(String value) throws IOException {
        if (value == null || !value.matches("[A-Za-z0-9][A-Za-z0-9-]{0,38}")) throw new IOException("GitHub 계정 또는 head 소유자 이름을 확인해 주세요.");
        return value;
    }
    private static String branch(String value) throws IOException {
        if (value == null || value.isEmpty() || value.length() > 255 || value.startsWith("-") || value.equals("@")
                || value.contains("..") || value.contains("@{") || value.endsWith(".") || value.matches(".*[~^:?*\\[\\\\].*"))
            throw new IOException("Git 브랜치 이름을 확인해 주세요.");
        checkedUtf8(value, 255);
        for (int i = 0; i < value.length(); i++) if (Character.isWhitespace(value.charAt(i)) || Character.isISOControl(value.charAt(i))) throw new IOException("브랜치 이름에 공백이나 제어 문자를 넣을 수 없습니다.");
        for (String part : value.split("/", -1)) if (part.isEmpty() || part.startsWith(".") || part.endsWith(".lock")) throw new IOException("Git 브랜치 경로를 확인해 주세요.");
        return value;
    }

    static void emptySource(File source) throws IOException {
        File checked = Z8Files.directory(source, "");
        try (DirectoryStream<Path> entries = Files.newDirectoryStream(checked.toPath())) {
            if (entries.iterator().hasNext()) throw new IOException("이 프로젝트의 소스 폴더가 비어 있지 않습니다. 숨김 파일을 포함해 파일이 없는 새 프로젝트에서 clone해 주세요.");
        }
    }

    static List<String> cloneCommand(String selectedRepository) throws IOException {
        return cloneCommand(selectedRepository, true);
    }
    static List<String> cloneCommand(String selectedRepository, boolean useGh) throws IOException {
        String selected = repository(selectedRepository);
        List<String> command = new ArrayList<>(); command.add("/usr/bin/git");
        if (useGh) command.addAll(Arrays.asList("-c", "credential.https://github.com.helper=",
            "-c", "credential.https://github.com.helper=!/usr/bin/gh auth git-credential"));
        command.addAll(Arrays.asList("clone", "--no-recurse-submodules", "--", "https://github.com/" + selected + ".git", "/workspace"));
        return command;
    }

    private void cloneIntoEmptySource(String selectedRepository) throws IOException {
        checkCloneReady(selectedRepository); // Recheck after confirmation and acquiring the lease.
        Z8Git.Result cloned = execute(cloneCommand(selectedRepository, available()), 110);
        if (cloned.code != 0) throw new IOException("clone 종료 상태를 확인해 주세요.");
        Z8Files.directory(source, ".git");
        if (!Files.isRegularFile(new File(source, ".git/HEAD").toPath(), LinkOption.NOFOLLOW_LINKS)
                || !Files.isRegularFile(new File(source, ".git/config").toPath(), LinkOption.NOFOLLOW_LINKS))
            throw new IOException("clone 이후 Git 메타데이터를 확인할 수 없습니다.");
        Z8Files.directory(source, ".git/objects");
        Z8Git.Result verified = execute(Arrays.asList("/usr/bin/git", "-C", "/workspace", "rev-parse", "--is-inside-work-tree"), 10);
        if (verified.code != 0 || !"true".equals(verified.output().trim())) throw new IOException("프로젝트 Git 저장소 확인에 실패했습니다.");
    }

    public enum AuthPhase { AUTHENTICATED, LOGIN_REQUIRED, NETWORK_ERROR, FORBIDDEN, INVALID_RESPONSE }
    public static final class AuthStatus {
        public final AuthPhase phase;
        public final String account, message;
        AuthStatus(AuthPhase phase, String account, String message) { this.phase = phase; this.account = account; this.message = message; }
        public boolean authenticated() { return phase == AuthPhase.AUTHENTICATED; }
    }

    /** gh 2.45 auth status can exit 0 with GH_HOST and no account. Only GET /user is proof. */
    public AuthStatus authStatus() throws IOException {
        if (!available()) throw new IOException("프로젝트 Linux 환경에 gh가 필요합니다.");
        final Z8Git.Result response;
        try { response = execute(apiCommand("GET", "user", false), 30); }
        catch (IOException unavailable) { return new AuthStatus(AuthPhase.NETWORK_ERROR, "", "인증을 확인하지 못했습니다. 네트워크·시간 제한·Linux 환경을 확인한 뒤 다시 시도해 주세요."); }
        if (response.code != 0) {
            String diagnostic = new String(response.stderr, StandardCharsets.UTF_8);
            AuthPhase phase = diagnostic.contains("HTTP 401") || diagnostic.contains("gh auth login") || diagnostic.contains("not logged")
                ? AuthPhase.LOGIN_REQUIRED : diagnostic.contains("HTTP 403") || diagnostic.contains("HTTP 429") ? AuthPhase.FORBIDDEN : AuthPhase.NETWORK_ERROR;
            return new AuthStatus(phase, "", failure(response));
        }
        try {
            Map<String, Object> user = object(decode(response.stdout));
            String account = owner(required(user, "login", 100));
            Object id = user.get("id");
            if (!(id instanceof Number) || ((Number) id).longValue() <= 0 || ((Number) id).doubleValue() != ((Number) id).longValue())
                throw new IOException("계정 응답을 확인하지 못했습니다.");
            return new AuthStatus(AuthPhase.AUTHENTICATED, account, "@" + account + " · github.com 인증 확인됨");
        } catch (IOException | RuntimeException invalid) {
            return new AuthStatus(AuthPhase.INVALID_RESPONSE, "", "인증 응답을 확인하지 못했습니다. 성공으로 처리하지 않았습니다. 다시 확인해 주세요.");
        }
    }

    public boolean authenticated() throws IOException {
        AuthStatus status = authStatus();
        if (status.phase == AuthPhase.LOGIN_REQUIRED) return false;
        if (!status.authenticated()) throw new IOException(status.message);
        return true;
    }

    /** Read origin in the same project guest; remote URL credentials are never shown. */
    public String projectRepository() throws IOException {
        if (!cloneAvailable()) return "";
        Z8Git.Result origin = execute(Arrays.asList("/usr/bin/git", "-C", "/workspace", "remote", "get-url", "origin"), 10);
        if (origin.code != 0) return "";
        return repositoryFromRemote(origin.output().trim());
    }

    static String repositoryFromRemote(String remote) throws IOException {
        if (remote == null || remote.isEmpty()) return "";
        String path;
        if (remote.startsWith("git@github.com:")) path = remote.substring("git@github.com:".length());
        else {
            try {
                URI url = new URI(remote);
                if (!"github.com".equalsIgnoreCase(url.getHost()) || url.getRawQuery() != null || url.getRawFragment() != null
                        || (!"https".equals(url.getScheme()) && !"ssh".equals(url.getScheme()))
                        || (url.getPort() != -1 && !("ssh".equals(url.getScheme()) && url.getPort() == 22))
                        || (url.getRawUserInfo() != null && !("ssh".equals(url.getScheme()) && "git".equals(url.getRawUserInfo())))) return "";
                path = url.getRawPath(); if (path == null || !path.startsWith("/")) return ""; path = path.substring(1);
            } catch (java.net.URISyntaxException invalid) { return ""; }
        }
        if (path.endsWith(".git")) path = path.substring(0, path.length() - 4);
        try { return repository(path); } catch (IOException invalid) { return ""; }
    }

    public Page load(View view, String repository, String argument, int page) throws IOException {
        String endpoint = endpoint(view, repository, argument, page);
        Z8Git.Result result = run(Arrays.asList("api", "--hostname", "github.com", "--method", "GET",
            "--header", "Accept: application/vnd.github+json", "--header", "X-GitHub-Api-Version: 2022-11-28", "--", endpoint));
        if (result.code != 0) throw new IOException(failure(result));
        return parse(view, repository, decode(result.stdout), page);
    }

    private Z8Git.Result run(List<String> command) throws IOException {
        if (!available()) throw new IOException("프로젝트 Linux 환경에 gh와 z8 전용 PRoot가 필요합니다.");
        Z8Files.directory(source, "");
        List<String> guest = new ArrayList<>(); guest.add("/usr/bin/gh"); guest.addAll(command);
        try { return execute(guest, 30); }
        catch (IOException failed) {
            throw new IOException("GitHub CLI 실행을 완료하지 못했습니다. 30초 시간 제한·응답 크기·프로젝트 환경을 확인하고 다시 시도해 주세요.");
        }
    }

    private Z8Git.Result execute(List<String> guestCommand, int timeout) throws IOException {
        return execute(guestCommand, timeout, new byte[0]);
    }
    private Z8Git.Result execute(List<String> guestCommand, int timeout, byte[] input) throws IOException {
        boolean git = !guestCommand.isEmpty() && "/usr/bin/git".equals(guestCommand.get(0));
        if (git ? !cloneAvailable() : !available()) throw new IOException("프로젝트 GitHub 도구가 준비되지 않았습니다.");
        Z8Files.directory(source, "");
        List<String> argv = new ArrayList<>(); argv.add(proot.getAbsolutePath()); argv.addAll(prefix);
        argv.addAll(guestCommand);
        // Start from a narrow environment, never the Android process's tokens,
        // GH_CONFIG_DIR, proxies, SSH agent, GIT_* redirects or XDG overrides.
        Map<String, String> env = environment(temp);
        return runner.run(argv, source, env, input, timeout, MAX_OUTPUT);
    }

    static Map<String, String> environment(File temp) {
        Map<String, String> env = new HashMap<>();
        env.put("HOME", "/z8/home"); env.put("USER", "root"); env.put("LOGNAME", "root");
        env.put("PATH", "/z8/home/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin");
        env.put("TMPDIR", "/tmp"); env.put("PROOT_TMP_DIR", temp.getAbsolutePath());
        env.put("LANG", "C.UTF-8"); env.put("TERM", "dumb"); env.put("NO_COLOR", "1");
        env.put("GH_HOST", "github.com"); env.put("GH_PROMPT_DISABLED", "1");
        env.put("GH_PAGER", "cat"); env.put("GIT_TERMINAL_PROMPT", "0");
        env.put("GH_NO_UPDATE_NOTIFIER", "1"); env.put("GH_NO_EXTENSION_UPDATE_NOTIFIER", "1");
        return env;
    }

    static String repository(String value) throws IOException {
        if (value == null || !value.matches("[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}"))
            throw new IOException("저장소를 owner/repository 형식으로 입력해 주세요.");
        String name = value.substring(value.indexOf('/') + 1);
        if (name.equals(".") || name.equals("..")) throw new IOException("저장소 이름을 확인해 주세요.");
        return value;
    }

    static String endpoint(View view, String repo, String argument, int page) throws IOException {
        if (page < 1 || page > 100) throw new IOException("지원하는 조회 페이지 범위를 벗어났습니다.");
        String paging = "per_page=" + PAGE_SIZE + "&page=" + page;
        if (view == View.SEARCH) {
            if (argument == null || argument.trim().isEmpty() || argument.length() > 200 || hasControls(argument))
                throw new IOException("검색어를 1~200자로 입력해 주세요.");
            if (page > 34) throw new IOException("검색은 GitHub의 최대 1,000개 결과 범위까지 지원합니다.");
            return "search/repositories?q=" + URLEncoder.encode(argument.trim(), "UTF-8").replace("+", "%20") + "&" + paging;
        }
        String root = "repos/" + repository(repo);
        switch (view) {
            case REPOSITORY: return root;
            case ISSUES: return root + "/issues?state=open&sort=updated&direction=desc&" + paging;
            case PULLS: return root + "/pulls?state=open&sort=updated&direction=desc&" + paging;
            case ACTIONS: return root + "/actions/runs?" + paging;
            case ISSUE: return root + "/issues/" + number(argument);
            case PULL: return root + "/pulls/" + number(argument);
            case PULL_FILES: return root + "/pulls/" + number(argument) + "/files?" + paging;
            case REVIEWS: return root + "/pulls/" + number(argument) + "/reviews?" + paging;
            case CHECKS: return root + "/commits/" + sha(argument) + "/check-runs?filter=latest&" + paging;
            case STATUSES: return root + "/commits/" + sha(argument) + "/status?" + paging;
            default: throw new IOException("지원하지 않는 GitHub 조회입니다.");
        }
    }

    private static long number(String value) throws IOException {
        if (value == null || !value.matches("[1-9][0-9]{0,9}")) throw new IOException("이슈 또는 PR 번호가 올바르지 않습니다.");
        try { return Long.parseLong(value); } catch (NumberFormatException error) { throw new IOException("번호가 너무 큽니다."); }
    }
    private static String sha(String value) throws IOException {
        if (value == null || !value.matches("[a-fA-F0-9]{40}|[a-fA-F0-9]{64}")) throw new IOException("PR 커밋을 확인할 수 없습니다.");
        return value;
    }

    private Object decode(byte[] output) throws IOException {
        if (output.length > MAX_OUTPUT) throw new IOException("GitHub 응답 크기가 제한을 초과했습니다.");
        String text;
        try { text = StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(output)).toString(); }
        catch (java.nio.charset.CharacterCodingException invalid) { throw new IOException("GitHub 응답 인코딩을 확인할 수 없습니다."); }
        // Bound nesting before the platform JSON parser allocates nested objects.
        int depth = 0; boolean quoted = false, escape = false;
        for (int i = 0; i < text.length(); i++) {
            char c = text.charAt(i);
            if (quoted) { if (escape) escape = false; else if (c == '\\') escape = true; else if (c == '"') quoted = false; }
            else if (c == '"') quoted = true;
            else if (c == '[' || c == '{') { if (++depth > 32) throw new IOException("GitHub 응답 중첩이 너무 깊습니다."); }
            else if (c == ']' || c == '}') depth--;
        }
        return decoder.decode(text);
    }

    static Page parse(View view, String repository, Object decoded, int page) throws IOException {
        List<Row> rows = new ArrayList<>();
        if (view == View.REPOSITORY) {
            rows.add(repo(object(decoded))); return new Page(rows, "저장소 정보", false);
        }
        if (view == View.ISSUE || view == View.PULL) {
            rows.add(work(object(decoded), view == View.PULL, repository));
            return new Page(rows, view == View.PULL ? "PR 상세" : "이슈 상세", false);
        }
        Object list = decoded;
        String summary = "";
        boolean incomplete = false;
        if (view == View.SEARCH) {
            Map<String, Object> data = object(decoded); list = data.get("items");
            incomplete = Boolean.TRUE.equals(data.get("incomplete_results"));
            summary = incomplete ? "GitHub 검색 일부 결과 · 다시 조회할 수 있습니다" : "저장소 검색";
        } else if (view == View.CHECKS) { list = object(decoded).get("check_runs"); summary = "체크 실행 · PR HEAD 커밋 기준"; }
        else if (view == View.STATUSES) { list = object(decoded).get("statuses"); summary = "커밋 상태 · 체크 실행과 별도"; }
        else if (view == View.ACTIONS) { list = object(decoded).get("workflow_runs"); summary = "최근 Actions 실행"; }
        else if (view == View.PULL_FILES) summary = "PR 변경 파일 · GitHub 제공 patch (최대 3,000개)";
        else if (view == View.REVIEWS) summary = "PR 리뷰 · 작성 시간순";
        else summary = view == View.ISSUES ? "열린 이슈 · PR 제외" : "열린 PR";
        List<?> values = array(list);
        if (values.size() > PAGE_SIZE) throw new IOException("GitHub 목록이 요청한 페이지 크기를 초과했습니다.");
        for (Object raw : values) {
            Map<String, Object> item = object(raw);
            if (view == View.SEARCH) rows.add(repo(item));
            else if (view == View.ISSUES) { if (!item.containsKey("pull_request")) rows.add(work(item, false, repository)); }
            else if (view == View.PULLS) rows.add(work(item, true, repository));
            else if (view == View.PULL_FILES) {
                String patch = text(item, "patch", 131072);
                rows.add(new Row(Kind.FILE, 0, required(item, "filename", 4096), text(item, "status", 100),
                    patch.isEmpty() ? "이 파일의 patch가 응답에 없습니다. 바이너리 또는 큰 diff는 GitHub에서 확인해 주세요." : patch,
                    repository, ""));
            } else if (view == View.REVIEWS) {
                String author = item.get("user") instanceof Map ? text(object(item.get("user")), "login", 100) : "계정 미확인";
                rows.add(new Row(Kind.REVIEW, 0, author, text(item, "state", 100) + " · " + text(item, "submitted_at", 100),
                    text(item, "body", 16384), repository, ""));
            }
            else if (view == View.CHECKS || view == View.STATUSES) {
                boolean check = view == View.CHECKS;
                String state = text(item, check ? "conclusion" : "state", 100);
                if (state.isEmpty()) state = text(item, "status", 100);
                rows.add(new Row(Kind.CHECK, 0, required(item, check ? "name" : "context", 300),
                    state.isEmpty() ? "상태 미확인" : state, text(item, "description", 4000), repository, ""));
            } else {
                String conclusion = text(item, "conclusion", 100);
                rows.add(new Row(Kind.RUN, 0, required(item, "name", 300),
                    text(item, "status", 100) + (conclusion.isEmpty() ? "" : " · " + conclusion),
                    "브랜치: " + text(item, "head_branch", 300) + "\n" + text(item, "updated_at", 100), repository, ""));
            }
        }
        boolean next = values.size() == PAGE_SIZE && page < (view == View.SEARCH ? 34 : 100);
        return new Page(rows, summary, next);
    }

    private static Row repo(Map<String, Object> data) throws IOException {
        String name = repository(required(data, "full_name", 160));
        String detail = Boolean.TRUE.equals(data.get("private")) ? "비공개" : "공개";
        if (Boolean.TRUE.equals(data.get("archived"))) detail += " · 보관됨";
        return new Row(Kind.REPOSITORY, 0, name, detail, text(data, "description", 4000)
            + "\n기본 브랜치: " + text(data, "default_branch", 300), name, "");
    }

    private static Row work(Map<String, Object> data, boolean pull, String repository) throws IOException {
        Object raw = data.get("number");
        if (!(raw instanceof Number)) throw new IOException("GitHub 항목 번호가 없습니다.");
        long number = ((Number) raw).longValue();
        if (number <= 0 || number > 9999999999L || ((Number) raw).doubleValue() != number) throw new IOException("GitHub 항목 번호가 올바르지 않습니다.");
        String state = text(data, "state", 100);
        if (pull && data.get("merged_at") != null) state = "merged";
        if (Boolean.TRUE.equals(data.get("draft"))) state += " · draft";
        String head = "";
        if (pull && data.get("head") instanceof Map) head = text(object(data.get("head")), "sha", 64);
        if (!head.isEmpty()) sha(head);
        String author = data.get("user") instanceof Map ? text(object(data.get("user")), "login", 100) : "";
        return new Row(pull ? Kind.PULL : Kind.ISSUE, number, required(data, "title", 500), state + (author.isEmpty() ? "" : " · " + author),
            text(data, "body", 65536), repository, head);
    }

    @SuppressWarnings("unchecked") private static Map<String, Object> object(Object value) throws IOException {
        if (!(value instanceof Map)) throw new IOException("GitHub 응답 객체 형식이 올바르지 않습니다.");
        return (Map<String, Object>) value;
    }
    private static List<?> array(Object value) throws IOException {
        if (!(value instanceof List)) throw new IOException("GitHub 응답 목록 형식이 올바르지 않습니다.");
        return (List<?>) value;
    }
    private static String required(Map<String, Object> data, String key, int bound) throws IOException {
        String value = text(data, key, bound); if (value.isEmpty()) throw new IOException("GitHub 응답 필드가 없습니다: " + key); return value;
    }
    private static String text(Map<String, Object> data, String key, int bound) throws IOException {
        Object value = data.get(key); if (value == null) return "";
        if (!(value instanceof String)) throw new IOException("GitHub 응답 필드 형식이 올바르지 않습니다: " + key);
        String text = (String) value;
        if (text.length() > bound) text = text.substring(0, bound) + "…";
        return text.replaceAll("[\\p{Cntrl}&&[^\\n\\t]]|[\\u202A-\\u202E\\u2066-\\u2069]", "");
    }
    private static boolean hasControls(String value) {
        for (int i = 0; i < value.length(); i++) if (Character.isISOControl(value.charAt(i))) return true;
        return false;
    }
    private static String failure(Z8Git.Result result) {
        String error = new String(result.stderr, StandardCharsets.UTF_8);
        if (error.contains("HTTP 401") || error.contains("gh auth login")) return "GitHub 인증이 필요합니다. 이 프로젝트의 터미널에서 로그인해 주세요.";
        if (error.contains("HTTP 403") || error.contains("HTTP 429")) return "GitHub 권한 또는 요청 제한으로 조회하지 못했습니다. 로그인과 접근 권한을 확인하고 잠시 후 다시 시도해 주세요.";
        if (error.contains("HTTP 404")) return "저장소나 항목을 찾지 못했거나 이 계정의 접근 권한이 없습니다.";
        return "GitHub 조회를 완료하지 못했습니다 (gh 종료 코드 " + result.code + "). 네트워크·로그인·gh 설치를 터미널에서 확인해 주세요.";
    }
}
