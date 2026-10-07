"""Independent diagnostics; neither behavioral probes nor test scores select parents."""
from itertools import product
from .core import act, RandomView, seed_for
from tools.direct_reciprocity.records import digest


def behavior_profile(policy):
    histories=[()]
    outcomes=list(product('CD',repeat=2))
    for length in (1,2,3):
        histories.extend(product(outcomes,repeat=length))
    actions=[]
    for i, history in enumerate(histories):
        for repeat in range(3):
            rng=RandomView(seed_for('behavior-v1',i,repeat))
            actions.append(act(policy.compile(rng),history,rng))
    return digest(''.join(actions))


def population_behavior(population):
    profiles=[]
    errors=[]
    for policy in population:
        try:
            profiles.append(behavior_profile(policy))
        except Exception as exc:
            errors.append({'key':policy.key,'error':str(exc)})
    return {'distinct_valid_profiles':len(set(profiles)), 'profile_errors':errors,
            'profile_version':'all_histories_length_0_to_3_three_rng_replicates_v1'}
