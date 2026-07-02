import asyncio
import json
import logging
import hashlib
import re
import os
from typing import List, Optional, Tuple
import aiosqlite
from tenacity import retry, wait_exponential, stop_after_attempt
from backend.app.config import config

logger = logging.getLogger(__name__)

def log_with_context(level: int, msg: str, job_hash: str, phase: str, status: str, **kwargs):
    context = {"job_hash": job_hash, "phase": phase, "status": status}
    context.update(kwargs)
    logger.log(level, msg, extra={"context": context})

def generate_robust_job_hash(company: str, title: str, raw_jd_text: str) -> str:
    def normalize(text: str) -> str:
        text = text.lower()
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'[^\w\s]', '', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    norm_company = normalize(company)
    norm_title = normalize(title)
    norm_body = normalize(raw_jd_text)[:500]

    core = f"{norm_company}|{norm_title}|{norm_body}"
    return hashlib.sha256(core.encode('utf-8')).hexdigest()

def simple_minhash(text: str, num_hashes: int = 100) -> List[int]:
    words = text.split()
    if not words:
        return [0] * num_hashes

    hashes = []
    for i in range(num_hashes):
        min_h = float('inf')
        for w in words:
            # Replaced built-in hash() with md5 for deterministic consistency across process restarts
            w_str = f"{i}_{w}"
            h = int(hashlib.md5(w_str.encode('utf-8')).hexdigest(), 16)
            if h < min_h:
                min_h = h
        hashes.append(min_h)
    return hashes

def jaccard_similarity(mh1: List[int], mh2: List[int]) -> float:
    if not mh1 or not mh2:
        return 0.0
    matches = sum(1 for h1, h2 in zip(mh1, mh2) if h1 == h2)
    return matches / len(mh1)

@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
async def init_db():
    try:
        async with aiosqlite.connect(config.DB_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS jobs_discovered (
                    job_hash TEXT PRIMARY KEY,
                    company TEXT NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    raw_jd_text TEXT NOT NULL,
                    compatibility_score REAL,
                    disqualified_reasons TEXT,
                    processing_status TEXT NOT NULL,
                    rubric_version TEXT NOT NULL,
                    manual_override BOOLEAN DEFAULT FALSE,
                    discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    minhash_signature TEXT
                )
            """)
            # Also checking if we need to add the column to an existing table if this isn't fresh
            try:
                 await db.execute("ALTER TABLE jobs_discovered ADD COLUMN raw_jd_text TEXT")
            except aiosqlite.OperationalError:
                 pass # Column exists

            await db.execute("CREATE INDEX IF NOT EXISTS idx_status ON jobs_discovered(processing_status)")
            await db.commit()
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

async def check_tailored_file_exists(job_hash: str, rubric_version: str) -> bool:
    """Verify if a tailored file already exists to guarantee retry idempotency."""
    filepath = f"./tailored_applications/{job_hash}_{rubric_version}.txt"
    return os.path.exists(filepath)

@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
async def insert_job(job_hash: str, company: str, title: str, url: str, raw_jd_text: str, rubric_version: str) -> bool:
    if await check_tailored_file_exists(job_hash, rubric_version):
         log_with_context(logging.INFO, "Tailored file already exists, skipping insertion", job_hash, "insertion", "skipped_idempotent")
         return False

    mh = simple_minhash(raw_jd_text)
    mh_str = json.dumps(mh)

    try:
        async with aiosqlite.connect(config.DB_PATH) as db:
            # Check near-duplicates
            async with db.execute("SELECT job_hash, minhash_signature FROM jobs_discovered") as cursor:
                async for row in cursor:
                    existing_hash, existing_mh_str = row
                    if existing_mh_str:
                        existing_mh = json.loads(existing_mh_str)
                        if jaccard_similarity(mh, existing_mh) > 0.8:
                            log_with_context(logging.INFO, "Near duplicate detected", job_hash, "insertion", "duplicate", matched_with=existing_hash)
                            return False

            await db.execute("""
                INSERT INTO jobs_discovered
                (job_hash, company, title, url, raw_jd_text, processing_status, rubric_version, minhash_signature)
                VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
                ON CONFLICT(job_hash) DO NOTHING
            """, (job_hash, company, title, url, raw_jd_text, rubric_version, mh_str))
            await db.commit()
            log_with_context(logging.INFO, "Job inserted successfully", job_hash, "insertion", "pending")
            return True
    except Exception as e:
        log_with_context(logging.ERROR, f"Database insertion failed: {e}", job_hash, "insertion", "error")
        raise

@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
async def update_job_status(job_hash: str, new_status: str, reasons: List[str] = None, score: float = None) -> bool:
    try:
        reasons_json = json.dumps(reasons) if reasons else '[]'
        async with aiosqlite.connect(config.DB_PATH) as db:
            async with db.execute("SELECT updated_at FROM jobs_discovered WHERE job_hash = ?", (job_hash,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return False
                current_time = row[0]

            cursor = await db.execute("""
                UPDATE jobs_discovered
                SET processing_status = ?, disqualified_reasons = ?, compatibility_score = ?, updated_at = CURRENT_TIMESTAMP
                WHERE job_hash = ? AND updated_at = ?
            """, (new_status, reasons_json, score, job_hash, current_time))

            # Use cursor.rowcount instead of db.total_changes
            if cursor.rowcount > 0:
                await db.commit()
                log_with_context(logging.INFO, "Job status updated", job_hash, "update", new_status)
                return True
            return False
    except Exception as e:
        log_with_context(logging.ERROR, f"Database update failed: {e}", job_hash, "update", "error")
        raise
