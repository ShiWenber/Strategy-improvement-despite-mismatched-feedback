# Direct reciprocity：论文实验与图表复现

本项目对应论文 **Strategy improvement despite mismatched feedback: evolving direct reciprocity with large language models**。它在重复囚徒困境中固定父代，分别测量报告匹配、候选生成和外部选择的作用。本 README 汇总正文、补充材料及原实验记录中的数据来源、实现细节、脚本依赖和运行方法。图号以当前英文稿实际编译引用为准：正文 Figure 1–3，补充 Figure S1–S6；中英文稿共用英文图件。旧文件名 `figure3.pdf` 实际对应补充 Figure S1，不能据文件名判断正文编号。

**直接复现：** 在项目根目录运行 `python tools/reproduce.py`。原始数据在 [results](results/)，复现中间结果另存 `_reproduct` 文件；[reproduct](reproduct/) 仅保存新数据和图像。默认流程离线，不需要 API key，不重新生成候选。正文数值图输出为 `fig2.png`、`fig3.png`，补充图为 `figS1.png`–`figS6.png`；数值图同时输出 PDF/SVG。Figure 1 是方法示意图，直接使用 `paper_zh_direct/figures/figure1.{png,pdf}` 和 `figure1_editable.pptx`，无需复制到 `reproduct`。

## 1. 安装与一键运行

```bash
git clone https://github.com/ShiWenber/Strategy-improvement-despite-mismatched-feedback.git
cd Strategy-improvement-despite-mismatched-feedback
```

完整项目要求 Python ≥3.12；本次验证环境为 Python 3.12.7。完整依赖与解析结果分别见 [pyproject.toml](pyproject.toml) 和 [uv.lock](uv.lock)。安装依赖后即可复现：

```powershell
# Windows PowerShell，从项目根目录运行
python -m venv .venv-reproduct
.venv-reproduct/Scripts/python.exe -m pip install -r requirements-reproduction.txt
.venv-reproduct/Scripts/python.exe tools/reproduce.py
```

```bash
# Linux / macOS，从项目根目录运行
python3 -m venv .venv-reproduct
.venv-reproduct/bin/python -m pip install -r requirements-reproduction.txt
.venv-reproduct/bin/python tools/reproduce.py
```

已有项目环境可直接运行：

```powershell
.venv/Scripts/python.exe tools/reproduce.py
```

分阶段运行适合检查中间结果：

```powershell
python tools/reproduce.py --stage prepare     # 校验全部论文原始输入
python tools/reproduce.py --stage statistics  # 从记录重算统计及敏感性分析
python tools/reproduce.py --stage figures     # 重绘正文及补充图、导出表格
python tools/reproduce.py --stage replay      # 真实执行样本策略与 H 对手对局
python tools/reproduce.py --stage export      # 导出候选、种群和条件统计 CSV
```

每步失败会停止，详情见 `results/reproduction/*_reproduct.log`。每个阶段都先校验原始输入。复现器使用项目本身的源码，不解包、不创建工作副本，输出与论文原文件分开。

| 依赖 | 用途 | 是否为离线复现必需 |
|---|---|---|
| NumPy、SciPy | 种群聚合、bootstrap、统计与距离计算 | 是 |
| Matplotlib | 图像、PDF/SVG 导出和字号/边界检查 | 是 |
| pandas | 表格与历史框架导入依赖 | 是 |
| OpenAI SDK、python-dotenv | 历史运行模块的导入依赖；在线生成时用于调用和配置 | 是，但离线不调用 API |
| tiktoken、`cl100k_base` | 提示附加块长度匹配 | 新生成/重新构建提示需要；缓存重绘无需重新分词 |
| TypeSafe / Jev | 可见推理的原始标签判读 | 读取冻结判读缓存不需要；重新判读需要服务与依赖 |
| TeX 与稿件字体 | 编译原多文件论文 | 数据和图像复现不需要 |

最小环境的版本在 [requirements-reproduction.txt](requirements-reproduction.txt) 固定。本机运行版本和各步骤耗时由 `results/reproduction/verification_reproduct.json` 记录。本项目已去掉与当前论文无关的 GPU 嵌入和旧框架依赖。

## 2. 单一项目结构与原始记录

本项目只关联 [Strategy-improvement-despite-mismatched-feedback](https://github.com/ShiWenber/Strategy-improvement-despite-mismatched-feedback) 仓库。源码直接位于 `experiments/`、`tools/` 和 `paper_zh_direct/tools/`；论文原始记录直接位于根目录的 `results/`，保留原来的目录和文件名。无需另行下载数据压缩包，也无需复制源码或建立第二个工作树。

| 位置 | 内容 |
|---|---|
| `experiments/direct_reciprocity/` | 当前研究的模拟器、反馈、生成、选择、统计代码 |
| `tools/reproduce.py` | 根目录的一键复现入口 |
| `tools/reproduce_worker.py` | 单步离线运行，写入独立复现文件，禁止网络调用 |
| `results/<原实验名>/` | 原始请求、代码、评分、封存选择、H/F′测量与原分析文件 |
| `results/figure_rendering/` | S2 原始直方图/密度显示坐标及绘图输入，原文件名不变 |
| `results/reproduction/INPUT_MANIFEST.json` | 每个论文输入的相对路径、字节数和 SHA-256 |
| `results/reproduction/` | 本次检查报告、日志与精简表格；文件名带 `_reproduct` |
| `paper_interface_focus/`、`paper_zh_direct/` | 英文正文/补充材料和中文稿；共用中文稿目录中的一套原图 |
| `reproduct/` | **只有一层**新算出的 CSV/JSON 数据和 `fig2`、`fig3`、`figS1`–`figS6` 图像；没有源码、原始数据副本或子目录 |

旧框架和额外的源码快照不参与复现，也不提供兼容层。历史 manifest 中的实现哈希保留为原实验记录字段，不要求精简后的代码继续使用旧哈希。分析会重新核对提示、响应、候选代码、选择封存和收益算术；一键入口还核对全部原始输入哈希。

新增中间结果按 `原文件名去掉扩展名 + _reproduct + 扩展名` 保存，例如 `results/feedback_specificity_v2/ANALYSIS_reproduct.json`、`role_analysis/ANALYSIS_reproduct.json` 和 `docs/direct_reciprocity/mismatch_distance/mismatch_distance_thinking_off_reproduct.json`。原 `ANALYSIS.json` 及封存记录不被覆盖。后续绘图优先读取本次重算文件；尚未重算的部分读取原文件，因此单独重绘图像不代表统计复核已完成。

## 3. 每个论文实验的数据归属

以下路径均相对项目根目录。表中列出分析脚本的原入口；安全生成 `_reproduct` 中间结果时使用 `python tools/reproduce.py --stage statistics`。直接调用原分析脚本会写入它的默认结果路径。

| 实验/分析 | 冻结数据 | 复现入口 | 复现产物 |
|---|---|---|---|
| DeepSeek OFF 主实验 | `results/feedback_specificity_v2/` | `python -m experiments.direct_reciprocity.specificity_analysis` | `ANALYSIS.json`、主比较/6项次比较、逐条件 Raw 与 S1/S2/S3 |
| 同池采用政策，OFF 事后分析 | 上述 `holdout/`、`selection_scores/`、`SELECTIONS_SEALED.json` | `python -m experiments.direct_reciprocity.role_analysis` | `role_analysis/ANALYSIS.json`，R/G/U/B 的精确期望和差分 |
| DeepSeek ON 后续配置 | `results/feedback_specificity_thinking_384k_20260923/` 与 OFF 父代 | `python thinking_control_analysis.py` | 新候选统计、历史配对配置比较、两项 focus 检验 |
| Qwen OFF/ON 后续模型检查 | `results/qwen3_8/{off,on}/` | `python results/qwen3_8/analyze.py` | 每配置 `ANALYSIS.json` 与 Qwen 汇总 |
| 跨模型核对 | 上述四配置及 `model_comparison_20260928/cross_model_mainline_data.json` | `python results/model_comparison_20260928/cross_model_summary.py` | 逐种群匹配差及精确符号交换核对日志 |
| 候选分布及采用去向 | 两份 DeepSeek 原始候选、H 与 S3 封存选择 | `python tools/analyze_population.py` | `population_summary_reproduct.json`，1200候选增益、质量计数、种群向量及采用计数 |
| H 分对手家族收益，DeepSeek OFF/ON | 两配置 `holdout/` 与封存选择 | `python paper_zh_direct/tools/analyze_opponent_profiles.py` | `figure4_opponent_profiles_20260926/ANALYSIS.json` |
| 独立行为 F′、真实修改实例 | 两配置行为测量、父代/候选代码和 S3 决定 | `python paper_zh_direct/tools/plot_behavior_evidence.py` | `reciprocity_population_visuals_20260924/behavior/ANALYSIS.json`、示例 |
| 报告错配距离与近供体剔除 | 240成员 F 报告、60父代/报告来源、Raw/S3 记录 | `python -m experiments.direct_reciprocity.mismatch_distance --root .` | `docs/direct_reciprocity/mismatch_distance/*.json` |
| 可见推理归属/处理标签，仅 DeepSeek ON | `results/mismatch_detection_jev/{summaries,judgments}/`、`summary.json`、`validation.json` | 默认导出冻结判读；见第8节 | `reproduct/jev_recount.json`，原逐条标签在 results 中保留一份 |
| 五种群探索性前导实验 | `results/feedback_attribution_v1/` | `python -m experiments.direct_reciprocity.feedback_analysis` | `results/feedback_attribution_v1/ANALYSIS_reproduct.json` |

原提示矩阵、多代框架试验、阳性对照和群体福利扩展是其他研究记录，未作为当前正文三图及上述补充统计的额外独立样本。相关代码入口仍在 `experiments/direct_reciprocity/`，研究协议见 `docs/direct_reciprocity/`；本项目的“所有论文实验”范围以上表与当前实际引用图表为准。

### 从原记录到结果的依赖顺序

1. `requests_initial/` → `initial/` → `populations/`：240次初始化响应，验证代码并测量训练收益及 F 报告。
2. `contexts/`：按训练排名选择每种群第1、3、6位父代，保存全部种群代码、真实成绩、五条件提示和报告来源。
3. `requests_candidates/` → `candidates/`：每父代、每条件两次独立请求；最终程序和无效状态均保留。
4. `selection_scores/` → `SELECTIONS_SEALED.json`：分别计算 S1/S2/S3 并固定900个决定。
5. `H_RELEASED.json` → `holdout/`：选择固定后才做 H 收益和独立 F′ 行为测量；不让 H 参与选择。
6. `ANALYSIS.json` / `role_analysis/ANALYSIS.json` → 论文表格和绘图缓存 → `fig2/fig3/figS*`。

OFF 的初始化和父代被后续三配置复用。每配置有600次候选生成、300个双候选池、900项选择决定；四配置合计2400个候选，加共享240次初始化是2640个最终生成响应。它们共享20个种群，不是80个独立种群。请求失败历史与最终候选数不是同一个计数。

## 4. 正文和补充图逐张复现

执行 `python tools/reproduce.py --stage figures` 即可重绘下表。绘图只使用冻结均值、区间、种群向量或原显示坐标；统计重算另在 `--stage statistics` 完成并核对。

| 论文图号 → 输出 | 原资产名 | 数据/面板归属 | 绘图入口 |
|---|---|---|---|
| Figure 1 → 原 `figure1.png/pdf`、`figure1_editable.pptx` | `figure1` | 方法示意，不含需要统计重算的实验结果 | 直接引用唯一的原 PDF/PNG/PPTX；不重复存放 |
| Figure 2 → `fig2.png/pdf/svg` | `if_results_matching` | a,b：`model_comparison_20260928/cross_model_mainline_data.json.statistics`；c：四配置五条件等权的20种群 Raw/S3向量 | `plot_results_three_figures.py` |
| Figure 3 → `fig3.png/pdf/svg` | `if_payoff_behavior` | a,b：`figure4_opponent_profiles_20260926/ANALYSIS.json`，Accurate/Mismatched 的 H家族收益；c,d：行为 `ANALYSIS.json`，`controlled/pooled/{defection_exposure,recovery_rounds}` | 同上 |
| Figure S1 → `figS1.*` | 旧 `figure3` | DeepSeek OFF/ON、五条件、S1/S2/S3 全结果 | `plot_camera_ready.py --figures 3` |
| Figure S2 → `figS2.*` | `if_generation_selection` | `population_summary.json` 中600候选分布、20种群对、300池去向；直方图/KDE复用 `frozen_generation_display.json` 的原显示坐标 | `build_interface_figures.py` |
| Figure S3 → `figS3.*` | 旧 `figure5` | OFF `role_analysis/ANALYSIS.json.summaries`，同池政策及分解 | `plot_camera_ready.py --figures 5` |
| Figure S4 → `figS4.*` | `if_opponent_profiles` | 原始候选/S3、两配置、两报告条件、四H家族 | `plot_opponent_profiles.py` |
| Figure S5 → `figS5.*` | 旧 `figure4` | OFF `ANALYSIS.json` 中独立行为变化，给定合作历史/空历史 | `plot_camera_ready.py --figures 4` |
| Figure S6 → `figS6.*` | `if_mismatch_distance` | 两份冻结距离 JSON；60对距离相同，2640个同群异体有序对作参照 | `plot_mismatch_distance.py` |

以上绘图脚本位于 `paper_zh_direct/tools/`，样式依赖 `results_plot_style.py`，补充图输出审计依赖 `results_plot_audit.py`。这些脚本随项目提交，只有一份源码。Figure 2/3 的读取键、种群顺序、输入哈希、最小字号和画布边界检查保存在 `results/reproduction/*_reproduct.json`。

主图3上排只含Accurate/Mismatched，下排等权平均五条件；下排只用DeepSeek，不能声称已有Qwen行为复现。H 收益和 F′ 行为是不同测量。共享父代基线只绘一次，连线表示同父代比较，不是世代轨迹。Figure S2 的零增量回退属于分布的一部分；显示密度平滑该零点，不删除失败候选。

## 5. 每张表和正文数值如何得到

| 论文位置 | 来源和计算 | 文件/导出入口 |
|---|---|---|
| 正文 Table I：五信息条件 | Score无附加块；Accurate自身报告；Mismatched同群他人报告；Background/Cooperation长度对照 | `specificity_assets.py` 与 `contexts/*.json`，设计定义，不是估计值 |
| 正文 Table II：三选择器 | S1训练5重复；S2训练20重复；S3验证20重复 | `specificity.py` 和 `selection_scores/*.json` |
| 补充 Table S1：F′ 探针 | 两起始历史、五探针、40测量轮、20重复 | `specificity_assets.py:probe_specs`，参数定义 |
| 补充 Table S2：OFF主/次比较 p | 主比较独立；6次比较一个Holm族 | `ANALYSIS.json.primary/secondary` → `tools/export_paper_tables.py` → `tableS2_primary_reproduct.tex/csv` |
| 补充 Table S3：噪声/长对局 | OFF Accurate/Mismatched的Raw，逐设置重新以该父代为基线 | `ANALYSIS.json.raw` → 同脚本 → `tableS3_sensitivity_reproduct.tex/csv` |
| 补充 Table S4：ON Accurate−Score | Raw和S3两个事后比较、两项Holm | `interface_focus_revision_20260925/ANALYSIS.json.thinking_on_accurate_minus_score_posthoc` → `tools/export_paper_tables.py`，再用种群向量重算核对 |
| 补充 Table S5：S3随机采用差 | 默认/噪声/长对局的B−R | `role_analysis/ANALYSIS.json.summaries['pooled/S3/<setting>']` → `tableS5_selection_reproduct.tex/csv` |
| 补充 Table S6：剔除近三分之一 | cutoff=5.643，保留40父代，按种群配对汇总 | `mismatch_distance_thinking_{off,on}.json` 中敏感性项；正文表为已冻结值 |
| 四模型配置的有效数 | 最终响应/候选状态 | OFF/ON分别为DeepSeek 584/595、Qwen 572/528，600为各配置分母 |
| 正文31/120、30/31、1/31 | 逐个Jev origin/handling标签与阈值 | `mismatch_detection_jev/judgments/`、`summary.json`，见第8节 |
| 正文60/60数值不同及平均距离 | 240成员36特征标准化，60父代/报告来源对 | 两份 `mismatch_distance*.json`，不从图像估计 |
| 真实策略修改实例 | 封存S3选择、H收益、F′指标和源代码；在事后类别内取最近类别中位数的候选 | 行为 `ANALYSIS.json.examples`，ID见下文 |

当前稿件仅需 S1–S6 六张补充数值表。`tools/export_paper_tables.py` 将 CSV/TeX 保存到 `results/reproduction/tables/`，文件带 `_reproduct` 后缀；S4还独立重算两项比较的区间与 Holm p 值。原稿中已不用的完整表格导出器已删除，不重复导出已归档表格。

当前稿件中三个真实修改示例为：OFF Cooperation `s217-rank3-d0-pos2`，ON Accurate `s210-rank3-d1-pos3`，ON Cooperation `s213-rank6-d0-pos1`。原代码位于对应 `contexts/<parent>.json` 和 `candidates/<id>.json`；H、F′、S3分数及实际赢家保存在同ID测量/评分记录。示例是事后说明，不代表独立验证或归属识别的因果证据。

主要导出数据：`candidate_gains.csv` 含2400候选×3种H设置；`population_gains.csv` 含四配置×五条件×Raw/S1/S2/S3×20种群；`condition_statistics.csv` 含80个默认设置条件均值和区间。这些 CSV 位于 `reproduct/`；完整重算分析保存在各原结果目录下的 `_reproduct.json`，不再复制一份到 `reproduct`。

## 6. 正文实现细节集中说明

### 程序接口、随机数和失败规则

策略实现 `strategy(history, rng)`，返回`C`或`D`。`history`是不可变行动对序列，自身行动在前；只提供本场历史和受控随机数。源码≤16000字符，每行动≤20000 line/opcode跟踪事件。每场重新实例化程序与历史，策略随机流和行动噪声流独立，并由比赛种子派生。

初始化验证包括编译和对13训练参考策略的100轮对局，验证种子12345。初始化程序无效或F探针失败时部署ALLD并保留失败记录；240初始化中4例回退，均未入选父代。候选无效不补抽。父代评价失败停止分析；候选选择评分失败仅令其在相应选择器下不合格；某H设置运行失败仅在该设置回退父代，不改变封存选择。Raw均值包含无效/失败候选的零增量，不能仅平均有效程序。

### 游戏、训练、验证和测试

收益 `(R,S,T,P)=(3,0,5,1)`。默认100轮、无行动噪声。初始化训练分为对其他11个种群成员的平均累计收益×0.6，加对13个固定训练参考的平均累计收益×0.4，每对手5重复，排除自对局。参考为ALLC、ALLD、TFT、Grim、Pavlov、Random、Alternator、Bayesian、GTFT、Gradual、Prober、SuspiciousTFT、Extort2；以`baselines.py`实际源码为准。

S1/S2使用命名空间19001的新训练流；父代与候选共享对应流。S1每训练对手5重复，共120场，直接嵌套于S2的20重复、480场。S3对24个V对手各20重复，共480场，对手等权。S2与S3对局数相同，但分布和权重不同。

V/H各含Recovery、Exploitation、Random、Memory-one四家族，分别每家族6/3成员。具体参数由`experiments/direct_reciprocity/specificity_assets.py:panel`保留；它逐项定义背叛起点/长度/宽恕率、剥削延迟/周期、随机合作概率和四状态memory-one概率。H每对手20重复，默认每策略240场，收益按每轮计。敏感性设置为100轮、独立行动翻转概率0.01，以及200轮、无噪声。历史记录实际执行动作。

### 报告F与独立行为F′

F先给10轮CC历史（不计入测量），随后24轮、10重复、5种探针。报告包含前4轮/后续/末5轮合作、末5轮相互与单方面合作、24轮收益；前三恢复探针还记录从背叛结束到连续5轮CC的时间和未恢复率。未恢复按剩余观察长度封顶；持续和周期背叛不设恢复时间字段。报告均值舍入4位小数，共36数值特征。

F′使用7轮CC给定历史或空历史，再观察40轮、20重复。前三探针等权平均恢复；持续背叛末5轮单方面合作衡量暴露。恢复最短为5轮，未恢复仍封顶并保留失败标记。探针参数为`two_D_TFT`起点3/背叛2轮、`five_D_GTFT`起点9/5轮/宽恕0.15、`three_D_ALLC`起点6/3轮、`sustained_D`起点5/35轮、`periodic_D`起点4/每7轮前2轮背叛。F′不生成提示报告、不参与选择，也不计入H收益。

### 条件输入、长度、顺序与选择平局

种群种子200–219，每种群12成员，以真实训练排名固定1/3/6名父代。五条件共享父代、全部种群代码、游戏规则和真实训练成绩（6位小数），只改变附加文本。报告来源按同群12成员无固定点置换分配，不限于三个父代，不按行为距离挑选。

每父代×条件两次调用的用户消息和参数逐字相同，不提供模型生成seed；draw编号只是记录两次随机采样。条件在种群内随机排序，父代/draw的五条件构成批次，批次再随机排列。每配置600候选、900选择决定先固定，随后开放H。候选需有效且选择分严格高于父代才采用；同分保留父代，候选间同分取第一次draw。

长度仅匹配附加块，使用`cl100k_base`代理分词，非Score块需在Accurate长度±5%以内，Score不填充。60个上下文Accurate/Mismatched均504代理tokens，Background502，Cooperation494；120个父代/draw匹配对的OFF Accurate/Mismatched服务商输入token均相同，两条件分别共1,052,774输入tokens。代理长度不等于服务商计费或计算量。

### 统计单位、政策期望和显示口径

Raw先平均两个draw，再平均种群内三个父代，最后20种群等权。选择输出每池一个策略或父代。效应`Δ_H=J_H(child)−J_H(parent)`单位为每轮收益。五条件汇总仍在每条件自己的池内决策，再在种群内等权平均；不跨条件合并选优。

两侧配对检验枚举`2^20`种群符号交换，依赖配对差的符号可交换假设；对父代零基线的检验还需对称性假设。95%区间使用20000次种群bootstrap，未做区间多重校正。OFF主比较Accurate−Mismatched独立，6次比较应用Holm；ON及Qwen保持各自原有后续检验族。区间跨零不证明等效。配置同时改变思考与输出上限，且服务端别名不能固定权重，不能将差异单独归因于思考开关。

R（旧表有时写N）从两个候选均匀采用；G先均匀取一个，仅合格时采用；U从合格池均匀采用；B取合格池选择分最高者，空池保留父代。直接平均两种draw计算随机政策精确期望，不额外抽样。`B−R=(G−R)+(U−G)+(B−U)`是指定政策路径上的恒等分解，不能解释为一般因果贡献。R期望等于Raw，B输出等于对应S3时的S3，不增加独立样本。

## 7. 在线重新生成：独立于原结果的重复实验

默认离线流程足以复现已有统计和图表。重新调用模型属于新的随机重复，无法保证逐字输出或原论文均值；不应覆盖原实验候选与封存记录。以下命令仅说明完整新实验如何运行，默认复现器不会执行。

使用本项目现有源码，选择新的输出目录并准备相应协议文件后，用`.env`或环境变量设置`DEEPSEEK_API_KEY`、`DEEPSEEK_API_BASE`；Qwen使用`QWEN_API_KEY`、`QWEN_API_BASE`。配置模块为`experiments/config/load_env.py`。当前`.env.example`的模型默认值不应替代论文manifest里的请求参数。

| 配置 | 论文展示名 / 记录API model | temperature | thinking | 输出上限 |
|---|---|---:|---|---:|
| 初始化 / DeepSeek OFF | deepseek-v4.1-flash / `deepseek-flash` | 1 | disabled | 6000 |
| DeepSeek ON | deepseek-v4.1-flash / `deepseek-flash` | 1 | enabled，reasoning_effort=high | 384000 |
| Qwen OFF | qwen3.8-flash / `qwen3.8-flash` | 1 | enable_thinking=false | 6000 |
| Qwen ON | qwen3.8-flash / `qwen3.8-flash` | 1 | enable_thinking=true，high | 131072 |

原API标识不保证服务商当前仍提供同一版本。ON上限包含可见思考及程序输出，384K是上限，不是实际请求用量；只执行最终程序。

```powershell
# 使用当前项目源码和新的输出目录；费用取决于服务商
python -m experiments.direct_reciprocity.specificity pilot --output results/new_off_reproduct --workers 4 --env-file .env
python -m experiments.direct_reciprocity.specificity freeze --output results/new_off_reproduct --env-file .env
python -m experiments.direct_reciprocity.specificity all --output results/new_off_reproduct --workers 4 --api-workers 2 --env-file .env

# OFF完整后，复用其新父代和提示，开启ON
python -m experiments.direct_reciprocity.thinking_control prepare --source results/new_off_reproduct --output results/new_on_reproduct --env-file .env
python -m experiments.direct_reciprocity.thinking_control first --source results/new_off_reproduct --output results/new_on_reproduct --env-file .env
python -m experiments.direct_reciprocity.thinking_control all --source results/new_off_reproduct --output results/new_on_reproduct --workers 4 --api-workers 2 --env-file .env

# Qwen需要results/qwen3_8/PROTOCOL.md；依次运行off/on
python -m experiments.direct_reciprocity.qwen38_control prepare --source results/new_off_reproduct --output results/qwen_new_reproduct/off --env-file .env
python -m experiments.direct_reciprocity.qwen38_control first --source results/new_off_reproduct --output results/qwen_new_reproduct/off --env-file .env
python -m experiments.direct_reciprocity.qwen38_control all --source results/new_off_reproduct --output results/qwen_new_reproduct/off --workers 4 --api-workers 2 --env-file .env
```

为ON重复Qwen命令并将输出改为`results/qwen_new_reproduct/on`。阶段`first`完成后才允许`all`。API异常会停止；不自动重试可能已计费的请求。上述在线完整新实验未在本次离线整理中执行。完整新实验需要240初始化和每配置600候选请求，不属于“少量API验证”。需要小规模连通性检查时，仅在新目录运行对应`first`，仍不能据此宣称整项实验复现成功。

## 8. JEV标签、距离敏感性和资源计数的边界

原归属判读只分析600条DeepSeek ON轨迹，每条件120条。`tools/judge_mismatch_detection_summary.py`用记录API `deepseek-flash`按40000字符、2000重叠提取逐字证据，再由记录模型`jev-1.13.0`分别判断origin和handling；不传条件标签。严格标准是质疑报告来源概率≥0.40且置信度≥0.60。31/120 Mismatched被标为质疑来源，对照Accurate0/120；31条中30继续使用、1弃用，全部Mismatched handling为119继续/1弃用。

`s219-rank3-d1-pos4`是唯一弃用标签实例；原响应、提取和判读按该ID对应。部分人工核查17个正例及480条件对照给出TP17/FP5/TN475/FN0，其余103条Mismatched不具有独立人工真值。标签比例不等于真实识别率，不能由识别分组收益比较建立因果机制。复现读取逐条冻结判读，不重新上传轨迹。重新提取/判读会调用两种外部服务，另需安装TypeSafe；这些标签本身不能按确定性离线过程重新生成。

距离将36个F特征在240成员上标准化后计算欧氏距离，OFF/ON共用60对。均距7.452，同群异体2640有序对均距7.487；低十分位参照不定义实质相似。剔除最近三分之一保留40父代，OFF/ON的匹配差分别约+0.00450 / +0.01027，区间仍跨零。敏感性按种群聚合，不能把40父代当40独立种群。

原主流水线记录1,102,920场规范收益对局，另有反馈、行为探针、失败验证和重复计算。原六对象样本有一无效候选不重放，其他五对象共1200场。此次默认复现扩展到四配置的相同身份选择规则，实际对局数和误差见`reproduct/replay.json`；它使用当前项目模拟器，不是独立执行器验证，更不是对全部百万场的全量重放。

## 9. 验证证据和范围

已在干净 Git 克隆和新建最小依赖环境中完成全部流程：12,563 个原始输入哈希通过，26 组共 54,800 个数值与论文原结果逐值一致，样本重放 5520 场、最大误差 0；102 项测试通过、1 项跳过。英文正文、英文补充材料和中文稿均重新编译成功。完整证据见 [clean_clone_validation_reproduct.json](results/reproduction/clean_clone_validation_reproduct.json)。

每次运行产生 [verification_reproduct.json](results/reproduction/verification_reproduct.json)，记录输入哈希检查、逐组数值比较、最大误差、执行命令和耗时。对局重放记录在 [replay.json](reproduct/replay.json)，图像来源清单在 [FIGURE_MANIFEST_reproduct.json](results/reproduction/FIGURE_MANIFEST_reproduct.json)。PDF/SVG 的时间或字体元数据可随环境变化，统计值与输入内容是主要核对对象。

默认按身份抽样四配置各一个父代及每条件第一个候选，共24对象；无效候选记录为不执行对局。若要执行所有默认 H 记录：

```powershell
python tools/replay_worker.py --work . --output reproduct/full_replay.json --workers 4 --full
```

全量模式可能需要数小时，仍不包含全部训练、噪声、长对局和 F′ 测量。离线复现不调用 LLM API，不重新生成原候选或 Jev 标签；其范围是从保存的原始响应、评分和测量记录重新算出论文统计、绘制数值图，以及实际执行样本 H 对局。模型重新生成属于另一次随机实验，少量调用不能证明整项论文实验已经重复成功。

相关测试可运行：

```powershell
python -m pytest tests/test_specificity.py tests/test_specificity_pipeline.py tests/test_direct_reciprocity.py tests/test_direct_reciprocity_recovery.py tests/test_direct_reciprocity_control_prepare.py tests/test_direct_reciprocity_control_analysis.py tests/test_feedback_attribution.py tests/test_feedback_selection.py tests/test_feedback_analysis.py tests/test_import_health.py -q
```

## 10. 稿件编译

英文正文为 `paper_interface_focus/main.tex`，补充材料为 `supplement.tex`；中文稿为 `paper_zh_direct/main.tex`。两种语言共用 `paper_zh_direct/figures/` 中的一套原图。可在英文稿目录执行 `tools/build.ps1`，或使用支持 XeLaTeX 字体的 TeX/tectonic 环境。字体设置见各 `.tex` 导言区，中文稿另需中文字体。统计和图像复现不需要 TeX。
