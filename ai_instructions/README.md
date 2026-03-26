# AI Instructions Package

This folder contains a split version of the long analysis prompt.

Recommended usage:

1. Put `INSTRUCTIONS.md` into the project instructions field.
2. Add the other `.md` files as supporting instruction files.
3. Add the latest `metrics_YYYY-MM-DD.json` file that should be analyzed.
4. Use `templates/training_plan_template.md` as the starting point for a real user plan, or leave plan context generic if no plan context is available.

The goal is to keep the instruction block short and move definitions, schema, and rules into separate source files.

Suggested file roles:

- `05_output_format.md` = route the question to the right answer mode first
- `02_metric_definitions.md` = what each metric means
- `03_json_structure.md` = where each metric lives in the JSON
- `03b_json_schema.md` = strict field contract, types, units, nullability, and aggregation semantics
- `04_analysis_logic.md` = how to reason from the data to a conclusion
- `04b_confidence_rules.md` = when conclusions are strong, limited, or weak
- `06_decision_rules.md` = how to turn interpreted state into practical action
- `07_database_query_mode.md` = how to answer direct lookup questions from the local SQLite database

Recommended reading order during analysis:

1. `05_output_format.md`
2. `01_data_sources.md` and `03_json_structure.md` as needed
3. `02_metric_definitions.md` for metric meaning
4. `04_analysis_logic.md`
5. `04b_confidence_rules.md` when uncertainty is material
6. `06_decision_rules.md`

For direct history lookups such as `find rides >100 km` or `longest ride this year`, route first to:

1. `05_output_format.md`
2. `07_database_query_mode.md`
