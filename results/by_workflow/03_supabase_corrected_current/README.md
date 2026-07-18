# Supabase Corrected Current Results

Status: current corrected workflow.

These are the benchmark artifacts produced after the workflow was corrected so that:

- Reference answers are hidden from all CoVe generation steps.
- Source metadata/context is injected into draft, verification planning, verification answering, and final synthesis.
- The verification planner is instructed to create only verification questions answerable from the provided source context.
- Reference answers are used only by the final hallucination-scoring step.

Use this folder for current Supabase-question hallucination comparisons between direct baseline answers and factored CoVe final answers.
