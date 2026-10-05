"""Resume local stages with transient Windows file-sharing retries only.

The three frozen experimental modules and all numerical functions are unchanged.
This wrapper cannot initialize or generate policies and makes no API requests.
"""
import argparse
from pathlib import Path
import sys
import time

from . import specificity
from .core import digest

original_write = specificity.write_json


def write_with_sharing_retry(path, data):
    for attempt in range(30):
        try:
            return original_write(path, data)
        except PermissionError:
            if attempt == 29:
                raise
            time.sleep(.05 * min(attempt + 1, 10))


# Applied also when Windows spawn imports this entry point in a worker process.
specificity.write_json = write_with_sharing_retry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='results/feedback_specificity_v2')
    parser.add_argument('--workers', type=int, default=24)
    parser.add_argument('--stage', choices=['select', 'holdout', 'both'], default='both')
    args = parser.parse_args()
    specificity.check_manifest(args.output)
    write_with_sharing_retry(Path(args.output) / 'LOCAL_IO_RECOVERY.json', {
        'reason': 'Windows PermissionError while atomically replacing EXECUTION_STATUS.json',
        'numerical_functions_changed': False, 'frozen_source_hash': specificity.source_hash(),
        'wrapper_hash': digest(Path(__file__).read_text(encoding='utf-8')),
        'api_calls': 0, 'resume_stage': args.stage, 'started_at': time.time(),
        'retry_scope': 'PermissionError on file persistence only; never model requests'})
    for stage in (['select', 'holdout'] if args.stage == 'both' else [args.stage]):
        sys.argv = ['specificity', stage, '--output', args.output, '--workers', str(args.workers)]
        specificity.main()


if __name__ == '__main__':
    main()
