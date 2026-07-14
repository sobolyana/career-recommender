"""
recommender.py — Core logic for Career Recommender System
Steps 1-3: Job recommendations, gap analysis, course recommendations
"""

import os
import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity


# # ── Paths ─────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
DATA_DIR   = os.path.join(BASE_DIR, 'data')
 
JOB_EMBEDDINGS_PATH    = os.path.join(DATA_DIR, 'job_embeddings.npy')
JOBS_PATH              = os.path.join(DATA_DIR, 'jobs_30k.parquet')
COURSE_EMBEDDINGS_PATH = os.path.join(DATA_DIR, 'course_embeddings.npy')
COURSES_PATH           = os.path.join(DATA_DIR, 'courses.parquet')



# ── Constants ─────────────────────────────────────────────────
COURSE_SIM_THRESHOLD = 0.45
TOP_GAP_SKILLS       = 10
SIMILARITY_THRESHOLD = 0.75


# ── Load model and data ───────────────────────────────────────
print('⏳ Loading model...')
model = SentenceTransformer('all-MiniLM-L6-v2')
print('✅ Model loaded')

print('⏳ Loading data...')
df               = pd.read_parquet(JOBS_PATH)
job_embeddings   = np.load(JOB_EMBEDDINGS_PATH)
courses          = pd.read_parquet(COURSES_PATH)
course_embeddings = np.load(COURSE_EMBEDDINGS_PATH)
print(f'✅ Jobs: {len(df):,} | Courses: {len(courses):,}')


# ════════════════════════════════════════════════════════════
# STEP 1 — Job Recommendations
# ════════════════════════════════════════════════════════════

def build_profile_vector(profile: dict) -> dict:
    
    parts   = []
    weights = []

    if profile.get('bio'):
        parts.append(profile['bio'])
        weights.append(2.0)

    if profile.get('skills'):
        skills_str = (', '.join(profile['skills'])
                      if isinstance(profile['skills'], list)
                      else str(profile['skills']))
        parts.append(f"Skills: {skills_str}")
        weights.append(2.0)

    if profile.get('current_title'):
        parts.append(f"Current role: {profile['current_title']}")
        weights.append(0.5)

    if profile.get('education'):
        parts.append(f"Education: {profile['education']}")
        weights.append(0.5)

    if not parts:
        raise ValueError('Profile is empty — please enter at least a description')

    embeddings  = model.encode(parts, normalize_embeddings=True)
    profile_vec = np.average(embeddings, weights=np.array(weights), axis=0)
    norm        = np.linalg.norm(profile_vec)
    profile_vec = profile_vec / norm if norm > 0 else profile_vec

    # Target role — separate clean vector
    target_vec = None
    if profile.get('target_role'):
        role         = profile['target_role']
        target_parts = [
            f"Job title: {role}",
            f"Position: {role}",
            f"I am looking for a job as {role}",
        ]
        target_embs = model.encode(target_parts, normalize_embeddings=True)
        target_vec  = np.mean(target_embs, axis=0)
        t_norm      = np.linalg.norm(target_vec)
        target_vec  = target_vec / t_norm if t_norm > 0 else target_vec

    return {'profile_vec': profile_vec, 'target_vec': target_vec}


def filter_by_region(region: str) -> pd.Series:
    """Filters jobs by region. 'CA' matches California only, not Canada."""
    r = region.strip()
    if len(r) <= 2:
        pattern = rf'(?:,\s*{r}\b|\b{r}(?:,|\s*$))'
    else:
        pattern = r
    return df['job_location'].str.contains(
        pattern, case=False, na=False, regex=True
    )


def recommend_jobs(
    profile:       dict,
    top_k:         int   = 5,
    region:        str   = None,
    candidate_pool: int  = 50,
    target_weight: float = 0.7
) -> list[dict]:
   
    vectors     = build_profile_vector(profile)
    profile_vec = vectors['profile_vec']
    target_vec  = vectors['target_vec']

    # Regional filter
    if region and region.strip():
        mask           = filter_by_region(region)
        candidate_df   = df[mask].copy()
        candidate_embs = job_embeddings[mask.values]
        if len(candidate_df) == 0:
            candidate_df   = df.copy()
            candidate_embs = job_embeddings
    else:
        candidate_df   = df.copy()
        candidate_embs = job_embeddings
    
    # ── Job type filter ───────────────────────────────────────
    job_types = profile.get('job_types', [])
    if job_types and len(job_types) < 3:
        type_mask = candidate_df['job_type'].isin(job_types)
        if type_mask.sum() == 0:
            print(f'⚠️  No jobs found for types {job_types} — showing all')
        else:
            candidate_df   = candidate_df[type_mask].copy()
            candidate_embs = candidate_embs[type_mask.values]
            print(f'🏠 Types {job_types}: {len(candidate_df):,} jobs')



   
    profile_sims = cosine_similarity(
        profile_vec.reshape(1, -1), candidate_embs
    )[0]

    if target_vec is not None:
        target_sims = cosine_similarity(
            target_vec.reshape(1, -1), candidate_embs
        )[0]
        final_sims = (target_weight * target_sims +
                      (1 - target_weight) * profile_sims)
    else:
        final_sims = profile_sims

    top_idx = np.argsort(final_sims)[::-1][:candidate_pool]
    top_df  = candidate_df.iloc[top_idx].copy()
    top_df['semantic_sim'] = final_sims[top_idx]
    top_df  = top_df.drop_duplicates(subset=['job_title', 'company'])
    top_df  = top_df.nlargest(top_k, 'semantic_sim')

    results = []
    for _, row in top_df.iterrows():
        results.append({
            'job_title':    row['job_title'],
            'company':      row['company'],
            'location':     row['job_location'],
            'level':        row.get('job_level', ''),
            'job_type':     row.get('job_type', ''),
            'skills':       str(row.get('job_skills', '')),
            'similarity':   round(float(row['semantic_sim']) * 100, 1)
        })
    return results


# ════════════════════════════════════════════════════════════
# STEP 2 — Gap Analysis
# ════════════════════════════════════════════════════════════

def get_user_skills(profile: dict) -> list[str]:
    """Returns user skills list from profile."""
    skills = profile.get('skills')
    if not skills:
        return []
    if isinstance(skills, list):
        result = [s.strip() for s in skills if s and s.strip()]
    else:
        result = [s.strip() for s in str(skills).split(',') if s.strip()]

    seen, unique = set(), []
    for s in result:
        if s.lower() not in seen:
            seen.add(s.lower())
            unique.append(s)
    return unique


def parse_job_skills(job_skills_str: str) -> list[str]:
    """Parses job skills string into list."""
    if pd.isna(job_skills_str) or not job_skills_str:
        return []
    return [s.strip() for s in str(job_skills_str).split(',') if s.strip()]


def compute_skill_match(user_skills: list, job_skills: list) -> dict:
    """
    Semantically compares user skills with job skills.
    Returns matched, missing, and coverage score.
    """
    if not user_skills or not job_skills:
        return {'matched': [], 'missing': job_skills, 'coverage': 0.0}

    all_skills     = user_skills + job_skills
    all_embeddings = model.encode(all_skills, normalize_embeddings=True)

    user_embs = all_embeddings[:len(user_skills)]
    job_embs  = all_embeddings[len(user_skills):]
    sim_matrix = cosine_similarity(job_embs, user_embs)

    matched, missing = [], []
    for j_idx, job_skill in enumerate(job_skills):
        best_u_idx = np.argmax(sim_matrix[j_idx])
        best_sim   = sim_matrix[j_idx][best_u_idx]
        if best_sim >= SIMILARITY_THRESHOLD:
            matched.append({
                'job_skill':  job_skill,
                'user_skill': user_skills[best_u_idx],
                'similarity': round(float(best_sim), 2)
            })
        else:
            missing.append(job_skill)

    coverage = len(matched) / len(job_skills) if job_skills else 0.0
    return {'matched': matched, 'missing': missing, 'coverage': round(coverage, 2)}


def analyze_gap(profile: dict, top_jobs: list) -> dict:
    """
    Full gap analysis: user skills vs job skills for each job.
    Returns per-job gap and aggregated priority list.
    """
    user_skills = get_user_skills(profile)
    if not user_skills:
        return {'user_skills': [], 'per_job': [], 'aggregated_gap': []}

    per_job = []
    for job in top_jobs:
        job_skills = parse_job_skills(job['skills'])
        match      = compute_skill_match(user_skills, job_skills)
        per_job.append({
            'job_title': job['job_title'],
            'company':   job['company'],
            'matched':   match['matched'],
            'missing':   match['missing'],
            'coverage':  match['coverage']
        })

    # Aggregate gap by frequency
    gap_counter = {}
    for job in per_job:
        for skill in job['missing']:
            key = skill.lower().strip()
            if key not in gap_counter:
                gap_counter[key] = {'skill': skill, 'count': 0}
            gap_counter[key]['count'] += 1

    n_jobs = len(per_job)
    aggregated_gap = sorted(
        [{'skill': v['skill'], 'count': v['count'],
          'frequency': round(v['count'] / n_jobs, 2)}
         for v in gap_counter.values()],
        key=lambda x: x['count'],
        reverse=True
    )

    return {
        'user_skills':    user_skills,
        'per_job':        per_job,
        'aggregated_gap': aggregated_gap
    }


# ════════════════════════════════════════════════════════════
# STEP 3 — Course Recommendations
# ════════════════════════════════════════════════════════════

def find_course_for_skill(skill: str) -> dict | None:
    """
    Finds the most relevant Coursera course for a skill.
    Ranking: 0.7 × semantic_sim + 0.3 × normalized_rating
    Returns None if similarity < COURSE_SIM_THRESHOLD.
    """
    skill_vec   = model.encode([skill], normalize_embeddings=True)
    sims        = cosine_similarity(skill_vec, course_embeddings)[0]
    top_idx     = np.argsort(sims)[::-1][:10]

    best_score  = -1
    best        = None

    for idx in top_idx:
        sim = sims[idx]
        if sim < COURSE_SIM_THRESHOLD:
            continue
        rating      = courses.iloc[idx]['course_rating']
        final_score = 0.7 * sim + 0.3 * (rating / 5.0)
        if final_score > best_score:
            best_score = final_score
            best = {
                'name':       courses.iloc[idx]['course_name'],
                'university': courses.iloc[idx]['university'],
                'level':      courses.iloc[idx]['difficulty_level'],
                'rating':     float(rating),
                'url':        courses.iloc[idx]['course_url'],
                'similarity': round(float(sim), 2)
            }
    return best


def recommend_courses(gap_result: dict) -> list[dict]:
    """
    Finds courses for top gap skills.
    Naturally filters soft skills — if no course found, skill is skipped.
    Deduplicates by URL.
    """
    aggregated_gap = gap_result.get('aggregated_gap', [])
    if not aggregated_gap:
        return []

    results   = []
    seen_urls = set()

    for item in aggregated_gap[:TOP_GAP_SKILLS]:
        course = find_course_for_skill(item['skill'])
        
        if not course:
            continue
        if course['url'] in seen_urls:
            continue
        seen_urls.add(course['url'])
        results.append({
            'skill':        item['skill'],
            'frequency':    item['frequency'],
            'count':        item['count'],
            'course_name':  course['name'],
            'university':   course['university'],
            'level':        course['level'],
            'rating':       course['rating'],
            'url':          course['url']
        })

    return results


# ════════════════════════════════════════════════════════════
# FULL PIPELINE
# ════════════════════════════════════════════════════════════

def run_pipeline(profile: dict) -> dict:
    """
    Full pipeline: profile → jobs → gap → courses

    Returns:
    {
      'jobs':    list of job dicts,
      'gap':     gap analysis dict or None,
      'courses': list of course dicts
    }
    """
    # Step 1: Jobs
    region   = profile.get('region', '').strip()
    top_k  = profile.get('top_k', 5)
    top_jobs = recommend_jobs(profile, top_k=top_k, region=region or None)

    # Step 2 + 3: Gap and courses (only if skills provided)
    user_skills = get_user_skills(profile)
    if user_skills:
        gap         = analyze_gap(profile, top_jobs)
        courses_rec = recommend_courses(gap)
    else:
        gap         = None
        courses_rec = []

    return {
        'jobs':    top_jobs,
        'gap':     gap,
        'courses': courses_rec
    }