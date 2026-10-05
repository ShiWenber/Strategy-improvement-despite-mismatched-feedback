# Qwen3.8-Flash paired replication

- Reuse the frozen 20 populations, 60 parents, five arms, 600 prompts, request order, and parent selection scores from `results/feedback_specificity_v2`. No new initialization calls or changed prompts.
- Run independent `off` and `on` candidate batches, 600 requests per mode. The OpenAI-compatible Qwen API is read from the worktree `.env`; the model is explicitly `qwen3.8-flash`, overriding the `.env` model alias without editing the file.
- Both modes use temperature 1. `off`: `enable_thinking=false`, `max_tokens=6000`. `on`: `enable_thinking=true`, `reasoning_effort=high`, `max_tokens=131072`. The latter is the model's published maximum, below the original DeepSeek thinking budget of 384000; this is a material configuration difference.
- Save each request specification, streamed events, response, usage, and candidate validation. Failed or uncertain requests are never retried automatically. A truncated or invalid candidate is treated as invalid and falls back to its parent under the existing evaluation protocol.
- Evaluate the two candidate pools with the frozen S1/S2/S3 and H code. Reuse original parent selection and H scores. Seal all selection decisions before H is released to the batch. H is an existing panel, so this is a follow-up model comparison, not a new blind holdout.
- The two modes differ in thinking and output budget. Their difference cannot isolate a pure thinking-mode causal effect. Historical model comparisons also differ in model and collection time.
- Each mode has its own manifest, progress, logs, candidates, selection scores, holdout measurements, and analysis under `results/qwen3_8/{off,on}`.

Model specification and limits: https://help.aliyun.com/en/model-studio/qwen3-8-flash
OpenAI-compatible thinking parameter: https://help.aliyun.com/en/model-studio/qwen-api-via-openai-chat-completions
