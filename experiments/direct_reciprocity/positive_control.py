"""Known-defect positive control for the feedback-specificity experiment.

Purpose
-------
The frozen v2 experiment found no stable mean advantage for an accurate
behavioural report over a mismatched one.  That null is compatible with three
explanations:

    H1  the model used the report but exact correspondence is not required;
    H2  the model used only report content that is redundant with the source;
    H3  the model largely ignored the report and edited from source alone.

A positive control separates H3 from H1/H2 by supplying a parent with a
*declared, measured* defect, a *known* repair, and a report that either
describes the defect (accurate) or describes the repaired sibling (mismatched).

Design
------
Every condition shares one defective parent p*.  Only the appended block changes:

    accurate    -> D(p*)                the report of the defective parent
    mismatched  -> D(r*)                the report of the declared repair r*
    score       -> (no block)           source-only baseline

r* is the same policy family with the defect axis corrected, so the mismatch is
the tightest available contrast: identical code style, identical report format,
different defect-relevant numbers.  Two axes are used:

    recovery      p* restores mutual cooperation slowly; r* restores it quickly
    exploitation  p* is exploited under sustained defection; r* defends

Outcomes are read on the same measurement assets the report itself is built
from (F probes) plus the frozen holdout panel H.  The repair direction is known
before generation, so the control is directional, not merely "better/worse".

Nothing here mutates the frozen v2 pipeline: this module only imports read-only
helpers.  ``experiments/direct_reciprocity/specificity*.py`` and the hash-locked
implementation files are untouched.

Usage
-----
    python -m experiments.direct_reciprocity.positive_control calibrate
    python -m experiments.direct_reciprocity.positive_control verify
    python -m experiments.direct_reciprocity.positive_control run --repeats 3
    python -m experiments.direct_reciprocity.positive_control analyze
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from dataclasses import replace
import json
from pathlib import Path
import re
from statistics import mean
import time

from .core import Config, Policy, digest, match, versus
from .baselines import TRAIN
from .run import Generator, read_json, write_json
from .prompts import build_prompt
from .specificity_assets import probes, diagnostic_block, panel, tokenizer

ROOT = Path('results/positive_control_20260929')
CONDITIONS = ('accurate', 'mismatched', 'score')
MODEL, PROVIDER = 'deepseek-flash', 'deepseek'
CALIBRATION_REPEATS = 5
REPORT_PROBES = ('one_D_TFT', 'four_D_TFT', 'four_D_ALLC')


# ---------------------------------------------------------------------------
# Policy families.  Both are deterministic and use only history, so the model
# cannot see any per-run randomness in the parent.  The defect is a numeric
# constant whose behavioural consequence requires simulation to evaluate.
# ---------------------------------------------------------------------------

def weighted_code(window, decay, threshold):
    """Exponentially weighted defection tally; retaliate above a threshold.

    Low threshold  -> sustained punishment after a short burst (recovery defect)
    High threshold -> tolerates defection, so it is exploited
    """
    return (
        "def strategy(history, rng):\n"
        "    if not history:\n"
        "        return 'C'\n"
        "    d = 0.0\n"
        f"    for x, y in history[-{window}:]:\n"
        f"        d = d * {decay} + (1.0 if y == 'D' else 0.0)\n"
        f"    return 'D' if d > {threshold} else 'C'\n"
    )


def window_code(window, needed):
    """Retaliate only when enough recent opponent moves were defections."""
    return (
        "def strategy(history, rng):\n"
        "    if not history:\n"
        "        return 'C'\n"
        f"    recent = history[-{window}:]\n"
        f"    if sum(1 for x, y in recent if y == 'D') >= {needed}:\n"
        "        return 'D'\n"
        "    return 'C'\n"
    )


FAMILIES = {
    'weighted': lambda **p: weighted_code(p['window'], p['decay'], p['threshold']),
    'window': lambda **p: window_code(p['window'], p['needed']),
}


def code_for(spec):
    return FAMILIES[spec['family']](**spec['params'])


def policy_for(spec, which='defect'):
    params = spec['repair'] if (which == 'repair' and 'repair' in spec) else spec['params']
    return Policy(f"{spec['id']}-{which}", code_for({**spec, 'params': params}))


# ---------------------------------------------------------------------------
# Candidate defect / repair pairs.  Each pair is verified offline before use:
# the defect must be measurable, the repair must remove it, and the repair must
# not lower holdout payoff.  See ``calibrate`` for the sweep.
# ---------------------------------------------------------------------------

def sweep_candidates():
    """Parameter grid used by ``calibrate`` to discover usable defect/repair pairs.

    Each row is a single policy; pairs are derived from the measured table.
    """
    rows = []
    for window in (12, 16, 20):
        for decay in (0.88, 0.92):
            for threshold in (0.20, 0.30, 0.45, 0.70, 1.00, 1.40, 2.00, 2.80, 4.00):
                rows.append(dict(id=f'w{window}-d{int(decay*100)}-t{int(threshold*100)}',
                                 family='weighted',
                                 params=dict(window=window, decay=decay, threshold=threshold)))
    for window in (12, 16, 20):
        for needed in (2, 3, 4, 5, 6, 8, 10, 12, 14):
            rows.append(dict(id=f'win{window}-n{needed}', family='window',
                             params=dict(window=window, needed=needed)))
    return rows


def behaviour(candidate, cfg):
    """Defect-relevant behaviour from the same F probes used to build reports.

    ``exploitation`` is cooperation *during* a sustained defection (rounds 4-23
    of the burst), not the last five rounds: under an unbroken defection every
    tally-based policy retaliates eventually, so a final-window statistic is
    identically zero and cannot separate an exploited parent from a defended one.
    """
    diagnostic = probes(candidate, cfg, 'F')
    recovery = mean(diagnostic[name]['mean']['recovery_time_capped'] for name in REPORT_PROBES)
    not_recovered = mean(diagnostic[name]['mean']['not_recovered'] for name in REPORT_PROBES)
    exploitation = diagnostic['sustained_D']['mean']['own_cooperation_after4']
    return {'recovery_time': recovery, 'not_recovered': not_recovered,
            'exploitation': exploitation, 'diagnostic': diagnostic}


def holdout_payoff(candidate, cfg, repeats=20):
    result = versus(candidate, [p for _, p in panel('H')], replace(cfg, repeats=repeats),
                    'positive-control-H')
    return result['score'] / cfg.rounds


def cfg_for(spec, index):
    return Config(seed=9001 + index)


# Measurement is the expensive part (opcode-traced play), so results are memoised
# within a process and calibration is cached on disk across processes.
_MEASURED = {}


def measure_policy(candidate, cfg, repeats=20):
    key = (candidate.key, cfg.seed, repeats)
    if key not in _MEASURED:
        row = behaviour(candidate, cfg)
        row['holdout'] = holdout_payoff(candidate, cfg, repeats)
        _MEASURED[key] = row
    return _MEASURED[key]


def measure(spec, cfg, which, repeats=20):
    return measure_policy(policy_for(spec, which), cfg, repeats)


def verify_pair(spec, cfg, min_gap=3.0, min_exploit_gap=0.15):
    """Return (axis, defect_row, repair_row) when the declared pair is usable."""
    if 'repair' not in spec:
        return None
    defect, repair = measure(spec, cfg, 'defect'), measure(spec, cfg, 'repair')
    if spec['axis'] == 'recovery':
        gap = defect['recovery_time'] - repair['recovery_time']
        axis = 'recovery' if gap >= min_gap else None
    else:
        gap = defect['exploitation'] - repair['exploitation']
        axis = 'exploitation' if gap >= min_exploit_gap else None
    if axis is None or repair['holdout'] + 1e-9 < defect['holdout']:
        return None
    return axis, defect, repair


def calibrate(refresh=False, root=ROOT):
    """Screen every sweep point once at reduced holdout precision; cache on disk.

    The sweep only ranks candidates, so it uses ``CALIBRATION_REPEATS`` holdout
    repetitions; ``verify`` confirms the retained pairs at the full 20.
    """
    path = Path(root) / 'CALIBRATION.json'
    if path.exists() and not refresh:
        return read_json(path)['rows']
    grid = sweep_candidates()
    rows = []
    for index, spec in enumerate(grid):
        cfg = Config(seed=9001 + index % 50)
        measured = measure(spec, cfg, 'defect', CALIBRATION_REPEATS)
        rows.append({'id': spec['id'], 'family': spec['family'], 'params': spec['params'],
                     'recovery_time': measured['recovery_time'],
                     'not_recovered': measured['not_recovered'],
                     'exploitation': measured['exploitation'],
                     'holdout': measured['holdout']})
        print(json.dumps({'swept': len(rows), 'of': len(grid)}), flush=True)
    write_json(path, {'rows': rows, 'sweep': grid, 'holdout_repeats': CALIBRATION_REPEATS,
                      'swept_at': time.time()})
    return rows


# ---------------------------------------------------------------------------
# Frozen selection (populated after calibrate; see SELECTED.json).
# ---------------------------------------------------------------------------

SELECTION = Path(__file__).with_name('positive_control_selected.json')


def load_selected():
    return read_json(SELECTION)['specs']


def build_selection(min_rec_gap=6.0, min_exp_gap=0.20, h_tolerance=0.005):
    """Derive defect/repair pairs from the sweep, keeping the largest separations.

    A pair is usable when the declared repair moves the defect axis by at least
    ``min_*_gap`` without lowering holdout payoff by more than ``h_tolerance``.
    """
    rows = calibrate()
    specs = []

    def add(spec, defect_row, repair_row, axis, gap):
        specs.append({**spec, 'axis': axis, 'repair': repair_row['params'],
                      'calibration': {'defect': {k: defect_row[k] for k in
                                                 ('recovery_time', 'exploitation', 'holdout')},
                                      'repair': {k: repair_row[k] for k in
                                                 ('recovery_time', 'exploitation', 'holdout')},
                                      'gap': gap,
                                      'axis_field': 'recovery_time' if axis == 'recovery' else 'exploitation'}})

    # Recovery defects: weighted family, group by (window, decay), sweep threshold up.
    groups = {}
    for row in rows:
        if row['family'] == 'weighted':
            groups.setdefault((row['params']['window'], row['params']['decay']), []).append(row)
    candidates = []
    for key, group in groups.items():
        group.sort(key=lambda r: r['params']['threshold'])
        for defect_row in group:
            for repair_row in group:
                if repair_row['params']['threshold'] <= defect_row['params']['threshold']:
                    continue
                gap = defect_row['recovery_time'] - repair_row['recovery_time']
                if gap < min_rec_gap or repair_row['holdout'] < defect_row['holdout'] - h_tolerance:
                    continue
                candidates.append((gap, defect_row, repair_row))
    candidates.sort(key=lambda item: -item[0])
    used_groups = set()
    for gap, defect_row, repair_row in candidates:
        key = (defect_row['params']['window'], defect_row['params']['decay'])
        if key in used_groups:
            continue
        used_groups.add(key)
        add({'id': 'rec-' + defect_row['id'], 'family': 'weighted',
             'params': defect_row['params']}, defect_row, repair_row, 'recovery', gap)
        if len(used_groups) >= 4:
            break

    # Exploitation defects: window family, sweep `needed` down.
    groups = {}
    for row in rows:
        if row['family'] == 'window':
            groups.setdefault(row['params']['window'], []).append(row)
    candidates = []
    for key, group in groups.items():
        group.sort(key=lambda r: r['params']['needed'])
        for defect_row in group:
            for repair_row in group:
                if repair_row['params']['needed'] >= defect_row['params']['needed']:
                    continue
                gap = defect_row['exploitation'] - repair_row['exploitation']
                if gap < min_exp_gap or repair_row['holdout'] < defect_row['holdout'] - h_tolerance:
                    continue
                candidates.append((gap, defect_row, repair_row))
    candidates.sort(key=lambda item: -item[0])
    used_groups = set()
    for gap, defect_row, repair_row in candidates:
        key = defect_row['params']['window']
        if key in used_groups:
            continue
        used_groups.add(key)
        add({'id': 'exp-' + defect_row['id'], 'family': 'window',
             'params': defect_row['params']}, defect_row, repair_row, 'exploitation', gap)
        if len(used_groups) >= 4:
            break

    record = {'built_at': time.time(), 'sweep_rows': len(rows), 'specs': specs}
    write_json(SELECTION, record)
    return specs


# ---------------------------------------------------------------------------
# Prompt construction.  Only the appended block changes across conditions.
# ---------------------------------------------------------------------------

def base_prompt(parent, cfg):
    return build_prompt(cfg, parent) + '\n'


METRIC_KEYS = ('recovery_time', 'not_recovered', 'exploitation', 'holdout')


def spec_metrics(spec, cfg, which, repeats=20):
    """Prefer the full-precision numbers frozen by ``verify`` over remeasuring."""
    verified = spec.get('verified', {})
    if which in verified:
        return {k: verified[which][k] for k in METRIC_KEYS}
    row = measure(spec, cfg, which, repeats)
    return {k: row[k] for k in METRIC_KEYS}


def condition_block(spec, cfg, condition, cache):
    if condition == 'score':
        return ''
    which = 'defect' if condition == 'accurate' else 'repair'
    if which not in cache:
        cache[which] = diagnostic_block(measure(spec, cfg, which)['diagnostic'])
    return cache[which]


def build_units(specs):
    units = []
    for index, spec in enumerate(specs):
        cfg = cfg_for(spec, index)
        parent = policy_for(spec, 'defect')
        repair = policy_for(spec, 'repair')
        cache = {}
        blocks = {c: condition_block(spec, cfg, c, cache) for c in CONDITIONS}
        base = base_prompt(parent, cfg)
        units.append({
            'id': spec['id'], 'index': index, 'axis': spec['axis'],
            'family': spec['family'], 'params': spec['params'], 'repair_params': spec['repair'],
            'axis_field': spec.get('calibration', {}).get('axis_field'),
            'cfg': {'seed': cfg.seed},
            'parent': {'name': parent.name, 'code': parent.code},
            'repair_policy': {'name': repair.name, 'code': repair.code},
            'parent_metrics': spec_metrics(spec, cfg, 'defect'),
            'repair_metrics': spec_metrics(spec, cfg, 'repair'),
            'blocks': blocks,
            'prompts': {c: ((base + blocks[c]) if blocks[c] else base) + '\nReturn only the new strategy source.\n'
                        for c in CONDITIONS},
        })
    return units


def freeze(root=ROOT):
    root = Path(root)
    specs = load_selected()
    units = build_units(specs)
    enc = tokenizer()
    manifest = {
        'version': 'positive-control-v1', 'provider': PROVIDER, 'model': MODEL,
        'max_tokens': 6000, 'thinking': 'disabled',
        'conditions': list(CONDITIONS),
        'reused_assets': 'specificity_assets.probes / diagnostic_block / panel(H)',
        'note': ('Hand-built declared defects; frozen v2 pipeline untouched. '
                 'Score has no appended block, so it is the source-only baseline.'),
        'units': [{**{k: u[k] for k in ('id', 'index', 'axis', 'family', 'params',
                                       'repair_params', 'cfg', 'parent', 'repair_policy',
                                       'parent_metrics', 'repair_metrics')},
                   'block_tokens': {c: len(enc.encode(u['blocks'][c])) for c in CONDITIONS},
                   'prompt_tokens': {c: len(enc.encode(u['prompts'][c])) for c in CONDITIONS}}
                  for u in units],
        'frozen_at': time.time(),
    }
    write_json(root / 'manifest.json', manifest)
    for unit in units:
        write_json(root / 'units' / (unit['id'] + '.json'), unit)
    return manifest


def load_units(root=ROOT):
    root = Path(root)
    manifest = read_json(root / 'manifest.json')
    return [read_json(root / 'units' / (u['id'] + '.json')) for u in manifest['units']]


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

def job_id(unit_id, condition, repeat):
    return f'{unit_id}__{condition}__r{repeat}'


def planned_jobs(units, repeats):
    return [{'id': job_id(u['id'], c, r), 'unit': u['id'], 'condition': c, 'repeat': r}
            for u in units for c in CONDITIONS for r in range(repeats)]


def run(root=ROOT, repeats=3, only=None):
    root = Path(root)
    units = {u['id']: u for u in load_units(root)}
    jobs = planned_jobs(list(units.values()), repeats)
    if only:
        jobs = [j for j in jobs if j['unit'] in only]
    config = Config(seed=0)
    generator = Generator(root / 'requests', PROVIDER, MODEL, config.temperature)
    outcomes = []
    for job in jobs:
        unit = units[job['unit']]
        out = root / 'candidates' / (job['id'] + '.json')
        if out.exists():
            outcomes.append({'id': job['id'], 'cached': True})
            continue
        prompt = unit['prompts'][job['condition']]
        child = generator.generate(job['id'], prompt, config)
        write_json(out, {'id': job['id'], 'unit': job['unit'], 'condition': job['condition'],
                         'repeat': job['repeat'], 'child': None if child is None else
                         {'name': child.name, 'code': child.code}, 'valid': child is not None})
        outcomes.append({'id': job['id'], 'valid': child is not None})
        print(json.dumps(outcomes[-1]), flush=True)
    write_json(root / 'RUN_STATUS.json', {'completed': len(outcomes), 'total': len(jobs),
                                          'repeats': repeats, 'updated_at': time.time()})
    return outcomes


# ---------------------------------------------------------------------------
# Thinking mode.  The OFF run leaves no record of *why* a candidate was
# produced, so report use had to be inferred from behaviour alone -- which is
# exactly the inference that cannot be defended.  Native reasoning makes it
# directly measurable: if the model reads the report, its trace should contain
# the report's own probe vocabulary and the report's own numbers.
#
# Two markers, with different jobs:
#
#   probe names    appear ONLY in a report (never in the parent source or the
#                  base instruction), so they cleanly separate "a report was
#                  present" (accurate, mismatched) from "no report" (score).
#   report values  parent-block numbers versus repair-block numbers.  If traces
#                  cite the numbers of the block they were actually given, the
#                  model read that specific block -- an internal validity check
#                  that no behavioural outcome can provide.
#
# The score condition doubles as the false-positive baseline for both markers.
# ---------------------------------------------------------------------------

THINKING_ROOT = Path('results/positive_control_thinking_20260930')
THINKING_MAX_TOKENS = 384000
THINKING_EFFORT = 'high'
PROBE_NAMES = ('one_D_TFT', 'four_D_TFT', 'four_D_ALLC', 'sustained_D', 'periodic_D')
NUMBER = re.compile(r'\d+(?:\.\d+)?')
VALUE_PAIR = re.compile(r'([a-z_0-9]+)=([0-9]+\.[0-9]+)')


def thinking_spec(prompt):
    return dict(provider=PROVIDER, model=MODEL, prompt=prompt, temperature=1,
                max_tokens=THINKING_MAX_TOKENS, reasoning_effort=THINKING_EFFORT,
                extra_body={'thinking': {'type': 'enabled'}},
                stream=True, stream_options={'include_usage': True})


def prepare_thinking(root=THINKING_ROOT, source=ROOT):
    """Copy the frozen units so the thinking run is self-contained and hashable."""
    root, source = Path(root), Path(source)
    if (root / 'manifest.json').exists():
        return read_json(root / 'manifest.json')
    manifest = read_json(source / 'manifest.json')
    write_json(root / 'manifest.json', {
        **manifest, 'thinking': 'enabled', 'reasoning_effort': THINKING_EFFORT,
        'max_tokens': THINKING_MAX_TOKENS, 'source_root': str(source),
        'source_manifest_hash': digest((source / 'manifest.json').read_text(encoding='utf-8')),
        'prepared_at': time.time()})
    for item in manifest['units']:
        unit = read_json(source / 'units' / (item['id'] + '.json'))
        write_json(root / 'units' / (unit['id'] + '.json'), unit)
    return read_json(root / 'manifest.json')


def receive_stream(stream, sink):
    """Collect content and native reasoning; every chunk is archived verbatim."""
    content, reasoning = [], []
    usage, finish, response_id, model = None, None, None, None
    for chunk in stream:
        sink.write(json.dumps(chunk.model_dump(), ensure_ascii=False) + '\n')
        sink.flush()
        response_id = chunk.id or response_id
        model = chunk.model or model
        if chunk.usage is not None:
            usage = chunk.usage.model_dump()
        for choice in chunk.choices:
            if choice.index != 0:
                raise RuntimeError('Unexpected multiple choices')
            delta = choice.delta
            reasoning.append(getattr(delta, 'reasoning_content', None) or '')
            content.append(delta.content or '')
            if choice.finish_reason is not None:
                finish = choice.finish_reason
    if finish is None:
        raise RuntimeError('Stream ended without finish_reason; uncertain request, never retry silently')
    return dict(content=''.join(content), reasoning_content=''.join(reasoning), usage=usage,
                finish_reason=finish, response_id=response_id, returned_model=model)


def _validate_child(code, cfg):
    """Strip fences and check the candidate executes; mirrors the OFF validation."""
    if code.strip().startswith('```'):
        lines = code.strip().splitlines()
        if lines and lines[-1].strip() == '```':
            code = '\n'.join(lines[1:-1])
    policy = Policy('thinking-child', code)
    try:
        policy.compile()
        for opponent in TRAIN:
            match(policy, opponent, replace(cfg, repeats=1), 12345)
    except Exception as exc:
        return None, f'{type(exc).__name__}: {exc}'
    return policy, None


def thinking_job(arg):
    root, unit, condition, repeat = arg
    root = Path(root)
    job = job_id(unit['id'], condition, repeat)
    out = root / 'candidates' / (job + '.json')
    if out.exists():
        return {'id': job, 'cached': True}
    spec = thinking_spec(unit['prompts'][condition])
    fingerprint = digest(json.dumps(spec, sort_keys=True))
    path = root / 'requests' / (job + '.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    record = None
    if path.exists():
        previous = read_json(path)
        if previous.get('fingerprint') != fingerprint:
            raise RuntimeError('Request identity collision: ' + job)
        if previous.get('status') == 'requested':
            # Ambiguous outcome: refuse rather than risk a silent duplicate.
            raise RuntimeError('Uncertain request; inspect before retrying: ' + job)
        if previous.get('status') == 'received' and previous.get('content'):
            record = previous
        # api_error / empty response: the failure is known, so re-issuing is safe.
    if record is None:
        from openai import OpenAI
        import httpx
        from ..config.load_env import get_api_key, get_base_url
        key = get_api_key(PROVIDER)
        if not key:
            raise RuntimeError('Provider not configured')
        record = dict(spec, fingerprint=fingerprint, status='requested', started_at=time.time())
        write_json(path, record)
        events = root / 'streams' / (job + '.jsonl')
        events.parent.mkdir(parents=True, exist_ok=True)
        try:
            with OpenAI(api_key=key, base_url=get_base_url(PROVIDER), max_retries=0,
                        timeout=httpx.Timeout(3600, connect=30)) as client:
                with events.open('w', encoding='utf-8') as sink:
                    with client.chat.completions.create(
                            model=MODEL, messages=[{'role': 'user', 'content': spec['prompt']}],
                            temperature=1, max_tokens=THINKING_MAX_TOKENS,
                            reasoning_effort=THINKING_EFFORT,
                            extra_body={'thinking': {'type': 'enabled'}},
                            stream=True, stream_options={'include_usage': True}) as stream:
                        record.update(receive_stream(stream, sink))
            record.update(status='received', finished_at=time.time())
            write_json(path, record)
        except Exception as exc:
            record.update(status='api_error', error_type=type(exc).__name__,
                          error_message=str(exc)[:500], finished_at=time.time())
            write_json(path, record)
            raise
    cfg = Config(seed=unit['cfg']['seed'])
    policy, error = _validate_child(record.get('content') or '', cfg)
    write_json(out, {'id': job, 'unit': unit['id'], 'condition': condition, 'repeat': repeat,
                     'child': None if policy is None else {'name': policy.name, 'code': policy.code},
                     'valid': policy is not None, 'validation_error': error,
                     'reasoning_chars': len(record.get('reasoning_content') or ''),
                     'usage': record.get('usage')})
    return {'id': job, 'valid': policy is not None,
            'reasoning_chars': len(record.get('reasoning_content') or '')}


def run_thinking(root=THINKING_ROOT, repeats=3, workers=6, only=None):
    root = Path(root)
    # The thinking run is a separate experiment; writing it into the frozen OFF
    # root would silently no-op every job and clobber the OFF status file.
    if root.resolve() == Path(ROOT).resolve():
        raise RuntimeError('Refusing to run thinking mode against the OFF root; '
                           'pass --root ' + str(THINKING_ROOT))
    prepare_thinking(root)
    units = {u['id']: u for u in load_units(root)}
    jobs = [j for j in planned_jobs(list(units.values()), repeats)
            if not only or j['unit'] in only]
    arguments = [(root, units[j['unit']], j['condition'], j['repeat']) for j in jobs]
    outcomes, errors = [], []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(thinking_job, arg): arg for arg in arguments}
        for future in as_completed(futures):
            arg = futures[future]
            label = job_id(arg[1]['id'], arg[2], arg[3])
            try:
                result = future.result()
                outcomes.append(result)
                print(json.dumps(result), flush=True)
            except Exception as exc:
                errors.append({'id': label, 'type': type(exc).__name__, 'message': str(exc)[:300]})
                print(json.dumps({'id': label, 'error': type(exc).__name__}), flush=True)
    write_json(root / 'RUN_STATUS.json', {'completed': len(outcomes), 'failed': len(errors),
                                          'total': len(arguments), 'repeats': repeats,
                                          'errors': errors, 'updated_at': time.time()})
    if errors:
        raise RuntimeError(f'{len(errors)} thinking requests failed; re-run to retry known failures')
    return outcomes


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def _policy_metrics(arg):
    """Worker: measure one reference policy (parent or declared repair)."""
    key, seed, code = arg
    cfg = Config(seed=seed)
    policy = Policy(key, code)
    row = behaviour(policy, cfg)
    return {'key': key, 'holdout': holdout_payoff(policy, cfg),
            'recovery_time': row['recovery_time'], 'exploitation': row['exploitation']}


def _candidate_metrics(arg):
    """Worker: measure one generated candidate.  Opcode-traced play is the
    expensive part, so all measurement is parallelised across processes."""
    seed, record_path, unit_id = arg
    record = read_json(record_path)
    cfg = Config(seed=seed)
    if not record.get('valid') or not record.get('child'):
        return {'id': record['id'], 'condition': record['condition'],
                'repeat': record['repeat'], 'valid': False}
    child = Policy(**record['child'])
    try:
        child_behaviour = behaviour(child, cfg)
        child_holdout = holdout_payoff(child, cfg)
    except Exception as exc:  # execution failure: excluded and flagged
        return {'id': record['id'], 'condition': record['condition'],
                'repeat': record['repeat'], 'valid': False, 'error_type': type(exc).__name__}
    return {'id': record['id'], 'condition': record['condition'], 'repeat': record['repeat'],
            'valid': True, 'holdout': child_holdout,
            'recovery_time': child_behaviour['recovery_time'],
            'exploitation': child_behaviour['exploitation']}


def evaluate_candidates(root=ROOT, workers=8):
    root = Path(root)
    units = load_units(root)
    policy_jobs, candidate_jobs = [], []
    for unit in units:
        seed = unit['cfg']['seed']
        for item in (unit['parent'], unit['repair_policy']):
            policy_jobs.append((f"{unit['id']}:{item['name']}", seed, item['code']))
        candidate_jobs += [(seed, path, unit['id'])
                           for path in sorted((root / 'candidates').glob(unit['id'] + '__*.json'))]
    with ProcessPoolExecutor(max_workers=workers) as executor:
        measured_policies = list(executor.map(_policy_metrics, policy_jobs))
        measured_candidates = list(executor.map(_candidate_metrics, candidate_jobs))
    policy_by_key = {row['key']: row for row in measured_policies}
    candidate_by_id = {row['id']: row for row in measured_candidates}

    results = []
    for unit, parent_row, repair_row in zip(units, measured_policies[0::2], measured_policies[1::2]):
        rows = []
        for path in sorted((root / 'candidates').glob(unit['id'] + '__*.json')):
            row = candidate_by_id[path.stem]
            if row.get('valid'):
                row = dict(row)
                row['d_holdout'] = row['holdout'] - parent_row['holdout']
                row['d_recovery'] = row['recovery_time'] - parent_row['recovery_time']
                row['d_exploitation'] = row['exploitation'] - parent_row['exploitation']
            rows.append(row)
        results.append({
            'unit': unit['id'], 'axis': unit['axis'], 'family': unit['family'],
            'params': unit['params'], 'repair_params': unit['repair_params'],
            'parent': parent_row, 'repair': repair_row, 'candidates': rows,
        })
    write_json(root / 'EVALUATED.json', {'units': results, 'evaluated_at': time.time(),
                                         'policy_keys': sorted(policy_by_key)})
    return results


def repair_gain(row, axis):
    """Signed progress toward the declared repair (positive is improvement)."""
    return -row['d_recovery'] if axis == 'recovery' else -row['d_exploitation']


def condition_markers(unit, condition, text):
    """Measure report use in one reasoning trace, against the block actually shown.

    Three markers, in decreasing reliability:

    ``probe_names``   Report-only vocabulary, counted against the condition's own
                     block.  0 means the trace never names a probe, which is what
                     a report-free prompt should give.  Validated to separate
                     perfectly (5/5 with a report, 0/5 without).
    ``exact_cited``   Exact ``field=value`` strings copied from the given block.
                     Far more specific than bare numbers, which collide with
                     ordinary reasoning ("0.25", "20 rounds").
    ``parent_only_cited`` / ``repair_only_cited``
                     Bare-number hits.  NOISY: the report-free ``score`` arm still
                     scores on small decimals, so this is only ever read against
                     the ``score`` baseline, never on its own.
    """
    block = unit['blocks'].get(condition) or ''
    pairs = sorted({m.group(0) for m in VALUE_PAIR.finditer(block)})
    parent_values = {float(m.group(2)) for m in VALUE_PAIR.finditer(unit['blocks']['accurate'])}
    repair_values = {float(m.group(2)) for m in VALUE_PAIR.finditer(unit['blocks']['mismatched'])}
    cited = {float(t) for t in NUMBER.findall(text)}
    return {
        'probe_names': sum(name in text for name in PROBE_NAMES),
        'exact_cited': sum(1 for pair in pairs if pair in text),
        'exact_total': len(pairs),
        'parent_only_cited': len((parent_values - repair_values) & cited),
        'parent_only_total': len(parent_values - repair_values),
        'repair_only_cited': len((repair_values - parent_values) & cited),
        'repair_only_total': len(repair_values - parent_values),
        'trace_chars': len(text),
    }


def analyze_reasoning(root=THINKING_ROOT):
    """Summarise report use across conditions from the archived traces."""
    root = Path(root)
    units = {u['id']: u for u in load_units(root)}
    rows = []
    for path in sorted((root / 'candidates').glob('*.json')):
        record = read_json(path)
        request = root / 'requests' / (record['id'] + '.json')
        reasoning = read_json(request).get('reasoning_content') or '' if request.exists() else ''
        rows.append({**{k: record.get(k) for k in ('id', 'unit', 'condition', 'repeat')},
                     'valid': record.get('valid', False),
                     **condition_markers(units[record['unit']], record['condition'], reasoning)})
    by_condition = {}
    for condition in CONDITIONS:
        subset = [r for r in rows if r['condition'] == condition]
        if not subset:
            continue
        by_condition[condition] = {
            'n': len(subset),
            'traces_naming_a_probe': sum(r['probe_names'] > 0 for r in subset),
            'mean_probe_names': mean(r['probe_names'] for r in subset),
            'mean_exact_cited': mean(r['exact_cited'] for r in subset),
            'mean_exact_total': mean(r['exact_total'] for r in subset),
            'mean_trace_chars': mean(r['trace_chars'] for r in subset),
        }
    return {'per_condition': by_condition, 'rows': rows}


def summarize(results):
    from .core import seed_for
    import random as _random
    out = {'per_unit': [], 'overall': {}}
    for unit in results:
        axis = unit['axis']
        per_condition = {}
        for condition in CONDITIONS:
            rows = [r for r in unit['candidates'] if r['condition'] == condition]
            valid = [r for r in rows if r.get('valid')]
            per_condition[condition] = {
                'n': len(rows), 'valid': len(valid),
                'repair_gain': mean(repair_gain(r, axis) for r in valid) if valid else None,
                'd_holdout': mean(r['d_holdout'] for r in valid) if valid else None,
            }
        out['per_unit'].append({'unit': unit['unit'], 'axis': axis, **per_condition})
    # Paired across units: accurate minus each control.
    for control in ('mismatched', 'score'):
        for metric, key in (('repair_gain', 'repair_gain'), ('d_holdout', 'd_holdout')):
            diffs = [u['accurate'][key] - u[control][key] for u in out['per_unit']
                     if u['accurate'][key] is not None and u[control][key] is not None]
            if not diffs:
                continue
            rng = _random.Random(seed_for('positive-control-bootstrap'))
            boots = sorted(mean(rng.choices(diffs, k=len(diffs))) for _ in range(20000))
            out['overall'][f'{metric}_accurate_minus_{control}'] = {
                'n_units': len(diffs), 'mean': mean(diffs),
                'ci95': [boots[int(.025 * len(boots))], boots[int(.975 * len(boots)) - 1]],
                'positive_units': sum(d > 0 for d in diffs),
            }
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('calibrate', 'verify', 'freeze', 'run', 'analyze',
                                            'think', 'think-analyze'))
    # The thinking commands act on a DIFFERENT root; defaulting them to the OFF
    # root silently reports every job as cached and writes a status file into the
    # frozen OFF results, so the default is resolved per command below.
    parser.add_argument('--root', default=None)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--only', nargs='*', help='restrict to these unit ids')
    args = parser.parse_args()
    args.root = args.root or str(THINKING_ROOT if args.command in ('think', 'think-analyze') else ROOT)
    if args.command == 'calibrate':
        rows = calibrate(refresh=True, root=args.root)
        print(json.dumps({'swept': len(rows)}))
        for row in sorted(rows, key=lambda r: (r['family'], -r['exploitation'])):
            print(json.dumps({'id': row['id'], 'rec': round(row['recovery_time'], 2),
                              'nr': round(row['not_recovered'], 2),
                              'exp': round(row['exploitation'], 3),
                              'H': round(row['holdout'], 4)}))
    elif args.command == 'verify':
        root = Path(args.root)
        specs = load_selected() if SELECTION.exists() else build_selection()
        report = []
        for index, spec in enumerate(specs):
            cfg = cfg_for(spec, index)
            spec['verified'] = {'defect': measure(spec, cfg, 'defect'),
                                'repair': measure(spec, cfg, 'repair')}
            for which in ('defect', 'repair'):
                spec['verified'][which].pop('diagnostic', None)
            ok = verify_pair(spec, cfg) is not None
            report.append({'id': spec['id'], 'axis': spec['axis'], 'ok': ok,
                           'defect': spec['verified']['defect'],
                           'repair': spec['verified']['repair']})
            print(json.dumps({'id': spec['id'], 'ok': ok,
                              'axis': spec['axis'],
                              'defect_axis_value': round(spec['verified']['defect'][
                                  'recovery_time' if spec['axis'] == 'recovery' else 'exploitation'], 3),
                              'repair_axis_value': round(spec['verified']['repair'][
                                  'recovery_time' if spec['axis'] == 'recovery' else 'exploitation'], 3),
                              'defect_H': round(spec['verified']['defect']['holdout'], 4),
                              'repair_H': round(spec['verified']['repair']['holdout'], 4)}))
        record = read_json(SELECTION)
        record['specs'] = specs
        record['verified_at'] = time.time()
        write_json(SELECTION, record)
        write_json(root / 'VERIFY.json', {'report': report})
    elif args.command == 'freeze':
        print(json.dumps(freeze(args.root)['units'], indent=2)[:4000])
    elif args.command == 'run':
        print(json.dumps(run(args.root, args.repeats, args.only), indent=2))
    elif args.command == 'analyze':
        results = evaluate_candidates(args.root, args.workers)
        summary = summarize(results)
        write_json(Path(args.root) / 'ANALYSIS.json', summary)
        for unit in summary['per_unit']:
            print(json.dumps(unit))
        print(json.dumps(summary['overall'], indent=2))
    elif args.command == 'think':
        print(json.dumps(run_thinking(args.root, args.repeats, args.workers, args.only), indent=2))
    elif args.command == 'think-analyze':
        report = analyze_reasoning(args.root)
        write_json(Path(args.root) / 'REASONING_ANALYSIS.json', report)
        print(json.dumps(report['per_condition'], indent=2))


if __name__ == '__main__':
    main()
