import os
import time
import uuid
import logging

from flask import Flask, request, jsonify
from flask_cors import CORS

from logging_config import setup_logging
import db
from schemas import Case, merge_case
from modules import ai_workflow, rag_engine, display
from services.cache import ttl_cache

setup_logging()
logger = logging.getLogger("case_analyzer.app")

app = Flask(__name__)
CORS(app)  # allow the frontend (Person 5) to call this API directly from any origin

db.init_db()

CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "3600"))


@ttl_cache(ttl_seconds=CACHE_TTL_SECONDS)
def cached_extract_profile(text: str, language: str):
    return ai_workflow.extract_profile(text, language)


# ---------------------------------------------------------------------------
# Request logging
# ---------------------------------------------------------------------------
@app.before_request
def _start_timer():
    request.start_time = time.time()


@app.after_request
def _log_request(response):
    duration = time.time() - getattr(request, "start_time", time.time())
    logger.info(f"{request.method} {request.path} -> {response.status_code} ({duration:.3f}s)")
    return response


# ---------------------------------------------------------------------------
# Global error handling — every failure returns structured JSON, never a
# bare stack trace, and is logged for debugging.
# ---------------------------------------------------------------------------
@app.errorhandler(Exception)
def handle_uncaught_error(e):
    logger.exception("Unhandled error")
    return jsonify({
        "error": {
            "message": "Internal server error" if not app.debug else str(e),
            "type": e.__class__.__name__,
        }
    }), 500


@app.errorhandler(404)
def handle_404(e):
    return jsonify({"error": {"message": "Not found"}}), 404


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/health", methods=["GET"])
def health():
    programs_loaded = len(rag_engine._load_programs())
    return jsonify({
        "status": "ok",
        "demo_programs_loaded": programs_loaded,
        "ai_configured": bool(os.getenv("ANTHROPIC_API_KEY")),
    })


@app.route("/analyze-case", methods=["POST"])
def analyze_case():
    """
    THE single reliable entry point for the frontend (Person 5).

    Request body (send `text`, `case`, or both):
      {
        "text": "free text in Arabic, French, or English",
        "language": "ar" | "fr" | "en",   # optional hint
        "case": { ...partial user_profile the frontend already collected... }
      }

    Response:
      {
        "case_id": "...",
        "user_profile": {...},        # see contracts.py
        "rag_result": {...},          # programs, evidence, matches, warnings, sources
        "final_response": {...},      # safe explanation + checklist
        "display_model": {...},       # what the frontend actually renders
        "meta": {"ai_used", "cache_hit", "warnings"}
      }

    Every external step (AI extraction, retrieval) is wrapped so a failure
    anywhere still returns a 200 with partial results plus a warning,
    rather than breaking the demo.
    """
    body = request.get_json(silent=True) or {}
    text = (body.get("text") or "").strip()
    language = body.get("language") or "en"
    partial_case = body.get("case") or {}

    if not text and not partial_case:
        return jsonify({
            "error": {"message": "Provide 'text' and/or 'case' in the request body."}
        }), 400

    warnings = []
    ai_used = False
    cache_hit = False
    extracted = {}

    # --- Step 1: profile extraction (Person 2's module) --------------------
    if text:
        try:
            extracted, cache_hit = cached_extract_profile(text, language)
            ai_used = True
        except Exception as e:
            logger.warning(f"ai_workflow.extract_profile failed entirely: {e}")
            warnings.append("Profile extraction was degraded; some fields may be missing.")

    merged = merge_case(partial_case, extracted)
    try:
        case_obj = Case(**merged)
    except Exception as e:
        logger.error(f"Profile validation failed: {e}")
        return jsonify({"error": {"message": f"Invalid profile data: {e}"}}), 400

    user_profile = case_obj.model_dump()
    user_profile["missing_information"] = case_obj.compute_missing()

    # --- Step 2: retrieval + eligibility rules (Person 3's module) ---------
    try:
        rag_result = rag_engine.find_programs(user_profile)
    except Exception as e:
        logger.error(f"rag_engine.find_programs failed: {e}")
        warnings.append("Program search failed; no candidates found.")
        rag_result = {"programs": [], "evidence": [], "matches": [], "warnings": [], "sources": []}

    warnings.extend(rag_result.get("warnings", []))

    # --- Step 3: safe explanation + action plan (Person 2's module) --------
    try:
        final_response = ai_workflow.generate_final_response(user_profile, rag_result, language)
    except Exception as e:
        logger.error(f"ai_workflow.generate_final_response failed: {e}")
        warnings.append("Could not generate the explanation/action plan.")
        final_response = {
            "language": language, "summary": "", "ranked_programs": [],
            "checklist": [], "disclaimer": "Please confirm any program details with the official provider.",
        }

    # --- Step 4: display model (backend-owned) ------------------------------
    display_model = display.build_display_model(user_profile, rag_result, final_response)

    # --- Step 5: persistence (non-fatal if it fails) -------------------------
    case_id = str(uuid.uuid4())
    if not db.save_case(case_id, text, user_profile, rag_result, final_response):
        warnings.append("Could not persist this case to the database.")

    return jsonify({
        "case_id": case_id,
        "user_profile": user_profile,
        "rag_result": rag_result,
        "final_response": final_response,
        "display_model": display_model,
        "meta": {
            "ai_used": ai_used,
            "cache_hit": cache_hit,
            "warnings": warnings,
        },
    })


@app.route("/case/<case_id>", methods=["GET"])
def get_case_route(case_id):
    result = db.get_case(case_id)
    if not result:
        return jsonify({"error": {"message": "Case not found"}}), 404
    return jsonify(result)


@app.route("/programs", methods=["GET"])
def list_programs():
    """Debug/inspection endpoint for the fallback dataset."""
    return jsonify(rag_engine._load_programs())


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_ENV") != "production"
    app.run(host="0.0.0.0", port=port, debug=debug)
