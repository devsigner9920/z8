# 미리보기 데이터 삭제와 공개 안내

2026-11-01 구현. 앱 공통 WebView 데이터 삭제와 오프라인 개인정보·환경 안내를 제공한다. 기존 사용자 데이터로 삭제를 시험하지 않는다.

## 공개 설정

`Z8SettingsActivity`에서 개인정보처리방침, 데이터 보관·삭제, 환경·외부 도구 안내, 오픈소스 라이선스·소스로 이동한다. `Z8AboutActivity`는 release에서도 사용할 수 있으며 진단 화면과 별개다. 개인정보·보관·환경 안내는 네트워크 없이 읽을 수 있다.

운영 정보는 `BuildConfig.Z8_DEVELOPER_NAME`, `Z8_SUPPORT_EMAIL`, `Z8_PRIVACY_URL`, `Z8_SOURCE_URL`, `Z8_POLICY_DATE`만 사용한다. 값이 없는 candidate/debug에서는 가짜 연락처를 표시하지 않고 빈 링크를 숨긴다. 운영자 연락처가 없다는 사실은 그대로 표시한다. production release의 값·HTTPS 검증은 빌드 도구가 담당한다. 오픈소스 고지는 `assets/z8-licenses/third-party-notices.txt`를 읽어 14,000자 안팎의 페이지로 나눈다.

공개용 정책 초안은 [PRIVACY_POLICY_DRAFT.ko.md](PRIVACY_POLICY_DRAFT.ko.md)에 있다. 실제 값 치환·공개 및 Play Console 등록은 별도 제출 작업이다.

## 삭제 범위와 완료 기준

동의 창은 모든 프로젝트의 공유 프로필이라는 점, 로그인·저장 작업 손실, 열린 미리보기 중단, 되돌릴 수 없음을 설명한다. 프로젝트 파일·CLI 인증·외부 브라우저는 삭제 대상이 아니다. 터미널과 개발 서버는 계속 실행한다.

AndroidX WebKit 1.13.0의 `WebStorageCompat.deleteBrowsingData`를 사용한다. 이 API는 쿠키, 네트워크 캐시, JavaScript가 읽는 저장소와 서비스 워커 등 WebView 데이터를 삭제하고 완료 callback을 제공한다. 기능 지원을 먼저 확인한다. 미지원이면 어떤 삭제도 시작하지 않고 Android System WebView 업데이트를 안내한다. `WebStorage.deleteAllData`와 Web SQL origin 목록만으로 삭제 완료를 추정하는 대체 경로는 없다. [Android API 문서](https://developer.android.com/reference/androidx/webkit/WebStorageCompat)

`Z8PreviewDataOperation`은 시작 시 미리보기 생성 gate를 먼저 닫고 현재 `Z8BrowserPane`의 WebView를 제거한다. 이후에 삭제를 요청한다. RUNNING 중에는 새 내부 미리보기를 만들거나 주소를 자동 복원하지 않는다. provider callback에서만 COMPLETE로 전환하며 중복 요청과 오래된 callback을 무시한다. 예외 발생 시 성공이라고 표시하지 않는다. 웹페이지를 다시 열려면 사용자가 주소를 입력하거나 CLI에서 다시 요청해야 한다.

작업 상태는 프로세스 안에서 공유하고 설정 Activity는 표시 중에만 observer로 등록한다. 화면 회전·다른 화면 이동이 작업을 취소하지 않는다. 프로세스가 죽으면 완료를 추정하지 않으며 재실행 뒤 새로 요청할 수 있다. 삭제 이후 새로 연 페이지는 데이터를 다시 저장할 수 있다.

## 확인한 범위

- `tests/test_preview_data.py`: 실제 Java coordinator의 provider 완료 지연, 중복 요청, 미지원 무변경, 예외와 늦은 callback, observer 이탈·예외, 이전 요청 callback, 동기 callback. 6개 통과.
- 기존 `test_browser_*.py`: URL 허용 범위, 인증 요청 보관·유효성, Custom Tab에서의 복귀 상태. 23개 통과.

호스트 테스트는 Android System WebView의 실제 저장소 삭제 결과를 입증하지 않는다. Android 컴파일과 아래 폐기 가능한 테스트 데이터 검증은 통합 빌드에서 별도로 수행한다.

## 기기 검증 절차

1. 개인정보·삭제·환경·라이선스 화면을 release 또는 candidate에서 열고 네트워크 없이 내용을 읽을 수 있는지 확인한다. 공개 안내는 보이고 DEBUG 진단 항목은 release에 없어야 한다. 긴 라이선스의 다음·이전 페이지, 회전, 확대 글꼴을 확인한다.
2. 개인 계정과 분리한 테스트 앱/에뮬레이터에서 루프백 출처 두 개에 테스트 쿠키·localStorage·IndexedDB·Cache Storage·서비스 워커를 만든다. 외부 브라우저와 프로젝트 HOME에는 별도의 무해한 확인용 값을 둔다.
3. 삭제 확인창을 취소하면 저장 데이터·미리보기가 유지되어야 한다. 확인하면 열린 미리보기가 중단되고 완료 전 재진입·중복 요청이 거절되어야 한다. 설정을 닫았다 열거나 회전해도 조기 성공 표시가 없어야 한다.
4. 완료 후 두 출처를 다시 열어 테스트 값과 서비스 워커가 사라졌는지 확인한다. 다시 열면서 생긴 새 데이터는 이전 데이터와 구분한다. 외부 브라우저·프로젝트 HOME 확인용 값과 실행 중인 터미널·서버는 유지되어야 한다.
5. 기능 미지원 provider 또는 오류를 주입한 테스트 환경에서는 ‘삭제 완료’를 표시하지 않아야 한다. 결과·로그에는 URL·인증값·파일 내용이 없어야 한다.
