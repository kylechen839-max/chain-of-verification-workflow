# Results Organization

Results are grouped by workflow phase so old benchmark artifacts do not get mixed with current corrected runs.

## Which Results Should I Trust?

- `by_workflow/03_supabase_corrected_current/` is the current corrected Supabase-question workflow.
- `by_workflow/02_supabase_legacy_flawed/` is the previous flawed Supabase-question workflow. Keep these files for audit only; do not use them as current evidence.
- `by_workflow/01_nasa_context_backed/` contains NASA article context-backed runs from the earlier NASA benchmark lineage.
- `by_workflow/00_exploratory_and_infrastructure/` contains early smoke tests, Ollama/GCE checks, and prototype/confined-database runs.

Each workflow folder keeps the same two artifact types:

- `evaluations/` stores raw benchmark outputs.
- `scoring/` stores hallucination scoring and aggregate summaries.

The flawed Supabase runs are separated because they were produced before the workflow was corrected to hide reference answers from CoVe steps and to inject source context through every CoVe step.
