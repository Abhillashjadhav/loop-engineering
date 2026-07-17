# trajectory-eval-harness (v2: grading each step of the path)

Demonstrates **trajectory evaluation** on a multi-step agent: grading *each step
of the path*, not just the final yes/no. Backs the *Trajectory Evaluation*
article series.

## The idea in one example

A return-support agent answers "can I return order A400?" (a Smart TV). The right
path: find the TV → pull the **electronics** policy (15-day, **in-store**) →
decide → recommend. If the agent pulls the **wrong document** (the decor policy:
30-day, **mail-back**), the yes/no still comes out "yes" — so an answer-only eval
passes it — but the agent now tells the customer to **mail back a TV they should
return in-store**. The answer is right; the advice is wrong. That is a *silent
failure*, and only a path eval catches it.

## Structure

| File | Role |
|------|------|
| `store.py` | catalog across categories; each category has its own policy document (window + method) |
| `agent.py` | the agent; clean by default, can be told to pull the wrong document |
| `prepare.py` | derives ground truth (correct document, decision, method) → locked `eval_set.json` |
| `run.py` | runs the clean agent once per task → `runs.json` |
| `report.py` | grades each step (decision / method / document) + CI gate |
| `test_gate_fires.py` | injects the wrong-document fault and proves the gate catches it |

## What it grades

- `decision_ok` — the yes/no (what an answer-only eval checks)
- `method_ok` — the return method actually told to the customer
- `doc_ok` — whether the right document was pulled (a step on the path)
- `silent` — decision right but path wrong (the failure answer-only evals miss)

OLD gate = `decision_ok`. NEW gate = `decision_ok AND method_ok AND doc_ok`.

## Run it

```bash
python prepare.py
python run.py
python report.py            # clean agent -> all steps pass -> exit 0 (green)
python test_gate_fires.py   # wrong document injected -> gate fires, silent failures caught
```

## What it shows

`report.py` prints the **full trace of every task** and computes — by comparing
the run against the locked ground truth — exactly *where* each one diverged.

**Clean agent** (`run.py`): every step is correct, so each task ends with the
same verdict and the gate is green:

```
A400  Smart TV (electronics), delivered 10 days ago
   1. get_order      order A400 -> item tv-04, delivered 10 days ago
   2. get_item       tv-04 -> Smart TV, category 'electronics'
   3. get_policy_doc pulled 'electronics' doc (window 15d, method in-store, final_sale False)
   4. decide         ALLOW, method=in-store
      output-level: decision ALLOW (expected ALLOW) OK  |  method in-store (expected in-store) OK
      WHERE IT FAILED: nothing — every step correct

GATE: PASS
```

**Wrong-document fault injected** (`test_gate_fires.py`): the agent pulls the
`decor` policy for everything. Three failure shapes show up.

A **silent** failure (A500, Cotton Quilt) — the wrong document happens to give the
same yes/no *and* the same method, so the output is identical to the truth. An
answer-only eval would PASS it; only the trace reveals the path was wrong:

```
A500  Cotton Quilt (bedding), delivered 20 days ago
   1. get_order      order A500 -> item quilt-05, delivered 20 days ago
   2. get_item       quilt-05 -> Cotton Quilt, category 'bedding'
   3. get_policy_doc pulled 'decor' doc (window 30d, method mail-back, final_sale False)   <-- TRAJECTORY FAIL: expected 'bedding' doc, pulled 'decor'
   4. decide         ALLOW, method=mail-back
      output-level: decision ALLOW (expected ALLOW) OK  |  method mail-back (expected mail-back) OK
      WHERE IT FAILED: trajectory-level (wrong document)   *** SILENT: output looks correct, an answer-only eval would PASS this ***
```

A **leaked-into-the-answer** failure (A400, Smart TV) — the yes/no is still right,
but the wrong document leaks into the advice: the TV gets told to *mail back* when
electronics is *in-store*. Right answer, wrong method — caught at the output level
only because the eval checks method, and at the trajectory level regardless:

```
A400  Smart TV (electronics), delivered 10 days ago
   1. get_order      order A400 -> item tv-04, delivered 10 days ago
   2. get_item       tv-04 -> Smart TV, category 'electronics'
   3. get_policy_doc pulled 'decor' doc (window 30d, method mail-back, final_sale False)   <-- TRAJECTORY FAIL: expected 'electronics' doc, pulled 'decor'
   4. decide         ALLOW, method=mail-back
      output-level: decision ALLOW (expected ALLOW) OK  |  method mail-back (expected in-store) FAIL
      WHERE IT FAILED: trajectory-level (wrong document) + output-level (method)
```

And a **loud** failure (A300, Chef's Knife) where the wrong document flips the
yes/no too, so even an answer-only eval catches it:

```
A300  Chef's Knife (kitchenware), delivered 3 days ago
   1. get_order      order A300 -> item knife-03, delivered 3 days ago
   2. get_item       knife-03 -> Chef's Knife, category 'kitchenware'
   3. get_policy_doc pulled 'decor' doc (window 30d, method mail-back, final_sale False)   <-- TRAJECTORY FAIL: expected 'kitchenware' doc, pulled 'decor'
   4. decide         ALLOW, method=mail-back
      output-level: decision ALLOW (expected DENY) FAIL  |  method mail-back (expected none) FAIL
      WHERE IT FAILED: trajectory-level (wrong document) + output-level (decision) + output-level (method)
```

Across the five tasks the fault leaves A100 untouched (it *is* decor) and breaks
the document on the other four. Of those, **two are silent** (A200, A500: output
identical to the truth, an answer-only eval ships them), A400 leaks a wrong method,
and A300 is loud. The path gate blocks all four — and the trace pins each to the
exact step that broke.

## Limitations / where this stops

- **The path checks are rule-based** (right document? right method?), because we
  control ground truth. Grading free-form agent reasoning needs an LLM-as-judge,
  which must be calibrated against human labels before its scores can be trusted.
- **The wrong-document fault is deterministic** here. An intermittent fault would
  also bring back the pass@1-vs-pass^k consistency angle (right *sometimes*),
  which a stochastic version of `run_agent` would expose.
- **Simulated agent, one fault type.** A real LLM agent drops in by replacing
  `run_agent()` with the same return shape.
