## BigLawBench → Harbor Adapter

## Overview

BigLaw Bench (BLB) by Harvey evaluates LLMs/agents on real-world legal work product (transactional and litigation tasks drawn from billable-time entries), graded with per-task rubrics. This adapter covers **BLB-Core public sample: 6 tasks** (ids 4, 5, 19, 49, 60, 96 in `blb-core/core-samples.csv`). Upstream: https://github.com/harveyai/biglaw-bench (pinned to commit `138fd481b459a00bbd98eeb710f69ada1052bd47`). The full BLB dataset is private to Harvey.

**Excluded:** `blb-workflows/spa` (SPA deal-point extraction; no scorer or judge prompt upstream, needs a new scoring design) and `blb-retrieval` (retrieval-system benchmark with queries only, no gold labels). Out of scope for this round.

## What is BigLawBench?

"A new standard for evaluating AI on legal & professional tasks" (Harvey, 2024). Each task has a rubric of affirmative points (e.g. "Does the response state X? (1 point)") and negative points (-1 per hallucination, -0.5 per extraneous statement). Answer score = net points / total affirmative points. Harvey also describes a separate source-reliability score (not in the public rubrics). See https://www.harvey.ai/blog/introducing-biglaw-bench.

## Adapter Features

- Downloads `core-samples.csv` and the task PDFs from the pinned upstream commit at generation time; **no upstream data is committed**. Generated PDFs are baked into each task's `environment/documents/`.
- Task ids: `blb-core-004`, ... ; task names `harvey/biglawbench__blb-core-004`.
- Verifier: stdlib-only rubric scorer `tests/judge.py` (LLM judge over any OpenAI-compatible endpoint). Judge returns per-criterion booleans and counts of hallucinations/extraneous statements; the scorer computes `clamp((sum(met points) - penalties) / total_positive_points, 0, 1)`.
- Oracle: `solution/answer.md` is a rubric-derived reference answer (every affirmative criterion restated as a satisfied statement, generated mechanically by the adapter). It is a checklist, not a polished work product; the oracle verifies the pipeline end to end.
- Instruction = upstream `Prompt` verbatim + attached-document list + output location (`/app/answer.md`). This is the only prompt change.

## Generated Task Structure

```
biglawbench/
├── blb-core-004/
│   ├── task.toml
│   ├── instruction.md
│   ├── environment/{Dockerfile, documents/*.pdf}
│   ├── solution/{solve.sh, answer.md}
│   └── tests/{test.sh, judge.py, rubric.md}
```

## Run Evaluation / Harness

Judge configuration is read from the environment via `[verifier.env]`:

```bash
export JUDGE_API_KEY=...                       # required
export JUDGE_BASE_URL=https://app.ppapi.ai/    # optional, OpenAI-compatible endpoint (default shown)
export JUDGE_MODEL=gpt-5-2025-08-07            # optional, default shown (configurable)

uv run biglawbench --output-dir datasets/biglawbench
harbor run -p datasets/biglawbench -a oracle
harbor run -c src/biglawbench/run_biglawbench.yaml -a <agent> -m "<model>"
harbor trial start -p datasets/biglawbench/blb-core-004
```

## Usage: Create Task Directories

```bash
cd src/biglawbench
uv run biglawbench --output-dir ../../datasets/biglawbench
```

Flags: `--output-dir`, `--limit`, `--overwrite`, `--task-ids` (e.g. `blb-core-004` or `4`). No `--split parity` needed: only 6 tasks.

## Comparison with Original Benchmark (Parity)

Not yet run (parity plan pending team approval). The upstream repo ships no harness or judge, so parity needs a Scenario-2 style reference judge.

| Agent | Model | Metric | Number of Runs | Dataset Size | Original Benchmark Performance | Harbor Adapter Performance |
|-------|-------|--------|------------------|--------------|------------------------------|----------------------------|
| TBD | TBD | Rubric answer score | TBD | 6 | TBD | TBD |

## Notes & Caveats

- Upstream has no LICENSE file and publishes only samples; PDFs are fetched, not redistributed. Confirm terms with Harvey before publishing generated datasets.
- No judge prompt/model is specified upstream; ours is a new judge (per-criterion true/false + error counts). Scores are judge-dependent and not exactly comparable to Harvey's internal numbers. The source-reliability score is not implemented.
- Tasks 49 and 96 have no attached documents (hallucination counts are judged without source access to the task's context beyond the prompt).
- Oracle needs a live judge key; it is a rubric checklist, so the pass depends on the judge accepting it.
- Rubric labels are parsed by regex; "Style: N/A" sections are simply absent.

## Installation / Prerequisites

- Docker, Harbor (`uv tool install harbor`), `uv sync` in this directory, network access to GitHub raw at generation time, a judge API key.

## Troubleshooting

- `judge unavailable; no reward written`: check `JUDGE_API_KEY` / `JUDGE_BASE_URL` / `JUDGE_MODEL`.

## Citation

```bibtex
@misc{harvey_biglawbench,
  title={BigLaw Bench},
  author={Pereyra, Julio and Lebens, Elizabeth and Guillod, Matthew and Toulme, Laura and others},
  year={2024},
  url={https://github.com/harveyai/biglaw-bench}
}
```

## Authors & Contributions

Adapter developed by the Harbor team. Issues and PRs go to the main repository.
