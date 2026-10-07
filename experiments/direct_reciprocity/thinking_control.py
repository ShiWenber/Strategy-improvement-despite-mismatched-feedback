"""DeepSeek ON settings and compatibility entry point for shared candidate generation."""
from pathlib import Path

from .condition_generation import (generate_candidate, specification as request_specification,
                                   transport_diagnostics, validate, receive_stream, TOKEN_LIMITS)

SOURCE = Path('results/feedback_specificity_v2')
DEFAULT_ROOT = Path('results/feedback_specificity_thinking_384k_20260923')
PROTOCOL = Path('docs/direct_reciprocity/THINKING_384K_PROTOCOL.md')
MAX_TOKENS = TOKEN_LIMITS['deepseek', 'on']


def specification(prompt):
    return request_specification(prompt, 'deepseek', 'on')


def generate_one(arg):
    root, job = arg
    return generate_candidate(root, job, job['arm'], provider='deepseek', mode='on')
