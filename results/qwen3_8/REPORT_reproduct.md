# Qwen3.8-Flash paired replication

Same frozen 20 populations, 60 parents and 240 prompts per mode. H was previously used.

| Mode | Valid / 240 | Raw Accurate | Raw Mismatched | S3 Accurate | S3 Mismatched | Input tokens | Output tokens | Uncached list cost (CNY) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| off | 224 | +0.01959 | +0.02131 | +0.03484 | +0.03939 | 2,139,274 | 329,025 | 2.60 |
| on | 221 | +0.11655 | +0.11044 | +0.16352 | +0.15107 | 2,147,914 | 16,865,276 | 47.25 |

Primary descriptive contrasts (population is the independent unit):

- off: raw Accurate − Mismatched -0.00171 payoff per round; Holm p=1.00000.
- on: raw Accurate − Mismatched +0.00611 payoff per round; Holm p=1.00000.
- on_minus_off: raw Accurate − Mismatched +0.00782 payoff per round; Holm p=1.00000.

Thinking and output limit differ between modes (6,000 vs 131,072); the mode contrast does not isolate thinking alone. The cost assumes uncached Beijing list prices and can differ from the actual bill.
