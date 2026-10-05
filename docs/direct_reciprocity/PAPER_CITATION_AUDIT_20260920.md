# 论文引用独立核验

**修订后核验：两处已解决，未解决项为 0。**

核验日期：2026-09-20。对象：`FEEDBACK_ATTRIBUTION_DRAFT.md` 的 11 条参考文献及正文引用处。

本轮由独立子代理执行，只接收主稿和参考文献，不读取研究日志、证据规划、实验代码或结果文件。按 paper-writer 的 fresh-context verification 流程，对每条文献执行题名、作者与年份、核心关键词三种查询，并回到原文核对正文主张。本报告不复算论文实验，不评价被引研究自身的实验可靠性。定位使用章节和句首；括号内行号是本轮读取时的位置。

## 结论

11 条参考文献均存在；主稿所列作者、年份、版本及已标注的发表渠道未发现实质性错误。初审发现 [10] 的一处表述超出原文范围，另有一处跨文献概括容易误将外部候选选择归入所有反馈修订方法。主代理已完成两处局部修改；本核验代理重新读取主稿并对照原文确认，均已解决。**最终状态：11/11 引用通过，无未解决问题项。**

不存在 NOT_FOUND 项。第 3 条的 OpenReview 页面触发浏览器验证，但已用授权的本地论文正文和 workshop 官网交叉解决，不将访问受阻误记为文献不存在。Nature 页面直接访问重定向失败，使用其官方页面的检索全文及作者机构说明交叉核验。

## 初审要求修改的两处（已解决）

### 1. [10] 支持泛化评价分布，不能直接支持验证选择对输出的作用

- 位置：第 7.3 节（读取时第 209 行）。
- 原句片段：“与共同演化泛化研究相比，验证分布对输出的作用也有明确先例 [10]。”
- 判定：**OVERCLAIM，局部**。[10] §2 以对手分布下的期望表现定义泛化，并研究用测试对手样本估计泛化；其有偏与无偏测试集比较说明评价结论依赖测试分布。该文不提供与本文 S3 相同的独立验证选择干预证据。
- 建议替换：“在指定测试对手分布上评价共同演化策略的泛化表现，已有明确研究先例 [10]。”
- 复核状态：**RESOLVED**。主稿实际已改为“在指定测试对手分布上评价泛化，也已有共同演化研究的明确先例 [10]”，与原文支持范围一致。
- 主稿第 1 节关于训练成绩与未见对手表现的区别，以及第 2 节关于指定对手分布上的泛化，均可保留。

依据：[作者稿，§1–2、§5–6](https://www.cs.bham.ac.uk/~pxt/PAPERS/ieee_tec07.pdf)。

### 2. 不要把 Self-Refine 概括为必然包含外部候选筛选

- 位置：引言第二段，紧接 [6–8] 的句子（读取时第 21 行）。
- 原句：“然而，完整流程中的正向结果通常同时包含候选生成、重复尝试和外部选择。”
- 判定：**OVERCLAIM，跨文献概括风险**。上下文容易让读者将该句理解为对 [6–8] 的共同方法描述。但 Self-Refine §2 的通用流程返回最后一次修订，不能据此称其普遍依靠外部候选选择。
- 建议替换：“在将修订与候选搜索结合的系统中，最终收益还可能同时受到重复生成和外部选择的影响 [1,2,8]。”随后“若系统只保留少数优良变体”的条件论证可保留。
- 复核状态：**RESOLVED**。主稿实际已改为“在将生成或修订与候选搜索结合的系统中，最终收益还可能同时受到重复生成和外部选择的影响 [1,2,8]”，限定了适用系统并指向相应搜索文献。

依据：[Self-Refine §2](https://arxiv.org/html/2303.17651v2)、[LLaMEA §III-D](https://arxiv.org/html/2405.20132v3)、[GEPA v2 方法](https://arxiv.org/pdf/2507.19457v2)。

## 逐条结果

| 编号 | 元数据 | 正文主张 | 结论 |
| --- | --- | --- | --- |
| [1] FunSearch | 首作者、2024 卷期、2023 在线发表、625:468–475 均吻合 | 程序生成与系统评价相结合 | VERIFIED |
| [2] LLaMEA | van Stein 与 Bäck；2024；v3 为 2024-08-20 | 生成、变异、选择；总体与函数组成绩反馈 | VERIFIED |
| [3] Li 与 Wang | 两位作者、题名、ICLR 2026 workshop 吻合 | 完整 Python 策略、锦标赛成绩、历史档案支持演化 | VERIFIED |
| [4] Willis 等 | 四位作者、2025、v1 题名吻合 | 提示诱发不同态度策略及群体选择 | VERIFIED |
| [5] CSRO | 四位作者、2026、2603.10098v1 吻合 | 代码策略响应搜索；零样本、迭代修订、演化搜索 | VERIFIED |
| [6] Self-Refine | Madaan 等、2023、NeurIPS 吻合 | 自反馈迭代；具体可操作反馈消融 | VERIFIED；跨文献概括问题已解决 |
| [7] Reflexion | Shinn 等、2023、v4 吻合 | 环境/任务反馈转为文字反思并存入记忆 | VERIFIED |
| [8] GEPA | Agrawal 等、ICLR 2026；初稿 2025；v2 2026-02-14 | 轨迹反思与候选搜索；代码优化实验 | VERIFIED |
| [9] When Benchmarks Talk | Pan 等、ACL Findings 2025、24672–24700 吻合 | 方向正确性分类；错误方向反馈也可能伴随改进 | VERIFIED |
| [10] Chong 等 | 作者、2008、12(4):479–505、DOI 吻合 | 泛化评价主张支持；原验证选择效果表述已收窄 | VERIFIED（原 OVERCLAIM 已解决） |
| [11] Huang 等 | 首作者、2023、2310.01798v1 吻合 | 无外部反馈纠错限制；oracle 答案信息与停止条件 | VERIFIED |

### [1] Mathematical discoveries from program search with large language models

Nature 官方条目列 Bernardino Romera-Paredes 为首作者，在线日期 2023-12-14，正式卷页为 Nature 625, 468–475 (2024)。主稿明确区分两种年份，正确。原文摘要与方法将预训练模型与系统评价器结合，支持引言、相关工作及讨论中的程序搜索概括。没有必要增加更强的模型理解或因果归因主张。

来源：[Nature 原文](https://www.nature.com/articles/s41586-023-06924-6)、[作者机构对生成—评价循环的说明](https://deepmind.google/blog/funsearch-making-new-discoveries-in-mathematical-sciences-using-large-language-models/)。

### [2] LLaMEA

arXiv 版本历史确认 v3 发布于 2024-08-20，两位作者及题名吻合。§III-C 明确比较总平均性能摘要与五类 BBOB 函数组的细分均值/标准差；§III-D 讨论变异、选择及详细反馈。因此第 2.2 节的细分反馈先例并非仅靠摘要推断。主稿按 2024 预印本引用合理，不能把后来正式期刊版本年份静默套在 v3 上。

来源：[版本历史](https://arxiv.org/abs/2405.20132v3)、[全文 §III-C–D](https://arxiv.org/html/2405.20132v3)。说明：HTML 的排版脚注出现异常的 2026 年 manuscript received 日期，年份核验采用 arXiv 版本历史，而不采用该脚注。

### [3] Code Driven Game Theoretic Evolution of LLM Agents as Holistic Strategy Generators

OpenReview 直接访问受验证页阻挡，检索可返回论文条目。按授权读取本地 `references/1789404497217-1786609484800(1).pdf` 第 1–3 页：标题、Siwei Li / Xin Wang、ICLR 2026 workshop 抬头吻合；§2 描述完整 Python 策略、锦标赛、HoF 和成绩指导更新。workshop 官网 accepted papers 列出相同标题及两位作者，列为 Short Paper。主稿没有将 workshop 冒写为 ICLR 主会。

来源：[论文入口](https://openreview.net/pdf?id=VBpIRGHktc)、[workshop 官方收录列表](https://alimama-tech.github.io/aims-2026/)。

### [4] Will Systems of LLM Agents Cooperate: An Investigation into a Social Dilemma

指定 v1 为 2025-01-27，四位作者顺序吻合。§3.2–3.4 描述由不同提示生成 aggressive/cooperative/neutral 策略，并用 Moran process 研究态度群体变化，支持主稿概括。这里的群体选择不等于每代重新生成代码；主稿现有文字没有越过此界限。

来源：[指定版本全文](https://arxiv.org/html/2501.16173v1)。另有 AAMAS 2025 扩展摘要，题名使用 “Lead to Cooperation”；主稿明确引用 arXiv v1，因此现有 “Cooperate” 不算题名错误，无须强制换成另一版本。

### [5] Code-Space Response Oracles

指定版本为 2026-03-10；Daniel Hennes、Zun Li、John Schultz、Marc Lanctot 顺序吻合。§2.4.2 明列 ZeroShot、LinearRefinement 和 AlphaEvolve 三种形式。主稿关于代码空间响应搜索及三种生成/修订机制的陈述有直接支持。原文实验是重复石头剪刀布与 Leduc poker，主稿仅称“博弈领域”，没有误称其为囚徒困境研究。

来源：[arXiv v1，§2.4.2、§3.1](https://arxiv.org/html/2603.10098v1)。

### [6] Self-Refine

官方 NeurIPS 2023 条目确认题名与首作者；arXiv v2 为 2023-05-25。§2 支持模型生成反馈并迭代修订。§4 Table 2 比较具体可操作反馈、笼统反馈、无反馈，支持主稿“可以优于”的措辞；不是对所有任务和反馈形式的普遍保证。需改的是上述邻接概括，而不是删除 Self-Refine 的反馈消融陈述。

来源：[NeurIPS 官方条目](https://proceedings.neurips.cc/paper_files/paper/2023/hash/91edff07232fb1b55a505a9e9f6c0ff3-Abstract-Conference.html)、[arXiv v2 §2、§4](https://arxiv.org/html/2303.17651v2)。

### [7] Reflexion

arXiv v4 日期为 2023-10-10。全文与摘要明确将任务反馈转化为反思文字，存入 episodic memory 以影响后续尝试，支持主稿引用。当前 “Noah Shinn et al.” 无误。若后续展开作者名单，应按所引版本抄录：v4 包含 Edward Berman，而 NeurIPS 官方会议页的作者列表不同，不能混拼两个版本。

来源：[v4 版本与作者](https://arxiv.org/abs/2303.11366v4)、[v4 全文](https://arxiv.org/html/2303.11366v4)、[NeurIPS 会议条目](https://proceedings.neurips.cc/paper_files/paper/2023/hash/1b44b878bb782e6954cd888628510e90-Abstract-Conference.html)。

### [8] GEPA

arXiv 初稿为 2025-07-25，v2 为 2026-02-14；v2 抬头注明 ICLR 2026 接收，ICLR 官方论文集也有对应条目。因此主稿“2026（初稿 2025）”正确。v2 摘要、方法与 §5.1 支持轨迹反思、提出并测试更新及代码优化实验的概括。主稿没有引用新版与旧版之间可能变动的具体领先幅度，未发现版本混用造成的事实错误。

来源：[arXiv 版本页](https://arxiv.org/abs/2507.19457v2)、[v2 全文](https://arxiv.org/pdf/2507.19457v2)、[ICLR 2026 官方条目](https://proceedings.iclr.cc/paper_files/paper/2026/hash/0e9e708b6f48e14fd0ac29e167413f76-Abstract-Conference.html)。

### [9] When Benchmarks Talk

ACL 官方条目列 Jane Pan、Ryan Shar、Jacob Pfau、Ameet Talwalkar、He He、Valerie Chen，年份与页码吻合。全文 §4.1–4.2 和 Figure 4 确实按方向正确性分类，并观察到错误方向反馈后仍有性能改善。主稿使用“也可能伴随改进”，保持了描述性关联语气，没有错误声称随机操纵错误反馈证明了因果改善。

来源：[ACL 元数据](https://aclanthology.org/2025.findings-acl.1267/)、[全文 §4，PDF 第 6–7 页](https://aclanthology.org/2025.findings-acl.1267.pdf)。

### [10] Measuring Generalization Performance in Coevolutionary Learning

University of Birmingham 作者机构记录确认 2008、12(4)、479–505 与 DOI；作者稿确认三位作者。正文 §1 解释种群内相对适应度不保证新对手上的全局表现，§2 将泛化写为对手分布上的期望，支持主稿引言和相关工作的陈述。讨论中的“验证分布对输出的作用”须改为泛化评价层面的陈述，见前述必须修改项。

来源：[作者机构书目](https://research.birmingham.ac.uk/en/publications/measuring-generalization-performance-in-co-evolutionary-learning/)、[作者稿](https://www.cs.bham.ac.uk/~pxt/PAPERS/ieee_tec07.pdf)。作者稿标题用 “Co-evolutionary”，正式索引常用 “Coevolutionary”；此连字符差异不构成实质性元数据错误。

### [11] Large Language Models Cannot Self-Correct Reasoning Yet

指定 v1 为 2023-10-03，Jie Huang 为首作者。§3.1 将正确标签作为停止依据，并用随机答案加 oracle 停止的对照解释收益归因问题；§3.2 研究无外部反馈时的纠错。因而主稿关于外部答案信息、停止规则和无外部反馈限制的措辞有直接支持。主稿未把结论夸大为所有模型与所有反馈设计都不能纠错。

来源：[v1 元数据](https://arxiv.org/abs/2310.01798v1)、[v1 全文 §3.1–3.2](https://arxiv.org/html/2310.01798v1)。

## 核验边界与交付条件

正文和参考文献编号可双向对应，未发现未引用条目。预印本、conference 与 workshop 标注均按实际所引版本判断，不因存在更新版本而擅自改写年份。

主代理已完成前述两处局部替换，本核验代理已独立重新读取并完成针对性复核；本轮识别的引用层问题全部解决，无须删除文献或增加研究数据。主稿未由本核验代理改动。本报告证明的是引用存在及当前主张的来源匹配，不是对主研究数据、被引实验结论或全文论证的整体背书。逐条详述保留初审问题背景，最终状态以本结论和表格为准。
