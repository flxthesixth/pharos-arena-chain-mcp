# Portfolio no-login demo candidate

Status: LOCAL ONLY. Independent exact-path review required before publication/deploy. No credentials, signing, wallet connection, payment, or generic RPC proxy. Video/capture security/provenance HOLD remains unresolved; this runtime does not use capture.py or media.

## Run and check

From repository root:

```sh
python3 -B portfolio-demo/selfcheck.py
python3 -B -O portfolio-demo/selfcheck.py
python3 -B portfolio-demo/resource_check.py
python3 -B -O portfolio-demo/resource_check.py
python3 -B -m unittest discover -p 'test_pharos_portfolio_box3_20261110.py' -v
node --check portfolio-demo/public/app.js
python3 -B portfolio-demo/server.py
```

Open http://127.0.0.1:8765. Python stdlib only; no install/build needed. Server binds loopback by default. Seven example buttons and typed bounded-English questions execute original source `answer()`; no financial/parser duplication. Sample wallet fixed, deliberately not arbitrary-wallet service.

Recorded mode executes original parser against saved 17-row RPC trace at block 22661772, not prewritten answer cards and not live data. Replay allowed as demonstration, but rubric acceptance of recorded evidence is not established. Live mode performs genuine reads against fixed `https://rpc.pharos.xyz`, uses original snapshot logic and fixed wallet/contracts, one read at a time, at most one per 30 seconds per process. No caller-selected endpoint, method, parameters, wallet or contract. Demo-only transport caps each RPC body at 65,536 bytes plus one overflow-detection byte. A disposable subprocess executes the original parser/snapshot with its existing transport hook; parent kills and reaps it after 25 seconds total, including slow single-byte progress, DNS and TLS. Process launch/reclamation adds OS scheduling overhead; this is not a real-time guarantee. Published source transport remains unchanged. Unknowns remain unknown; chain/transport failures produce unavailable errors. No automatic retry or history/price inference.

Local browser verified seven recorded intents, citations, unknown earnings, rejected scope/XSS text, keyboard/labels/live-region/mobile layout and real live exposure: block 22722109; wallet USDC raw 1974365593; RockawayX underlying raw 2000206945234; SharpByte underlying raw 0; total raw 2002181310827. Historical observation only, not revalidated by resource-control tests. Later independent block 22722937 had RockawayX and total unknown; no fallback to historical values. Earlier observation showed two successful vault reads, not two nonzero positions. Recorded and live blocks differ. All quantities raw integer units, not USD. Zero address sentinel denotes native PROS. Contract-reported names are not official deployment provenance.

## Free deployment handoff — do not execute before review

Static-only hosting cannot execute existing Python parser/live reads. Use minimal Python backend; no new dependency or translation to JavaScript. Existing Wrangler/Render CLIs not found; no provider login, account entitlement, quota or payment status inspected. Render public documentation fetched successfully: Free web services spin down after 15 minutes idle, wake in about one minute, workspace allowance 750 hours/month. Free availability is provider-controlled, not a guaranteed zero-charge entitlement. Sources: https://render.com/docs/free and https://render.com/docs/deploy-flask .

After independent approval and explicit publication/deploy permission:

1. Publish only exact approved files/dependencies; never upload repository root containing unrelated work. Required existing files: `pharos_portfolio_box3_20261110.py`, `evidence/portfolio-assistant/steps1-3-producer/fresh-live-rpc-trace.json`; new `portfolio-demo/` files listed in separate review manifest. No video, capture driver, local review folder, credentials or `.git` content belongs in public assets.
2. Owner logs into Render and creates Web Service from approved repo/branch. Language Python 3; repository root working directory; Free instance explicitly; build command `python3 --version`; start command `python3 -B portfolio-demo/server.py`; environment `HOST=0.0.0.0`, provider supplies `PORT`. No disk, DB, secrets or paid addon. Disable automatic deploys until future changes receive review. Confirm displayed price remains zero; stop if card/payment or paid plan required.
3. Anonymous browser at assigned HTTPS URL: run all seven questions, verify recorded label, perform live exposure after cooldown, check citations/two vaults, scope rejection and unknown earnings. Verify source exact hashes, no source-file HTTP exposure, POST refusal, GET-only same-origin browser traffic. Origin admits at most eight client handlers (eight timer threads), backlog eight; overflow connections close without a worker. Socket inactivity timeout is five seconds; absolute header deadline five seconds, execution phase 30 seconds, response-write deadline five seconds. Timers shut down sockets even during single-byte progress. Stdlib request-line/header size limits still apply. Errors log no client details. Public reverse proxy must additionally enforce rate limits, upstream/header limits and prevent direct-origin bypass; bounded stdlib demo is not full denial-of-service protection. Do not scale to multiple processes without shared quota.
4. Parent reviews exact public URL and rubric before any Arena submit. No URL created here. Submission/repo/video approval remain separate gates; this demo does not waive capture HOLD.

Recorded mode remains available if RPC throttles; label never implies live. Public denial-of-service resistance and provider free eligibility require review. No deployment configuration added: manual Free selection avoids accidental paid provider defaults.
