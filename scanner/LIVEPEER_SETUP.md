# iPhone Moblin -> Livepeer Studio -> Render detector

## Why an intermediary is required
Render web services accept public HTTP(S) and WebSocket traffic, not public RTMP TCP ingest. **Do not paste the Render HTTPS API URL into Moblin's RTMP URL field.**

## Screen sharing using only an iPhone
1. Sign up for Livepeer Studio Sandbox (subject to the provider's current allowance).
2. In Livepeer Studio dashboard, create a livestream named Last Z Scanner.
3. Disable recording and apply an appropriate playback access policy (Livepeer streams may be publicly accessible by playback URL).
4. Copy **RTMP ingest URL** to Moblin Custom > RTMP(S) > URL and **stream key** to Moblin > Stream Key. Do not send the stream key to ChatGPT, GitHub, or the public.
5. Choose the iOS screen broadcast option in Moblin and explicitly start screen sharing from iOS; switch to Last Z.
6. Copy **HLS .m3u8 playback URL** into the Render service `lastz-live-scanner-api` Environment variable `HLS_PLAYBACK_URL`. Keep this URL private if it contains access credentials. Also set `LASTZ_STATE` to the current game state, e.g. 406.
7. Render auto-deploys after environment variable changes. The server starts `hls_worker.py` and pulls frames from the trusted playback URL. For verification, check `/v1/status` with the existing private scanner API token.
8. Existing Quick Switch + scanner dashboard remains available at GitHub Pages. **It cannot capture the Last Z app directly.**

## Constraints
- No viewer stream URL or API key should be published on GitHub.
- Sandbox free plan is limited, not indefinite free unlimited streaming.
- HLS latency may be several seconds; cannot guarantee real-time raid viability.
- Current vision detector is only a yellow-color prefilter, **not a trained S truck detector**. Blue-chest Lv.5 bounty is not implemented.
- Stream sharing can expose private messages/notifications; enable appropriate privacy options.
- No automated map navigation or Last Z DM send, both require explicit in-game action.
