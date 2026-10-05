"""Complete descriptive tables from the frozen analysis; no new hypothesis tests."""
import argparse
from pathlib import Path
from .run import read_json


def estimate(row):
    return f"{row['mean']:+.5f} [{row['ci95'][0]:+.5f}, {row['ci95'][1]:+.5f}]"


def tables(root):
    root = Path(root)
    read_json(root / 'COMPLETE.json')
    a = read_json(root / 'ANALYSIS.json')
    if a['audit']['issues']:
        raise RuntimeError('Analysis audit has unresolved issues')
    arms = list(a['raw'])
    lines = ['# 诊断针对性 v2：完整补充结果', '',
             '所有区间均为 20 个种群聚类的未校正 95% bootstrap 区间。除冻结的主比较和六项次比较外，'
             '以下为探索性或描述性结果，不新增假设检验，不用区间重叠判断组间差异。'
             '收益单位为每轮收益；合作指标为比例，行为时间单位为轮。', '',
             '## 原始提案的全部指标', '',
             '| 指标（相对父代增量） | ' + ' | '.join(arms) + ' |',
             '| --- | ' + ' | '.join(['---:'] * len(arms)) + ' |']
    for metric in a['raw'][arms[0]]['metrics']:
        lines.append('| ' + metric + ' | ' + ' | '.join(estimate(a['raw'][arm]['metrics'][metric]) for arm in arms) + ' |')
    lines += ['', '## 独立行为探针', '',
              '| 行为指标（相对父代增量） | ' + ' | '.join(arms) + ' |',
              '| --- | ' + ' | '.join(['---:'] * len(arms)) + ' |']
    for metric in a['raw'][arms[0]]['behavior']:
        lines.append('| ' + metric + ' | ' + ' | '.join(estimate(a['raw'][arm]['behavior'][metric]) for arm in arms) + ' |')
    lines += ['', '## 三种选择规则的全部收益设置', '',
              '| 规则/组别 | 接受数/60 | 接受后默认退化数 | 默认增量 | 噪声增量 | 长局增量 |',
              '| --- | ---: | ---: | --- | --- | --- |']
    for key, row in a['selected'].items():
        lines.append(f"| {key} | {row['accepted']}/60 | {row['accepted_default_degrades']} | " +
                     ' | '.join(estimate(row['metrics'][s]) for s in ('default', 'noise01', 'long')) + ' |')
    lines += ['', '## 有效性、回退与源码保持', '',
              '| 组别 | 有效数/120 | 与父代相同源码数 | 默认回退 | 噪声回退 | 长局回退 | 行为回退 | 仅默认成功候选增量 |',
              '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for arm, row in a['raw'].items():
        success = row['successful_only_default_gain']
        success_text = 'NA' if success is None else f'{success:+.5f}'
        lines.append(f"| {arm} | {row['valid']}/120 | {row['unchanged']} | " +
                     ' | '.join(str(row['fallbacks'][s]) for s in ('default', 'noise01', 'long', 'behavior')) +
                     f" | {success_text} |")
    lines += ['', '仅成功候选结果条件化于执行成功，可能有选择偏差，不能替代含回退的主分析。'
              '源码相同只识别字面保持，源码不同也可能行为相同。', '',
              '## 选择决定分歧', '', '| 组别 | S1–S2 | S2–S3 | S1–S3 |', '| --- | ---: | ---: | ---: |']
    for arm, row in a['selection_disagreements'].items():
        lines.append('| ' + arm + ' | ' + ' | '.join(str(row[s]) for s in ('S1-S2', 'S2-S3', 'S1-S3')) + ' |')
    lines += ['', '## 父代特征与准确−错配效应的探索性关联', '',
              '| 特征 | 斜率 | 95% 种群 bootstrap 区间 |', '| --- | ---: | --- |']
    for feature, row in a['parent_feature_interactions_exploratory'].items():
        lines.append(f"| {feature} | {row['interaction_slope']} | {row['ci95']} |")
    lines += ['', '斜率表示父代特征每增加一个单位时，准确−错配默认收益差的变化。'
              '关联并非已识别的行为中介或内部因果理解。逐父代数据和逐种群差值保存在 ANALYSIS.json。', '']
    path = root / 'EXPLORATORY_TABLES.md'
    path.write_text('\n'.join(lines), encoding='utf-8')
    return path


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', nargs='?', default='results/feedback_specificity_v2')
    print(tables(p.parse_args().root))
