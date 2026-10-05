# 种群图、策略实例与 PCA：文献核验及写作依据

核验日期：2026-09-24。用途：为本轮新增图表和正文叙述提供依据；本文件不是新增实验结果。已先通过 Zotero MCP 检索并阅读三篇核心论文的 PDF 全文及图注，再对 Zotero 中未找到的两篇查阅原始出版页面或 arXiv。以下设计判断主要依据全文、方法与图注，未声称完成这些参考论文的逐像素版式审查。

## 1. 最值得借鉴的不是图形样式，而是证据分层

| 文献 | 实际采用的证据组织 | 本文可直接借鉴的做法 | 不可越界之处 |
| --- | --- | --- | --- |
| Willis 等，2026，v2 | 行为指纹与共同 PCA → 群体混合组成下的自博弈 → 收益偏置模仿下的文化演化 | 在相同坐标和测量协议中呈现整个策略集合；用实际行为测量解释策略差异 | 其 PCA 输入是行动响应，本文既有嵌入是代码表示；其多代模拟也不能替代本文缺失的长期演化证据 |
| Binz 与 Schulz，2023 | 任务结构和真实输入示例 → 总体表现 → 机制独有的条件预测 | 用具体父代和候选让读者理解“改了什么”，再用全部种群的配对证据检验“为什么改变” | 总体收益好并不自动支持定向修复；单个成功示例也不能证明反馈作用 |
| Ashery 等，2025 | 个体无历史时的选择 → 群体最终惯例 → 特定历史条件下的响应 | 将原始候选、采用策略与总体统计并排，明确各层级的分母和实验单位 | 当前一步候选采用不是规范形成、群体共识或长期文化演化 |

本轮建议形成三类互补证据：**候选与种群分布说明普遍性，真实执行实例说明行为含义，共享 PCA 说明代码集合的结构。** 三者均不能替代 Accurate−Mismatched 的预定主比较。

## 2. Willis 等：共有坐标与可解释的策略对象

**核验版本：** *Evaluating Collective Behaviour of Hundreds of LLM Agents*，arXiv:2602.16662v2；PDF 首页标注 Strategic Engineering Workshop on LLMs and Game Theory，SE@AAMAS 2026，May 25, 2026，18 页。它是 workshop 论文，不能写为 AAMAS 主会论文。[版本入口](https://arxiv.org/abs/2602.16662v2)

**Zotero：** 主条目 `2XWZF6LV`，PDF `C9F2ULY3`。库内另有 v1 条目 `AUNK3X9G`、PDF `2SZY99XH`，本轮已明确区分。v2 PDF 的作者顺序为 **Richard Willis, Jianing Zhao, Joel Z. Leibo, Yali Du**；Zotero 元数据仍将 Du 排在 Leibo 前，引用应以所读 v2 正文为准。

### 方法和图表已核验内容

v2 §4.2 枚举四人、七轮博弈中的对手历史，每条历史进行 30 次 rollout，取得策略的平均合作响应，组成 5,461 维行为向量。所有游戏、模型和态度共同拟合一套 PCA。Figure 1 展示策略点、各集合中心以及固定参考策略；前两主成分解释 61.2% 和 9.2% 的方差。Table 1 另外用完整特征空间报告集合内部距离、标准化中心距离及有效维数。因此，二维图用于展示，而不是取代完整空间的统计。

论文用 Always Cooperate、Always Defect 以及条件响应策略解释轴的方向，并提醒后期轮次包含更多历史组合，可能在指纹中占更大权重。这一提醒非常有用：低维轴的解释取决于输入特征及采样权重，不能仅凭点云外观决定。

**版本陷阱：** v1 使用五轮历史、50 次 rollout、961 维和 65.5%／9.0% 的解释率。上述数字不应与 v2 混写。

### 对本文的具体设计建议

- 用一套共同拟合的 PCA 比较初始化策略、关闭思考的候选和开启思考的候选；各子图共用坐标范围，避免分别旋转后造成虚假可比性。
- 保留所有合格策略的可追溯 ID，并说明重复代码的去重和点大小规则。初始化种群的 240 个成员、60 个被选父代、两批各 600 个请求槽位和最终可执行代码数是不同分母。
- 复用既有 SFR 代码嵌入时，图名应为“策略代码表示的共享 PCA”或“策略代码空间”，坐标应写 PC1、PC2 和解释率。**不能直接沿用 Willis 的“合作率轴／响应性轴”解释。** 行为特征可作为外部颜色或伴随面板，但仍需要独立数据支持。
- 父代到候选的连线仅表示一次修订关系。多个候选和 S3 选择不得画成多代演化轨迹。
- 若给出全部种群的小图，应让读者看见每个 seed 的完整集合，而非只展示最漂亮的分离结果。PCA 的重叠不能证明策略行为相同，分离也不能证明诊断有效。

## 3. Binz 与 Schulz：先让读者看懂任务，再检验机制

**书目：** Marcel Binz and Eric Schulz. *Using cognitive psychology to understand GPT-3*. Proceedings of the National Academy of Sciences, 120(6), e2218523120 (2023). DOI: 10.1073/pnas.2218523120。[论文入口](https://doi.org/10.1073/pnas.2218523120)

**Zotero：** 条目 `U52S9HV3`，PDF `U33LI89Q`；元数据与 PDF 题名、作者、卷期及文章号相符。

### Figure 3 及相邻正文的证据结构

Figure 3 依次放置 Horizon task 的视觉示意、一个实际提交给 GPT-3 的输入实例、按 horizon 条件比较的平均 regret。误差条是 **均值标准误**。正文随后用不同信息条件下的选择模型检验随机探索与定向探索的预测，而不是从较低 regret 直接推断模型采用了哪种探索机制。

这一写法特别适合本稿：先用一个可执行实例让读者看到“持续背叛下的合作减少”或“临时冲突后的恢复延迟”究竟是什么，再展示总体统计与 Accurate−Mismatched 对照。**真实例子负责解释行为，配对干预负责检验归因。** 不应把实例中出现的分支修改解释为模型内部推理机制。

### 可采用的实例面板

建议每个实例包含父代 ID、候选 ID、信息条件、父代与候选的关键执行规则、相同探针下的行动序列，以及 V 是否接受和 H 收益是否改善。短规则可从程序中人工核对后忠实概括；不要用模型生成的策略名称代替代码执行证据。

选例规则须可复现。例如先按“接受且测试改善”“接受但测试退化”“拒绝”分层，再在各层按收益接近该层中位数、候选 ID 打破并列的规则选取。若只选机制容易解释的例子，应直接称为说明性案例，不称为典型或代表性结果。用 H 帮助挑选说明性案例可以，但需说明这是事后展示规则，不能倒写为实际 S3 选择过程。

**统计写法的启发：** 此文综合使用均值、标准差、SE、回归系数与检验结果。借鉴的是“统计量服务于具体问题”，不是将本稿的区间全部改成另一种误差条。正文可先写方向、大小和跨种群一致性，完整推断放表格或附录；任何误差条都应明确含义。

## 4. Ashery 等：同一图中区分个体与群体观察量

**书目：** Ariel Flint Ashery, Luca Maria Aiello and Andrea Baronchelli. *Emergent social conventions and collective bias in LLM populations*. Science Advances, 11(20), eadu9368 (2025), published 14 May 2025. DOI: 10.1126/sciadv.adu9368。[论文入口](https://doi.org/10.1126/sciadv.adu9368)

**Zotero：** 本轮读取条目 `4UUTF3V8`、PDF `GV5HUULP`；另有 `IHZHPB8N`／`9ABU9Z7N`。所读条目缺卷期和 DOI，但 PDF 首页、末页明确给出上述出版信息，不能因为条目为空就遗漏或猜测。

### Figure 2 及相邻正文的证据结构

Figure 2A 展示最终共识名称的分布。Figure 2B 将无历史个体的首次选择概率与群体运行最终达成的共识比例并排比较，并明确两者不同的样本来源和次数。图注对个体偏差的表述是缺乏足够证据拒绝无偏假设；不能将“不显著”简化为已证明严格无偏。随后的特定记忆状态分析进一步解释早期对称与后续不对称如何并存。

本文可借鉴这种分层方式：把全部原始候选的质量分布与 S3 最终采用结果并排，让读者看见“生成了什么”和“留下了什么”。种群间的散点、配对线或 heatmap 可展示均值之外的异质性；接受／拒绝及测试改善／退化的计数能够说明选择并不保证迁移。分布图的每个候选不能被当作新的独立种群，推断仍以原有 20 个 seed 为单位。

**叙事边界：** 文中存在真实的重复命名互动与共识形成过程。本稿没有这个过程，不能把 S3 接受比例称为社会共识，也不能将一步修订后合作率改变称为规范涌现。可借鉴其“现象 → 候选解释 → 分层检验”的叙述顺序。

## 5. 补充核验：研究定位及方法近邻

### Machine behaviour

Zotero 精确标题未找到该论文，故查看 [Nature 原始页面](https://www.nature.com/articles/s41586-019-1138-y)。页面确认：Iyad Rahwan 等，*Machine behaviour*，Nature 568, 477–486 (2019)，published 24 April 2019，DOI 10.1038/s41586-019-1138-y，文章类别为 Review。页面摘要主张将 AI 行为作为跨学科科学研究对象，适合用于引言定位。本轮只核验出版信息、摘要及公开图题，不把未取得的全文细节作为论据。

### CUDAnalyst

Zotero 以完整标题关键词和 CUDAnalyst 均未找到。已读 [arXiv v1 全文](https://arxiv.org/html/2605.26720v1)：Yee Hin Chong, Jiaming Wu, Youhui Zhang and Peng Qu，*Towards Feedback-to-Plan Decisions for Self-Evolving LLM Agents in CUDA Kernel Generation*，arXiv:2605.26720v1 (2026)。Figure 1 对比端到端轨迹漂移与冻结状态干预；Figure 4 比较 DummyPlan 和同代程序间随机置换反馈。前者替换规划输出，后者破坏程序—反馈对应，均不能简单等同本稿的输入背景文本对照。

该文强调定点、受控干预，而本稿还需区分未经选择的平均提案与固定池采用结果。不能把冻结程序、错配反馈或“流程改善不等于诊断有效”写成首次发现。[arXiv 摘要页](https://arxiv.org/abs/2605.26720) 的作者备注称 ICML 2026 accepted、camera-ready in progress；本轮未查到正式 proceedings 元数据，因此新增引用宜暂按所读 arXiv 版本，不编造卷页。

## 6. 面向当前稿件的图文组织

1. **种群统计图：候选质量如何分布，选择后留下什么？** 展示两配置的原始质量分布、改进／退化／回退计数及 seed 配对结果。对照配置包括输出预算和执行时间等变化，不能把配置差异全部归因于 thinking 开关。
2. **行为图和实例：分数改变对应什么互惠行为？** 使用同一组独立探针贯穿父代、原始候选和最终采用策略。不同采用政策是并行比较，不是时间轴。局部实例解释规则与行为，完整集合统计约束其普遍性。
3. **全策略 PCA：代码集合在共同表示中如何分布？** 主图简洁呈现所有初始化成员及有效候选，可附完整 seed 分面。报告输入、有效样本、去重、PCA 拟合集合和解释率；把代码结构与行为测量分开命名。

可用于正文的过渡语（需随实际新增数值完成后再写结果）：

> 平均收益只描述策略修改的总体方向，无法说明候选是否普遍改善，也不能告诉我们哪些互惠行为被保留下来。因此，我们进一步检查全部种群的候选分布，并在同一组独立行为探针上比较父代、原始候选与最终采用策略。代码表示的低维投影用于描述候选集合的结构；反馈的定向作用仍由预定的组间干预比较检验。

图注应第一句回答图的问题，再交代面板、分母、配对单位、统计标记和探索性地位。避免用长串区间作为每段开头，也不应为了丰富图表而重复同一个均值五次。

## 7. 可复用的 BibTeX（未直接修改主库）

```bibtex
@inproceedings{williscollective2026,
  author = {Willis, Richard and Zhao, Jianing and Leibo, Joel Z. and Du, Yali},
  title = {Evaluating Collective Behaviour of Hundreds of {LLM} Agents},
  booktitle = {Strategic Engineering Workshop on LLMs and Game Theory (SE@AAMAS 2026)},
  year = {2026},
  note = {arXiv:2602.16662v2},
  url = {https://arxiv.org/abs/2602.16662v2}
}

@article{binz2023,
  author = {Binz, Marcel and Schulz, Eric},
  title = {Using cognitive psychology to understand {GPT-3}},
  journal = {Proceedings of the National Academy of Sciences},
  volume = {120},
  number = {6},
  pages = {e2218523120},
  year = {2023},
  doi = {10.1073/pnas.2218523120},
  url = {https://doi.org/10.1073/pnas.2218523120}
}

@article{ashery2025,
  author = {Ashery, Ariel Flint and Aiello, Luca Maria and Baronchelli, Andrea},
  title = {Emergent social conventions and collective bias in {LLM} populations},
  journal = {Science Advances},
  volume = {11},
  number = {20},
  pages = {eadu9368},
  year = {2025},
  doi = {10.1126/sciadv.adu9368},
  url = {https://doi.org/10.1126/sciadv.adu9368}
}

@misc{cudanalyst2026,
  author = {Chong, Yee Hin and Wu, Jiaming and Zhang, Youhui and Qu, Peng},
  title = {Towards Feedback-to-Plan Decisions for Self-Evolving {LLM} Agents in {CUDA} Kernel Generation},
  howpublished = {arXiv:2605.26720v1},
  year = {2026},
  doi = {10.48550/arXiv.2605.26720},
  url = {https://arxiv.org/abs/2605.26720v1}
}
```

引文审核范围：三篇核心论文的全文和图注、Willis v1/v2 差别及作者顺序、CUDAnalyst 原文控制设计；Machine behaviour 仅公开页面。未复制原论文图像，未改 Zotero 条目，未将文献结论当成本研究结果。
