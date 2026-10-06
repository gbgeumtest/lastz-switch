# GB YS / Last Z Switch

개인용 Last Z 계정 전환 보조 페이지와 Naver IMAP 메일 브리지입니다.

## Render 환경변수

다음 값은 Render Web Service의 Environment에만 저장합니다.

- `GB_MAIN_EMAIL`
- `GB_MAIN_APP_PASSWORD`
- `GB_SUB_EMAIL`
- `GB_SUB_APP_PASSWORD`
- `OTP_ACCESS_KEY`: 충분히 긴 임의 문자열

Naver 앱 비밀번호나 `OTP_ACCESS_KEY`를 GitHub, 이 파일, 이슈, 로그에 넣지 않습니다.

## 동작

- `GET /`: 서비스와 환경변수 설정 여부만 반환
- `GET /health`: 상태 확인
- `GET /api/otp/main?after=<ISO 시간>`
- `GET /api/otp/sub?after=<ISO 시간>`

OTP API에는 `X-OTP-Access-Key` 헤더가 필요합니다. 메일은 읽기만 하며 삭제, 수정,
전송하지 않습니다. 지정 시각 이후 받은 Last Z 관련 최신 메일에서만 6자리 코드를
찾습니다.

## 로컬 확인

```sh
npm install
npm test
npm start
```

프론트는 GitHub Pages에서 제공되며 백엔드는
`https://lastz-switch-2.onrender.com`을 사용합니다.
