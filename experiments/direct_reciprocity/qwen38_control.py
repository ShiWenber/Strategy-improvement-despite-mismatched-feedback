"""Qwen OFF/ON settings and compatibility entry point for shared candidate generation."""
from pathlib import Path

from .condition_generation import generate_candidate, specification as request_specification, TOKEN_LIMITS

SOURCE = Path('results/feedback_specificity_v2')
DEFAULT_ROOT = Path('results/qwen3_8')
MODEL = 'qwen3.8-flash'
LIMITS = {mode: TOKEN_LIMITS['qwen', mode] for mode in ('off', 'on')}


def mode_for(root):
    mode = Path(root).name
    if mode not in LIMITS or Path(root).parent.name != 'qwen3_8':
        raise ValueError('Use results/qwen3_8/off or results/qwen3_8/on')
    return mode


def specification(prompt, mode):
    return request_specification(prompt, 'qwen', mode)


def generate_one(arg):
    root, job = arg
    return generate_candidate(root, job, job['arm'], provider='qwen', mode=mode_for(root))
