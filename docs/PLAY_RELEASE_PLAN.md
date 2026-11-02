# Z8 Play 출시 개선·추가 개발 계획

2026-11-02 공개 문서 정리. 이 문서는 **2026-11-01 구현 도중 작성한 작업 계획과 당시 현황을 보존한 기록**이다. 아래 체크박스와 “제안”·“다음” 표현은 원래 수용 기준을 담고 있으며, 현재의 미구현 목록이나 최신 후보의 검증 결과를 뜻하지 않는다. 현재 빌드 설정과 명령은 [BUILDING.md](../BUILDING.md), 실행 구조는 [runtime/README.md](../runtime/README.md), 대응 소스와 고지 절차는 [RELEASE_LICENSES.md](RELEASE_LICENSES.md)를 따른다.

코드 구현 여부, 특정 후보·기기에서 확인한 실행 결과, 공개 배포 및 Play 심사 판정은 각각 구분한다. 이 계획이나 공개 저장소의 존재만으로 출시 준비 완료·기기 지원·심사 승인을 주장하지 않는다. 무료·광고 없음·인앱결제 없음, Local only MVP라는 제품 범위를 유지한다.

작성 당시 참고한 `reports/compliance/2026-10-31/PLAY_STORE_REVIEW.md`는 **비공개 내부 검증 기록**으로, 공개 저장소에는 포함하지 않는다. 아래 원래 작업 항목의 체크박스는 코드 작성만으로 완료 처리하지 않고 기기·정책·출시 증거까지 충족했을 때 별도로 평가한다.

**2026-11-01 구현 상태 — 해당 시점의 스냅샷**

- R1/R2: target 36, 시스템 linker 기반 host 실행, APK 동봉 PRoot loader, 예측 뒤로가기·화면/키보드 영역·알림 PendingIntent·foreground service 유형을 반영했다. 기존 prefix를 보존하는 검증형 업데이트 경로를 추가했다. 최종 runtime 기기 시험은 별도 결과로 남긴다.
- R3: unsigned release AAB 후보, bundletool 검증·로컬 시험 APK, 공개 설정 검증과 업로드 키 분리, 동일 후보의 QA·라이선스·운영 검토 증거를 요구하는 서명 단계를 구현했다. [현재 빌드 절차](../BUILDING.md)를 따른다.
- R5/R6: release 공개 설정에서 오프라인 개인정보·저장/삭제·외부 CLI·격리 한계·라이선스를 읽을 수 있다. 미리보기 쿠키·사이트 저장소·캐시 삭제에 전체 미리보기 중지, 확인·취소, 비동기 완료와 지원 여부 확인을 추가했다. 운영자 정보와 공개 URL은 실제 값 입력이 남아 있다.
- R7: 소스 아카이브·패키지별 대응 소스 수집·고지·최종 artifact 연결 검증 도구를 구현했다. 도구 존재와 전체 라이선스 의무 충족은 구분한다.
- R4/R8/R9/R10: 외부 실행 코드 정책 적용, 배포 조건, Data safety, 사용자 계정으로 수행할 CLI 작업, 실기기·Play 테스트는 검토/검증이 남아 있다. 현재 코드를 심사 승인된 것으로 표시하지 않는다.

**사용자가 확정한 제품 범위**

Z8는 **Android에서 Codex·Claude Code 같은 공식 CLI를 PC 환경처럼 편하게 실행하는 개발 환경·터미널 도구**다. 프로젝트·셸·세션·설치·브라우저 인증 연결을 지원한다. 자체 AI 채팅, Z8 서버를 통한 모델 요청 중개, 공용 AI 계정, AI 사용량 재판매는 제품 범위에 포함하지 않는다. 사용자가 선택한 공식 CLI에서 본인의 계정으로 직접 인증하고 사용하는 구조를 유지한다.

스토어 설명 초안: “Android 기기에서 프로젝트별 Linux 개발 환경과 터미널을 사용할 수 있는 개발 도구입니다. Codex와 Claude Code 등 지원되는 명령줄 도구를 설치하고 실행할 수 있도록 돕습니다. 각 외부 서비스의 계정과 이용 조건은 별도로 적용됩니다.” 실제 검증을 통과한 CLI·기기·기능만 지원 목록에 넣는다.

AI 콘텐츠 생성 UI·신고 서버는 기본 개발 목록에서 제외한다. Google의 정책 적용은 명칭만으로 결정되지 않으므로 실제 CLI 호스팅 구조를 설명하고 적용 여부를 확인한다. 별도 신고 기능은 정책상 요구가 확인되거나 제품 범위가 바뀔 때 다시 검토한다. 사용자 직접 실행 구조라도 개인정보·라이선스·외부 코드 정책 검토는 필요하다.

**우선순위와 의존성**

| 작업 | 우선순위 | 구분 | 선행 조건 | 완료 산출물 |
| --- | --- | --- | --- | --- |
| R1 Play용 런타임 최소 실험 | P0 | 핵심 구조 개발 | 없음 | target 36 이상에서 동작하는 셸·PRoot·guest 실행 증거 |
| R2 Android 동작·서비스 대응 | P0 | 필수 개발 | R1과 병행, 최종 통합은 R1 이후 | 알림·백그라운드·뒤로가기·화면 호환성 검증 |
| R3 출시 AAB·서명 파이프라인 | P0 | 필수 개발 | 골격은 병행, 최종 검증은 R1/R2 이후 | release AAB, 실제 manifest·서명·해시 보고서 |
| R4 실행 코드 정책 설명 | P0 | 기술 검토·운영 확인 | R1 설계와 병행 | 공급·실행 경로 문서와 심사 설명 자료 |
| R5 개인정보·환경 안내 | P1 | 필수 고지·안내 개발 | 실제 데이터 흐름 확인 | 공개 정책 URL, release 내 안내, Data safety 근거표 |
| R6 저장 데이터 삭제 범위 정리 | P1 | 보안 UX 보완 | 현재 구조로 병행 가능 | 미리보기 데이터 삭제, CLI 로그아웃·삭제 안내 |
| R7 배포 소스·라이선스 자동화 | P1 | 배포 의무를 위한 개발 | 현재 구조로 시작, 최종 R1 산출물 반영 | 대응 소스 아카이브·고지·릴리스 연결표 |
| R8 이미지·공급자 조건 확정 | P1 | 운영·법무 결정 | R1/R4와 병행 | guest 공급 결정, 계약·브랜드 확인 기록 |
| R9 출시 후보 검증 | P0 | 검증 | R1–R8 | 실제 release 설치·업데이트·삭제·CLI 실행 결과 |
| R10 스토어·계정 준비 | P1 | 운영 작업 | 초안 병행, 제출은 R9 이후 | 스토어 등록정보, 테스트·FGS·심사 안내 |

P0는 공개 출시 판단의 선행 과제다. P1도 필요한 요건을 충족해야 출시할 수 있으며, 우선순위가 낮다고 생략 가능한 것은 아니다. R6의 추가 삭제 UI 등은 정책상 특정 버튼이 강제된다는 뜻이 아니라 현재 저장 구조를 사용자가 관리할 수 있게 하는 권장 구현이다.

**R1 — Play용 런타임 최소 실험**

- [ ] 기존 실행 경로를 host(Android/Bionic)와 guest(Linux/glibc·musl)로 분리해 목록화한다. PRoot·bash·tmux·설치 프로세스·자식 프로세스·shebang·공유 라이브러리까지 포함한다.
- [ ] 공식 Termux Play판의 로더 배치와 실행 방식을 비교한다. 조사 시점 커밋은 `cf69df7a8d2a4c496f5b2464d0365a63a58716c5`이며 target/compile 37, min 30이다. Z8의 min 28·overlay와 다르므로 전체 코드를 곧바로 교체하지 않고 실행 어댑터와 로더 패키징을 최소 실험한다. [고정 소스](https://github.com/termux-play-store/termux-apps/tree/cf69df7a8d2a4c496f5b2464d0365a63a58716c5)
- [ ] target 36 이상에서 APK의 native library 영역에 필요한 로더를 패키징하고, 실제 설치 경로를 이용하는 실행 구조를 시험한다. 파일 확장자를 바꾸는 것만으로 호환성·정책 문제가 해결된다고 보지 않는다. Android host의 LD_PRELOAD를 Linux guest에 그대로 전달하지 않는다.
- [ ] host 실행을 한 어댑터로 모으는 설계를 추가한다(제안 이름 `Z8RuntimeLauncher`). PTY뿐 아니라 환경 준비·버전 probe·Git·백그라운드 자식 프로세스도 같은 실행 규칙을 사용하게 한다. Android system linker를 적용하는 대상은 Android host ELF이며 Ubuntu glibc·Codex musl 바이너리를 일괄 변경하지 않는다.
- [ ] 현재 prefix·application ID와 프로젝트 HOME/소스 분리를 유지한다. `.local/build-src`는 생성 결과이므로 수정은 `tools/prepare-app.py`, `overlay/`, runtime recipe에 기록한다.

선별 이식 참고: [Play판 실행 인수·환경](https://github.com/termux-play-store/termux-apps/blob/cf69df7a8d2a4c496f5b2464d0365a63a58716c5/termux-app/src/main/java/com/termux/app/TermuxShellUtils.java#L81), [nativeLibraryDir 연결](https://github.com/termux-play-store/termux-apps/blob/cf69df7a8d2a4c496f5b2464d0365a63a58716c5/termux-app/src/main/java/com/termux/app/TermuxInstaller.java#L314), [PRoot 빌드](https://github.com/termux-play-store/termux-packages/blob/57401119f9988f79fa095398a9b33b03380222b3/packages/proot/build.sh#L16), [host exec 구현](https://github.com/termux-play-store/termux-exec/blob/47633d5df2db3dfea34cef568c6c82a7ba8dcc2e/src/termux-exec.c). 앱과 패키지·exec 라이브러리를 각각 고정하며, Z8에 사용 중인 PRoot 버전과의 차이도 확인한다.

주요 변경 위치: [Z8Guest.java](../overlay/app/src/main/java/com/termux/app/Z8Guest.java), [Z8Bootstrap.java](../overlay/app/src/main/java/com/termux/app/Z8Bootstrap.java), [Z8GuestSessionLauncher.java](../overlay/app/src/main/java/com/termux/app/Z8GuestSessionLauncher.java), [prepare-app.py](../tools/prepare-app.py), `tools/prepare-runtime.py`, `runtime/container-build.sh`.

완료 기준: SELinux·설치 보안 설정을 바꾸지 않은 시험 기기에서 새 설치→셸→PRoot→Python/Node→git→자식 프로세스→컴파일 결과 실행이 된다. 파일만 배치되거나 --version만 출력되는 결과는 전체 통과가 아니다. 기존 `smoke-runtime.py`, `smoke-guest.py`, `smoke-guest-continuity.py`를 실제 출시 경로에 맞춰 확장한다. 기술 성공과 Play 정책 허용은 별도 결과로 기록한다. [Android 실행 제한](https://developer.android.com/about/versions/10/behavior-changes-10#execute-permission)

**R2 — Android 타깃 상향에 따른 동작 대응**

- [ ] `targetSdk 28` 고정 검사·빌드 메타데이터·시험 기대값을 함께 변경한다. 최종 target은 제출 시점의 Google 요건을 충족하고 compileSdk도 그 이상이어야 한다.
- [ ] 현재 TermuxService의 일반 터미널 세션과 환경 설치 작업을 구별해 foreground service 사용 근거를 정리한다. `specialUse`는 후보이며 manifest 유형·전용 권한·subtype 설명과 Play 신고가 모두 필요하다. 장시간 터미널을 임의로 dataSync나 shortService로 분류하지 않는다.
- [ ] 알림 권한 허용·거부, 화면 종료, 사용자 서비스 중지, 프로세스 종료 후 복구를 처리한다. 현재 진행률·WakeLock 해제·작업 중복 방지 로직은 보존한다.
- [ ] 상속한 TermuxActivity의 동적 broadcast receiver를 감사한다. 앱 내부 broadcast 등록에는 지원 버전에 맞게 NOT_EXPORTED를 명시하고, 시스템 broadcast 전용 등록과 구별한다. 현재 API 28 동작에 의존한 등록을 그대로 유지하지 않는다. [Android 14 receiver 요건](https://developer.android.com/about/versions/14/behavior-changes-14#runtime-receivers-exported)
- [ ] target 36에서 달라지는 뒤로가기와 edge-to-edge, 접기·회전·분할 화면, IME 영역을 대응한다. 현재 `onBackPressed()` 패치에 의존하는 미리보기 복귀·설치 화면 동작을 새 back API로 옮긴다.
- [ ] hiddenapibypass 호출을 목록화하고 공개 API 대체·미지원 경로 정리를 검토한다. 존재 자체를 정책 위반 확정으로 취급하지 않는다. localhost 미리보기와 설치 네트워크도 실제 target에서 회귀 확인한다.

주요 변경 위치: [manifest 생성](../tools/prepare-app.py), 같은 파일의 `patch_sessions`, [Z8PreparationNotification.java](../overlay/app/src/main/java/com/termux/app/Z8PreparationNotification.java), [Z8SessionChrome.java](../overlay/app/src/main/java/com/termux/app/Z8SessionChrome.java), [Z8Theme.java](../overlay/app/src/main/java/com/termux/app/Z8Theme.java), `Z8SetupActivity.java`, `Z8ThemeActivity.java`.

완료 기준: 일반 기기 설정에서 알림 거부가 설치 정리·세션 종료를 망가뜨리지 않고, 중지된 일반 셸 명령을 자동 재실행하지 않는다. 키보드·시스템 바가 터미널을 가리지 않고 뒤로가기가 브라우저→터미널 복귀를 유지한다. 기존 preparation notification/process, session navigation, input 시험을 확장한다. [FGS 정책](https://support.google.com/googleplay/android-developer/answer/16559646?hl=en), [Android 16 동작 변경](https://developer.android.com/about/versions/16/behavior-changes-16)

**R3 — release AAB와 서명·산출물 검증**

- [ ] 현재 `--mode diagnostic/runtime`와 debug/release 구분을 별도 설정으로 둔다. `assembleDebug`만 실행하는 흐름에 release AAB 생성을 추가한다.
- [ ] release는 명시적인 업로드 키·alias·비밀정보 입력이 없으면 실패시킨다. debug 키 자동 생성으로 대체하지 않는다. 비밀번호·키·계정 파일은 저장소나 로그에 기록하지 않는다.
- [ ] versionCode/versionName을 릴리스 입력으로 관리한다. `targetSdk`, debuggable, ABI 등 메타데이터는 현재처럼 상수로 쓰지 않고 최종 산출물에서 추출해 검증한다.
- [ ] AAB는 번들 구조·서명을 검증하고 bundletool로 생성한 APK도 확인한다. APK용 apksigner/zipalign 검사와 AAB 검사를 구분한다. 최종 패키지의 native loader 및 16 KiB 정렬도 확인한다.
- [ ] 앱 서명 키와 업로드 키 역할, Play App Signing, 백업·키 접근 책임자를 정한다. 개발 APK와 출시 앱의 서명이 다를 경우 기존 설치를 덮어쓸 수 없으므로 별도 시험 기기를 사용하고 사용자 프로젝트 삭제를 유도하지 않는다.

주요 위치: [build-app.py](../tools/build-app.py), [prepare-app.py](../tools/prepare-app.py), `tools/toolchain.lock.json`, `tests/test_prepare_app.py`, `BUILDING.md`.

완료 기준: 키 누락·debug 서명·debuggable=true·잘못된 target/버전이면 release 생성 또는 검증이 실패한다. 정상 번들로 설치·업데이트한 결과와 실제 서명 지문·SHA를 기록한다. 테스트 결과 없는 기기를 PASS로 적지 않는다. [앱 서명](https://developer.android.com/studio/publish/app-signing), [bundletool](https://developer.android.com/tools/bundletool), [업데이트 조건](https://developer.android.com/google/play/app-updates)

**R4 — 외부 실행 코드와 제품 역할 설명**

- [ ] 각 파일을 APK 동봉 host/guest, 설치 중 apt·Node, 사용자 선택 CLI, 사용자 임의 프로젝트 도구로 구분한다. 원본 URL·버전·해시·설치 위치·실행 주체·업데이트 경로를 기록한다.
- [ ] 공식 CLI 실행 호스트라는 제품 역할, Android 권한/API 접근 범위, 앱 자체 업데이트와 사용자 개발 도구 설치의 차이를 실제 동작과 함께 설명한다.
- [ ] 무결성 검사와 사용자 동의는 보존하되, 이를 VM·인터프리터 예외의 자동 충족 근거로 쓰지 않는다. 실제 아키텍처 자료를 갖춘 후 Google에 적용 여부를 문의할 수 있도록 초안을 만든다.

완료 기준: R1의 실제 실행 경로와 설명 자료가 일치하고 미확인 정책 해석이 명시된다. 정책 문의 답변은 사전 승인 보장이 아니며 최종 출시는 심사 결과에 따른다. 문의 전송·콘솔 업로드는 별도 운영 단계이다. [실행 코드 정책](https://support.google.com/googleplay/android-developer/answer/16559646?hl=en)

**R5 — 개인정보·라이선스·환경 안내를 release에 제공**

- [ ] 공개 설정에 `개인정보처리방침`, `데이터 보관·삭제`, `환경·외부 도구 안내`, `오픈소스 라이선스·소스`를 추가한다. 간결한 하나의 읽기 화면으로 묶어도 된다.
- [ ] 현재 디버그 환경 화면에만 있는 PRoot 격리 한계·외부 서비스 로그인·검증 범위를 공개 안내로 옮긴다. 런타임 진단 셸·복구·훅 테스트까지 노출하지 않는다.
- [ ] 운영자 이름·지원 연락처·공개 정책 URL을 준비한다. 값이 없는데 가짜 사업자명이나 placeholder URL로 출시하지 않는다. 공개 페이지와 앱 내 안내의 버전을 맞춘다.
- [ ] 허가된 시험 계정과 민감정보 없는 프로젝트로 CLI 설치→로그인→사용→로그아웃을 확인한다. Z8의 로컬 데이터와 외부 CLI가 전송·보관하는 데이터, 기본 텔레메트리, 토큰 저장을 구분해 Data safety 답변 근거표를 작성한다. 실제 토큰은 증거에 저장하지 않는다.

주요 위치: [Z8SettingsActivity.java](../overlay/app/src/main/java/com/termux/app/Z8SettingsActivity.java), [Z8EnvironmentActivity.java](../overlay/app/src/main/java/com/termux/app/Z8EnvironmentActivity.java), [공개·디버그 분리 시험](../tests/test_prepare_app.py), `docs/BROWSER_PREVIEW.md`, `runtime/guest/AI_TOOLS.md`.

완료 기준: 실제 release에서 안내에 접근할 수 있고, 기본 보관·전송 설명은 오프라인에도 읽을 수 있다. 정책 URL이 공개 접속 가능하며 앱·문서·Data safety 답변이 일치한다. Z8가 모델 API를 직접 호출하지 않는다는 사실을 모든 기기 외 전송이 없다는 주장으로 확대하지 않는다. [User Data](https://support.google.com/googleplay/android-developer/answer/10144311?hl=en), [Data safety](https://support.google.com/googleplay/android-developer/answer/10787469?hl=en)

**R6 — 삭제와 로그아웃을 정확하게 제공**

- [ ] `미리보기 데이터 삭제`를 추가한다. 모든 프로젝트가 공유하는 WebView 쿠키·사이트 저장소·캐시에 영향을 준다는 설명 후 실행한다. 활성 미리보기를 멈추고 비동기 삭제 완료 후 결과를 표시한다. 프로젝트 삭제 때 다른 프로젝트의 웹 데이터를 몰래 함께 지우지 않는다.
- [ ] CLI 종료, 공식 CLI 로그아웃, 프로젝트 HOME 삭제, 공급자 측 토큰 폐기·계정 삭제의 차이를 안내한다. 버전별 의미가 검증된 경우에만 로그아웃 버튼을 제공한다. 임의의 인증 디렉터리를 통째로 삭제하거나 모든 CLI를 새 중앙 vault로 이관하는 기능은 이번 범위에 넣지 않는다.
- [ ] 현재 프로젝트 삭제가 프로세스 종료를 확인한 후 해당 소스·HOME·환경만 지우는 보호 장치를 유지한다. 히스토리·앱 공통 기록·WebView·외부 브라우저·외부 서비스의 삭제 범위를 구분한다.

주요 위치: [Z8BrowserPane.java](../overlay/app/src/main/java/com/termux/app/Z8BrowserPane.java), `Z8SessionChrome.java`, `Z8SettingsActivity.java`, `Z8Projects.java`, `runtime/guest/shellrc`.

완료 기준: 두 프로젝트의 테스트 origin에 쿠키·웹 저장소를 만든 뒤 삭제와 재실행으로 제거를 확인한다. CLI 인증·외부 브라우저 상태에는 영향을 주지 않는다. 가짜 인증 파일 fixture로 프로젝트 삭제와 다른 프로젝트 보존을 검증한다. 기존 `test_project_removal.py`, `test_workspace.py` 및 browser 시험을 활용하되 실제 WebView 저장소 시험을 별도로 실시한다. [WebView 저장소 API](https://developer.android.com/reference/android/webkit/WebView.html)

**R7 — 대응 소스와 고지 생성 자동화**

- [ ] 소스 패키징 도구를 추가한다(제안 이름 `tools/package-release-source.py`). 고정된 upstream 소스, overlay, 빌드·설치 스크립트, source/toolchain/builder lock을 명시적으로 모은다. `.gitignore`에서 빠지는 upstream을 누락하지 않고 `.local` 전체·키·인증파일을 통째로 포함하지 않는다.
- [ ] 실제 동봉 host/guest 패키지 목록을 provenance에 연결하고 정확한 원본 소스·패치·라이선스를 수집한다(제안 이름 `tools/collect-release-package-sources.py`). URL 목록만 남기는 것으로 대응 소스 제공을 끝내지 않는다. 사용자 기기에서 공급자로부터 직접 받는 파일과 Z8가 동봉·재호스팅하는 파일을 구분한다.
- [ ] Gradle/native/guest 라이선스 목록과 고지를 생성하고 앱에 포함한다(제안 이름 `tools/generate-release-notices.py`). 모르는 라이선스는 임의로 MIT로 분류하지 않고 검토 대상으로 남긴다.
- [ ] 최종 AAB, 소스 아카이브, 고지, runtime/guest manifest, 공개 소스 링크를 한 릴리스에 연결한다(제안 이름 `tools/verify-release-compliance.py`).

완료 기준: 깨끗한 디렉터리에 소스를 풀어 같은 빌드 소스와 입력을 재구성하고, 실제 배포한 GPL/LGPL 구성요소의 대응 소스가 추적된다. 바이너리 바이트까지 동일하다는 주장은 별도 시험 이후에만 한다. 일반 공개 링크를 택하면 비로그인 다운로드·해시 일치도 확인한다. 도구 구현 후에도 실제 대응 소스 확보·검토 상태를 확인한다. [기존 배포 고지](../THIRD_PARTY_NOTICES.md), [GPLv3](https://opensource.org/license/gpl-3.0)

**R8 — 코드로 해결되지 않는 배포 결정**

- [ ] Ubuntu guest를 수정 동봉할지, 공식 원본을 기기에서 구성할지, 다른 배포 모델을 택할지 결정한다. 패키지 라이선스와 사용자에게 보이는 상표 표현을 검토하며, 내부 출처 표기만으로 침해를 확정하거나 저작권 고지를 삭제하지 않는다. 공급 방식 변경이 Play 실행 코드 문제도 해결한다고 간주하지 않는다. [Canonical 조건](https://canonical.com/legal/intellectual-property-policy)
- [ ] 공식 Claude Code를 제품에서 설치·실행하도록 제공하는 운영자의 적용 약관·계약 상태를 확인한다. 바이너리 무수정, 인증 방법 유지, 사용자 본인 인증·직접 과금, 사용량 재판매·중개 없음이라는 구조를 유지한다. 사용자가 누르는 체크박스만으로 운영자 계약 의무가 해결되지는 않는다. [Claude Code 제공 조건](https://code.claude.com/docs/en/legal-and-compliance)
- [ ] Z8·공급자 이름과 아이콘의 최종 표현, 정책 페이지 책임자·문의처·소스 배포 책임자·키 보관 책임자를 정한다.

완료 기준: 각 결정의 담당자·확인 근거·최종 공급 방식이 기록되고 앱 동작/스토어 문구와 일치한다. 별도 서버·공용 AI 계정·구독 중개는 만들지 않는다.

**R9·R10 — 실제 출시 후보 검증과 콘솔 작업**

- [ ] 최종 release를 기준으로 새 설치·네트워크 중단과 재개·디스크 부족·프로젝트 전환·세션 종료·업데이트·삭제를 시험한다. 이전 debug APK 기록을 새 릴리스 검증으로 대체하지 않는다.
- [ ] API 36/37 대상 기기, 16 KiB 환경, 실제 Galaxy 폴더블에서 키보드/한글·접기·분할 화면·장시간 세션을 검증한다. minSdk 28을 유지하면 해당 최소 버전도 시험한다. 특정 기기를 확보하지 못하면 미검증으로 기록한다.
- [ ] Codex·Claude Code 각각 로그인 이후 작업·파일 변경·명령/테스트·권한 요청을 확인한다. 정상 sandbox가 실패하면 승인 우회로 통과 처리하지 않고 지원 범위 또는 제품 동작을 정리한다.
- [ ] Play가 생성·서명한 최종 APK의 loader 배치·권한·서명·업데이트를 확인한다. 내부 시험만으로 최종 심사 승인을 보장하지 않는다.
- [ ] 개발자 인증·적용되는 비공개 테스트, 개인정보/Data safety, 콘텐츠 등급·대상 연령, 광고 없음, FGS 설명·영상, 정확한 스크린샷·기기/도구 지원 범위·심사 접근 안내를 준비한다. 외부 서비스의 개인 비밀키를 심사 자료에 첨부하지 않는다.

**작성 당시 예정한 검증 순서**

작성 당시 다음 우선순위는 **최종 target 36 후보에서 셸·PRoot·Node/Python·사용자 작업이 유지되는지 검증하는 것**이었다. 아래는 그 시점의 검증 계획이며 완료 상태는 해당 후보의 별도 결과로 판단한다. 새로운 후보의 fresh install·기존 프로젝트 보존·16 KiB·뒤로가기·키보드·미리보기 삭제를 기록하고 실기기 시험으로 이어간다. 공개 운영자 값·정책 페이지·대응 소스 게시와 R8의 운영 조건은 별도로 완료한다. R1 실패 시 SDK를 낮춰 제출하거나 원격 실행으로 제품을 바꾸지 않고 원인을 고친다.

추가 개발에서 자동 분석 SDK, 자체 Z8 로그인, 결제, 범용 AI 채팅, 자동 승인·sandbox 우회, 모든 CLI 인증정보의 중앙 수집은 현재 범위에 포함하지 않는다. 업로드 가능 여부는 최종 후보의 실제 검증과 남은 운영 조건을 근거로 판단한다.
