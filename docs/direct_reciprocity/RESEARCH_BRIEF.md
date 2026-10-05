> 归档说明：以下为 2026-09-15 至 16 日实验前的研究记录，状态描述保留当时语境。当前方案及进度见 EXPERIMENT_PLAN.md 与 STATUS.md。

# 直接互惠研究简报与证据记录

状态：文献调研进行中；尚未修改实验代码、尚未运行实验。2026-09-15。

## 研究问题

RQ1：在相同代码接口、博弈信息、模型和生成预算下，提示词中的行为目标及反馈信息如何影响策略收益、合作率和稳健性？
RQ2：在相同初始化、变异算子和评价协议下，锦标赛选择、Fermi 模仿及响应预言机式搜索如何改变改进速度、多样性和最终收益？整套机制比较与单因素归因必须分别报告。
RQ3：累计锦标赛收益的提高是否能推广到未参与生成反馈的对手、噪声和对局长度，而非仅改善训练对手适配？

用户约束：使用当前框架创建独立 Git worktree；先调研指定三篇文献，再制定方案，最后实现并实际实验；以锦标赛基准为默认参数。

## 当前仓库证据

- 工作目录：C:/Users/shiwenbo/.minimax/agents/mavis/workspace/llm-reputation-paper/llm-reputation。
- develop HEAD：a6ae52f；存在大量用户未提交改动，不能丢弃或擅自提交。
- 已注册的另一 worktree 是 feature/code-contract-validation（ba75433），尚未创建本任务 worktree。
- docs/evolution_modes.md：现有 Tournament 是精英保留、随机小组竞赛与 full mutation；Fermi 是接受概率、small mutation 和独立初始化的组合。文档不能替代实现核对，尤其同步/异步更新语义需查代码。
- experiments/run_fermi_v3.py：默认 learning_method=fermi，N=15，100代，1000交互/代，fitness_window_fraction=0.2，benefit=3，cost=1。不能将其当作指定 IPD 论文的锦标赛基准。
- 本机工具列表在工作区切换后已无 Zotero 方法；两篇指定论文先通过公开原文检索，不能声称已读 Zotero。

## 指定本地 PDF：已读取全部 9 页文本

Siwei Li, Xin Wang. Code Driven Game Theoretic Evolution of LLM Agents as Holistic Strategy Generators. ICLR 2026 Workshop on AI for Mechanism Design and Strategic Decision Making.
本地：references/1789404497217-1786609484800(1).pdf。
公开检索匹配：https://openreview.net/pdf?id=VBpIRGHktc 。

论文明确参数（第3页 §2.3、§3.1）：

| 参数 | 原文值 |
| --- | --- |
| 博弈 | Iterated Prisoner’s Dilemma |
| R,S,T,P | 3,0,5,1 |
| N | 12 |
| 每代淘汰数 | 6，按混合收益排名保留前6 |
| 代数 | 10 |
| 随机种子数 | 每模型5 |
| 温度 | 1.0 |
| 混合评价 | 0.6 × 同代平均收益 + 0.4 × HoF平均收益 |
| 历史归档 | 每代前3永久加入 HoF |
| 初始 HoF | TFT, Grim, Pavlov, ALLC, ALLD, Random, Alternator, Bayesian, GTFT, Gradual, Prober, Suspicious TFT, ZD Extortion |
| 信息条件 | 完整两方历史；仅末3轮；累计声誉摘要 |

需要进一步核实：每场长度（图与提示词中300对应合作收益，暗示100轮，但正文未明确参数）、重复对局数、自我对局、随机基线具体实现、HoF重复策略处理和更新时点、噪声、初代和10代的计数口径。不得把推定值标为原文明确值。

方法证据：第8–9页给出初始与继承提示词。初始要求最大化锦标赛得分；继承反馈同时给幸存者、失败策略与战绩，要求分析失败并改进。不能据此把结果单独归因于某种提示词或某种选择机制。

需保留的局限：正文将动态 HoF 用于训练，而图2底部称 static HoF baselines，训练分数与固定评价分数需明确区分。第2–3页 tabula rasa 并不排除模型预训练中的策略先验。原文的强泛化及内在推理表述不等于跨对手/跨环境的独立验证。

## 后续顺序

1. 核实另两篇指定论文及经典 IPD 评价、噪声、对手分布的相关证据；汇总完整中文调研。
2. 固定实验计划：默认值出处、待选实现约定、提示词×演化方式的控制变量、训练/测试隔离、预算与统计单位。
3. 创建独立 worktree 并记录基准提交及当前未提交框架改动的迁移清单；不携带密钥或大型实验结果。
4. 实现直接两方历史接口、完整收益矩阵、累计对局评价、HoF与独立测试、可重放生成记录。
5. 先做解析基线/协议验证，再实际运行 LLM 实验并分析结果；dry-run 或手工策略烟测不能作为研究任务完成依据。

## 实现核对补充（2026-09-16）

已读取 evolution_architecture.py 的两类 plan 实现及 game.py：

- 当前 FermiEvolutionRule.plan 从不可变 population snapshot 中为所有 learner 选择 role model，先生成全部 jobs；这是代际快照式批量计划，不能沿用文档中“代内逐步变化”的说法。直接互惠比较需显式记录 update_schedule。
- 当前 TournamentEvolutionRule 通过 elite_count + tournament_size 抽样找幸存者，与参考论文按全部 fitness 取前 N-M 不同；应区分 tournament_selection 与 paper_truncation。
- 当前 DonorGame 是每步随机抽取一个 pair，之后分发观察；收益为 (b-c,-c,b,0)，与论文 (3,0,5,1) 的四格矩阵不等价。对 donation game 加常数也不能同时满足所有差值，必须支持完整收益矩阵。
- 当前 fitness 默认仅统计最后20%的交互；累计锦标赛要求整场累计、每个对手平均，然后按 population/HoF 权重合成，不能复用窗口计分作为默认。

## 评价方法补充来源（已核实原始发表页面）

- Glynatsi, Knight, Harper (2024), Properties of winning Iterated Prisoner’s Dilemma strategies, PLOS Computational Biology. https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1012644 。195种策略、多种锦标赛环境的结果强调对手构成与噪声/长度的重要性；不能由固定小型 HoF 优胜推导普遍稳健。
- Harper et al. (2017), Reinforcement learning produces dominant strategies for the Iterated Prisoner’s Dilemma, PLOS ONE. https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0188046 。提供非 LLM 的学习策略参照；需将训练对手适配与未见环境评价分离。
- Balancing Cooperativeness and Adaptiveness in the (Noisy) Iterated Prisoner’s Dilemma, arXiv:2303.03519. https://arxiv.org/abs/2303.03519 。已核实摘要，具体算法与参数待全文核对，暂不用于细节结论。
