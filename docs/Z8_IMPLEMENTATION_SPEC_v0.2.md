# z8 Android 개발 워크스페이스 구현 명세 v0.2

> 2026-10-05 범위 변경: 사용자 요청으로 네이티브 파일·Git·GitHub 화면과 별도 워크스페이스 홈을 제거한다. 프로젝트·세션·터미널을 중심으로 하고 git·gh 등은 최초 환경 준비에서 설치한다. 해당 UI에 관한 아래 초기 계획은 현재 범위와 다르다.
>
> 2026-10-05 추가 확정: **MVP는 Local only이며 Remote는 후속으로 보류한다.** 아래 U08·F10·G3, SSH 호스트·원격 tmux·SFTP·원격 알림 항목은 향후 설계 기록이며 현재 MVP의 구현 또는 완료 조건이 아니다.

작성일: 2026-10-03. 상태: 구현 제안 및 검증 계획. 독자: z8를 구현하는 개발자와 코딩 에이전트.

z8는 **루팅하지 않은 Android의 자원으로 실제 개발 프로세스를 실행하고, 프로젝트·터미널·파일·GitHub를 연결하는 네이티브 앱**이다. 폴더블과 태블릿의 넓은 작업 공간을 우선 설계하되, 커버 화면과 분할 화면에서도 작업을 이어갈 수 있어야 한다.

이 문서는 제공된 `android_dev_workspace_spec_v0_1.md`와 추가된 폴더블·Android17·논문 조사 요구를 반영한 설계안이다. 현재 z8은 G0 진단 APK와 Termux PTY 실행 기반을 구현하는 단계다. 구현·검증 현황은 첫 빌드 보고서 (비공개 내부 검증 기록: `reports/compatibility/G0_FIRST_BUILD.md`)를 따른다. 아래 기본값은 별도 표시가 없으면 **제안**이고, 전체 제품 지원 여부와 성능은 G0 측정 전까지 **NOT TESTED**다.

## 1. 제품 범위와 완료 정의

### 1.1 사용자 요구사항

| ID | 요구사항 | 설계에 미치는 영향 |
|---|---|---|
| U01 | 별도 Termux 앱 없이 자체 APK 사용 | Termux 실행 기반을 포함하고 자체 applicationId·bootstrap을 검증 |
| U02 | 루팅 없이 기기 자원 사용 | root·Shizuku·ADB 정책 변경·원격 서버를 실행 전제로 요구하지 않음 |
| U03 | 폴더블·태블릿 우선, RAM 8GB 이상 목표 | 기기 종류 대신 현재 창 크기·힌지·키보드 상태로 배치 결정 |
| U04 | 프로젝트별 Linux 환경 | rootfs·HOME·패키지 설정·임시 파일 분리, 소스는 환경 밖에 보존 |
| U05 | 실제 Claude Code와 Codex를 순차 사용 | 실제 PTY/TUI 제공, 같은 소스 공유, 대화 이력은 별개 |
| U06 | 화면을 나가도 실행·재연결 | 화면 수명과 실행 수명 분리, OS 중단은 정확히 표시 |
| U07 | 파일·Git·GitHub를 편리하게 조작 | 네이티브 탐색·편집·diff·issue·PR·리뷰·체크 UI |
| U08 | 명시적으로 선택하는 SSH 실행 | 생성 시 host 고정, 로컬 장애나 발열 때문에 자동 이동하지 않음 |
| U09 | 논문을 참고해 최적화 | 근거→설계 가설→비교 실험→채택 기준으로 추적 |
| U10 | 권한 요청·의사결정 필요를 훅으로 받아 알림 | Android 알림과 응답 필요 목록, 해당 프로젝트·세션으로 복귀 |

“Orca 같은 느낌”은 프로젝트와 작업 세션을 빠르게 바꾸고 변경 내용을 가까이에서 확인하는 경험으로 정의한다. Orca의 현재 공개 모바일 앱은 데스크톱과 페어링하는 companion으로 설명되어 있다. z8는 그 탐색 흐름을 참고하되 실행 엔진을 독립 Android용으로 만든다. [Orca 원본](https://github.com/stablyai/orca)

### 1.2 최초 세로 기능 구현의 완료 조건

자체 서명 APK를 일반 설치하고, 프로젝트를 생성하여 Claude Code로 파일을 수정·테스트한다. 다른 앱을 다녀오거나 폴드를 접었다 펼친 후 **동일한 살아 있는 세션**에 다시 연결한다. 변경 파일을 확인한 뒤 Claude를 종료하고 Codex로 후속 작업을 수행한다.

`--version` 성공, mock 터미널 화면, 에뮬레이터에서의 앱 실행만으로 이 조건을 통과시키지 않는다. 한 CLI만 성공하면 해당 CLI만 검증 완료로 기록한다.

### 1.3 포함하지 않는 범위

초기에는 VM·QEMU·Docker Engine·systemd 기반 전체 OS, Android 에뮬레이터, 온디바이스 대형 모델 추론, 전체 IDE/LSP, 여러 AI의 병렬 작업 조율, 기기 간 세션 동기화, 자동 원격 실행을 만들지 않는다. Docker/OCI **이미지를 읽는 기능**과 Docker daemon/Compose 호환은 별개다.

## 2. 기기와 빌드 호환성

| 항목 | 제안 및 상태 |
|---|---|
| 주 실기기 | 사용자 보고: Galaxy Fold z8, Android 17, RAM 약 12GB. 모델 코드·빌드 지문·실제 RAM은 진단으로 확인 |
| 자원 목표 | ARM64, RAM 8GB 이상. 8GB 기준 소규모 Node/Python 프로젝트, AI 1개 + Shell + 가벼운 dev server를 시험 |
| 화면 목표 | 커버 화면, 펼친 화면, 태블릿, 멀티윈도우, 가변 창, 외장 키보드 |
| 지원 OS | Android 17 우선 검증. Android 16은 후속 비교 대상. 그 외는 지원을 선포하지 않음 |
| Linux 기준 환경 | Ubuntu 24.04 ARM64 이미지 후보. tag만 기록하지 않고 실제 digest/아카이브 hash를 고정 |
| 저장소 | 내부 앱 데이터. 초기 설치·재생성 전 다운로드 + 압축 해제 크기 + 임시 공간 + 여유량을 계산해 표시 |
| 배포 | 개인용 sideload APK. Play 배포는 별도의 targetSdk·정책·라이선스 검토 과제 |
| SDK | G0에서 min/target/compile 세트를 함께 고정. upstream의 legacy target 빌드를 출발 후보로 하며 API 37 대응을 별도 검사 |
| 앱 ID | `dev.devsigner.z8`를 임시 후보로 사용. bootstrap 제작 전에 고정하고 이후 변경은 데이터 이동 프로젝트로 취급 |
| native page size | 실제 4KB/16KB 값을 기록하고 JNI·host ELF·PRoot·guest loader/libc·Node/Python·AI CLI 전체를 프로필별 검증 |

Android 10부터 target API 29 이상 앱의 쓰기 가능한 앱 홈에서 `exec()` 실행에 제약이 생겼다. 따라서 최신 targetSdk를 적기만 해서는 Termux형 패키지 실행이 성립하지 않는다. 낮은 target을 쓰더라도 새 OS의 설치 제한·공통 동작 변경을 피할 수 있다는 뜻은 아니다. **Android 17 기본 설정에서 일반 APK 설치와 자식 프로세스 실행이 가능한 SDK 조합을 찾는 것이 G0의 첫 관문**이다. 정책 우회 ADB가 필요한 조합은 제품 합격으로 처리하지 않는다. [Android 실행 제약](https://developer.android.com/about/versions/10/behavior-changes-10#execute-permission), [Termux 실행 환경](https://github.com/termux/termux-packages/wiki/Termux-execution-environment)

Android 17 공식 문서는 targetSdk와 무관한 RAM 기반 앱 메모리 제한을 설명한다. 따라서 12GB 기기라도 앱이 모든 RAM을 사용할 수 있다고 가정하지 않는다. `ApplicationExitInfo`에서 제공되는 종료 이유와 `MemoryLimiter:AnonSwap` 설명을 진단에 수집하되, 자식 Linux 프로세스의 종료 원인까지 항상 알아낼 수 있다고 보장하지 않는다. [Android 17 변경 사항](https://developer.android.com/about/versions/17/behavior-changes-all)

16KB 검증은 APK의 JNI 정렬 확인에서 끝나지 않는다. 다운로드한 host/guest ELF의 실행까지 통과해야 한다. Android의 일부 4KB 앱 호환 모드가 모든 guest 바이너리 문제를 해결한다고 가정하지 않는다. [페이지 크기 공식 안내](https://developer.android.com/guide/practices/page-sizes)

## 3. 전체 실행 구조

```text
Compose UI
  프로젝트 / 세션 / 파일·편집 / Git·GitHub / 환경·진단
        │ 명시적 사용자 작업, 상태 구독
WorkspaceCoordinator ─ Room 메타데이터 / 설정 / 인증 참조
        │
ExecutionService (Termux 서비스 기반 foreground 실행 관리)
        ├─ LocalEngine
        │    ├─ host runtime: PTY, tmux, proot, proot-distro
        │    ├─ 프로젝트 A tmux server → pane → PRoot A → CLI/Shell
        │    └─ 프로젝트 B tmux server → pane → PRoot B → CLI/Shell
        └─ RemoteEngine → OpenSSH → 원격 tmux → 원격 프로젝트

네이티브 FileRepository → 앱 내부 프로젝트 소스
GitRepository → 해당 프로젝트 환경의 git
GitHubRepository → 인증 범위가 정해진 gh 명령
```

### 3.1 실행 경계

- Android 호스트: Bionic 계열 Termux 실행 패키지, PTY·tmux·PRoot·환경 설치 도구.
- Linux 게스트: 해당 rootfs의 glibc 계열 도구, Git·gh·Node·Python·AI CLI·프로젝트 패키지.
- UI: 내부 소스 파일을 Android 파일 API로 직접 읽는다. 폴더 클릭마다 PRoot나 셸을 새로 띄우지 않는다.
- 네트워크: 모든 로컬 환경은 Android 커널의 네트워크를 사용한다. 환경별 독립 IP·포트 공간을 가정하지 않는다.

PRoot는 비루팅 환경에서 경로·사용자 ID 동작을 흉내 내지만 보안 VM이나 별도 Linux 커널을 제공하지 않는다. 프로젝트 간 기본 바인딩을 막는 것은 실수와 설정 간섭을 줄이는 정책이다. 같은 Android UID의 악성 코드에 대해 키·파일의 접근 차단을 보장하지 않는다. [PRoot-Distro 구조와 제한](https://github.com/termux/proot-distro)

### 3.2 tmux 배치 결정

**활성 로컬 프로젝트당 host tmux server 하나**, UI 세션당 tmux session 하나·pane 하나를 기본안으로 한다. tmux를 PRoot 바깥에 두어 터미널 재연결과 프로젝트 환경 프로세스 상태를 따로 관찰한다. 여러 프로젝트의 tmux 전역 환경변수·종료 범위가 섞이지 않게 별도 socket을 사용한다.

socket은 앱 내부 짧은 경로에 두고, 이름에 사용자 프로젝트명을 직접 넣지 않는다. 서버는 살아 있는 세션이 있을 때만 유지한다. G0에서 단일 공용 서버 및 guest tmux와 비교해 메모리·재연결·신호 전달 비용을 측정한 뒤 ADR로 확정한다. 서버 분리는 보안 경계가 아니다.

초기 UI는 임의 tmux 레이아웃 편집을 관리하지 않는다. CLI에서 직접 tmux 구조를 바꾼 경우 locator를 재조회하고 불일치를 표시한다. 선택적 화면 분할은 서로 다른 UI 세션을 배치하는 방식이다. tmux가 보존하는 것은 살아 있는 서버 안의 작업이며, 서버가 죽은 뒤 프로세스 메모리를 복원하는 기능은 아니다. [tmux 모델](https://github.com/tmux/tmux/wiki/Getting-Started)

### 3.3 Termux 포크와 런타임 공급

Termux의 PTY/JNI, emulator, terminal view, 세션·서비스 코드를 먼저 유지한다. Compose는 기존 View를 `AndroidView`로 감싼다. G0에서 수명주기 어댑터를 검증한 후 프로젝트 도메인을 추가한다. 실행 코어 전체 재작성은 첫 과제가 아니다.

앱 ID 변경에는 bootstrap과 host 패키지의 고정 prefix 재빌드가 따라온다. 공식 `com.termux`용 패키지 저장소를 자체 prefix와 무조건 혼용하지 않는다. 초기에는 필요한 host 패키지 묶음과 의존성 폐쇄를 빌드 산출물로 제공하고, 사용자가 설치하는 개발 패키지는 주로 guest의 apt/npm/pip를 사용한다. [Termux 빌드 안내](https://github.com/termux/termux-app), [prefix 구조](https://github.com/termux/termux-packages/wiki/Termux-execution-environment)

고정할 산출물은 upstream commit, patch 목록, NDK/SDK/Gradle 버전, ABI, prefix, bootstrap hash, host 패키지와 license, rootfs digest, guest 도구 버전이다. 다운로드 hash는 신뢰할 수 있는 manifest에서 받아야 한다. 같은 비신뢰 응답에 있는 파일과 hash만 맞춘 것은 출처 검증이 아니다.

host bootstrap은 컴파일된 최종 prefix에서 실행해야 한다. 임시 디렉터리에서 실행 검증 후 단순 이동할 수 있다고 가정하지 않는다. 다운로드·해제 검사 후 설치 잠금과 journal을 사용해 최종 경로를 구성하고, 최종 경로 smoke test가 끝나기 전에는 READY로 바꾸지 않는다. runtime 업데이트 시 새 작업 진입을 막고 활성 세션·Operation을 종료/취소한 뒤 lease가 해제됐는지 확인한다. 무중단 교체는 초기 범위에서 제외한다.

현재 PRoot-Distro upstream은 Python 기반 OCI 이미지·컨테이너 관리 흐름을 제공한다. 예전 셸 스크립트 구조나 옵션을 고정 사실로 사용하지 않는다. `DistroAdapter`가 실제 채택 버전의 설치·진입·삭제·바인딩·storage root 옵션을 캡슐화하고, `--help`와 실제 생성 argv를 계약 테스트한다. OCI cache는 공유할 수 있어도 **쓰기 가능한 rootfs와 HOME은 공유하지 않는다**. [현재 upstream](https://github.com/termux/proot-distro)

## 4. 폴더블과 태블릿 UI

### 4.1 정보 구조

시작 화면은 최근 프로젝트와 실행 중 세션이다. 프로젝트를 열면 마지막 보던 터미널로 돌아간다. 상단에는 프로젝트명·브랜치·`LOCAL · 이 기기` 또는 `REMOTE · 별칭`·세션 상태를 항상 표시한다. 환경 이미지 목록은 프로젝트 설정 안에 둔다.

핵심 화면은 프로젝트 목록, 작업 화면, 변경 사항, GitHub, 환경·진단의 다섯 가지다. 작업 화면의 주 콘텐츠는 실제 터미널이며 파일 편집기는 같은 프로젝트 문맥에서 열린다.

첫 사용 흐름에는 터미널 테마 선택을 넣는다. 배경·글자·ANSI 색상의 샘플 출력을 미리 보여주고, 선택을 명시적으로 적용한 뒤 저장한다. 기본 테마가 선택된 상태라 그대로 시작할 수도 있다. 이후 설정에서 다시 바꿀 수 있으며 미리보기 취소는 기존 선택을 보존한다. G0에는 Midnight·Graphite·Ember·Paper를 제공한다. 테마 변경·설정 화면 이동은 기존 PTY를 다시 만들거나 작업을 재실행하지 않는다. 선택 중 회전·창 크기 변경과 앱 재시작 후 저장된 테마 복원도 확인한다.

새 대화형 셸 세션에는 테마 색을 사용한 `Welcome to Z8 Terminal`과 간단한 명령 안내를 표시한다. 세션 재연결·회전·중첩 셸에서는 반복하지 않고, 비대화형 명령의 stdout에는 넣지 않는다. 안내는 실제 실행 환경을 표현하며 Linux·AI CLI 준비 상태를 과장하지 않는다.

### 4.2 가용 창 크기별 배치

| 조건 | 기본 배치 | 열 수 있는 보조 화면 |
|---|---|---|
| 너비 < 600dp | 터미널 한 화면, 프로젝트·파일은 sheet/drawer | 편집기·GitHub는 화면 전환 |
| 600 ≤ 너비 < 840dp | 터미널 우선 + 접을 수 있는 탐색 rail/panel | 파일과 터미널을 두 영역으로 전환하되 최소 작업 폭 확보 |
| 840 ≤ 너비 < 1200dp | 240~280dp 탐색 + 주 작업 영역 | 편집기/터미널 분할은 각 영역 가용 폭을 확인한 후 제공 |
| 너비 ≥ 1200dp | 탐색 + 편집기 + 터미널의 세 영역 가능 | 보조 Git/diff 패널은 사용자 선택 시 표시 |
| 높이 < 480dp 또는 IME로 높이 부족 | 탐색·보조 영역을 접고 입력 중 영역 확대 | 입력 포커스와 문서 상태 보존 |

600/840/1200dp는 Android 공식 창 크기 분류를 참조한다. 세부 panel 폭과 최소 편집 폭 360dp는 z8 제안값이며 사용자 글꼴 확대·IME를 포함해 조정한다. 펼친 폴드가 언제나 세 영역을 띄울 수 있다고 가정하지 않는다. [창 크기 분류](https://developer.android.com/develop/ui/compose/layouts/adaptive/use-window-size-classes)

```text
넓은 창 예시
┌ 프로젝트 · branch · LOCAL ─── 세션 + ─── 실행 상태 ┐
│ 프로젝트 / 파일 │ 편집기 또는 diff │ Claude 터미널 │
│                 │                 │ Shell / Dev   │
└───────────────────────────────────────────────────┘
좁은 창: 같은 세션을 전체 화면으로 표시하고 파일·diff는 전환
```

`WindowSizeClass`와 `WindowLayoutInfo`를 구독한다. `FoldingFeature.isSeparating` 또는 힌지 가림이 있을 때 pane 경계를 그 영역에 맞춘다. 단순히 접힌 자국이 있다는 이유로 항상 화면을 나누지 않는다. tabletop은 위쪽 터미널·아래쪽 입력 보조를 선택적으로 제공하며 키보드 영역과 경쟁하면 한 영역으로 축소한다. [fold-aware 공식 안내](https://developer.android.com/develop/ui/compose/layouts/adaptive/foldables/make-your-app-fold-aware)

### 4.3 크기 변경과 입력 계약

- 접기·펼치기·회전·멀티윈도우는 레이아웃과 PTY rows/columns만 바꾼다. 새 CLI 프로세스를 만들지 않는다.
- terminal session ID, 선택 파일, draft, 커서·스크롤, split 비율, 포커스를 보존한다. 활성 입력 중 한글 조합 문자열이 중복 전송되지 않아야 한다.
- Ctrl/Alt/Esc/Tab/방향키 보조 행은 기본으로 숨긴다. 사용자가 원할 때 터미널에서만 켤 수 있게 하며 시스템 키보드와 외장 키보드 입력은 유지한다. 선택 상태의 Ctrl+C 복사와 Ctrl+C SIGINT는 별도 동작으로 구분한다.
- 최소 터치 목표 48dp, 글자 크기 설정, TalkBack 이름과 상태 텍스트를 제공한다. 색만으로 LOCAL/REMOTE·중단·충돌을 구분하지 않는다.
- 여러 줄 붙여넣기는 미리보기 후 사용자가 전송한다. bracketed paste 지원을 시험하며 UI가 마지막 Enter를 임의 추가하지 않는다.
- 파일 트리 탐색은 터미널 입력을 발생시키지 않는다. “여기서 새 터미널”만 cwd를 지정해 새 세션을 만든다.

## 5. 저장 구조와 데이터 모델

### 5.1 논리 저장 구조

다음은 앱 관리 경로의 설계이며 PRoot-Distro의 실제 내부 디렉터리 구조를 단정한 것이 아니다. adapter가 실제 경로를 해석한다.

```text
app-private/
  files/usr/                       # 빌드 prefix와 일치하는 host runtime
  files/z8/projects/<workspaceId>/source/
  files/z8/environments/<envId>/    # guest rootfs 또는 adapter locator
  files/z8/homes/<envId>/            # 프로젝트 전용 HOME
  files/z8/tmp/<envId>/
  files/z8/run/<short-id>/          # socket/launch manifest; 짧은 경로
  files/z8/drafts/<workspaceId>/    # Git 밖의 편집 복구본
  files/z8/trash/<workspaceId>/     # 앱에서 삭제한 파일의 복구 영역
  files/z8/auth/                    # vault 암호문, CLI HOME과 별개
  cache/z8/images/                  # 재다운로드 가능한 이미지 cache
  databases/z8.db                   # 상태 메타데이터; 비밀값 원문 금지
```

guest에는 `source → /workspace`, 프로젝트 전용 HOME → `/z8/home`, 전용 tmp → `/tmp`를 매핑한다. 일반 새 셸의 `HOME`과 기본 작업 디렉터리는 `/z8/home`이다. 프로젝트 도구 실행이나 “여기서 새 터미널 열기”는 사용자가 고른 시작 디렉터리를 명시하며, 실행 중인 셸에 `cd`를 자동 입력하지 않는다. 환경마다 `/z8/home`의 실제 저장 디렉터리는 다르고, 환경 재생성 시 HOME·인증 보존 정책을 따른다. 실제 Linux UID 분리를 의미하지 않는다. 전체 Android HOME·공유 저장소·다른 프로젝트·host tmux socket은 기본 guest bind에 넣지 않는다. PRoot의 기본 `/proc`, `/dev`, 네트워크·DNS 관련 노출은 채택 버전의 실제 argv에서 검사한다.

`/z8/home`은 PRoot가 매핑하는 guest 경로이며 Android 시스템 루트에 만드는 디렉터리가 아니다. 현재 진단 셸은 앱 내부의 실제 `files/home`을 사용하고 `pwd`를 위장하지 않는다. `ll`, `la`, `l`, `..`, `...`, `mkcd`는 기본 셸 편의 기능으로 제공한다. Git·검색·압축·네트워크·편집 도구의 guest 기본 패키지와 설치 입력은 `runtime/guest/`에서 관리하며, 패키지 설치·실행까지 성공해야 해당 환경을 준비 완료로 표시한다.

SAF로 선택한 외부 폴더는 초기 버전에서 **가져오기/내보내기** 대상으로 다룬다. SAF URI를 POSIX 경로라고 가정하거나 rootfs·node_modules를 공유 저장소에서 실행하지 않는다. 기본 UI가 다루는 파일 범위는 `/workspace`다.

### 5.2 엔터티

| 모델 | 필수 필드 | 불변 조건 |
|---|---|---|
| HostProfile | id, LOCAL/SSH, alias, endpoint, hostKeyRef, credentialRef | LOCAL은 기기 자체, 비밀값 원문 없음 |
| Workspace | id, hostId, sourceLocator, environmentId, displayName, defaultCwd, lastOpenedAt | source 실제 경로가 이름 변경에 영향받지 않음 |
| Environment | id, generation, distroDigest, rootfsLocator, homeLocator, state, toolManifest | 재생성 시 generation 증가, source 경로 별개 |
| Session | id, workspaceId, hostId, envGeneration, toolKind, launchSpecRef, tmuxLocator, launchId | host 변경 불가, 하나의 launch attempt와 연결 |
| ProcessObservation | bootIdentity, pid/startTime(가능할 때), tmuxServer/pane ID, observedAt, exitEvidence | PID만으로 재연결하지 않음 |
| Operation | id, workspaceId, kind, state, startedAt, resultRef, externalResultId | 쓰기 요청 중복 클릭·전송 재시도 관리 |
| AttentionItem | id, workspaceId, sessionId, launchId, providerSessionId, turnId?, requestId?, kind, sourceEvent, observedAt, state, deliveryState | 알림을 읽은 상태와 CLI 요청 해결 상태는 별개 |
| FileRevision | pathToken, size, mtime, inode(가능할 때), contentHash | mtime만으로 변경 여부를 확정하지 않음 |
| CapabilityReport | device/build/pageSize, runtime/toolVersion, capability, result, evidenceRef, checkedAt | 버전 변경 후 검증 결과를 새 버전으로 승계하지 않음 |

branch·Git status는 표시 cache이며 Git 저장소가 원본이다. session DB의 RUNNING 값도 관측 cache이지 프로세스 생존 증거가 아니다.

Environment 상태는 `ABSENT / DOWNLOADING / VERIFYING / EXTRACTING / CONFIGURING / READY / MAINTENANCE / FAILED`로 관리한다. 실패에는 마지막 성공 단계·재시도 가능 여부·정리 대상 경로를 남긴다. Operation은 `QUEUED / RUNNING / CANCEL_REQUESTED / SUCCEEDED / FAILED / UNKNOWN`으로 관리하고, 외부 쓰기의 결과가 불명확하면 실패로 단정해 자동 재실행하지 않는다.

### 5.3 삭제와 재생성

| 사용자 동작 | 소스 | 환경·HOME | 세션 |
|---|---|---|---|
| 목록에서 숨기기 | 유지 | 유지 | 유지 여부를 표시 |
| 환경 재생성 | 항상 유지 | 새 rootfs, 새 HOME 기본. 기존 HOME 이관은 파일 범위 선택 | 먼저 종료, 자동 명령 재실행 없음 |
| 환경만 삭제 | 유지 | 제거 | 종료 필수 |
| 프로젝트 삭제 | source 삭제를 별도 확인 | 환경 삭제 범위 별도 확인 | 종료 필수 |
| 앱 제거/데이터 지우기 | Android 내부 데이터와 함께 사라질 수 있음 | 동일 | 모두 중단 |

재생성은 새 환경을 검증한 후 environment 참조를 교체한다. 구 환경을 동시에 유지할 디스크 공간이 없으면 중단하고 정리 선택을 제시한다. source와 구 HOME을 무심코 새 이미지 안으로 덮어쓰지 않는다. 기본 backup은 코드·선택 설정 중심이며 인증 파일·SSH key·`.env` 제외 목록과 실제 포함 파일 미리보기를 제공한다. Android 자동 백업에서도 rootfs·인증·runtime를 제외한다.

환경 삭제·재생성은 해당 workspace를 MAINTENANCE로 전환해 새 session/runTask 진입을 막는다. 터미널뿐 아니라 clone·Git·설치 등 활성 Operation의 종료/취소를 확인하고 lease가 모두 해제된 뒤 rootfs/HOME을 바꾼다. 취소 요청이 완료됐다는 관측 없이 파일을 삭제하지 않는다.

## 6. 실행 API와 세션 상태

### 6.1 도메인 계약

```kotlin
// 인터페이스 설계 예시. 구현 코드 또는 확정 SDK API가 아니다.
data class LaunchSpec(
    val workspaceId: String,
    val hostId: String,
    val environmentGeneration: Long,
    val executable: String,
    val arguments: List<String>,
    val workingDirectory: GuestPath,
    val environmentProfileId: String,
    val terminalSize: TerminalSize
)

interface ExecutionEngine {
    suspend fun probe(): CapabilityReport
    suspend fun create(spec: LaunchSpec, requestId: String): SessionId
    suspend fun attach(id: SessionId): TerminalConnection
    suspend fun detach(id: SessionId)
    suspend fun inspect(id: SessionId): SessionObservation
    suspend fun interrupt(id: SessionId) // Ctrl+C에 해당하는 중단 요청
    suspend fun terminate(id: SessionId): StopResult
    suspend fun runTask(spec: TaskSpec, requestId: String): TaskHandle
}

interface WorkspaceFiles {
    suspend fun list(directory: WorkspacePath, cursor: String?): FilePage
    suspend fun read(path: WorkspacePath, limitBytes: Long): FileSnapshot
    suspend fun save(path: WorkspacePath, expected: FileRevision, bytes: ByteArray): SaveResult
}
```

도메인에서는 `WorkspacePath`, `GuestPath`, `HostPath`, `RemotePath`를 구분한다. 사용자 문자열을 셸 코드에 연결하지 않는다. PTY 실행과 구조화 명령 실행을 분리하고 argv를 보존한다. tmux/SSH 경계에서 셸 문자열이 불가피하면 고정 launcher와 생성된 opaque ID/manifest를 사용하고 escaping을 검증한다. 암호는 argv·URL·launch manifest에 기록하지 않는다.

`TaskSpec`에는 argv/cwd/환경 참조 외에 deadline, stdout/stderr 저장 한도, read/write 구분과 취소 정책을 넣는다. interactive session에 일괄 timeout을 적용하지 않는다. 오류 코드는 `ENV_NOT_READY`, `TOOL_UNSUPPORTED`, `AUTH_REQUIRED`, `CONNECTION_LOST`, `FILE_CONFLICT`, `DISK_FULL`, `PROCESS_INTERRUPTED`, `RESULT_UNKNOWN` 등으로 정규화하되 원래 exit code와 redacted 진단도 보존한다.

### 6.2 상태를 별도 축으로 보관

```text
process:   NEW → STARTING → RUNNING → EXITED
                          ↘ INTERRUPTED / UNKNOWN
view:      ATTACHED / DETACHED
transport: LOCAL / CONNECTING / CONNECTED / DISCONNECTED
agent:     UNKNOWN / WORKING / NEEDS_INPUT / TURN_COMPLETE
```

`agent`는 검증된 CLI 이벤트가 있을 때만 판정한다. 출력이 없는 시간·CPU 사용률·프롬프트 색상만으로 완료라고 표시하지 않는다. 연결 실패는 프로세스 종료와 다르다. 남아 있는 tmux pane도 그 안의 CLI 생존과 다르다.

세션 생성은 DB에 requestId와 STARTING을 기록 → 동일 ID locator 조회 → tmux/PRoot 시작 → 자식·pane 확인 → RUNNING 기록 순이다. 시작 도중 앱이 죽으면 다음 실행에서 기존 locator와 launchId를 조정해 중복 실행을 막는다. 종료 코드는 신뢰 가능한 종료 이벤트/launcher 결과가 있을 때만 표시한다.

### 6.3 화면 종료와 작업 종료

| 이벤트 | 동작 |
|---|---|
| 뒤로 가기·다른 프로젝트 선택 | UI detach. CLI 유지 |
| 회전·접힘·Activity 재생성 | 같은 session에 attach, PTY resize |
| Ctrl+C | 현재 foreground 작업에 interrupt, 터미널은 유지될 수 있음 |
| 세션 종료 버튼 | 대상 확인 → 종료 요청 → 종료 관측. 남은 자식 있으면 결과를 표시 |
| 앱 프로세스 재시작 | 살아 있는 socket/pane을 먼저 조회. 확인 불가 시 UNKNOWN, 소실 시 INTERRUPTED |
| OS 강제 종료·사용자 FGS 중지·재부팅 | 자동 AI/Git 명령 재시작 없음. 앱 수동 진입 시 중단 상태 표시 |
| Remote 연결 끊김 | DISCONNECTED, 원격 실행 여부 UNKNOWN. 재접속 후 확인 |

종료는 검증된 프로세스 그룹/세션 범위에 한정한다. PID 재사용을 검증하지 않은 `kill`이나 공용 `kill-server`를 쓰지 않는다. PRoot 하위 프로세스 정리가 안 되면 전체 프로젝트 종료 선택과 진단을 제공한다. 재연결 실패를 숨기려고 새 셸을 기존 세션처럼 표시하지 않는다.

## 7. 기능별 구현 계약

| ID | 기능 | 구현 계약과 완료 기준 | 단계 |
|---|---|---|---|
| F01 | 첫 실행·설치 | 기기 진단, 용량 추정, 다운로드/검증/해제/초기화 진행, 실패 재시도, 부분 설치 READY 금지 | G0→G1 |
| F02 | 프로젝트 | 빈 프로젝트·clone·내부 프로젝트 열기·최근 목록. 생성 취소/재시도 시 중복 rootfs·clone 방지 | G1 |
| F03 | 환경 | 전용 rootfs/HOME/tmp, 환경변수 allowlist, generation, source를 보존하는 재생성 | G0→G1 |
| F04 | CLI | 설치·버전·로그인·파일/셸/테스트·resume를 별도 검사. CLI별 capability 표시 | G0→G1 |
| F05 | 터미널 | 세션 이름/전환/검색/복사, 실 PTY, 키보드·IME·resize, 분리된 종료 동작 | G1 |
| F06 | 재연결 | 화면 수명과 분리, locator 조정, 중단 인식, 위험 명령 자동 재실행 금지 | G0→G1 |
| F07 | 실행 유지 | FGS 상태·실행 알림, keep-awake 정책, 자원 사용·중단 이유 표시 | G0→G1 |
| F08 | 파일·편집 | 지연 트리/검색/CRUD, Sora, 충돌 확인, draft·복구본, cwd 주입 없음 | G1 |
| F09 | Git·GitHub | 아래 전체 기능 표 구현. CLI 결과와 UI 일치, 쓰기 대상 검토 | G1→G2 |
| F10 | SSH | host 선택, 호스트 키 검증, remote tmux/SFTP, 로컬과 별도 인증 | G3 |
| F11 | 진단·설정 | 호환성 보고, font/theme, 버전·저장량·오류, 비밀값 제외 내보내기 | G0→G2 |
| F12 | 선택 기능 | localhost 웹 미리보기, 지원 CLI 첨부 | G4 |
| F13 | 훅·응답 필요 알림 | 권한 요청/질문/계획 검토 이벤트 수신, 알림·앱 내 목록, 정확한 세션 복귀. 도구·버전별 감지 범위 표시 | G0 조사→G1 필수, 원격 G3 |

### 7.1 AI 도구

ToolAdapter별로 install/version/login/launch/resume/events/attachments/sandbox 정보를 관리한다. 공식 설치 경로와 로그인 흐름을 사용하며 앱이 계정·구독을 대신하지 않는다. Codex device code는 계정/조직에서 제공되는 경우만 선택한다. 브라우저 callback, loopback, 앱 복귀와 만료된 code를 실제 기기에서 시험한다. [Codex CLI](https://learn.chatgpt.com/docs/codex/cli), [인증](https://learn.chatgpt.com/docs/auth), [Claude 설치](https://code.claude.com/docs/en/setup)

events는 단일 boolean 대신 `permissionRequested`, `userQuestion`, `planReview`, `requestResolved`, `turnCompleted`로 나눈다. 각 capability에 toolVersion·관측 근거·지원 모드·제한을 기록한다. 상세 알림 계약은 F13을 따른다.

도구 상태는 `미설치 / 설치됨 / 로그인 필요 / 일부 기능 검증 / 실제 작업 검증 / 호환 오류`로 구분한다. “검증됨”에는 도구 버전·기기/OS·확인한 기능을 붙인다. 업데이트가 감지되면 이전 검증을 과거 기록으로 남기고 다시 검사한다.

Claude→Codex 전환 시 기존 도구 종료 또는 사용자가 명시적으로 전환하는 흐름을 제공한다. 같은 프로젝트에서 앱이 관리하는 AI가 살아 있으면 중복 쓰기 가능성을 알린다. 일반 셸에서 사용자가 실행한 모든 AI를 완벽하게 찾아낸다고 보장하지 않는다. 선택적 인계 메모는 작업 요약·변경 파일·실행 테스트·남은 문제를 사용자가 검토한 뒤 전달한다.

CLI 내장 sandbox는 독립 검증한다. Claude Linux sandbox의 bubblewrap/socat 의존성이 설치되어 있어도 Android 커널 기능을 사용할 수 있다는 뜻은 아니다. 실패 시 자동으로 무승인 옵션을 넣지 않는다. 정상 승인 흐름이 가능한 제한 모드가 있다면 기능과 제한을 분명히 표시하고 사용자가 선택한 설정으로만 실행한다. 안전한 기본 실행을 구성할 수 없는 도구/버전은 미지원으로 남긴다. [Claude sandbox](https://code.claude.com/docs/en/sandboxing)

### 7.2 파일 편집과 경쟁 쓰기

텍스트 편집의 제안 기본 한도는 2MiB 또는 50,000줄 중 먼저 초과하는 값이다. 초과하면 제한 미리보기/외부 CLI 편집 안내를 제공한다. 바이너리·특이 인코딩·매우 긴 단일 행은 별도 판정한다. UTF-8, CRLF/LF, 실행 비트와 저장 전 마지막 개행을 보존한다.

저장은 읽을 때 revision 수집 → 현재 내용/hash 재확인 → 불일치 시 내 draft/디스크 내용/차이 보기 → 일치하면 복구 snapshot 생성 및 같은 디렉터리 임시 파일 write·fsync·rename 순으로 설계한다. 앱 내부 저장은 직렬화하고 file watcher는 조기 알림으로만 사용한다. watcher 누락/overflow 시 다시 읽는다.

**임의 CLI 작성자와 POSIX 파일 저장 사이에 완전한 compare-and-swap을 보장할 수 없다.** 해시 검사 직후에도 AI가 쓸 수 있다. 이 잔여 경쟁을 숨기지 않고 내 draft·직전 디스크 복구본을 유지하며, 충돌 반복 시 AI 작업을 멈춘 뒤 병합하게 한다. 무조건 덮어쓰기 선택은 대상과 결과를 보여준 뒤 실행한다.

symlink는 원래 링크와 대상 경로를 구분한다. 프로젝트 밖이나 guest 절대 경로를 Android host 절대 경로로 잘못 해석하지 않는다. 초기에는 범위 밖 링크를 표시하고 편집을 막는다. hardlink·symlink 대상 저장 정책은 검증 전 읽기 전용으로 취급한다. 경로 이탈·개행·따옴표·한글 파일명 시험을 포함한다.

### 7.3 Git과 GitHub

Git은 guest 환경에서 실행해 CLI와 설정·hooks·파일 권한 해석을 맞춘다. UI 명령은 별도 비대화형 command channel로 실행하며 사용자의 실행 중 터미널에 명령을 입력하지 않는다. Git status는 `--porcelain=v2 -z`, 경로 목록은 NUL 구분 등 기계 판독 형식을 사용한다. 큰 diff는 파일 단위·페이지 단위로 읽고 binary 변경은 텍스트처럼 표시하지 않는다.

| 흐름 | UI 및 명령 결과 계약 |
|---|---|
| 로그인·저장소 찾기·clone | 계정/host/대상/로컬 위치 표시. clone 완료 후 Git repository 확인 |
| 변경·stage·unstage | Git 최신 상태를 다시 읽고 선택 경로만 처리. 큰 파일·untracked 표시 |
| commit | staged diff, 메시지, 사용자 identity 확인. hook 실패·서명 요구를 그대로 보고 |
| branch 생성·전환 | 현재 변경과 대상 branch 확인. 자동 stash/discard 없음 |
| fetch·pull·push | target remote/branch 표시. pull은 우선 fast-forward only. 충돌·divergence는 선택 안내 |
| issue에서 작업 시작 | issue 번호/본문 링크, 저장소, 새 branch, 검토 가능한 초기 프롬프트 |
| PR 생성·조회 | base/head/title/body 미리보기. 제출 결과 URL/번호 기록 |
| PR 리뷰 | 현재 head SHA에 고정한 diff, 줄 위치/side 검증, 본문·approve/request-changes/ comment 선택 후 제출 |
| checks·Actions | 실행 ID·job·결과·최신 갱신 시각, 필요한 로그만 조회. stale/offline 구분 |

구조화 결과는 `gh --json`/`gh api`를 사용하고 JSON schema·pagination·rate limit·취소를 처리한다. PR/리뷰 전송 후 응답이 끊기면 재전송 전에 서버 결과를 조회한다. 임의의 모든 GitHub API가 idempotency key를 지원한다고 가정하지 않는다. force push·merge·브랜치 삭제·변경 폐기는 기본 흐름 밖의 명시적 동작이다. [gh 구조화 출력](https://cli.github.com/manual/gh_help_formatting)

workspace별 UI Git 쓰기를 직렬화한다. CLI가 동시에 Git을 실행할 수 있으므로 `.git/index.lock` 등 실제 Git 잠금을 존중하고 임의 삭제하지 않는다. 작업 후 상태를 다시 읽고 캐시를 무효화한다. PR head가 바뀌면 예전 diff line으로 리뷰를 전송하지 않는다.

### 7.4 인증 경계

앱 GitHub 계정은 프로젝트별 사용 동의를 거쳐 필요한 gh/Git 동작에만 전달한다. 모든 guest 셸의 전역 환경변수에 토큰을 넣지 않는다. Git credential helper는 검증한 HTTPS host/계정 범위에만 응답하도록 설계하고, credential 전달 시 hook/자식 프로세스에 노출될 수 있는 한계를 기록한다.

앱 보관 토큰은 Keystore 보호 키로 암호화한 vault를 사용한다. gh 로그인은 전용 임시 config 영역에서 수행하고 plaintext fallback 여부를 탐지한다. vault 이관 구현·검증 전에는 평문 CLI 저장을 암호화 보관으로 표시하지 않는다. CLI HOME의 Claude/Codex 인증 파일은 앱 vault와 별도이며 해당 프로젝트 환경의 private 파일로 관리한다. [gh 로그인 저장 방식](https://cli.github.com/manual/gh_auth_login), [Keystore](https://developer.android.com/privacy-and-security/keystore)

진단 로그·터미널 내보내기는 기본 꺼짐이다. 명령 출력에는 임의 비밀값이 포함될 수 있으므로 redaction만으로 완전 제거를 보장하지 않는다. 사용자가 내보낼 파일을 미리 검토하게 한다. SSH key와 known_hosts, 원격 AI 인증은 로컬 계정에서 자동 복제하지 않는다.

### 7.5 리모트와 선택 기능

로컬 프로젝트에서 SSH를 고르면 원격 경로를 가진 **새 remote workspace/session**을 생성한다. 기존 세션의 hostId는 변경하지 않는다. 원격 tmux 없는 연결은 비지속형임을 표시한다. 원격 파일은 SFTP로 접근하고 저장 경쟁의 한계는 로컬과 동일하게 다룬다.

웹 미리보기는 loopback dev server URL을 명시적으로 연다. Android WebView를 쓰면 JS bridge는 제공하지 않고 localhost 접근 정책·외부 탐색을 분리한다. 원격은 명시적 SSH tunnel이며 외부 네트워크 노출은 기본 꺼짐이다. 파일·이미지 첨부는 source 안에 복사한 경로를 검증된 CLI 입력 방식으로 전달하며 이미지 지원을 추정하지 않는다.

### 7.6 F13 훅 기반 권한 요청과 의사결정 알림

사용자가 다른 앱을 쓰거나 화면을 꺼둔 동안 CLI가 권한·답변·계획 검토를 요구하면 Android 알림으로 알린다. 프로젝트 목록에는 응답 필요 개수를, 작업 화면에는 요청 목록을 제공한다. 이 기능은 후순위 편의 기능에서 **G1 필수 기능**으로 올린다. 초기 구현은 **알림 → 해당 세션 열기 → 원래 CLI에서 확인·답변**이다.

#### 이벤트와 사용자 경험

| 정규화 이벤트 | 예시 | 표시와 기본 동작 |
|---|---|---|
| PERMISSION_REQUESTED | 셸 실행·쓰기·네트워크 권한 요청 | “권한 확인이 필요합니다”, 세션 열기 |
| USER_INPUT_REQUESTED | 선택지·추가 질문·MCP 입력 요청 | “답변이 필요합니다”, 질문이 있는 세션 열기 |
| PLAN_REVIEW_REQUESTED | 구현 계획 검토·진행 판단 | “계획 검토가 필요합니다”, 해당 세션 열기 |
| TURN_COMPLETED | CLI가 이번 응답을 마침 | 완료 알림 설정을 켠 경우만 표시. 전체 개발 작업 성공과 구분 |
| SESSION_INTERRUPTED | 프로세스 종료·실행 중단 | 세션 중단 및 확인 가능한 이유 표시 |

알림은 요청이 발생했다는 사실을 전달한다. pre-event만 있고 현재 대기 여부를 확인할 수 없으면 “확인 필요”로 표시한다. 임의 대화의 모든 질문을 완벽하게 감지하거나 출력 정지로 의사결정 대기를 추정하지 않는다. 질문 문장을 AI로 재분석하는 별도 모델 호출도 기본 기능에 넣지 않는다.

#### 도구별 이벤트 연결과 한계

아래는 2026-10-03 공식 문서 확인에 따른 **연결 후보**다. 실제 설치 버전·PRoot·interactive TUI에서 아직 실행 검증하지 않았다.

| 도구 | 후보 이벤트 | 연결 정책 |
|---|---|---|
| Claude Code | `PermissionRequest`, `Notification`의 `permission_prompt` | 즉시 요청과 지연 알림을 가능한 request identity로 연결해 중복을 줄임 |
| Claude Code | `PreToolUse`의 `AskUserQuestion`/`ExitPlanMode`, 해당 elicitation 알림 | 질문·계획 검토를 구분. 일부 알림 타입은 특정 모드에서만 발생하므로 범용 감지로 확대하지 않음 |
| Codex | `PermissionRequest` | 요청 관측 후 기존 승인 흐름 유지 |
| Codex | 지원되는 function tool의 `PreToolUse`/`PostToolUse` | 실제 버전의 질문 tool 경로를 시험한 경우만 USER_INPUT 지원. Claude의 Notification 이벤트 이름을 그대로 쓰지 않음 |
| 공통 | 검증된 `Stop`, 세션 종료 및 후속 이벤트 | 턴 완료·요청 해결·프로세스 종료를 각각 판정 |

Claude의 Notification에는 지연·모드 조건이 있고, Codex는 일부 특수 tool 경로가 훅 관측에서 제외될 수 있다. `Stop` 자체를 테스트 통과나 모든 요청 해결의 증거로 사용하지 않는다. [Claude 훅 명세](https://code.claude.com/docs/en/hooks), [Codex 훅 명세](https://learn.chatgpt.com/docs/hooks)

#### 수신 경로

```text
CLI 공식 훅 → guest용 z8-event helper
  → 프로젝트·launch에 연결된 로컬 이벤트 통로
  → ExecutionService / EventAdapter
  → AttentionItem 저장·중복 정리
  → Android Notification + 앱 내 응답 필요 목록
  → 사용자가 탭 → 동일 workspace/session의 터미널
```

로컬 통로는 앱 private Unix domain socket과 guest의 좁은 bind를 우선 검증한다. guest에서 socket 접속·helper 실행이 가능한지는 G0에서 확인한다. 외부 Termux:API APK나 자체 클라우드 push 서버를 요구하지 않는다. 짧은 JSON frame, 제안 payload 상한 16KiB, 제한된 queue·재시도와 ACK를 사용하고 transcript·전체 파일 내용을 전송하지 않는다. 앱 수신기가 eventId를 저장한 뒤 ACK하며 재전송은 같은 eventId를 사용한다. 넘친 이벤트·연결 실패는 진단에 남긴다.

payload에는 schemaVersion, eventId, launchId, providerSessionId, 선택적 turn/request/toolUse ID, event kind, 발생 시각과 최소 요약을 담는다. workspace·host·session은 payload의 자기 주장만 믿지 않고 앱의 launcher 등록과 연결한다. 오래된 launch·종료된 세션의 이벤트는 현재 실행의 요청으로 표시하지 않는다. session별 통로와 nonce는 오연결을 줄이는 장치이며 같은 Android UID 안의 악성 코드에 대한 보안 격리는 아니다. 이벤트의 URL/명령/경로를 수신 즉시 실행하지 않는다.

관측용 helper는 이벤트 전달 후 즉시 끝나며 **승인·거절·입력 변경 결정을 반환하지 않는다**. 표준 출력은 해당 훅 계약에 맞게 비워두고, 장애 시 기존 CLI의 승인 흐름을 유지한다. 알림 수신기를 기다리며 permission hook을 장시간 붙잡지 않는다. 설치는 사용자 기존 hook 설정을 보존해 z8 항목만 추가·제거하며, 도구가 요구하는 훅 검토·신뢰 절차를 존중한다. 훅 trust 우회 옵션을 기본으로 넣지 않는다.

#### 요청 수명과 응답

AttentionItem의 요청 상태는 `OBSERVED / WAITING_CONFIRMED / RESOLVED / STALE / UNKNOWN`, 사용자 읽음은 `seenAt`, 전달 상태는 `QUEUED / POSTED / SUPPRESSED / BLOCKED / FAILED`로 따로 기록한다. POSTED는 Android API에 게시했다는 뜻이며 사용자가 보거나 소리를 들었다는 보장이 아니다.

동일 provider request ID의 재전송은 한 요청으로 처리한다. 고유 ID가 없는 이벤트는 좁은 시간창과 launch·turn·종류를 사용해 알림음을 묶되 서로 다른 권한 요청을 삭제/병합하지 않는다. 다른 훅이 요청을 처리했거나 CLI에서 이미 답변한 경우 확인 가능한 후속 이벤트로 해결 처리한다. 해결 이벤트가 없는 버전에서는 알림을 읽었다고 RESOLVED로 바꾸지 않으며, 나중에 상태를 확인할 수 없으면 UNKNOWN/STALE로 표시한다.

알림 탭은 승인이나 `y`/Enter 입력이 아니다. launch와 요청 상태를 재확인해 터미널로 이동하고, 세션이 사라졌으면 중단 화면을 연다. 임의 명령 재시작은 하지 않는다. 알림 자체의 승인·거절·빠른 답장은 후속 확장 후보이며, 정확한 request ID·내용 hash·유효기간·한 번만 적용·도구 ACK를 검증하는 공식 응답 통로가 있을 때만 구현한다. raw PTY 입력으로 흉내 내지 않는다.

#### Android 알림 정책

- `runtime_status` 실행 유지 알림과 `agent_attention` 응답 요청 채널을 나눈다. 완료 알림은 별도 선택 채널이다. 같은 세션을 보고 있는 동안은 앱 내 표시를 우선하고 화면 밖 요청에 알림을 사용한다. 동일 요청의 소리 반복은 기본 꺼짐이다.
- 기본 잠금 화면 문구는 “z8 · 확인이 필요합니다”로 제한한다. PRIVATE/publicVersion과 최소 payload를 사용하고, 프로젝트명·명령·질문 본문 표시는 사용자 선택으로 둔다. 상세 내용은 앱에서 확인한다.
- Android13+의 `POST_NOTIFICATIONS`, 앱/채널 차단 여부를 확인하고 거부 시 앱 내 응답 필요 목록과 설정 이동을 제공한다. target≤32 후보에서는 시스템이 권한창 시점을 정하므로 임의 시점의 재요청을 약속하지 않는다. 첫 알림 채널 생성 전에 알림 용도를 안내한다.
- 클릭은 명시적 Activity와 immutable PendingIntent를 사용한다. event/session별 고유 identity로 구성해 오래된 알림이 다른 세션을 열지 않게 한다. 전달값은 앱 ID 참조만 사용하고 Activity에서 검증한다.
- DND·채널 음소거·OS 회수·강제 종료 중 알림 도달/소리를 보장하지 않는다. FGS 알림 존재와 요청 알림 권한 허용은 별개다. 채널을 재생성해 사용자 음소거를 우회하지 않는다.

Android 동작 근거: [알림 권한](https://developer.android.com/develop/ui/compose/notifications/notification-permission), [채널](https://developer.android.com/develop/ui/compose/notifications/channels), [잠금 화면](https://developer.android.com/develop/ui/compose/notifications/create-notification#set-lockscreen-visibility), [알림에서 화면 열기](https://developer.android.com/develop/ui/views/notifications/navigation).

G3 원격은 SSH로 인증된 이벤트 통로를 별도 추가한다. 연결이 끊기면 원격에서 제한된 queue를 보관하고 재연결 후 오래된 요청을 재검증한다. 기기와 원격 호스트 사이에 연결이 없을 때 실시간 알림을 보장하지 않는다. 지속 알림을 위해 몰래 클라우드 계정이나 외부 공개 endpoint를 추가하지 않는다.

## 8. 백그라운드와 자원 정책

### 8.1 실행 서비스

사용자가 화면에서 실행을 시작할 때 서비스·알림을 시작한다. Activity가 서비스에 bind/unbind해도 프로세스 소유권을 넘기지 않는다. 서비스는 상태 조회와 재연결을 담당하며 Android가 앱 전체를 중지한 뒤 실행을 보장하지 않는다. FGS type/권한은 최종 targetSdk에 맞춰 결정한다. `specialUse`는 검토 후보이고 일반 개발 세션을 `dataSync`로 무조건 분류하지 않는다. [FGS 유형](https://developer.android.com/develop/background-work/services/fgs/service-types), [사용자 중지](https://developer.android.com/develop/background-work/services/fgs/handle-user-stopping)

| 정책 | CPU wake lock | 보조 작업 |
|---|---|---|
| 기본 실행 유지 | 프로세스·FGS 유지 시도, wake lock 없음 | 화면 밖에서 트리 스캔·GitHub polling·렌더링 중지 |
| 화면 꺼져도 계속 실행 | 사용자가 켠 프로젝트의 살아 있는 로컬 세션 또는 Operation lease가 있을 때 partial lock | 동일하게 보조 작업은 중지 |
| 모든 실행 lease 종료 | 즉시 해제 | 필요한 짧은 정리 후 service 종료 |

“계속 실행”은 최초 세션 생성과 설정 화면에서 명시적으로 선택할 수 있게 한다. lock owner는 ExecutionService 하나이고 활성 요구량을 계산해 acquire/release한다. 예외·설치 실패·작업 취소·마지막 실행 lease 종료를 해제 경로에 포함한다. UI visibility나 출력 정지로 AI 작업이 끝났다고 판단하지 않는다. lock 활성 이유·경과 시간·끄기 동작을 알림에서 제공한다. wake lock은 네트워크·생존 보증이 아니다. [wake lock](https://developer.android.com/develop/background-work/background-tasks/awake/wakelock)

Session과 별도 command channel의 Operation은 runtime/environment에 활성 lease를 가진다. terminal이 0개여도 clone·설치·Git 작업이 실행 중이면 서비스와 환경을 유지한다. 완료·실패·취소 후 실제 자식 종료를 관측해 lease를 해제한다. 재시작 시 lease 레코드만 믿지 않고 실제 프로세스/operation 상태를 조정한다.

### 8.2 자원 제한의 범위

- 앱 소유 작업 queue는 기본 동시 무거운 작업 1개, 관리되는 build worker 수 2 이하를 시작값으로 시험한다. 사용자가 직접 실행한 CLI의 모든 자식 프로세스를 통제한다고 표시하지 않는다.
- Android native child/phantom-process 정책과 과도한 CPU 사용에 따른 종료는 메모리 제한과 별도로 검사한다. workspace 1/3/5개·worker 1/2/4개에서 자식 수와 signal 종료를 관측하고, 원인 불명 SIGKILL을 OOM으로 단정하지 않는다. 기기 전체 정책의 숫자를 z8에 보장된 프로세스 할당량으로 해석하지 않는다. [Termux 공식 경고](https://github.com/termux/termux-app#termux-application)
- thermal 상태가 높아지면 새 index·diff prefetch·설치를 줄이고 사용자에게 장시간 작업 상태를 알려준다. 실행 중 AI·build를 조용히 죽이거나 리모트로 옮기지 않는다.
- CPU governor·DVFS·cgroup·swap·커널 프로세스 제한을 바꾸는 기능은 전제로 하지 않는다. RAM/thermal API가 제공하지 않는 값은 UNKNOWN으로 표시한다.
- 메모리는 앱 UI, host runtime/tmux, guest/CLI, Android 가용 메모리를 분리 측정한다. 오래된 pane의 화면 cache·큰 diff를 먼저 줄이고 소스나 프로세스를 자동 삭제하지 않는다.
- 화면이 보일 때만 선택 디렉터리 watcher·현재 diff 갱신을 유지한다. focus 복귀 시 실제 상태를 재검사한다. 전 프로젝트를 일정 주기로 순회하지 않는다.
- 터미널 output burst는 순서대로 처리하고 화면 invalidate를 프레임에 맞춰 묶는다. 임의 바이트를 버리거나 escape sequence 중간을 잘라내지 않는다. 보이지 않는 세션은 tmux에서 유지하고 UI 렌더링을 멈춘다.
- scrollback은 제안 기본 10,000행/pane과 앱 cache 예산을 시험한다. 줄 수만으로 메모리 상한을 보장하지 않는다. 무한 로그 보관·자동 디스크 transcript는 기본 제공하지 않는다.
- 터미널 문자·키 입력마다 Room에 쓰지 않는다. 표시용 통계·진단 로그는 배치하고 크기를 제한한다. session 생성, 환경 참조 변경, 외부 쓰기 Operation 결과는 복구 가능한 영구 기록으로 구분한다. 이 최적화를 위해 source 저장이나 Git의 내구성을 낮추지 않는다.

이 정책들의 논문 근거와 비교 실험은 [최적화 연구](research/OPTIMIZATION_RESEARCH.md), 수치 목표는 [G0 검증 계획](validation/G0_VALIDATION_PLAN.md)에 둔다. 수치는 논문에서 복사한 성능 보증이 아니다.

## 9. 코드 경계와 구현 순서

제안 논리 모듈은 아래와 같다. 초기에는 이 경계를 package 수준으로 구현해도 되며 Gradle module을 불필요하게 먼저 늘리지 않는다.

| 경계 | 책임 |
|---|---|
| app / feature-workspace | Compose navigation, 창 적응, 프로젝트 화면 |
| runtime-termux | upstream service/session/PTY/JNI bridge, host bootstrap |
| terminal | upstream emulator/view 연결, 크기·키·선택 처리 |
| domain / data | 상태 조정, Room, 작업 queue, 설정·vault 참조 |
| environment | DistroAdapter, generation, manifest, install journal |
| files / editor | source 파일 API, draft·revision·Sora |
| git / github | command channel, JSON/NUL parser, 계정 범위, operation 기록 |
| remote | SSH/SFTP/remote tmux, host key, 재연결 |
| events / notifications | CLI 훅 adapter, AttentionItem, 중복·수명 처리, Android 채널·세션 이동 |
| diagnostics | capability 보고서, 성능 수집, 민감 정보 제외 |

| 단계 | 작업 묶음 | 다음 단계 진입 조건 |
|---|---|---|
| G0 실행 검증 | upstream 고정, 자체 prefix runtime, 기본 PTY+tmux+PRoot, 두 CLI 실제 작업, Android17 자원·백그라운드 시험 | 필수 시험 통과. 실패는 지원 범위/구조 결정 후 처리 |
| G1 로컬 제품 | 프로젝트/환경 lifecycle, adaptive UI, 세션 그룹, 파일 편집, GitHub 로그인·clone·diff, F13 응답 요청 알림 | 최초 세로 기능 구현 + 편집 충돌 + 접기/펼치기 + 알림에서 세션 복귀 시험 통과 |
| G2 GitHub 완성 | stage/commit/branch/push, issue, PR·리뷰·checks/Actions, backup/진단 | issue→수정→검토→PR→리뷰 전체 흐름 |
| G3 리모트 | SSH profile, remote tmux, SFTP, remote Git, 원격 이벤트 전달 | 연결 단절 후 기존 원격 세션 확인·재연결, 오래된 알림 재검증 |
| G4 편의 기능 | preview, 첨부, 선택적 완료 알림과 검증된 구조화 응답 | 기존 실행·입력·자원 지표 회귀 없음 |

G0의 APK 소스 및 재현 방법은 `BUILDING.md`, 결정은 `docs/adr/`, 실제 결과는 `reports/compatibility/`에 기록한다. 이 경로에 첫 진단 빌드와 제한된 실행 시험 결과가 있으며, 전체 G0 통과를 의미하지 않는다. upstream 원본 라이선스·수정 범위·고지를 보존하고 앱 전체를 임의 MIT로 선언하지 않는다. Claude Code는 공식 설치하는 외부 도구로 취급한다.

## 10. 미확정 결정과 검증 실패 처리

| 결정 | G0에서 확보할 증거 | 실패 시 처리 |
|---|---|---|
| SDK/OS 조합 | Android17 기본 정책의 설치·exec·PRoot·FGS | 정책 변경을 요구하지 않는 다른 정식 실행 구조 검토. 미해결 시 로컬 지원 미완료 |
| 자체 prefix | 모든 host 실행 파일·loader·shebang·pkg 의존성 검사 | 공식 Termux 경로에 기대는 파일을 찾아 재빌드 |
| 4KB/16KB | JNI부터 guest CLI까지 해당 page size에서 실제 실행 | 미검증/실패 프로필을 지원 완료로 표시하지 않음 |
| CLI/sandbox | 승인 흐름 포함 파일·셸·테스트·resume | 지원 기능 제한을 공개, 무승인 옵션 자동 적용 금지 |
| 훅 알림 | 실제 CLI별 권한/질문/계획 이벤트·Android 게시·세션 이동 | 미지원 이벤트 명시, 터미널 추측 파싱으로 지원 완료를 가장하지 않음 |
| tmux topology | 신호·종료·복귀·메모리 비교 | host/guest 및 서버 단위 결정 갱신 |
| 8GB 지원 | 대표 프로젝트·장시간 작업의 메모리/발열 | 기본 동시성/cache 축소, 실제 지원 작업 범위를 좁혀 명시 |
| background | 화면 꺼짐·절전·Samsung 정책·네트워크 전환 | 성공 조건과 중단 유형 표시. 영구 실행 주장 금지 |
| 저장 경쟁 | AI 반복 쓰기 중 editor 저장·복구 | 잠금만으로 해결됐다고 하지 않고 draft/merge 흐름 보강 |

완료 보고에는 구현한 기능, 실제 기기/도구 버전, PASS/FAIL/NOT TESTED, 재현 절차를 함께 적는다. 논문 인용과 문서 검토는 실행 성공의 증거로 계산하지 않는다.
