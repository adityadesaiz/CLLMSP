import hashlib
import json
import logging
import asyncio
from typing import Dict, Any, Optional
from litellm import acompletion
from tenacity import retry, wait_exponential, stop_after_attempt

from backend.app.config import config
from backend.app.database import update_job_status, log_with_context

logger = logging.getLogger(__name__)

# Daily budget tracking
_daily_spend = 0.0
_spend_lock = asyncio.Lock()

class ImmutableProfile:
    def __init__(self, filepath: str = "master_profile.md"):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                self.text = f.read()
        except FileNotFoundError:
            raise RuntimeError(f"Tamper alert: {filepath} not found!")

        computed_hash = hashlib.sha256(self.text.encode('utf-8')).hexdigest()
        if computed_hash != config.MASTER_PROFILE_SHA256:
            raise RuntimeError("Tamper alert: Master profile hash mismatch!")

profile = ImmutableProfile()

@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
async def process_job_with_gemini(job_hash: str, raw_jd_text: str) -> Dict[str, Any]:
    log_with_context(logging.INFO, "Starting Gemini schema extraction", job_hash, "schema_extraction", "started")
    try:
        response = await acompletion(
            model="gemini/gemini-1.5-flash",
            messages=[{"role": "user", "content": f"Extract structured schema from this JD. Include a 'score' out of 100 based on software engineering requirements, and 'reasons' array for disqualification if score < 60:\n{raw_jd_text}"}],
            response_format={"type": "json_object"},
            api_key=config.GEMINI_API_KEY
        )

        content = response.choices[0].message.content
        extracted = json.loads(content)

        score = extracted.get("score", 0)
        reasons = extracted.get("reasons", [])

        if score >= 75:
            await update_job_status(job_hash, "qualified", score=score)
        elif score >= 60:
            await update_job_status(job_hash, "manual_review", score=score)
        else:
            await update_job_status(job_hash, "disqualified", reasons=reasons, score=score)

        log_with_context(logging.INFO, "Gemini schema extraction complete", job_hash, "schema_extraction", "success", score=score)
        return extracted
    except Exception as e:
        log_with_context(logging.ERROR, f"Gemini extraction failed: {e}", job_hash, "schema_extraction", "error")
        raise

@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
async def strategy_node_claude(job_hash: str, extracted_schema: Dict[str, Any]) -> Optional[str]:
    global _daily_spend

    async with _spend_lock:
        if _daily_spend >= config.DAILY_BUDGET_CAP:
            log_with_context(logging.WARNING, "Daily budget cap reached", job_hash, "strategy", "blocked")
            return None

    log_with_context(logging.INFO, "Starting Claude strategy generation", job_hash, "strategy", "started")
    try:
        response = await acompletion(
            model="anthropic/claude-3-haiku-20240307",
            messages=[
                {"role": "system", "content": f"You are a career strategist. Base your application entirely on this master profile:\n{profile.text}"},
                {"role": "user", "content": f"Generate a tailored application summary string targeting the enterprise pain points in this JD schema. Output paragraphs broken by newlines.\n{json.dumps(extracted_schema)}"}
            ],
            api_key=config.OPENAI_API_KEY
        )

        cost = response.get("_hidden_params", {}).get("response_cost", 0.01)
        async with _spend_lock:
            _daily_spend += cost

        content = response.choices[0].message.content
        log_with_context(logging.INFO, "Claude strategy generation complete", job_hash, "strategy", "success")
        return content
    except Exception as e:
        log_with_context(logging.ERROR, f"Claude strategy generation failed: {e}", job_hash, "strategy", "error")
        raise

def deterministic_verifier(job_hash: str, generated_text: str) -> str:
    # Verifies every sentence against the master profile
    sentences = generated_text.split(". ")
    verified_sentences = []

    for sentence in sentences:
        if not sentence.strip():
            continue

        # Strict substring containment constraint as requested
        citation = sentence.strip()
        if citation not in profile.text:
             log_with_context(logging.WARNING, f"Ungrounded claim dropped: {sentence}", job_hash, "verification", "dropped")
             continue

        verified_sentences.append(sentence)

    final_text = ". ".join(verified_sentences)
    if final_text: final_text += "."
    return final_text
