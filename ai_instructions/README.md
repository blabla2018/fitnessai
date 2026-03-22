# AI Instructions Package

This folder contains a split version of the long analysis prompt.

Recommended usage in an AI workspace or project:

1. Put `INSTRUCTIONS.md` into the project instructions field.
2. Add the other `.md` files to the project Source.
3. Add your latest `metrics_YYYY-MM-DD.json` files to the project Source.
4. Add your real training plan to `training_plan.md` in the project Source.

The goal is to keep the instruction block short and move definitions, schema, and rules into separate source files.

Suggested file roles:

- `02_metric_definitions.md` = what each metric means
- `03_json_structure.md` = where each metric lives in the JSON
- `03b_json_schema.md` = strict field contract, types, units, nullability, and aggregation semantics
- `04_analysis_logic.md` = how to reason from the data to a conclusion
- `04b_confidence_rules.md` = when conclusions are strong, limited, or weak
