package com.termux.app;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;
import com.termux.BuildConfig;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Public, offline-readable notices. Operator details come only from the release configuration. */
public final class Z8AboutActivity extends Activity {
    public enum Page { PRIVACY, DATA, ENVIRONMENT, LICENSES }
    private static final String EXTRA_PAGE = "dev.devsigner.z8.ABOUT_PAGE";
    private final ExecutorService reader = Executors.newSingleThreadExecutor();
    private Z8PanelUi ui;
    private Page page = Page.PRIVACY;
    private int licensePage;
    private List<String> licensePages;
    private TextView licenseText, licensePosition;
    private LinearLayout licensePrevious, licenseNext;

    public static Intent intent(Context context, Page page) {
        return new Intent(context, Z8AboutActivity.class).putExtra(EXTRA_PAGE, page.name());
    }
    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        try { page = Page.valueOf(getIntent().getStringExtra(EXTRA_PAGE)); } catch (RuntimeException ignored) { }
        if (saved != null) licensePage = Math.max(0, saved.getInt("licensePage", 0));
        render();
    }
    @Override public void onSaveInstanceState(Bundle state) { state.putInt("licensePage", licensePage); super.onSaveInstanceState(state); }
    @Override public void onDestroy() { reader.shutdownNow(); super.onDestroy(); }

    private void render() {
        String title = page == Page.PRIVACY ? Z8Text.text("Privacy policy", "개인정보처리방침") : page == Page.DATA ? Z8Text.text("Data storage and deletion", "데이터 보관·삭제")
            : page == Page.ENVIRONMENT ? Z8Text.text("Environment and external tools", "환경·외부 도구 안내") : Z8Text.text("Open-source licenses and source", "오픈소스 라이선스·소스");
        ui = new Z8PanelUi(this, title);
        switch (page) {
            case PRIVACY: privacy(); break;
            case DATA: data(); break;
            case ENVIRONMENT: environment(); break;
            case LICENSES: licenses(); break;
        }
    }

    private void privacy() {
        paragraph(Z8Text.text("Z8 Privacy Policy · ", "Z8 개인정보처리방침 · ") + BuildConfig.Z8_POLICY_DATE);
        ui.section(Z8Text.text("Developer and contact", "운영자와 문의"));
        if (!BuildConfig.Z8_DEVELOPER_NAME.trim().isEmpty()) paragraph(Z8Text.text("Developer: ", "운영자: ") + BuildConfig.Z8_DEVELOPER_NAME);
        if (!BuildConfig.Z8_SUPPORT_EMAIL.trim().isEmpty()) {
            paragraph(Z8Text.text("Privacy inquiries: ", "개인정보 문의: ") + BuildConfig.Z8_SUPPORT_EMAIL);
            ui.setting(Z8Text.text("Compose an email", "문의 이메일 작성"), Z8Text.text("Review the message before sending it yourself.", "내용을 검토한 뒤 직접 전송할 수 있습니다."), this::email);
        } else paragraph(Z8Text.text("This build does not include developer contact information.", "이 빌드에는 운영자 연락처가 등록되지 않았습니다."));
        webLink(Z8Text.text("Online privacy policy", "공개 개인정보처리방침"), BuildConfig.Z8_PRIVACY_URL);
        ui.section(Z8Text.text("What Z8 does", "Z8의 역할"));
        paragraph(Z8Text.text("Z8 is a development tool that provides a Linux environment and terminal for each project on Android. Z8 does not operate its own account system or AI model server. It does not include advertising, usage analytics or automatic crash reporting.", "Z8는 Android에서 프로젝트별 Linux 환경과 터미널을 제공하는 개발 도구입니다. Z8 자체 계정이나 AI 모델 서버를 운영하지 않습니다. 광고, 사용 분석, 자동 오류 보고 기능을 제공하지 않습니다."));
        ui.section(Z8Text.text("Information stored on your device", "기기에 보관하는 정보"));
        paragraph(Z8Text.text("Z8 processes project names and source files, Linux environments, settings, shell history and CLI credentials in each project's HOME, app settings and notification history in app storage. Notification integration records event types, times, and project and session names and identifiers. It does not copy prompts or command text into notification history.", "프로젝트 이름과 소스 파일, Linux 환경, 프로젝트 HOME의 설정·셸 기록·CLI 인증 정보, 앱 설정과 알림 기록을 앱 저장소에서 처리합니다. 알림 연결은 종류·시간·프로젝트 및 세션의 이름·식별자를 기록하며 프롬프트나 명령 원문을 알림 기록으로 복사하지 않습니다."));
        paragraph(Z8Text.text("The built-in preview may store cookies, site storage and caches from development servers on your device. Preview data is shared across all projects. This browser data is separate from CLI authentication files.", "내부 미리보기는 방문한 개발 서버의 쿠키·사이트 저장소·캐시를 기기에 보관할 수 있습니다. 미리보기 데이터는 모든 프로젝트가 공유합니다. 이 브라우저 데이터와 CLI의 인증 파일은 서로 별개입니다."));
        ui.section(Z8Text.text("Network access and external services", "네트워크와 외부 서비스"));
        paragraph(Z8Text.text("Downloading development environments and tools connects to the selected distribution servers, which receive your IP address and download request information. Git, CLIs, package installers and development servers that you run connect to networks according to their commands and settings. Pages opened in the preview may also connect to external servers according to their code.", "개발 환경과 도구를 내려받을 때 선택한 배포 서버로 접속하며, 서버에는 IP 주소와 다운로드 요청 정보가 전달됩니다. 사용자가 실행한 Git, CLI, 패키지 설치 도구와 개발 서버는 해당 명령과 설정에 따라 네트워크에 접속합니다. 미리보기에서 연 웹페이지도 페이지 코드에 따라 외부 서버에 접속할 수 있습니다."));
        paragraph(Z8Text.text("External CLIs such as Codex and Claude Code authenticate with the service and account you choose and may send input, source code and command results to that service. The data sent, diagnostics, retention periods and deletion procedures depend on the tool version, settings and provider policies. Running locally does not mean that AI processing or all work happens offline.", "Codex·Claude Code 등 외부 CLI는 사용자가 선택한 서비스와 계정으로 인증하며, 입력·소스·명령 결과 등을 서비스로 보낼 수 있습니다. 실제 전송 범위, 진단 정보, 보관 기간과 삭제 절차는 설치한 도구의 버전·설정 및 공급자 정책에 따릅니다. 로컬에서 실행된다는 말은 AI 처리나 모든 작업이 오프라인이라는 뜻이 아닙니다."));
        paragraph(Z8Text.text("External websites and sign-in pages open in your device's browser. That browser and those websites apply their own privacy policies. Z8 does not delete browser sign-ins or external service accounts on your behalf.", "외부 사이트와 로그인은 기기 브라우저의 창에서 열립니다. 해당 브라우저와 사이트는 각자의 개인정보처리방침을 적용합니다. Z8가 브라우저 로그인 정보나 외부 서비스의 계정을 대신 삭제하지는 않습니다."));
        ui.section(Z8Text.text("Protection, retention and deletion", "보호와 보관·삭제"));
        paragraph(Z8Text.text("Z8 uses Android app-private storage and disables automatic app backup. External authentication URLs are not written to saved screen state or notification history. The protection of CLI authentication files depends on the tool; Z8 does not guarantee that all credentials are stored in a separate encrypted vault.", "Z8는 Android 앱 전용 저장소를 사용하며 앱의 자동 백업을 허용하지 않습니다. 외부 인증 URL은 저장된 화면 상태나 알림 기록에 쓰지 않습니다. CLI 인증 파일의 보호 방식은 해당 도구에 따르며, 모든 인증 정보가 별도 암호화 저장소에 보관된다고 보장하지 않습니다."));
        paragraph(Z8Text.text("Project data may remain until you delete the project or clear app data. Conversations and history recorded by a CLI depend on its settings. App notification history holds up to 256 entries; at that limit, new entries may replace older entries that have been read or belong to ended sessions. You can also clear eligible history from the notifications screen.", "프로젝트 데이터는 사용자가 프로젝트를 삭제하거나 앱 데이터를 지울 때까지 남을 수 있습니다. CLI가 기록하는 대화·히스토리는 도구 설정에 따라 달라집니다. 앱 알림 기록은 최대 256개이며, 한도에 도달하면 읽었거나 종료된 오래된 기록을 새 기록으로 대체할 수 있습니다. 알림 화면에서도 기록을 정리할 수 있습니다."));
        paragraph(Z8Text.text("Clear built-in preview data separately in Settings. Clear app data in Android settings to remove shared app settings and remaining local data. Information stored on external servers must be deleted through the provider's procedures. For privacy inquiries, use the contact information above.", "내부 미리보기 데이터는 설정에서 별도로 삭제합니다. 앱 공통 설정과 남은 로컬 데이터는 Android 설정의 앱 데이터 삭제로 제거할 수 있습니다. 외부 서버에 보관된 정보는 공급자의 삭제 절차를 이용해야 합니다. 개인정보 관련 문의는 위 연락처로 요청할 수 있습니다."));
        ui.setting(Z8Text.text("More about deleting data", "삭제 방법 자세히 보기"), Z8Text.text("Closing sessions, signing out and deleting projects", "종료·로그아웃·프로젝트 삭제의 차이"), () -> startActivity(intent(this, Page.DATA)));
    }

    private void data() {
        ui.section(Z8Text.text("Closing a terminal and signing out", "터미널 종료와 로그아웃"));
        paragraph(Z8Text.text("Closing a terminal leaves project files, shell history and saved CLI credentials in place. Use each tool's official sign-out command in the relevant project. Check the help for your installed version first.", "터미널을 닫아도 프로젝트 파일, 셸 기록과 저장된 CLI 로그인 정보는 남습니다. 각 도구의 공식 로그아웃 명령을 해당 프로젝트에서 사용하세요. 설치한 버전의 도움말을 먼저 확인하세요."));
        paragraph(Z8Text.text("Signing out locally or deleting authentication files does not guarantee deletion of an external service account or revocation of issued tokens. Check connected apps, sessions and tokens in your provider account settings and revoke them if needed. Custom authentication paths or environment variables may require separate handling.", "로컬 로그아웃이나 인증 파일 삭제는 외부 서비스 계정 삭제 또는 발급된 토큰의 폐기를 보장하지 않습니다. 공급자 계정 설정에서 연결된 앱·세션·토큰을 확인하고 필요하면 직접 해제하세요. 사용자 지정 인증 경로나 환경변수는 별도일 수 있습니다."));
        ui.section(Z8Text.text("Deleting a project", "프로젝트 삭제"));
        paragraph(Z8Text.text("Long-press a project's name in the project list to delete it. Z8 stops its running sessions, then removes that project's source files, Linux environment, HOME and project settings. CLI credentials and history in HOME are also removed. Back up any files you need first.", "프로젝트 목록에서 이름을 길게 눌러 삭제할 수 있습니다. 실행 중인 세션을 종료한 뒤 해당 프로젝트의 소스, Linux 환경, HOME과 프로젝트 설정을 지웁니다. HOME에 있는 CLI 인증 정보와 기록도 함께 삭제됩니다. 필요한 파일을 먼저 보관하세요."));
        paragraph(Z8Text.text("Deleting a project does not delete other projects, shared notification history, built-in preview data, device browser sign-ins or data on external servers. Files for unreadable projects are preserved and are not deleted automatically.", "프로젝트를 삭제해도 다른 프로젝트, 앱 공통 알림 기록, 내부 미리보기 데이터, 기기 브라우저 로그인 상태와 외부 서버의 데이터는 함께 삭제되지 않습니다. 읽을 수 없는 프로젝트는 파일을 보존하며, 자동으로 지우지 않습니다."));
        ui.section(Z8Text.text("Preview data", "미리보기 데이터"));
        paragraph(Z8Text.text("Clear preview data in Settings removes the built-in WebView's cookies, site storage, caches and service workers shared by all projects. Z8 stops open previews and displays the result after WebView reports completion. If your WebView does not support this operation, Z8 asks you to update it.", "설정의 ‘미리보기 데이터 삭제’는 모든 프로젝트가 공유하는 내부 WebView의 쿠키·사이트 저장소·캐시·서비스 워커를 삭제합니다. 열린 미리보기를 멈추고 WebView가 완료를 알려준 뒤 결과를 표시합니다. 지원되지 않는 WebView에서는 업데이트 안내를 제공합니다."));
        paragraph(Z8Text.text("This does not delete project source files, CLI credentials or sign-ins in external browsers such as Chrome. Development servers running in the terminal continue running.", "이 작업은 프로젝트 소스, CLI 인증 정보, Chrome 등 외부 브라우저의 로그인 상태를 지우지 않습니다. 터미널에서 실행한 개발 서버는 계속 실행됩니다."));
        ui.section(Z8Text.text("Notifications and all app data", "알림과 앱 전체 데이터"));
        paragraph(Z8Text.text("Clear history on the notifications screen removes read notifications and history for ended sessions. Clearing notifications does not approve or reject a CLI request.", "알림 화면의 ‘기록 정리’는 읽은 알림과 종료된 세션의 기록을 정리합니다. 알림을 정리하는 것은 CLI의 요청을 승인하거나 거절하는 동작이 아닙니다."));
        paragraph(Z8Text.text("Clearing Z8's app data in Android settings deletes local app data, including projects. Manage data already sent to external services and information in external browsers separately.", "Android 설정에서 Z8의 앱 데이터를 지우면 프로젝트를 포함한 앱의 로컬 데이터가 삭제됩니다. 외부 서비스에 이미 전송된 데이터와 외부 브라우저 정보는 별도로 관리하세요."));
    }

    private void environment() {
        ui.section(Z8Text.text("Development environment on your device", "기기에서 실행하는 개발 환경"));
        paragraph(Z8Text.text("Each project has separate source files, HOME and a Linux environment. PRoot shares the Android kernel and the app's permissions; it is not a security virtual machine. Z8 does not guarantee that tools running with the same app permissions cannot access other projects or authentication files. Run only code and tools you trust.", "프로젝트마다 소스와 HOME, Linux 환경을 나눕니다. PRoot는 Android 커널과 앱 권한을 공유하며 보안 가상 머신이 아닙니다. 같은 앱 권한으로 실행되는 도구에 대해 다른 프로젝트나 인증 파일의 접근 차단을 보장하지 않습니다. 신뢰하는 코드와 도구만 실행하세요."));
        ui.section(Z8Text.text("External CLIs and AI services", "외부 CLI와 AI 서비스"));
        paragraph(Z8Text.text("Z8 helps install and run official command-line tools and open browser authentication. Each external service's accounts, subscriptions and terms apply separately. Z8 does not sell access to these services or provide accounts on your behalf.", "Z8는 공식 명령줄 도구의 설치와 실행, 브라우저 인증 연결을 돕습니다. 각 외부 서비스의 계정·구독·약관은 별도로 적용됩니다. Z8가 이용권을 판매하거나 사용자의 계정을 대신 제공하지 않습니다."));
        paragraph(Z8Text.text("Installing an executable or checking its version does not guarantee sign-in or compatibility with all features. Some Linux sandbox features are unavailable on Android. If you choose Codex local mode, file changes, shell commands and network operations may run without that tool's sandbox and without additional approval. Read the explanation and choices shown before running it.", "실행 파일의 설치나 버전 확인이 로그인과 모든 기능의 호환성을 보장하지는 않습니다. 일부 Linux sandbox 기능은 Android에서 사용할 수 없습니다. Codex의 로컬 실행 모드를 선택하면 해당 도구의 sandbox 없이 파일 수정·셸·네트워크 작업이 추가 승인 없이 실행될 수 있습니다. 실행 전에 표시되는 설명과 선택을 확인하세요."));
        paragraph(Z8Text.text("Codex local-mode consent is stored separately for each project. Run 'codex --z8-reset-local-mode' to clear the choice for future launches. This does not change sessions already running or your provider account state.", "Codex 로컬 실행 동의는 프로젝트별로 저장됩니다. ‘codex --z8-reset-local-mode’로 향후 실행의 선택을 해제할 수 있습니다. 이미 실행 중인 세션이나 공급자 계정의 상태는 바꾸지 않습니다."));
        ui.section(Z8Text.text("Installation and storage", "설치와 저장 공간"));
        paragraph(Z8Text.text("Installing development tools requires an internet connection and may involve hundreds of MB of downloads and several GB of free storage per project. You can choose network usage during initial setup. Actual sizes depend on the tools and versions.", "개발 도구 설치에는 인터넷 연결과 수백 MB 이상의 다운로드, 프로젝트별로 수 GB의 여유 공간이 필요할 수 있습니다. 초기 설치 화면에서 네트워크 사용을 선택할 수 있으며 실제 크기는 도구와 버전에 따라 달라집니다."));
        ui.section(Z8Text.text("Previews and authentication", "미리보기와 인증"));
        paragraph(Z8Text.text("Localhost development servers open in the built-in preview. External websites and sign-in flows continue in your device's browser; closing that browser window returns you to the terminal. Check external services' retention and transfer policies before entering sensitive information.", "localhost 개발 서버는 내부 미리보기에서 표시합니다. 외부 사이트와 로그인은 기기 브라우저의 창에서 이어지며 창을 닫으면 터미널로 돌아갑니다. 외부 서비스의 보관·전송 정책을 확인한 뒤 민감한 정보를 입력하세요."));
    }

    private void licenses() {
        paragraph(Z8Text.text("License and copyright notices for this app and its included software. Long notices are split into pages.", "이 앱과 포함된 소프트웨어의 라이선스·저작권 고지입니다. 긴 고지는 페이지를 나누어 표시합니다."));
        paragraph(Z8Text.text("Z8 is a modified Termux application distributed under GNU GPL version 3 only. You may use, modify and redistribute it under that license. Individual components retain their own licenses and original copyright notices below.", "Z8는 GNU GPL 버전 3 전용 조건으로 배포하는 Termux 수정 앱입니다. 해당 라이선스에 따라 사용·수정·재배포할 수 있습니다. 개별 구성요소의 라이선스와 원저작권 고지는 아래에 유지됩니다."));
        paragraph(Z8Text.text("This software is provided without warranty to the extent permitted by applicable law. The full license terms and original notices follow; corresponding sources and build instructions are available from the link below.", "관계 법령이 허용하는 범위에서 이 소프트웨어에는 보증이 제공되지 않습니다. 전체 라이선스와 원문 고지는 아래에서, 대응 소스와 빌드 안내는 다음 링크에서 확인할 수 있습니다."));
        webLink(Z8Text.text("Corresponding source and build information", "대응 소스와 빌드 안내"), BuildConfig.Z8_SOURCE_URL);
        licensePosition = paragraph(Z8Text.text("Loading notices…", "고지를 불러오는 중…"));
        licenseText = paragraph("");
        licensePrevious = ui.setting(Z8Text.text("Previous page", "이전 페이지"), "", () -> showLicensePage(licensePage - 1));
        licenseNext = ui.setting(Z8Text.text("Next page", "다음 페이지"), "", () -> showLicensePage(licensePage + 1));
        licensePrevious.setVisibility(View.GONE); licenseNext.setVisibility(View.GONE);
        reader.execute(() -> {
            List<String> pages = new ArrayList<>();
            try (InputStream input = getAssets().open("z8-licenses/third-party-notices.txt");
                 ByteArrayOutputStream bytes = new ByteArrayOutputStream()) {
                byte[] buffer = new byte[8192]; int count;
                while ((count = input.read(buffer)) != -1) {
                    if (Thread.currentThread().isInterrupted() || bytes.size() + count > 16 * 1024 * 1024)
                        throw new java.io.IOException("Notice unavailable");
                    bytes.write(buffer, 0, count);
                }
                String text = new String(bytes.toByteArray(), StandardCharsets.UTF_8);
                for (int start = 0; start < text.length();) {
                    int end = Math.min(start + 14000, text.length());
                    if (end < text.length()) {
                        int line = text.lastIndexOf('\n', end);
                        if (line > start) end = line + 1;
                        else if (Character.isHighSurrogate(text.charAt(end - 1))) end--;
                    }
                    pages.add(text.substring(start, end)); start = end;
                }
            } catch (Exception unavailable) { pages.clear(); }
            runOnUiThread(() -> {
                if (isFinishing() || isDestroyed()) return;
                licensePages = pages;
                if (pages.isEmpty()) { licensePosition.setText(Z8Text.text("Could not read the open-source notices for this build.", "이 빌드의 오픈소스 고지를 읽을 수 없습니다.")); return; }
                showLicensePage(Math.min(licensePage, pages.size() - 1));
            });
        });
    }
    private void showLicensePage(int next) {
        if (licensePages == null || next < 0 || next >= licensePages.size()) return;
        licensePage = next;
        licensePosition.setText((next + 1) + " / " + licensePages.size() + Z8Text.text(" pages", " 페이지"));
        licenseText.setText(licensePages.get(next));
        licensePrevious.setVisibility(next > 0 ? View.VISIBLE : View.GONE);
        licenseNext.setVisibility(next + 1 < licensePages.size() ? View.VISIBLE : View.GONE);
        ui.scroll.post(() -> { if (!isDestroyed()) ui.scroll.scrollTo(0, 0); });
    }
    private TextView paragraph(String text) {
        TextView view = ui.text(text, 14, ui.style.text, false);
        view.setLineSpacing(ui.dp(5), 1); view.setTextIsSelectable(true);
        view.setPadding(ui.dp(8), ui.dp(12), ui.dp(8), ui.dp(4));
        ui.content.addView(view, new LinearLayout.LayoutParams(-1, -2)); return view;
    }
    private void webLink(String label, String value) {
        String url = Z8BrowserUrls.normalize(value);
        if (url == null || !"https".equalsIgnoreCase(Uri.parse(url).getScheme())) return;
        ui.setting(label, Uri.parse(url).getHost(), () -> {
            try { startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url))); }
            catch (ActivityNotFoundException | SecurityException unavailable) { Toast.makeText(this, Z8Text.text("Could not open the link in a browser.", "브라우저에서 링크를 열 수 없습니다."), Toast.LENGTH_LONG).show(); }
        });
    }
    private void email() {
        if (BuildConfig.Z8_SUPPORT_EMAIL.trim().isEmpty()) return;
        try { startActivity(new Intent(Intent.ACTION_SENDTO, Uri.fromParts("mailto", BuildConfig.Z8_SUPPORT_EMAIL, null))); }
        catch (ActivityNotFoundException | SecurityException unavailable) { Toast.makeText(this, Z8Text.text("Could not open an email app. Copy the address shown above.", "메일 앱에서 작성할 수 없습니다. 표시된 주소를 복사해 주세요."), Toast.LENGTH_LONG).show(); }
    }
}
