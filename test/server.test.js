import assert from "node:assert/strict";
import test from "node:test";

import { createApp, extractOtp, isLastZMessage, parseAfter } from "../server.js";

test("Last Z 발신자 또는 제목만 허용한다", () => {
  assert.equal(
    isLastZMessage({
      subject: "로그인 인증",
      from: [{ name: "Last Z: Survival Shooter", address: "notice@example.com" }],
    }),
    true,
  );
  assert.equal(isLastZMessage({ subject: "택배 인증번호 123456", from: [] }), false);
});

test("라벨이 있는 6자리 인증번호를 우선 추출한다", () => {
  assert.equal(extractOtp("귀하의 인증 코드는 다음과 같습니다: 183655"), "183655");
  assert.equal(extractOtp("주문 123456 / 인증번호 506784"), "506784");
  assert.equal(extractOtp("날짜 260101, 주문 123456"), null);
});

test("after는 최대 30분 범위로 제한한다", () => {
  const now = Date.parse("2026-10-06T00:00:00.000Z");
  assert.equal(parseAfter("invalid", now), null);
  assert.equal(parseAfter(now - 60 * 60 * 1000, now), now - 30 * 60 * 1000);
  assert.equal(parseAfter(String(now - 1_000), now), now - 1_000);
});

test("OTP API는 최신 조회 기준과 결과만 반환한다", async (t) => {
  const originalKey = process.env.OTP_ACCESS_KEY;
  process.env.OTP_ACCESS_KEY = "test-key";
  t.after(() => {
    if (originalKey === undefined) delete process.env.OTP_ACCESS_KEY;
    else process.env.OTP_ACCESS_KEY = originalKey;
  });

  let seen;
  const app = createApp({
    otpFetcher: async (account, after) => {
      seen = { account, after };
      return { code: "506784", receivedAt: "2026-10-06T00:00:01.000Z" };
    },
  });
  const server = app.listen(0);
  t.after(() => server.close());

  const address = server.address();
  const response = await fetch(
    `http://127.0.0.1:${address.port}/api/otp/main?after=2026-10-06T00:00:00.000Z`,
    { headers: { "X-OTP-Access-Key": "test-key" } },
  );
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), {
    ok: true,
    code: "506784",
    receivedAt: "2026-10-06T00:00:01.000Z",
  });
  assert.equal(seen.account, "main");
  assert.equal(seen.after, Date.parse("2026-10-06T00:00:00.000Z"));
});

test("접근 키가 없거나 틀리면 OTP를 반환하지 않는다", async (t) => {
  const originalKey = process.env.OTP_ACCESS_KEY;
  process.env.OTP_ACCESS_KEY = "correct-key";
  t.after(() => {
    if (originalKey === undefined) delete process.env.OTP_ACCESS_KEY;
    else process.env.OTP_ACCESS_KEY = originalKey;
  });

  const app = createApp({ otpFetcher: async () => ({ code: "000000", receivedAt: "now" }) });
  const server = app.listen(0);
  t.after(() => server.close());
  const address = server.address();
  const response = await fetch(`http://127.0.0.1:${address.port}/api/otp/main`);
  assert.equal(response.status, 401);
  assert.deepEqual(await response.json(), { ok: false, error: "access_denied" });
});
