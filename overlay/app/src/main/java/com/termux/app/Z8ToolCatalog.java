package com.termux.app;

import java.util.Arrays;
import java.util.Collections;
import java.util.List;

/** Fixed display/install choices. A catalog lookup never executes or downloads a tool. */
public final class Z8ToolCatalog {
    public enum Group { RECOMMENDED, OPTIONAL }
    public enum Presence { UNKNOWN, NEEDS_INSTALLATION, INSTALLED }

    public static final class Tool {
        public final String id;
        public final Group group;
        public final boolean releaseMetadata;
        private final String englishName, koreanName, englishDetail, koreanDetail;
        private final List<String> packages;

        private Tool(String id, Group group, String englishName, String koreanName,
                String englishDetail, String koreanDetail, boolean releaseMetadata, String... packages) {
            this.id = id; this.group = group; this.englishName = englishName; this.koreanName = koreanName;
            this.englishDetail = englishDetail; this.koreanDetail = koreanDetail;
            this.releaseMetadata = releaseMetadata;
            this.packages = Collections.unmodifiableList(Arrays.asList(packages.clone()));
        }
        public String name() { return Z8Text.text(englishName, koreanName); }
        public String detail() { return Z8Text.text(englishDetail, koreanDetail); }
        public List<String> packages() { return packages; }
        public boolean isProviderClient() { return id.equals("codex") || id.equals("claude"); }
        public String source() {
            switch (id) {
                case "node": return Z8Text.text("Official Node.js download and this Linux environment's package repositories.", "Node.js 공식 다운로드와 이 Linux 환경의 패키지 저장소.");
                case "codex": return Z8Text.text("Official OpenAI Codex release and this Linux environment's package repositories.", "OpenAI Codex 공식 릴리스와 이 Linux 환경의 패키지 저장소.");
                case "claude": return Z8Text.text("Official Anthropic Claude Code download and this Linux environment's package repositories.", "Anthropic Claude Code 공식 다운로드와 이 Linux 환경의 패키지 저장소.");
                default: return Z8Text.text("This Linux environment's configured package repositories.", "이 Linux 환경에 설정된 패키지 저장소.");
            }
        }
    }

    public static final List<Tool> TOOLS = Collections.unmodifiableList(Arrays.asList(
        new Tool("python", Group.RECOMMENDED, "Python", "Python", "Python, pip and virtual environments.", "Python, pip, 가상 환경.", false,
            "python3", "python3-pip", "python3-venv", "ca-certificates"),
        new Tool("git", Group.RECOMMENDED, "Git", "Git", "Version control for your projects.", "프로젝트 버전 관리.", false,
            "git", "ca-certificates"),
        new Tool("node", Group.OPTIONAL, "Node.js 24 LTS", "Node.js 24 LTS", "JavaScript runtime and npm.", "JavaScript 실행 환경과 npm.", true,
            "python3", "ca-certificates"),
        new Tool("codex", Group.OPTIONAL, "Codex", "Codex", "Official command-line client. Uses your own account.", "공식 명령줄 클라이언트. 본인 계정으로 사용합니다.", true,
            "python3", "ca-certificates"),
        new Tool("claude", Group.OPTIONAL, "Claude Code", "Claude Code", "Official command-line client. Uses your own account.", "공식 명령줄 클라이언트. 본인 계정으로 사용합니다.", true,
            "python3", "ca-certificates", "gpgv"),
        new Tool("gh", Group.OPTIONAL, "GitHub CLI", "GitHub CLI", "Work with GitHub from the terminal.", "터미널에서 GitHub 작업.", false,
            "gh", "git", "python3", "ca-certificates"),
        new Tool("ssh", Group.OPTIONAL, "SSH client", "SSH 클라이언트", "Connect to your remote machines.", "원격 컴퓨터에 연결.", false,
            "openssh-client", "ca-certificates"),
        new Tool("build-tools", Group.OPTIONAL, "Build tools", "빌드 도구", "C/C++ compiler, make and standard build dependencies.", "C/C++ 컴파일러, make, 기본 빌드 의존성.", false,
            "build-essential"),
        new Tool("tmux", Group.OPTIONAL, "tmux", "tmux", "Terminal sessions and panes inside the Linux shell.", "Linux 셸 안에서 세션과 창 관리.", false,
            "tmux"),
        new Tool("utilities", Group.OPTIONAL, "Utilities", "유틸리티", "Search, transfer, archive and editing tools.", "검색, 전송, 압축, 편집 도구.", false,
            "bash-completion", "curl", "wget", "ripgrep", "fd-find", "fzf", "jq", "less", "nano", "tree", "file", "unzip", "zip", "procps", "ca-certificates")
    ));

    private Z8ToolCatalog() {}

    public static Tool get(String id) {
        for (Tool tool : TOOLS) if (tool.id.equals(id)) return tool;
        throw new IllegalArgumentException("Unknown tool");
    }

    /** A failed or absent check is not proof that a custom/manual installation is absent. */
    public static Presence presence(boolean checked, boolean installed, boolean incomplete) {
        if (installed) return Presence.INSTALLED;
        return checked && !incomplete ? Presence.NEEDS_INSTALLATION : Presence.UNKNOWN;
    }

    /** Recognize only known CLI output formats; a random number in custom output is not a version. */
    public static String releaseVersion(String tool, String value) {
        if (tool == null || value == null) return "";
        if (validReleaseVersion(tool, value)) return value;
        String candidate = "";
        if (tool.equals("codex") && value.matches("codex-cli [0-9]+\\.[0-9]+\\.[0-9]+")) candidate = value.substring(10);
        if (tool.equals("claude") && value.matches("[0-9]+\\.[0-9]+\\.[0-9]+ \\(Claude Code\\)")) candidate = value.substring(0, value.indexOf(' '));
        return validReleaseVersion(tool, candidate) ? candidate : "";
    }

    /** Exact request shown in the confirmation dialog and later handed to the service. */
    public static final class Request {
        public final Tool tool;
        public final boolean update;
        public final String version;
        public Request(String toolId, boolean update, String version) {
            tool = get(toolId); this.update = update;
            this.version = version == null ? "" : version;
            if (!tool.releaseMetadata && !this.version.isEmpty()) throw new IllegalArgumentException("Package versions come from configured repositories");
            if (!update && !this.version.isEmpty()) throw new IllegalArgumentException("Install uses the configured release");
            if (update && tool.releaseMetadata && !validReleaseVersion(tool.id, this.version))
                throw new IllegalArgumentException("Check the official release before updating");
        }
    }

    static boolean validReleaseVersion(String tool, String version) {
        String number = "(0|[1-9][0-9]{0,5})";
        if (tool == null || version == null || version.length() > 30) return false;
        if (tool.equals("node")) return version.matches("v24\\." + number + "\\." + number);
        return (tool.equals("codex") || tool.equals("claude"))
            && version.matches(number + "\\." + number + "\\." + number);
    }
}
