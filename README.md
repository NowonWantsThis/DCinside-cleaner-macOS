# DCInside Cleaner for macOS

<p align="center">
  <img src="docs/images/app-main.png" alt="DCInside Cleaner for macOS" width="760">
</p>

디시인사이드에 작성한 글과 댓글을 조회하고 정리하는 macOS용 GUI 포팅 버전입니다.

원작: [dlcjsdltlq/dcinside-cleaner](https://github.com/dlcjsdltlq/dcinside-cleaner)

## 기능

- 계정 로그인 및 작성 글·댓글 조회/삭제
- 진행률과 작업 로그 표시
- 프록시 및 선택적 2Captcha 설정

## 설치

[Releases](https://github.com/NowonWantsThis/DCinside-cleaner-macOS/releases)에서 최신 Apple Silicon용 ZIP을 내려받아 실행합니다.

현재 테스트 배포 중인 비공증 빌드입니다. macOS가 실행을 차단하면 Finder에서 앱을 Control-클릭한 뒤 `열기`를 선택하세요.

## 직접 실행 및 빌드

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt pyinstaller
python execute.py
pyinstaller --noconfirm --clean build-macos.spec
```

## 주의

삭제 작업은 되돌릴 수 없습니다. 실행 전 대상 갤러리와 작업 종류를 확인하세요. 계정 정보, 쿠키, API 키와 프록시 목록은 저장소에 포함하지 않습니다.

## 라이선스

[MIT License](LICENSE) · Original work copyright (c) 2020 dlcjsdltlq
