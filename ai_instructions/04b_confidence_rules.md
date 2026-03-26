# Confidence Rules

Use these rules to decide whether an interpretation is strong, limited, or weak.

## General Principle

- High confidence requires multiple aligned signals and acceptable data coverage.
- Medium confidence is appropriate when the main signals are present but one or more are partial, noisy, or contradictory.
- Low confidence is appropriate when coverage is weak, `n` is small, or important signals disagree.

## Coverage Thresholds

Default interpretation thresholds for aggregated windows:

- `coverage_pct >= 85` = strong coverage
- `coverage_pct 60..84` = usable but limited
- `coverage_pct < 60` = weak coverage

Default `n` thresholds:

- `n >= 5` = usually interpretable for short windows
- `n 3..4` = usable with caution
- `n < 3` = weak evidence for most conclusions

## Metric-Specific Confidence Guidance

### Sleep

- Sleep trends are usually reliable when `coverage_pct >= 85`.
- One very bad night can matter meaningfully for readiness, but do not over-generalize from a single point to the whole process.

### HRV

- Treat HRV as interpretable only if there are at least `3` recent valid points.
- Low `sd` with a clear `delta_vs_*` is stronger evidence than a tiny shift inside normal variability.
- If HRV coverage is weak, explicitly lower confidence.

### RHR

- Treat RHR as interpretable only if there are at least `3` recent valid points.
- A small RHR shift is weaker evidence than a large sleep or load change unless it persists across multiple days.

### VO2max

- Treat VO2max as a slow capacity signal.
- Do not use it as a primary readiness indicator.
- If `n` is very low or coverage is sparse, treat it as background context only.

### Weight

- Weight conclusions need repeated observations.
- If `coverage_pct < 60`, explicitly say the weight conclusion is limited.
- Prefer trend language, not single-day judgments.

### Mood / Motivation

- Subjective metrics are supportive, not sufficient by themselves.
- If `n < 3` in the relevant window, treat them as weak context.
- Use them mainly in combination with sleep, HRV/RHR, session execution, and notes.

### FTP / eFTP Proxies

- For current trends, use both `avg` and `best` when available.
- If recent `n` is very low, avoid strong statements like `clearly improving` or `clearly down`.
- A stable proxy with poor recovery can still mean `capacity stable, readiness reduced`.

### Form / Fatigue / Fitness

- These are modeled signals and are usually available with strong coverage.
- `form` and `fatigue` are generally more decision-relevant than `fitness` alone for short-term load advice.

## Contradiction Rules

Lower confidence when important signals disagree, for example:

- poor sleep but neutral HRV/RHR
- high motivation but poor mood
- stable FTP proxy but worsening recovery
- good subjective state but unusually high RPE for only moderate IF

When contradictions exist:

- state both signals explicitly
- explain which one you trust more and why
- avoid overconfident recommendations
- separate `long-term capacity / foundation` from `current readiness / short-term state`
- if the contradiction changes the practical advice, say what assumption needs validation

## Decision Reliability

### Stronger basis for reducing load

Recommend reducing load more confidently when at least two of these align:

- poor sleep versus short baseline
- HRV down or RHR up versus baseline
- `fatigue > fitness` with negative `form`
- low mood and low motivation
- high RPE at only moderate IF

### Stronger basis for keeping plan stable

Keeping the plan is more reasonable when:

- sleep is near baseline
- HRV/RHR are neutral
- `form` is not unusually negative for the athlete
- recent session execution looks controlled
- no major contradiction appears in notes or subjective data

## Output Guidance

- Use `high confidence` only when both data quality and signal alignment are strong.
- Use `medium confidence` as the default when there is some uncertainty.
- Use `low confidence` when coverage is weak, `n` is small, or major contradictions remain unresolved.
- If a metric is present but weakly covered, do not ignore it silently; mention that it exists but is limited.

## Validation Guidance

Add a short validation step when one of these is true:

- strong historical capacity but weak current readiness
- good subjective feel but objectively expensive recent execution
- good modeled capacity but poor sleep / HRV / RHR cluster
- notes suggest one story and the metrics suggest another

In those cases:

- say what part looks solid
- say what part remains uncertain
- name the key assumption that could change the recommendation
- keep the recommendation on the conservative side until clarified
