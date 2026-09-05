'use strict';
const $ = (id) => document.getElementById(id);
const el = (tag, text, cls) => {
  const n = document.createElement(tag);
  if (text !== undefined) n.textContent = text;
  if (cls) n.className = cls;
  return n;
};
let caps, schema, controls = new Map(),
  artifacts = [],
  currentJob = null,
  pollTimer = null,
  reviewed = false,
  planJob = null,
  planResult = null;
const names = {
  audio_plan: 'Audio plan',
  audio_workflow: 'Audio workflow',
  transcribe: 'Transcribe · Supadata',
  visual: 'Understand video · Gemini',
  pipeline: 'Library pipeline',
  inspect: 'Inspect source',
  download: 'Download format',
  thumbnail: 'Download thumbnail',
  probe: 'Probe local media',
  extract: 'Extract audio',
  convert: 'Convert audio',
  enrich: 'Enrich audio'
};

function resolve(s) {
  if (s.$ref) return resolve(schema.$defs[s.$ref.split('/').pop()]);
  if (s.anyOf) return resolve(s.anyOf.find(x => x.type !== 'null'));
  return s;
}

function labelFor(key) {
  return key.replaceAll('_', ' ').replace(/^./, c => c.toUpperCase());
}

function help(text, name = 'this setting') {
  const d = el('details', undefined, 'help'),
    summary = el('summary', '?');
  summary.setAttribute('aria-label', `Help for ${name}`);
  d.append(summary, el('p', text));
  return d;
}

function field(key, raw, path, required) {
  const s = resolve(raw),
    wrap = el('div', undefined, 'field');
  wrap.dataset.path = path;
  if (s.type === 'object' && s.properties) {
    const group = el('details', undefined, 'group');
    group.open = true;
    group.dataset.path = path;
    group.append(el('summary', labelFor(key)));
    for (const [k, v] of Object.entries(s.properties)) group.append(field(k, v, `${path}.${k}`, (s.required || []).includes(k)));
    return group;
  }
  const head = el('div', undefined, 'field-heading'),
    label = el('label', labelFor(key) + (required ? ' *' : ''));
  label.htmlFor = path;
  head.append(label, help(raw.description || s.description || `Set ${key.replaceAll('_',' ')} explicitly for this operation.${required?' Required when applicable.':' Optional; leave blank to omit.'}`, labelFor(key)));
  wrap.append(head);
  let input;
  if (s.enum) {
    input = el('select');
    input.append(new Option('Choose…', ''));
    s.enum.forEach(v => input.append(new Option(names[v] || v, v)));
  } else if (key.endsWith('artifact_id')) {
    input = el('select');
    input.append(new Option('Choose session file…', ''));
    input.dataset.artifact = 'true';
  } else if (key.endsWith('_path')) {
    input = el('select');
    input.append(new Option('Choose detected executable…', ''));
  } else if (s.type === 'boolean') {
    input = el('input');
    input.type = 'checkbox';
  } else if (s.type === 'array' || s.type === 'object' || key === 'cookie_text' || key === 'transcript_context') {
    input = el('textarea');
    input.placeholder = s.type === 'array' ? 'JSON array' : s.type === 'object' ? 'JSON object' : '';
  } else {
    input = el('input');
    input.type = ['number', 'integer'].includes(s.type) ? 'number' : key === 'url' ? 'url' : 'text';
    if (input.type === 'number') {
      input.step = s.type === 'integer' ? '1' : 'any';
      if (s.minimum !== undefined) input.min = s.minimum;
      if (s.exclusiveMinimum !== undefined) input.min = s.exclusiveMinimum;
    }
  }
  input.id = path;
  input.autocomplete = 'off';
  input.dataset.required = required ? 'true' : 'false';
  controls.set(path, {
    input,
    s,
    wrap
  });
  wrap.append(input);
  return wrap;
}

function val(path) {
  const c = controls.get(path);
  return c.s.type === 'boolean' ? c.input.checked : c.input.value;
}

function shown(path, yes) {
  const n = document.querySelector(`[data-path="${path}"]`);
  if (n) n.hidden = !yes;
}

function action() {
  return val('action');
}

function activeSections() {
  const a = action(),
    p = a === 'pipeline',
    w = a === 'audio_workflow',
    en = w && $('enable-enrichment').checked,
    conversion = w && !!planResult?.plan?.requires_mp3_conversion;
  return {
    media: ['inspect', 'audio_plan', 'download', 'thumbnail', 'audio_workflow'].includes(a) || (p && (val('pipeline.metadata') || val('pipeline.media') || val('pipeline.visual'))),
    transcript: a === 'transcribe' || (p && val('pipeline.transcript')),
    visual: a === 'visual' || (p && val('pipeline.visual')),
    local: ['probe', 'extract', 'convert', 'enrich'].includes(a) || (w && (en || conversion)),
    transform: ['extract', 'convert'].includes(a) || conversion,
    enrichment: a === 'enrich' || en,
    pipeline: p
  };
}

function sync() {
  const a = action(),
    sections = activeSections();
  for (const k of Object.keys(sections)) shown(k, sections[k]);
  shown('url', ['inspect', 'audio_plan', 'download', 'thumbnail', 'transcribe', 'pipeline', 'audio_workflow'].includes(a));
  shown('input_artifact_id', ['visual', 'probe', 'extract', 'convert', 'enrich'].includes(a));
  shown('selected_format_id', a === 'download');
  shown('compatible_bitrate_ratio', a === 'audio_plan' || (a === 'audio_workflow' && !reviewed));
  shown('plan_job_id', false);
  $('enrichment-toggle').hidden = a !== 'audio_workflow';
  shown('enrichment.source_cover', a === 'audio_workflow');
  shown('pipeline.selected_format_id', a === 'pipeline' && val('pipeline.media'));
  shown('pipeline.visual_format_id', a === 'pipeline' && val('pipeline.visual'));
  shown('visual.transcript_context', a === 'visual');
  const mode = val('visual.settings.processing_mode');
  shown('visual.settings.static_fps', ['static', 'automatic'].includes(mode));
  shown('visual.settings.agentic_threshold_seconds', mode === 'automatic');
  shown('visual.windows', val('visual.timestamp_mode') === 'windows');
  const runtime = val('media.runtime_name'),
    path = controls.get('media.runtime_path').input,
    prev = path.value;
  path.replaceChildren(new Option('Choose detected executable…', ''));
  (caps.executables[runtime] || []).forEach(p => path.append(new Option(p, p)));
  path.value = prev;
  $('review').hidden = !(a === 'audio_workflow' && planJob);
  $('run').textContent = a === 'audio_workflow' ? (reviewed ? 'Run reviewed audio workflow' : 'Inspect & build audio plan') : 'Run operation';
  markRequired();
  drawPlan();
}

function markRequired() {
  const conditional = ['visual.settings.static_fps', 'visual.settings.agentic_threshold_seconds', 'pipeline.selected_format_id', 'pipeline.visual_format_id', 'selected_format_id', 'compatible_bitrate_ratio', 'url', 'input_artifact_id'];
  for (const path of conditional) {
    const c = controls.get(path);
    const required = !c.input.closest('[hidden]');
    c.wrap.querySelector('label').textContent = labelFor(path.split('.').at(-1)) + (required ? ' * (required)' : '');
    c.input.setAttribute('aria-required', String(required));
  }
}

function drawPlan() {
  const a = action(),
    nodes = [];
  if (a === 'pipeline') {
    const initial = [];
    if (val('pipeline.metadata')) initial.push('Inspect source → metadata');
    if (val('pipeline.transcript')) initial.push('Supadata → transcript');
    if (val('pipeline.media') || val('pipeline.visual')) initial.push('Download selected media');
    if (initial.length) nodes.push('Start in parallel: ' + initial.join(' ∥ '));
    nodes.push('Barrier: every requested initial stage must succeed');
    if (val('pipeline.visual')) nodes.push('After barrier → Gemini visual analysis' + (val('pipeline.include_transcript_context') ? ' with transcript context' : ''));
    nodes.push('All requested outputs complete → result');
  } else if (a === 'audio_workflow') {
    nodes.push('Inspect source → compare audio formats → review plan');
    nodes.push('Explicit review → download selected audio');
    if (planResult?.plan?.requires_mp3_conversion) nodes.push('Convert to MP3');
    if ($('enable-enrichment').checked) nodes.push(val('enrichment.source_cover') ? 'Download source cover → enrich audio' : 'Apply tags / uploaded cover');
  } else nodes.push(names[a] || 'Choose an operation');
  $('planned').replaceChildren(...nodes.map(x => el('div', x, 'node')));
}

function readGroup(prefix) {
  const out = {};
  for (const [path, c] of controls) {
    if (!path.startsWith(prefix + '.') || c.input.closest('[hidden]')) continue;
    const raw = c.input.value;
    let value;
    if (c.s.type === 'boolean') value = c.input.checked;
    else if (raw === '') continue;
    else if (['integer', 'number'].includes(c.s.type)) value = Number(raw);
    else if (['array', 'object'].includes(c.s.type)) value = JSON.parse(raw);
    else value = raw;
    const keys = path.slice(prefix.length + 1).split('.');
    let target = out;
    keys.slice(0, -1).forEach(k => target = target[k] || (target[k] = {}));
    target[keys.at(-1)] = value;
  }
  return out;
}

function payload() {
  const a = action();
  let req = {
    action: a
  };
  for (const key of ['url', 'input_artifact_id', 'selected_format_id', 'compatible_bitrate_ratio']) {
    const c = controls.get(key);
    if (!c.wrap.hidden && c.input.value !== '') req[key] = c.s.type === 'number' ? Number(c.input.value) : c.input.value;
  }
  const sections = activeSections();
  Object.entries(sections).forEach(([key, on]) => {
    if (on) req[key] = readGroup(key);
  });
  if (a === 'audio_workflow') {
    if (!reviewed) {
      req = {
        action: 'audio_plan',
        url: req.url,
        media: req.media,
        compatible_bitrate_ratio: req.compatible_bitrate_ratio
      };
    } else {
      req.plan_job_id = planJob;
      delete req.compatible_bitrate_ratio;
    }
  }
  return req;
}
async function api(url, options = {}) {
  const r = await fetch(url, options);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) {
    const message = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail || body);
    const error = Error(message + (body.fields ? '\nFields: ' + JSON.stringify(body.fields) : ''));
    error.status = r.status;
    throw error;
  }
  return body;
}

function safeUrl(url) {
  if (typeof url !== 'string' || !url.trim()) return null;
  try {
    const u = new URL(url, location.href);
    return ['http:', 'https:'].includes(u.protocol) ? u.href : null;
  } catch {
    return null;
  }
}

function timelineLabel(row) {
  const start = row.start_seconds ?? row.start ?? row.timestamp_seconds ?? row.timestamp,
    end = row.end_seconds ?? row.end;
  const window = row.window ?? row.window_label;
  if (window != null) return 'Window: ' + (typeof window === 'object' ? JSON.stringify(window) : window);
  if (start == null) return 'Untimed';
  const mode = row.timestamp_mode ?? row.timing ?? (row.timestamp_seconds != null ? 'approximate' : '');
  return (mode === 'approximate' ? 'Approx. ' : '') + String(start) + (end != null ? '–' + end : '') + ' s';
}

function render(value, depth = 0) {
  if (value === null || value === undefined) return el('span', '—');
  if (typeof value !== 'object') return el('div', String(value), 'readable');
  if (depth > 7) return el('pre', JSON.stringify(value, null, 2));
  if (value.download_url && value.id) {
    const div = el('div');
    div.append(el('p', value.filename || value.id));
    const href = safeUrl(value.download_url);
    if (href) {
      const a = el('a', 'Download file');
      a.href = href;
      div.append(a);
    }
    return div;
  }
  if (Array.isArray(value)) {
    if (!value.length) return el('p', 'No entries.', 'muted');
    if (value.every(x => x && typeof x === 'object' && !Array.isArray(x))) {
      const wrap = el('div', undefined, 'table-wrap'),
        table = el('table'),
        head = el('tr'),
        keys = [...new Set(value.flatMap(Object.keys))];
      const timed = keys.some(k => ['start_seconds', 'end_seconds', 'timestamp_seconds', 'start', 'end', 'timestamp', 'window'].includes(k));
      if (timed) {
        const caption = el('caption', 'Segment / event timeline · seconds; approximate timestamps and supplied windows are labeled below.');
        table.append(caption);
        head.append(el('th', 'Time / window'));
      }
      keys.forEach(k => head.append(el('th', labelFor(k))));
      const thead = el('thead');
      thead.append(head);
      table.append(thead);
      const tbody = el('tbody');
      value.forEach(row => {
        const tr = el('tr');
        if (timed) tr.append(el('td', timelineLabel(row)));
        keys.forEach(k => {
          const td = el('td');
          if ((k === 'url' || k === 'preview_url') && safeUrl(row[k])) {
            const a = el('a', 'Open');
            a.href = safeUrl(row[k]);
            a.target = '_blank';
            a.rel = 'noopener noreferrer';
            td.append(a);
            if (/thumbnail|image/i.test(JSON.stringify(row)) || /\.(jpg|jpeg|png|webp)(\?|$)/i.test(row[k])) {
              const img = el('img');
              img.src = a.href;
              img.alt = 'Source thumbnail';
              img.loading = 'lazy';
              td.append(img);
            }
          } else td.append(render(row[k], depth + 1));
          tr.append(td);
        });
        tbody.append(tr);
      });
      table.append(tbody);
      wrap.append(table);
      return wrap;
    }
    const div = el('div');
    value.forEach(x => div.append(render(x, depth + 1)));
    return div;
  }
  const div = el('div');
  const facts = el('dl', undefined, 'facts');
  for (const [key, item] of Object.entries(value)) {
    if (item === null || typeof item !== 'object') {
      const row = el('div');
      row.append(el('dt', labelFor(key)), el('dd', item == null ? '—' : String(item)));
      facts.append(row);
    }
  }
  if (facts.childNodes.length) div.append(facts);
  Object.entries(value).forEach(([k, v]) => {
    if (v === null || typeof v !== 'object') return;
    const block = el('div', undefined, 'result-block');
    block.append(el('h3', labelFor(k)), render(v, depth + 1));
    div.append(block);
  });
  return div;
}

function showJob(job) {
  $('job-status').textContent = `${names[job.action]||job.action} · ${job.state} · ${Number(job.elapsed_seconds||0).toFixed(1)}s`;
  $('steps').replaceChildren(...job.steps.map(s => {
    const n = el('div', `${labelFor(s.id)} · ${s.state} · ${Number(s.elapsed_seconds).toFixed(1)}s`, 'step');
    n.dataset.state = s.state;
    n.append(el('small', s.dependencies.length ? `After: ${s.dependencies.join(', ')}` : 'Ready independently'));
    if (s.progress) {
      const p = s.progress;
      n.append(el('small', `${p.phase||'Working'}${p.downloaded_bytes!=null?' · '+p.downloaded_bytes+' bytes':''}${p.total_bytes?' / '+p.total_bytes+(p.total_is_estimate?' estimated':''):''}`));
      if (p.total_bytes) {
        const bar = el('progress');
        bar.max = p.total_bytes;
        bar.value = p.downloaded_bytes || 0;
        bar.setAttribute('aria-label', labelFor(s.id) + ' download progress');
        n.append(bar);
      }
    }
    if (s.state === 'running' && !s.progress?.total_bytes) {
      const bar = el('progress');
      bar.setAttribute('aria-label', labelFor(s.id) + ' in progress');
      n.append(bar);
    }
    return n;
  }));
  $('logs').textContent = JSON.stringify(job.logs, null, 2);
  if (job.error) $('notice').textContent = job.error;
}
async function poll() {
  if (!currentJob) return;
  try {
    const job = await api(`/api/jobs/${currentJob}`);
    showJob(job);
    if (['completed', 'failed', 'cancelled'].includes(job.state)) {
      currentJob = null;
      $('cancel').disabled = true;
      $('run').disabled = false;
      if (job.state === 'completed') {
        $('result').replaceChildren(render(job.result));
        const raw = el('details');
        raw.append(el('summary', 'Raw JSON'), el('pre', JSON.stringify(job.result, null, 2)));
        $('result').append(raw);
        if (job.action === 'audio_plan' && action() === 'audio_workflow') {
          planJob = job.id;
          planResult = job.result;
          reviewed = false;
          $('plan-result').replaceChildren(render(job.result.plan));
          $('review-status').textContent = 'Review required before downloading.';
          sync();
        }
      } else $('result').replaceChildren(el('p', 'No results were published for this job. Earlier files remain in Session files.'));
      await refreshArtifacts();
    } else pollTimer = setTimeout(poll, 1000);
  } catch (e) {
    $('notice').textContent = e.message;
    if (e.status === 404) {
      currentJob = null;
      $('cancel').disabled = true;
      $('run').disabled = true;
      $('notice').textContent += ' Reload the page to start a new session.';
    } else pollTimer = setTimeout(poll, 1000);
  }
}
async function refreshArtifacts() {
  artifacts = await api('/api/artifacts');
  for (const [path, c] of controls) {
    if (!c.input.dataset.artifact || path === 'media.cookie_artifact_id') continue;
    const prev = c.input.value;
    c.input.replaceChildren(new Option('Choose session file…', ''));
    artifacts.filter(a => !path.includes('cover_') || a.media_type.startsWith('image/')).forEach(a => c.input.append(new Option(a.filename + ' · ' + a.id, a.id)));
    c.input.value = prev;
  }
  $('artifacts').replaceChildren(...artifacts.map(a => {
    const d = el('div', undefined, 'artifact');
    d.append(el('p', `${a.filename} · ${a.size_bytes.toLocaleString()} bytes`));
    const link = el('a', 'Download');
    link.href = a.download_url;
    d.append(link);
    const preview = el('details');
    preview.append(el('summary', 'Preview'));
    if (a.media_type.startsWith('image/')) {
      const im = el('img');
      im.src = a.preview_url;
      im.alt = a.filename;
      preview.append(im);
    } else if (/^(audio|video)\//.test(a.media_type)) {
      const media = el(a.media_type.startsWith('audio/') ? 'audio' : 'video');
      media.controls = true;
      media.preload = 'metadata';
      media.src = a.preview_url;
      preview.append(media);
    } else {
      const l = el('a', 'Open browser preview');
      l.href = a.preview_url;
      l.target = '_blank';
      l.rel = 'noopener';
      preview.append(l);
    }
    d.append(preview);
    const del = el('button', 'Delete');
    del.type = 'button';
    del.onclick = async () => {
      try {
        await api(`/api/artifacts/${a.id}`, {
          method: 'DELETE'
        });
        await refreshArtifacts();
      } catch (e) {
        $('notice').textContent = e.message;
      }
    };
    d.append(del);
    return d;
  }));
}
async function init() {
  try {
    caps = await api('/api/capabilities');
    schema = caps.schema;
    $('capabilities').textContent = `Supadata ${caps.credentials.supadata?'configured':'unavailable'} · Gemini ${caps.credentials.gemini?'configured':'unavailable'} · FFmpeg ${(caps.executables.ffmpeg||[]).length?'available':'unavailable'}`;
    $('retention').textContent = `Session files are retained for ${Math.round(caps.retention_seconds/60)} minutes. Download anything you want to keep.`;
    for (const [key, s] of Object.entries(schema.properties)) $('fields').append(field(key, s, key, (schema.required || []).includes(key)));
    for (const key of ['ffmpeg', 'ffprobe']) {
      const input = controls.get(`local.${key}_path`).input;
      (caps.executables[key] || []).forEach(p => input.append(new Option(p, p)));
    }
    const toggle = el('div', undefined, 'field');
    toggle.id = 'enrichment-toggle';
    const lab = el('label', ' Add audio tags or cover art');
    const cb = el('input');
    cb.id = 'enable-enrichment';
    cb.type = 'checkbox';
    lab.prepend(cb);
    toggle.append(lab, help('Optional audio workflow enrichment. Configure local tools and metadata when enabled.'));
    $('fields').append(toggle);
    const cookie = controls.get('media.cookie_artifact_id'),
      upload = el('input');
    upload.type = 'file';
    upload.setAttribute('aria-label', 'Upload Netscape cookie file');
    cookie.wrap.append(upload, el('p', 'Cookies are temporary and consumed by each job. Upload or paste them again for the audio download after reviewing its plan.', 'muted'));
    upload.onchange = async () => {
      if (!upload.files[0]) return;
      try {
        const f = new FormData();
        f.append('file', upload.files[0]);
        f.append('kind', 'cookie');
        const a = await api('/api/uploads', {
          method: 'POST',
          body: f
        });
        cookie.input.append(new Option(a.filename, a.id));
        cookie.input.value = a.id;
        controls.get('media.cookie_text').input.value = '';
        upload.value = '';
        sync();
      } catch (e) {
        $('notice').textContent = e.message;
      }
    };
    $('fields').addEventListener('change', e => {
      if (['url', 'compatible_bitrate_ratio'].includes(e.target.id) || ['media.request_timeout_seconds', 'media.runtime_name', 'media.runtime_path'].includes(e.target.id)) {
        reviewed = false;
        planJob = null;
        planResult = null;
      }
      sync();
    });
    $('fields').addEventListener('input', e => {
      if (['url', 'compatible_bitrate_ratio'].includes(e.target.id) || ['media.request_timeout_seconds', 'media.runtime_name', 'media.runtime_path'].includes(e.target.id)) {
        reviewed = false;
        planJob = null;
        planResult = null;
        sync();
      }
    });
    controls.get('action').input.value = 'inspect';
    sync();
    await refreshArtifacts();
  } catch (e) {
    $('notice').textContent = `Could not load demo: ${e.message}`;
    $('run').disabled = true;
  }
}
$('request-form').onsubmit = async e => {
  e.preventDefault();
  if (!caps || currentJob) return;
  $('run').disabled = true;
  $('notice').textContent = '';
  try {
    const body = payload();
    const job = await api('/api/jobs', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(body)
    });
    controls.get('media.cookie_text').input.value = '';
    controls.get('media.cookie_artifact_id').input.replaceChildren(new Option('Upload cookies again for another job…', ''));
    currentJob = job.id;
    $('result').replaceChildren(el('p', 'Waiting for this job to complete successfully.'));
    $('run').disabled = true;
    $('cancel').disabled = false;
    await poll();
  } catch (err) {
    $('notice').textContent = err.message;
    $('run').disabled = false;
  } finally {
    controls.get('media.cookie_text').input.value = '';
  }
};
$('approve-plan').onclick = () => {
  reviewed = true;
  $('review-status').textContent = 'Plan reviewed. Configure any required conversion settings, then run.';
  sync();
};
$('cancel').onclick = async () => {
  try {
    if (currentJob) await api(`/api/jobs/${currentJob}/cancel`, {
      method: 'POST'
    });
  } catch (e) {
    $('notice').textContent = e.message;
  }
};
$('upload-form').onsubmit = async e => {
  e.preventDefault();
  try {
    const f = new FormData();
    f.append('file', $('upload-file').files[0]);
    if ($('upload-duration').value) f.append('duration_seconds', $('upload-duration').value);
    await api('/api/uploads', {
      method: 'POST',
      body: f
    });
    $('upload-form').reset();
    await refreshArtifacts();
    $('notice').textContent = '';
  } catch (err) {
    $('notice').textContent = err.message;
  }
};
$('clear-session').onclick = async () => {
  try {
    await api('/api/session', {
      method: 'DELETE'
    });
    clearTimeout(pollTimer);
    currentJob = null;
    planJob = null;
    planResult = null;
    reviewed = false;
    controls.get('media.cookie_text').input.value = '';
    controls.get('media.cookie_artifact_id').input.replaceChildren(new Option('Choose cookie file…', ''));
    $('run').disabled = false;
    $('cancel').disabled = true;
    $('result').replaceChildren(el('p', 'Session cleared.'));
    $('steps').replaceChildren();
    $('logs').textContent = '[]';
    $('job-status').textContent = 'No job started.';
    $('notice').textContent = '';
    $('plan-result').replaceChildren();
    $('review-status').textContent = '';
    caps = await api('/api/capabilities');
    await refreshArtifacts();
    sync();
  } catch (e) {
    $('notice').textContent = e.message;
  }
};
document.querySelectorAll('[data-preset]').forEach(b => b.onclick = () => {
  if (!caps) return;
  controls.get('action').input.value = b.dataset.preset;
  sync();
});
init();
