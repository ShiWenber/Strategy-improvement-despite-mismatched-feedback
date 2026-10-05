# 诊断针对性实验 v2：冻结协议结果

完成 840 次请求；报告 tokens 5,917,619；审计问题 0。

| 组别 | 有效候选 | 原始默认增量 | S1 后增量 | S2 后增量 | S3 后增量 |
| --- | ---: | ---: | ---: | ---: | ---: |
| score | 117/120 | +0.003809 | +0.010198 | +0.014186 | +0.032029 |
| accurate | 116/120 | +0.002321 | +0.006589 | +0.007190 | +0.027147 |
| mismatched | 116/120 | +0.002629 | +0.007648 | +0.009543 | +0.023542 |
| background | 119/120 | +0.009750 | +0.006397 | +0.008676 | +0.033928 |
| cooperation | 116/120 | +0.016506 | +0.013464 | +0.019901 | +0.033129 |

主比较 accurate−mismatched：-0.000308，95% 区间 [-0.010014105902777787, 0.009500624999999948]，配对符号交换 p=0.951618。

| 预定次比较 | 差值 | 未校正 95% 区间 | Holm p |
| --- | ---: | --- | ---: |
| raw_accurate-score | -0.001488 | [-0.013208758680555571, 0.010478949652777758] | 1.000000 |
| raw_accurate-background | -0.007429 | [-0.017142413194444484, 0.0018650347222221987] | 0.608192 |
| raw_accurate-cooperation | -0.014185 | [-0.023313654513888914, -0.00473305555555559] | 0.049992 |
| S3_accurate-score | -0.004882 | [-0.01876821180555559, 0.0063021354166666495] | 1.000000 |
| S3_accurate-parent | +0.027147 | [0.01709262152777776, 0.036900138888888885] | 0.000687 |
| selection_interaction | +0.002115 | [-0.009702083333333346, 0.011527465277777713] | 1.000000 |

量化推进门槛：未通过，不启动多代扩展。

20 independent population clusters. Primary is accurate vs mismatched raw proposals. Six secondary tests Holm-adjusted. Other endpoints exploratory. CIs are unadjusted seed-bootstrap intervals; a parent sign-swap test requires symmetry and is not a randomized parent assignment.
