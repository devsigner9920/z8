# z8 실행 가능성 및 성능 검증 계획

작성일: 2026-10-03. **모든 실행 결과는 NOT TESTED**다. 이 문서는 앞으로 실행할 시험과 판정 기준이며 측정 보고서가 아니다.

2026-10-05 사용자 확정: **MVP는 Local only, Remote는 후속 범위**다. 아래 원격 SSH·tmux·알림 시험(AT-13·AT-21·B08)은 향후 검증 항목으로 보존하며 현재 MVP의 합격 게이트에 포함하지 않는다.

G0는 독립 APK·비루팅 로컬 실행·두 AI CLI·세션 지속성의 성립을 확인한다. 기능 화면을 많이 만드는 것보다 실패 조건을 빨리 드러내는 것이 목적이다. 제품 정의는 [구현 명세](../Z8_IMPLEMENTATION_SPEC_v0.2.md), 최적화 가설의 근거는 [연구 문서](../research/OPTIMIZATION_RESEARCH.md)를 따른다.

## 1. 시험 프로필과 재현 정보

| 프로필 | 역할 | 현재 상태 |
|---|---|---|
| D1 | 사용자 보고 Galaxy Fold z8 / Android17 / RAM 약12GB, stock 설정 | 정확한 모델·빌드·RAM·ABI·page size 미확인 |
| D2 | ARM64 / RAM 8GB 폴더블 또는 태블릿, 가능한 Android17 | 확보 전. 에뮬레이터로 성능 합격 대체 불가 |
| D3 | Android16 비교 실기기, ARM64 | 선택적 후속 비교 |
| D4 | 16KB page-size 기기 또는 시스템 이미지 | 설치·실행 검증용. D1이 16KB라면 동일 기기로 가능 |

매 실행에 `runId`, 날짜, 앱 commit, APK hash, 서명 인증서 fingerprint, applicationId, min/target/compile SDK, 제조사·모델 코드, OS/API·빌드 지문, ABI, RAM total/available, page size, runtime manifest hash, PRoot/tmux/distro/CLI 버전, 테스트 저장소 commit, 전원·배터리·thermal·화면·네트워크·절전 조건을 기록한다.

실기기 진단 전까지 사용자 보고값을 관측값 필드에 채우지 않는다. serial, 토큰, 개인 저장소 내용은 결과 파일에 넣지 않는다. 앱 로그·OS trace에서 수집 불가능한 값은 `UNAVAILABLE`로 남긴다.

ADB와 Android Studio는 개발 중 관측·테스트 트리거에 사용할 수 있다. 사용자의 일반 실행을 위해 low-target install bypass, phantom-process 제한 해제, memory limiter 무시, root·Shizuku를 요구하면 제품 기준에서는 실패다. 이런 정책 변경 실험을 별도로 하더라도 기본 합격 결과와 섞지 않는다.

## 2. 최소 시험용 앱과 데이터

G0 앱은 설치/진단, 프로젝트 A/B 생성, 도구 설치, 실제 터미널, 세션 목록/재연결/종료, 비밀값 제외 결과 내보내기까지만 필요하다. 실제 런타임을 대체하는 mock은 호환성 증거가 될 수 없다.

기능용 fixture는 외부 서비스 없이 테스트 가능한 작은 Git 저장소로 만든다. Python 또는 Node 소스 2~5개, 실패하는 단위 테스트 하나, 한글·공백·따옴표가 들어간 경로, symlink와 권한 확인용 파일을 포함한다. AI에게 함수 수정과 테스트 실행을 요청하고 실제 Git diff·exit code를 확인한다. 네트워크/계정이 필요한 AI 실험과 로컬 개발 도구 벤치마크는 분리한다.

성능 fixture는 seed와 생성 규칙을 고정한다.

| 세트 | 구성 | 목적 |
|---|---|---|
| W1 | 소규모 대표 앱, lockfile과 commit 고정 | 실제 개발 흐름 |
| W2 | 10,000 파일과 1,000항목 디렉터리, 총 용량 기록 | 탐색·검색·작은 파일 I/O |
| W3 | 100,000 파일 stress 세트, 생성물 디렉터리 포함 | 확대 시 중단·페이지 처리·메모리 제한 확인 |
| W4 | ANSI/UTF-8/한글/줄바꿈/긴 행을 포함한 출력 replay | terminal 처리·누락·jank |
| W5 | 1Hz sequence와 timestamp를 파일에 기록하는 작업 | 백그라운드 연속 실행, 네트워크 없는 기준 |

## 3. G0 필수 게이트

| Gate | 절차 | 통과 기준과 남길 증거 |
|---|---|---|
| G0-01 독립 설치 | 별도 Termux 없는 D1에 기본 설치 UI로 자체 서명 APK 신규 설치·업데이트 | 정책 해제 없이 설치, 앱 ID/서명/hash 기록, 사용자 데이터 유지 |
| G0-02 prefix | 자체 host 셸·loader·tmux·PRoot 실행, host 패키지 의존성 확인 | `com.termux` 경로/별도 앱 의존 없음. shebang·동적 링크·인증서·DNS 확인 |
| G0-03 이미지 | hash/digest 검증, 다운로드 취소·재개·압축해제 실패·용량 부족 주입 | 경로 이탈하는 archive entry 거부, 부분 환경 READY 금지, 재시도 성공 |
| G0-04 guest | A/B 환경 설치, apt 패키지·Node/Python·Git·gh 실행 | root 없이 spawn·파일 권한·symlink·TLS·DNS 동작. 실패 세부 기록 |
| G0-05 분리 | A에만 HOME 설정·환경변수·패키지·auth fixture 저장, B에서 기본 경로 확인 | B에 자동 상속/bind 없음. 실제 PRoot argv와 bind 목록 보관. 보안 격리 판정으로 확대하지 않음 |
| G0-06 tmux | host/guest 배치와 workspace 서버 단위 비교 | create/attach/detach/resize/exit·자식 종료를 관측, 하나의 서버 종료가 타 프로젝트에 미치는 영향 기록 |
| G0-07 Claude | 설치→version→로그인→repo 읽기→수정→자식 셸→테스트→종료→지원 resume | diff와 테스트 결과 확인. sandbox/approval 실패는 별도 칸, 화면 캡처만으로 통과 불가 |
| G0-08 Codex | G0-07과 동일한 독립 fixture 실행 | 도구/버전별 실제 결과. Claude의 성공을 전용하지 않음 |
| G0-09 순차 전환 | Claude가 만든 변경을 종료 후 Codex에서 읽기·후속 수정 | 같은 source, 독립 대화, 변경 상태와 테스트 일치 |
| G0-10 UI 재연결 | 회전·접기/펼치기·멀티윈도우·프로젝트 전환 총20회 | locator/launchId 유지, 신규 CLI 실행 0회, PTY 크기 정상, draft·스크롤 보존 |
| G0-11 백그라운드 | W5 + 별도 CLI 실제 작업으로 앱 이탈·화면 꺼짐 시험 | 아래 지속성 표에 따라 생존과 상태 정확도를 별도 판정 |
| G0-12 중단 | OS 강제 종료, FGS Stop, 재부팅 후 수동 진입 | 소실 세션 INTERRUPTED, 알 수 없는 원인은 UNKNOWN, AI/push/build 자동 재실행 0회 |
| G0-13 native 호환 | 4KB/16KB별 JNI·host ELF·guest libc/loader·Node/Python·CLI 실행 | 해당 page-size 프로필 전체 성공. APK 설치만으로 통과 불가 |
| G0-14 코드 보존 | rootfs 재생성·취소·실패, source tree hash 전후 비교 | source hash 일치, env generation 일관, 인증 이관 범위 일치 |
| G0-15 자원 | 8GB 목표 워크로드, build 병렬도 1/2/4, workspace 1/3/5 비교 | 프로세스·메모리·열·지연 기록. 기본 1 AI+Shell+가벼운 server에서 OS 중단 없이 완료 |
| G0-16 종료 정리 | 모든 로컬 세션 및 Operation 종료/취소, 설치 오류, terminal 0개에서 clone 수행 | 활성 lease 동안 FGS/환경 유지, 마지막 lease 이후 wake lock 해제·불필요 FGS 종료. 자식 미정리는 표시 |
| G0-17 훅 기능 조사 | CLI별 권한·질문·계획 검토 훅을 실제 발생시키고 guest helper→앱 통로 확인 | tool/version/event/mode별 지원표, 원래 승인 흐름 불변, 알림 권한별 결과. 해당 버전 미지원은 NOT_SUPPORTED로 구분 |

G0-01/02/04/07/08/10/11의 기본 모드가 통과하지 않으면 “요청한 로컬 개발 앱이 성립했다”고 결론내리지 않는다. 일부 도구 성공은 부분 결과다. D2 미확보 상태에서는 **8GB 지원 NOT TESTED**, D4 미검증 시 **16KB 지원 NOT TESTED**를 유지한다.

### 3.1 백그라운드 지속성 매트릭스

| 조건 | 제안 시험 길이 | 판정 |
|---|---|---|
| 다른 앱 사용, 화면 켜짐, 일반 전원 정책 | 30분 × 3회 | 작업 생존·동일 세션 복귀 모두 필요 |
| 화면 꺼짐, 계속 실행 on, 일반 전원 정책 | 30분 × 3회 | W5 연속 sequence·시간 간격·세션 생존 확인. 지속 실행 지원은 생존해야 PASS |
| 화면 꺼짐, 계속 실행 off | 30분 × 3회 | 생존/중단 관측. on 모드의 성공으로 대체하지 않음 |
| 충전/비충전, 장시간 대표 작업 | 각 2시간 × 1회 이상 | thermal·메모리 추세·성공률·배터리 기록, 무중단 보증으로 확대하지 않음 |
| 배터리 세이버·OEM 제한 모드 | 각 30분 | 지원 조건 기록. 유지 실패와 중단 표시 성공을 별도 칸에 기록 |
| Wi-Fi→모바일/오프라인→복귀 | 각 3회 | 프로세스와 AI 네트워크 오류 구분, 요청 중복 실행 없음 |

W5 시간 간격이 늘어나면 프로세스가 살아 있어도 계속 CPU를 받았다고 판단하지 않는다. 네트워크 없는 W5 성공도 AI 서버 연결 유지의 증거가 아니다. 사용자 FGS 중지와 OS force-stop, recent-apps 스와이프를 같은 이벤트로 처리하지 않는다.

## 4. G1 이후 기능 수용 시험

| ID | 절차 | 통과 기준 |
|---|---|---|
| AT-01 | 한글 조합 중 fold/unfold·IME 열기/닫기·외장 키보드 전환 | 중복/유실/의도하지 않은 Enter 없음 |
| AT-02 | Ctrl/Alt/Esc/Tab/방향키, 텍스트 선택 복사, Ctrl+C interrupt | 복사와 SIGINT 구분, CLI별 키 동작 확인 |
| AT-03 | 트리에서 여러 폴더 선택 | 기존 터미널 stdin 입력 0회, 새 터미널만 선택 cwd |
| AT-04 | CLI가 파일을 반복 수정하는 동안 편집·저장 | 감지 가능한 충돌 표시, draft·직전 복구본 유지, 미관측 경쟁 한계 기록 |
| AT-05 | symlink, hardlink, 밖으로 나가는 경로, 공백/한글/개행/따옴표 | 오대상 저장·shell injection 없음, 미지원 경로는 손상 없이 거부 |
| AT-06 | 1,000개 디렉터리 항목·10,000 파일·큰 diff 열기/취소 | 전체 tree 선로딩 없음, 취소 반영, pagination, OOM/ANR 없음 |
| AT-07 | clone→issue→branch→수정→stage→commit→push→PR→review→checks | CLI·서버·UI 일치, 제출 전 대상과 내용, 결과 ID/URL 확인 |
| AT-08 | UI/CLI가 Git 동시 변경, hook 실패, pull divergence | lock 임의 삭제·자동 discard 없음, 실제 실패와 최신 상태 표시 |
| AT-09 | PR 생성/리뷰 전송 후 네트워크 차단 | 재조회로 성공 여부 조정, 중복 제출 방지, 불명 시 UNKNOWN |
| AT-10 | PR head가 바뀐 뒤 이전 diff line 리뷰 제출 | 새 SHA/diff로 위치 재검증, 잘못된 줄 제출 방지 |
| AT-11 | 권한 만료·rate limit·오프라인 | cache의 마지막 갱신 시각과 오류 구분, 과도한 재시도 없음 |
| AT-12 | font 확대·TalkBack·600/840/1200dp 경계·높이 부족 | 핵심 동작 접근 가능, 힌지/IME에 입력 영역 가림 없음 |
| AT-13 | SSH host key 최초 확인·변경·단절·원격 tmux 재접속 | 원격 종료를 추정하지 않음, 로컬 토큰 자동 복사 없음 |
| AT-14 | backup·진단 export·앱 자동 백업 규칙 | auth/key/.env 제외 정책과 미리보기 일치, plaintext fallback을 숨기지 않음 |
| AT-15 | 백그라운드·화면 꺼짐 중 실제 권한 요청/질문/계획 검토 생성 | 지원되는 이벤트가 해당 프로젝트의 응답 필요 목록과 허용된 알림 채널에 게시됨. helper 수신→게시 p95 2초 이내를 제안 목표로 측정; CLI 자체 이벤트 지연은 별도 |
| AT-16 | 알림 여러 개, 접기/펼치기 후 예전 알림 탭 | 정확한 workspace/session/launch로 이동, 자동 승인·Enter·새 CLI 실행 0회 |
| AT-17 | 알림 전에 CLI에서 답변, 중복/역순 이벤트, helper ACK 유실, 세션 종료 | 중복 게시·소리 억제, 확인 가능한 해결만 RESOLVED, stale 요청은 현재 대기로 오표시하지 않음 |
| AT-18 | 알림 권한 거절·채널 off·DND·잠금 화면·앱 강제 종료 | 앱 내 목록/차단 상태 정확, 본문 노출 정책 일치, 도달을 보장했다고 표시하지 않음 |
| AT-19 | helper 실패/timeout/큰 payload/다른 launch 이벤트, 훅 미신뢰 | 기존 CLI 승인 흐름 유지, 무승인 옵션/자동 허용 없음, 초과 payload·오연결 거부, hook 활성 상태 표시 |
| AT-20 | 기존 사용자 훅이 있는 환경에서 설치·업데이트·해제 | 기존 hook 정의 보존, z8 항목만 변경, 필요한 신뢰 검토 수행, tool 업데이트 후 capability 재검사 |
| AT-21 | SSH 단절 중 원격 요청 발생 후 재연결 | 단절 중 미전달 상태 표시, queued 이벤트 재검증, 오래된 요청/답변 replay 없음 |

## 5. 성능 목표와 측정 경계

아래는 **초기 개발 예산**이다. 아직 달성한 수치가 아니며 G0 기준선에 따라 ADR로 수정한다. 모든 결과에는 UI/host/guest·워크로드·화면 조건을 붙인다.

| 지표 | 제안 목표 | 측정 경계 |
|---|---|---|
| 로컬 키 입력→실제 echo 표시 | p95 ≤ 50ms | 로컬 echo fixture, 원격/AI 응답 시간 제외 |
| 살아 있는 세션 전환 | p95 ≤ 300ms | 사용자 선택→사용 가능한 terminal frame, 신규 PRoot 시작 제외 |
| warm 파일 트리 첫 표시 | p95 ≤ 200ms | 1,000항목 디렉터리 첫 viewport, 모든 파일 hash 제외 |
| cold 환경 진입 | 목표를 먼저 선언하지 않고 baseline 기록 | 설치/다운로드 제외한 새 guest Shell 준비 시간 |
| idle 앱+기본 UI 메모리 | PSS 300MiB 이하를 시작 예산으로 시험 | AI·guest·tmux는 별도 계측해 함께 보고. 합산 시 RSS 공유 page 중복 주의 |
| 화면 밖 보조 작업 | tree scan·GitHub polling·UI frame 0 | 명시적으로 실행 중인 사용자 작업과 서비스 상태 감시는 별개 |
| lock 정리 | 마지막 Session/Operation lease 종료 후 5초 이내 | instrumentation 예산, OS 전체 lock 통계와 혼동 금지 |
| 지속 처리량 | 30분 추세와 초기/마지막 5분 처리량 비교 | 발열 상태·전원·동시성 포함, 임의 절감률/향상률 목표 없음 |

터미널 처리량은 고정 byte 수와 replay 시간으로 보고한다. UI는 프레임마다 새 output 전체를 Compose state로 복사하지 않으며 ANSI parser와 PTY 읽기를 막지 않아야 한다. backlog가 커질 때 바이트를 버리기보다 backpressure와 렌더링 횟수 조절을 비교한다. 화면 밖에는 tmux scrollback 한도에 따른 보존 범위를 표시한다.

## 6. 논문 기반 비교 실험

| 실험 | 비교하는 한 가지 변화 | 주요 지표 | 채택 조건 |
|---|---|---|---|
| B01 경로 비용 | native/host 파일 API vs guest 반복 명령 vs guest 배치 명령 | 동일 작업 시간, CPU, process starts, 파일/결과 동일성 | UI 직접 파일 API/배치가 측정상 유리하고 경로 의미 보존 |
| B02 tmux 구조 | 공용 host server / workspace별 host / guest server | attach p95, RSS/PSS, process 수, 종료 영향, env 간섭 | 안정성 요구 우선, overhead를 근거로 topology 확정 |
| B03 file watcher | 전체 순회 vs 열린 디렉터리 watcher+복귀 시 재조회 | wakeups, 파일 변경 반영, scan 시간, 배터리 | 누락 보완이 있고 부가 비용 감소 |
| B04 화면 꺼짐 정책 | polling 유지 vs 부가 polling 중지 | 작업 완료, 에너지, network wakeup | 작업 생존을 훼손하지 않고 측정 개선 |
| B05 wake lock | off / 명시 owner·수명에 따른 on | 연속 실행, held duration, 종료 후 leak, 에너지 | 설정 의미와 수명 일치, leak 0 |
| B06 지속 성능 | build concurrency 1/2/4 | 완료시간, 30분 처리량, thermal, peak memory, child 수 | peak만 빠른 설정보다 안정적 완료와 장시간 효율 우선 |
| B07 terminal batching | output마다 invalidate vs frame별 합치기 | echo p95, frame time, ANSI correctness, CPU, memory | 문자/순서 손상 없이 지연 예산 충족 |
| B08 remote 재연결 | 통신 단절·지연 주입, 기존 tmux 확인 | 입력 중복, 불확실 상태, reconnect 시간 | 확인 전 명령 replay 0, 상태 표시 정확 |
| B09 작은 쓰기 | 표시용 통계·진단 로그 개별 쓰기 vs 제한된 배치 | DB commit 빈도/시간, UI stall, 쓰기량, crash 후 상태 | source/Git/환경 참조 내구성을 유지하며 비용 감소 |

B01의 host/guest 비교에는 libc·도구 버전·실행 경로 차이가 포함된다. 결과 전부를 PRoot의 ptrace overhead라고 해석하지 않는다. 순수 비용을 분리할 실험이 불가능하면 “전체 실행 경로 비용”으로 보고한다.

### 6.1 반복과 통계

- 기능 성공률: 실행 횟수와 실패 횟수를 그대로 제시하고 원인을 보관한다.
- 짧은 성능 실험: 동일 조건의 A/B 순서를 교차·무작위화하고 10회 이상 측정, median/IQR을 제시한다.
- p95 지표: 5개 독립 실행 블록에 총100개 이상 상호작용을 모으고 블록별 결과도 남긴다. 3~5회 실행의 p95를 정밀한 결론처럼 쓰지 않는다.
- warm/cold를 분리한다. 비루팅 기기에서 page cache 제거를 가정하지 않는다. 프로세스 새 시작과 OS filesystem cold cache를 같은 조건이라고 쓰지 않는다.
- 입력 latency는 앱 내부 timestamp 또는 trace로 경계를 명시한다. 고속 카메라 기반 end-to-end 측정이 없으면 전체 물리 키 입력 지연으로 부르지 않는다.
- AI 모델 네트워크 지연은 로컬 엔진 최적화 실험에서 제외하고, 실제 작업 완료는 별도 E2E 시험으로 확인한다.

### 6.2 에너지·발열 계측

동일 밝기·주사율·통신 방식·배터리 범위·초기 thermal 조건에서 비교한다. 배터리 소모 실험은 가능한 비충전 상태로 하고, 충전 중 지속 성능은 별도 프로필로 둔다. 서로 다른 폼팩터·SoC·OS의 결과를 합쳐 하나의 절감률로 만들지 않는다.

Perfetto/Android profiler, 접근 가능한 BatteryManager·PowerManager thermal API, CPU 시간·프로세스 관측을 사용한다. 이들은 전체 SoC 에너지를 항상 정확히 제공하지 않는다. 전류/전압 센서가 지원되고 단위·부호·sampling이 검증되면 적분 에너지를 추정하고, 외부 계측기가 있으면 대조한다. 지원되지 않는 경우 배터리 %는 거친 대리 지표로만 기록하며 정밀한 mWh를 만들어내지 않는다.

작업 실행 구간과 완료 후 60초 관측 구간을 따로 기록해 네트워크 tail·남은 watcher/lock 비용을 살핀다. 이 60초는 z8 실험 구간이며 모든 무선 장치 tail을 포괄한다는 논문 결론이 아니다. profiling 자체의 부하도 측정하고 고빈도 trace를 기본 제품 기능으로 계속 켜두지 않는다.

Android17 memory limit, OEM thermal/배터리 정책, phantom child 종료 가능성은 독립 관측 항목이다. 정확한 원인이 없으면 메모리 부족으로 단정하지 않는다. 진단 중 정책을 끈 결과는 stock 지원 근거에서 제외한다.

## 7. 결과 기록 양식

```yaml
run_id: TODO
status: NOT_TESTED # 실행 후 PASS / FAIL / BLOCKED 중 실제 결과 기록
device:
  user_report: "Galaxy Fold z8, Android 17, RAM 약 12GB"
  observed_model: null
  api_level: null
  build_fingerprint: null
  memory_total_bytes: null
  page_size_bytes: null
build:
  app_commit: null
  apk_sha256: null
  application_id: null
  sdk: {min: null, target: null, compile: null}
runtime:
  manifest_sha256: null
  proot_version: null
  proot_distro_commit: null
  tmux_version: null
  image_digest: null
tool: {name: null, version: null, auth_method: null}
conditions:
  keep_awake: null
  battery_saver: null
  charging: null
  thermal_start: null
  network: null
  window_dp: null
  posture: null
results:
  gate_id: null
  process_survived: null
  state_reported_correctly: null
  sandbox_capability: NOT_TESTED
  observed_exit_reason: null
  measurements_file: null
  redacted_evidence_files: []
limitations: []
```

FAIL과 BLOCKED를 구분한다. 로그인 계정이나 실기기를 확보하지 못한 경우 기능 실패로 단정하지 않고 시험 불가 사유를 기록한다. 단, 실행하지 않은 시험은 PASS로 바꾸지 않는다. 개선 전·후 결과, fixture hash, 측정 스크립트 commit을 함께 보관해야 최적화 채택 근거로 사용할 수 있다.

## 8. 공식 검증 근거

제품 제약과 관측 API의 근거는 [Android 17 공통 변경](https://developer.android.com/about/versions/17/behavior-changes-all), [16KB 페이지](https://developer.android.com/guide/practices/page-sizes), [Termux 실행 환경](https://github.com/termux/termux-packages/wiki/Termux-execution-environment), [foreground app 사용자 중지](https://developer.android.com/develop/background-work/services/fgs/handle-user-stopping), [창 크기](https://developer.android.com/develop/ui/compose/layouts/adaptive/use-window-size-classes), [fold-aware API](https://developer.android.com/develop/ui/compose/layouts/adaptive/foldables/make-your-app-fold-aware)다. 이 문서들은 z8 측정 결과를 대신하지 않는다.
