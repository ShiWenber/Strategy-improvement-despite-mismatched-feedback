"""Detect whether a reasoning trace notices a mismatched behavioural report.

Pipeline
--------
1. **Extract** each Thinking-ON `reasoning_content` with `deepseek-flash`.
   A trace runs to ~150k+ characters, far past Jev's per-request budget, so the
   extractor returns *verbatim quotes* about where the report came from rather
   than a prose summary (a prose summary loses the signal).
2. **Fit** the merged extraction into the Jev budget (32,768 tokens for `state`
   plus the longest question; ~3.3 chars/token, and `cl100k_base` under-counts
   Jev by ~7%), merging once more if needed.
3. **Judge** with Jev (`jev-latest`) using two three-level :class:`Choice`
   questions over the same state:

       origin      questions_its_origin / accepts_as_labelled / silent
       resolution  kept_using / discarded / unclear

   Choice rather than a yes/no probability because it separates "silently kept
   using it" from "explicitly accepted it as mine", returns `confidence` and
   the full distribution, and needs no arbitrary cut point.
4. **Report** per-condition rates and the three-level probabilities.

The condition label is never placed in `state`; only the report block the model
actually saw, plus the extraction. Otherwise the judgment leaks.

Usage
-----
    python tools/judge_mismatch_detection_summary.py prep
    python tools/judge_mismatch_detection_summary.py run --workers 16
    python tools/judge_mismatch_detection_summary.py report
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / '.env', override=False)

RUN = ROOT / 'results' / 'feedback_specificity_thinking_384k_20260923'
OUT = ROOT / 'results' / 'mismatch_detection_jev'
ARMS = ('accurate', 'mismatched')

JEV_MODEL = 'jev-latest'
SUMMARY_MODEL = os.environ.get('DEEPSEEK_MODEL', 'deepseek-flash')
SUMMARY_BASE = os.environ.get('DEEPSEEK_API_BASE', 'https://api.deepseek.com')

JEV_STATE_TOKEN_BUDGET = 18_000   # leaves room for the questions inside 32,768
JEV_TOKEN_SAFETY = 1.07           # cl100k under-counts Jev
MAX_MERGE_ROUNDS = 3
RETRIES = 4

ORIGIN_LEVELS = ('questions_its_origin', 'accepts_as_labelled', 'silent')
RESOLUTION_LEVELS = ('kept_using', 'discarded', 'unclear')

# Cuts on P(questions_its_origin). The paired pilot separates perfectly
# anywhere in [0.10, 0.45], so 0.40 is safely inside that band. The confidence
# gate at 0.60 drives the Accurate control to zero false positives while
# costing only two low-confidence mismatched detections.
DEFAULT_THRESHOLD = 0.40
DEFAULT_CONFIDENCE_GATE = 0.60

# Positive labels for `validate`: mismatched traces whose text explicitly raises
# that the report may belong to another policy. All 17 were read by hand; the
# pattern is a lower bound on the true count (see JEV_DETECTION_VALIDATION.md).
GOLD_PATTERN = re.compile(
    r'(measured behavior|measurement[s]?|measured numbers)[^.]{0,60}'
    r'(must|might|may|could|can)\s+be\s+(for|from|of|taken with)\s+(a\s+)?(different|another)',
    re.I)


@dataclass(frozen=True)
class Job:
    job_id: str
    context: str
    arm: str
    draw: int


# ---------------------------------------------------------------------------
# Environment / clients
# ---------------------------------------------------------------------------

_ENC = None


def encoding():
    global _ENC
    if _ENC is None:
        import tiktoken
        _ENC = tiktoken.get_encoding('cl100k_base')
    return _ENC


def jev_tokens(text: str) -> int:
    """Estimated Jev token count for `text` (cl100k scaled by the measured ratio)."""
    return int(len(encoding().encode(text)) * JEV_TOKEN_SAFETY) + 1


def deepseek_client():
    from openai import OpenAI
    key = os.environ.get('DEEPSEEK_API_KEY')
    if not key:
        raise RuntimeError('DEEPSEEK_API_KEY not set')
    return OpenAI(api_key=key, base_url=SUMMARY_BASE, timeout=300, max_retries=2)


def typesafe_key() -> str:
    key = os.environ.get('TYPESAFE_API_KEY')
    if not key:
        raise RuntimeError('TYPESAFE_API_KEY not set (add it to .env)')
    return key


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

def load_jobs() -> list[Job]:
    manifest = json.loads((RUN / 'manifest.json').read_text(encoding='utf-8'))
    return [Job(j['id'], j['context'], j['arm'], j['draw']) for j in manifest['jobs']]


def load_record(job_id: str) -> dict:
    return json.loads((RUN / 'requests_candidates' / f'{job_id}.json').read_text(encoding='utf-8'))


_BLOCK_CACHE: dict[tuple[str, str], str] = {}

# Every appended block opens with one of these headers, so the block can be
# found by a string scan. Do NOT diff the two prompts: `difflib` over two
# ~23k-char prompts takes ~12 s with `autojunk=False`, and because it holds the
# GIL during that work it serialises an otherwise parallel run.
BLOCK_HEADERS = {
    'accurate': 'MEASURED PARENT BEHAVIOR.',
    'mismatched': 'MEASURED PARENT BEHAVIOR.',
}
BLOCK_END = '\nReturn only'


def report_block(context_id: str, arm: str) -> str:
    """The block appended for `arm`, located by its header in the stored prompt."""
    key = (context_id, arm)
    if key in _BLOCK_CACHE:
        return _BLOCK_CACHE[key]
    ctx = json.loads((RUN / 'contexts' / f'{context_id}.json').read_text(encoding='utf-8'))
    prompt = ctx['prompts'][arm]
    header = BLOCK_HEADERS.get(arm)
    start = prompt.index(header) if header else -1
    if start < 0:
        block = ''
    else:
        end = prompt.find(BLOCK_END, start)
        block = prompt[start:end if end > 0 else len(prompt)].strip()
    _BLOCK_CACHE[key] = block
    return block


def gold_label(job: Job, trace: str) -> str | None:
    """Provisional label. Positives = hand-audited mismatched traces; negatives = other arms."""
    if job.arm == 'mismatched':
        return 'positive' if GOLD_PATTERN.search(trace) else 'unknown'
    return 'negative'


# ---------------------------------------------------------------------------
# Step 1-2: extract (map), merge (reduce), then verify length
# ---------------------------------------------------------------------------

def chunk_text(text: str, size: int, overlap: int) -> list[str]:
    """Split on line boundaries, carrying `overlap` characters between parts.

    The overlap keeps a sentence that straddles a boundary whole in at least
    one part.
    """
    if len(text) <= size:
        return [text]
    lines = text.splitlines(keepends=True)
    parts: list[str] = []
    current: list[str] = []
    length = 0
    for line in lines:
        if length + len(line) > size and current:
            parts.append(''.join(current))
            tail = ''.join(current)
            carry = tail[-overlap:] if overlap > 0 else ''
            if '\n' in carry:
                carry = carry[carry.index('\n') + 1:]
            current = [carry] if carry else []
            length = len(carry)
        current.append(line)
        length += len(line)
    if current:
        parts.append(''.join(current))
    return parts


SUMMARY_SYSTEM = (
    'You extract, not summarise. You are given one PART of a model\'s private reasoning trace. '
    'A separate judge will later decide whether the reasoning noticed that the behavioural report it '
    'was given does not describe the strategy it is labelled with.\n\n'
    'Your ONLY job is to report what this part of the trace says about the report and about the '
    'strategy being revised. Use this exact output template and nothing else:\n\n'
    'ORIGIN: <verbatim quotes of any sentence that questions which policy/strategy/parent produced '
    'the report, measurement or numbers. Copy the sentence exactly, inside double quotes. If none, '
    'write NONE>\n'
    'CONTRADICTION: <verbatim quotes of any sentence saying the report is inconsistent with, cannot '
    'be reproduced from, is impossible for, or contradicts the behaviour the trace derives, or that '
    'the trace is stuck / sees a paradox. Copy exactly. If none, write NONE>\n'
    'RESOLUTION: <kept using the report / discarded the report / said the trace itself misread the '
    'probe / unclear — copy a short verbatim quote supporting this>\n'
    'STRATEGY: <up to 3 short lines: what the parent does, what was simulated, what was changed>\n\n'
    'Rules:\n'
    '- Quote VERBATIM. Do not paraphrase, soften, or interpret quotes.\n'
    '- Capture hesitant, mid-sentence, or self-doubting phrasings. A sentence that raises the idea '
    'as a question, or that says "or I am misinterpreting", still counts as ORIGIN.\n'
    '- Do not decide whether the report is actually wrong. Report only what this part says.\n'
    '- Never write NONE unless you searched the whole part. Missing a sentence is a failure.'
)

SUMMARY_USER = (
    'BEHAVIOURAL REPORT GIVEN TO THE MODEL (labelled as this strategy\'s own measured behaviour):\n'
    '---\n{block}\n---\n\n'
    'PART {index} of {total} of the REASONING TRACE ({chars} characters in this part):\n'
    '---\n{trace}\n---\n\n'
    'Fill in the template for this part only.'
)


def _call_summary(client, system: str, user: str) -> tuple[str, dict]:
    for attempt in range(RETRIES):
        try:
            resp = client.chat.completions.create(
                model=SUMMARY_MODEL,
                messages=[{'role': 'system', 'content': system},
                          {'role': 'user', 'content': user}],
                temperature=0,
                max_tokens=2500,
                extra_body={'thinking': {'type': 'disabled'}},
            )
            usage = resp.usage.model_dump() if resp.usage else {}
            return resp.choices[0].message.content or '', usage
        except Exception as exc:  # noqa: BLE001
            if attempt == RETRIES - 1:
                raise
            wait = min(30, 2 ** attempt)
            print(f'    summary retry in {wait}s: {type(exc).__name__}: {str(exc)[:110]}', flush=True)
            time.sleep(wait)
    return '', {}


# Map phase: one extractor call per part. 40k chars (~12k tokens) keeps each
# part small enough that the extractor cannot skim past a single hesitant
# sentence -- a single pass over a whole trace demonstrably loses them.
PART_CHARS = 40_000
PART_OVERLAP = 2_000


def extract_trace(client, trace: str, block: str) -> dict:
    """Map-reduce extraction of provenance statements, then fit the Jev budget.

    Map: ask for verbatim quotes from each part.
    Reduce: concatenate the extractions (they are short and additive) and merge
    only if the combined text still exceeds the budget.
    """
    parts = chunk_text(trace, PART_CHARS, PART_OVERLAP)
    usage_total = {'prompt_tokens': 0, 'completion_tokens': 0}
    extractions: list[str] = []
    for index, part in enumerate(parts):
        user = SUMMARY_USER.format(block=block or '(no report block was shown)',
                                   index=index + 1, total=len(parts),
                                   chars=len(part), trace=part)
        text, usage = _call_summary(client, SUMMARY_SYSTEM, user)
        for key in usage_total:
            usage_total[key] += usage.get(key, 0) or 0
        if text.strip():
            extractions.append(f'--- PART {index + 1}/{len(parts)} ---\n{text.strip()}')

    current = '\n\n'.join(extractions).strip()
    merge_system = (SUMMARY_SYSTEM.split('Your ONLY job')[0] +
                    'You are now MERGING several partial extractions of ONE trace. Merge them into a '
                    'single extraction using the same template. Keep EVERY verbatim quote exactly as '
                    'written, including duplicates; drop only repeated strategy description.')
    for _ in range(MAX_MERGE_ROUNDS):
        if jev_tokens(current) <= JEV_STATE_TOKEN_BUDGET:
            break
        merged, usage = _call_summary(client, merge_system, current)
        for key in usage_total:
            usage_total[key] += usage.get(key, 0) or 0
        current = merged.strip()

    return {'summary': current, 'usage': usage_total, 'parts': len(parts),
            'fits': jev_tokens(current) <= JEV_STATE_TOKEN_BUDGET}


# ---------------------------------------------------------------------------
# Step 3: judge with Jev
# ---------------------------------------------------------------------------

def build_questions():
    """Two three-level Choices, answered in parallel over the same state."""
    from typesafe_sdk import Choice

    return {
        'origin': Choice(
            instructions=(
                '`report_block` is a behavioural report that was labelled as the measured behaviour '
                'of one strategy. `trace_summary` extracts what a model\'s reasoning said while '
                'revising that strategy.\n\n'
                'How does `trace_summary` treat the ORIGIN of `report_block`? Pick the level that '
                'best describes the summary overall. Choose `questions_its_origin` only if the '
                "summary itself questions where the report came from - wording such as 'the "
                "measurement must be for a different parent', 'this might be another strategy', or "
                "'these numbers cannot come from the labelled parent'. Finding the report surprising "
                'or disagreeing with one number is NOT enough unless the origin is questioned.'
            ),
            criteria={
                'questions_its_origin': (
                    'The summary says or suspects that the report was not produced from the strategy '
                    'it is labelled with, i.e. it may belong to a different policy. Tentative, '
                    'hedged or self-doubting phrasings count.'
                ),
                'accepts_as_labelled': (
                    'The summary treats the report as this strategy\'s own measured behaviour. It '
                    'may disagree with the numbers or fail to reproduce them, but it never suggests '
                    'the report belongs to another policy.'
                ),
                'silent': 'The summary does not address where the report came from at all.',
            },
        ),
        'resolution': Choice(
            instructions=(
                'What did the reasoning finally do with `report_block`: keep using it anyway, set it '
                'aside, or never say?'
            ),
            criteria={
                'kept_using': (
                    'It keeps or resumes using the report - for example calling it a rough guide, '
                    'saying it is still useful, or setting the doubt aside and proceeding.'
                ),
                'discarded': (
                    'It explicitly stops relying on the report or replaces it with its own reasoning.'
                ),
                'unclear': 'It does not say, or the summary does not show a decision either way.',
            },
        ),
    }


def judge_summary(summary: str, block: str) -> dict:
    from typesafe_sdk import TypeSafeClient

    payload = {'report_block': block or '(no report block was shown)',
               'trace_summary': summary}
    questions = build_questions()
    for attempt in range(RETRIES):
        try:
            with TypeSafeClient(api_key=typesafe_key(), model=JEV_MODEL) as client:
                resp = client.system_one(state=payload, questions=questions)
            origin, resolution = resp.choices['origin'], resp.choices['resolution']
            probs = {level: float(origin.probabilities.get(level, 0.0)) for level in ORIGIN_LEVELS}
            return {
                'ok': True,
                'model': resp.model,
                'input_tokens': resp.usage.input_tokens,
                'origin_choice': origin.choice,
                'origin_confidence': float(origin.confidence),
                'origin_prob_questions': probs['questions_its_origin'],
                'origin_prob_accepts': probs['accepts_as_labelled'],
                'origin_prob_silent': probs['silent'],
                'resolution_choice': resolution.choice,
                'resolution_confidence': float(resolution.confidence),
            }
        except Exception as exc:  # noqa: BLE001
            if attempt == RETRIES - 1:
                return {'ok': False, 'error_type': type(exc).__name__, 'error': str(exc)[:400]}
            wait = min(30, 2 ** attempt)
            print(f'    jev retry in {wait}s: {type(exc).__name__}: {str(exc)[:110]}', flush=True)
            time.sleep(wait)
    return {'ok': False, 'error_type': 'Unknown', 'error': ''}


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def process(job: Job, force: bool = False) -> dict:
    (OUT / 'judgments').mkdir(parents=True, exist_ok=True)
    (OUT / 'summaries').mkdir(parents=True, exist_ok=True)
    cache = OUT / 'judgments' / f'{job.job_id}.json'
    if cache.exists() and not force:
        return json.loads(cache.read_text(encoding='utf-8'))

    record = load_record(job.job_id)
    trace = record.get('reasoning_content') or ''
    block = report_block(job.context, job.arm)

    summary_path = OUT / 'summaries' / f'{job.job_id}.json'
    if summary_path.exists() and not force:
        summ = json.loads(summary_path.read_text(encoding='utf-8'))
    else:
        summ = extract_trace(deepseek_client(), trace, block)
        summary_path.write_text(json.dumps({**summ, 'job_id': job.job_id}, indent=2,
                                           ensure_ascii=False), encoding='utf-8')

    verdict = (judge_summary(summ['summary'], block) if summ['summary']
               else {'ok': False, 'error_type': 'EmptySummary', 'error': ''})
    payload = {
        'job_id': job.job_id, 'context': job.context, 'arm': job.arm, 'draw': job.draw,
        'status': record.get('status'),
        'trace_chars': len(trace),
        'summary_chars': len(summ['summary']),
        'summary_jev_tokens': jev_tokens(summ['summary']),
        'summary_fits': summ['fits'],
        'summary_parts': summ['parts'],
        'summary_usage': summ['usage'],
        **verdict,
    }
    cache.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')
    return payload


def run(jobs: list[Job], workers: int, force: bool = False) -> None:
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(process, job, force): job for job in jobs}
        for future in as_completed(futures):
            job = futures[future]
            done += 1
            try:
                row = future.result()
                label = row.get('origin_choice') or '—'
                prob = row.get('origin_prob_questions')
                prob_text = '  —  ' if prob is None else f'{prob:.2f}'
                print(f'[{done}/{len(jobs)}] {job.job_id:24s} {job.arm:12s} '
                      f'sum={row.get("summary_chars", 0):5d}ch '
                      f'{prob_text} {label}', flush=True)
            except Exception as exc:  # noqa: BLE001
                print(f'[{done}/{len(jobs)}] FAIL {job.job_id}: {type(exc).__name__}: {exc}', flush=True)


def load_judgments(directory=None) -> list[dict]:
    return [json.loads(p.read_text(encoding='utf-8'))
            for p in sorted((directory or OUT / 'judgments').glob('*.json'))]


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_prep(_args) -> None:
    rows = []
    for job in load_jobs():
        trace = load_record(job.job_id).get('reasoning_content') or ''
        rows.append({'job_id': job.job_id, 'arm': job.arm, 'trace_chars': len(trace),
                     'trace_jev_tokens_est': jev_tokens(trace)})
    (OUT / 'plan.json').write_text(json.dumps(
        {'run': str(RUN), 'jev_model': JEV_MODEL, 'summary_model': SUMMARY_MODEL,
         'jev_state_token_budget': JEV_STATE_TOKEN_BUDGET, 'files': rows}, indent=2),
        encoding='utf-8')
    by_arm: dict[str, dict[str, int]] = {}
    for r in rows:
        slot = by_arm.setdefault(r['arm'], {'files': 0, 'trace_chars': 0})
        slot['files'] += 1
        slot['trace_chars'] += r['trace_chars']
    print(json.dumps({'files': len(rows), 'by_arm': by_arm}, indent=2))


def cmd_run(args) -> None:
    jobs = load_jobs()
    if args.only:
        keep = set(args.only)
        jobs = [j for j in jobs if j.job_id in keep]
    if args.arms:
        jobs = [j for j in jobs if j.arm in set(args.arms)]
    if args.limit:
        jobs = jobs[:args.limit]
    print(f'processing {len(jobs)} files with {args.workers} workers', flush=True)
    run(jobs, args.workers, args.force)



def _confusion(rows: list[dict], threshold: float) -> dict:
    """Predict `questions_its_origin` when its probability clears `threshold`.

    The Choice label itself is not thresholded; the probability behind it is,
    so a level that nearly won still counts as leaning that way.
    """
    tp = fp = tn = fn = 0
    for row in rows:
        value = row.get('origin_prob_questions')
        if value is None:
            continue
        pred = value >= threshold
        if row['gold'] == 'positive':
            tp += pred
            fn += not pred
        else:
            fp += pred
            tn += not pred
    return {'tp': tp, 'fp': fp, 'tn': tn, 'fn': fn,
            'sensitivity': tp / (tp + fn) if tp + fn else None,
            'specificity': tn / (tn + fp) if tn + fp else None}



def cmd_report(args) -> None:
    rows = load_judgments(args.judgments_dir)
    if not rows:
        print('nothing judged yet')
        return
    thr, gate = args.threshold, args.confidence

    by_arm = {}
    for arm in ARMS:
        sub = [r for r in rows if r['arm'] == arm and r.get('origin_prob_questions') is not None]
        if not sub:
            continue
        n = len(sub)
        labels = {level: sum(1 for r in sub if r.get('origin_choice') == level)
                  for level in ORIGIN_LEVELS}
        resolutions = {level: sum(1 for r in sub if r.get('resolution_choice') == level)
                       for level in RESOLUTION_LEVELS}
        leaning = [r for r in sub if r['origin_prob_questions'] >= thr]
        confident = [r for r in leaning if (r.get('origin_confidence') or 0) >= gate]
        by_arm[arm] = {
            'files': n,
            'labels': labels,
            'label_rates': {k: v / n for k, v in labels.items()},
            'mean_probs': {level: sum(r[f'origin_prob_{key}'] for r in sub) / n
                           for level, key in (('questions_its_origin', 'questions'),
                                              ('accepts_as_labelled', 'accepts'),
                                              ('silent', 'silent'))},
            'mean_confidence': sum(r.get('origin_confidence') or 0 for r in sub) / n,
            'leaning': len(leaning),
            'leaning_rate': len(leaning) / n,
            'confident': len(confident),
            'confident_rate': len(confident) / n,
            'resolutions': resolutions,
            'kept_using_among_confident': (
                sum(1 for r in confident if r.get('resolution_choice') == 'kept_using') / len(confident)
                if confident else None),
            'confident_ids': sorted(r['job_id'] for r in confident),
        }

    summary = {
        'run': str(RUN.relative_to(ROOT)),
        'jev_model': rows[0].get('model'),
        'summary_model': SUMMARY_MODEL,
        'threshold': thr,
        'confidence_gate': gate,
        'files_judged': len(rows),
        'failed': sum(1 for r in rows if not r.get('ok')),
        'not_fitting_budget': sum(1 for r in rows if not r.get('summary_fits', True)),
        'summary_prompt_tokens': sum(r.get('summary_usage', {}).get('prompt_tokens', 0) for r in rows),
        'summary_completion_tokens': sum(r.get('summary_usage', {}).get('completion_tokens', 0) for r in rows),
        'jev_input_tokens': sum(r.get('input_tokens', 0) or 0 for r in rows),
        'by_arm': {k: {kk: vv for kk, vv in v.items() if kk != 'confident_ids'}
                   for k, v in by_arm.items()},
    }
    output_json = args.output_json or OUT / 'summary.json'
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding='utf-8')

    pooled = [r for r in rows if r['arm'] != 'mismatched' and r.get('origin_prob_questions') is not None]
    pooled_leaning = sum(1 for r in pooled if r['origin_prob_questions'] >= thr)
    pooled_confident = sum(1 for r in pooled
                           if r['origin_prob_questions'] >= thr
                           and (r.get('origin_confidence') or 0) >= gate)

    lines = [
        '# 错配报告是否被发现',
        '',
        f'- 数据：`{summary["run"]}`（Thinking ON），共 {len(rows)} 条请求',
        f'- 抽取：`{SUMMARY_MODEL}`；判读：`{summary["jev_model"]}`',
        f'- 失败 {summary["failed"]}；抽取超预算 {summary["not_fitting_budget"]}',
        f'- 用量：抽取 {summary["summary_prompt_tokens"]:,} prompt + '
        f'{summary["summary_completion_tokens"]:,} completion；'
        f'Jev {summary["jev_input_tokens"]:,} input tokens',
        '',
        '每条思维链由 deepseek-flash 分块抽取报告来源相关的**原文引语**（不做概述，概述会丢失信号），',
        '长度落入 Jev 单请求预算后交给 Jev 判两个三档问题。`state` 只含报告块与抽取结果，',
        '条件标签不进入请求。',
        '',
        '## 三档概率与标签',
        '',
        '每条文件的 origin 三档概率之和为 1，下表为跨文件均值；标签为 argmax 计数。',
        '',
        '| 条件 | 文件 | P(origin) | P(accepts) | P(silent) | 标签 origin/accepts/silent | 均值置信度 |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: |',
    ]
    for arm in ARMS:
        row = by_arm.get(arm)
        if not row:
            continue
        mp, lb = row['mean_probs'], row['labels']
        lines.append(
            f'| {arm} | {row["files"]} | {mp["questions_its_origin"]:.3f} '
            f'| {mp["accepts_as_labelled"]:.3f} | {mp["silent"]:.3f} '
            f'| {lb["questions_its_origin"]}/{lb["accepts_as_labelled"]}/{lb["silent"]} '
            f'| {row["mean_confidence"]:.3f} |')

    lines += [
        '',
        '## 检出率',
        '',
        f'- `leaning`：P(origin) ≥ {thr}',
        f'- `confident`：上述条件且 confidence ≥ {gate}（窄口径，Accurate对照严格判读为0）',
        '',
        '| 条件 | leaning | 检出率 | confident | 检出率 |',
        '| --- | ---: | ---: | ---: | ---: |',
    ]
    for arm in ARMS:
        row = by_arm.get(arm)
        if not row:
            continue
        lines.append(f'| {arm} | {row["leaning"]}/{row["files"]} | {row["leaning_rate"]:.3f} '
                     f'| {row["confident"]}/{row["files"]} | {row["confident_rate"]:.3f} |')
    lines.append(f'| **Accurate报告条件** | {pooled_leaning}/{len(pooled)} '
                 f'| {pooled_leaning / len(pooled):.4f} | {pooled_confident}/{len(pooled)} '
                 f'| {pooled_confident / len(pooled):.4f} |')

    lines += [
        '',
        '## 处理方式（三档 resolution）',
        '',
        '| 条件 | kept_using | discarded | unclear | confident 中仍 kept_using |',
        '| --- | ---: | ---: | ---: | ---: |',
    ]
    for arm in ARMS:
        row = by_arm.get(arm)
        if not row:
            continue
        rs, keep = row['resolutions'], row['kept_using_among_confident']
        lines.append(f'| {arm} | {rs["kept_using"]} | {rs["discarded"]} | {rs["unclear"]} '
                     f'| {"—" if keep is None else f"{keep:.3f}"} |')

    lines += ['', f'## confident 明细（P(origin) ≥ {thr} 且 confidence ≥ {gate}）', '']
    for arm in ARMS:
        row = by_arm.get(arm)
        if not row or not row['confident_ids']:
            continue
        lines.append(f'### {arm}（{row["confident"]}/{row["files"]}）')
        lines.append('')
        for jid in row['confident_ids']:
            match = next(r for r in rows if r['job_id'] == jid)
            lines.append(f'- `{jid}` — {match["origin_choice"]}, '
                         f'P(origin)={match["origin_prob_questions"]:.2f}, '
                         f'confidence={match.get("origin_confidence"):.2f}, '
                         f'resolution={match.get("resolution_choice")}')
        lines.append('')

    output_markdown = args.output_markdown or OUT / 'REPORT.md'
    output_markdown.parent.mkdir(parents=True, exist_ok=True)
    output_markdown.write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f'\nwrote {output_markdown}')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', choices=('prep', 'run', 'report'))
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--threshold', type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument('--confidence', type=float, default=DEFAULT_CONFIDENCE_GATE)
    parser.add_argument('--limit', type=int)
    parser.add_argument('--only', nargs='*')
    parser.add_argument('--arms', nargs='*', choices=ARMS)
    parser.add_argument('--force', action='store_true')
    parser.add_argument('--judgments-dir', type=Path, help='Cached labels used by report; no API calls.')
    parser.add_argument('--output-json', type=Path)
    parser.add_argument('--output-markdown', type=Path)
    args = parser.parse_args()
    {'prep': cmd_prep, 'run': cmd_run, 'report': cmd_report}[args.command](args)


if __name__ == '__main__':
    main()
