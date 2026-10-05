# 错配报告是否被发现

- 数据：`results\feedback_specificity_thinking_384k_20260923`（Thinking ON），共 240 条请求
- 抽取：`deepseek-flash`；判读：`jev-1.13.0`
- 失败 0；抽取超预算 0
- 用量：抽取 12,932,888 prompt + 306,590 completion；Jev 643,535 input tokens

每条思维链由 deepseek-flash 分块抽取报告来源相关的**原文引语**（不做概述，概述会丢失信号），
长度落入 Jev 单请求预算后交给 Jev 判两个三档问题。`state` 只含报告块与抽取结果，
条件标签不进入请求。

## 三档概率与标签

每条文件的 origin 三档概率之和为 1，下表为跨文件均值；标签为 argmax 计数。

| 条件 | 文件 | P(origin) | P(accepts) | P(silent) | 标签 origin/accepts/silent | 均值置信度 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| accurate | 120 | 0.034 | 0.927 | 0.038 | 4/116/0 | 0.897 |
| mismatched | 120 | 0.279 | 0.690 | 0.031 | 33/87/0 | 0.903 |

## 检出率

- `leaning`：P(origin) ≥ 0.4
- `confident`：上述条件且 confidence ≥ 0.6（窄口径，Accurate对照严格判读为0）

| 条件 | leaning | 检出率 | confident | 检出率 |
| --- | ---: | ---: | ---: | ---: |
| accurate | 4/120 | 0.033 | 0/120 | 0.000 |
| mismatched | 33/120 | 0.275 | 31/120 | 0.258 |
| **Accurate报告条件** | 4/120 | 0.0333 | 0/120 | 0.0000 |

## 处理方式（三档 resolution）

| 条件 | kept_using | discarded | unclear | confident 中仍 kept_using |
| --- | ---: | ---: | ---: | ---: |
| accurate | 120 | 0 | 0 | — |
| mismatched | 119 | 1 | 0 | 0.968 |

## confident 明细（P(origin) ≥ 0.4 且 confidence ≥ 0.6）

### mismatched（31/120）

- `s200-rank1-d0-pos0` — questions_its_origin, P(origin)=1.00, confidence=1.00, resolution=kept_using
- `s200-rank1-d1-pos0` — questions_its_origin, P(origin)=1.00, confidence=1.00, resolution=kept_using
- `s201-rank6-d0-pos3` — questions_its_origin, P(origin)=0.99, confidence=0.99, resolution=kept_using
- `s201-rank6-d1-pos3` — questions_its_origin, P(origin)=0.99, confidence=0.99, resolution=kept_using
- `s203-rank1-d1-pos1` — questions_its_origin, P(origin)=0.98, confidence=0.97, resolution=kept_using
- `s204-rank6-d1-pos1` — questions_its_origin, P(origin)=0.91, confidence=0.87, resolution=kept_using
- `s205-rank3-d1-pos0` — questions_its_origin, P(origin)=0.99, confidence=0.99, resolution=kept_using
- `s205-rank6-d1-pos0` — questions_its_origin, P(origin)=1.00, confidence=1.00, resolution=kept_using
- `s206-rank1-d0-pos3` — questions_its_origin, P(origin)=1.00, confidence=1.00, resolution=kept_using
- `s206-rank1-d1-pos3` — questions_its_origin, P(origin)=1.00, confidence=1.00, resolution=kept_using
- `s207-rank1-d0-pos4` — questions_its_origin, P(origin)=0.97, confidence=0.95, resolution=kept_using
- `s207-rank1-d1-pos4` — questions_its_origin, P(origin)=0.94, confidence=0.91, resolution=kept_using
- `s208-rank6-d1-pos3` — questions_its_origin, P(origin)=1.00, confidence=1.00, resolution=kept_using
- `s209-rank3-d1-pos0` — questions_its_origin, P(origin)=1.00, confidence=1.00, resolution=kept_using
- `s210-rank1-d1-pos4` — questions_its_origin, P(origin)=0.89, confidence=0.84, resolution=kept_using
- `s211-rank3-d0-pos0` — questions_its_origin, P(origin)=1.00, confidence=1.00, resolution=kept_using
- `s211-rank3-d1-pos0` — questions_its_origin, P(origin)=1.00, confidence=1.00, resolution=kept_using
- `s214-rank6-d0-pos0` — questions_its_origin, P(origin)=0.89, confidence=0.84, resolution=kept_using
- `s215-rank1-d0-pos2` — questions_its_origin, P(origin)=1.00, confidence=1.00, resolution=kept_using
- `s215-rank1-d1-pos2` — questions_its_origin, P(origin)=1.00, confidence=1.00, resolution=kept_using
- `s215-rank3-d1-pos2` — questions_its_origin, P(origin)=0.96, confidence=0.94, resolution=kept_using
- `s215-rank6-d0-pos2` — questions_its_origin, P(origin)=0.99, confidence=0.98, resolution=kept_using
- `s215-rank6-d1-pos2` — questions_its_origin, P(origin)=0.99, confidence=0.99, resolution=kept_using
- `s216-rank1-d0-pos0` — questions_its_origin, P(origin)=0.94, confidence=0.90, resolution=kept_using
- `s216-rank1-d1-pos0` — questions_its_origin, P(origin)=0.98, confidence=0.98, resolution=kept_using
- `s217-rank1-d0-pos1` — questions_its_origin, P(origin)=1.00, confidence=1.00, resolution=kept_using
- `s217-rank1-d1-pos1` — questions_its_origin, P(origin)=1.00, confidence=1.00, resolution=kept_using
- `s217-rank6-d0-pos1` — questions_its_origin, P(origin)=0.99, confidence=0.98, resolution=kept_using
- `s217-rank6-d1-pos1` — questions_its_origin, P(origin)=1.00, confidence=1.00, resolution=kept_using
- `s219-rank1-d1-pos4` — questions_its_origin, P(origin)=0.78, confidence=0.66, resolution=kept_using
- `s219-rank3-d1-pos4` — questions_its_origin, P(origin)=0.99, confidence=0.99, resolution=discarded
