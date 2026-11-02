# ADR-0002 · G0 진단 APK와 런타임 APK

- 상태: 첫 구현에 적용, 기기 검증 대기
- 날짜: 2026-10-03

## 결정

G0를 재현 가능한 Android 빌드와 자체 prefix Linux 공급으로 나눈다. 먼저 Termux의 PTY·터미널·서비스를 유지한 진단 APK를 빌드한다. 진단 모드의 명시적인 셸은 `/system/bin/sh`이며 화면에 Linux 미설치 상태를 표시한다. bootstrap 미포함 상태에서 upstream bootstrap 다운로드를 시작하지 않는다.

runtime 모드는 별도로 빌드한 bootstrap의 앱 ID, prefix, ABI, 해시를 확인한 뒤에만 포함한다. `com.termux`용 바이너리를 앱 ID만 바꿔 재사용하지 않는다. Java namespace와 JNI symbol은 원본대로 남기고 설치 package·provider authority·실행 prefix만 z8로 바꾼다. private development key로 서명하고 upstream 공개 테스트 키를 사용하지 않는다.

minSdk 28, targetSdk 28, compileSdk 36, ARM64 한 ABI로 시작한다. target을 낮게 설정한 것은 upstream의 쓰기 가능한 앱 prefix 실행 구조를 시험하기 위한 선택이다. Android 17 설치·프로세스 정책을 통과했다고 판단하지 않는다. 설치 정책 우회를 제품 시험에 사용하지 않는다. 최신 target을 지원하는 별도 실행 구조나 배포 정책은 G0 증거를 보고 결정한다.

## 범위와 후속 작업

현재 launcher는 기기 정보를 위한 native Activity이고 제품용 폴더블 UI가 아니다. 프로젝트/환경 데이터 모델, tmux 및 PRoot 수명주기, Claude·Codex 실제 작업, 훅 수신/알림은 후속 구현이다. 앱 화면을 닫거나 회전할 때 세션을 종료하지 않는 upstream 서비스 구조는 유지하며 실제 동작을 측정한다.

진단 APK 성공은 G0의 일부 준비 작업이다. Android 셸은 PRoot guest나 Termux host 도구의 호환성 증거가 아니다. 빌드, 에뮬레이터, 실기기 결과를 각각 구분해 기록한다. APK가 정상적으로 만들어져도 G0 전체 상태는 필수 수용 시험 전까지 NOT TESTED다.
