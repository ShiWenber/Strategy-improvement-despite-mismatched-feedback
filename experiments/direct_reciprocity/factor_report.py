"""Paired prompt/selection comparisons across every held-out endpoint metric."""
import argparse
from pathlib import Path
from statistics import mean

from .analyze import interval
from .run import read_json, write_json


def report(root):
    root = Path(root)
    analysis = read_json(root / 'analysis.json')
    groups = {}
    for row in analysis['endpoints']:
        groups.setdefault((row['prompt'], row['selection']), {})[row['seed']] = row
    comparisons = []
    for selection in ('paper_truncation',):
        for prompt in ('score', 'full'):
            comparisons.append(((prompt, selection), ('minimal', selection)))
    metrics = [f'{setting}_{metric}' for setting in ('default', 'noise01', 'long')
               for metric in ('score', 'cooperation', 'worst_score')]
    records = []
    for left_key, right_key in comparisons:
        left, right = groups.get(left_key, {}), groups.get(right_key, {})
        shared = sorted(set(left) & set(right))
        for metric in metrics:
            successful = [s for s in shared
                          if left[s][metric] is not None and right[s][metric] is not None]
            differences = [left[s][metric] - right[s][metric] for s in successful]
            records.append({
                'left': list(left_key), 'right': list(right_key), 'metric': metric,
                'available_paired_seeds': shared, 'successful_paired_seeds': successful,
                'left_missing_test_seeds': [s for s in shared if left[s][metric] is None],
                'right_missing_test_seeds': [s for s in shared if right[s][metric] is None],
                'differences': differences, 'mean': mean(differences) if differences else None,
                'bootstrap95': interval(differences),
            })
    result = {'all_main_cells_complete': analysis['all_main_cells_complete'],
              'endpoint_count': len(analysis['endpoints']), 'contrasts': records,
              'note': 'Left minus right; seed is the unit. Exploratory unadjusted 95% bootstrap intervals with at most five seeds. Missing tests are excluded pairwise, never zero-filled. Equal generations do not match calls/tokens; this estimates workflow effects, not an isolated mechanism effect.'}
    write_json(root / 'FACTOR_COMPARISONS.json', result)
    lines = ['# 提示词与选择方式的配对比较', '',
             f"主实验完整条件：{len(analysis['endpoints'])}/45；以下为当前快照。", '',
             '差值均为左侧减右侧；收益按每轮归一，合作率按比例。统计单位是生成种子。',
             '区间为未做多重比较校正的探索性 95% bootstrap 区间，每项最多五个种子。',
             '测试失败按配对剔除并单列，不补零；因此成功样本比较可能存在幸存者偏差。',
             '等代数比较未匹配请求数或 tokens，反映整套流程的效果。独立采样对照另见 CONTROL_REPORT.md。', '',
             '| 左侧 − 右侧 | 指标 | 成功/可配对种子 | 左/右测试缺失 | 平均差 | 95% 区间 |',
             '| --- | --- | ---: | ---: | ---: | --- |']
    for row in records:
        contrast = '/'.join(row['left']) + ' − ' + '/'.join(row['right'])
        estimate = 'NA' if row['mean'] is None else f"{row['mean']:.5f}"
        ci = row['bootstrap95']
        bounds = 'NA' if ci is None else f'[{ci[0]:.5f}, {ci[1]:.5f}]'
        lines.append(f"| {contrast} | {row['metric']} | {len(row['successful_paired_seeds'])}/{len(row['available_paired_seeds'])} | {len(row['left_missing_test_seeds'])}/{len(row['right_missing_test_seeds'])} | {estimate} | {bounds} |")
    (root / 'FACTOR_COMPARISONS.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f"Endpoints: {result['endpoint_count']}; contrasts: {len(records)}")
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    report(parser.parse_args().root)
