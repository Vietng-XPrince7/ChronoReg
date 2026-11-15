# QLoRA 3B course experiment – results (2026-11-15)

A standalone, reproducible course-mode 5-stage QLoRA experiment was completed on a Kaggle Tesla T4. It contains 5 sequential adapters for years 2022–2026, 200 training QA examples and 450 evaluation predictions on 90 benchmark questions.

All artifacts and instructions live under [`experiments/qlora3b_course_20261115/`](../experiments/qlora3b_course_20261115/README.md).

**Not an official gated release.** Training-year labels were proposed and require separate policy-effectivity confirmation. The reported Token F1 scores are not semantic factual accuracy or version accuracy. Existing BM25 RAG baseline outputs are not apples-to-apples generative LoRA results.
