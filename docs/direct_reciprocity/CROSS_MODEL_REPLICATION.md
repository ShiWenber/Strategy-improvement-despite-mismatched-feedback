# Cross-Model Replication：第二条模型上的错配反馈对照

**日期**：2026-09-30
**对应审稿意见**：[`审稿意见.md`](../../审稿意见.md) 第 6 条（单模型与 Thinking ON/OFF 的泛化问题）
**代码**：`results/qwen3_8/analyze.py`（汇总）、`results/model_comparison_20260928/cross_model_summary.py`（本报告全部表格与断言）、`results/model_comparison_20260928/plot_cross_model_mainline.py`（论文图）
**数据**：`results/qwen3_8/{off,on}/`（Qwen）、`results/feedback_specificity_v2/`（DeepSeek OFF）、
`results/feedback_specificity_thinking_384k_20260923/`（DeepSeek ON）

本报告记录**第二个模型上的配对复现**：DeepSeek-V4.1-Flash 与 Qwen3.8-Flash 在同一批冻结的
种群、父代和提示词上各跑两套生成配置（Off / On），用来回答审稿意见第 6 条的泛化质疑。

---

## 0. 结论摘要

| # | 结论 | 证据强度 |
|---|---|---|
| 1 | 主对照 τ（准确诊断 − 错配诊断的原始候选增益）**在 4/4 个"模型 × 模式"配置中区间跨零** | 测量（20 种群/配置） |
| 2 | τ 的**符号跟随生成模式，而不是模型**：两个 Off 均为负，两个 On 均为正 | 描述（4 个点估计） |
| 3 | 两条 On 的 τ 几乎相同（+0.00613 vs +0.00611），差距 2×10⁻⁵ | 描述 |
| 4 | 外部选择（S3）的增益在 4/4 配置中**区间不含零**，为 τ 点估计的 13–104 倍，即使按 \|τ\| 置信上限口径也仍有 2.9–4.2 倍 | 测量 |
| 5 | 但本复现**不足以**支持"LLM 普遍如此"：只有两个模型、两条 On 的输出预算不同、两次采集非同期、无权重快照 | 声明（局限） |

**一句话**：把第二个模型（Qwen3.8-Flash）放进完全相同的配对设计后，主结论
"准确匹配的行为诊断没有可检出的原始收益优势"**在跨模型、跨模式上重复出现**；
而真正驱动收益的是外部选择通道，不是诊断匹配。

---

## 1. 为什么需要这个复现

审稿意见第 6 条指出：原稿只有一个模型标识 `deepseek-flash`，Thinking Off/On 是同一模型的
两种调用配置，**不能当作两个独立模型**；并且 On 相对 Off 同时改变原生思考、输出上限和有效采样规则，
所以 Off/On 的差异不能被归因于"思考机制"。审稿人建议：与其继续扩大 Thinking 分析，
不如**增加第二个明确版本的模型**。

本复现采取"完全配对"策略：不重新初始化种群、不新造父代、不改提示词，只替换生成端的模型，
从而把跨模型的差异限制在模型本身。相对地，作为对照的 CUDAnalyst 跨四个模型做出 alignment 结论，
本复现规模更小，只覆盖两个模型。

---

## 2. 设计

### 2.1 复用清单

Qwen 两臂**逐字复用** `results/feedback_specificity_v2` 的以下内容，未做任何重新初始化调用：

| 复用对象 | 说明 |
|---|---|
| 20 个独立种群、每群 12 个策略 | 与 DeepSeek 完全相同 |
| 60 个父代（按训练适应度第 1/3/6 名，每群 3 个） | 父代槽位、供体映射完全一致 |
| 5 个信息条件（score / accurate / mismatched / background / cooperation） | 附加文本逐字相同 |
| 600 份候选提示词 | 哈希一致；含 `mismatched` 的 derangement 供体分配 |
| 请求顺序 | 与 v2 冻结的随机排列一致 |
| 父代选择分与 H 评价记录 | 直接复用，不重跑 |

因此 Qwen 的两臂各 600 次候选请求，合计 1 200 次，加上零次初始化请求。

两臂与 DeepSeek 侧共用同一个引擎哈希
（`implementation_hash = 7f99254d…f15d5`，与 `results/feedback_specificity_v2/manifest.json` 一致）。

### 2.2 两条生成配置

| 项目 | Off | On |
|---|---|---|
| `enable_thinking` | `false` | `true` |
| `reasoning_effort` | — | `high` |
| `max_tokens` | 6 000 | 131 072（该模型公布的输出上限） |
| temperature | 1 | 1 |
| 模型标识 | `qwen3.8-flash` | `qwen3.8-flash` |

作为对照，DeepSeek 侧的两条配置分别是 `deepseek-flash` 关闭思考（输出上限 6 000）与
原生思考 `reasoning_effort=high`（输出上限 384 000）。

> **必须强调**：Qwen On 的输出上限（131 072）**低于** DeepSeek On 的 384 000。
> 因此两条 On 臂之间的收益量级差异**不能**当作模型能力差异来解释；
> 同理，每个模型内部的 Off/On 差异也**不能**归因于思考开关本身。

### 2.3 评价与封存

- 候选池用冻结的 S1/S2/S3 与 H 代码评价，版本哈希与 v2 一致（`implementation_hash` 相同）。
- 选择决定全部封存后才释放 H；`SELECTIONS_SEALED.json` 与 `H_RELEASED.json` 成对存在。
- **H 是一个已经被使用过的面板**，因此这是后续模型比较，**不是**新的盲测 holdout。
- 父子代 H 分数直接复用原记录（`REUSED_PARENT_H.json`），保证跨模型口径一致。

---

## 3. 执行与有效性

| 配置 | 请求 | 有效候选 | 截断 | prompt tokens | completion tokens | 未缓存列表成本 (CNY) |
|---|---:|---:|---:|---:|---:|---:|
| Qwen Off | 600 | 572 | 1 | 5 258 734 | 784 913 | 6.33 |
| Qwen On | 600 | 528 | 0 | 5 280 334 | 38 624 227 | 108.51 |
| DeepSeek Off | 840（含 240 初始化） | 584 / 600 候选 | — | 未拆分 | 未拆分 | 未记录 |
| DeepSeek On | 600 | 595 | — | 未拆分 | 27 697 786（含思考） | 未记录 |

> DeepSeek 两臂未按臂记录 prompt/completion 拆分，只有请求总量：
> Off 840 次请求合计 5 917 619 tokens；On 600 次候选请求合计 32 913 056 tokens，
> 其中输出 27 697 786。因此该两行的分列值留空而非填 0。

- Qwen 两臂 `AUDIT.json` 的 `issues` 均为空；用量零缺失。
- Qwen On 的 `reasoning_characters` 为 128 136 207；Off 为 0，确认思考开关按预期生效。
- Qwen Off 有 1 条截断响应，按协议判为无效并回退父代，未自动重试。
- Qwen On 首轮执行失败（`results/qwen3_8/attempt1_status.json`，`stage=on_all`），随后由监督进程重启；
  5 个流错误任务被归档重跑（`results/qwen3_8/SUPERVISOR_STATUS.json`），最终 `status=complete`。
- 无效候选与设置特有的运行失败按协议**回退父代**（Δ 记 0），这与主实验口径一致；
  其影响见 §4.5。

---

## 4. 结果

### 4.1 主对照：未经筛选的候选

每轮收益增量相对各自父代，先按父代聚合两个候选、再按种群聚合，20 个种群等权。

| 模型 | 模式 | raw Score | raw Accurate | raw Mismatched | **τ = A − M** | τ 95% CI | 符号交换 p |
|---|---|---:|---:|---:|---:|---|---:|
| DeepSeek | Off | +0.00381 | +0.00232 | +0.00263 | **−0.000308** | [−0.01001, +0.00950] | 0.9516 |
| DeepSeek | On | +0.05272 | +0.07198 | +0.06585 | **+0.006127** | [−0.01311, +0.02463] | 0.5373 |
| Qwen | Off | +0.01617 | +0.01959 | +0.02131 | **−0.001714** | [−0.01411, +0.00923] | 0.7904 |
| Qwen | On | +0.07129 | +0.11655 | +0.11044 | **+0.006106** | [−0.01621, +0.02794] | 0.5981 |

**4/4 个配置的 τ 区间都覆盖零**（DeepSeek Off 的主检验未校正 p = 0.952；
其余三个配置 Holm 校正后 p = 1.000）。

按审稿意见第 9 条的要求，这里给出实际意义而不是只报显著性。与数据兼容的 \|τ\| 上限为：

| 配置 | \|τ\| 的置信上限 | S3 选择增益 | 上限占选择增益 |
|---|---:|---:|---:|
| DeepSeek Off | 0.0100 | +0.03203 | 31% |
| DeepSeek On | 0.0246 | +0.07996 | 31% |
| Qwen Off | 0.0141 | +0.04067 | 35% |
| Qwen On | 0.0279 | +0.11792 | 24% |

即：**匹配效应即使存在，也不超过每轮约 0.010–0.028**，在任何配置中都小于外部选择增益的
三分之一。这比"未达显著"更有信息量——它排除的不是"零效应"，而是"与选择通道同量级的匹配效应"。

### 4.2 选择后输出（S3 验证选择）

S3 在独立验证面板 V 上评价候选，采用规则为"候选的选择分严格超过父代才采用，否则保留父代"。

| 模型 | 模式 | S3 Score | S3 Accurate | S3 Mismatched | τ_S3 = A − M | τ_S3 95% CI |
|---|---|---:|---:|---:|---:|---|
| DeepSeek | Off | +0.03203 | +0.02715 | +0.02354 | +0.003606 | [−0.00361, +0.01118] |
| DeepSeek | On | +0.07996 | +0.10070 | +0.10701 | −0.006311 | [−0.03286, +0.02059] |
| Qwen | Off | +0.04067 | +0.03484 | +0.03939 | −0.004552 | [−0.01789, +0.00855] |
| Qwen | On | +0.11792 | +0.16352 | +0.15107 | +0.012456 | [−0.02124, +0.04495] |

τ_S3 的四个区间同样全部覆盖零。
注意 S3 输出收益是**门控与是否采用之后的非线性量**，因此 τ_S3 的正负号不能读作
"准确诊断对选择更有用"；它只说明在四条流水线的输出上都没有可检出的匹配优势。

> 说明：τ_S3 不是 v2 预注册的次比较端点，本表由 `results/model_comparison_20260928/cross_model_summary.py`
> 从 `results/*/ANALYSIS.json` 中 `selected.S3.*.metrics.default.seed_values` 用同一套种群聚类自助
> 重新计算，未做多重检验校正。该脚本同时断言 τ 的点估计与符号交换 p 与冻结记录一致。

### 4.3 τ 的符号跟随生成模式，而不是模型

| 模式 | DeepSeek τ | Qwen τ | 差距 |
|---|---:|---:|---:|
| Off | −0.000308 | −0.001714 | −0.001406 |
| **On** | **+0.006127** | **+0.006106** | **−0.000021** |

两条 On 臂的 τ 在数值上几乎相同，而两条 Off 臂同为负。也就是说，
τ 的符号在**模式内**跨模型一致，在**模型内**跨模式反号。
这更像是一个与生成配置（输出预算、采样规则）相关的残余项，
而不是某个模型的性质；它也再次说明 Off/On 的差异不能被归因于思考机制。

另外，`mismatched − score` 的原始差值在 4 个配置中为
−0.00118（DS Off）、+0.01313（DS On）、+0.00514（Qwen Off）、+0.03915（Qwen On），
即**收到错配报告通常不差于只给总分**，且在两个 Qwen 配置与 DeepSeek On 中更好。
这与主实验的读法一致，但也再次提醒：只有与 `accurate` 配对比较才能检验"匹配"的价值。

### 4.4 匹配效应与选择效应的量级对比

| 配置 | \|τ\| | S3 选择增益（Score 臂） | 倍数 |
|---|---:|---:|---:|
| DeepSeek Off | 0.000308 | +0.032029 | **104×** |
| DeepSeek On | 0.006127 | +0.079963 | **13×** |
| Qwen Off | 0.001714 | +0.040669 | **24×** |
| Qwen On | 0.006106 | +0.117922 | **19×** |

在每一个配置中，外部选择带来的收益都是 τ 点估计的 13 倍以上；即使用更保守的口径
（把 §4.1 中与数据兼容的 \|τ\| 上限当作真实匹配效应），选择增益仍是它的 **2.9–4.2 倍**。

这是本文"最终策略变强不能反推生成反馈有效"这一归因论点的**跨模型证据**：
收益的主要来源是候选池 × 选择器，而不是个体匹配的诊断内容。

### 4.5 有效性与回退的敏感性

Qwen 的有效率低于 DeepSeek（Off 572/600，On 528/600），且无效候选按协议回退父代（Δ=0），
因此 Qwen 的原始均值会被系统性拉低。逐臂回退次数：

| 配置 | score | accurate | mismatched | background | cooperation |
|---|---:|---:|---:|---:|---:|
| Qwen Off | 3 | 7 | 9 | 4 | 5 |
| Qwen On | 15 | 7 | 12 | 22 | 16 |
| DeepSeek Off | 3 | 4 | 4 | 1 | 4 |
| DeepSeek On | 1 | 1 | 2 | 1 | 0 |

（单位：120 个候选中的回退数，`fallbacks.default`。）

DeepSeek Off 的 `successful_only_default_gain`（只统计成功执行的候选）与全量均值之差
在 0.0001–0.0006 之间（如 score 臂 0.003809 → 0.003906），说明该口径下的回退**不驱动**结论。
其余三个配置没有保存该字段，因此 Qwen 侧的回退敏感性**未做**同口径核算——
这是本报告的一处已知缺口，见 §6。

关键的量级判断：Qwen On 的 background 臂有 22/120 回退，是全表最高；
即便如此，它的原始均值仍是 +0.06857，与 score 臂同向。
由于 τ 是同一配置内两臂之差，而 accurate 与 mismatched 在 Qwen On 的回退数（7 vs 12）
并不极端，回退不足以解释 τ 的符号。

---

## 5. 对审稿意见第 6 条的回应

审稿意见要求：**最好增加第二个模型；至少弱化所有"LLM 普遍行为"表述。**

| 要求 | 本复现的状态 |
|---|---|
| 增加第二个模型 | ✅ 已完成。Qwen3.8-Flash 在同一批 20 种群 / 60 父代 / 600 提示词上跑完两套配置 |
| 主结论是否跨模型成立 | ✅ 4/4 配置 τ 区间跨零；选择增益 4/4 区间不含零 |
| 能否宣称"LLM 普遍" | ❌ **仍然不能**。只有两个模型，且两条 On 的输出预算不同 |
| 能否把 On/OFF 当作思考机制的消融 | ❌ **不能**。Off/On 同时改变思考、输出上限与有效采样规则 |
| 是否有封存的权重快照 | ❌ 无。服务端别名无法保证权重固定 |

**建议的正文表述**（保守版）：

> 在第二个模型（Qwen3.8-Flash）上复现同一配对设计后，准确匹配诊断相对错配诊断的
> 原始候选增益仍未显示可检出的优势（4/4 配置的 95% 区间覆盖零，与数据兼容的 \|τ\| 上限为
> 每轮 0.010–0.028）；而外部选择在这四个配置中一致地带来 0.032–0.118 每轮的增益，
> 至少是上界口径下匹配效应的 2.9–4.2 倍。
> 两个模型的两套生成配置共享父代与提示词，但输出预算与采集时间不同，
> 因此这些结果支持"反馈匹配的价值在该任务上很小"这一**任务层面**的结论，
> 不支持关于语言模型的一般性主张。

---

## 6. 局限

| 局限 | 具体说明 |
|---|---|
| **只有两个模型** | DeepSeek-V4.1-Flash 与 Qwen3.8-Flash；不足以支持"LLM 普遍"表述 |
| **输出预算不等** | Qwen On 上限 131 072 vs DeepSeek On 384 000；两条 On 臂不可直接比大小 |
| **模式混淆** | 每个模型内 Off/On 同时改变思考、输出上限与有效采样规则 |
| **非同期采集** | 两次采集相隔数日，服务端权重无快照保证 |
| **H 已被使用** | 这是后续模型比较，不是新的盲测面板 |
| **共享父代** | 两模型复用同一批 20 种群，**不能**合并为 40 个独立重复 |
| **τ_S3 非预注册** | §4.2 由本报告计算，未做多重检验校正 |
| **回退敏感性不全** | 仅 DeepSeek Off 保存了 `successful_only_default_gain` |
| **区间跨零 ≠ 等效** | 未拒绝零假设不等于证明两种反馈等效；本设计只能排除 \|τ\| ≳ 0.028 的效应 |

---

## 7. 复现

Qwen 的每个模式是一条独立的五阶段流水线。
`--output` 必须恰好是 `results/qwen3_8/off` 或 `results/qwen3_8/on`（由 `mode_for` 强制校验）：

```powershell
$env:PYTHONPATH = (Get-Location).Path

foreach ($mode in 'off', 'on') {
  # 1. prepare：冻结请求清单（复用 v2 的种群/父代/提示词，零初始化调用）
  python -m experiments.direct_reciprocity.qwen38_control prepare --output results/qwen3_8/$mode
  # 2. first：单请求预检，写 FIRST_REQUEST_CHECK.json 作为后续放行凭据
  python -m experiments.direct_reciprocity.qwen38_control first   --output results/qwen3_8/$mode
  # 3. all：生成 600 个候选
  python -m experiments.direct_reciprocity.qwen38_control all     --output results/qwen3_8/$mode --api-workers 50 --workers 24
  # 4. select：S1/S2/S3 选择并封存
  python -m experiments.direct_reciprocity.qwen38_control select  --output results/qwen3_8/$mode
  # 5. holdout：释放 H 并评价
  python -m experiments.direct_reciprocity.qwen38_control holdout --output results/qwen3_8/$mode
}

# 汇总：写出 results/qwen3_8/ANALYSIS.json 与 REPORT.md（须在工作区根目录运行）
python results/qwen3_8/analyze.py

# 本报告的全部表格（只读冻结的 ANALYSIS.json；内部断言 τ 与冻结记录一致）
python results/model_comparison_20260928/cross_model_summary.py

# 跨模型图：只读冻结的 ANALYSIS.json，只写自己的结果目录
python results/model_comparison_20260928/plot_cross_model_mainline.py
```

`prepare` 阶段只读本地冻结数据、不发起 API 调用，因此无需凭据即可跑；
`first` / `all` / `select` / `holdout` 需要 `.env` 中的 Qwen 配置。
模型名在调用中被显式指定为 `qwen3.8-flash`，覆盖 `.env` 中的别名而不修改该文件。
批量生成期间 `RUNNER.lock` 阻止同一批次的并发写入，进程退出时自动释放。

---

## 8. 文件索引

| 内容 | 路径 |
|---|---|
| 本报告 | `docs/direct_reciprocity/CROSS_MODEL_REPLICATION.md` |
| 本报告表格的复算脚本 | `results/model_comparison_20260928/cross_model_summary.py` |
| Qwen 协议（冻结） | `results/qwen3_8/PROTOCOL.md` |
| Qwen 顶层汇总 | `results/qwen3_8/ANALYSIS.json`、`results/qwen3_8/REPORT.md` |
| Qwen 分臂数据 | `results/qwen3_8/{off,on}/{ANALYSIS,AUDIT,manifest,SELECTIONS_SEALED}.json` |
| Qwen 推理流 | `results/qwen3_8/{off,on}/streams/*.jsonl` |
| 跨模型图（论文用） | `results/model_comparison_20260928/cross_model_mainline.{pdf,png,svg}` |
| 跨模型图数据 | `results/model_comparison_20260928/cross_model_mainline_data.json` |
| 图注（中文） | `results/model_comparison_20260928/caption_zh.md` |
| Qwen 独立图 | `results/qwen3_8/figures/qwen_fig2_complete.{pdf,png,svg}` |
| DeepSeek Off 数据 | `results/feedback_specificity_v2/` |
| DeepSeek On 数据 | `results/feedback_specificity_thinking_384k_20260923/` |

**交叉引用**：错配强度量化见 [`MISMATCH_DISTANCE_ANALYSIS.md`](MISMATCH_DISTANCE_ANALYSIS.md)；
模型是否"察觉到"错配见 [`JEV_DETECTION_VALIDATION.md`](JEV_DETECTION_VALIDATION.md)；
known-defect 阳性对照见 [`POSITIVE_CONTROL_REPORT.md`](POSITIVE_CONTROL_REPORT.md)。

> **注意（与审稿意见第 13 条相关）**：`.gitignore` 把整个 `results/` 目录标为 local-only
> （第 87–88 行），因此本报告中指向 `results/` 的脚本、`ANALYSIS.json`、推理流与图形
> **当前不在版本控制内**。投稿前若要把这些作为可复现代码/数据发布，需要显式
> `git add -f` 或把这部分产物归档到独立仓库并分配 DOI。

冻结的 v2 管线未被改动：本复现只复用只读的种群、提示词与评价代码，
`specificity*.py` 与 `core.py` 的 `implementation_hash` 与 Qwen 清单一致
（`7f99254d4c27fb4c37044e7e44cd051a38fce93498be65a8e99b45fbed1f15d5`）。
