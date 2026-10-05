# Feedback attribution: one-step results

Complete: True; 120/120 outcomes; 0 audit issues.

| Arm | Valid / total | Default fallback | Default score gain | Training gain | Tokens |
| --- | ---: | ---: | ---: | ---: | ---: |
| true | 30/30 | 0 | -0.25768 | -0.13021 | 269,683 |
| shuffled | 29/30 | 1 | -0.25617 | -0.13026 | 267,958 |
| hidden | 30/30 | 0 | -0.25195 | -0.15413 | 262,522 |
| diagnostic | 30/30 | 0 | -0.10172 | -0.02538 | 270,862 |

| Contrast | Metric | Mean difference | Bootstrap 95% | Exact paired sign-flip p |
| --- | --- | ---: | --- | ---: |
| true-shuffled | training/score | +0.00004 | [-0.08541501165501167, 0.09436997668997672] | 1.0 |
| true-shuffled | default/score | -0.00152 | [-0.10489999999999992, 0.09825000000000003] | 1.0 |
| true-shuffled | noise01/score | +0.00133 | [-0.06537499999999995, 0.06804166666666664] | 0.9375 |
| true-shuffled | long/score | -0.02507 | [-0.09887499999999995, 0.04578750000000004] | 0.625 |
| true-shuffled | default/cooperation | +0.00392 | [-0.07853333333333334, 0.090925] | 0.9375 |
| true-shuffled | default/mixture:forgiving | +0.02237 | [-0.05070833333333332, 0.09544166666666673] | 0.6875 |
| true-shuffled | default/mixture:retaliatory | -0.05613 | [-0.2746433333333333, 0.16743000000000005] | 0.875 |
| true-shuffled | default/mixture:exploitative | +0.03030 | [-0.07275833333333333, 0.13335166666666665] | 0.6875 |
| true-hidden | training/score | +0.02392 | [-0.09392969696969707, 0.16440708624708625] | 0.75 |
| true-hidden | default/score | -0.00573 | [-0.12559166666666668, 0.11859166666666679] | 1.0 |
| true-hidden | noise01/score | -0.01817 | [-0.09999166666666663, 0.061333333333333385] | 0.6875 |
| true-hidden | long/score | -0.07328 | [-0.2046666666666666, 0.054175000000000015] | 0.4375 |
| true-hidden | default/cooperation | +0.01289 | [-0.08842499999999999, 0.107975] | 0.875 |
| true-hidden | default/mixture:forgiving | +0.02674 | [-0.07624999999999996, 0.15152833333333335] | 0.75 |
| true-hidden | default/mixture:retaliatory | -0.05587 | [-0.2996016666666666, 0.1774716666666667] | 0.75 |
| true-hidden | default/mixture:exploitative | +0.01746 | [-0.1035716666666667, 0.12436666666666665] | 0.9375 |
| diagnostic-true | training/score | +0.10483 | [0.06436242424242412, 0.15261631701631684] | 0.0625 |
| diagnostic-true | default/score | +0.15596 | [0.06870000000000004, 0.23635] | 0.0625 |
| diagnostic-true | noise01/score | +0.12005 | [0.05025833333333337, 0.17999999999999994] | 0.125 |
| diagnostic-true | long/score | +0.12235 | [0.05387916666666666, 0.22654166666666664] | 0.0625 |
| diagnostic-true | default/cooperation | +0.10608 | [0.051266666666666655, 0.16090000000000002] | 0.0625 |
| diagnostic-true | default/mixture:forgiving | +0.09355 | [0.061021666666666655, 0.12608166666666668] | 0.0625 |
| diagnostic-true | default/mixture:retaliatory | +0.32485 | [0.1376283333333333, 0.5086983333333334] | 0.0625 |
| diagnostic-true | default/mixture:exploitative | +0.13452 | [0.05886666666666669, 0.2101666666666667] | 0.0625 |

Score gains are offspring minus the same parent on fixed tests, with failed offspring retaining the parent.
Unit of inference is the initialization seed, not candidate or match. Bootstrap intervals are exploratory.
Matching requests does not match tokens. Diagnostic probes add 600 parent decisions per context (9,000 unique decisions).
Mixtures reweight fixed opponent payoffs; they are not ecological evolution.
Raw seed differences, successful-only summaries and all failures are in ANALYSIS.json.
