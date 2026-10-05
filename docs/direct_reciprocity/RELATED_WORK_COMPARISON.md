# 从合作策略到反馈利用：相关工作与当前研究的对照

2026-09-19。本文配合 [研究草稿](FEEDBACK_ATTRIBUTION_DRAFT.md) 阅读；第一阶段事实以 `results/feedback_attribution_v1` 为准，新增的第二阶段事实以 `results/feedback_specificity_v2` 为准。第 1–7 节保留最初的文献对照，第 8 节同步第二阶段的完成结果，不新增文献首次性主张。

## 摘要

相关工作已经覆盖 LLM 生成互惠策略、收益驱动的代码演化、具体反馈与自我修订、以及共同演化的泛化评价。“提示词影响合作”“详细反馈可能优于粗粒度反馈”“训练收益不保证泛化”都不是本文可独立主张的新发现。本文固定父代及代码上下文，先干预成绩对应关系，再在 20 个新种群中比较准确与错配诊断、等长背景及合作建议，并交叉评价同一候选池的三种选择规则。第二阶段没有支持匹配诊断的增量收益；验证选择后准确组虽高于父代，却未优于总分组。当前定位是反馈归因的受控边界检验，而非新的成功演化算法或内部机制发现。这与前人的整体系统收益并不直接矛盾；完整结果见第 8 节。

## 1. 范围与研究问题

本轮回答三个问题。第一，最接近的合作与策略演化论文实际研究的是策略能力、群体选择，还是生成器利用成绩反馈？第二，具体诊断、自我修订和反馈真实性的哪些结论已经存在？第三，当前的一步干预究竟能补充或限制哪些既有结论，还不能回答哪些问题？

检索采用三个独立视角：直接互惠与合作；支持和质疑反馈修订的工作；共同演化、预算和泛化评价。主线程补查 GEPA 与 VISTA，并核对本地实验。优先使用论文原文、正式会议页面和作者机构稿；摘要级证据只用于摘要所支持的概括。不把未检索到完全相同设计视为首次性的证明。

下文按主要研究对象分类。一个系统可以同时使用反馈和选择，但在这里仅按其对本文最重要的证据角色归入一个主题，以免将同一结论重复计作多条支持。

## 2. 策略能力与群体演化：最接近的直接互惠工作

| 工作 | 实际研究对象及主要发现 | 与当前工作的关系 |
| --- | --- | --- |
| Li 与 Wang，2026，*Code Driven Game Theoretic Evolution of LLM Agents as Holistic Strategy Generators* | LLM 生成完整策略，在 peer-play 与 HoF 成绩下选择和改写；报告合作形成及锦标赛表现改善 | 框架最接近。整体过程改善未单独识别生成器读取正确成绩的作用。当前固定父代的一步成绩干预提供更窄的检验，但不推翻多代精英选择的整体效果。 |
| Willis 等，2025，*Will Systems of LLM Agents Cooperate* | 提示生成不同态度的策略池，比较合作与攻击行为，再用 Moran 过程选择 | 提示影响合作已有先例。其演化复制既定策略池，并非每代依据锦标赛成绩生成新策略；本文研究生成端反馈。 |
| Sistla 与 Kleiman-Weiner，2025，*Evaluating LLMs in Open-Source Games* | 策略可读取对手源码；研究源码理解及参照前轮源码、交互历史的程序修订 | 强调代码本身携带行为信息。我们的全代码条件可能降低数值成绩的边际价值，但这尚是解释假设；运行时信息接口也不同。 |
| Pal 等，2026，*Large language models instantiate evolutionarily robust strategies of cooperation* | 从模型对历史的动作响应刻画有效策略与稳健性；合作与理性表现依赖条件 | 说明合作策略及其稳健性已有专门刻画。其 evolutionarily robust 不等于通过多代代码变异取得改进；本文也未进行同等演化稳定性检验。 |

Li 与 Wang 是本文最直接的参照：两者都以完整代码和双边历史为对象，但该文观察的是生成、筛选与档案共同作用的系统轨迹，而本文当前将父代固定后改变生成端成绩。该文还在 Future Work 中提到全信息与受限信息的反馈粒度比较，将细节留待后续发表；因此不能写“此前没有研究反馈粒度”。准确的区别是公开稿未提供本文这种固定父代的真实／错配／隐藏成绩对照。[本地原文](../../references/1789404497217-1786609484800(1).pdf)，[公开论文](https://openreview.net/pdf?id=VBpIRGHktc)

Willis 等的提示实验与 Pal 等的策略刻画共同说明，合作行为可以随条件变化；它们不回答生成器是否利用正确成绩改进代码。尤其需要区分 Willis 长稿中的自我批评改写与后续固定策略池的 Moran 选择，不能把两者拼成成绩反馈驱动的逐代代码学习。[Willis 等原文](https://arxiv.org/html/2501.16173v1)，[Pal 等出版社页面](https://academic.oup.com/pnasnexus/article/5/6/pgag210/8705778)

Sistla 与 Kleiman-Weiner 则提示另一个边界：当代码可见时，模型可直接推断行为，正确数值可能不是唯一有效信号。但他们的程序在执行时可以读取对手源码，我们的执行策略只能读取双方行动历史；两类结果不能直接等同。[NeurIPS 2025 原文](https://arxiv.org/html/2512.00371v1)

## 3. 反馈指导生成：不能遗漏的概念和方法先例

| 工作 | 与本文相关的已验证内容 | 不能作为本文独立创新的部分 |
| --- | --- | --- |
| Self-Refine，Madaan 等，2023 | 比较具体、笼统和无反馈，强调可操作的修订意见 | 具体反馈有时优于笼统或缺失反馈 |
| Reflexion，Shinn 等，2023 | 将环境反馈与执行轨迹转成文字反思，比较测试与反思的组合 | 利用行为结果、而非仅凭再次生成来修订 |
| LLaMEA，van Stein 与 Bäck，2024 | 原版已比较总体成绩与按 BBOB 函数组别细分的成绩反馈 | 详细成绩反馈消融、反馈驱动代码演化 |
| CSRO，Hennes 等，2026 | 将代码策略生成接入 PSRO，使用对手信息与收益反馈进行迭代改进 | 多智能体代码策略、收益反馈和搜索的组合 |
| GEPA，Agrawal 等，2025／2026 | 使用轨迹和反馈进行反思式更新，并以候选筛选支持迭代搜索 | 丰富诊断、credit assignment 与演化搜索结合 |
| When Benchmarks Talk，Pan 等，2025 | 分析交互编程反馈的正确性、修订收益及行为变化 | 反馈方向正确不保证修订更好；表面编辑不等于行为改进 |

Self-Refine 与 LLaMEA 已分别在文本反馈和数值反馈的粒度上做出对照：前者改变修订意见的具体程度，后者改变性能报告的细分程度。因此，本文的 diagnostic−true 正差不能独立构成“首次发现详细反馈有效”。区别在于本文先固定父代和群体源码，再破坏或隐藏数值对应关系，并测量未筛选的提案分布。[Self-Refine 原文](https://arxiv.org/html/2303.17651v2)，[LLaMEA 原文，§III-D](https://arxiv.org/html/2405.20132v3)

Reflexion 的模块消融提示，反思与可执行测试依据需要分别考察；CSRO 则表明执行策略的收益反馈已经参与多智能体代码搜索。二者对反馈利用提供正向证据，但整体系统或模块组合的收益不能自动等同于“给定相同父代，显示正确数值比显示错配数值更有用”。当前实验检验的是这个更局部的处理效应，而不是复现其全部系统。[Reflexion 原文](https://arxiv.org/html/2303.11366v4)，[CSRO 原文](https://arxiv.org/html/2603.10098v1)

GEPA 是必须正面承认的邻近工作：它读取轨迹和评估反馈，使用反思提出更新，再评价候选。因此，我们不能将“总分用于选择，诊断用于修改”的总体思路写成原创。GEPA 还包含代码优化实验，不能仅凭其名称含 Prompt 就将其排除出代码演化相关工作。[GEPA 原文，§3、§5.1](https://arxiv.org/pdf/2507.19457)

Pan 等对编程反馈的分析与本文的真实／打乱成绩结果尤其接近：正确反馈并不总伴随更好修订。不过，该文对反馈方向正确性的分析属于对已生成反馈的事后分类；本文显式干预数值的对应关系，更直接控制了局部信息差异。这是具体设计上的区别，仍不是“此前无人研究反馈真实性”的依据。[When Benchmarks Talk 正式论文](https://aclanthology.org/2025.findings-acl.1267/)

两项更新近邻进一步限制宽泛的新颖性表述。LLaMEA-SAGE 用代码结构与 SHAP 信息指导变异；VISTA 将假设生成和提示重写分开，并验证假设。前者说明可解释结构反馈已用于代码演化，后者说明“诊断为何有效”已经进入反思式优化研究。本文的潜在增量必须落实到互惠中的可检验行为，而不是单纯添加一段诊断。SAGE 此处引用预印本；VISTA 的比较仅采用已核实摘要层面的概括，不将特定坏初始提示上的退化推广为 GEPA 普遍失败。[LLaMEA-SAGE](https://arxiv.org/abs/2601.21511)，[VISTA](https://aclanthology.org/2026.acl-srw.8/)

## 4. 评价与归因：为什么“系统有效”与“单步反馈有效”可以同时成立或不成立

| 工作 | 对评价的贡献 | 对本文的约束 |
| --- | --- | --- |
| Chong、Tiño 与 Yao，2008 | 在共同演化、包括 IPD 中区分内部适应度和指定对手分布上的泛化 | 训练收益不保证泛化是直接先例，不是本文首次发现 |
| Huang 等，2023 | 分析无外部反馈的自我纠错，指出基于真值的停止／选择可改变表面收益 | 需要区分候选生成质量、选择及停止的贡献；不能推广为所有新模型都无法纠错 |
| Oved 等，2026 | 研究固定预算在更多种子与更多迭代之间的分配及方法排名变化 | 公平预算与宽深对照是必要条件，不能作为本文独立创新 |

Chong 等直接以对手分布定义泛化，这使得本文“训练选优后默认测试优势缩小”的结果更像既有问题在 LLM 修改中的一个具体实例，而非全新现象。Huang 等从另一任务类型说明，整体收益可能包含选择或停止带来的贡献；本文新增的 best-of-two 接受分析回应了这一问题，但它是事后分析且不是多代进化。[共同演化泛化原文](https://www.cs.bham.ac.uk/~pxt/PAPERS/ieee_tec07.pdf)，[自我纠错原文](https://arxiv.org/html/2310.01798v1)

Oved 等研究预算分配，并未证明独立采样普遍胜过演化。我们的旧 45 条轨迹与请求数匹配对照，也只能说明特定预算下没有检出稳定优势，不能与其结果合并成“演化无效”的结论。作为正向对照，FunSearch 展示了带执行评价器的程序搜索能够取得有效解；它与我们当前的局部反馈结果可以同时成立。[Evolution or Illusion?](https://arxiv.org/abs/2609.19799)，[FunSearch](https://www.nature.com/articles/s41586-023-06924-6)

## 5. 当前研究实际多回答了什么

### 5.1 研究对象从总体轨迹缩小到显式反馈通道

当前第一阶段不是新的多代演化算法。它从五个已有初始种群中固定 15 个父代，在相同代码上下文下比较四种生成端信息，每组 30 次请求。真实、错配、隐藏成绩的对照用于检查正确数值的边际价值；诊断组提供了额外行为统计。训练父代的选择仍隐含成功信息，隐藏组并非完全无反馈；全代码也可能替代部分成绩信息。

与报告最终冠军的完整演化研究相比，这种设计更直接观察生成器产出的候选分布；与只观察候选分布相比，事后训练接受分析又检查了差异能否经过选优保留下来。两个估计量不同，必须并列，而不能挑一个有利结果称为最终方法收益。

### 5.2 结果与前人结论的对应

| 本文结果 | 与前人关系 | 当前证据允许的解释 |
| --- | --- | --- |
| true−shuffled 默认每轮收益 −0.00152，95% 区间 [−0.10490, 0.09825] | 限制“显示正确成绩必然改善生成”的一般化解释；不是对 Li、CSRO 整体搜索收益的反驳 | 该条件下未检出稳定增量价值；未证明无效、等效或模型忽视分数 |
| true−hidden 为 −0.00573，区间 [−0.12559, 0.11859] | 与反馈效用依赖任务和上下文的文献相容 | 不能认为增加一张真实成绩表自动提高一次改写质量 |
| diagnostic−true 为 +0.15596，五个种子同方向，精确 p=0.0625 | 与 Self-Refine、GEPA 等具体反馈路线方向相符 | 有复验价值的相对改善，尚非强确认性结论 |
| diagnostic 子代相对父代仍为 −0.10172 | 与“变异可产生大量较差候选、搜索仍靠选择”兼容 | 主要是缓解退化，不是已证明父代提升 |
| 训练选优后 diagnostic−true 为 +0.02772，区间 [−0.03460, 0.09003] | 与选择和泛化需要分离评价的文献相符 | 原始提案的相对优势尚未明确转化为最终可用优势 |

这里还需校准一句容易过度概括的话：“累计收益能筛选策略，但不能指导修改”。本研究没有比较真实收益选择与随机选择，因而前半句不是本实验的新发现；后半句也超出了五种群、区间较宽的零结果。更准确的结论是：**在当前固定父代和完整代码上下文下，正确聚合成绩的增量价值尚不明确；行为诊断主要呈现减轻修改退化的信号，选优后测试优势仍需验证。**

## 6. 贡献边界与最值得补的证据

不能作为独立创新的内容包括：提示风格影响合作；LLM 生成策略代码；迭代评分与精英保留；详细反馈或解释性反馈帮助修改；训练适应度与泛化不同；预算匹配和独立采样对照。

当前可以明确描述的工作是：对 IPD 策略修改中的成绩对应关系进行配对干预，并同时报告原始提案、执行失败、行为响应和训练接受后的测试表现。这是一项具体的实证设计及初步发现，不是已经确立的新原理，也不是仅凭一个正向差值即可成立的新算法。

要使故事更有区分度，优先补三类证据。第一，在真实诊断、错配诊断和等长度无关诊断之间做控制，检验作用是否来自与父代失败相匹配的行为证据。第二，定义特定行为预测，例如一次误背叛后恢复合作的改动，是否只在相应报复环境中带来可预测收益；新增独立探针，避免在用于反馈的探针上自证。第三，增加独立种群后再做多代验证，区分生成阶段的改善、训练选择的偏好和对未见对手的收益，避免将一步结果外推为长期演化结论。

如果这些实验成立，论文才能进一步回答“什么诊断在什么互惠环境中有用，为什么提案改善有时被训练选择抵消”。若不成立，应保留受控负结果，而不是继续将故事包装成成功的反馈归因方法。

## 7. 回答三个研究问题

RQ1：直接互惠文献分别证明或展示了策略能力、合作条件和完整演化系统的行为，不能全部视作生成端成绩利用的实验证据。本文当前检验的是局部的显式反馈通道。

RQ2：反馈具体性、分组成绩、轨迹反思、反馈真实性和结构诊断都有先例。本文的可区分部分在于相同父代与代码条件下的数值对应关系干预，以及提案与训练接受后收益的并列评价；首次性尚未建立。

RQ3：当前结果主要与既有反馈和泛化研究相符，同时限制了将整体演化成功归因于正确数值反馈的推断。它没有推翻前人的多代实验，也尚未证明诊断能带来稳定的父代提升或长期演化收益。

## 8. 第二阶段完成后，当前工作的定位如何变化

20 个新种群、60 个固定父代和五组 600 次修改的结果，没有支持匹配诊断的收益优势：准确−错配为每轮 −0.00031，95% 区间 [−0.01001, 0.00950]，p=0.95162。准确−总分为 −0.00149，区间 [−0.01321, 0.01048]。S3 验证选择后，准确组对父代提高 0.02715（Holm p=0.000687），但准确−总分为 −0.00488，区间跨零；预定选择交互也未获得支持。独立行为中，准确组减少持续背叛下的单方面合作，却延长合作恢复时间。完整表格与审计见统一草稿第 6.7–6.11 节。

这使本文从“诊断可能减轻退化”的初步正向信号，转为**对诊断针对性及其收益归因的受控边界检验**。与 Self-Refine、LLaMEA、GEPA 的关系仍不是直接反驳：这些工作中的丰富反馈或整体修订流程获得收益，并不等于它们都声称 IPD 数值诊断必须与特定父代匹配。本研究测试的是具体格式、单一模型和固定对手分布，未否定其他反馈形式。

与 Li/Wang、CSRO 等整体搜索研究相比，新增证据强调：候选经选择后变强，不能单凭这一点推断模型利用了正确的个体诊断。与共同演化泛化研究相比，S3 的结果仍是已知“选择分布影响输出”问题中的一个具体实例，不能单独作为新原理。本文可区分的内容在于把准确、错配、背景、合作建议与同池选择并列控制，并用独立双向行为检查限制修复解释。当前尚未建立首次性，也没有新的多代算法成果。

第二阶段更换了诊断探针及测试面板，所以其准确−总分结果与第一阶段 +0.15596 的差异不能归因为某一个因素，也不是相同协议下的精确复验失败。按照生成前冻结的门槛，本批次停止多代扩展，保留负结果及单模型、格式、分布和精度边界。

## 参考文献与核验说明

1. Siwei Li, Xin Wang. 2026. *Code Driven Game Theoretic Evolution of LLM Agents as Holistic Strategy Generators*. ICLR AIMS Workshop short paper. [论文](https://openreview.net/pdf?id=VBpIRGHktc)。使用本地九页原文；公开入口有浏览器验证限制。
2. Richard Willis, Yali Du, Joel Z. Leibo, Michael Luck. 2025. *Will Systems of LLM Agents Cooperate: An Investigation into a Social Dilemma*. [arXiv:2501.16173v1](https://arxiv.org/abs/2501.16173v1)。不与三作者、题名含 Lead to Cooperation 的 AAMAS 短稿混写。
3. Swadesh Sistla, Max Kleiman-Weiner. 2025. *Evaluating LLMs in Open-Source Games*. NeurIPS. [arXiv:2512.00371](https://arxiv.org/abs/2512.00371)。
4. Saptarshi Pal et al. 2026. *Large language models instantiate evolutionarily robust strategies of cooperation*. PNAS Nexus 5(6), pgag210. [DOI](https://doi.org/10.1093/pnasnexus/pgag210)。
5. Aman Madaan et al. 2023. *Self-Refine: Iterative Refinement with Self-Feedback*. NeurIPS. [arXiv:2303.17651](https://arxiv.org/abs/2303.17651)。
6. Noah Shinn et al. 2023. *Reflexion: Language Agents with Verbal Reinforcement Learning*. [arXiv:2303.11366](https://arxiv.org/abs/2303.11366)。
7. Niki van Stein, Thomas Bäck. 2024. *LLaMEA: A Large Language Model Evolutionary Algorithm for Automatically Generating Metaheuristics*. [arXiv:2405.20132](https://arxiv.org/abs/2405.20132)。年份按初始预印本，方法核对 v3。
8. Daniel Hennes, Zun Li, John Schultz, Marc Lanctot. 2026. *Code-Space Response Oracles: Generating Interpretable Multi-Agent Policies with Large Language Models*. [arXiv:2603.10098v1](https://arxiv.org/abs/2603.10098v1)。
9. Lakshya A Agrawal et al. 2025/2026. *GEPA: Reflective Prompt Evolution Can Outperform Reinforcement Learning*. ICLR 2026；初稿 2025，本文核对 v2。 [arXiv:2507.19457](https://arxiv.org/abs/2507.19457)。
10. Jane Pan et al. 2025. *When Benchmarks Talk: Re-Evaluating Code LLMs with Interactive Feedback*. Findings of ACL, 24672–24700. [正式论文](https://aclanthology.org/2025.findings-acl.1267/)。
11. Siang Yew Chong, Peter Tiño, Xin Yao. 2008. *Measuring Generalization Performance in Coevolutionary Learning*. IEEE Transactions on Evolutionary Computation 12(4), 479–505. [DOI](https://doi.org/10.1109/TEVC.2007.907593)。
12. Jie Huang et al. 2023. *Large Language Models Cannot Self-Correct Reasoning Yet*. [arXiv:2310.01798](https://arxiv.org/abs/2310.01798)。本次引用限于核对的早期版本与任务条件。
13. Tal Oved, Roi Pony, Oshri Naparstek, Udi Barzelay. 2026. *Evolution or Illusion? Rethinking Evaluation in LLM Evolutionary Search*. [arXiv:2609.19799](https://arxiv.org/abs/2609.19799)。近期预印本，不能当作定论。
14. Bernardino Romera-Paredes et al. *Mathematical discoveries from program search with large language models*. Nature，2023 在线发表、2024 卷期。 [原文](https://www.nature.com/articles/s41586-023-06924-6)。
15. Niki van Stein, Anna V. Kononova, Lars Kotthoff, Thomas Bäck. 2026. *LLaMEA-SAGE: Guiding Automated Algorithm Design with Structural Feedback from Explainable AI*. [arXiv:2601.21511](https://arxiv.org/abs/2601.21511)。只标预印本，不根据占位 DOI 推定正式会议发表。
16. Shiyan Liu et al. 2026. *Reflection in the Dark: Exposing and Escaping the Black Box in Reflective Prompt Optimization*. ACL Student Research Workshop, 76–109. [正式页面](https://aclanthology.org/2026.acl-srw.8/)。

核验采用独立检索视角与主线程原文复核。VISTA 的独立核验限于正式页面和摘要；Li 与 Wang 的主要方法证据来自已归档本地全文。OpenReview 的另一个检索候选因验证页无法核实，未采用。检索不是系统综述的穷尽性证明；没有以“未找到”支持首次性。
