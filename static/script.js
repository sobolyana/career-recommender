// ── Tab switching ───────────────────────────────────────
document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.add('hidden'));
    tab.classList.add('active');
    document.getElementById('tab' + capitalize(tab.dataset.tab)).classList.remove('hidden');
  });
});

function capitalize(str) {
  return str.charAt(0).toUpperCase() + str.slice(1);
}

// ── Form submit ─────────────────────────────────────────
document.getElementById('profileForm').addEventListener('submit', async (e) => {
  e.preventDefault();

  const btn = document.getElementById('submitBtn');
  btn.classList.add('loading');
  btn.querySelector('.btn-text').textContent = 'Analyzing...';

  showState('loading');

  const selectedTypes = [...document.querySelectorAll('input[name="job_type"]:checked')]
  .map(cb => cb.value);


  const payload = {
  bio:           document.getElementById('bio').value,
  current_title: document.getElementById('current_title').value,
  skills:        document.getElementById('skills').value,
  target_role:   document.getElementById('target_role').value,
  region:        document.getElementById('region').value,
  top_k:         parseInt(document.getElementById('top_k').value),  
  job_types:     selectedTypes,
};

  try {
    const res  = await fetch('/recommend', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(payload)
    });
    const data = await res.json();

    if (!res.ok) {
      showError(data.error || 'Something went wrong');
      return;
    }

    renderResults(data);

  } catch (err) {
    showError('Network error — make sure the server is running');
  } finally {
    btn.classList.remove('loading');
    btn.querySelector('.btn-text').textContent = 'Find My Job Match';
  }
});

// ── State helpers ───────────────────────────────────────
function showState(state) {
  document.getElementById('emptyState').classList.add('hidden');
  document.getElementById('loadingState').classList.add('hidden');
  document.getElementById('errorState').classList.add('hidden');
  document.getElementById('resultsContent').classList.add('hidden');

  if (state === 'empty')   document.getElementById('emptyState').classList.remove('hidden');
  if (state === 'loading') document.getElementById('loadingState').classList.remove('hidden');
  if (state === 'error')   document.getElementById('errorState').classList.remove('hidden');
  if (state === 'results') document.getElementById('resultsContent').classList.remove('hidden');
}

function showError(msg) {
  document.getElementById('errorMsg').textContent = msg;
  showState('error');
}

// ── Render results ──────────────────────────────────────
function renderResults(data) {
  renderJobs(data.jobs || []);
  renderGap(data.gap);
  renderCourses(data.courses || []);

  // Update tab counts
  document.getElementById('jobsCount').textContent    = (data.jobs || []).length;
  document.getElementById('gapCount').textContent     = data.gap ? (data.gap.aggregated_gap || []).length : 0;
  document.getElementById('coursesCount').textContent = (data.courses || []).length;

  // Reset to jobs tab
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(c => c.classList.add('hidden'));
  document.querySelector('[data-tab="jobs"]').classList.add('active');
  document.getElementById('tabJobs').classList.remove('hidden');

  showState('results');
}

// ── Jobs ────────────────────────────────────────────────
function renderJobs(jobs) {
  const el = document.getElementById('jobsList');
  if (!jobs.length) {
    el.innerHTML = '<p style="color:var(--text-3);padding:2rem;text-align:center">No jobs found</p>';
    return;
  }

  el.innerHTML = jobs.map((job, i) => {
    const sim     = job.similarity;
    const skills  = job.skills ? job.skills.substring(0, 120) + '...' : '';
    const level   = job.level  || '';
    const jobType = job.job_type || '';

    return `
    <div class="job-card" style="animation-delay:${i * 0.05}s">
      <div class="job-header">
        <div class="job-title">${escHtml(job.job_title)}</div>
        <div class="job-score">${sim}%</div>
      </div>
      <div class="job-meta">
        <span>🏢 ${escHtml(job.company)}</span>
        <span>📍 ${escHtml(job.location)}</span>
        ${level   ? `<span>⚡ ${escHtml(level)}</span>`   : ''}
        ${jobType ? `<span>🏠 ${escHtml(jobType)}</span>` : ''}
      </div>
      <div class="sim-bar-wrap">
        <div class="sim-bar">
          <div class="sim-bar-fill" style="width:${sim}%"></div>
        </div>
      </div>
      ${skills ? `<div class="job-skills">🔑 ${escHtml(skills)}</div>` : ''}
    </div>`;
  }).join('');
}

// ── Gap ─────────────────────────────────────────────────
function renderGap(gap) {
  const el = document.getElementById('gapContent');

  if (!gap || !gap.user_skills || gap.user_skills.length === 0) {
    el.innerHTML = `
      <div class="no-skills-notice">
        <div style="font-size:2rem">📊</div>
        <p>Add your <strong>skills</strong> to the profile<br>to see a detailed gap analysis</p>
      </div>`;
    return;
  }

  const n_jobs = gap.per_job ? gap.per_job.length : 5;

  // Aggregated priority list
  const aggHtml = (gap.aggregated_gap || []).slice(0, 10).map(item => {
    const pct      = Math.round(item.frequency * 100);
    const priority = item.frequency >= 0.8 ? 'critical' : item.frequency >= 0.5 ? 'important' : 'nice';
    const label    = item.frequency >= 0.8 ? '🔴 Critical' : item.frequency >= 0.5 ? '🟡 Important' : '⚪ Nice to have';
    return `
    <div class="gap-item">
      <div class="priority-dot priority-${priority}"></div>
      <div class="gap-skill">${escHtml(item.skill)}</div>
      <div class="gap-bar">
        <div class="gap-bar-fill ${priority}" style="width:${pct}%"></div>
      </div>
      <div class="gap-freq">${item.count}/${n_jobs} jobs</div>
    </div>`;
  }).join('');

  // Per-job breakdown
  const perJobHtml = (gap.per_job || []).map(job => {
    const covPct = Math.round(job.coverage * 100);
    const matchedStr = (job.matched || [])
      .map(m => {
        const diff = m.job_skill.toLowerCase() !== m.user_skill.toLowerCase()
          ? ` <span style="color:var(--text-3)">(≈${escHtml(m.user_skill)})</span>` : '';
        return `<span style="color:var(--success)">✓ ${escHtml(m.job_skill)}${diff}</span>`;
      }).join('  ');
    const missingStr = (job.missing || [])
      .slice(0, 8)
      .map(s => `<span style="color:var(--text-3)">✗ ${escHtml(s)}</span>`)
      .join('  ');
    const more = (job.missing || []).length > 8
      ? `<span style="color:var(--text-3)"> +${job.missing.length - 8} more</span>` : '';

    return `
    <div class="gap-summary">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.6rem">
        <div class="gap-summary-title">${escHtml(job.job_title)}</div>
        <div style="font-size:0.75rem;color:var(--text-3)">${covPct}% covered</div>
      </div>
      <div class="sim-bar-wrap" style="margin-bottom:0.6rem">
        <div class="sim-bar"><div class="sim-bar-fill" style="width:${covPct}%"></div></div>
      </div>
      ${matchedStr ? `<div style="font-size:0.78rem;line-height:2;margin-bottom:0.3rem">${matchedStr}</div>` : ''}
      ${missingStr ? `<div style="font-size:0.78rem;line-height:2">${missingStr}${more}</div>` : ''}
    </div>`;
  }).join('');

  el.innerHTML = `
    <div class="gap-summary">
      <div class="gap-summary-title">Priority gap skills</div>
      ${aggHtml || '<p style="color:var(--text-3);font-size:0.85rem">No gap found — great coverage!</p>'}
    </div>
    <div style="margin-top:1.2rem">
      <div class="gap-summary-title" style="font-size:0.8rem;color:var(--text-3);margin-bottom:0.8rem;letter-spacing:0.05em;text-transform:uppercase">Per job breakdown</div>
      ${perJobHtml}
    </div>`;
}

// ── Courses ─────────────────────────────────────────────
function renderCourses(courses) {
  const el = document.getElementById('coursesList');

  if (!courses.length) {
    el.innerHTML = `
      <div class="no-skills-notice">
        <div style="font-size:2rem">📚</div>
        <p>Add your <strong>skills</strong> to the profile<br>to get course recommendations</p>
      </div>`;
    return;
  }

  el.innerHTML = courses.map((c, i) => {
    const priority = c.frequency >= 0.8 ? 'critical' : c.frequency >= 0.5 ? 'important' : 'nice';
    const label    = c.frequency >= 0.8 ? '🔴 Critical' : c.frequency >= 0.5 ? '🟡 Important' : '⚪ Nice to have';
    const pct      = Math.round(c.frequency * 100);
    const stars    = '★'.repeat(Math.round(c.rating)) + '☆'.repeat(5 - Math.round(c.rating));

    return `
    <div class="course-card" style="animation-delay:${i * 0.05}s">
      <div class="course-skill-badge ${priority}">
        ${label} · Gap: ${escHtml(c.skill)} · ${c.count}/${courses.length > 5 ? 5 : courses.length} jobs (${pct}%)
      </div>
      <div class="course-name">${escHtml(c.course_name)}</div>
      <div class="course-meta">
        <span>🏛 ${escHtml(c.university)}</span>
        <span>📈 ${escHtml(c.level)}</span>
        <span class="course-rating">${stars} ${c.rating.toFixed(1)}</span>
      </div>
      <a class="course-link" href="${escHtml(c.url)}" target="_blank" rel="noopener">
        View on Coursera
      </a>
    </div>`;
  }).join('');
}

// ── Escape HTML ─────────────────────────────────────────
function escHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}