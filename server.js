import crypto from "node:crypto";
import { pathToFileURL } from "node:url";

import cors from "cors";
import express from "express";
import { ImapFlow } from "imapflow";
import { simpleParser } from "mailparser";

const IMAP_HOST = "imap.naver.com";
const DEFAULT_LOOKBACK_MS = 5 * 60 * 1000;
const MAX_LOOKBACK_MS = 30 * 60 * 1000;
const MAX_CANDIDATES = 40;
const ALLOWED_ORIGINS = new Set([
  "https://gbgeumtest.github.io",
  "http://127.0.0.1:5500",
  "http://localhost:5500",
]);

export function normalizeForMatch(value = "") {
  return String(value).toLowerCase().replace(/[^a-z0-9가-힣]+/g, "");
}

export function isLastZMessage(envelope = {}) {
  const people = [...(envelope.from || []), ...(envelope.sender || [])]
    .map((person) => `${person?.name || ""} ${person?.address || ""}`)
    .join(" ");
  const identity = normalizeForMatch(`${envelope.subject || ""} ${people}`);
  return identity.includes("lastz") || identity.includes("라스트z");
}

export function extractOtp(text = "") {
  const value = String(text).replace(/\u00a0/g, " ");
  const labelled = [
    /(?:인증\s*(?:코드|번호)|verification\s*code|security\s*code|one[ -]?time\s*(?:password|code)|otp)[^0-9]{0,100}([0-9]{6})(?![0-9])/iu,
    /([0-9]{6})(?![0-9])[^\n\r]{0,60}(?:인증\s*(?:코드|번호)|verification\s*code|otp)/iu,
  ];

  for (const pattern of labelled) {
    const match = value.match(pattern);
    if (match) return match[1];
  }

  const allSixDigitCodes = [...value.matchAll(/(?<![0-9])([0-9]{6})(?![0-9])/gu)].map(
    (match) => match[1],
  );
  return allSixDigitCodes.length === 1 ? allSixDigitCodes[0] : null;
}

export function parseAfter(value, now = Date.now()) {
  if (value === undefined || value === null || value === "") {
    return now - DEFAULT_LOOKBACK_MS;
  }

  const parsed = /^\d+$/.test(String(value)) ? Number(value) : Date.parse(String(value));
  if (!Number.isFinite(parsed)) return null;

  const earliest = now - MAX_LOOKBACK_MS;
  const latest = now + 60 * 1000;
  return Math.min(Math.max(parsed, earliest), latest);
}

function getAccountConfig(account, env = process.env) {
  const prefix = account === "main" ? "GB_MAIN" : account === "sub" ? "GB_SUB" : null;
  if (!prefix) return null;

  return {
    user: env[`${prefix}_EMAIL`]?.trim(),
    password: env[`${prefix}_APP_PASSWORD`]?.trim(),
  };
}

function hasAccountConfig(account, env = process.env) {
  const config = getAccountConfig(account, env);
  return Boolean(config?.user && config?.password);
}

function safeEqual(left, right) {
  const a = Buffer.from(String(left || ""));
  const b = Buffer.from(String(right || ""));
  return a.length === b.length && a.length > 0 && crypto.timingSafeEqual(a, b);
}

function requestAccessKey(req) {
  return req.get("x-otp-access-key") || "";
}

function accessKeyMiddleware(req, res, next) {
  const configuredKey = process.env.OTP_ACCESS_KEY?.trim();
  if (!configuredKey) {
    return res.status(503).json({ ok: false, error: "access_key_not_configured" });
  }
  if (!safeEqual(requestAccessKey(req), configuredKey)) {
    return res.status(401).json({ ok: false, error: "access_denied" });
  }
  return next();
}

function receivedTime(message, parsed) {
  const candidates = [message.internalDate, parsed?.date];
  for (const candidate of candidates) {
    const timestamp = candidate instanceof Date ? candidate.getTime() : Date.parse(candidate);
    if (Number.isFinite(timestamp)) return timestamp;
  }
  return 0;
}

function imapSearchDay(afterMs) {
  const date = new Date(afterMs);
  date.setUTCHours(0, 0, 0, 0);
  return date;
}

export async function fetchLatestOtp(account, afterMs) {
  const config = getAccountConfig(account);
  if (!config?.user || !config?.password) {
    const error = new Error("mail_not_configured");
    error.code = "mail_not_configured";
    throw error;
  }

  const client = new ImapFlow({
    host: IMAP_HOST,
    port: 993,
    secure: true,
    auth: { user: config.user, pass: config.password },
    logger: false,
    disableAutoIdle: true,
    connectionTimeout: 20_000,
    greetingTimeout: 12_000,
    socketTimeout: 30_000,
    tls: { minVersion: "TLSv1.2", servername: IMAP_HOST },
  });

  let lock;
  try {
    await client.connect();
    lock = await client.getMailboxLock("INBOX");

    const uids = await client.search({ since: imapSearchDay(afterMs) }, { uid: true });
    const newestUids = uids.slice(-MAX_CANDIDATES).reverse();

    for (const uid of newestUids) {
      const message = await client.fetchOne(
        uid,
        { uid: true, envelope: true, internalDate: true, source: true },
        { uid: true },
      );
      if (!message || !isLastZMessage(message.envelope)) continue;

      const quickReceivedAt = message.internalDate ? new Date(message.internalDate).getTime() : 0;
      if (quickReceivedAt && quickReceivedAt < afterMs) continue;

      const parsed = await simpleParser(message.source, {
        skipHtmlToText: false,
        skipTextToHtml: true,
        maxHtmlLengthToParse: 500_000,
      });
      const timestamp = receivedTime(message, parsed);
      if (!timestamp || timestamp < afterMs) continue;

      const code = extractOtp(`${parsed.text || ""}\n${parsed.html || ""}`);
      if (code) return { code, receivedAt: new Date(timestamp).toISOString() };
    }

    return null;
  } catch (error) {
    if (error?.code === "mail_not_configured") throw error;
    const wrapped = new Error("mail_connection_failed");
    wrapped.code = "mail_connection_failed";
    throw wrapped;
  } finally {
    if (lock) lock.release();
    if (client.usable) {
      try {
        await client.logout();
      } catch {
        client.close();
      }
    } else {
      client.close();
    }
  }
}

export function createApp({ otpFetcher = fetchLatestOtp } = {}) {
  const app = express();
  app.disable("x-powered-by");
  app.use(
    cors({
      origin(origin, callback) {
        if (!origin || ALLOWED_ORIGINS.has(origin)) return callback(null, true);
        return callback(null, false);
      },
      methods: ["GET"],
      allowedHeaders: ["Content-Type", "X-OTP-Access-Key"],
      maxAge: 86_400,
    }),
  );

  app.use((_req, res, next) => {
    res.set("Cache-Control", "no-store, max-age=0");
    res.set("Pragma", "no-cache");
    res.set("X-Content-Type-Options", "nosniff");
    next();
  });

  app.get("/", (_req, res) => {
    res.json({
      ok: true,
      service: "GB YS Mail Bridge",
      accessKeyConfigured: Boolean(process.env.OTP_ACCESS_KEY?.trim()),
      accounts: {
        main: hasAccountConfig("main"),
        sub: hasAccountConfig("sub"),
      },
    });
  });

  app.get("/health", (_req, res) => res.json({ ok: true }));

  app.get("/api/otp/:account", accessKeyMiddleware, async (req, res) => {
    if (req.params.account !== "main" && req.params.account !== "sub") {
      return res.status(404).json({ ok: false, error: "account_not_found" });
    }
    const after = parseAfter(req.query.after);
    if (after === null) {
      return res.status(400).json({ ok: false, error: "invalid_after" });
    }

    try {
      const result = await otpFetcher(req.params.account, after);
      if (!result) return res.status(404).json({ ok: false, error: "otp_not_found" });
      return res.json({ ok: true, code: result.code, receivedAt: result.receivedAt });
    } catch (error) {
      const code = error?.code || "mail_connection_failed";
      const status = code === "mail_not_configured" ? 503 : 502;
      return res.status(status).json({ ok: false, error: code });
    }
  });

  app.use((_req, res) => res.status(404).json({ ok: false, error: "not_found" }));
  return app;
}

const isMainModule = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (isMainModule) {
  const port = Number(process.env.PORT) || 3000;
  createApp().listen(port, () => {
    console.log(`GB YS Mail Bridge listening on port ${port}`);
  });
}
