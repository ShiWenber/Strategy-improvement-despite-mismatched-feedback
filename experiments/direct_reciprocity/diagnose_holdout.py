"""Replay a failed generation without API calls or changing training checkpoints."""
import argparse
from dataclasses import replace
from pathlib import Path

from .baselines import TEST
from .core import Config, Policy, PolicyError, evaluate, ranking, match, seed_for
from .diagnostics import implementation_hash
from .run import read_json, write_json


def diagnose(directory, generation):
    directory = Path(directory)
    metadata = read_json(directory / 'config.json')
    if metadata['implementation_hash'] != implementation_hash():
        raise ValueError('Replay must use the original implementation')
    cfg = Config(**metadata['config'])
    previous = read_json(directory / f'generation_{generation-1:03d}.json')
    if previous['status'] != 'complete':
        raise ValueError('Previous generation is incomplete')
    population = [Policy(**p) for p in previous['next_population']]
    archive = [Policy(**p) for p in previous['next_archive']]
    assessment = evaluate(population, archive, cfg, generation)
    champion = population[ranking(population, assessment)[0]]
    result = {'generation': generation, 'implementation_hash': implementation_hash(),
              'champion_key': champion.key, 'training_evaluation_succeeded': True,
              'matches': [], 'failures': []}
    for label, rounds, noise in [('default', cfg.rounds, 0),
                                 ('noise01', cfg.rounds, .01), ('long', cfg.rounds*2, 0)]:
        for j, opponent in enumerate(TEST):
            for repeat in range(cfg.repeats):
                seed = seed_for(cfg.seed, 'holdout-'+label, generation, j, repeat)
                row = {'test': label, 'opponent': opponent.name, 'repeat': repeat,
                       'seed': seed, 'rounds': rounds, 'noise': noise}
                try:
                    row['result'] = match(champion, opponent, replace(cfg, rounds=rounds, noise=noise), seed)
                except PolicyError as exc:
                    row.update(error_type=type(exc).__name__, error=str(exc))
                    result['failures'].append(row)
                result['matches'].append(row)
    write_json(directory / f'holdout_diagnosis_{generation:03d}.json', result)
    print({'generation': generation, 'matches': len(result['matches']),
           'failures': len(result['failures']), 'champion_key': champion.key}, flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--generation', type=int, required=True)
    args = parser.parse_args()
    if args.generation < 1:
        parser.error('Replay requires a previous complete generation')
    diagnose(args.directory, args.generation)
