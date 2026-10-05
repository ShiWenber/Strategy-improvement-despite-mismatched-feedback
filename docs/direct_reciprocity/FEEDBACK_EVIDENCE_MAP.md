> 本轮符号沿用写作时的 R/G/U/B（反馈报告记为 $D$）。

# Feedback attribution — internal evidence map and chapter blueprint

The living manuscript is FEEDBACK_ATTRIBUTION_DRAFT.md. This supporting file records provenance, not additional results.

## 2026-09-24 native-thinking integration

This update adds completed results to the existing manuscript, rather than merging the historical and follow-up samples. The LaTeX counterpart is `paper_zh_direct/main.tex`. Existing literature claims and reference lists are not expanded in this update.

| ID | Evidence (L1: local records) | Claim permitted | Cannot support | Use |
| --- | --- | --- | --- | --- |
| T1 | results/feedback_specificity_thinking_384k_20260923/manifest.json; PROTOCOL.md | Same parents, prompts and panels; thinking=enabled, high, 384000; two prespecified contrasts | Pure causal effect of thinking; fresh blinded H; 40 independent populations | Methods 4.6 |
| T2 | same directory, ANALYSIS.json: thinking/historical | Five-arm raw/S3 means and descriptive population directions; historical paired configuration differences | Budget-matched benefit; independent generation seeds; causal attribution to native reasoning | Results 5.5, Table 3, Table A7 |
| T3 | same ANALYSIS.json: focus_holm_two | Accurate−mismatched +0.0061267361, 11/20 positive; change +0.0064347222, 13/20 positive; raw p=.537256/.582979, both Holm p=1 | Zero-effect/equivalence proof; mismatched diagnosis is superior | Results 5.5, Table A6 |
| T4 | same AUDIT.json; requests_candidates; old feedback_specificity_v2/requests_candidates | 595 vs 584 valid; final 600-request reported token ratio 5.7689 total, 54.7791 output | Complete billed cost; token ratio equals fee ratio | Reliability/resource reporting |
| T5 | same RESUME_12.json; attempt_history/before_resume_12 | 35 reused, 565 remaining, 16 archived interrupted attempts; 616 attempts total | Missing-at-random interruption; complete usage accounting | Methods, limitations, Appendix C |
| T6 | old feedback_specificity_v2/role_analysis/ANALYSIS.json | Original nonthinking fixed-pool R/G/U/B decomposition | Same gate/opportunity/rank decomposition for thinking candidates | Scope qualifiers in Section 6 |

Blueprint: add a separate paired follow-up Methods subsection and Results subsection; keep original main results and decomposition scoped; distinguish better proposal quality from diagnostic matching in Discussion; update abstract, conclusion, limitations, resource accounting and statistics appendix. Do not add a new confirmatory test to the cross-arm descriptive averages.

Validation: a separate audit agent independently reconstructed raw and S3 seed values from candidate holdouts and sealed selections (maximum deviation 0) and reproduced both exact sign-swap p values. No model requests or game replay were required. Precise intervals stay in the appendix, while the main text uses effects, directions and paired tests.

## Earlier evidence ledger

| ID | Evidence | Claim permitted | Limit |
| --- | --- | --- | --- |
| E1 | FINAL_REPORT.md; results/direct_reciprocity_main_v2/CONTROL_ANALYSIS.json | Previous nine default paired intervals include zero | Does not establish equivalence, causal attribution, or evolution failure |
| E2 | MAIN_MATRIX_FINDINGS.md; FACTOR_COMPARISONS.json | Prompt/selection-dependent exploratory patterns | Post hoc motivation, not new confirmatory data |
| L1 | Willis et al. 2025, https://arxiv.org/html/2501.16173v1 | Prompting and selection of fixed LLM strategy libraries | Refine is self-critique; Moran does not generate policies online |
| L2 | Hennes, Li, Schultz, Lanctot 2026, https://arxiv.org/html/2603.10098v1 | Code-space oracles use opponent context and iterative utility feedback | Different games; does not isolate IPD causal understanding |
| L3 | Chong, Tiño, Yao 2008, https://www.cs.bham.ac.uk/~pxt/PAPERS/ieee_tec07.pdf | Internal fitness and test-distribution generalization are distinct | Not an LLM attribution study |
| L4 | Oved, Pony, Naparstek, Barzelay 2026, https://arxiv.org/abs/2609.19799 | Width/depth budget allocation changes search comparisons | Not evidence that evolutionary search or feedback is ineffective |
| N1 | results/feedback_attribution_v1/manifest.json | Frozen new protocol and jobs | 120 proposals, conditional on historical initial populations |
| N2 | results/feedback_attribution_v1/ANALYSIS.json | New measured effects once complete and audited | Five seed clusters, one step, one model |
| N3 | results/feedback_attribution_v1/SELECTION_ANALYSIS.json | Training-only best-of-two acceptance diagnostic | Added after partial results; not actual multigeneration selection |
| N4 | results/feedback_attribution_v1/BEHAVIOR_ANALYSIS.json | Changes on controlled behavior probes | Probes seen by diagnostic arm; not independent holdout |
| N5 | results/feedback_attribution_v1/RECORD_AUDIT.json | 120 outcomes, 360 setting aggregations, source and response identities checked | Not full independent game replay |

Phase 1 completed 2026-09-19. N2–N5 now complete. True−shuffled default score is −0.0015167 with exploratory CI [−0.10490, 0.09825]; diagnostic−true is +0.1559583 with CI [0.06870, 0.23635] and exact paired sign-flip p=0.0625. Diagnostic offspring still underperform their own parents on average (−0.101725 per round). After training-only acceptance, diagnostic−true is +0.0277167 with CI [−0.03460, 0.09003]. These bounds are retained in the draft; no claim of equivalence, proven internal attribution, or stable multi-generation improvement is warranted.

Literature independently checked by a fresh-context verifier on 2026-09-18. Willis, CSRO and Chong were checked against full text; Oved claims limited to verified abstract. No firstness claim was verified. Chong bibliographic details: IEEE Transactions on Evolutionary Computation 12(4), 479–505, DOI 10.1109/TEVC.2007.907593.

## Chapter blueprint

1. Motivation: distinguish selecting success from generating an effective modification; E1–E2 motivate, do not prove mechanism.
2. Related work: L1–L4 exclude prompting, generalization and budget matching as standalone novelty.
3. Questions: explicit score pairing, presence of score, diagnostic information, multi-generation accumulation.
4. Methods: N1; fixed parents and real selection, interventions only at generation interface, independent test panel, seed-level analysis.
5. Prior observations: E1–E2, clearly historical.
6. New results: N2; all arms and failure rates before interpretation.
7. Discussion: identify which explanations survive, no internal reasoning claim from performance alone.
8. Conclusion: bounded by actual completed stages; future multi-generation work never written as completed.

## Known gaps

- Hidden scores do not remove information implicit in selecting the parent.
- Diagnostic vs true confounds targeted information with context length and additional evaluation.
- One-step effects are not cumulative evolution effects.
- Five seeds cannot support a two-sided exact sign-flip p below 0.0625 even when all signs agree.
- New source hashes do not prove behavioral or family-disjoint generalization.
- API generation randomness is not a controlled matched seed; pairing is by parent and draw block.


## 2026-09-24 新增探索性可视化证据

| 编号 | 可写观点 | 证据 | 边界 |
|---|---|---|---|
| V1 | 候选质量改善覆盖原20种群，匹配差仍方向混合 | population_summary.json；296→489个测试改善；原始均值20/20上升 | 同20种群；配置差不是纯思考因果效应 |
| V2 | 外部选择改变防御/恢复组合，方向依赖池 | behavior/ANALYSIS.json；旧恢复18/20加快且暴露17/20上升；新暴露13/20降低、恢复10快10慢 | 五条件等权的事后观察，不是诊断匹配效应 |
| V3 | 局部行为改善不等于H改善 | 第三真实例子局部防御/恢复改善，H−0.03233；V通过父代门控但输给另一候选 | 事后近类别中位数示例，不估计总体概率 |
| V4 | 全体代码在共同表示中的分布可追溯 | 1419记录/1407唯一代码，共享PCA、二维20.86% | PC1与代码字符数rho−0.701；不证明行为簇、机制或多代演化 |

文件均在 `results/reciprocity_population_visuals_20260924/`；独立科学审核未发现阻断问题。新增4条文献以Zotero全文或原始来源核验，查阅轨迹见文献图表笔记。
