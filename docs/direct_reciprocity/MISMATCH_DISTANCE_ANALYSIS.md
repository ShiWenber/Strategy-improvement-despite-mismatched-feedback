> 符号已与正文一致：反馈报告记为 $R$，标准化后的报告向量记为 $\tilde R$。探针名（`one_D_TFT` 等）为记录原文，保持不改。

# 错配距离分析（Mismatch-Distance Analysis）

**对应审稿意见条目 2「没有量化『错配到底有多错』」。**

本分析把 `Mismatched` 这一二元标签展开为可测量的**诊断距离** $\delta(p,q)$，
并检验距离大小是否与候选收益、候选行为变化、选择后输出收益相关。
所有距离都由父代与供体的行为诊断在候选生成**之前**测得，因此它是前处理协变量，
而不是结果变量。本文档中的关联分析均为**探索性**：推断单位为 20 个独立种群，
区间为种子聚类自助区间；未做多重检验校正，相关性不构成因果中介证据。

## 1. 距离定义

反馈探针 $F$ 为每个策略产生 36 维行为特征：恢复类探针 `one_D_TFT`、`four_D_TFT`、
`four_D_ALLC`（含 `not_recovered`、`recovery_time_capped` 两个恢复时间统计量）
与受剥削类探针 `sustained_D`、`periodic_D`。把全部 20 个种群的 240 个成员在每个
维度上标准化为 $\tilde R(\cdot)$，定义

$$\delta_{\text{full}}(p,q)=\left\|\tilde R(p)-\tilde R(q)\right\|_2 .$$

辅助量：仅在恢复类特征上的 $\delta_{\text{rec}}$、仅在受剥削类特征上的
$\delta_{\text{expl}}$、按种群内平均两两距离归一化的 $\delta_{\text{rel}}$，
以及先在各特征块内取平均再求范数的 $\delta_{\text{2d}}$。

## 2. 错配强度到底有多大？

**父代、供体与诊断均为两套生成配置共享**，因此下表对思考关闭与思考开启完全一致；
它描述的是设计本身，而不是某个配置的结果。

特征维度 36；60 个父代全部满足 `effective_mismatch = true`（即供体报告与父代报告在数值上不相同）。

| 指标 | 均值 | 中位数 | 最小 | p25 | p75 | 最大 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| $\delta_{\text{full}}$ | 7.452 | 7.002 | 2.012 | 5.084 | 8.263 | 20.354 |
| $\delta_{\text{rec}}$ | 6.242 | 5.797 | 1.532 | 4.113 | 7.267 | 15.843 |
| $\delta_{\text{expl}}$ | 3.748 | 3.068 | 0.611 | 2.180 | 4.763 | 12.779 |
| $\delta_{\text{rel}}$ | 0.997 | 0.900 | 0.275 | 0.725 | 1.181 | 2.033 |

**与"同种群随机成员"参照的对照。** 同一种群内成员两两距离（有序对，2640 对）为
均值 7.487、中位数 6.949、10%–90% 分位 3.344–12.644。

父代—供体距离均值 7.452，为该参照均值的 100%。这一吻合是**设计使然**：错配由全种群报告的无固定点置换（derangement）产生，
供体是从同种群中均匀抽取的“另一位成员”，因此“随机成员配对”正是该干预的期望行为。

因此正确的表述不是"错配很弱"，而是：**错配是真实的（全部 60 对数值均改变），但强度高度异质**——$\delta_{\text{full}}$ 从 2.01 到 20.35（10.1 倍），
且只有 3 个父代落在参照分布的第 10 百分位以下，即"实质等价"的错配占比很低。

| 父代排名 | n | 平均 $\delta_{\text{full}}$ | 中位数 |
| --- | ---: | ---: | ---: |
| rank1 | 20 | 8.141 | 7.001 |
| rank3 | 20 | 7.281 | 7.176 |
| rank6 | 20 | 6.933 | 6.876 |

## 3. 思考关闭（旧配置）

**各条件原始候选增益（每轮收益）与主对照：**

score +0.00381，accurate +0.00232，mismatched +0.00263，background +0.00975，cooperation +0.01651。

主对照 Accurate−Mismatched = **-0.000308**（正式区间与配对符号交换检验见 `ANALYSIS.json`）。

### 3.1 距离与结果指标的关联

| 距离 | 结果指标 | Pearson | 95% CI | Spearman | 排名校正 Pearson | 留一种群符号一致 |
| --- | --- | ---: | --- | ---: | ---: | ---: |
| $\delta_{\text{full}}$ | Accurate - Mismatched raw gain | +0.134 | [-0.053, +0.305] | +0.154 | +0.132 | 20/20 |
| $\delta_{\text{full}}$ | Mismatched raw proposal gain | +0.013 | [-0.364, +0.355] | -0.172 | +0.029 | 16/20 |
| $\delta_{\text{full}}$ | Accurate raw proposal gain | +0.110 | [-0.231, +0.430] | +0.049 | +0.117 | 19/20 |
| $\delta_{\text{full}}$ | Accurate - Mismatched S3 gain | -0.062 | [-0.197, +0.092] | +0.036 | -0.071 | 20/20 |
| $\delta_{\text{full}}$ | Mismatched-arm behavioural movement | +0.254 | [-0.006, +0.470] | +0.257 | +0.251 | 20/20 |
| $\delta_{\text{full}}$ | Accurate-arm behavioural movement | +0.281 | [-0.092, +0.564] | +0.224 | +0.300 | 20/20 |
| $\delta_{\text{full}}$ | Mismatched-arm movement minus Score-arm movement | -0.102 | [-0.317, +0.167] | +0.028 | -0.144 | 20/20 |
| $\delta_{\text{full}}$ | Movement: Mismatched minus Accurate | -0.045 | [-0.272, +0.222] | -0.035 | -0.070 | 19/20 |
| $\delta_{\text{full}}$ | Mismatched-arm code change | -0.024 | [-0.192, +0.196] | +0.139 | -0.040 | 17/20 |
| $\delta_{\text{full}}$ | Code change: Mismatched minus Accurate | +0.040 | [-0.097, +0.182] | +0.156 | +0.009 | 20/20 |
| $\delta_{\text{rec}}$ | Accurate - Mismatched raw gain | +0.145 | [-0.078, +0.346] | +0.109 | +0.148 | 20/20 |
| $\delta_{\text{rec}}$ | Mismatched raw proposal gain | -0.041 | [-0.404, +0.305] | -0.169 | -0.030 | 18/20 |
| $\delta_{\text{rec}}$ | Accurate raw proposal gain | +0.066 | [-0.279, +0.390] | +0.041 | +0.074 | 19/20 |
| $\delta_{\text{rec}}$ | Accurate - Mismatched S3 gain | -0.049 | [-0.209, +0.131] | -0.003 | -0.059 | 20/20 |
| $\delta_{\text{rec}}$ | Mismatched-arm behavioural movement | +0.194 | [-0.061, +0.418] | +0.168 | +0.191 | 20/20 |
| $\delta_{\text{rec}}$ | Accurate-arm behavioural movement | +0.254 | [-0.070, +0.534] | +0.270 | +0.280 | 20/20 |
| $\delta_{\text{rec}}$ | Mismatched-arm movement minus Score-arm movement | -0.106 | [-0.306, +0.167] | -0.031 | -0.162 | 20/20 |
| $\delta_{\text{rec}}$ | Movement: Mismatched minus Accurate | -0.081 | [-0.295, +0.174] | -0.119 | -0.114 | 19/20 |
| $\delta_{\text{rec}}$ | Mismatched-arm code change | +0.059 | [-0.117, +0.288] | +0.202 | +0.039 | 20/20 |
| $\delta_{\text{rec}}$ | Code change: Mismatched minus Accurate | +0.108 | [-0.057, +0.273] | +0.220 | +0.067 | 20/20 |
| $\delta_{\text{expl}}$ | Accurate - Mismatched raw gain | +0.130 | [-0.055, +0.327] | +0.185 | +0.114 | 20/20 |
| $\delta_{\text{expl}}$ | Mismatched raw proposal gain | +0.075 | [-0.315, +0.409] | -0.108 | +0.102 | 19/20 |
| $\delta_{\text{expl}}$ | Accurate raw proposal gain | +0.167 | [-0.192, +0.484] | +0.095 | +0.172 | 20/20 |
| $\delta_{\text{expl}}$ | Accurate - Mismatched S3 gain | -0.031 | [-0.240, +0.207] | +0.060 | -0.041 | 17/20 |
| $\delta_{\text{expl}}$ | Mismatched-arm behavioural movement | +0.293 | [+0.015, +0.529] | +0.275 | +0.285 | 20/20 |
| $\delta_{\text{expl}}$ | Accurate-arm behavioural movement | +0.270 | [-0.151, +0.567] | +0.065 | +0.271 | 20/20 |
| $\delta_{\text{expl}}$ | Mismatched-arm movement minus Score-arm movement | -0.104 | [-0.354, +0.163] | -0.015 | -0.122 | 20/20 |
| $\delta_{\text{expl}}$ | Movement: Mismatched minus Accurate | +0.012 | [-0.258, +0.313] | +0.065 | +0.003 | 14/20 |
| $\delta_{\text{expl}}$ | Mismatched-arm code change | -0.147 | [-0.323, +0.061] | -0.041 | -0.147 | 20/20 |
| $\delta_{\text{expl}}$ | Code change: Mismatched minus Accurate | -0.076 | [-0.216, +0.064] | -0.031 | -0.082 | 20/20 |

“排名校正”为在每个父代排名组内中心化后的 Pearson 相关，用于排除父代强弱（rank1/3/6 的 $\delta$ 均值略有差异，见第 2 节）造成的混淆。

### 3.2 主对照在不同距离定义下的稳定性

| 距离定义 | Pearson | 95% CI | Spearman |
| --- | ---: | --- | ---: |
| $\delta_{\text{full}}$ | +0.134 | [-0.053, +0.305] | +0.154 |
| $\delta_{\text{rec}}$ | +0.145 | [-0.078, +0.346] | +0.109 |
| $\delta_{\text{expl}}$ | +0.130 | [-0.055, +0.327] | +0.185 |
| $\delta_{\text{2d}}$ | +0.097 | [-0.061, +0.245] | +0.099 |
| $\delta_{\text{rel}}$ | +0.158 | [-0.055, +0.335] | +0.112 |

### 3.3 低/中/高错配分位

| 距离 | 结果指标 | 低错配 | 中错配 | 高错配 |
| --- | --- | ---: | ---: | ---: |
| $\delta_{\text{rec}}$ | Accurate−Mismatched（原始） | -0.0074 | -0.0084 | +0.0149 |
| $\delta_{\text{rec}}$ | 错配原始候选增益 | +0.0131 | +0.0056 | -0.0108 |
| $\delta_{\text{expl}}$ | Accurate−Mismatched（原始） | -0.0148 | +0.0091 | +0.0048 |
| $\delta_{\text{expl}}$ | 错配原始候选增益 | +0.0065 | -0.0088 | +0.0101 |

### 3.4 弱错配敏感性（剔除"几乎相同"的供体）

按 $\delta_{\text{full}}$ 排序取最接近的三分之一（20 个父代，切点 5.643）为**弱错配**子集，其余 40 个为较强错配。若"无差异"只因供体报告几乎相同，两组的主对照应明显分离。

| 子集 | n | Accurate−Mismatched 原始增益 | 95% CI |
| --- | ---: | ---: | --- |
| 全部父代 | 60 | -0.000308 | [-0.00992, +0.00948] |
| 弱错配（最接近三分之一） | 20 | -0.009929 | [-0.02793, +0.00360] |
| 较强错配（其余三分之二） | 40 | +0.004503 | [-0.00929, +0.01666] |

## 4. 思考开启（384K）

**各条件原始候选增益（每轮收益）与主对照：**

score +0.05272，accurate +0.07198，mismatched +0.06585，background +0.05781，cooperation +0.05284。

主对照 Accurate−Mismatched = **+0.006127**（正式区间与配对符号交换检验见 `ANALYSIS.json`）。

### 4.1 距离与结果指标的关联

| 距离 | 结果指标 | Pearson | 95% CI | Spearman | 排名校正 Pearson | 留一种群符号一致 |
| --- | --- | ---: | --- | ---: | ---: | ---: |
| $\delta_{\text{full}}$ | Accurate - Mismatched raw gain | +0.172 | [-0.035, +0.378] | +0.156 | +0.182 | 20/20 |
| $\delta_{\text{full}}$ | Mismatched raw proposal gain | -0.035 | [-0.404, +0.287] | -0.165 | -0.024 | 17/20 |
| $\delta_{\text{full}}$ | Accurate raw proposal gain | +0.145 | [-0.245, +0.486] | -0.039 | +0.172 | 19/20 |
| $\delta_{\text{full}}$ | Accurate - Mismatched S3 gain | +0.245 | [+0.038, +0.402] | +0.229 | +0.256 | 20/20 |
| $\delta_{\text{full}}$ | Mismatched-arm behavioural movement | -0.336 | [-0.588, -0.094] | -0.292 | -0.310 | 20/20 |
| $\delta_{\text{full}}$ | Accurate-arm behavioural movement | +0.091 | [-0.135, +0.305] | +0.018 | +0.140 | 20/20 |
| $\delta_{\text{full}}$ | Mismatched-arm movement minus Score-arm movement | -0.385 | [-0.574, -0.156] | -0.332 | -0.394 | 20/20 |
| $\delta_{\text{full}}$ | Movement: Mismatched minus Accurate | -0.353 | [-0.559, -0.144] | -0.302 | -0.355 | 20/20 |
| $\delta_{\text{full}}$ | Mismatched-arm code change | +0.256 | [-0.174, +0.603] | +0.197 | +0.256 | 20/20 |
| $\delta_{\text{full}}$ | Code change: Mismatched minus Accurate | +0.107 | [-0.164, +0.387] | +0.174 | +0.101 | 20/20 |
| $\delta_{\text{rec}}$ | Accurate - Mismatched raw gain | +0.179 | [-0.033, +0.388] | +0.190 | +0.194 | 20/20 |
| $\delta_{\text{rec}}$ | Mismatched raw proposal gain | -0.061 | [-0.376, +0.228] | -0.168 | -0.050 | 20/20 |
| $\delta_{\text{rec}}$ | Accurate raw proposal gain | +0.124 | [-0.257, +0.481] | -0.002 | +0.155 | 19/20 |
| $\delta_{\text{rec}}$ | Accurate - Mismatched S3 gain | +0.270 | [+0.037, +0.439] | +0.277 | +0.287 | 20/20 |
| $\delta_{\text{rec}}$ | Mismatched-arm behavioural movement | -0.401 | [-0.609, -0.176] | -0.319 | -0.366 | 20/20 |
| $\delta_{\text{rec}}$ | Accurate-arm behavioural movement | +0.025 | [-0.194, +0.249] | -0.046 | +0.084 | 17/20 |
| $\delta_{\text{rec}}$ | Mismatched-arm movement minus Score-arm movement | -0.374 | [-0.532, -0.132] | -0.282 | -0.386 | 20/20 |
| $\delta_{\text{rec}}$ | Movement: Mismatched minus Accurate | -0.349 | [-0.560, -0.135] | -0.258 | -0.352 | 20/20 |
| $\delta_{\text{rec}}$ | Mismatched-arm code change | +0.289 | [-0.069, +0.599] | +0.292 | +0.289 | 20/20 |
| $\delta_{\text{rec}}$ | Code change: Mismatched minus Accurate | +0.131 | [-0.119, +0.387] | +0.195 | +0.127 | 20/20 |
| $\delta_{\text{expl}}$ | Accurate - Mismatched raw gain | +0.116 | [-0.072, +0.319] | +0.110 | +0.119 | 20/20 |
| $\delta_{\text{expl}}$ | Mismatched raw proposal gain | +0.025 | [-0.383, +0.397] | -0.065 | +0.040 | 18/20 |
| $\delta_{\text{expl}}$ | Accurate raw proposal gain | +0.152 | [-0.210, +0.455] | +0.020 | +0.174 | 19/20 |
| $\delta_{\text{expl}}$ | Accurate - Mismatched S3 gain | +0.144 | [-0.031, +0.305] | +0.100 | +0.144 | 20/20 |
| $\delta_{\text{expl}}$ | Mismatched-arm behavioural movement | -0.173 | [-0.478, +0.114] | -0.147 | -0.167 | 20/20 |
| $\delta_{\text{expl}}$ | Accurate-arm behavioural movement | +0.179 | [-0.094, +0.428] | +0.151 | +0.207 | 20/20 |
| $\delta_{\text{expl}}$ | Mismatched-arm movement minus Score-arm movement | -0.301 | [-0.561, -0.041] | -0.244 | -0.308 | 20/20 |
| $\delta_{\text{expl}}$ | Movement: Mismatched minus Accurate | -0.296 | [-0.496, -0.088] | -0.319 | -0.299 | 20/20 |
| $\delta_{\text{expl}}$ | Mismatched-arm code change | +0.154 | [-0.381, +0.547] | +0.001 | +0.156 | 19/20 |
| $\delta_{\text{expl}}$ | Code change: Mismatched minus Accurate | +0.048 | [-0.257, +0.354] | +0.062 | +0.033 | 19/20 |

“排名校正”为在每个父代排名组内中心化后的 Pearson 相关，用于排除父代强弱（rank1/3/6 的 $\delta$ 均值略有差异，见第 2 节）造成的混淆。

### 4.2 主对照在不同距离定义下的稳定性

| 距离定义 | Pearson | 95% CI | Spearman |
| --- | ---: | --- | ---: |
| $\delta_{\text{full}}$ | +0.172 | [-0.035, +0.378] | +0.156 |
| $\delta_{\text{rec}}$ | +0.179 | [-0.033, +0.388] | +0.190 |
| $\delta_{\text{expl}}$ | +0.116 | [-0.072, +0.319] | +0.110 |
| $\delta_{\text{2d}}$ | +0.145 | [-0.071, +0.370] | +0.115 |
| $\delta_{\text{rel}}$ | +0.073 | [-0.182, +0.383] | +0.149 |

### 4.3 低/中/高错配分位

| 距离 | 结果指标 | 低错配 | 中错配 | 高错配 |
| --- | --- | ---: | ---: | ---: |
| $\delta_{\text{rec}}$ | Accurate−Mismatched（原始） | -0.0073 | -0.0026 | +0.0283 |
| $\delta_{\text{rec}}$ | 错配原始候选增益 | +0.0776 | +0.0701 | +0.0498 |
| $\delta_{\text{expl}}$ | Accurate−Mismatched（原始） | -0.0001 | +0.0027 | +0.0157 |
| $\delta_{\text{expl}}$ | 错配原始候选增益 | +0.0630 | +0.0688 | +0.0658 |

### 4.4 弱错配敏感性（剔除"几乎相同"的供体）

按 $\delta_{\text{full}}$ 排序取最接近的三分之一（20 个父代，切点 5.643）为**弱错配**子集，其余 40 个为较强错配。若"无差异"只因供体报告几乎相同，两组的主对照应明显分离。

| 子集 | n | Accurate−Mismatched 原始增益 | 95% CI |
| --- | ---: | ---: | --- |
| 全部父代 | 60 | +0.006127 | [-0.01285, +0.02440] |
| 弱错配（最接近三分之一） | 20 | -0.002166 | [-0.02503, +0.02539] |
| 较强错配（其余三分之二） | 40 | +0.010273 | [-0.00555, +0.03236] |

## 5. 结论与对审稿意见的回应

1. **错配不是"名义错配"，但强度高度异质。** 60 个父代的诊断向量全部改变；由于错配由全种群无固定点置换产生，其期望强度正好等于"随机抽取同种群另一位成员"，只有 3/60 个父代的距离落在该参照分布的第 10 百分位以下。因此二元 `Accurate vs Mismatched` 标签掩盖的是**强度异质**，而不是"错配不足"。

2. **错配强度不预测候选生成收益——包括"错得更远反而更好"这一方向。**

| 配置 | 距离 | 与主对照 (Accurate−Mismatched) 的 Pearson | 95% CI |
| --- | --- | ---: | --- |
| 思考关闭（旧配置） | $\delta_{\text{full}}$ | +0.134 | [-0.053, +0.305] |
| 思考关闭（旧配置） | $\delta_{\text{rec}}$ | +0.145 | [-0.078, +0.346] |
| 思考关闭（旧配置） | $\delta_{\text{expl}}$ | +0.130 | [-0.055, +0.327] |
| 思考开启（384K） | $\delta_{\text{full}}$ | +0.172 | [-0.035, +0.378] |
| 思考开启（384K） | $\delta_{\text{rec}}$ | +0.179 | [-0.033, +0.388] |
| 思考开启（384K） | $\delta_{\text{expl}}$ | +0.116 | [-0.072, +0.319] |

所有区间均覆盖 0；低/中/高分位分组亦无单调趋势。剔除最接近的三分之一供体后，两组的 Accurate−Mismatched 区间仍然都覆盖 0，说明"准确诊断无稳定增量优势"并非由个别近乎相同的供体造成。

3. **少数区间穿过 0，但方向并不一致，因此不构成连贯的机制信号。**

**收益层面：**

| 配置 | 距离 | 结果指标 | Pearson | 95% CI |
| --- | --- | --- | ---: | --- |
| 思考开启（384K） | $\delta_{\text{full}}$ | Accurate - Mismatched S3 gain | +0.245 | [+0.038, +0.402] |
| 思考开启（384K） | $\delta_{\text{rec}}$ | Accurate - Mismatched S3 gain | +0.270 | [+0.037, +0.439] |

**行为层面：**

| 配置 | 距离 | 结果指标 | Pearson | 95% CI |
| --- | --- | --- | ---: | --- |
| 思考关闭（旧配置） | $\delta_{\text{expl}}$ | Mismatched-arm behavioural movement | +0.293 | [+0.015, +0.529] |
| 思考开启（384K） | $\delta_{\text{full}}$ | Mismatched-arm behavioural movement | -0.336 | [-0.588, -0.094] |
| 思考开启（384K） | $\delta_{\text{full}}$ | Mismatched-arm movement minus Score-arm movement | -0.385 | [-0.574, -0.156] |
| 思考开启（384K） | $\delta_{\text{full}}$ | Movement: Mismatched minus Accurate | -0.353 | [-0.559, -0.144] |
| 思考开启（384K） | $\delta_{\text{rec}}$ | Mismatched-arm behavioural movement | -0.401 | [-0.609, -0.176] |
| 思考开启（384K） | $\delta_{\text{rec}}$ | Mismatched-arm movement minus Score-arm movement | -0.374 | [-0.532, -0.132] |
| 思考开启（384K） | $\delta_{\text{rec}}$ | Movement: Mismatched minus Accurate | -0.349 | [-0.560, -0.135] |
| 思考开启（384K） | $\delta_{\text{expl}}$ | Mismatched-arm movement minus Score-arm movement | -0.301 | [-0.561, -0.041] |
| 思考开启（384K） | $\delta_{\text{expl}}$ | Movement: Mismatched minus Accurate | -0.296 | [-0.496, -0.088] |

行为层面的关联并非单一方向：**原始移动量**（Mismatched-arm behavioural movement）在不同配置/距离间符号不一致，而**组内差分**（扣除 Score 组反应性、或 Mismatched−Accurate 配对差）在 6 个组合中一致为负。两者回答不同问题：原始移动量混合了父代自身的行为反应性，组内差分则在扣除父代基线后测量可归因于错配的额外移动，后者随距离下降更符合"报告越偏离自身，模型越少据此修改"的读法。

收益层面仅 S3 输出收益出现正相关，且只在思考开启配置中；原始候选收益（主对照）在所有距离定义下均不显著。S3 收益是门控与采用规则之后的非线性量，该关联不能读作"错配越远、准确诊断越有用"。

这些关联均未做多重检验校正（此处共检查 60 个组合），且大多只在一个配置中出现，只能作为待验证的探索性观察，不能作为机制结论。

4. **对审稿意见 3 的作用是排除一种解释，而不是替代它。** 本分析可以排除"错配强度不足以致无法检验"这一解释，但不能排除"数值报告本身可利用性有限"或"模型主要依据源码与成绩修改"（对应审稿意见中的 $H_2$、$H_3$）。后者需要 known-defect 阳性对照实验。

**方法与适用边界。** 距离仅基于反馈探针 $F$ 的 36 维统计量；标准化参照为全体 240 个
种群成员；关联分析未做多重检验校正；行为变化量以父代自身探针行为为基准，
受行为天花板影响，故同时报告扣除 Score 组反应性的组内差分与 Mismatched−Accurate 配对差；
S3 输出收益是选择（含门控与是否采用）之后的非线性量，其关联只能视为探索性。
相关性不等于因果中介；本分析不能替代审稿意见 3 所要求的 known-defect 阳性对照。
