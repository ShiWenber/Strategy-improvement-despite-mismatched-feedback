# 引用补充与核查记录（2026-09-30）

2026-09-30 构建路径补充核查：中文根目录旧 `main.bbl` 只有21条，17:02单次XeLaTeX编译沿用该文件，导致根 `main.pdf` 显示21条并出现14次未定义引用。已修复 `paper_zh_direct/tools/build.ps1` 的根目录产物同步，重新运行两稿Tectonic完整构建。当前中英文主稿均34条、编号相同、无未定义引用、无孤儿条目；中文根 `main.pdf` 与稳定交付PDF均已更新。本次未改任何tex/bib；详情和验收记录见 `../../tmp/citation_build_sync_20260930/README.md` 及同目录 `validation.json`。

按作者批准方案实施；未加入备选、元数据不完整条目或未批准的统计文献。

| 检查 | 结果 |
|---|---|
| 新增bib条目 | 11 |
| 启用原有孤儿条目 | eoh2024、huang2023，共2条 |
| 正文新增被引文献 | 13；原21篇增加为34篇 |
| 两稿bib条目 | 各34，内容逐字节相同 |
| 两主稿bib孤儿条目 | 0 |
| 两主稿undefined citation | 0 |
| 实际编译编号 | 两稿34条全部一致 |
| 原有条目保护 | 原23条全部逐字节保留，含原有21条被引文献 |
| 结论与原句保护 | 独立审计确认去除cite后的改动仅有审批新增句，无原字删除或替换；结论原样 |
| Abstract与Results | 原样、零引用 |
| Tectonic | 0.16.9；English supplement→main→supplement与Chinese main均退出0 |
| BibTeX / IEEEtran.bst | 两主稿均正常生成34条，blg无错误或警告 |
| 排版警告 | 字体形状回退；中文既有method_details段落3条Underfull hbox；无Overfull |
| 文献页视觉检查 | 通过：英文11–12页、中文8–9页；无溢出、重叠、缺字或格式异常 |

编号检查以两篇main为范围。英文补充材料是既有独立文档，其3篇参考文献单独编号；共享数据库的31条未用记录不进入补充材料文献表。主文及整个稿件包的bib孤儿均为0。

## 新增引用的精确位置

| 文献key／编译编号 | 目标文件:行号 | 引用理由 |
|---|---|---|
| `eoh2024` [7] | [paper_interface_focus/related_work.tex:5](C:\Users\shiwenbo\.mavis\agents\mavis\workspace\llm-reputation-paper\llm-reputation\.worktrees\direct-reciprocity\paper_interface_focus\sections\related_work.tex:5)<br>[paper_interface_focus/methods.tex:5](C:\Users\shiwenbo\.mavis\agents\mavis\workspace\llm-reputation-paper\llm-reputation\.worktrees\direct-reciprocity\paper_interface_focus\sections\methods.tex:5)<br>[paper_zh_direct/related_work.tex:5](C:\Users\shiwenbo\.mavis\agents\mavis\workspace\llm-reputation-paper\llm-reputation\.worktrees\direct-reciprocity\paper_zh_direct\sections\related_work.tex:5)<br>[paper_zh_direct/methods.tex:5](C:\Users\shiwenbo\.mavis\agents\mavis\workspace\llm-reputation-paper\llm-reputation\.worktrees\direct-reciprocity\paper_zh_direct\sections\methods.tex:5) | 程序变体生成与执行评价的总体架构。 |
| `bachrach2025` [8] | [paper_interface_focus/related_work.tex:5](C:\Users\shiwenbo\.mavis\agents\mavis\workspace\llm-reputation-paper\llm-reputation\.worktrees\direct-reciprocity\paper_interface_focus\sections\related_work.tex:5)<br>[paper_zh_direct/related_work.tex:5](C:\Users\shiwenbo\.mavis\agents\mavis\workspace\llm-reputation-paper\llm-reputation\.worktrees\direct-reciprocity\paper_zh_direct\sections\related_work.tex:5) | 代码生成与自博弈相结合的策略搜索。 |
| `huang2023` [18] | [paper_interface_focus/related_work.tex:10](C:\Users\shiwenbo\.mavis\agents\mavis\workspace\llm-reputation-paper\llm-reputation\.worktrees\direct-reciprocity\paper_interface_focus\sections\related_work.tex:10)<br>[paper_zh_direct/related_work.tex:10](C:\Users\shiwenbo\.mavis\agents\mavis\workspace\llm-reputation-paper\llm-reputation\.worktrees\direct-reciprocity\paper_zh_direct\sections\related_work.tex:10) | 无外部反馈的推理自我纠正局限。 |
| `akata2025` [21] | [paper_interface_focus/related_work.tex:17](C:\Users\shiwenbo\.mavis\agents\mavis\workspace\llm-reputation-paper\llm-reputation\.worktrees\direct-reciprocity\paper_interface_focus\sections\related_work.tex:17)<br>[paper_zh_direct/related_work.tex:17](C:\Users\shiwenbo\.mavis\agents\mavis\workspace\llm-reputation-paper\llm-reputation\.worktrees\direct-reciprocity\paper_zh_direct\sections\related_work.tex:17) | 有限重复博弈中的LLM合作与协调行为。 |
| `fan2024` [22] | [paper_interface_focus/related_work.tex:17](C:\Users\shiwenbo\.mavis\agents\mavis\workspace\llm-reputation-paper\llm-reputation\.worktrees\direct-reciprocity\paper_interface_focus\sections\related_work.tex:17)<br>[paper_zh_direct/related_work.tex:17](C:\Users\shiwenbo\.mavis\agents\mavis\workspace\llm-reputation-paper\llm-reputation\.worktrees\direct-reciprocity\paper_zh_direct\sections\related_work.tex:17) | 通过欲望、信念和行动评估LLM博弈理性。 |
| `vallinder2024` [23] | [paper_interface_focus/related_work.tex:19](C:\Users\shiwenbo\.mavis\agents\mavis\workspace\llm-reputation-paper\llm-reputation\.worktrees\direct-reciprocity\paper_interface_focus\sections\related_work.tex:19)<br>[paper_zh_direct/related_work.tex:19](C:\Users\shiwenbo\.mavis\agents\mavis\workspace\llm-reputation-paper\llm-reputation\.worktrees\direct-reciprocity\paper_zh_direct\sections\related_work.tex:19) | 多代LLM智能体的间接互惠文化演化。 |
| `horibe2026` [24] | [paper_interface_focus/related_work.tex:19](C:\Users\shiwenbo\.mavis\agents\mavis\workspace\llm-reputation-paper\llm-reputation\.worktrees\direct-reciprocity\paper_interface_focus\sections\related_work.tex:19)<br>[paper_zh_direct/related_work.tex:19](C:\Users\shiwenbo\.mavis\agents\mavis\workspace\llm-reputation-paper\llm-reputation\.worktrees\direct-reciprocity\paper_zh_direct\sections\related_work.tex:19) | 间接互惠合作抵抗搭便车入侵的稳健性。 |
| `ren2026` [25] | [paper_interface_focus/related_work.tex:19](C:\Users\shiwenbo\.mavis\agents\mavis\workspace\llm-reputation-paper\llm-reputation\.worktrees\direct-reciprocity\paper_interface_focus\sections\related_work.tex:19)<br>[paper_zh_direct/related_work.tex:19](C:\Users\shiwenbo\.mavis\agents\mavis\workspace\llm-reputation-paper\llm-reputation\.worktrees\direct-reciprocity\paper_zh_direct\sections\related_work.tex:19) | 动态声誉与交互网络调整维持合作。 |
| `trivers1971` [26] | [paper_interface_focus/background.tex:5](C:\Users\shiwenbo\.mavis\agents\mavis\workspace\llm-reputation-paper\llm-reputation\.worktrees\direct-reciprocity\paper_interface_focus\sections\background.tex:5)<br>[paper_zh_direct/background.tex:5](C:\Users\shiwenbo\.mavis\agents\mavis\workspace\llm-reputation-paper\llm-reputation\.worktrees\direct-reciprocity\paper_zh_direct\sections\background.tex:5) | 互惠利他的经典理论来源。 |
| `xia2023` [28] | [paper_interface_focus/background.tex:5](C:\Users\shiwenbo\.mavis\agents\mavis\workspace\llm-reputation-paper\llm-reputation\.worktrees\direct-reciprocity\paper_interface_focus\sections\background.tex:5)<br>[paper_zh_direct/background.tex:5](C:\Users\shiwenbo\.mavis\agents\mavis\workspace\llm-reputation-paper\llm-reputation\.worktrees\direct-reciprocity\paper_zh_direct\sections\background.tex:5) | 直接、间接及声誉互惠机制的背景区分。 |
| `nowak1992` [30] | [paper_interface_focus/background.tex:7](C:\Users\shiwenbo\.mavis\agents\mavis\workspace\llm-reputation-paper\llm-reputation\.worktrees\direct-reciprocity\paper_interface_focus\sections\background.tex:7)<br>[paper_zh_direct/background.tex:7](C:\Users\shiwenbo\.mavis\agents\mavis\workspace\llm-reputation-paper\llm-reputation\.worktrees\direct-reciprocity\paper_zh_direct\sections\background.tex:7) | 异质群体中的慷慨以牙还牙。 |
| `nowak1993` [31] | [paper_interface_focus/background.tex:7](C:\Users\shiwenbo\.mavis\agents\mavis\workspace\llm-reputation-paper\llm-reputation\.worktrees\direct-reciprocity\paper_interface_focus\sections\background.tex:7)<br>[paper_zh_direct/background.tex:7](C:\Users\shiwenbo\.mavis\agents\mavis\workspace\llm-reputation-paper\llm-reputation\.worktrees\direct-reciprocity\paper_zh_direct\sections\background.tex:7) | WSLS纠正偶然错误。 |
| `fudenberg2012` [32] | [paper_interface_focus/discussion.tex:23](C:\Users\shiwenbo\.mavis\agents\mavis\workspace\llm-reputation-paper\llm-reputation\.worktrees\direct-reciprocity\paper_interface_focus\sections\discussion.tex:23)<br>[paper_zh_direct/discussion.tex:23](C:\Users\shiwenbo\.mavis\agents\mavis\workspace\llm-reputation-paper\llm-reputation\.worktrees\direct-reciprocity\paper_zh_direct\sections\discussion.tex:23) | 防御与惩罚后恢复合作的解释框架。 |

## 核验来源

| key | 来源与版本 | 可验证记录 |
|---|---|---|
| `eoh2024` | 现有条目；ICML/PMLR 2024，作者指定外部标识已批准 | [记录](https://proceedings.mlr.press/v235/liu24bs.html) |
| `bachrach2025` | 指定外部；IJCAI正式记录，DOI已批准 | [记录](https://www.ijcai.org/proceedings/2025/1249) |
| `huang2023` | 现有条目；作者指定arXiv版本已批准 | [记录](https://arxiv.org/abs/2310.01798v1) |
| `akata2025` | Zotero B35AZSSX；正式卷页由出版商补核 | [记录](https://www.nature.com/articles/s41562-025-02172-y) |
| `fan2024` | Zotero NRNN9X68 | [记录](https://ojs.aaai.org/index.php/AAAI/article/view/29751) |
| `vallinder2024` | Zotero 8VVLUJQB；DOI已从arXiv正式页面核实 | [记录](https://arxiv.org/abs/2412.10270v1) |
| `horibe2026` | Zotero 5FD353I3 | [记录](https://arxiv.org/abs/2608.04507v1) |
| `ren2026` | Zotero 5NZAWR9B；2026年v3，不补未核会议信息 | [记录](https://arxiv.org/abs/2505.05029v3) |
| `trivers1971` | Zotero CT9S85PU；内容由出版商摘要核查 | [记录](https://www.journals.uchicago.edu/doi/10.1086/406755) |
| `xia2023` | Zotero T372TRGV | [记录](https://www.sciencedirect.com/science/article/pii/S1571064523000489) |
| `nowak1992` | 指定外部；DOI已批准 | [记录](https://www.nature.com/articles/355250a0) |
| `nowak1993` | 指定外部；DOI已批准 | [记录](https://www.nature.com/articles/364056a0) |
| `fudenberg2012` | 指定外部；DOI已批准 | [记录](https://www.aeaweb.org/articles?id=10.1257/aer.102.2.720) |

库内新增条目均在生成bib之前执行MCP搜索与get_item_details完整核查；外部候选已呈示DOI/arXiv标识并获得作者批准。Akata正式卷页为9:1380–1390；Bachrach按正式IJCAI作者表保留全部14名作者。

## 修改文件

- [paper_interface_focus/sections/related_work.tex](C:\Users\shiwenbo\.mavis\agents\mavis\workspace\llm-reputation-paper\llm-reputation\.worktrees\direct-reciprocity\paper_interface_focus\sections\related_work.tex)
- [paper_interface_focus/sections/background.tex](C:\Users\shiwenbo\.mavis\agents\mavis\workspace\llm-reputation-paper\llm-reputation\.worktrees\direct-reciprocity\paper_interface_focus\sections\background.tex)
- [paper_interface_focus/sections/methods.tex](C:\Users\shiwenbo\.mavis\agents\mavis\workspace\llm-reputation-paper\llm-reputation\.worktrees\direct-reciprocity\paper_interface_focus\sections\methods.tex)
- [paper_interface_focus/sections/discussion.tex](C:\Users\shiwenbo\.mavis\agents\mavis\workspace\llm-reputation-paper\llm-reputation\.worktrees\direct-reciprocity\paper_interface_focus\sections\discussion.tex)
- [paper_zh_direct/sections/related_work.tex](C:\Users\shiwenbo\.mavis\agents\mavis\workspace\llm-reputation-paper\llm-reputation\.worktrees\direct-reciprocity\paper_zh_direct\sections\related_work.tex)
- [paper_zh_direct/sections/background.tex](C:\Users\shiwenbo\.mavis\agents\mavis\workspace\llm-reputation-paper\llm-reputation\.worktrees\direct-reciprocity\paper_zh_direct\sections\background.tex)
- [paper_zh_direct/sections/methods.tex](C:\Users\shiwenbo\.mavis\agents\mavis\workspace\llm-reputation-paper\llm-reputation\.worktrees\direct-reciprocity\paper_zh_direct\sections\methods.tex)
- [paper_zh_direct/sections/discussion.tex](C:\Users\shiwenbo\.mavis\agents\mavis\workspace\llm-reputation-paper\llm-reputation\.worktrees\direct-reciprocity\paper_zh_direct\sections\discussion.tex)
- [paper_interface_focus/references.bib](C:\Users\shiwenbo\.mavis\agents\mavis\workspace\llm-reputation-paper\llm-reputation\.worktrees\direct-reciprocity\paper_interface_focus\references.bib)
- [paper_zh_direct/references.bib](C:\Users\shiwenbo\.mavis\agents\mavis\workspace\llm-reputation-paper\llm-reputation\.worktrees\direct-reciprocity\paper_zh_direct\references.bib)

## 编译与审计证据

- [机器核查记录](C:\Users\shiwenbo\.mavis\agents\mavis\workspace\llm-reputation-paper\llm-reputation\.worktrees\direct-reciprocity\tmp\citation_update_20260930\manifest.json)
- [英文编译日志](C:\Users\shiwenbo\.mavis\agents\mavis\workspace\llm-reputation-paper\llm-reputation\.worktrees\direct-reciprocity\tmp\citation_update_20260930\english_build_console.txt)
- [中文编译日志](C:\Users\shiwenbo\.mavis\agents\mavis\workspace\llm-reputation-paper\llm-reputation\.worktrees\direct-reciprocity\tmp\citation_update_20260930\chinese_build_console.txt)
- 修改前快照：`C:\Users\shiwenbo\.mavis\agents\mavis\workspace\llm-reputation-paper\llm-reputation\.worktrees\direct-reciprocity\tmp\citation_update_20260930\before`

未补齐缺口：统计方法原始来源；Coopeval与survey母条目缺元数据；未将交替互动、随机博弈、WSLL或ZD几何强行挂到不匹配句子。

审计范围：原文保留检查以本次修改前快照为基线。独立核查发现，另有Results/Discussion的并行修订已进入该基线；本次引用操作没有引入这些文字删改。
