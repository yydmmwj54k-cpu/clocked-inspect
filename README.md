# 手不停 Inspect — Clocked Build Challenge entry

**手不停 Inspect** turns a free-text field inspection note (the kind an offshore / industrial
operator dictates hands-free) into a structured, PII-safe, decision-routed, evidence-checked
record — by calling **Clocked by Rezolve.ai**, an API that returns *structured results instead of
generated text*.

A single paste of a messy shift log like:

> P-101 出口压力 0.62 MPa，正常。P-102 出口压力 0.71 MPa，偏高，需关注。V-203 调节阀开度 45%。巡检人：张伟，电话 13800000000。

becomes:

1. **Masked original** — names / phones redacted (Protect)
2. **Structured readings** — device · reading · status, with source positions (Extract)
3. **Decisions** — *needs escalation?* and *complete?* with probabilities (Decide)
4. **Grounding** — the abnormal reading checked claim-by-claim against the procedure (Verify)

---

## How Clocked is used (all three endpoint groups)

The app calls **two** endpoints, covering **all three** of Clocked's groups, which earns the
"breadth" points judges look for:

| Group | Endpoint | How 手不停 uses it |
|---|---|---|
| **Decide / Extract / Fill** | `/pipeline` → `extract` + `decide` | `extract` pulls each equipment reading as a record (device, reading, status) with character offsets; `decide` returns *needs_escalation* / *complete* as choices **with probabilities**. |
| **Protect / Guard / Inspect** | `/pipeline` → `pii` | `pii` finds person names, phones, emails and IDs, which the app uses to **mask** the original text before anything leaves the page. |
| **Verify / Compare / Rerank** | `/grounding` | the abnormal reading is turned into a claim and checked **claim-by-claim** against the inspection procedure (support / contradict / not-stated + source quote). |

`/pipeline` runs `pii` + `extract` + `decide` in **one round trip** (one admission, one bill, one
idempotency key); `/grounding` is a second call because its input is a document set, not the shared
text. See `app.py` (`analyze_pipeline`, `analyze_grounding`).

### Judging-category mapping
- **Best Overall App** — a coherent, real-domain workflow where each endpoint's output *changes what the app shows* (the structured table, the escalation badge, the masked text, the grounding verdict).
- **Best Use of Decide / Extract / Fill** — `extract` produces typed records; `decide` produces probabilistic routing.
- **Best Use of Protect / Guard / Inspect** — `pii` drives redaction before display.
- **Best Use of Verify / Compare / Rerank** — `grounding` verifies the escalation claim against the procedure.
- **People's Choice** — see the LinkedIn step in the submission form.

---

## Run it (live, with your key)

Zero third-party dependencies — Python 3.9+ standard library only.

```bash
cd clocked-inspect
export CLOCKED_API_KEY="your-clocked-api-key"   # from https://clocked.rezolve.ai/account
python3 app.py
# open http://127.0.0.1:8000
```

Without a key the app still runs in **demo mode** (it returns a built-in sample result), so the
UI is fully demonstrable even before you add a key.

## Verified with real API calls (not mock data)

`demo.html` and `demo_data.json` are populated by an **actual `app.build_report()` run on
2026-11-09** against the live Clocked API, using a synthetic inspection log (fictional inspector
name and phone). The raw responses are committed in **`real_call_evidence.json`** so reviewers can
check every field. No API keys or real personal data are included anywhere in this repository.

Observed real results:

| Endpoint | Real output |
|---|---|
| `pii` | found `person name` + `phone number` with exact character offsets → app masks them |
| `extract` | 4 equipment readings as records (`P-101 0.62 MPa 正常`, `P-102 0.71 MPa 偏高，需关注`, …) |
| `decide` | `needs_escalation` at **0.9956**, `complete` at **0.7851**, with full probability distributions → drives the escalation badge |
| `grounding` | `grounded` **0.8866**, claim `supported`, with a verbatim quote from the procedure → if the verdict is *not* supported, the app sets `needs_review` and flags the record for human review |

That last row is the important one: **the endpoint output changes what the application does**, it
is not a call whose result is ignored.

## Demo without a server (judges / reviewers)

Open **`demo.html`** directly in any browser — fully self-contained, shows the complete UI with the
real captured result. Or open the hosted page:
**https://yydmmwj54k-cpu.github.io/clocked-inspect/demo.html**

## Files
- `app.py` — zero-dependency HTTP server + Clocked client (pipeline + grounding) + result parser.
- `templates/index.html` — the live UI (fetches `/analyze`).
- `demo.html` — self-contained demo with the embedded real result.
- `demo_data.json` — the real result shown in the demo.
- `real_call_evidence.json` — raw Pipeline + Grounding responses (synthetic data only).

## Notes
- Each analysis = 1 Pipeline call (≤ 800 credit reservation) + 1 Grounding call. With the 20,000
  challenge credits this is comfortably in budget.
- Grounding receives **two documents** (the procedure *and* the original log): checking a claim
  with a specific reading against the procedure alone correctly returns `not_stated`, which was
  confirmed in a real call. Supplying both makes the verdict meaningful.
- Behind Cloudflare-fronted or corporate networks, `urllib` may get a 403 challenge; the client
  automatically retries through `curl`, honouring `HTTPS_PROXY` / `https_proxy`.
  ```bash
  export https_proxy="http://127.0.0.1:7897"   # only if you need a proxy
  ```
- The inspection procedure text (`STANDARD_TEXT`) is a placeholder; swap in your own SOP.
- Idempotency keys are generated per request; retries are safe.
