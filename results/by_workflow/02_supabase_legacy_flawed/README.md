# Supabase Legacy Flawed Results

Status: flawed legacy workflow. Audit only.

These are the previous Supabase-question benchmark results, mostly from `deepseek-coder:6.7b`, produced before the workflow corrections requested later in the project.

Known issues:

- Reference answers were available too early in the workflow in some runs.
- Supabase metadata/source context was not guaranteed to be injected through every CoVe step.
- Verification questions were not fully constrained to questions answerable from the provided source metadata.

Keep these files for provenance and comparison, but do not use them as evidence for the corrected CoVe workflow.
