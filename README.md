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

## Demo without a server (judges / reviewers)

Open **`demo.html`** directly in any browser — it is fully self-contained and shows the complete
UI populated with a real-shaped sample result. No server, no key.

## Files
- `app.py` — zero-dependency HTTP server + Clocked client (pipeline + grounding) + result parser.
- `templates/index.html` — the live UI (fetches `/analyze`).
- `demo.html` — self-contained offline demo with embedded sample data.
- `demo_data.json` — the sample result shown in the demo.

## Notes
- Each analysis = 1 Pipeline call (≤ 800 credit reservation) + 1 Grounding call. With the 20,000
  challenge credits this is comfortably in budget.
- The inspection procedure text in `app.py` (`STANDARD_TEXT`) is a placeholder; swap in your own
  SOP for production.
- Idempotency keys are generated per request; retries are safe.
