# 错配报告是否被发现：思维链判读方法与验证

**脚本：** `tools/judge_mismatch_detection_summary.py`（单文件）
**输出：** `results/mismatch_detection_jev/`
**数据：** `results/feedback_specificity_thinking_384k_20260923`（Thinking ON，600 条请求）

**核对更新：** 2026-09-30。全量统计以 [summary.json](../../results/mismatch_detection_jev/summary.json)、[REPORT.md](../../results/mismatch_detection_jev/REPORT.md) 和逐条 judgments 为准；早期问法校准的数字单独标注，不替代最终缓存。

**核心判断：** 错配在 Thinking ON 的部分可见推理中能被自发察觉。严格口径检出 31/120 条 Mismatched 轨迹，其中 30 条判为继续使用报告、1 条判为弃用精确数值并提交修改后的策略。识别并不普遍，识别也不必然导致弃用；这项观察不足以单独解释准确报告为何未稳定优于错配报告。

## 1. 要回答的问题

在 Mismatched 条件下，模型拿到的是**同一种群另一位策略**的行为报告，却被标注为父代自身的测量行为。
问题：思维链里是否出现了"这份报告不属于这个策略"的判断？

本分析检验**失配的可检出性**（detectability），并区分“质疑报告归属”与“随后如何处理报告”。生成提示没有要求模型检查错配，因此轨迹中的归属质疑属于修改过程中自发出现的判断。它是对干预可察觉性的检查，不直接检验错配识别是否造成了收益变化。

样本只来自 DeepSeek 的 Thinking ON：五条件各 120 条请求，共 600 条；不能把这里的检出率推广到 OFF 或 Qwen。判读对象是输出的可见推理文字，经抽取和自动判读后得到标签，不能将这些标签当作模型内部认知或全部代码行为的完整测量。

## 2. 为什么不能直接把思维链送给 Jev

`jev-1.13` 的每请求预算是 **32,768 tokens**（`state` + 最长问题）。实测边界：

| state 字符 | cl100k 计数 | Jev 实际 input_tokens | 结果 |
| ---: | ---: | ---: | --- |
| 4,000 | 1,102 | 1,535 | OK |
| 40,000 | 11,247 | 12,135 | OK |
| 100,000 | 29,971 | 32,447 | OK |
| **101,000** | 30,219 | **32,713** | **OK** |
| 103,000 | 30,855 | — | `max_tokens_exceeded` |
| 130,000 | 39,594 | — | `max_tokens_exceeded` |

边界落在 32,713 与约 33,400 之间，即 32,768 = 2¹⁵。附带实测两个校准量：

- Jev 实际 tokenizer 比 `cl100k_base` 多约 **7%**（脚本里以 `JEV_TOKEN_SAFETY = 1.07` 计）
- 英文推理文本约 **3.3 字符/token**

本次思维链长度为中位 154,564 字符（p90 = 185,697），**远超预算**，必须压缩。

## 3. 流程

```
思维链 (≈150k 字符)
   │
   ├─ ① deepseek-flash 抽取（map）：按 40k 字符分块，重叠 2k
   │      每块输出固定模板：ORIGIN / CONTRADICTION / RESOLUTION / STRATEGY
   │      ORIGIN 要求**逐字引用**，不得转述
   │
   ├─ ② 长度校验：合并各块抽取结果，若超 18,000 Jev tokens
   │      则再调用一次合并（保留全部引语）
   │
   └─ ③ Jev 判读：同一个 `state` 上两个三档 Choice 并行
           origin      报告来源归属   ← 主判据
           resolution  最终处理方式
```

`state` 只含**报告块 + 抽取结果**，**条件标签从不进入请求**，否则判读会被泄漏。

### ⚠ 不要用 difflib 提取报告块

最初用 `difflib.SequenceMatcher(None, score_prompt, arm_prompt, autojunk=False)` 找"最大插入跨度"
来定位块。它正确但极慢：两个 ~23k 字符的提示词需要 **12.1 秒/次**，300 个
(context, arm) 组合合计约 **1 小时的单线程 CPU**。因为它在持住 GIL，整个多线程运行会被串行化——
实测 16 并发只跑出 **4 文件/分**（对比单次 Jev 调用仅 3.5 秒）。

块总是以固定表头开头（`MEASURED PARENT BEHAVIOR.` / `BACKGROUND INFORMATION.` /
`GENERAL COOPERATION ADVICE.`），所以改为字符串扫描即可，**瞬时完成**。
已用结构不变量验证 240/240 个组合：`prompt == 公共主体 + "\n" + block + 固定结尾`，
与 difflib 的结果等价。修好后全量 600 文件从 **110 分钟降到 0.3 分钟**。

### 主判据：三档 Choice

| 档 | 含义 |
| --- | --- |
| `questions_its_origin` | 提出报告可能来自另一策略 |
| `accepts_as_labelled` | 当作被标注策略自身的行为接受（**可以**与数值不合，但不怀疑来源） |
| `silent` | 完全未涉及报告来源 |

`resolution` 同样三档：`kept_using` / `discarded` / `unclear`。

**为什么用 Choice 而不是阈值化的二值判断：**

1. **二值会把两个不同状态压成同一个"否"。** "沉默地照用" 与 "明确认定这就是我的数据"
   是两种不同的认知状态；二值都记为 0。三档把它们分开。
2. **Choice 返回 `confidence` 与完整概率分布**；二值概率没有独立置信度字段
   （`{type, noul}` 只有两个字段，实测确认，见 §3.1）。
3. **不需要人为切点。** Choice 用 argmax 即可；概率切点只作为稳健性交叉检验。

报告同时给出一个概率口径 `leaning` = P(`questions_its_origin`) ≥ 阈值，以及叠加置信度门限的
`confident` 窄口径。

这些概率与置信度来自**判读者**。概率切点和置信度门限筛选的是同一 Choice 问题上的判读结果，不能分别解释为“模型曾经想到过”与“模型最终确信”。是否一度提出后又否定，需要回看原始轨迹；是否弃用由单独的 resolution 问题测量。

### 3.1 早期问法校准：两种提问方式的语义差异

**早期二值 Noul 问的是“是否曾提出”，Choice 要求描述抽取结果的整体立场。** 实测中最能说明这一点的是
`s203-rank1-d0-pos1`（Mismatched，已人工确认为正例）：

| 设计 | 结果 |
| --- | --- |
| 二值概率「是否提出报告可能来自另一策略」 | **0.67** → 按阈值算检出 |
| Choice「整体上如何处理报告来源」 | P(origin)=**0.48**，标签 `accepts_as_labelled` |

原文实际过程是：

> *"So I'm stuck. Let's consider that the measurement might be for a different parent? The parent
> slot is 5. The code at slot 5 is as above. **The measured parent behavior is likely for that
> code.** So there must be a reason parent defects."*

即**先提出假设、再自我否定**，最终立场是"报告仍属于该父代"。所以：

- Noul 的 0.67 没错 —— 它确实提出过；
- Choice 的 `accepts_as_labelled` 也没错 —— 它的最终立场是接受。

两个设计**测的不是同一件事**，引用结果时必须说明用的是哪一个。Choice 要求选择最能描述抽取结果整体的标签，但其判据允许试探性、保留性或自我怀疑的归属质疑；因此不能把 questions_its_origin 自动译成“最终认定报告不属于该策略”。

上表记录的是早期问法对照。最终全量缓存中，同一条 `s203-rank1-d0-pos1` 的 Choice P(origin)=0.56、标签为 questions_its_origin、confidence=0.34：它计入宽口径，但未通过 0.60 的置信度门限。正式引用全量率时使用 §5 的最终缓存，不能把早期 0.48 的数值混入最终统计。

### 3.2 Noul 缺少置信度

实测 SDK 返回字段：

```
Noul   → {type, noul}                                 ← 无 confidence
Choice → {type, choice, probabilities, confidence}    ← 有 confidence
```

Noul 是二值的，任何 confidence 都只是 $|p-0.5|$ 的单调函数，不含额外信息；Choice 则给出
完整三档分布，因此能报告 `confidence` 并区分"沉默照用"与"明确接受"。

在真实文件上的对照：

| 文件 | arm | Noul | Choice P(origin) |
| --- | --- | ---: | ---: |
| `s200-rank1-d1-pos0` | mismatched | 0.94 | 0.96 |
| `s217-rank6-d1-pos1` | mismatched | 0.97 | 1.00 |
| `s200-rank1-d1-pos3` | accurate | 0.56（贴阈值） | **0.13** |
| `s209-rank3-d1-pos2` | accurate | 0.07 | 0.01 |

正例上两者一致；在**临界负例**上 Noul 偏高。

（保留：该次对照的 Noul 提问文本比脚本内的短，0.56 与脚本内 0.43 之差不能干净归因于提问类型。）

### 为什么用抽取而不是摘要

第一版用"摘要"提示词、单次送入 110k 字符，在已知正例 `s200-rank1-d1-pos0` 上**漏检**
（Jev 判定 0.04），且摘要文本还断言"the trace never questions the origin of the report"——
与事实相反。定位后确认关键句位于思维链 47% 处，**并未被截断**，是摘要器自己丢弃了信号。

改为分块抽取后，同一文件的关键句被逐字保留：

```
ORIGIN: "... So measurement 4.29 is impossible for this parent. Therefore, the
measurement must be for a different parent, or I am misinterpreting the probe description."
```

Jev 判定从 0.04 升至 **0.96**。

## 4. 验证（`pilot` 命令）

金标准是**临时**的：

- **正例（17）**：Mismatched 条件中，文本显式提出报告可能属于另一策略的思维链。
  正则 `(measured behavior|measurement[s]?|measured numbers)...(must|might|may|could|can) be
  (for|from|of|taken with) (a )?(different|another)`。该模式在 Accurate / Background /
  Cooperation / Score 四个条件上**各命中 0/120，合计 0/480**；17 条全部人工读过。
- **负例（17）**：与每个正例**同 context、同 draw** 的 Accurate 臂文件，作为配对对照。

### 4.1 早期 34 文件配对校准

早期 pilot 在概率阈值 0.40 下得到 TP=17、FP=0、TN=17、FN=0；当时 [0.10, 0.45] 是敏感度和特异度均为 1.000 的稳定带，据此选取默认阈值 0.40。当时 Choice 的 argmax 标签命中 16/17 个正例，另一个是 §3.1 的两义轨迹。

这是**早期校准记录**，不是最终缓存的全量验证。17 个正例均判为 kept_using，只能说明这些选入 pilot 的轨迹中，归属质疑没有伴随明确弃用；全量结果另有一例弃用，见 §5.3。

### 4.2 最终缓存的流程复核

[validation.json](../../results/mismatch_detection_jev/validation.json) 使用 17 条正则筛选并经人工确认的正例，以及四个非错配条件的 480 条条件对照。概率阈值 0.40 下，TP=17、FP=5、TN=475、FN=0，敏感度 1.000、特异度 0.990。叠加 confidence≥0.60 后，四个非错配条件的检出数为 0/480；这描述当前样本的判读结果，不能据此保证新样本没有误报。

这套标签不是独立的全量人工真值：17 个正例按特定文本模式挑选，480 个负例按实验条件指定；其余 103 条 Mismatched 轨迹没有因此获得独立负标签。敏感度和特异度衡量这个已标注集合上的流程表现，不能代表完整错配样本的真实识别准确率。

**不要用 pilot 数据估算总体检出率。** pilot 正例被人为富集，17/17 不是 Mismatched 的总体率；运行中“预计全量只有 17/120”的早期推测也已被最终 33/120 的宽口径结果替代。可引用的全量检出率见下一节。

## 5. 全量结果（600 文件）

| 条件 | 文件 | questions_its_origin | accepts_as_labelled | silent | leans_origin | **confident_origin** | 均值 P | 均值置信度 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **mismatched** | 120 | **0.275** | 0.725 | 0.000 | **0.275** | **0.258** | 0.279 | 0.903 |
| accurate | 120 | 0.033 | 0.967 | 0.000 | 0.033 | 0.000 | 0.034 | 0.897 |
| cooperation | 120 | 0.008 | 0.992 | 0.000 | 0.008 | 0.000 | 0.005 | 0.661 |
| score | 120 | 0.000 | 0.992 | 0.008 | 0.000 | 0.000 | 0.010 | 0.771 |
| background | 120 | 0.000 | 1.000 | 0.000 | 0.000 | 0.000 | 0.004 | 0.841 |

前三个标签列是 argmax 标签的比例，均值 P 指 P(questions_its_origin)。Mismatched 的标签计数为 33/87/0，Accurate 为 4/116/0；比例按三位小数显示。

**四个非错配条件合并：leans_origin 5/480 = 1.0%；加置信度门限后 0/480 = 0.0%。** Accurate 本身也含行为报告，因此不能称这四个条件为“非报告条件”。

### 5.1 正则确认集与自动判读候选不是全量真值

正则模式（`GOLD_PATTERN`）在 mismatched 上只命中 17/120 = 14.2%。但 Jev 判定 33/120 = 27.5%，
**多出 16 条**。正则只有出现特定措辞
（`must/might be for a different/another`）才命中。人工抽查确认：

| 文件 | 原文（逐字） |
| --- | --- |
| `s211-rank3-d0-pos0` | "Could the measured parent behavior be for a different parent?" / "The measured parent behavior might be for slot6, not slot2." |
| `s201-rank6-d1-pos3` | "Maybe the measured parent behavior is for a different parent?" |
| `s207-rank1-d0-pos4` | "Perhaps the measurement is from a different version of the parent?" |
| `s215-rank3-d1-pos2` | "Wait, could it be that the parent is not the one being measured?" |
| `s204-rank6-d1-pos1` | "Maybe the measured parent behavior in prompt for PARENT is not slot3?" |

在这 16 条中，约 10 条是明确的归属质疑，约 3 条是质疑探针机制而非报告归属，
约 3 条没有 ORIGIN 抽取（疑似误报）。这说明自动判读候选仍需核查：

> 17 条正则确认轨迹是已发现的显式归属质疑集合，33 条是当前自动判读的宽口径候选。没有对全部 120 条轨迹作独立人工判读，因此不能把 33 当作真实检出数上界，也不能由此给出真实率的 26–28% 点估计。

引用时必须写明用的是哪个口径，不要单独引用正则的 14.2%。

### 5.2 置信度门限下，当前非错配对照为零检出

五条非错配条件的宽口径检出，其判读置信度为 0.26–0.53；16 条额外 Mismatched 候选中 15 条 ≥0.60：

| 组 | n | confidence 范围 |
| --- | ---: | --- |
| 非错配条件的宽口径检出 | 5 | 0.26 – 0.53 |
| mismatched 额外检出 | 16 | 0.29 – 1.00（中位 0.96，15 条 ≥0.60） |

因此 `DEFAULT_CONFIDENCE_GATE = 0.60` 把四个非错配条件的检出率从 1.0% 降到 **0.0%**，
代价是 2 条低置信度的 mismatched（33→31）。

非错配条件中的归属质疑可能是生成模型错误怀疑报告，也可能是判读误差；没有逐条独立真值时，不能把所有对照检出都归为判读器假阳性。

门限扫描：

| 门限 | mismatched | 四类对照 |
| ---: | ---: | ---: |
| 不过滤 | 33/120 (0.275) | 5/480 (0.0104) |
| ≥0.50 | 31/120 (0.258) | 1/480 (0.0021) |
| **≥0.60** | **31/120 (0.258)** | **0/480 (0.0000)** |
| ≥0.70 | 30/120 (0.250) | 0/480 (0.0000) |

**正文优先报告严格口径，补充材料报告门限敏感性。** 宽口径为 P(origin)≥0.40，窄口径再要求 confidence≥0.60；两者均使用同一个 Choice 问题。窄口径表示判读者更有把握，不表示生成模型最终确信或已经弃用。

### 5.2b 三档概率的形态：双峰，而非普遍怀疑

三档概率每条文件构成一个和为 1 的分布。跨文件均值：

| 条件 | n | P(origin) | P(accepts) | P(silent) |
| --- | ---: | ---: | ---: | ---: |
| **mismatched** | 120 | **0.279** | 0.690 | 0.031 |
| accurate | 120 | 0.034 | 0.927 | 0.038 |
| cooperation | 120 | 0.005 | 0.775 | 0.219 |
| score | 120 | 0.010 | 0.846 | 0.145 |
| background | 120 | 0.004 | 0.895 | 0.101 |

**mismatched 的判读 P(origin) 明显集中在两端：**

```
0.0-0.1   76   ← 判读概率低
0.1-0.3   11
0.3-0.5    0   ← 中间地带完全是空的
0.5-0.9    5
0.9-1.0   28   ← 判读概率高
```

即 115/120 落在 P(origin)<0.3 或 ≥0.9 两端。0.279 的跨文件均值不能读成每条轨迹都带有约 28% 的怀疑，也不能从低判读概率断言模型内部“完全没想到”。这些数值描述判读者对可见文字的判断。

**一个更保守的窄口径：** `P(origin) ≥ 0.9` 在 mismatched 上命中 **28/120 = 23.3%**，
在其余四臂为 **0/480**。这个口径比 `P≥0.40 且 conf≥0.60` 更严格，且不需要置信度门限，
可作为门限敏感性结果引用，但高判读概率本身不构成独立人工真值。

**silent 档的解释能力有限：** Mismatched 上 P(silent) 最大为 0.14，四个非错配条件中 silent 标签总共只出现 1 次。不能依据这一档很少出现就判断所有轨迹都充分关注或利用了报告。

### 5.3 察觉有时发生，但不必然导致弃用

| 条件 | kept_using | discarded | unclear |
| --- | ---: | ---: | ---: |
| mismatched | **119** | 1 | 0 |
| 其余四条件 | 475 | 0 | 5 |

**31 条通过严格口径的归属质疑中，30/31（96.8%）判为 kept_using，1/31 判为 discarded。** 全量 120 条 Mismatched 中，119 条判为继续使用，1 条判为弃用。resolution 是对推理中报告处理方式的判读，不能直接替代候选代码的行为或收益测量。

唯一弃用例为 [s219-rank3-d1-pos4 的原始轨迹](../../results/feedback_specificity_thinking_384k_20260923/requests_candidates/s219-rank3-d1-pos4.json)，其[判读记录](../../results/mismatch_detection_jev/judgments/s219-rank3-d1-pos4.json)给出 P(origin)=0.99、origin confidence=0.99、resolution=discarded。轨迹根据父代代码推演出最初四轮合作率为 0.5，却发现报告是 0.95，随后指出测量不属于该父代。后续它表示不再依赖精确测量值，转而以同群另一策略的代码思路为基础提交修改后的有效策略。这里的“自行修正”指修改策略代码，并非修正报告中的数值；也不能仅凭这一例认定修订后的测试收益提高。

这项结果支持“**失配是真实且有时可察觉的，模型有时能分辨**”：模型未被要求检查错配，却在部分可见推理中提出了报告归属问题，个别轨迹还转向不依赖精确报告值的修订。不过，大多数轨迹未通过严格识别口径，识别后也多被判为继续使用报告。识别不是普遍现象，弃用更加罕见。

### 5.4 对论文结果的解释边界

这些观察是 Thinking ON 设置下的探索性过程证据，**不足以单独解释**准确报告相对错配报告未稳定取得更好原始候选收益的现象。它们没有随机操纵“是否识别错配”，也没有建立识别、报告处理、代码改动与收益差之间的因果链；本分析亦未覆盖 OFF 或 Qwen 的对应过程。

正文可以写“错配有时可被自发识别，但识别与弃用均不普遍”，不能写“匹配收益接近是因为模型普遍识别并修正错配”，也不能写“看出来不会影响代码行为”。Accurate−Mismatched 未显示稳定优势的收益结果须由原始候选的种群配对分析支撑，不能简写成两条件已被证明等效。120 条错配请求共享 20 个种群、60 个父代，以上比例是当前轨迹的描述，不把它们当作 120 个独立实验重复。

## 6. 命令

```powershell
python tools/judge_mismatch_detection_summary.py prep      # 规模与预算检查
python tools/judge_mismatch_detection_summary.py pilot     # 34 文件配对验证
python tools/judge_mismatch_detection_summary.py validate  # 混淆矩阵 + 阈值扫描
python tools/judge_mismatch_detection_summary.py run --workers 16  # 全量 600
python tools/judge_mismatch_detection_summary.py report    # 生成 REPORT.md
```

结果按文件缓存于 `results/mismatch_detection_jev/{summaries,judgments}/`，
已有缓存可复用；缺失缓存或使用 `--force` 强制重算时仍可能产生模型调用与费用。`--threshold`（默认 0.40）与 `--confidence`（默认 0.60）可调。`report` 从本地缓存汇总，不重新生成候选或重跑收益实验。

全量 600 条轨迹完成分块抽取与判读：Jev 输入 1,285,842 tokens，失败 0，超预算 0。600 是轨迹数而非抽取 API 调用数；逐条记录共含 2,621 个抽取分块，不能把它们写成 600 次分块调用。

## 7. 对照判读者的检出规模接近

已用 deepseek-flash 作对照判读者，在同一批抽取结果上重判全部 600 条：
**一致率 593/600 = 98.8%**（双方都判 YES 34、都判 NO 559、分歧 7），
mismatched 触发 34 对 33（均 /120），四类对照 3 对 5（/480）。

7 条分歧各向两边，且都有解释：

- **deepseek YES / Jev NO（3 条）**：均为模型在质疑**探针机制**（"one\_D\_TFT 到底怎么算"
  "分数是 24 轮还是 34 轮"），而非报告归属。最清楚的一条明确写着
  *"Therefore, my interpretation of the probe must be wrong."* —— 它把矛盾归因于**自己**。
  Jev 正确保持低分。
- **deepseek NO / Jev YES（4 条）**：其中 3 条正是 Jev 的低置信度假阳性（置信度 0.26–0.53），
  deepseek 正确地拒绝了它们。故在控制臂误报上 deepseek 反而更少（3 vs 5）。

但 deepseek 的置信度区分力较低：抽取模式下 570/600（95%）落在同一个值 0.95，取值仅 5 个；
Jev 则有 63 个不同取值。概率阈值仍可扫描，但 deepseek 的置信度门限在这批数据中缺少区分力；Jev 的置信度门限可以将当前四个非错配条件的检出数筛至零。因此保留 Jev 作主判据，并保留对照判读结果作为补充。

两个判读者在这批抽取结果上的检出规模接近，提供了判读稳健性的线索；高一致率不能替代独立人工真值，也不能验证错配识别导致收益变化的机制。

### 7.1 附带结论：抽取步骤是承重的

同一次对照中测了 deepseek 判读**原始思维链**（60k 字符分块，34 文件）：

| 判读输入 | 敏感度 | 特异度 |
| --- | ---: | ---: |
| 抽取结果 | **1.000** | 1.000 |
| 原始思维链 | **0.235**（17 个正例漏 13 个） | 1.000 |

改用 20k 字符分块后，6 个漏检中 5 个恢复检出，提示单次输入过长可能影响检出；这个对照没有单独识别“注意力稀释”的机制。

这些运行记录支持在当前流程中使用原文抽取，把约 15 万字符的轨迹压到数千字符，同时保留判据引语；不能推广成直接判读原始思维链必然失效的一般结论。

> 该对照实验的脚本与缓存已删除；上表数字来自当时的运行记录，如需复现需重跑
> （全量 600 条约 600 次额外 API 调用）。
