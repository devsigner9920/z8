# z8 논문 기반 최적화 설계

작성일: 2026-10-03. 대상: 비루팅 Android17, ARM64, RAM 8GB 이상 폴더블·태블릿에서 동작할 Termux·PRoot·tmux 기반 개발 앱.

논문의 역할은 z8의 최적화 가설과 측정 방법을 정하는 것이다. 아래 논문은 Galaxy Fold z8에서 이 구성이 성공하거나 일정 비율로 빨라진다는 증거가 아니다. **사용자 작업의 정확성·세션 생존·입력 반응을 보존한 상태에서 실기기 비교 결과가 나아질 때만 최적화를 채택한다.**

## 1. 조사 범위와 근거 수준

에너지·wake lock·백그라운드·발열과 실행 경로·컨테이너·터미널 통신을 나누어 Exa로 조사했다. 저자·학회·출판사 원문을 우선하고 일반 블로그의 성능 주장은 채택하지 않았다. 같은 논문의 중복 출판 페이지는 하나로 합쳤다.

두 조사 축의 Exa 검색 요청량은 합계 **85개 결과 슬롯**이다(에너지 55, 실행 경로 30; 각 검색의 `numResults` 합계). 이는 중복·무결과 요청을 포함하므로 85개의 서로 다른 원문을 읽었다는 뜻이 아니다. 최종 선별은 **논문 8편**이며, 7편은 원 논문 PDF, E1은 출판사 기록·초록과 저자 서지까지 확인했다. 보완한 공식 플랫폼 문서는 별도 근거로 취급한다.

근거 수준은 다음처럼 구분한다.

- **논문 관찰:** 원 논문이 그 실험 환경에서 확인한 사실.
- **z8 설계 가설:** 논문에서 착안했지만 z8에서 아직 검증하지 않은 선택.
- **현재 플랫폼 제약:** Android·Termux 공식 문서로 별도 확인할 사항.

발표 연도가 오래된 모바일 논문은 전력·열·백그라운드의 원리를 참고하는 데 쓴다. 당시 기기·3G 네트워크·Android 버전의 절감률을 현재 Wi-Fi/5G·Android17 성능으로 옮기지 않는다. 논문에서 요구하는 root·커널 수정·CPU 정책 조작은 z8의 실행 전제가 될 수 없다.

## 2. 에너지와 백그라운드

### E1 Wake lock 수명과 no-sleep 오류

**What is keeping my phone awake?: characterizing and detecting no-sleep energy bugs in smartphone apps** — Abhinav Pathak, Abhilash Jindal, Y. Charlie Hu, Samuel P. Midkiff. ACM MobiSys, 2012. DOI: `10.1145/2307636.2307661`. [출판사 기록·초록](https://dl.acm.org/doi/10.1145/2307636.2307661), [저자 출판 목록](https://engineering.purdue.edu/~ychu/publications/)

**확인 범위:** 출판 기록·초록 및 저자 서지를 확인했다. 이 문서에서는 원문 전체의 수치·검출 개수를 인용하지 않는다.

**논문 관찰:** 전원 제어 API의 잘못된 사용은 기능이 끝난 뒤에도 구성요소가 깨어 있는 no-sleep 오류를 만들 수 있다. 기능이 정상으로 보인다는 사실만으로 에너지 문제가 없다고 할 수 없다.

**z8 설계 가설:** ExecutionService가 실행 유지의 소유권을 관리한다. Session뿐 아니라 clone·설치·Git Operation에도 실행 lease를 부여하고, 명시적 keep-awake 정책에 해당하는 활성 lease에서만 partial wake lock을 요구한다. 시작 실패·취소·예외·마지막 실행 종료를 해제 경로로 검사한다.

**적용 한계:** 의도적으로 켜둔 유휴 셸은 자동으로 오류가 아니다. 낮은 CPU나 화면 비가시만으로 작업 완료를 판단하지 않는다. 이 연구는 Android17 FGS·Doze·OEM 정책하의 프로세스 생존을 보장하지 않는다.

**검증 연결:** B05·G0-16. lock 유지 시간과 owner 목록이 일치하고, 마지막 실행 lease 종료 후 해제되며, 실패 경로에도 잔여 lock이 없어야 한다.

### E2 CPU 시간만으로 에너지를 설명하지 않기

**Where is the energy spent inside my app? Fine Grained Energy Accounting on Smartphones with Eprof** — Abhinav Pathak, Y. Charlie Hu, Ming Zhang. ACM EuroSys, 2012. DOI: `10.1145/2168836.2168841`. [원 논문 PDF의 Columbia 대학 보관본](https://www.cs.columbia.edu/~lierranli/coms6998-11Fall2012/papers/eprof_eurosys2012.pdf), [저자 서지](https://engineering.purdue.edu/~ychu/publications/)

**확인 범위:** 대학 보관 원 논문 PDF의 방법과 결과. 저자가 연결한 원본 및 출판사 페이지 일부는 조회 timeout이 있었다.

**논문 관찰:** 장치의 전력 소비는 이를 유발한 코드의 실행 종료 후에도 이어질 수 있다. CPU 시간 비율만으로 에너지를 설명하기 어렵고, I/O 활동과 원인 연결이 분석에 중요하다.

**z8 설계 가설:** Git status·파일 watcher 이벤트를 묶어 중복 스캔을 줄이고, 작업 완료 후에도 별도 관측 구간을 둔다. CPU 시간, 네트워크 활동, wake lock, 에너지 추정치는 서로 다른 지표로 기록한다.

**적용 한계:** 원 연구의 오래된 Android/Windows Mobile 기기와 프레임워크·bionic·커널 계측은 현재 비루팅 APK에 그대로 이식할 수 없다. 당시 무선 tail 값과 절감률을 사용할 수 없다. watcher 최적화는 이 논문이 z8에서 실증한 결과가 아니다.

**검증 연결:** B03·B04. 완료 후 60초는 초기 관측창으로 두되, baseline 복귀 여부와 관측창 길이에 따른 민감도를 확인한다. 센서 미지원 시 배터리 %를 정밀한 mWh로 바꾸지 않는다.

### E3 화면 밖 부가 작업 줄이기

**Smartphone Background Activities in the Wild: Origin, Energy Drain, and Optimization** — Xiaomeng Chen, Abhilash Jindal, Ning Ding, Y. Charlie Hu, Maruti Gupta, Rath Vannithamby. ACM MobiCom, 2015. DOI: `10.1145/2789168.2790107`. [학회 원문 PDF](https://sigmobile.org/mobicom/2015/papers/p40-chenA.pdf)

**확인 범위:** 학회 원 논문. 연구의 HUSH 최적화와 측정 앱을 구분해서 읽었다.

**논문 관찰:** 다수의 Galaxy S3/S4 추적에서 화면이 꺼진 동안의 활동과 에너지 소비를 분석하고, 사용자별 효용에 따라 백그라운드 작업을 억제하는 HUSH를 제안했다. 계측 정밀도를 높이는 것 자체에도 비용이 있다.

**z8 설계 가설:** 화면 밖에서는 z8이 만드는 GitHub polling·전체 색인·diff prefetch·UI 렌더링을 중지하거나 줄인다. 사용자가 실행한 CLI·테스트·서버는 선택한 실행 유지 정책에 따라 계속 관리한다. 화면 복귀 시 실제 파일/Git 상태를 다시 읽는다.

**적용 한계:** HUSH의 OS 스케줄러 개입을 비루팅 z8이 수행할 수 있다는 근거는 아니다. 다음 화면 켜짐 때 사용되는 앱만 유용하다는 모델을 장시간 개발 작업에 적용하지 않는다. CLI 내부 타이머를 앱이 전부 통제할 수 없다.

**검증 연결:** B03·B04. 화면 꺼짐 중 작업 완료, 부가 작업 횟수, 복귀 후 상태 일치, 에너지를 함께 비교한다. profiler를 켠/끈 실행도 비교해 계측 오버헤드를 확인한다.

### E4 최고 순간 성능보다 지속 처리량

**Providing Sustainable Performance in Thermally Constrained Mobile Devices** — Onur Sahin, Ayse K. Coskun. ACM ESTIMedia, 2016. DOI: `10.1145/2993452.2994309`. [저자 연구실 원문 PDF](https://www.bu.edu/peaclab/files/2016/10/ESWEEK16_sahin.pdf)

**확인 범위:** 저자 연구실 원 논문 PDF.

**논문 관찰:** 모바일 장시간 부하에서는 SoC 외에 표면·배터리의 열 제약도 중요하다. 초기에 최대 성능을 내는 정책과 전체 시간 동안 성능을 유지하는 정책의 결과가 다를 수 있다.

**z8 설계 가설:** 관리되는 build 동시성을 1/2/4로 비교하고, 30분 이상 구간별 처리량과 입력 지연을 함께 본다. 발열이 높을 때 z8 자체의 새 색인·압축·다운로드 작업을 줄이며 사용자 작업을 조용히 종료하지 않는다.

**적용 한계:** 논문의 Nexus 5·Qualcomm 개발 기기·Odroid 결과를 Fold에 전용하지 않는다. 사용된 cpufreq·DVFS·thread mapping 제어는 z8의 비루팅 기능으로 채택하지 않는다. 이미 실행 중인 임의 CLI의 병렬도를 안전하게 바꿀 수 있다고 가정하지 않는다.

**검증 연결:** B06. 같은 초기 열 상태·밝기·전원·접힘 상태로 교차 반복하고, 5분 구간 처리량·완료 작업 수·p95 입력 지연·peak memory를 비교한다. 한 번의 짧은 build 시간만으로 기본값을 정하지 않는다.

## 3. 실행 경로와 터미널 연구

### R1 시스템 호출 가로채기 비용

**zpoline: a system call hook mechanism based on binary rewriting** — Kenichi Yasukata, Hajime Tazaki, Pierre-Louis Aublin, Kenta Ishiguro. USENIX ATC, 2023, pp. 293–300. [공식 서지](https://www.usenix.org/conference/atc23/presentation/yasukata), [원문 PDF](https://www.usenix.org/system/files/atc23-yasukata.pdf)

**논문 관찰:** §3.1.1은 ptrace tracer/tracee 전환·깨우기의 비용을 설명하고, §3.2는 실제 syscall 동작과 hook 자체 비용을 구분해 비교한다. 가로채는 호출이 많은 작업은 그 비용을 별도로 측정할 필요가 있다.

**z8 설계 가설:** 파일 항목마다 셸·PRoot를 시작하지 않고 UI 탐색은 Android 파일 API로 처리한다. guest에서 실행해야 하는 Git/도구 요청은 묶는다. UI file I/O, process startup, guest syscall-heavy 작업을 각각 비교한다.

**적용 한계:** 논문의 Intel Xeon/Linux 결과는 Android ARM64/PRoot 측정이 아니다. zpoline은 ARM과 호환되는 일반 대체 구현이 아니고 주소 0 mapping 조건도 요구한다. **zpoline 자체는 z8 런타임 후보에서 제외한다.** Git을 host로 옮겨 config/filter/hooks 의미가 달라지게 하는 최적화도 기본 채택하지 않는다.

**검증 연결:** B01. 가능한 경우 동일 ARM64 binary로 CPU-only와 `open/stat/read/close` 워크로드를 비교한다. libc·compiler·binary가 다르면 전체 실행 경로 차이라고 표시한다. PRoot 아래 중첩 strace/ptrace가 가능하다고 가정하지 않는다. 현재 PRoot의 ptrace 기반 구조는 [공식 설명](https://proot-me.github.io/)으로 별도 확인한다.

### R2 사용자 개발 환경과 커널 격리 구분

**Charliecloud: Unprivileged Containers for User-Defined Software Stacks in HPC** — Reid Priedhorsky, Tim Randles. SC17, 2017. DOI: `10.1145/3126908.3126925`. [DOI](https://doi.org/10.1145/3126908.3126925), [원 논문 PDF의 FOSDEM 보관본](https://archive.fosdem.org/2018/schedule/event/containers_scientific/attachments/paper/2411/export/events/attachments/containers_scientific/paper/2411/charliecloud.pdf)

**논문 관찰:** Linux user/mount namespace를 활용해 사용자 소프트웨어 환경을 구성하고 호스트 커널·장치·네트워크를 사용하는 단순 구조를 설명한다. 평가 대상은 HPC workload와 namespace runtime이다.

**z8 설계 가설:** “전체 OS 가상화”보다 프로젝트별 사용자 도구 환경에 집중한다. 다운로드 cache와 쓰기 가능한 rootfs/HOME, 소스 데이터 수명주기를 구분하고 생성·초기화·복구 비용을 측정한다. 이 저장 구조 자체가 논문의 검증 결과라는 뜻은 아니다.

**적용 한계:** unprivileged라는 단어가 같아도 Charliecloud namespace와 PRoot ptrace는 다르다. 논문의 작은 성능 차이를 Android PRoot에 적용하거나 보안 성질이 같다고 주장할 수 없다. Android에서 필요한 user namespace가 허용된다는 근거도 아니다.

**검증 연결:** B02·G0-05·G0-14. 환경 1→3→5개에 대한 저장량·idle process·메모리·attach 비용을 보고, 초기화 후 source hash를 검증한다. 논문의 수치로 tmux topology를 결정하지 않는다.

### R3 원격 터미널의 지연과 상태 동기화

**Mosh: An Interactive Remote Shell for Mobile Clients** — Keith Winstein, Hari Balakrishnan. USENIX ATC, 2012, pp. 177–182. [공식 서지](https://www.usenix.org/conference/atc12/technical-sessions/presentation/winstein), [저자 원문 PDF](https://mosh.org/mosh-paper.pdf)

**논문 관찰:** UDP 기반 화면 상태 동기화와 검증 가능한 예측 echo로 높은 RTT, IP 변경, 간헐적 연결에서 상호작용을 개선한다. 모든 입력이 예측 가능한 것은 아니며 잘못 예측한 화면은 수정해야 한다.

**z8 설계 가설:** 원격 연결 상태와 원격 프로세스 상태를 별도 표시한다. 재접속 후 기존 tmux를 확인하며 입력/명령을 몰래 재전송하지 않는다. 로컬 UI에서는 redraw 횟수를 묶을 수 있지만 PTY 바이트·ANSI parser 상태를 버리면 안 된다.

**적용 한계:** 2012년 trace의 응답 지연·예측 성공률을 현재 AI TUI·한글 IME의 성능으로 사용하지 않는다. 로컬 세션에 network echo 최적화를 넣을 이유가 없으며, AI CLI에 낙관적 echo를 임의 추가하지 않는다. 2026-10-05 확정한 MVP는 Local only이며 Remote는 보류했다. SSH+원격 tmux는 후속 원격 기능의 설계 후보이고 Mosh 도입 역시 현재 범위가 아니다. 이 논문은 Android background 생존의 근거가 아니다.

**검증 연결:** B08. 서버/라우터에서 RTT·packet loss·10/60초 단절을 주고 Wi-Fi↔모바일 전환, password·vim·AI TUI·한글·paste·resize를 검사한다. 시험 네트워크 조절 때문에 Android root를 요구하지 않는다.

### R4 작은 쓰기와 저장 내구성

**Revisiting Storage for Smartphones** — Hyojun Kim, Nitin Agrawal, Cristian Ungureanu. USENIX FAST, 2012. 동일 제목의 후속 ACM TOS 확장판과 구분한다. [공식 서지](https://www.usenix.org/conference/fast12/revisiting-storage-smartphones-0), [원문 PDF](https://www.usenix.org/system/files/conference/fast12/kim.pdf)

**논문 관찰:** random I/O와 잦은 동기식 SQLite 쓰기가 앱 지연에 영향을 준다. §5.5–5.6에서는 transaction 묶음으로 sync 비용을 나누고 임시·cache·영구 데이터의 요구를 구분하는 접근을 설명한다.

**z8 설계 가설:** 터미널 문자·키 입력마다 Room transaction을 쓰지 않는다. 표시용 통계·진단 로그는 배치·상한·순환 정책을 사용하고, source 저장·환경 참조 교체·중요 Operation 결과와 구분한다. 작업 상태를 재구성할 수 있어야 한다.

**적용 한계:** 오래된 Nexus One·Android·SD카드·수정 커널 조건의 속도 배수를 현재 저장소에 옮기지 않는다. 논문의 RAMdisk·커널 변경을 도입하지 않고, 최적화를 이유로 Git·소스 저장의 fsync/내구성을 전역으로 낮추지 않는다.

**검증 연결:** B09. 10K/100K 파일과 대량 터미널 출력에서 DB commit 빈도·UI stall·쓰기량·로그 상한을 측정한다. 앱 종료/재시작 후 영구 메타데이터를 확인하고, root로 OS cache를 비우는 대신 첫 실행/반복 실행 조건을 명시한다.

## 4. 구현에 반영한 선택

| 최적화 | 현재 구현·설계 가설 구분과 근거 | 실기기에서 확인할 것 |
|---|---|---|
| 파일 트리를 Android 내부 파일 API로 읽기 | **구현.** [Z8Files](../../overlay/app/src/main/java/com/termux/app/Z8Files.java)는 프로젝트 소스를 `DirectoryStream`으로 읽고 symlink를 따라가지 않는다. 파일 항목마다 셸·PRoot를 시작하지 않는다. | 경로·권한 처리의 정확성, 큰 폴더의 지연과 메모리. 실기기 성능 개선은 미측정. |
| 파일 검색의 탐색량 제한 | **구현.** [Z8FileSearch](../../overlay/app/src/main/java/com/termux/app/Z8FileSearch.java)는 결과 200개·방문 20,000개·탐색 예산 3초를 제한하고 중단 사유를 반환한다. 시간 제한은 순회 중 확인하는 협력적 제한이며 개별 파일 I/O의 완료 시간을 보장하지 않는다. | 큰 저장소에서 입력 반응, 제한 도달 표시, 취소·부분 결과의 정확성. 현재 상한이 최적값이라는 근거는 없음. |
| Git/GitHub 작업을 메인 스레드에서 분리하고 중복 접수 제한 | **구현.** [Git 화면](../../overlay/app/src/main/java/com/termux/app/Z8GitActivity.java)·[GitHub 화면](../../overlay/app/src/main/java/com/termux/app/Z8GitHubActivity.java)은 worker와 busy 가드를 사용한다. [Git 실행기](../../overlay/app/src/main/java/com/termux/app/Z8Git.java)는 명령별 시간·출력 상한을 두며, [GitHub 실행기](../../overlay/app/src/main/java/com/termux/app/Z8GitHub.java)는 clone·PR 작업에 공유 worker와 프로젝트별 lease를 둔다. 조회 요청 통합·watcher 이벤트 병합은 **미구현**이다. | 실제 subprocess 수, UI 지연, 취소·실패 후 최신성. 메인 스레드 분리만으로 총 CPU·전력 감소를 주장하지 않음. |
| 원격 주기 조회를 만들지 않고 비가시 화면의 상태 관찰 중지 | **구현 범위 한정.** [Z8GitHubActivity](../../overlay/app/src/main/java/com/termux/app/Z8GitHubActivity.java)는 사용자 요청으로 원격 데이터를 조회하며 원격 polling을 하지 않는다. 실행 중 clone·PR의 로컬 상태 관찰은 `onPause`에서 중지한다. 모든 화면의 렌더링·색인·CLI 내부 타이머를 제어하는 정책은 **설계 가설**이다. | 수락한 작업의 생존, 복귀 후 상태 일치, 화면 밖 부가 작업 횟수와 에너지. |
| AI 훅 전달·알림의 처리량과 저장량 제한 | **구현.** [Z8AttentionBridge](../../overlay/app/src/main/java/com/termux/app/Z8AttentionBridge.java)는 프레임 16 KiB·전체 읽기 기한 1초·저장 항목 256개 상한, 중복 이벤트 확인과 민감 내용 제외를 적용한다. 완료 이벤트는 알림을 생략한다. 실제 AI가 발생시킨 이벤트와 실기기 부하는 **미검증**이다. | 이벤트 누락·중복·상한 도달 시 동작, 알림에서 기존 세션 복귀, 이벤트 폭주 시 지연·쓰기량. |
| 명시적 owner 기반 wake lock | **설계 가설·미구현.** 프로젝트·설치·Git 작업의 공통 owner/lease에 따른 wake lock 수명 관리는 기존 Termux의 wake lock 기능과 구분한다. | 실패·취소·마지막 작업 종료 시 해제, 실제 owner와 lock 유지 시간 일치. |
| 작은 기본 build 동시성 | **설계 가설·미구현.** 앱이 관리하는 build 병렬도 정책과 기본값은 비교 실험 후 정한다. 현재 GitHub worker 수는 build 동시성 정책이 아니다. | 장시간 처리량·입력 지연·열·메모리 균형. |
| bounded terminal history/cache와 렌더링 batching | **설계 가설.** 기존 Termux 터미널을 사용하며, z8의 추가 history/cache 상한·렌더링 batching 최적화를 구현·검증한 것으로 취급하지 않는다. | 실제 PSS와 ANSI/UTF-8 정확성, 재연결 후 보존 범위. |
| 표시용 통계·진단 DB/로그 쓰기 배치 | **설계 가설·미구현.** 현재 [훅 상태 저장](../../overlay/app/src/main/java/com/termux/app/Z8AttentionBridge.java)은 이벤트별 `AtomicFile` 기록과 항목 상한을 사용한다. 이를 DB transaction 배치 구현으로 간주하지 않는다. | 중요한 상태·소스의 내구성을 유지하면서 쓰기 빈도·UI stall이 달라지는지 비교. |
| 프로젝트별 host tmux 관리 | **설계 가설·미구현.** [프로젝트 실행기](../../overlay/app/src/main/java/com/termux/app/Z8Guest.java)의 guest 실행과 tmux 수동 연결 시험 (비공개 내부 검증 기록: `reports/compatibility/tmux-continuity.json`)은 앱의 프로젝트별 tmux 생성·재연결 관리와 별개다. | 전역 환경 간섭·장애 범위와 서버 수 비용, 실제 작업의 연결 해제·재연결. |
| 무한 watcher·초 단위 전 프로젝트 polling | **현재 미구현·기본 미채택.** 도입하려면 필요한 범위·빈도를 별도 설계하고 검증한다. | 필요한 최신성을 유지하는 최소 관찰 범위와 빈도. |
| kernel/DVFS 변경·root를 요구하는 최적화 | **설계에서 제외.** 비루팅 요구와 맞지 않는다. | 비루팅으로 관측 가능한 지표 안에서 비교. |

터미널 렌더링 batching, 10,000행 scrollback, worker 기본 2개, 30분 지속 부하, 60초 후속 관찰창은 모두 **z8의 측정 시작점**이다. 논문이 제시한 보편적 최적값으로 인용하지 않는다.

## 5. 측정과 채택 규칙

각 변경은 [검증 계획 B01~B09](../validation/G0_VALIDATION_PLAN.md)의 한 실험에 연결하고, 동일 fixture·앱/runtime 버전·기기·화면·전원 조건을 기록한다. A/B 실행 순서를 교차하고 warm/cold를 구분한다. throughput만 보지 않고 입력 latency·작업 정확성·메모리·프로세스 수·중단 여부를 함께 본다.

수치 개선이 있어도 파일 결과가 달라지거나 명령이 중복 실행되거나 세션이 끊기면 채택하지 않는다. 여러 지표가 상충하면 낮은 메모리·낮은 동시성·명확한 상태 표시를 기본값 후보로 검토하고, 성능 우선 설정은 사용자가 선택할 수 있게 한다.

비루팅 기기에서 읽을 수 없는 에너지·thermal 세부값을 추정해서 사실처럼 기록하지 않는다. Android17의 현재 메모리 제한은 [공식 변경 문서](https://developer.android.com/about/versions/17/behavior-changes-all)로 별도 검증하고, 논문의 과거 OS 동작을 근거로 무효화하지 않는다.

## 6. 아직 증명되지 않은 것

이 조사를 통해 Android17에서 자체 prefix Termux·PRoot·Claude Code·Codex 조합이 동작했다고 결론내릴 수 없다. 8GB와 12GB에서의 메모리 예산, fold/unfold IME 안정성, 실제 백그라운드 생존, OEM 발열 정책, CLI sandbox 호환성은 G0 실험이 필요하다.

직접적인 Android17/해당 Fold의 PRoot 개발 워크로드 실측 논문을 확보했다는 주장도 하지 않는다. 그런 직접 근거가 없는 구간에는 upstream 공식 동작 설명과 z8 자체 측정을 사용한다. 최적화 완료는 문헌조사 완료와 다른 상태다.
