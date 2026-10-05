# Independent behaviour across proposal and S3 deployment

Post-hoc exploration; no new model requests or games. All averages first aggregate within the 20 original population seeds.

| Configuration | Probe mode | Metric | Parent | Raw | S3 | S3 − raw | Positive / negative / zero seeds |
|---|---|---|---:|---:|---:|---:|---|
| non_thinking | controlled | defection_exposure | 0.129833 | 0.073917 | 0.099200 | +0.025283 | 17 / 3 / 0 |
| non_thinking | controlled | recovery_rounds | 14.940278 | 16.698889 | 15.120389 | -1.578500 | 2 / 18 / 0 |
| non_thinking | controlled | not_recovered | 0.286944 | 0.349056 | 0.276444 | -0.072611 | 1 / 19 / 0 |
| non_thinking | controlled | mutual_cooperation | 0.709611 | 0.613150 | 0.686067 | +0.072917 | 19 / 1 / 0 |
| non_thinking | natural | defection_exposure | 0.112333 | 0.063300 | 0.069367 | +0.006067 | 12 / 8 / 0 |
| non_thinking | natural | recovery_rounds | 17.058611 | 18.352639 | 17.497333 | -0.855306 | 3 / 17 / 0 |
| non_thinking | natural | not_recovered | 0.360833 | 0.413861 | 0.363556 | -0.050306 | 1 / 19 / 0 |
| non_thinking | natural | mutual_cooperation | 0.635778 | 0.551267 | 0.608600 | +0.057333 | 20 / 0 / 0 |
| thinking | controlled | defection_exposure | 0.129833 | 0.132117 | 0.118500 | -0.013617 | 7 / 13 / 0 |
| thinking | controlled | recovery_rounds | 14.940278 | 13.350944 | 13.963444 | +0.612500 | 10 / 10 / 0 |
| thinking | controlled | not_recovered | 0.286944 | 0.241222 | 0.267667 | +0.026444 | 11 / 9 / 0 |
| thinking | controlled | mutual_cooperation | 0.709611 | 0.742978 | 0.709822 | -0.033156 | 7 / 13 / 0 |
| thinking | natural | defection_exposure | 0.112333 | 0.103600 | 0.069833 | -0.033767 | 5 / 15 / 0 |
| thinking | natural | recovery_rounds | 17.058611 | 15.104417 | 15.502556 | +0.398139 | 10 / 10 / 0 |
| thinking | natural | not_recovered | 0.360833 | 0.301139 | 0.320778 | +0.019639 | 12 / 8 / 0 |
| thinking | natural | mutual_cooperation | 0.635778 | 0.676728 | 0.649667 | -0.027061 | 6 / 14 / 0 |

## Matched versus mismatched feedback reports

These are the relevant between-arm descriptive contrasts; within-arm parent comparisons do not establish a matching effect.

| Configuration | Mode / stage / metric | Accurate − mismatched | Positive / negative / zero seeds |
|---|---|---:|---|
| non_thinking | controlled/raw/defection_exposure/accurate_minus_mismatched | +0.013083 | 8 / 9 / 3 |
| non_thinking | controlled/S3/defection_exposure/accurate_minus_mismatched | -0.014000 | 7 / 10 / 3 |
| non_thinking | controlled/raw/recovery_rounds/accurate_minus_mismatched | -0.159306 | 8 / 12 / 0 |
| non_thinking | controlled/S3/recovery_rounds/accurate_minus_mismatched | +0.121667 | 10 / 10 / 0 |
| non_thinking | controlled/raw/not_recovered/accurate_minus_mismatched | -0.007778 | 12 / 8 / 0 |
| non_thinking | controlled/S3/not_recovered/accurate_minus_mismatched | +0.003333 | 9 / 11 / 0 |
| non_thinking | controlled/raw/mutual_cooperation/accurate_minus_mismatched | +0.007056 | 10 / 9 / 1 |
| non_thinking | controlled/S3/mutual_cooperation/accurate_minus_mismatched | +0.004889 | 11 / 9 / 0 |
| non_thinking | natural/raw/defection_exposure/accurate_minus_mismatched | +0.007000 | 9 / 8 / 3 |
| non_thinking | natural/S3/defection_exposure/accurate_minus_mismatched | -0.009500 | 8 / 7 / 5 |
| non_thinking | natural/raw/recovery_rounds/accurate_minus_mismatched | -0.121111 | 10 / 10 / 0 |
| non_thinking | natural/S3/recovery_rounds/accurate_minus_mismatched | +0.199722 | 10 / 10 / 0 |
| non_thinking | natural/raw/not_recovered/accurate_minus_mismatched | -0.011250 | 10 / 10 / 0 |
| non_thinking | natural/S3/not_recovered/accurate_minus_mismatched | +0.001389 | 10 / 9 / 1 |
| non_thinking | natural/raw/mutual_cooperation/accurate_minus_mismatched | -0.004778 | 11 / 9 / 0 |
| non_thinking | natural/S3/mutual_cooperation/accurate_minus_mismatched | -0.020000 | 10 / 9 / 1 |
| thinking | controlled/raw/defection_exposure/accurate_minus_mismatched | -0.004083 | 12 / 8 / 0 |
| thinking | controlled/S3/defection_exposure/accurate_minus_mismatched | +0.013667 | 10 / 9 / 1 |
| thinking | controlled/raw/recovery_rounds/accurate_minus_mismatched | +0.698611 | 12 / 8 / 0 |
| thinking | controlled/S3/recovery_rounds/accurate_minus_mismatched | +1.358056 | 12 / 8 / 0 |
| thinking | controlled/raw/not_recovered/accurate_minus_mismatched | +0.028472 | 12 / 8 / 0 |
| thinking | controlled/S3/not_recovered/accurate_minus_mismatched | +0.065833 | 12 / 7 / 1 |
| thinking | controlled/raw/mutual_cooperation/accurate_minus_mismatched | -0.011778 | 10 / 10 / 0 |
| thinking | controlled/S3/mutual_cooperation/accurate_minus_mismatched | -0.052611 | 9 / 11 / 0 |
| thinking | natural/raw/defection_exposure/accurate_minus_mismatched | -0.027667 | 8 / 11 / 1 |
| thinking | natural/S3/defection_exposure/accurate_minus_mismatched | -0.023833 | 9 / 8 / 3 |
| thinking | natural/raw/recovery_rounds/accurate_minus_mismatched | -0.244583 | 12 / 8 / 0 |
| thinking | natural/S3/recovery_rounds/accurate_minus_mismatched | +0.225556 | 9 / 11 / 0 |
| thinking | natural/raw/not_recovered/accurate_minus_mismatched | -0.026111 | 10 / 10 / 0 |
| thinking | natural/S3/not_recovered/accurate_minus_mismatched | +0.009722 | 10 / 9 / 1 |
| thinking | natural/raw/mutual_cooperation/accurate_minus_mismatched | +0.032139 | 10 / 10 / 0 |
| thinking | natural/S3/mutual_cooperation/accurate_minus_mismatched | -0.002778 | 11 / 9 / 0 |

## Illustrative cases

### Thinking OFF: adopted, defence/recovery trade-off

- ID: `non_thinking/s217-rank3-d0-pos2`; arm: cooperation; draw: 0; S3 adopted: True.
- Child SHA256: `0b6101dcc0cc4111e5f792eb1685518cc2aac5cb1a3fbeba8f3c01c85407e2b4`; parent SHA256: `d356d73eef810186620c1482531eaa2056505d8d7df31117e540b4c371dc6f79`.
- Eligibility category has 31 candidates; median H gain +0.042125. Selected nearest that median, config/ID tie-break.
- H payoff 1.929417 → 1.971542; delta +0.042125.
- Controlled defence delta -0.430000; recovery-time delta +3.183333.
- S3 validation scores: {'parent': 2.0830625, 'child': 2.1197083333333335, 'adopted': 2.1197083333333335}; passed parent gate: True; actual adopted ID: s217-rank3-d0-pos2.

父代在历史长至少10轮且对手最近连续两次D时，以0.5概率D；候选新增基于累计D占优或低合作率的分支，进入该分支后仅以0.06概率C。在持续背叛探针中单方面合作由0.49降至0.06，同时三个恢复探针的平均截尾恢复时间增加3.1833轮。这描述同一真实修改的防御与恢复变化，不把其中某段代码认定为已经通过消融验证的原因。

### Thinking ON: adopted, faster mean recovery

- ID: `thinking/s210-rank3-d1-pos3`; arm: accurate; draw: 1; S3 adopted: True.
- Child SHA256: `d2df3505e37cb7dba8117930e026633a2135c0340899f402dfc4f327d2770333`; parent SHA256: `54c3141925f91f2b4ac07397b995878631dbf19201a4b0150bd0a37c3771422b`.
- Eligibility category has 151 candidates; median H gain +0.082542. Selected nearest that median, config/ID tie-break.
- H payoff 1.902375 → 1.984917; delta +0.082542.
- Controlled defence delta +0.000000; recovery-time delta -1.750000.
- S3 validation scores: {'parent': 2.0514583333333336, 'child': 2.1233333333333335, 'adopted': 2.1233333333333335}; passed parent gate: True; actual adopted ID: s210-rank3-d1-pos3.

父代含最近8轮至少一半为D的历史窗口分支；候选压缩为若对手上一轮C则C（第100轮除外），并在连续D长度为1且累计D不超过2、或连续D长度为3且累计D不超过4时输出C，否则D。候选在GTFT恢复探针的末五轮相互合作由0.16升至0.75，但TFT探针由0.05降至0，三个恢复探针的平均截尾时间减少1.75轮。因此该例只说明平均恢复改善，不表示所有恢复情境均改善，也不建立准确匹配反馈的因果效应。

### Not adopted, lower independent-test payoff

- ID: `thinking/s213-rank6-d0-pos1`; arm: cooperation; draw: 0; S3 adopted: False.
- Child SHA256: `fc9382bf5e62bb2ffc4ffa353150c0246a68fba9ef6f783cf2182be7998bbb91`; parent SHA256: `b03746312495cd60a2f12ec0055e243ac42035fea0bfe3a8d1eda0e4c5de390e`.
- Eligibility category has 331 candidates; median H gain -0.032333. Selected nearest that median, config/ID tie-break.
- H payoff 1.971375 → 1.939042; delta -0.032333.
- Controlled defence delta -0.400000; recovery-time delta -12.950000.
- S3 validation scores: {'parent': 2.1321250000000003, 'child': 2.1374375, 'adopted': 2.1793333333333336}; passed parent gate: True; actual adopted ID: s213-rank6-d1-pos1.

父代在双方累计D均超过20时按轮次奇偶交替C/D；候选在对手累计D超过历史的一半时直接D，并对特定交替报复序列提供C响应。候选还会在最近10轮对手无D时根据此前对方对自身D的响应决定随机D概率。局部探针中持续背叛暴露降至0、平均恢复时间减少12.95轮，H收益却下降0.03233；这说明这些局部探针并不构成完整的收益充分统计量。该候选V为2.13744，高于父代2.13213，已经通过门控；未采用是因为同池另一候选V为2.17933，而非门控拒绝。

## Captions

**Behaviour stages.** Independent probes show that external adoption changes the behavioural composition of the same proposal pools. Thin lines join the means of each of 20 original populations; bold lines and circle/square/triangle markers show equally weighted grand means for fixed parents, all candidate generation outputs, and S3 deployment. Panels pool all five information conditions and use controlled H probes: lower unilateral cooperation against sustained defection indicates less exposure, while lower capped time indicates faster recovery across TFT, GTFT and ALLC restoration probes. S3 uses its sealed validation decision, with the parent retained if no candidate qualifies; these are post-hoc comparisons of the parent, raw-proposal and selected-output stages.

**Real strategy examples.** Concrete candidate revisions change defence and recovery differently, and favourable local probe changes need not raise independent-test payoff. Cells are the stored mean of 20 probe runs for the fraction of the final five rounds with the indicated cooperative behaviour, after seven externally supplied mutual-cooperation rounds and 40 measured rounds. The three post-hoc categories are non-thinking adopted gains with a defence/recovery trade-off, thinking adopted gains with faster mean recovery, and unadopted losses; within each category the displayed candidate is nearest the category-median H payoff change. V is the validation payoff used by S3, and H is the separate test payoff; the unadopted example passes the parent gate but loses to its higher-V pool competitor. IDs and code hashes are recorded in the companion analysis, and these illustrations do not estimate category prevalence or establish a report-matching effect.

## Figure-designer audit

Experimental-results figures. Paired stage paths expose population heterogeneity; annotated vector-cell fingerprints make individual changes inspectable without relying on colour. PDF/SVG vector exports and 300 dpi previews; physical width 6.802 inches at 0.95 text width; minimum font 8.7 pt; shape plus stage labels for paths and numeric annotations for heatmaps. Defence uses a zero baseline, recovery retains its full relevant range, and numeric fingerprints share the fixed 0–1 scale. No new trials, no 3D, no inferred psychological mechanism. Source metrics and all raw-behaviour/payoff aggregates were matched to released results.
