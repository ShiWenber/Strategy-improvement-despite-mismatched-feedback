"""Explicit evaluation-only recovery for frozen runs with holdout runtime errors.

Training errors still abort. Failed holdouts have null metrics, never fabricated
payoffs. The frozen runner and its implementation identity remain untouched;
the additional execution layer is recorded separately for every recovered run.
"""
import argparse
from pathlib import Path
from . import run as runner
from .core import Config, PolicyError, digest, versus
from .diagnostics import implementation_hash


def tolerate_holdout_failure(policy, opponents, cfg, phase, generation=0):
    try:
        return versus(policy, opponents, cfg, phase, generation)
    except PolicyError as exc:
        if not phase.startswith('holdout-'):
            raise
        return {'status': 'runtime_failure', 'score': None, 'cooperation': None,
                'worst_score': None, 'opponents': [],
                'error_type': type(exc).__name__, 'error': str(exc),
                'policy_key': policy.key, 'phase': phase, 'generation': generation}


def recover(directory):
    directory = Path(directory).resolve()
    metadata = runner.read_json(directory / 'config.json')
    base_hash = implementation_hash()
    if metadata['implementation_hash'] != base_hash:
        raise ValueError('Frozen training implementation differs')
    record = {'version': 1, 'base_implementation_hash': base_hash,
              'recovery_source_hash': digest(Path(__file__).read_text(encoding='utf-8')),
              'rule': 'Only holdout PolicyError becomes runtime_failure with null metrics; training errors propagate.',
              'training_changed': False, 'instruction_budget_changed': False}
    path = directory / 'evaluation_recovery.json'
    if path.exists() and runner.read_json(path) != record:
        raise ValueError('Recovery implementation differs from recorded version')
    runner.write_json(path, record)
    original = runner.versus
    try:
        runner.versus = tolerate_holdout_failure
        runner.run(Config(**metadata['config']), directory.parent,
                   metadata['provider'], metadata['model'], metadata['initial_source'])
    finally:
        runner.versus = original


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--env-file', type=Path)
    args = parser.parse_args()
    if args.env_file:
        from dotenv import load_dotenv
        load_dotenv(args.env_file, override=False)
    recover(args.directory)
