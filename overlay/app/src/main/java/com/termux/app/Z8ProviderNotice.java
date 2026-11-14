package com.termux.app;

import java.io.IOException;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.WeakHashMap;

/** Local information acknowledgment, never a provider contract or execution permission. */
public final class Z8ProviderNotice {
    public static final int REVISION = 1;
    private Z8ProviderNotice() {}

    public static boolean applies(String action) { return "codex".equals(action) || "claude".equals(action); }
    static String project(String value) {
        if (value == null || !UUID.fromString(value).toString().equals(value)) throw new IllegalArgumentException("Invalid project");
        return value;
    }
    public static String name(String tool) {
        if (!applies(tool)) throw new IllegalArgumentException("Unknown provider client");
        return "codex".equals(tool) ? "Codex" : "Claude Code";
    }
    public static String explanation(String tool) {
        String provider = "codex".equals(tool) ? "OpenAI" : "Anthropic";
        name(tool);
        return Z8Text.text(
            "Signing in and using this client can send prompts, source context, command output, account information and diagnostics to your configured provider, such as " + provider + ". What is sent and who receives it depend on the client, account, endpoint and settings.\n\n"
            + "Use your own account. Provider terms, privacy settings and charges apply separately. Z8 is a local terminal and does not operate the model service.\n\n"
            + "Continue acknowledges this Z8 notice; it does not accept a provider contract. You can cancel and keep using the terminal.",
            "이 클라이언트에 로그인하고 사용하면 프롬프트·소스 코드 문맥·명령 실행 결과·계정 정보·진단 정보가 선택·설정한 제공자(예: " + provider + ")에게 전송될 수 있습니다. 전송 내용과 수신자는 클라이언트·계정·연결 주소·설정에 따라 달라집니다.\n\n"
            + "본인 계정으로 사용하며, 제공자의 약관·개인정보 설정·요금이 별도로 적용됩니다. Z8는 로컬 터미널이며 모델 서비스를 운영하지 않습니다.\n\n"
            + "계속은 이 Z8 안내를 확인한다는 뜻이며 제공자 계약에 동의하는 것이 아닙니다. 취소해도 터미널을 계속 사용할 수 있습니다.");
    }
    public static String boundary() {
        return Z8Text.text("This notice covers Z8's Open action. Commands or custom launchers you run in the terminal are not automatically intercepted. Review the provider's settings before use.",
            "이 안내는 Z8의 열기 동작에 적용됩니다. 터미널에서 직접 실행하는 명령이나 사용자 실행기는 자동으로 가로채지 않습니다. 사용 전 제공자 설정을 확인하세요.");
    }
    public static final class Link {
        public final String label, url;
        Link(String en, String ko, String url) { this.label = Z8Text.text(en, ko); this.url = url; }
    }
    public static List<Link> links(String tool, String version) {
        name(tool);
        if ("claude".equals(tool)) return Collections.unmodifiableList(Arrays.asList(
            new Link("Consumer terms", "개인용 약관", "https://www.anthropic.com/legal/consumer-terms"),
            new Link("Commercial terms", "상업용 약관", "https://www.anthropic.com/legal/commercial-terms"),
            new Link("Privacy policy", "개인정보처리방침", "https://www.anthropic.com/legal/privacy"),
            new Link("Claude Code data and controls", "Claude Code 데이터·설정 안내", "https://code.claude.com/docs/en/data-usage"),
            new Link("Claude Code license and conditions", "Claude Code 라이선스·조건", "https://code.claude.com/docs/en/legal-and-compliance")));
        String normalized = Z8ToolCatalog.releaseVersion(tool, version);
        String ref = normalized.isEmpty() ? "main" : "rust-v" + normalized;
        String suffix = normalized.isEmpty() ? Z8Text.text(" · current repository", " · 현재 저장소") : " · " + normalized;
        return Collections.unmodifiableList(Arrays.asList(
            new Link("Consumer terms", "개인용 약관", "https://openai.com/policies/terms-of-use/"),
            new Link("Business / API terms", "기업·API 약관", "https://openai.com/policies/services-agreement/"),
            new Link("Privacy policy", "개인정보처리방침", "https://openai.com/policies/privacy-policy/"),
            new Link("Codex data and controls", "Codex 데이터·설정 안내", "https://learn.chatgpt.com/docs/config-file/config-advanced"),
            new Link("Codex LICENSE" + suffix, "Codex LICENSE" + suffix, "https://github.com/openai/codex/blob/" + ref + "/LICENSE"),
            new Link("Codex NOTICE" + suffix, "Codex NOTICE" + suffix, "https://github.com/openai/codex/blob/" + ref + "/NOTICE")));
    }

    interface Store {
        String read(String projectId, String tool) throws IOException;
        void write(String projectId, String tool, String value) throws IOException;
    }

    /** Rotation/resume may deliver the same prepared service ticket while its dialog is open. */
    static final class PendingRequests<T> {
        private final Map<T, Ticket> values = new WeakHashMap<>();
        static final class Ticket {
            final String requestId;
            Ticket(String requestId) { this.requestId = requestId; }
        }
        Ticket begin(T owner, String requestId, Runnable rejectDifferentRequest) {
            if (owner == null || requestId == null || requestId.isEmpty()) throw new IllegalArgumentException("Missing launch ticket");
            Ticket previous = values.get(owner);
            if (previous != null) {
                // Cancelling an identical request would also cancel the original dialog's launch.
                if (!previous.requestId.equals(requestId)) rejectDifferentRequest.run();
                return null;
            }
            Ticket ticket = new Ticket(requestId); values.put(owner, ticket); return ticket;
        }
        boolean current(T owner, Ticket ticket) { return values.get(owner) == ticket; }
        void remove(T owner, Ticket ticket) { values.remove(owner, ticket); }
    }
    /** A decision is single use. Unknown installation identities can never be remembered. */
    static final class Decision {
        final String projectId, tool, identity;
        private final Store store;
        private final Runnable launch;
        private boolean finished;
        Decision(String projectId, String tool, String identity, Store store, Runnable launch) {
            this.projectId = project(projectId); name(tool); this.tool = tool;
            this.identity = identity == null ? "" : identity;
            this.store = store; this.launch = launch;
        }
        String value() { return REVISION + ":" + identity; }
        boolean needsNotice() {
            if (identity.isEmpty()) return true;
            try { return !value().equals(store.read(projectId, tool)); }
            catch (IOException unavailable) { return true; }
        }
        void cancel() { finished = true; }
        boolean continueOnce() {
            if (finished) return false;
            finished = true;
            boolean remembered = false;
            if (!identity.isEmpty()) try { store.write(projectId, tool, value()); remembered = true; }
            catch (IOException unavailable) { /* Explicit choice still opens once; ask again next time. */ }
            launch.run();
            return remembered;
        }
        boolean alreadyAcknowledged() {
            if (!finished && !needsNotice()) { finished = true; launch.run(); return true; }
            return false;
        }
    }
}
