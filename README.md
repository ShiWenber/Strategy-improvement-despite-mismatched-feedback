# Strategy improvement despite mismatched feedback

本项目对应论文 *Strategy improvement despite mismatched feedback: evolving direct reciprocity with large language models*。唯一远程仓库为 [ShiWenber/Strategy-improvement-despite-mismatched-feedback](https://github.com/ShiWenber/Strategy-improvement-despite-mismatched-feedback)。

研究主线是 **Accurate 与 Mismatched**：在相同父代、种群源码、规则和真实训练成绩下，分别提供父代自身或同群另一策略的数值行为报告；区分未经选择的候选质量与外部选择后的输出质量。

## 快速复现

在项目根目录执行，推荐 Python 3.12。以下流程读取归档响应，不调用 LLM API。

```powershell
git clone https://github.com/ShiWenber/Strategy-improvement-despite-mismatched-feedback.git
cd Strategy-improvement-despite-mismatched-feedback
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-reproduction.txt
.venv/Scripts/python tools/reproduce.py
```

Linux/macOS 将解释器路径改为 `.venv/bin/python`。也可使用 `uv sync --frozen` 和 `uv run python tools/reproduce.py`。

完整流程依次核验输入哈希、重算统计、导出数据、生成图表并抽样重放对局。最终查看 `results/reproduction/verification_reproduct.json`：`status` 应为 `passed`，所有统计比较通过，重放误差不超过 `1e-12`。子进程禁止网络连接，防止离线复现意外产生 API 费用。

```powershell
.venv/Scripts/python tools/reproduce.py --stage prepare
.venv/Scripts/python tools/reproduce.py --stage statistics
.venv/Scripts/python tools/reproduce.py --stage figures
.venv/Scripts/python tools/reproduce.py --stage replay
```

分阶段复现时先运行 `statistics` 再运行 `figures`；它们按依赖顺序读取 `_reproduct` 中间结果。

## 数据范围与来源

当前发布只保留两种报告条件的原始记录。它们来自既有实验的主线子集，不是重新采集或重新随机化的两条件实验。保留记录的 ID、原始请求位置、提示词、响应、时间戳、候选源码和选择决定不变；ID 中的 `pos` 仍代表原始提交位置，不要求连续。

每个模型与配置有 20 个共享种群、60 个父代、每父代每条件两次生成，因此保留 **240 个候选、120 个双候选池、360 项 S1/S2/S3 选择决定**。四格共 960 个候选响应，共享 DeepSeek OFF 的 240 个初始化响应；模型或配置数量不增加独立种群数。

| 模型/配置 | 数据目录 | 有效候选 / 240 | 请求设置 |
|---|---|---:|---|
| DeepSeek OFF | `results/feedback_specificity_v2/` | 232 | `deepseek-flash`，temperature=1，thinking disabled，max_tokens=6000 |
| DeepSeek ON | `results/feedback_specificity_thinking_384k_20260923/` | 237 | 同一 API 模型标识，thinking enabled，reasoning_effort=high，max_tokens=384000 |
| Qwen OFF | `results/qwen3_8/off/` | 224 | `qwen3.8-flash`，temperature=1，enable_thinking=false，max_tokens=6000 |
| Qwen ON | `results/qwen3_8/on/` | 221 | 同一模型，enable_thinking=true，reasoning_effort=high，max_tokens=131072 |

论文中的 DeepSeek 名称为 deepseek-v4.1-flash；归档请求使用当时的 API 标识 `deepseek-flash`。服务端别名和后续模型版本不保证权重固定。ON/OFF 同时改变思考与输出预算，且属于不同时间的采集，不能把配置差单独归因于思考开关。Qwen 是复用同一父代与已使用测试面板的后续模型检验。

`manifest.json` 中的 `archive_projection` 记录主线筛选及原始容器的 SHA256；原 implementation/runner 哈希保留为历史来源。条件容器经过筛选，当前容器哈希不冒充最初封存哈希。`PROMPTS_SEALED.json`、`SELECTIONS_SEALED.json` 与 `H_RELEASED.json` 记录当前保留集及原封存文件来源；候选哈希和保留的选择决定未改。原归档不能被新版生成程序续写；新的 API 实验应使用新目录。

### 每种记录表示什么

| 文件/目录 | 内容与用途 |
|---|---|
| `manifest.json` | 种群种子、父代名次、保留条件、候选任务、请求配置与来源 |
| `requests_initial/`、`initial/` | 240 个初始化请求/响应及验证后的策略，仅 OFF 保存 |
| `populations/s200.json` … `s219.json` | 每群 12 个策略、初始训练成绩、反馈测量、无固定点供体置换 |
| `contexts/s200-rank1.json` 等 | 60 个共享父代、供体、两种完整提示与长度计数 |
| `requests_candidates/<id>.json` | 原始 API 参数、响应、用量、有效性；ON 另含可见推理 |
| `candidates/<id>.json` | 原始候选程序及验证结果 |
| `selection_scores/<id>.json` | 父代/候选 S1、S2、S3 的选择成绩，独立于测试结果 |
| `SELECTIONS_SEALED.json` | 360 项封存选择决定，候选或父代保留 |
| `holdout/<id>.json` | 原始收益与独立行为测量；失败回退及相对父代增量 |
| `ANALYSIS.json`、`AUDIT.json` | 当前两条件聚合统计与记录审计；论文数据文件名保持不变 |

ON 与 Qwen 目录已有共享父代的配套记录，它们不是新增初始化或独立父代。每次复现都使用现有记录，不额外复制数据或源码。

## 实验实现与统计口径

核心执行器在 `experiments/direct_reciprocity/core.py`，基准策略在 `baselines.py`，提示构造在 `prompts.py`；两条件流程在 `specificity.py`，供体置换在 `report_assignment.py`，报告与面板定义在 `specificity_assets.py`。

- 策略接口为 `strategy(history, rng)`，每轮返回 C/D。收益 CC/CD/DC/DD=3/0/5/1；默认每局100轮；训练按11个同群对手与13个固定基准分别赋权0.6/0.4。
- 种群种子为200–219，每群12个策略，按训练成绩取第1、3、6名作为父代。报告供体来自同群12个成员的无固定点置换，不根据行为距离挑选。
- 反馈探针 F 先给10轮CC，再测24轮，重复10次。包含短暂背叛后TFT/ALLC、持续背叛和周期背叛，报告36个统计特征。两条件报告均为504个 `cl100k_base` 代理tokens；OFF 的120对请求服务端输入token数逐对相等，两条件各1,052,774。
- S1与S2分别以训练对手重复5/20次评分，S1使用S2前5次。S3用验证面板V：4类×6个对手，各重复20次。只选最高分有效候选且须严格超过父代；与父代同分则保留父代，候选并列优先draw0。
- 收益面板H有4类×3个对手，各重复20次；默认100轮、噪声0.01及200轮长局分别记录。H不进入提示、候选资格或排名。V/H同属恢复互惠、剥削、随机和记忆一阶家族，参数不同。
- 行为探针F′独立于收益和选择：40轮、20次重复，分别从7轮预置CC或空历史开始。持续背叛下末5轮单方面合作衡量暴露；恢复时间为背叛结束后完成连续5轮CC所需轮数，未恢复按剩余窗口封顶，并保留未恢复标记。
- 无效生成不补抽。候选/设置执行失败时部署父代，增量为零；保留失败记录，不仅统计成功候选。OFF有8个无效候选，200轮设置另有1个有效候选执行失败。

Raw先在同父代同条件内平均两次生成；S1/S2/S3每池使用选择或父代保留的一个输出。随后在种群内平均3个父代，对20个独立种群等权汇总。主线的条件平均只覆盖Accurate与Mismatched。

原定确认性主比较是 DeepSeek OFF 的 Raw Accurate−Mismatched：均值 −0.000307986，95%区间[−0.010014106, +0.009500625]，双侧精确符号交换p=0.951618。检验枚举2^20个种群符号交换，依赖配对差的符号可交换性；区间用20,000次种群bootstrap，种子2026091903。区间跨零不证明等效。

ON聚焦比较沿用原两项Holm族；Qwen沿用OFF、ON及ON−OFF的三项Holm族。选择输出、行为、固定池政策、距离关联均属探索性，区间未作多重校正。删除其他条件后，不把剩余探索性检验改称预定确认性检验。

## 各实验如何复现

`tools/reproduce.py` 为统一入口；下表列出它运行的实际计算脚本。常规复现由 `tools/reproduce_worker.py` 将写入路由到同名 `_reproduct` 文件；不建议直接运行表中分析脚本覆盖论文使用的汇总。

| 分析 | 计算脚本 | 原始输入 → 重算中间结果 |
|---|---|---|
| OFF主比较、两条件Raw/S1/S2/S3、敏感性 | `experiments.direct_reciprocity.specificity_analysis` | OFF请求、封存决定、H → `ANALYSIS_reproduct.json`、`AUDIT_reproduct.json` |
| ON统计与历史配对配置差 | `thinking_control_analysis.py` | OFF/ON同父代H → ON的`ANALYSIS_reproduct.json` |
| Qwen四格补充 | `results/qwen3_8/analyze.py` | Qwen请求及H → 各模式与总`ANALYSIS_reproduct.json` |
| 固定池N/G/U/B选择政策 | `experiments.direct_reciprocity.role_analysis` | 同一候选池的选择成绩及H → `role_analysis/ANALYSIS_reproduct.json` |
| 候选分布与选择去向 | `tools/analyze_population.py` | OFF/ON 480个候选H与S3决定 → `population_summary_reproduct.json` |
| 分对手家族收益 | `paper_zh_direct/tools/analyze_opponent_profiles.py` | Accurate/Mismatched每个H对手收益 → `figure4_opponent_profiles_20260926/ANALYSIS_reproduct.json` |
| 独立行为阶段 | `paper_zh_direct/tools/plot_behavior_evidence.py` | 两条件F′及封存S3 → `behavior/ANALYSIS_reproduct.json` |
| 错配距离与敏感性 | `experiments.direct_reciprocity.mismatch_distance` | 240个初始成员F报告、60个父代供体、两条件候选H → 原距离JSON同名加`_reproduct` |
| 跨模型主线汇总 | `results/model_comparison_20260928/cross_model_summary.py` | 四格聚合及配对种群向量 → `cross_model_mainline_data_reproduct.json` |
| 可见推理标签复核 | `tools/reproduce.py`中的缓存重计 | `results/mismatch_detection_jev/judgments/`240个既有标签 → `reproduct/jev_recount.json` |

固定池政策N随机取已有候选，G随机取后执行父代门控，U在合格集合随机取，B在合格集合取最高分；使用两次可能抽取的精确期望，无新增模型调用。逐池重建封存决定，并核验B−N=(G−N)+(U−G)+(B−U)。政策分析bootstrap种子20260920，20,000次。

分对手收益对每家族3个对手等权平均，再对4家族等权平均，可逐种群还原总收益；探索性bootstrap种子2026092604。独立行为分析按同父代和封存选择连接Parent/Raw/S3，不解释为多代演化。

距离用F的36维特征在全部240个初始成员上标准化，计算父代与供体的欧氏距离。60个配对与同群不同成员的2,640个有序配对作参照；删除最近三分之一供体后，剩40父代的Raw匹配区间在OFF/ON仍跨零。距离与收益/行为关联为探索性，不构成中介证据。

可见推理检查仅覆盖DeepSeek ON两条件各120条轨迹。已有分块抽取与Jev标签保存在`summaries/`和`judgments/`。严格口径P(origin question)≥0.40且confidence≥0.60：Mismatched 31/120，Accurate 0/120；31条中30条继续使用、1条弃用。自动标签不等于真实识别率。常规复现仅重计缓存；重新抽取/判读需另行调用API。

## 图与表的对应关系

`reproduct/`只有一层。生成的数值数据和图像存放于此，源码及正常位置的中间结果不复制进去。正文图用`fig2`、`fig3`；补充图用`figS1`–`figS6`，各提供PNG/PDF/SVG。

| 论文编号 | 复现产物 | 脚本与数据 |
|---|---|---|
| 图1 | 原方法示意图`paper_zh_direct/figures/figure1.pdf`及PNG | 非实验数值图，提供现成图源及可编辑PPTX；使用原PDF即可重建论文 |
| 图2 | `reproduct/fig2.*` | `plot_results_three_figures.py`；四格主线匹配与两条件Raw/S3种群配对 |
| 图3 | `reproduct/fig3.*` | 同脚本；家族收益与两条件独立行为 |
| 图S1 | `reproduct/figS1.*` | `plot_camera_ready.py --figures 3`；两条件×三选择器×OFF/ON |
| 图S2 | `reproduct/figS2.*` | `build_interface_figures.py`；每配置240个候选与120池；重新计算直方图与Scott带宽Gaussian KDE |
| 图S3 | `reproduct/figS3.*` | `plot_camera_ready.py --figures 5`；两条件固定池政策及分解 |
| 图S4 | `reproduct/figS4.*` | `plot_opponent_profiles.py`；两条件Raw/S3的四家族收益 |
| 图S5 | `reproduct/figS5.*` | `plot_camera_ready.py --figures 4`；OFF两条件独立行为差 |
| 图S6 | `reproduct/figS6.*` | `plot_mismatch_distance.py`；共享父代供体距离 |
| 表S1 | `tableS1_probe_parameters_reproduct.csv/.tex` | F′固定探针参数 |
| 表S2 | `tableS2_primary_reproduct.csv/.tex` | 原定Raw匹配主比较 |
| 表S3 | `tableS3_sensitivity_reproduct.csv/.tex` | OFF两条件噪声与长局 |
| 表S4 | `tableS4_selection_reproduct.csv/.tex` | 两条件S3−N噪声与长局 |
| 表S5 | `tableS5_distance_reproduct.csv/.tex` | 排除最近供体后的匹配差 |

中文稿的附录连续编号：图S1–S6对应中文图4–9，表S1–S5对应中文表III–VII。

表格由`tools/export_paper_tables.py`生成，输出在`results/reproduction/tables/`。正文表1为两报告条件定义，表2为S1/S2/S3固定评分配置，不依赖API响应。

当前两条件均值为：DeepSeek OFF Raw/S3=0.002475/0.025344，ON=0.068914/0.103851；Qwen OFF=0.020451/0.037118，ON=0.113492/0.157295。S3高于Raw的配对为79/80，其中DeepSeek OFF为19/20，其他三格各20/20。这80个配对共享20个种群，不能当作80个独立样本。

`reproduct/candidate_gains.csv`导出960候选×3测试设置=2,880行；`population_gains.csv`导出4配置×2条件×4阶段×20种群=640行；`condition_statistics.csv`导出32项均值与区间。

## 重放、依赖与重新生成

默认重放每格按字典序取首个父代与两条件各首个候选，共12个对象；与有效性、收益方向无关。有效对象各重放240场默认H对局，检查平均收益、合作率和最差对手收益。无效程序单独记录、不执行。它使用本项目模拟器，并非独立实现，也不声称已重放全部对局。

```powershell
.venv/Scripts/python tools/replay_worker.py --work . --output reproduct/replay.json --full
```

`--full`重放每格所有父代/候选的默认H，可能耗时数小时；不会复查全部噪声、长局与F′记录。程序缺陷或重放差异会明确显示，不静默替换归档数据。

依赖精确版本见`requirements-reproduction.txt`，项目定义与锁见`pyproject.toml`和`uv.lock`：NumPy用于数组/bootstrap，SciPy用于KDE，Matplotlib用于图，pandas用于统计辅助，OpenAI/httpx用于可选API，python-dotenv用于本地密钥，tiktoken用于报告长度。图像不是图像生成模型绘制。

若需要重新采样，复制`.env.example`为`.env`并设置相应API密钥。本次发布验证使用0次API调用。LLM采样未设置生成种子，重新调用不能保证逐字或逐数值复现，且模型别名可能变化。

```powershell
.venv/Scripts/python -m experiments.direct_reciprocity.specificity freeze --output results/new_mainline_reproduct
.venv/Scripts/python -m experiments.direct_reciprocity.specificity all --output results/new_mainline_reproduct --env-file .env
```

全批次重新采样需要240次初始化与240次候选调用，应在理解费用后运行；常规离线复现不需要它。后续ON/Qwen生成器支持`--source`指向新版完成的OFF目录，且必须用新输出目录。Jev可选重标脚本只用于来源/处理方式标签，不生成候选策略。

## 编译论文与验证

英文正文为`paper_interface_focus/main.tex`，英文附录为`supplement.tex`；中文为`paper_zh_direct/main.tex`。它们共享`paper_zh_direct/figures/`的正式图。复现输出保留在`reproduct/`，不覆盖正式图；发布时正式图已经同步为两条件版本。

仓库提供编译后的[英文正文](paper_interface_focus/main.pdf)、[英文附录](paper_interface_focus/supplement.pdf)和[中文论文](paper_zh_direct/main.pdf)，各保存一份正式PDF。

安装Tectonic或XeLaTeX后，在对应论文目录编译；中文需要SimSun/SimHei/KaiTi/FangSong，英文使用Times New Roman/Arial/Consolas。首次Tectonic编译可能下载TeX包，`--only-cached`只适用于缓存齐全时。

```powershell
cd paper_interface_focus
tectonic main.tex
tectonic supplement.tex
cd ../paper_zh_direct
tectonic main.tex
```

英文附录通过`xr`引用正文标签，先编译正文。没有作者单位或通信邮箱信息，TeX保留TODO占位；这些不影响实验复现。

```powershell
.venv/Scripts/python -m pip install "pytest>=9.1.1"
.venv/Scripts/python -m pytest tests
```

记录审计检验请求/源码/封存哈希、父代复用、回退算术和选择重建；完整复现将重新计算的种群向量、均值和区间与正式汇总逐项比较。输入清单`results/reproduction/INPUT_MANIFEST.json`在流程前后均核验。图形检查包括最小字号与文字边界。验证日志和报告同名加`_reproduct`保存于`results/reproduction/`。

当前发布在独立克隆与新建Python环境中通过完整离线流程：5,658项输入哈希、23组比较中的26,477个数值及2,640场抽样重放均通过，最大误差为0，API调用为0。独立克隆生成的PNG和CSV与项目内运行逐字节一致；测试为80项通过、1项跳过。记录见[独立克隆验证](results/reproduction/clean_clone_validation_reproduct.json)和[完整流程报告](results/reproduction/verification_reproduct.json)。
