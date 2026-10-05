"""Populate the manuscript appendix directly from audited analysis artifacts."""
import json
from pathlib import Path


def render():
    root = Path('results/feedback_specificity_v2')
    a = json.loads((root/'ANALYSIS.json').read_text(encoding='utf-8'))
    r = json.loads((root/'role_analysis/ANALYSIS.json').read_text(encoding='utf-8'))
    assert not a['audit']['issues']
    def interval(row):
        return f"[{row['ci95'][0]:+.5f}, {row['ci95'][1]:+.5f}]"
    def estimate(row):
        return f"{row['mean']:+.5f} {interval(row)}"
    lines = ['<!-- BEGIN_GENERATED_STATISTICS -->', '**表 A1　主比较及六项预定次比较。**', '',
             '| 比较 | 每轮收益差 | 95% 区间 | 原始 p | Holm p |', '| --- | ---: | --- | ---: | ---: |']
    row = a['primary']
    lines.append(f"| 原始 Accurate−Mismatched（主） | {row['mean']:+.5f} | {interval(row)} | {row['sign_swap_p']:.5f} | — |")
    names = {'raw_accurate-score':'原始 Accurate−Score', 'raw_accurate-background':'原始 Accurate−Background',
             'raw_accurate-cooperation':'原始 Accurate−Cooperation', 'S3_accurate-score':'S3 Accurate−Score',
             'S3_accurate-parent':'S3 Accurate−父代', 'selection_interaction':'(S3 Accurate−Score)−(S2 Accurate−Score)'}
    for key, row in a['secondary'].items():
        lines.append(f"| {names[key]} | {row['mean']:+.5f} | {interval(row)} | {row['sign_swap_p']:.6f} | {row['holm_p']:.6f} |")
    lines += ['', '**表 A2　原始提案在三种收益设置中的增量与区间。**', '',
              '| 条件 | 默认 | 噪声 0.01 | 200 轮 |', '| --- | --- | --- | --- |']
    for arm, row in a['raw'].items():
        lines.append('| '+arm+' | '+' | '.join(estimate(row['metrics'][s+'/score']) for s in ('default','noise01','long'))+' |')
    lines += ['', '**表 A3　准确诊断组的独立行为变化。恢复时间单位为轮，合作单位为比例。**', '',
              '| 起点 | 恢复延迟 | 持续背叛下单方面合作变化 |', '| --- | --- | --- |']
    for prefix, label in [('controlled','给定合作历史'), ('natural','空历史')]:
        b = a['raw']['accurate']['behavior']
        lines.append('| '+label+' | '+estimate(b[prefix+'/recovery_time_capped'])+' | '+estimate(b[prefix+'/sustained_unilateral_cooperation_last5'])+' |')
    lines += ['', '**表 A4　新增固定池分析的配对差分。五条件等权；全部为事后、未校正区间。**', '',
              '| 规则/测试设置 | B−R | 门控 G−R | 机会 U−G | 排序 B−U |', '| --- | --- | --- | --- | --- |']
    for rule in ('S1','S2','S3'):
        for setting in ('default','noise01','long'):
            row = r['summaries'][f'pooled/{rule}/{setting}']
            lines.append(f'| {rule}/{setting} | '+' | '.join(estimate(row[k]) for k in ('total','gate','opportunity','ranking'))+' |')
    lines += ['', '**表 A5　S3 相对随机采用候选的默认测试增量，按反馈条件拆分。**', '',
              '| 条件 | B−R | 95% 区间 |', '| --- | ---: | --- |']
    for arm in a['raw']:
        row = r['summaries'][f'{arm}/S3/default']['total']
        lines.append(f"| {arm} | {row['mean']:+.5f} | {interval(row)} |")
    lines += ['', '其余行为指标、选择接受率和失败细分见 [完整补充表](../../results/feedback_specificity_v2/EXPLORATORY_TABLES.md)；新增分析全部政策与逐组对比见 [固定池结果](../../results/feedback_specificity_v2/role_analysis/REPORT.md)。', '<!-- END_GENERATED_STATISTICS -->']
    path = Path('docs/direct_reciprocity/FEEDBACK_ATTRIBUTION_DRAFT.md')
    text = path.read_text(encoding='utf-8')
    if '<!-- GENERATED_STATISTICS -->' in text:
        text = text.replace('<!-- GENERATED_STATISTICS -->', '\n'.join(lines))
    else:
        begin = text.index('<!-- BEGIN_GENERATED_STATISTICS -->')
        end = text.index('<!-- END_GENERATED_STATISTICS -->')+len('<!-- END_GENERATED_STATISTICS -->')
        text = text[:begin]+'\n'.join(lines)+text[end:]
    path.write_text(text, encoding='utf-8')
    print(path)


if __name__ == '__main__':
    render()
