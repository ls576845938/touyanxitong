# AlphaRadar Agent Rules

## Product Goal
Build a personal investment research system for A-share industry trend discovery, tenbagger early signal screening, K-line trend filtering, and daily research brief generation.

## Priority
1. Data correctness and source traceability
2. Explainable scoring
3. Evidence-chain quality
4. Reproducible daily pipeline
5. Safe product wording
6. Frontend usability

## Hard Rules
- Do not output buy, sell, target price, guaranteed return, or "must become tenbagger" wording.
- The system only outputs watchlist status, trend strength, industry heat, evidence chain, risks, and questions to verify.
- Every derived result must keep source, generated_at, and explanation fields where applicable.
- Keep data sources replaceable behind interfaces.
- If real data providers fail or are unavailable, use deterministic mock data to keep the MVP pipeline runnable.
- All scoring must be explainable; no black-box score-only output.

## Coding Rules
- Keep modules small and typed.
- Add focused tests for engines and pipeline.
- Do not rewrite unrelated files.
- Prefer pure domain engines that can be tested without network or database state.
- Run relevant tests and builds after changes.

## Current Priority
MVP loop: stock universe -> market bars -> news -> industry heat -> trend signals -> early signal score -> evidence chain -> daily report -> web dashboard.
