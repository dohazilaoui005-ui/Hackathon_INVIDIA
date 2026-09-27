"""
The shared contract for CivicPilot, matching the "How the five roles
connect" table in the team workflow doc. Backend (Person 4 / me) owns this
file and app.py's orchestration. I do NOT own the AI extraction logic, the
RAG/vector search, or the eligibility rules long-term — Persons 2 and 3 do.
My job is to pin down exactly what goes in and out of their modules so we
can all build in parallel, and to keep a working fallback behind each
interface so the demo never breaks just because one piece isn't ready yet.

              Field            Owner            Purpose
              ---------------  ---------------  --------------------------------
              user_profile     AI workflow (P2) Structured facts from the conversation
              programs+evidence RAG/data (P3)   Relevant official passages and source links
              eligibility result Rules/data (P3) Matched, missing, and failed requirements
              final response   AI workflow (P2) Safe explanation + prioritized action plan
              display model    Backend (P4)     Stable format for cards, citations, checklist

Pipeline (app.py):
  1. modules.ai_workflow.extract_profile(text, language)   -> user_profile
  2. merge with any partial profile the frontend already sent
  3. modules.rag_engine.find_programs(user_profile)        -> programs, evidence,
                                                                matches, warnings, sources
  4. modules.ai_workflow.generate_final_response(...)       -> safe explanation + checklist
  5. modules.display.build_display_model(...)               -> what the frontend renders
  6. db.save_case(...)                                       -> persistence (non-fatal)

Contract shapes (informal — see schemas.py for the strict pydantic version
of user_profile):

user_profile = {
    "personal": {"age", "country", "region", "city", "language"},
    "employment": {"status", "occupation"},
    "goal": {"type", "sector", "description", "stage"},
    "financial_need": {"amount", "currency", "purpose"},
    "business": {"existing", "has_business_plan", "has_business_registration"},
    "experience": {"relevant_experience", "skills": [...]},
    "eligibility": {"student", "low_income", "disability", "refugee", "rural_resident"},
    "constraints": {"cannot_take_debt", "other": [...]},
    "missing_information": [...],  # dotted paths still null — computed by schemas.Case
}

rag_result (return value of find_programs) = {
    "programs": [
        {"id", "name", "type", "sector", "countries", "max_amount", "currency",
         "requires": {...eligibility flags...}, "description",
         "required_documents": [...], "official_contact": "...", "deadline": "..."}
    ],
    "evidence": [
        {"program_id", "source_url", "snippet", "verification_date"}
    ],
    "matches": [
        {"program_id", "score", "matched_requirements": [...],
         "missing_requirements": [...], "failed_requirements": [...]}
    ],
    "warnings": [...],   # e.g. "source not verified in the last 90 days"
    "sources": [...],    # deduped list of source_urls actually used
}

final_response (return value of generate_final_response) = {
    "language": "ar" | "fr" | "en",
    "summary": "...",              # must use "appears to match" / "may be eligible",
                                     # NEVER "approved" or "guaranteed"
    "ranked_programs": [{"program_id", "why": "...", "risk_notes": "..."}],
    "checklist": [
        {"program_id", "documents": [...], "deadline": "...", "official_contact": "..."}
    ],
    "disclaimer": "...",           # always present — guidance, not an official decision
}

display_model (return value of build_display_model, what the frontend renders) = {
    "profile_summary": {...},       # short human-readable version of user_profile
    "program_cards": [
        {"name", "score", "type", "matched_requirements", "missing_requirements",
         "failed_requirements", "sources": [{"url", "verification_date"}], "why", "risk_notes"}
    ],
    "warnings": [...],
    "checklist": [...],
    "disclaimer": "...",
}
"""
