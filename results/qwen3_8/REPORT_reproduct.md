# Qwen3.8-Flash paired replication

Same frozen 20 populations, 60 parents and 600 prompts per mode. H was previously used.

| Mode | Valid / 600 | Raw Accurate | Raw Mismatched | S3 Accurate | S3 Mismatched | Input tokens | Output tokens | Uncached list cost (CNY) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| off | 572 | +0.01959 | +0.02131 | +0.03484 | +0.03939 | 5,258,734 | 784,913 | 6.33 |
| on | 528 | +0.11655 | +0.11044 | +0.16352 | +0.15107 | 5,280,334 | 38,624,227 | 108.51 |

Primary descriptive contrasts (population is the independent unit):

- off: raw Accurate − Mismatched -0.00171 payoff per round; Holm p=1.00000.
- on: raw Accurate − Mismatched +0.00611 payoff per round; Holm p=1.00000.
- on_minus_off: raw Accurate − Mismatched +0.00782 payoff per round; Holm p=1.00000.

Thinking and output limit differ between modes (6,000 vs 131,072); the mode contrast does not isolate thinking alone. The cost assumes uncached Beijing list prices and can differ from the actual bill.
