# Results 三张正文图：面板与制图规格

更新日期：2026-09-30。图内语言按作者本轮补充要求统一为英文。配套文件：[结果写作框架](../../结果部分写作框架_审稿改良版.md)、[约束](../../约束.md)。本文件细化设计，布局草图不含虚构数据；正式三图已于本轮整合至中英文稿，图1原样保留。正式图脚本为 `paper_zh_direct/tools/plot_results_three_figures.py`，核对记录位于 `paper_interface_focus/audit/results_rewrite_20260930/`。

**图 1 保持现有版本（作者确认，2026-09-30）。** 保留现有图 1 的图件、布局、图内文字、颜色、符号、尺寸和现有图注。新版图 1 的设计描述与备案草图已移除；本文件只细化图 2、3 的重排设计。

布局预览：[图 2](figures/results_3fig_design_20260930/figure2_layout.png)、[图 3](figures/results_3fig_design_20260930/figure3_layout.png)。同目录保留可编辑 SVG 和生成脚本；预览仅显示面板内容与排布，不是正式数据图。

## 1. 三图覆盖范围

正文总计三张图，方法图计入。压缩方式是合并科学问题相邻的面板，原四图的核心证据保留在正文，完整细节由补充材料承接。

| 现有内容 | 新位置 | 处理方式 |
| --- | --- | --- |
| 原图 1：现有方法图 | 正文图 1，原样保留 | 保持现有图件和现有图注，不重新设计 |
| 原图 2：错配下收益、准确匹配的原始候选比较 | 图 2a,b | 扩为四个模型×配置单元；种群配对散点移补充 |
| 原图 3：固定池 Raw→S3 | 图 2c | 四个等宽小分面；保留种群配对证据 |
| 原图 3：候选分布、采用去向、完整选择器比较 | 补充图表 | 仍可复核，正文第 2 节保留关键数值与引用 |
| 原图 4：分对手 Raw/S3 收益及独立行为 | 图 3a–d | OFF/ON全部进入正文；不再以 OFF 面板代表整个研究 |
| 新增考虑：Qwen3.8-Flash | 图 2a–c及补充总表 | 报告匹配与同池选择均覆盖第二模型 |
| 新增考虑：mismatched-distances | 正文第 4 节＋补充距离图表 | 回应“多数供体在已测报告上近同”的解释，不增加正文图数量 |
| 新增考虑：JEV 错配识别 | 正文第 4 节＋补充判读表、轨迹实例 | 分开报告察觉与弃用；只标 DeepSeek ON 的证据范围 |

## 2. 统一视觉与统计规则

以下制图规则适用于待重排的图 2、3；图 1 沿用现有版本，不据此调整。

- 图 2、3 以全宽 **175 mm** 设计，高各约 125–140 mm。尺寸是排版起点，正式制图后按实际字号与间距调整，不能以堆叠大量面板规避“三张中幅图”。
- 白底、细灰网格、无渐变或阴影；面板标签 a/b/c/d 位于左上角。无整图结论式大标题，无显著性星号。
- 印刷尺寸下轴标题和面板标题约 9–10 pt，刻度及图例约 8.5–9 pt，任何必要文字不低于 8 pt。若拥挤，先删冗余标签或移细节入补充材料。
- Accurate 使用蓝色 `#0072B2`，Mismatched 使用橙色 `#D55E00`，同时配圆/方形标记；不为统一此编码而改动现有方法图。
- Raw/S3 在图 2 用空心灰圆/实心深灰方形；OFF/ON主要依靠配置标题、分面及行标签辨认。图 3 行为面板用 OFF 实线圆点、ON 虚线三角，均为深灰，避免把模式颜色误读成报告条件颜色。
- 四单元顺序固定：DeepSeek OFF、DeepSeek ON、Qwen OFF、Qwen ON。不按收益大小排序；OFF/ON占用相同面积、相同字体和相同类型的标记。
- 点区间图直接读取已有 mean/ci95。误差条的对象在图注交代；不得从两臂区间相减获得配对差区间。候选数和池数不能替代 **20 个种群**的推断单位。
- 同一指标的配置面板共用数值尺度。不同指标分开轴，不采用双纵轴。零线必须覆盖收益增量与匹配差图；不画未经定义的等效区间。
- 四单元共用原始种群、父代和既有 H；不按 80 个独立种群合并估计，也不通过并排显示推断孤立的思考开关效应或模型能力排名。
- 图 2c 与图 3c,d 的阶段连线表达同一批父代/候选池的比较。图内不使用时间箭头、世代编号或循环演化箭头。

## 3. 图 2：报告匹配与同池采用

**读者要看懂：** 错配下选择输出仍有平均收益；准确匹配的 Raw 增量价值没有稳定正向证据；同一池中的候选怎样采用，也改变最终表现。

### 布局

上排 a/b 各约半宽、高约 55–60 mm，四行配置对齐；下排 c 高约 50–55 mm，内部四个等宽分面。上下排间距 7–9 mm，避免上排横轴文字侵入下排标题。只在上排 a 左侧保留完整模型×配置行名，b 复用相同位置；b 若省行名必须有清楚的配置对齐，不能让读者猜测。

### 2a：Mismatched: gains over parents

- 每行 Raw 空心圆与 S3 实心方形，纵向微错开；各有既有 95% CI，不连接两个均值。
- 横轴：**Payoff gain per round vs parent**。建议初始范围 −0.02～+0.20，正式制图须包含所有现有区间；以零线标父代，不另画零高柱。
- 只取 Mismatched。无需再画 Accurate 两阶段均值，因为 2b 直接回答匹配问题。
- 小图例只解释 Raw/S3。不要把 S3 相对父代的收益叫作 S3−Raw 选择增量。

### 2b：Correct report matching: Raw Accurate − Mismatched

- 四行单点与既有配对 95% CI，横轴：**Raw Accurate − Mismatched (payoff per round)**。
- 建议范围 −0.03～+0.035；保留零线，正方向只用轴旁短标签“Accurate higher”解释，不画绿色优势区。
- 图注说明这些区间来自种群配对差。DeepSeek OFF 的原论文预定地位在图注/统计说明中交代，不能将该行放大或将其他行称为不可靠。
- 四区间跨零是当前证据模式，不使用“equivalent”标签或结论箭头。

### 2c：Same-pool adoption: five conditions averaged

- 四个小分面，分别标题“DeepSeek / OFF”“DeepSeek / ON”“Qwen / OFF”“Qwen / ON”。每面只保留 Raw、S3 两个横轴刻度。
- 每条浅灰细线对应一个种群，连接五条件等权汇总的 Raw 与 S3；共 20 条/分面。均值以较大空心圆/实心方形或短横线突出，不把各候选当作独立散点。
- 四面共用纵轴 **Payoff gain per round vs parent**，初始范围 −0.075～+0.30；只在最左面显示纵轴标签及刻度。横向布置的四格必须等宽。
- 这是现有种群向量的汇总。**不新增差值 CI、不新增检验**。两阶段均值可以标注两到三位小数，完整精度在补充表中保留。
- Raw 对应同池随机采用的期望，S3 是按 V 采用候选或保留父代。每条件仍在自己的池里决策，不跨五条件合池选优。

### 四单元核对表

均为相对父代的每轮收益增量。c 的 Qwen 数值仅由五臂现有均值/种群向量等权汇总，无新区间。

| 单元 | 2a M Raw | 2a M S3 | 2b Raw A−M [95% CI] | 2c 五条件 Raw→S3 |
| --- | ---: | ---: | --- | --- |
| DeepSeek OFF | +0.00263 | +0.02354 | −0.00031 [−0.01001,+0.00950] | +0.00700→+0.02996 |
| DeepSeek ON | +0.06585 | +0.10701 | +0.00613 [−0.01311,+0.02463] | +0.06024→+0.09197 |
| Qwen OFF | +0.02131 | +0.03939 | −0.00171 [−0.01411,+0.00923] | +0.02027→+0.04095 |
| Qwen ON | +0.11044 | +0.15107 | +0.00611 [−0.01621,+0.02794] | +0.08610→+0.13261 |

### 数据入口

| 面板 | 文件与读取位置 | 处理边界 |
| --- | --- | --- |
| 2a,b | [cross_model_mainline_data.json](../../results/model_comparison_20260928/cross_model_mainline_data.json)：statistics 下四配置的 raw_mismatched、s3_mismatched、raw_accurate_minus_mismatched | 直接读取 mean、ci95；不要调用会重新 bootstrap 的旧绘图函数 |
| 2c DeepSeek | [population_summary.json](../../results/reciprocity_population_visuals_20260924/population_summary.json)：configurations 下各配置 raw_seed_means、s3_seed_means、seed_ids | 缓存标题含旧预算字样，图上仅写 OFF/ON；交叉核对各臂冻结向量 |
| 2c Qwen | [OFF ANALYSIS.json](../../results/qwen3_8/off/ANALYSIS.json)、[ON ANALYSIS.json](../../results/qwen3_8/on/ANALYSIS.json)：result.raw[arm].metrics['default/score'].seed_values 与 result.selected['S3/'+arm].metrics.default.seed_values | 按各 manifest 的 seeds 对齐；逐种群对五臂等权平均；每臂均为 20 个值 |

**建议中文图注：** 报告匹配与同池采用。(a) 四模型×配置单元在 Mismatched 下的 Raw 与 S3 相对父代收益，点与线为均值及既有 95% 种群自助区间。(b) Raw Accurate−Mismatched 的种群配对差及区间；DeepSeek OFF 为原论文预定核心比较。(c) 五条件在种群内等权汇总的 Raw 与 S3，每条细线连接同一种群，突出标记为均值。各条件保持独立候选池；Raw 是随机采用的期望，S3 使用 V 选择。四单元共用 20 个种群及父代，Qwen 为后续模型检验。

**English caption draft:** Report matching and same-pool adoption. (a) Mean payoff gains over parents for Mismatched raw candidates and S3 outputs, with existing 95% population-bootstrap intervals. (b) Population-paired Raw Accurate−Mismatched contrasts and intervals; the DeepSeek OFF contrast was the original prespecified core comparison. (c) Raw and S3 gains averaged equally across the five conditions within each population. Thin lines join paired population means; larger marks show overall means. Each condition retains its own candidate pools. Raw is the expected payoff of random adoption, whereas S3 selects using V. The four model–configuration cells share 20 populations and their parents; Qwen is a subsequent model check.

## 4. 图 3：分对手收益与独立行为

**读者要看懂：** 总收益掩盖对手类别间的得失；行为的平均路径也因配置不同。此图仅基于 DeepSeek，不暗示 Qwen 已有同类行为复现。

### 布局与范围标签

四面板 2×2。上排 a/b 较高，约 60–65 mm；下排 c/d 约 45–50 mm。上排窄标题带写 **H payoff · Accurate / Mismatched · DeepSeek**；下排写 **F′ behaviour · Five conditions averaged · DeepSeek**。这两条标签比装饰性的整图标题更有用，能直接防止条件范围混淆。

### 3a,b：Raw / S3 的对手家族收益

- a 为 Raw，b 为 S3；两个面板共用横轴尺度，均表示相对父代的每轮 H 收益。
- 纵向四家族，固定顺序 Recovery、Exploitation、Random、Memory-one。每一家族内各有 OFF、ON 两行，两行等距；每行有 Accurate/Mismatched 两点及现有区间，共 16 点/面板。
- 蓝圆/橙方形错开，不用四组粗柱来占空间。纵轴同时标家族和 OFF/ON，a/b 中至少一处完整出现标签；不把 ON 作为图例里的“supplementary”。
- 共同横轴初始范围约 **−0.13～+0.23**，覆盖当前所有区间；零线代表父代。区间是各臂**相对父代**增量的探索性未校正 95% 区间，不是家族内 Accurate−Mismatched 的区间。
- 面板不再叠加 A−M 差、显著性星号或个别对手点。完整家族匹配差和 12 个对手的细分结果放补充表。

### 3c：Unilateral cooperation under persistent defection

- 横轴 Parent / Raw / S3；纵轴 **Late unilateral cooperation (%)**。
- OFF 为实线圆点，ON 为虚线三角；同阶段横向微错开。共享父代均值及区间只画一次，标 Shared parent，再连接两个配置的对应结果。
- 画已有绝对行为均值与既有区间，不叠加 40 条种群线；种群细线版本在补充材料保留。
- 正文可报告 OFF 13.0%→7.4%→9.9%、ON 13.0%→13.2%→11.9%。比例乘 100 同时作用于均值和区间。较低只表示面对持续背叛时单方面合作较少，不直接等于总体收益更高。

### 3d：Recovery of mutual cooperation

- 同样的三个阶段与模式线型；纵轴 **Capped recovery time (rounds)**，不与 3c 共用数值轴。
- 均值为 OFF 14.94→16.70→15.12、ON 14.94→13.35→13.96 轮。保留未恢复对局的既定封顶处理，不能改成只分析恢复成功者。
- c/d 纵轴包括零及全部区间，保留适当空白，不在正式读取区间前固定狭窄范围来放大差异。
- 阶段区间并非阶段间配对差区间，不据其重叠与否判显著性；阶段间探索性差表在补充材料保留。

### 数据入口

| 面板 | 文件与读取位置 | 统计口径 |
| --- | --- | --- |
| 3a,b | [opponent ANALYSIS.json](../../results/figure4_opponent_profiles_20260926/ANALYSIS.json)：configs[non_thinking/thinking].summaries[raw/S3][accurate/mismatched][family] | mean、ci95_exploratory_unadjusted；按 20 个种群汇总；家族各 3 个 H 对手 |
| 3c,d | [behaviour ANALYSIS.json](../../results/reciprocity_population_visuals_20260924/behavior/ANALYSIS.json)：configs[non_thinking/thinking].summaries['controlled/pooled/defection_exposure'或'controlled/pooled/recovery_rounds'][parent/raw/S3] | mean、ci95_exploratory；给定合作历史，五条件等权汇总；父代均值与区间跨模式相同 |

原始记录里的行为 split 名虽含 H，本图仍按测量定义写 F′，不能与收益 H 混同。上排与下排不画连接箭头；下排的五条件汇总不能用来解释上排 Accurate−Mismatched 的原因。

**建议中文图注：** 分对手收益与独立行为，均来自 DeepSeek 的 OFF/ON。(a,b) Accurate/Mismatched 原始候选及 S3 输出在四类 H 对手上的相对父代收益；点与线为均值及既有探索性、未校正 95% 种群自助区间。(c,d) 独立行为探针 F′ 中，给定合作历史、五条件等权汇总的单方面合作比例与截尾恢复时间；图示阶段均值及既有区间，共享父代基线仅绘一次。阶段连线表示同一批父代的比较，不表示演化轨迹。H 收益与 F′ 行为具有不同条件范围，不构成彼此的因果解释。

**English caption draft:** Opponent-specific payoff and independent behaviour in DeepSeek OFF and ON. (a,b) Gains over parents for Accurate and Mismatched raw candidates and S3 outputs across four H opponent families. Points and lines show means and existing exploratory, unadjusted 95% population-bootstrap intervals. (c,d) Late unilateral cooperation and capped recovery time measured independently with F′ from a supplied cooperative history, averaging the five conditions equally. Stage means and existing intervals are shown, with the shared parent baseline drawn once. Lines connect comparisons at the same parents rather than an evolutionary trajectory. The payoff and behavioural panels cover different condition sets and do not establish a causal explanation for one another.

## 5. 补充材料必须保留的内容

最终编号按补充材料实际顺序分配，以下是内容标识，不预占 S1/S2 等图号。

| 内容标识 | 必须保留 | 正文如何调用 |
| --- | --- | --- |
| Candidate distribution / adoption destinations | DeepSeek OFF/ON 完整候选分布，零增量回退的口径；300 池的保留/采用后改善/采用后退化；Qwen完整选择表 | Results 第 2 节报告正负候选并存与采用去向，指向该图表 |
| Full selection policies | S1/S2/S3、N/G/U/B，同池配对差及既有区间；不得将路径分解当独立因果贡献 | 第 2 节只保留主要同池结果 |
| Report matching details | 四单元逐种群配对散点、五条件总表、预定与后续检验状态、无效候选回退计数 | 第 1 节辅助对照和第二模型说明 |
| Opponent / behaviour details | 家族 A−M 配对差；空历史、其他行为指标、逐条件与逐种群结果 | 第 3 节，正文图 3 不承载全部指标 |
| Mismatch distances | 60 对报告距离与同群异体参照分布；OFF/ON 距离—Raw A−M 散点；剔除最近三分之一后的差及区间 | 第 4 节报告 60/60 数值不同与剔除近供体后的敏感性结果；低十分位计数留补充材料，不定义实质近同 |
| JEV detectability | 严格判读 31/120 对 0/480；31 条中 30 继续使用、1 弃用；宽口径、置信阈值、判读方法与原始实例 | 第 4 节对照 Accurate 0/120 与 Mismatched 31/120 的归属质疑标签，分别报告继续使用与弃用判读；其他条件计数留补充材料，不把弃用例解释为总体收益机制 |

距离图不加一条未经支持的“距离越大匹配越有效”拟合结论；JEV 不做识别/未识别组的收益因果比较。JEV 范围只为 DeepSeek ON 的可见轨迹，不为 OFF 或 Qwen补造判读结果。

## 6. 正式制图与稿件整合验收

1. 新纯绘图脚本读取上述冻结结果，不运行实验、模型请求或重新 bootstrap；记录源文件哈希、读取键、均值/区间及种群顺序。
2. 图 2c 四个分面的种群向量按 manifest 的 seeds 对齐；验证均值与本文件核对表一致。无效候选继续按既定协议回退父代，不能只画有效样本。
3. 图 3 的 H 区间与 F′ 区间分别核对；c 的百分数换算覆盖上下限；共享父代仅绘一次；三阶段线不使用时间轴。
4. 图 2、3 输出可编辑矢量 PDF/SVG，PNG 预览至少 300 dpi。按 175 mm 实际尺寸查看彩色和灰度预览，检查必要文字≥8 pt、无重叠、区间端点未截断。图 1 直接复用现有资源。
5. 所有图内文字统一使用英文，只生成并维护英文图件，中英文稿复用相同资产，保持同一数值、尺度、面板编号和编码。同步改正文面板引用与补充材料引用；预定/探索性的表述与协议一致。图 1 现有图注保持原样。
6. Interface Focus 主文实际只输入三个 figure 环境，保留现有图 1 的输入与资源。原 figure4 的内容进入新 figure3，不能仅删文件名而留下旧正文引用。补充图按标签统一重新编号。

本设计依据已调用的 ARS-Codex 学术图件角色与统计可视化规范，结合作者的三图、摘要和 OFF/ON 并列要求裁剪；不新增实验，也不承诺各细节全部进入正文面板。
