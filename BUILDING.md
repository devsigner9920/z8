# z8 개발·Play 후보 빌드

진단 APK와 자체 prefix 런타임 APK를 구분한다. 공통 화면은 프로젝트·세션·터미널·Linux 준비·테마·응답 알림·실행 진단이며 실제 Termux PTY/JNI·터미널·서비스를 사용한다. 진단 APK의 `/system/bin/sh` 실행과 Linux guest·AI CLI 실행 검증은 서로 다른 단계다. 빌드 성공만으로 G0 통과를 기록하지 않는다.

## 개발 도구

macOS ARM64와 Python 3.12 이상, 동작하는 Git, curl이 필요하다. macOS의 `/usr/bin/java`, `git`, `python3`는 도구가 설치되지 않은 stub일 수 있다. 그 경우 설치된 실행 파일을 PATH에 넣거나 `Z8_GIT`, `Z8_PYTHON`을 지정한다.

```sh
python3 tools/setup-toolchain.py
python3 tools/prepare-app.py --mode diagnostic
python3 tools/generate-release-notices.py --allow-incomplete
python3 tools/build-app.py --mode diagnostic
```

공개 저장소에는 이전 후보에서 생성한 고지 파일을 넣지 않는다. 위 `prepare-app.py`는
고정 upstream 소스를 준비하고, `generate-release-notices.py`는 현재 소스의 라이선스
전문과 고지를 개발용으로 생성한다. 이 단계의 `INCOMPLETE`는 정상적인 미완료 표시이며
`--allow-incomplete`가 출시 검토를 통과시켜 주지는 않는다. 바이너리를 배포할 때는 아래의
실제 패키지·Gradle 명세와 대응 소스를 사용해 고지를 다시 생성해야 한다.

도구는 `.local/`에 설치하며 전역 JDK/SDK를 교체하지 않는다. JDK와 Android command-line tools 아카이브는 `tools/toolchain.lock.json`의 다운로드 체크섬을 검증한다. SDK 패키지 ID는 고정하지만 platform-tools처럼 upstream에서 갱신되는 ID는 완전한 재현 빌드를 보장하지 않는다. SDK 설치 시 공급자의 라이선스에 동의하는 절차가 포함된다.

Termux 원본은 `tools/sources.lock.json`의 커밋으로 받는다. `upstream/termux-app`은 수정하지 않는다. `tools/prepare-app.py`가 별도 `.local/build-src`에 정확한 패치와 `overlay/`를 적용한다. 원본 커밋 또는 예상 코드가 달라지면 중지한다. Gradle 캐시는 `.local/gradle`에 둔다.

기본 빌드 명령은 APK 생성 후 terminal-emulator 단위 테스트와 APK 서명·앱 ID·ABI·SDK·16 KiB ZIP 정렬 검사를 수행한다. 결과는 선택한 모드에 따라 `artifacts/z8-g0-diagnostic-arm64.apk` 또는 `artifacts/z8-g0-runtime-arm64.apk`, 같은 이름의 JSON·서명·manifest 보고서에 둔다. `.local/keys/z8-debug.jks`는 최초 빌드 때 생성하는 이 개발 환경 전용 키다. 공개된 Termux 테스트 키를 사용하지 않는다. 키를 분실하면 기존 설치와 같은 서명으로 업데이트할 수 없다. Play 후보와 업로드 서명은 아래의 별도 경로를 사용한다.

## APK 식별자와 SDK

| 항목 | 현재 빌드 설정 |
| --- | --- |
| applicationId | `dev.devsigner.z8` |
| Java namespace / JNI | upstream `com.termux` 유지 |
| host prefix | `/data/data/dev.devsigner.z8/files/usr` |
| ABI | `arm64-v8a` |
| min / target / compile SDK | 28 / 36 / 36 |
| 외부 Termux 앱 | 필요 없음 |

2026-11-01부터 target 36을 사용한다. Android 10 이상에서는 Android/Bionic host 실행에 시스템 linker를 사용하며 Android 9에서는 기존 직접 실행 경로를 유지한다. Linux guest 실행은 PRoot를 사용하며 PRoot loader는 APK native library에 동봉한다. 이 변경의 기기 호환성과 Play의 외부 실행 코드 정책 적용은 별개의 검토 대상이다. 낮은 target 설치 차단을 우회하는 ADB 옵션을 사용하지 않는다. 앱은 primary Android user의 표준 내부 경로를 전제로 하며 Secure Folder·work profile·secondary user는 미검증이다.

## Play 제출 후보와 업로드 파일

무료·광고 없음·인앱결제 없음, 사용자 기기에서 공식 CLI를 실행하는 개발용 터미널이라는 제품 범위를 유지한다. 업로드나 소스·정책 페이지 게시를 빌드 명령이 자동으로 수행하지 않는다.

`release/config.json`은 비밀정보가 없는 공개 설정이다. 개발자 표시명, 지원 이메일, 개인정보처리방침 HTTPS URL, **해당 릴리스의 대응 소스 ZIP을 직접 다운로드하는 공개 HTTPS URL**, 정책 시행일을 채운다. 서명키·비밀번호·인증 토큰은 넣지 않는다. URL 형식 검사는 공개 접속이나 법적 적합성을 보증하지 않는다. 실제 운영자 값이 없는 상태에서는 후보만 만들 수 있다.

```sh
python3 tools/build-app.py --variant candidate --mode runtime \
  --runtime-manifest /absolute/path/runtime/manifest.json \
  --guest-manifest /absolute/path/guest/manifest.json
```

후보는 `.local/build-candidate`에서 release 최적화로 빌드한다. `artifacts/z8-candidate-runtime-arm64.aab`는 **서명되지 않은 후보**이며 그대로 업로드할 파일이 아니다. 함께 생성되는 APK는 같은 AAB를 bundletool로 변환하여 로컬 개발 키로 서명한 기기 시험용이다. JSON에는 버전·SDK·debuggable·해시·공개 정보 누락·검증 범위를 남긴다. bundletool 자체도 고정 버전과 SHA-256을 검증한다. 개발 키로 Play 업로드 파일을 만들지 않는다.

후보에 대해 다음 증거를 준비한다.

1. `tools/collect-release-package-sources.py`, `tools/package-release-source.py`, `tools/generate-release-notices.py`로 실제 host/guest/Gradle 구성요소의 고지와 대응 소스를 구성한다. 각 명령의 `--help`와 [배포 고지](THIRD_PARTY_NOTICES.md)를 따른다. 소스나 라이선스를 확보하지 못하면 미해결 상태로 남긴다.
2. 소스·공개 설정 변경을 마친 뒤 소스 스냅샷과 고지를 다시 생성하고 **최종 후보를 다시 빌드**한다. 생성 고지 자체는 소스 해시 순환을 피하도록 스냅샷에서 제외한다. 이전 후보의 테스트를 새 파일의 결과로 사용하지 않는다.
3. `tools/verify-release-compliance.py`로 최종 AAB·고지·소스·패키지·Gradle 명세를 연결한다. `--source-url`과 `--check-source-url`은 공개 소스 ZIP을 비로그인으로 받아 해시를 확인한다. 실제 결과가 `VERIFIED`여야 다음 단계로 갈 수 있다.
4. `release/qa.example.json`을 복사해 실제 최종 후보 해시와 기기·시험 증거를 기록한다. 에뮬레이터는 실기기 시험을 대체하지 않으며, CLI 실제 인증·작업은 허가된 테스트 계정으로 확인한다. 미실행 항목은 `NOT_TESTED`를 유지한다.
5. `release/decisions.example.json`을 복사해 정책·공급자 조건·스토어 표현·Data safety·서비스 신고 검토를 기록한다. 이 파일은 운영자의 검토 기록이며 Google 또는 공급자의 승인서가 아니다. 근거가 없으면 `false`를 유지한다.

업로드 키는 운영자가 관리하는 별도 키를 사용한다. 비밀번호는 `Z8_UPLOAD_STORE_PASSWORD`, `Z8_UPLOAD_KEY_PASSWORD`, 키 경로와 별칭은 `Z8_UPLOAD_KEYSTORE`, `Z8_UPLOAD_KEY_ALIAS` 환경변수로 전달하며 소스·보고서·명령 기록에 값을 넣지 않는다. 모든 증거가 준비되면 다음 명령은 검증한 후보를 **재빌드하지 않고** 서명한다.

```sh
python3 tools/promote-release.py \
  --candidate-metadata artifacts/z8-candidate-runtime-arm64.json \
  --compliance-report /absolute/path/verified-compliance.json \
  --qa-report /absolute/path/final-qa.json \
  --decisions /absolute/path/reviewed-decisions.json
```

성공 결과는 `artifacts/releases/<versionCode>/`에 저장한다. 서명 전후 앱 payload가 같고 bundletool 검사가 통과했는지 확인하며 기존 릴리스 디렉터리는 덮어쓰지 않는다. 개발자 정보 누락, 개발용 서명, 변경된 후보, 미완료 시험·정책 검토·대응 소스 검증이 있으면 중단한다. Play App Signing 등록, 콘솔 신고, 계정에 적용되는 테스트 요건, Play가 생성한 APK 설치·업데이트와 심사는 별도 운영 단계다. 출시 앱 서명이 기존 개발 APK와 다르면 기존 설치에 덮어쓸 수 없으므로 사용자의 프로젝트 삭제를 요구하지 말고 별도 시험 기기를 사용한다.

## 기본 경로와 셸 편의 기능

첫 실행 시 Prism·Midnight·Graphite·Ember·Paper 중 터미널 테마를 미리 보고 선택한다. 선택과 초기 설정 완료 상태를 함께 저장하며, 이후 상단 톱니바퀴 → `설정` → `테마`에서 다시 바꿀 수 있다. 미리보기만 보고 뒤로 가면 기존 선택을 유지한다. 테마 변경은 터미널의 배경·글자·커서·ANSI 16색에 적용되며 실행 중인 셸을 재시작하지 않는다. 사용자 `colors.properties`·셸 설정 파일은 덮어쓰지 않는다.

새 Android 진단 세션은 선택한 팔레트로 `Welcome to Z8 Terminal`과 `ll`·`mkcd`·`z8help` 안내를 한 번 표시한다. 세션 복귀·화면 회전·중첩 셸·프로필 재로드에서는 배너를 반복하지 않는다. 비대화형 셸 출력에도 추가하지 않는다.

현재 진단 셸은 앱 내부의 실제 `files/home`에서 시작한다. APK가 관리하는 `files/z8/shell/diagnostic.mkshrc`를 대화형 Android 셸의 `ENV`로 지정하여 `ll`, `la`, `l`, `..`, `...`, `cls`, `mkcd`를 제공한다. `z8help`로 목록을 볼 수 있다. 사용자 `.profile`·`.mkshrc`는 덮어쓰지 않으며, 셸 시작 시 임의로 실행하지 않는다. `TMPDIR`는 앱이 쓸 수 있는 cache 디렉터리다. APK 업데이트 후 새로 만든 셸에 적용된다.

프로젝트 PRoot 환경의 `HOME`과 일반 새 Linux 터미널의 시작 경로는 `/z8/home`이다. 프로젝트 소스는 별도 `/workspace`에 매핑한다. 세션 목록의 `＋`는 해당 프로젝트의 HOME에 Terminal을 바로 연다. 최초 앱 설정에서 데이터 사용에 동의하면 프로젝트 생성 전에 숨겨진 기본 환경에 Git·gh·Python·pip·venv·Node LTS·npm·build-essential과 [기본 패키지](runtime/guest/README.md)를 준비한다. 새 프로젝트는 이 환경을 독립적인 파일로 복사하며 HOME·소스는 공유하지 않는다. 진행 알림, 네트워크 변경과 강제 종료 후의 복구 계약은 [설치 생명주기](docs/PREPARATION_LIFECYCLE.md)에 정리했다. AI CLI 설치·인증은 사용자의 명시적인 작업이며 초기 설정에서 자동 실행하지 않는다. 각 단계의 실제 검증 범위는 보고서로 확인한다.

## 프로젝트·세션 탐색

2026-10-05 사용자 요청에 따라 별도 워크스페이스 홈과 파일·Git·GitHub 화면을 제거했다. Git과 GitHub 작업에는 최초 환경 준비에 설치되는 `git`·`gh`를 사용한다. 이전 내부 Workspace 링크는 터미널 프로젝트 선택으로만 전환하며 새 셸을 생성하지 않는다.

앱은 터미널 화면에서 시작하며 왼쪽 위 목록 버튼으로 프로젝트별 세션 목록을 연다. 실제 창 너비가 720dp 이상이면 옆에 펼친 사이드바를 사용하고, 그보다 좁으면 슬라이드 패널을 사용한다. 접기·펼치기와 창 크기 변경에 따라 배치를 갱신한다. 현재 프로젝트의 세션은 상단 가로 탭에도 표시하며, 탭이 많아져도 오른쪽 `＋`는 고정되어 있다.

프로젝트 이름을 누르면 현재 터미널 화면이 기억하는 해당 프로젝트의 마지막 세션으로 이동한다. 그 세션이 더 이상 살아 있지 않으면 다른 기존 세션을 선택하고, 기존 세션이 없으면 해당 프로젝트를 선택한 빈 터미널 영역을 표시한다. 이름 선택은 새 세션을 만들지 않는다. 별도의 펼침 아이콘은 프로젝트 목록만 접거나 펼친다.

키보드 표시 등으로 사용 가능한 높이가 480dp 미만이면 패널 위쪽과 프로젝트 머리글의 여백을 줄인다. z8 로고 오른쪽에는 알림 버튼을 유지하며, 테마는 상단 톱니바퀴의 설정 화면에서 연다. 하단 응답·테마 버튼은 없다.

탭 줄의 `＋`는 선택한 프로젝트에 새 Terminal을 연다. 선택한 프로젝트에 탭이 없으면 탭 줄과 이 버튼을 숨기며, 첫 터미널은 프로젝트 옆 `＋`로 연다. 일반 터미널 이름은 프로젝트별 `Terminal 1`, `Terminal 2` 순서로 지정한다. 새 세션을 만들 때 프로젝트·도구 선택 모달을 거치지 않는다. Linux 환경이 없으면 터미널 영역에서 자동 준비 단계와 진행 막대를 보여주며 공용 기기 셸로 전환하지 않는다. 새 프로젝트를 만들 때의 이름 입력 대화상자는 유지한다.

새 세션을 준비하는 동안 추가 버튼을 잠시 비활성화하며, 빠른 연속 누르기가 중복 생성을 요청하지 않도록 처리한다.

Claude Code·Codex는 필요한 CLI를 명시적으로 설치한 뒤 터미널에서 실행한다. 개발 빌드의 `설정` → `현재 프로젝트 환경`에도 설치·실행 버튼을 제공한다. 최초 기본 환경 설치에는 두 AI CLI가 포함되지 않으며, 기본 AI 탭을 만들거나 자동 실행하지 않는다. 탭은 사용자가 만든 실제 세션을 표시한다. 기존 탭이나 세션 행을 누르면 서비스가 소유한 동일한 PTY에 연결한다. 세션 전환은 새 프로세스를 만들거나 기존 프로그램을 종료하지 않는다. 탭·행을 길게 눌러 이름 변경·최근 출력 복사·알림·터미널 종료를 선택한다. 프로젝트 제목을 길게 누르면 삭제 확인창을 열며, 실행 중인 터미널이 있으면 `모두 종료하고 삭제`로 한 번에 종료와 삭제를 요청할 수 있다. 프로세스 종료를 확인하지 못하면 파일을 삭제하지 않는다.

`미확인 알림` 표시에는 살아 있는 세션에 실제로 수신한 미확인 훅 이벤트만 사용한다. `세션 열림`은 PTY 프로세스 상태이며 AI가 작업 중이라는 뜻이 아니다. 앱 프로세스가 종료된 뒤의 셸·대화 복구는 이 UI의 제공 범위에 포함되지 않는다. 자세한 동작과 Orca 참고 출처는 [세션 탐색 문서](docs/SESSION_NAVIGATION.md), APK와 실제 시험 범위는 세션 UI 검증 기록 (비공개 내부 검증 기록: `reports/compatibility/session-navigation.json`)에 둔다.

## Linux 런타임 빌드

진단 모드에는 bootstrap을 넣지 않는다. Linux 버튼은 비활성화되고 `/system/bin/sh`만 열 수 있다. runtime 모드는 자체 앱 ID·prefix·ABI·SHA-256이 일치하는 bootstrap manifest를 요구하며, 기존 `com.termux` bootstrap으로 대체하지 않는다.

```sh
# Linux Docker backend에서 자체 prefix 도구를 소스 빌드한다.
bash tools/build-runtime.sh --build --profile core --jobs 4
# 생성된 검증 manifest 경로를 사용한다.
python3 tools/build-app.py --mode runtime --runtime-manifest /absolute/path/runtime-manifest.json
# 고정된 Ubuntu Base를 검사하고 guest 아티팩트를 생성한다.
python3 tools/prepare-guest.py --build
# 프로젝트 Linux 이미지를 함께 넣으려면 --guest-manifest를 추가한다.
python3 tools/build-app.py --mode runtime --runtime-manifest /absolute/path/runtime-manifest.json --guest-manifest /absolute/path/guest/manifest.json
```

bootstrap은 Android native 도구다. guest 이미지의 설치와 Claude/Codex의 실제 로그인·수정·셸·테스트 검증은 별도다. Linux 화면은 프로젝트별 rootfs를 새 staging 디렉터리에 준비한 뒤 게시하며 기존 환경을 덮어쓰지 않는다. HOME과 소스는 rootfs 밖에 보관한다. 환경만 초기화하거나 삭제하는 UI는 아직 제공하지 않는다. 프로젝트 제목을 길게 눌러 프로젝트 전체를 삭제하면 소스·HOME·Linux 환경이 함께 삭제되므로 환경 복구와 구분한다.

`tools/build-runtime.sh`는 source commit·공식 빌더 이미지 digest·NDK를 고정하고 자체 prefix 도구를 소스에서 컴파일한다. `core`는 셸·tmux·PRoot·압축 도구에 집중하며 전체 패키지 관리 환경은 `workspace` 프로파일이다. 공식 `com.termux` 패키지로 자동 대체하지 않는다. 자세한 공급 경계는 [runtime/README.md](runtime/README.md)에 있다.

macOS에서 Docker가 없다면 `python3 tools/setup-builder-vm.py --install`로 프로젝트 전용 Lima 빌드 VM을 준비할 수 있다. VM·도구·설정은 `.local/`에 두고 저장소만 공유한다. 빌드 시 `Z8_DOCKER="$PWD/.local/bin/docker-z8"`를 지정한다. 이것은 개발 머신의 크로스 컴파일 기반이며 Android 앱에 VM이나 루팅을 요구하지 않는다. 사용하지 않을 때는 `LIMA_HOME="$PWD/.local/linux-vm" .local/lima/bin/limactl stop z8-builder`로 중지할 수 있다.

## 기기 검사

```sh
sh tools/device-check.sh --output reports/compatibility/device-report.json
python3 -m unittest discover -s tests -v
```

기기 검사는 읽기 전용이며, 연결되지 않은 경우 `NOT_TESTED`로 기록한다. APK는 일반 설치 UI로 설치하는 시험을 우선한다. 설치 후 진단 화면에서 기기·prefix를 확인하고 “터미널 열기 / 이어가기”로 진입해 `id`, `pwd`, `uname -m`을 실행한다. “새 Android 진단 셸 만들기”는 별도 세션을 만든다. 앱 이탈·복귀·회전에서 같은 셸이 유지되는지 확인한다. 에뮬레이터 결과는 실기기 결과와 구분한다. 전체 판정 기준은 [G0 계획](docs/validation/G0_VALIDATION_PLAN.md)에 있다.

## 전용 에뮬레이터 smoke test

하단 ESC·CTRL·방향키 보조 바는 기본으로 숨긴다. 기존 `NEW SESSION`·`KEYBOARD` 패널은 새 프로젝트·세션 UI로 대체되어 화면에 표시하지 않는다. 새 세션은 프로젝트 옆 `＋` 또는 탭이 있을 때 표시되는 탭 줄의 `＋`를 사용하며, 시스템 키보드는 터미널 입력과 기존 외장 키보드 단축키로 사용한다. 보조 바와 시스템 키보드의 표시 여부는 별개다.

```sh
# 별도 터미널에서 실행. 최초 --install은 emulator/image를 추가 다운로드한다.
sh tools/start-emulator.sh --install
# 에뮬레이터 창을 보면서 직접 사용할 때:
sh tools/start-emulator.sh --windowed
# 부팅 후: 전용 AVD인지 확인하고 APK를 설치/업데이트하여 시험한다.
python3 tools/smoke-emulator.py
```

API 37.0·ARM64·16KB 이미지와 Pixel Fold 하드웨어 프로파일을 쓰며 RAM은 4GB로 설정한다. Galaxy 또는 8GB 수용 시험을 대신하지 않는다. 시험은 정상 알림 권한 UI를 허용하고 앱의 PTY에서 PID와 셸 변수를 기록해 10초 Home 이탈·복귀와 한 번의 회전을 확인한다. `run-as`는 전용 debug 앱의 시험 파일을 준비·읽고, 별도 tmux 연속성 시험에서 같은 앱 UID의 제어 클라이언트를 실행하는 데 사용한다. 실제 사용자 명령의 증거는 앱이 생성한 PTY에서 얻는다. 설치 정책 우회·root·실기기 설정 변경은 하지 않는다. 대상 serial과 AVD 이름이 다르면 중지한다.

런타임 APK가 생성되면 다음 순서로 검증한다. Linux 시험은 기존의 시험용 프로젝트 UUID와 화면 이름을 명시한다. 계정 로그인이나 원격 변경을 자동으로 실행하지 않는다.

2026-10-17 점검: 연속성·세션 탐색 스크립트가 현재 `Terminal N` 이름과 탭 길게 누르기 메뉴를 사용하도록 수정했고 관련 호스트 검사를 통과했다. 아래 명령 목록은 시험 진입점 안내이며 현재 APK에서 모든 기기 시험을 통과했다는 뜻이 아니다. 실행 전에 각 스크립트의 전용 AVD 제한과 필요한 초기 상태를 확인한다. 실제 재실행 결과는 APK 해시가 포함된 날짜별 `reports/compatibility/` 기록을 기준으로 한다.

```sh
python3 tools/smoke-runtime.py
python3 tools/smoke-tmux.py
python3 tools/smoke-guest.py --project PROJECT_UUID --name 'z8 demo'
python3 tools/smoke-guest-continuity.py --project PROJECT_UUID --name 'z8 demo'
# 설치된 Linux 환경 두 개를 사용하는 세션 탐색 시험:
python3 tools/smoke-session-navigation.py --project PROJECT_UUID --name 'z8 demo' --other-project OTHER_PROJECT_UUID --other-name 'hello-world'
```

연속성 시험은 기존 시험 프로젝트에 작은 증거 파일과 새 세션 두 개를 만든다. HOME 복귀·접기/펼치기·새 세션의 프로젝트 계승을 PID와 셸 변수로 확인하며 기존 세션을 종료하지 않는다. 현재 UI에서는 터미널의 프로젝트 목록 버튼, 상단 탭과 고정 `＋`를 사용한다. 터미널 길게 누르기 → `More…` → `세션 목록 / 새 세션` 경로도 같은 새 패널로 연결한다. 이전 APK에서 기록한 연속성 시험 결과와 현재 세션 UI의 시험 범위는 각 보고서의 APK 식별자로 구분한다.

세션 탐색 시험은 별도의 전용 fixture 프로젝트 두 개를 사용한다. 새 셸 생성·이름 변경·탭과 프로젝트 전환·키보드 표시 중 전환·접기/펼치기를 검사하고, 시험이 만든 `Scratch` 세션만 명시적 종료 확인으로 닫는다. `Build`, `Review` 이름과 다른 프로젝트의 셸, 작은 증거 파일은 남는다. 계정 인증과 AI 작업은 수행하지 않으며 최소 4개 세션 슬롯을 확보한 전용 시험 상태에서 실행한다.

각 스크립트는 설치된 APK·bootstrap을 확인하고 실제 실행 파일, PID, HOME, 페이지 크기를 기록한다. `smoke-tmux`의 수동 연결 시험은 제품의 자동 tmux 세션 관리가 구현됐다는 뜻이 아니다. 실제 CLI 로그인·파일 수정·명령/테스트 실행은 사용자 계정으로 별도 완료해야 한다.

원본 라이선스와 수정 범위는 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)를 따른다.
