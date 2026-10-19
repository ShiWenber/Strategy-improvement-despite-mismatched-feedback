"""Explicit evaluation-only recovery for frozen runs with holdout runtime errors.

Training errors still abort. Failed holdouts have null metrics, never fabricated
payoffs. Recovery reads the run configuration and reuses durable request records.
"""
import argparse
from pathlib import Path
from experiments.direct_reciprocity import run as runner
from .core import Config, PolicyError, versus


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
