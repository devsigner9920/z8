# GitHub 공개 준비

2026-11-02. 이 절차는 소스 저장소 공개와 앱 바이너리 출시를 구분한다.
운영자 표시명은 **romi**, 공개 문의처는 **ethsy2462@gmail.com**이다.
사용자가 지정한 GitHub 계정은 `devsigner9920`이다. 원격 작업 전 연결 도구가
반환하는 실제 로그인명과 저장소 소유자를 확인한다. 계정 이름만으로 저장소가
생성되었거나 접근 권한이 확보됐다고 판단하지 않는다.

## 공개할 내용

- Z8의 `overlay/`, `runtime/`, `tools/`, `tests/`, `docs/`와 공개 빌드 설정.
- 루트 `LICENSE`(GPL-3.0-only), `LICENSES/`의 원문 고지와 예외,
  `THIRD_PARTY_NOTICES.md`, 기여·보안 신고 안내.
- `.github/`의 소스 배포 검사. 자동 게시·서명·릴리스 업로드는 수행하지 않는다.
- 로고·Prism 이미지와 재생성 입력. 유지관리자가 2026-11-02 수정·재배포 권리 및
  GPL 공개를 확인했다. Material Icons 등 제3자 자산에는 원래 라이선스를 적용한다.

`.git/`, `.local/`, `artifacts/`, `reports/`, `design-qa.md`, 인증 파일·서명키,
완료된 운영자 심사 기록과 이전 릴리스에서 생성한 고지는 공개 저장소에서 제외한다.
공개 고지는 실제 배포할 소스·패키지 입력으로 다시 생성한다.

## 검토용 소스 폴더 만들기

```sh
python3 tools/prepare-public-repo.py
```

명령은 `artifacts/public-repo/` 아래에 해시로 구분된 소스 폴더, ZIP, 파일별 SHA-256
목록을 만든다. Git 커밋·원격 저장소 생성·업로드는 하지 않는다. 같은 산출물이
이미 있으면 덮어쓰지 않는다. 재검증에는 새 `--output` 경로를 지정할 수 있다.

포함 경로를 명시적으로 선정하고, 비밀정보 파일명·심볼릭 링크·과도한 파일 크기·
일부 알려진 인증 토큰 형식을 검사한다. 검출 메시지는 파일명과 분류만 표시한다.
패턴 검사를 모든 민감정보가 없다는 보증으로 사용하지 않는다. 첫 게시 전 파일
목록과 실제 내용을 검토한다. 작업 폴더 전체 대신 이 공개용 소스 폴더를 사용한다.

## 첫 저장소 연결

공개 저장소는 [devsigner9920/z8](https://github.com/devsigner9920/z8)이다.
기존 저장소에서 작업할 때는 내용을 읽고 해당 프로젝트인지 먼저 확인한다.
기존 파일·브랜치·가시성을 무조건 덮어쓰거나 변경하지 않는다.

공개 준비 ZIP은 일반 GitHub 저장소용이다. 자동 생성되는 GitHub의 Source code ZIP도
그 시점의 저장소 파일만 포함한다. 두 ZIP 모두 동봉 런타임 패키지까지 포함하는
바이너리 대응 소스 배포를 대신하지 않는다.

계정·저장소 확인 후 공개용 파일을 첫 커밋으로 올리고 원격 파일 목록과 커밋을
다시 읽어 확인한다. 이 문서에는 토큰·키를 넣지 않으며 GitHub 로그인 비밀번호를
커밋하거나 원격 URL에 포함하지 않는다.

## 소스 검사

GitHub Actions의 `Source distribution checks`는 Python 3.12에서 공개 소스·라이선스
포함, 비밀정보 제외, 서명·배포 경계, 네이티브 정렬 검사기를 검증한다. 모든 action은
정확한 커밋으로 고정하고 `contents: read`만 사용한다. 전체 Android 빌드나 실기기
시험을 수행하는 워크플로가 아니다. 로컬 캐시가 필요한 Groovy 검사는 깨끗한
환경에서 건너뛸 수 있으며 건너뛴 검사를 통과했다고 보고하지 않는다.

같은 검사는 로컬에서도 실행할 수 있다.

```sh
python3 -m unittest discover -s tests -p test_public_source.py -v
python3 -m unittest discover -s tests -p test_release_compliance.py -v
python3 -m unittest discover -s tests -p test_release_build.py -v
python3 -m unittest discover -s tests -p test_native_alignment.py -v
python3 -m unittest discover -s tests -p test_signing_identity.py -v
```

## 개인정보처리방침과 릴리스 소스 주소

개인정보처리방침 페이지의 원본은 [privacy.html](privacy.html)이며, 게시 주소는
[Z8 개인정보처리방침](https://devsigner9920.github.io/z8/privacy.html)이다.
GitHub Pages는 `main` 브랜치의 `docs/` 폴더를 사용한다. 앱을 배포하기 전에 이 주소가
로그인 없이 열리는지 확인한다. [이전 초안](PRIVACY_POLICY_DRAFT.ko.md)은 참고용이다.

앱의 `sourceUrl`에는 해당 버전의 완전한 대응 소스 ZIP을 직접 받는 주소를 사용한다.
예를 들어 실제 저장소와 태그가 확정된 후 `releases/download/<tag>/z8-source.zip`처럼
파일명을 먼저 정한다. 소스 설정에 소스 ZIP 자체의 해시를 넣으면 순환 의존성이 생긴다.
SHA 파일명으로 생성된 로컬 ZIP은 고정된 `z8-source.zip` 이름으로 Release에 첨부한다.
현재 설정은 `v0.1.0-rc1` 소스 미리보기 릴리스의 `z8-source.zip`을 가리킨다.
소스 미리보기 공개는 APK/AAB 배포 또는 최종 대응 소스 검토 완료를 뜻하지 않는다.

## 앱 바이너리를 공개할 때

1. 실제 정책·소스 주소와 릴리스 설정을 확정한다.
2. [대응 소스 절차](RELEASE_LICENSES.md)에 따라 정확한 host/guest 패키지 소스까지
   포함한 ZIP을 만들고, 고지를 생성한 뒤 후보 APK/AAB를 다시 빌드한다.
3. 소스 ZIP과 배포 파일의 해시·고지·명세를 연결하고 공개 다운로드를 확인한다.
4. 해당 새 후보의 필요한 기기·인증·정책 검증을 마친다. [출시 상태](RELEASE_STATUS.md)를
   확인하고 과거 후보 결과를 현재 파일의 시험 결과로 표시하지 않는다.

소스 공개 준비 완료는 Google Play 제출, 공급자 승인 또는 바이너리 재현성 보증이 아니다.
개발 키·업로드 키를 공개 소스에 포함하지 않는다. [빌드 절차](../BUILDING.md)와
[제3자 고지](../THIRD_PARTY_NOTICES.md)를 함께 따른다.
