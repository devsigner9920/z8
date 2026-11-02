# Z8

비루팅 Android 기기에서 Linux 개발 도구와 공식 AI CLI를 실행하는 개발 터미널입니다. 프로젝트별 작업 환경, 여러 터미널 세션, 로컬 웹 미리보기를 제공합니다.

**현재 개발 중이며 정식 배포·Play Store 출시는 완료되지 않았습니다.** 소스 공개와 스토어 출시는 별도 단계입니다. [현재 검증 범위와 제한](docs/RELEASE_STATUS.md)을 먼저 확인하세요.

## 무엇을 할 수 있나요?

- 프로젝트마다 HOME·소스·Linux 환경을 나누고 터미널 세션을 여러 개 엽니다.
- Python, Node.js, Git, gh, tmux와 빌드 도구를 기기에서 실행합니다. 파일 편집과 Git 작업은 터미널의 도구를 사용합니다.
- 개발 서버의 `localhost:포트`를 앱 안에서 미리 보고, 외부 링크와 인증 링크는 기기 브라우저로 엽니다.
- Codex·Claude Code 같은 공식 CLI를 명시적으로 설치하고 자신의 계정으로 인증해 사용합니다. CLI의 지원 여부와 제약은 도구·버전별로 다릅니다.

Z8은 공식 CLI를 실행하는 환경입니다. 자체 AI 서비스, 모델 요청 중개, 공용 계정이나 사용량 재판매 기능은 제공하지 않습니다. AI 기능의 네트워크 통신·계정·요금·이용 조건은 사용하는 외부 도구와 서비스에 따릅니다. Z8은 Termux, OpenAI 또는 Anthropic의 공식 제품이 아닙니다.

## 실행 환경과 주의점

| 항목 | 현재 설정 |
| --- | --- |
| Android | Android 9 / API 28 이상으로 설정 |
| CPU | ARM64 (`arm64-v8a`) |
| target / compile SDK | 36 / 36 |
| 개발 환경 | 기기 내부의 PRoot Linux, 루팅·별도 Termux 앱 불필요 |
| 화면 | 폴더블·태블릿 중심, 창 크기에 따라 세션 목록 조정 |

최소 SDK는 호환성 보증 범위가 아닙니다. 기본 환경을 준비할 때 다운로드와 저장 공간이 필요하며, 프로젝트마다 쓰기 가능한 환경을 별도로 보관합니다.

**PRoot는 보안 VM이나 프로젝트 간 보안 경계가 아닙니다.** 프로젝트들은 Android 커널과 앱 UID를 공유합니다. 신뢰하지 않는 명령이나 AI 도구가 실행하는 코드는 앱이 접근할 수 있는 데이터에 영향을 줄 수 있습니다. Codex의 기본 Linux sandbox는 시험한 PRoot 환경에서 정상 동작하지 않았으며, 일반 Linux와 같은 격리를 기대하면 안 됩니다.

현재 앱의 작업 환경은 로컬 실행 중심입니다. 앱에서 SSH 호스트를 관리하거나 원격 세션으로 연결하는 기능은 제공하지 않습니다.

## 빌드와 기여

[빌드 안내](BUILDING.md)에서 개발 도구 준비, 진단 APK, Linux 런타임, 제출 후보의 차이를 설명합니다. 현재 개발 도구 준비 경로는 macOS ARM64 기준이며, 런타임 소스 빌드에는 Linux Docker 환경을 사용합니다.

```sh
python3 tools/setup-toolchain.py
python3 tools/prepare-app.py --mode diagnostic
python3 tools/generate-release-notices.py --allow-incomplete
python3 tools/build-app.py --mode diagnostic
```

위 명령은 Linux 환경을 포함하지 않는 진단용 APK를 만듭니다. `--allow-incomplete`는 개발용 고지 생성을 허용할 뿐, 출시 검토를 완료 처리하지 않습니다. 실제 프로젝트 Linux 환경이 필요한 빌드는 빌드 안내의 runtime 절차를 따르세요. 빌드 도구는 `.local/`, 결과물은 `artifacts/`에 생성됩니다.

- [기여 방법과 테스트](CONTRIBUTING.md)
- [보안 문제 비공개 신고](SECURITY.md)
- [출시 상태와 검증 한계](docs/RELEASE_STATUS.md)
- [소스 공개 준비 절차](docs/OPEN_SOURCE_RELEASE.md)
- [프로젝트 Linux 환경](runtime/guest/README.md)

## 라이선스

Z8 애플리케이션은 Termux 앱 코드를 바탕으로 하며 기본 라이선스는 **GPL-3.0-only**입니다. [라이선스 전문](LICENSE)을 포함합니다. 파일·모듈별로 Apache-2.0, MIT 등 별도 라이선스와 예외가 적용되는 부분은 원래 조건을 유지합니다. [제3자 고지](THIRD_PARTY_NOTICES.md)와 각 파일의 고지를 확인하세요.

선택적으로 설치하는 CLI, Ubuntu 패키지와 기타 의존성에는 각각의 라이선스·이용 조건이 적용됩니다. 소스 저장소 공개만으로 모든 바이너리 배포 의무가 충족되는 것은 아닙니다. 바이너리를 배포할 때의 대응 소스와 고지 준비 절차는 [배포 라이선스 안내](docs/RELEASE_LICENSES.md)에 있습니다.
