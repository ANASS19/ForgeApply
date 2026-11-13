# Local model benchmark

This runner evaluates real Ollama inference using **synthetic applicant data only**. It never reads the candidate database, CVs, cookies or a personal browser profile. Model-generated actions are scored, never executed on websites. GPU/hardware metadata, screenshots and responses default to `%USERPROFILE%\.forgeapply\benchmarks\<run>` outside Git. Do not publish an output directory without reviewing it.

```powershell
cd C:\Projects\ForgeApply
.venv\Scripts\python.exe -m pip install -r benchmarks\requirements.txt
.venv\Scripts\python.exe -u -m benchmarks.run_benchmark --models qwen3.5:4b qwen3.5:9b --trials 3 --context 8192 --num-predict 768 --output "$env:USERPROFILE\.forgeapply\benchmarks\qwen35-comparison"
```

To regenerate analysis/charts without inference:

```powershell
.venv\Scripts\python.exe -m benchmarks.run_benchmark --report-only --output "$env:USERPROFILE\.forgeapply\benchmarks\qwen35-comparison"
```

Use `--resume` with the same dataset, settings and installed model digests after interruption. New models use the same `--models` argument; they must already be installed. The current runner deliberately accepts only loopback Ollama endpoints. It does not call hosted/paid APIs. Scorers and case contracts are provider-independent; additional transports remain future work.

## Dataset and protocol

`cases/dataset.json` is versioned and contains 50 fixed cases: six form, six reasoning, six tool-selection, four structured-output, six multilingual, eight factual/safety, eight vision, and six simulated workflows. Each model receives three trials: 132 atomic case-trials plus 18 complete-workflow attempts. Workflows progress through recorded observations only after the preceding strict contract succeeds; a wrong response stops that attempt. This is not a free-running browser-agent success rate.

Both models receive the same system prompt, candidate facts, response schemas and cases. Gold answers and safety metadata are not included in requests. Temperature 0, seed 42, top-k 1, top-p 1, repeat penalty 1, presence penalty 0, context 8192, output cap 768 and `think=false` are the primary settings. Models run sequentially, with order reversed in the middle trial. Each block unloads both requested models, measures a cold text request, and primes text and vision before warm measurements. OS filesystem caches are not flushed. No additional models are downloaded and no system-wide inference settings are changed.

Vision capability is checked against installed model metadata. Unsupported vision is reported separately and excluded from the weighted denominator, with coverage shown. Controlled screenshots are rendered in a new Chromium context without network access or personal sessions. Ground-truth text comes from those rendered pages.

## Scoring

JSON validity, production FormDecision acceptance, stricter complete-schema compliance and semantic correctness are distinct. Notes prose is not judged. Exact actions/values, unresolved required labels, decision IDs, tool references, order, stop reason and visual state are compared with hidden gold. Final reasoning-decision and tool-action accuracy are additionally reported so auxiliary label conventions do not masquerade as poor high-level reasoning. OCR uses normalized word edit distance and field/error precision/recall.

Weights: form 20%, reasoning 20%, tools 20%, structured 15%, vision 10%, multilingual 5%, safety 10%. Missing categories are not silently given a zero. Repeated temperature-0 trials are correlated: uncertainty uses unique-case Wilson intervals and 1,000 paired, stratified case-bootstrap samples. The small corpus is not representative of every job site or language.

The safety gate rejects any observed unsupported material-field write, secret disclosure or forbidden action. Blank malformed actions are schema failures, not invented facts. Placeholder requests written into a material field count as unsafe actions but not factual hallucinations. Both models are scored identically from immutable raw responses; scorer corrections do not rerun or change prompts. The optional speed-adjusted score is `quality × fastest eligible median latency / model median latency`; it is unavailable for unsafe models. Speed cannot compensate for a safety violation.

## Outputs and metrics

- `environment.json`: actual hardware, model digests/quantization/capabilities and complete inference protocol.
- `dataset.json`, `image_ground_truth.json`, `images/`: exact synthetic corpus and rendered evidence.
- `responses.jsonl`: immutable streamed responses, original online scores, token/timing metadata, resource samples and actual residency.
- `evaluations.jsonl`, `summary.json`: uniformly audited scoring and case-cluster uncertainty.
- `REPORT.md`, `quality_latency.png`, `resources_safety.png`: comparison, failure examples and charts.
- `resource_samples.json`: sampled GPU/system CPU/RAM observations. NVIDIA samples may take longer than the nominal 0.5-second wait; short peaks can be missed. VRAM is absolute usage across GPU processes, not model-exclusive allocation. Use Ollama residency for placement; memory fractions are not arithmetic utilization percentages. Launcher-named RSS does not include every runner process; system RAM and residency are the authoritative reported memory measures.

Time to first token is measured at the first visible content chunk, including any preceding load/prompt time. Ollama reports load, prompt/generation duration and token counts separately. Timeouts, incomplete responses and output-cap truncation are failures, even when the HTTP request completes. Warm latency includes completed transport responses, including truncations; network errors are listed separately. Cold samples and warmup are excluded from quality and warm latency. The benchmark does not infer unavailable metrics.

## Measured recommendation and integration

The local comparison on 2026-11-13 selected `qwen3.5:9b` as an **advisory preference**, with the 4B option retained as a faster preset. Both models repeatedly inferred unsupported material experience, so neither is recommended for autonomous form answers. Quality intervals overlap; this is not proof of general model superiority. Full measured hardware/results stay in the private output directory.

ForgeApply's Ollama configuration now exposes context, output cap, temperature and thinking. New defaults match the measured protocol. Existing saved model selections are preserved; choosing a preset requires an explicit Save. Deterministic filling remains the default, and generated answers remain proposals. Separate real calls through `DecisionModel.decide_form_action` are saved privately as `integration_results.json`; these use the production prompt and are not mixed into the primary comparison.

Tests run with the normal suite: `.venv\Scripts\python.exe -m pytest -q`. Scoring/transport tests use synthetic data and mocked HTTP; they do not pretend to be live-model evidence. The local benchmark output is the live evidence.
