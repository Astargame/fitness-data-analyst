# Fitness Data Analyst (in progress)

Ask questions about Fitbit data in plain English. Claude writes a read-only SQL query, runs it, and answers with a table, a chart and a short explanation, always showing the SQL it ran.

**Status:** Stage 1 of 8. Data validated, success criteria written before building.

- **Data:** public Fitbit dataset (Zenodo, CC BY 4.0), 33 user IDs, 12 Apr – 12 May 2016
- **Evaluation:** ~50 hand-checked questions, dev/test split, execution accuracy vs two baselines ([success criteria](docs/success_criteria.md))
- **Safety:** read-only database, SELECT-only, timeouts and row limits
