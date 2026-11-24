let allLoops = [];
let selectedLoop = null;
let currentData = null;
let activeChart = 'time';
let hoverIdx = null;
let hoverClientX = 0;
let hoverClientY = 0;
let replayProgress = 1.0;
let replayRaf = null;
let latestRequestSeq = 0;  // V4.0 Race-Condition Guard: stale responses NEVER overwrite newer runs!

const ANOMALY_ZH = {
  AGGRESSIVE_TUNING: '激进振荡',
  MODEL_MISMATCH: '模型失配',
  SLUGGISH_TUNING: '保守迟缓',
  VALVE_STICTION: '阀门粘滞',
  EXTERNAL_DISTURBANCE: '外部扰动',
  NORMAL: '运行正常',
};

const STATUS_ZH = {
  SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW: '仿真通过 · 待人工复核',
  HEALTHY_NO_CHANGE: '运行健康 · 无需变更',
  NO_CHANGE_HEALTHY: '运行健康 · 无需变更',
  MODEL_VALIDATION_FAILED: '模型未过 · 拒绝变更',
  VALVE_MAINTENANCE_REQUIRED: '阀门粘滞 · 建议检修',
  PERFORMANCE_NOT_IMPROVED: '外扰未改善 · 保持原参',
  SAFETY_REJECTED: '安全拦截 · 拒绝变更',
  INPUT_DATA_INVALID: '输入异常 · 拒绝执行',
  SIMULATION_TIMEOUT: '仿真超时 · 拒绝变更',
  AUDIT_INCOMPLETE: '审计缺失 · 拒绝变更',
};

const SEV_CLASS = {
  AGGRESSIVE_TUNING: 'sev-red',
  MODEL_MISMATCH: 'sev-amber',
  SLUGGISH_TUNING: 'sev-blue',
  VALVE_STICTION: 'sev-purple',
  EXTERNAL_DISTURBANCE: 'sev-amber',
  NORMAL: 'sev-ok',
};

function zhAnomaly(code) { return ANOMALY_ZH[code] || code; }
function zhStatus(code) { return STATUS_ZH[code] || `未验证状态 (${code || 'UNKNOWN'})`; }
function escHtml(v) {
  return String(v ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

async function init() {
  const [benchRes, loopsRes] = await Promise.all([
    fetch('/api/benchmark').then(r => r.json()),
    fetch('/api/loops').then(r => r.json()),
  ]);

  // ISA-101 Plant Control Health Bar
  const d = benchRes.denominators || {};
  document.getElementById('rTotal').textContent = `${loopsRes.loops.length} 回路`;
  document.getElementById('rHealthy').textContent = `${d.healthy_no_change_loops ?? 5} 个`;
  document.getElementById('rRetune').textContent = `${d.simulation_validated_retuned_loops ?? 11} 个`;
  document.getElementById('rValve').textContent = `${d.valve_maintenance_required_loops ?? 5} 个`;
  document.getElementById('rBlock').textContent = `${(d.model_validation_failed_loops ?? 6) + (d.performance_not_improved_loops ?? 3)} 个`;
  document.getElementById('rDiag').textContent = `${benchRes.diagnosis_accuracy_pct}%`;

  // View 3 Plant KPI Cards
  document.getElementById('pkSuccess').textContent = `${benchRes.task_success_rate_pct}%`;
  document.getElementById('pkDiag').textContent = `${benchRes.diagnosis_accuracy_pct}%`;
  document.getElementById('pkId').textContent = `${benchRes.avg_id_val_accuracy_pct}%`;
  document.getElementById('pkIdSub').textContent = `有效 n=19 (全25非健康均值 ${benchRes.avg_id_val_accuracy_all_25_non_healthy_pct}%)`;
  document.getElementById('pkSafe').textContent = `${benchRes.safety_constraint_coverage_pct}% / ${benchRes.unsafe_flagging_rate_pct}%`;
  document.getElementById('pkMulti').textContent = `${benchRes.avg_multi_regime_pass_rate_pct}%`;
  document.getElementById('pkImp').textContent = `-${benchRes.avg_oi_reduction_pct}% / -${benchRes.avg_iae_reduction_pct}%`;

  allLoops = loopsRes.loops;
  renderLoopList();
  renderPlantTable(benchRes.per_loop_results || []);
  setupEvents();

  const def = allLoops.find(l => l.loop_id === 'LOOP-006') || allLoops[0];
  if (def) {
    selectLoop(def);
    runWorkflow(def.loop_id);
  }
}

function setupEvents() {
  document.querySelectorAll('.nav-tab').forEach(btn => {
    btn.onclick = () => {
      document.querySelectorAll('.nav-tab').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById(btn.dataset.view).classList.add('active');
      if (btn.dataset.view === 'view-workbench' && currentData) renderActiveChart();
    };
  });

  document.querySelectorAll('.c-tab').forEach(btn => {
    btn.onclick = () => {
      document.querySelectorAll('.c-tab').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      activeChart = btn.dataset.chart;
      hoverIdx = null;
      replayProgress = 1.0;
      hideTip();
      if (currentData) renderActiveChart();
    };
  });

  document.querySelectorAll('.d-tab').forEach(btn => {
    btn.onclick = () => {
      document.querySelectorAll('.d-tab').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.detail-pane').forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById(btn.dataset.detail).classList.add('active');
    };
  });

  document.querySelectorAll('.r-tab').forEach(btn => {
    btn.onclick = () => {
      document.querySelectorAll('.r-tab').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.right-pane').forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById(btn.dataset.right).classList.add('active');
    };
  });

  document.getElementById('anomalyFilter').onchange = renderLoopList;
  document.getElementById('loopSearch').oninput = renderLoopList;

  document.getElementById('runBtn').onclick = () => {
    if (!selectedLoop) return;
    const strat = document.getElementById('strategySelect').value || null;
    runWorkflow(selectedLoop.loop_id, { preferred_strategy: strat });
  };
  document.getElementById('approvalBtn').onclick = () => {
    if (!selectedLoop) return;
    const rid = currentData && currentData.audit_meta ? `?run_id=${encodeURIComponent(currentData.audit_meta.run_id)}` : '';
    window.open(`/api/approval/${selectedLoop.loop_id}${rid}`, '_blank');
  };
  document.getElementById('bundleBtn').onclick = () => {
    if (!selectedLoop) return;
    const rid = currentData && currentData.audit_meta ? `?run_id=${encodeURIComponent(currentData.audit_meta.run_id)}` : '';
    window.open(`/api/export_bundle/${selectedLoop.loop_id}${rid}`, '_blank');
  };
  document.getElementById('replayBtn').onclick = startReplay;

  // Interactive Canvas Crosshair + Floating Glass Tooltip
  const mc = document.getElementById('mainCanvas');
  mc.addEventListener('mousemove', e => {
    if (!currentData || (activeChart !== 'time' && activeChart !== 'ident')) { hideTip(); return; }
    const rect = mc.getBoundingClientRect();
    const padL = 54, padR = 18;
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const n = currentData.waveforms.t.length;
    const ratio = Math.max(0, Math.min(1, (x - padL) / Math.max(1, rect.width - padL - padR)));
    hoverIdx = Math.round(ratio * (n - 1));
    hoverClientX = x;
    hoverClientY = y;
    renderActiveChart();
    updateFloatTip(rect.width, rect.height);
  });
  mc.addEventListener('mouseleave', () => {
    hoverIdx = null;
    hideTip();
    if (currentData) renderActiveChart();
  });

  document.getElementById('copilotSend').onclick = sendCopilot;
  document.getElementById('copilotInput').onkeydown = e => { if (e.key === 'Enter') sendCopilot(); };
  document.querySelectorAll('.quick-prompts .q-chip').forEach(c => {
    c.onclick = () => {
      document.getElementById('copilotInput').value = c.dataset.q;
      sendCopilot();
    };
  });

  document.getElementById('csvSampleOsc')?.addEventListener('click', () => submitCsvText('sample_fcc_oscillation.csv', buildSampleCsv('osc')));
  document.getElementById('csvSampleStic')?.addEventListener('click', () => submitCsvText('sample_cdu_stiction.csv', buildSampleCsv('stic')));
  document.getElementById('csvSampleBad')?.addEventListener('click', () => submitCsvText('sample_malformed_missing_op.csv', 't,sp,pv\n0,500,499\n1,500,501\n'));

  [['sK','vK'],['sTau','vTau'],['sTheta','vTheta'],['sKc','vKc'],['sTi','vTi'],['sS','vS'],['sOs','vOs']].forEach(([s,v]) => {
    const el = document.getElementById(s);
    el.oninput = () => document.getElementById(v).textContent = el.value;
  });
  document.getElementById('runSandboxBtn').onclick = runSandbox;
  document.getElementById('csvFileInput').onchange = handleCSVUpload;
}

function hideTip() {
  const tip = document.getElementById('floatTip');
  if (tip) tip.style.display = 'none';
}

function updateFloatTip(W, H) {
  const tip = document.getElementById('floatTip');
  if (hoverIdx === null || !currentData) { tip.style.display = 'none'; return; }
  if (activeChart === 'time') {
    const w = currentData.waveforms;
    tip.innerHTML = `
      <div style="color:#93c5fd;font-weight:700;margin-bottom:3px">t = ${w.t[hoverIdx]} s</div>
      <div>SP 设定值: <b>${w.sp[hoverIdx]}</b></div>
      <div style="color:#fca5a5">PV 整定前: <b>${w.pv_before[hoverIdx]}</b> (OP ${w.op_before[hoverIdx]}%)</div>
      <div style="color:#6ee7b7">PV 整定后: <b>${w.pv_after[hoverIdx]}</b> (OP ${w.op_after[hoverIdx]}%)</div>
    `;
  } else if (activeChart === 'ident' && currentData.identification_plot) {
    const ip = currentData.identification_plot;
    const err = (ip.pv_actual[hoverIdx] - ip.pv_predicted[hoverIdx]).toFixed(3);
    tip.innerHTML = `
      <div style="color:#93c5fd;font-weight:700;margin-bottom:3px">t = ${ip.t[hoverIdx]} s</div>
      <div>实测 PV: <b>${ip.pv_actual[hoverIdx]}</b></div>
      <div style="color:#60a5fa">预测 PV̂: <b>${ip.pv_predicted[hoverIdx]}</b></div>
      <div style="color:#fcd34d">预测残差: <b>${err}</b></div>
    `;
  } else {
    tip.style.display = 'none';
    return;
  }
  tip.style.display = 'block';
  const left = hoverClientX + 16 + 190 > W ? hoverClientX - 196 : hoverClientX + 16;
  const top = Math.max(10, Math.min(H - 96, hoverClientY - 24));
  tip.style.left = `${left}px`;
  tip.style.top = `${top}px`;
}

function startReplay() {
  if (!currentData) return;
  if (activeChart !== 'time') {
    document.querySelector('[data-chart="time"]').click();
  }
  if (replayRaf) cancelAnimationFrame(replayRaf);
  const t0 = performance.now();
  const dur = 2000;
  function step(now) {
    replayProgress = Math.min(1.0, (now - t0) / dur);
    renderActiveChart();
    if (replayProgress < 1.0) replayRaf = requestAnimationFrame(step);
  }
  replayRaf = requestAnimationFrame(step);
}

function renderLoopList() {
  const filter = document.getElementById('anomalyFilter').value;
  const q = (document.getElementById('loopSearch').value || '').trim().toLowerCase();
  const list = document.getElementById('loopList');
  list.innerHTML = '';
  const items = allLoops.filter(l => {
    if (filter !== 'ALL' && l.anomaly_type !== filter) return false;
    if (q && !(`${l.loop_id} ${l.tag_name} ${l.unit_name} ${l.description} ${l.anomaly_type} ${zhAnomaly(l.anomaly_type)}`.toLowerCase().includes(q))) return false;
    return true;
  });
  document.getElementById('loopCountTag').textContent = `${items.length}/${allLoops.length}`;

  // Group by Process Unit (ISA-101 / PlantESP hierarchical unit tree)
  const groups = new Map();
  items.forEach(loop => {
    const u = loop.unit_name || '未分组装置';
    if (!groups.has(u)) groups.set(u, []);
    groups.get(u).push(loop);
  });

  groups.forEach((uLoops, unitName) => {
    const abnCount = uLoops.filter(l => l.anomaly_type !== 'NORMAL').length;
    const hdr = document.createElement('div');
    hdr.className = 'unit-group-hdr';
    hdr.innerHTML = `<span>${unitName}</span><span class="u-badge ${abnCount > 0 ? 'has-alarm' : ''}">${abnCount > 0 ? `异常 ${abnCount}/${uLoops.length}` : `全健康 ${uLoops.length}`}</span>`;
    list.appendChild(hdr);

    uLoops.forEach(loop => {
      const row = document.createElement('div');
      const sev = SEV_CLASS[loop.anomaly_type] || 'sev-ok';
      row.className = `loop-row ${sev}` + (selectedLoop && selectedLoop.loop_id === loop.loop_id ? ' active' : '');
      row.innerHTML = `
        <div class="loop-row-top">
          <span class="tag-code">${loop.tag_name} <span style="font-weight:500;color:#64748b;font-size:10.5px">${loop.loop_id}</span></span>
          <span class="chip chip-${loop.anomaly_type}">${zhAnomaly(loop.anomaly_type)}</span>
        </div>
        <div class="loop-desc">${loop.description}</div>
      `;
      row.onclick = () => {
        selectLoop(loop);
        document.getElementById('strategySelect').value = '';
        runWorkflow(loop.loop_id);
      };
      list.appendChild(row);
    });
  });
}

function selectLoop(loop) {
  selectedLoop = loop;
  document.getElementById('selectedTitle').textContent = `${loop.loop_id} · ${loop.tag_name} — ${loop.description} (${loop.unit_name})`;
  renderLoopList();
}

function renderUnitSVG(unitName) {
  // ISA-101 High-Performance HMI: Muted industrial slate-gray equipment; color reserved strictly for abnormal/alarm states!
  if (unitName.includes('精馏') || unitName.includes('CDU')) {
    return `
      <rect x="24" y="10" width="38" height="72" rx="14" fill="#dde4ed" stroke="#334155" stroke-width="1.8"/>
      <line x1="26" y1="28" x2="60" y2="28" stroke="#64748b" stroke-dasharray="3,2"/>
      <line x1="26" y1="44" x2="60" y2="44" stroke="#64748b" stroke-dasharray="3,2"/>
      <line x1="26" y1="60" x2="60" y2="60" stroke="#64748b" stroke-dasharray="3,2"/>
      <text x="43" y="94" text-anchor="middle" font-size="9" font-weight="700" fill="#1e293b">常减压精馏塔</text>`;
  }
  if (unitName.includes('催化') || unitName.includes('FCC')) {
    return `
      <rect x="16" y="16" width="24" height="62" rx="5" fill="#dde4ed" stroke="#334155" stroke-width="1.6"/>
      <rect x="48" y="12" width="30" height="66" rx="6" fill="#cbd5e1" stroke="#334155" stroke-width="1.6"/>
      <line x1="40" y1="44" x2="48" y2="44" stroke="#334155" stroke-width="2"/>
      <text x="47" y="94" text-anchor="middle" font-size="9" font-weight="700" fill="#1e293b">FCC 反应-再生</text>`;
  }
  if (unitName.includes('裂解') || unitName.includes('Cracker')) {
    return `
      <polygon points="18,78 18,30 46,12 74,30 74,78" fill="#dde4ed" stroke="#334155" stroke-width="1.7"/>
      <path d="M28,68 L28,38 L46,26 L64,38 L64,68" fill="none" stroke="#475569" stroke-width="2"/>
      <text x="46" y="94" text-anchor="middle" font-size="9" font-weight="700" fill="#1e293b">乙烯裂解炉</text>`;
  }
  if (unitName.includes('反应釜') || unitName.includes('CSTR')) {
    return `
      <rect x="20" y="18" width="48" height="60" rx="8" fill="#dde4ed" stroke="#334155" stroke-width="1.7"/>
      <line x1="44" y1="10" x2="44" y2="62" stroke="#1e293b" stroke-width="1.8"/>
      <line x1="30" y1="62" x2="58" y2="62" stroke="#1e293b" stroke-width="2.2"/>
      <text x="44" y="94" text-anchor="middle" font-size="9" font-weight="700" fill="#1e293b">连续搅拌釜 CSTR</text>`;
  }
  return `
    <rect x="22" y="12" width="42" height="68" rx="10" fill="#dde4ed" stroke="#334155" stroke-width="1.7"/>
    <rect x="27" y="26" width="32" height="14" fill="#cbd5e1" stroke="#64748b" stroke-width="0.8"/>
    <rect x="27" y="48" width="32" height="14" fill="#cbd5e1" stroke="#64748b" stroke-width="0.8"/>
    <text x="43" y="94" text-anchor="middle" font-size="9" font-weight="700" fill="#1e293b">加氢精制床层</text>`;
}

function renderPIDSchematic(data) {
  const meta = data.loop_meta;
  const d = data.diagnosis;
  const isStic = d.anomaly_type === 'VALVE_STICTION';
  const valveColor = isStic ? '#b91c1c' : '#334155';
  const pipeColor = isStic ? '#b91c1c' : '#475569';
  const opPct = Math.max(0, Math.min(100, Number(meta.op_bias) || 50));
  const opW = Math.round((opPct / 100) * 56);
  document.getElementById('pidSchematic').innerHTML = `
    <svg viewBox="0 0 430 102" width="100%" height="102">
      ${renderUnitSVG(meta.unit_name)}
      <!-- Process line -->
      <line x1="80" y1="48" x2="245" y2="48" stroke="#cbd5e1" stroke-width="5"/>
      <line x1="80" y1="48" x2="245" y2="48" stroke="${pipeColor}" stroke-width="1.8" class="flow-pipe"/>
      <!-- ISA-5.1 Standard DCS Controller Symbol (Circle inside Square = Shared Display/DCS) -->
      <line x1="166" y1="48" x2="166" y2="38" stroke="#475569" stroke-width="1.4"/>
      <rect x="145" y="4" width="42" height="36" rx="2" fill="#ffffff" stroke="#1e293b" stroke-width="1.5"/>
      <circle cx="166" cy="22" r="16" fill="#f8fafc" stroke="#1e40af" stroke-width="1.6"/>
      <line x1="150" y1="22" x2="182" y2="22" stroke="#94a3b8" stroke-width="0.9"/>
      <text x="166" y="19" text-anchor="middle" font-size="7.8" font-weight="800" font-family="Consolas,monospace" fill="#0f172a">${meta.tag_name}</text>
      <text x="166" y="31" text-anchor="middle" font-size="6.8" font-weight="700" fill="#1e40af">DCS</text>
      <!-- Electronic signal line to control valve -->
      <path d="M187,22 L268,22 L268,34" fill="none" stroke="#334155" stroke-width="1.3" stroke-dasharray="3,2"/>
      <!-- Pneumatic Diaphragm Globe Valve (ISA-5.1) -->
      <path d="M256,28 A12,10 0 0,1 280,28 Z" fill="#cbd5e1" stroke="#334155" stroke-width="1.3"/>
      <line x1="268" y1="28" x2="268" y2="48" stroke="#334155" stroke-width="1.6"/>
      <polygon points="246,38 268,48 246,58" fill="${valveColor}"/>
      <polygon points="290,38 268,48 290,58" fill="${valveColor}"/>
      <line x1="290" y1="48" x2="328" y2="48" stroke="#cbd5e1" stroke-width="5"/>
      <line x1="290" y1="48" x2="328" y2="48" stroke="${valveColor}" stroke-width="1.8" class="flow-pipe"/>
      <text x="268" y="75" text-anchor="middle" font-size="9" font-weight="800" fill="${isStic ? '#b91c1c' : '#334155'}">${isStic ? '■ 阀杆粘滞告警' : '● 调节阀正常'}</text>
      <!-- Right DCS Mini Faceplate (SP / OP Bar Gauge) -->
      <rect x="334" y="6" width="90" height="84" rx="2" fill="#ffffff" stroke="#64748b" stroke-width="1.2"/>
      <rect x="334" y="6" width="90" height="17" fill="#1e293b"/>
      <text x="340" y="18" font-size="8.2" font-weight="700" font-family="Consolas,monospace" fill="#f8fafc">${meta.tag_name} · AUTO</text>
      <text x="340" y="36" font-size="8" fill="#64748b" font-family="Consolas,monospace">SP</text>
      <text x="418" y="36" text-anchor="end" font-size="9.5" font-weight="800" font-family="Consolas,monospace" fill="#1e40af">${meta.pv_bias}${meta.pv_unit}</text>
      <text x="340" y="53" font-size="8" fill="#64748b" font-family="Consolas,monospace">OP</text>
      <text x="418" y="53" text-anchor="end" font-size="9.5" font-weight="800" font-family="Consolas,monospace" fill="#0f172a">${opPct.toFixed(1)}%</text>
      <rect x="340" y="59" width="78" height="8" fill="#e2e8f0" stroke="#94a3b8" stroke-width="0.7"/>
      <rect x="340" y="59" width="${Math.round((opPct / 100) * 78)}" height="8" fill="${isStic ? '#b91c1c' : '#334155'}"/>
      <text x="379" y="81" text-anchor="middle" font-size="7.5" font-weight="700" font-family="Consolas,monospace" fill="#475569">SIM · NO WRITE</text>
    </svg>
  `;
}

async function runWorkflow(loopId, opts = {}) {
  const seq = ++latestRequestSeq;
  const btn = document.getElementById('runBtn');
  btn.disabled = true; btn.textContent = '诊断与安全校验中...';
  try {
    const res = await fetch(`/api/run/${loopId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(opts),
    });
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try { const errObj = await res.json(); if (errObj.detail) detail += ` · ${errObj.detail}`; } catch (_) {}
      throw new Error(detail);
    }
    const data = await res.json();
    // Stale-response guard: discard out-of-order response if user already switched loops!
    if (seq !== latestRequestSeq) return;
    replayProgress = 1.0;
    renderResult(data);
  } catch (err) {
    if (seq !== latestRequestSeq) return;
    // Fail-Closed P1-B: clear stale currentData and disable export buttons immediately
    currentData = null;
    const apBtn = document.getElementById('approvalBtn');
    const bdBtn = document.getElementById('bundleBtn');
    if (apBtn) apBtn.disabled = true;
    if (bdBtn) bdBtn.disabled = true;
    const rm = document.getElementById('rRunMeta');
    if (rm) rm.textContent = '当前工单: -- (请求失败，已清除旧状态)';
    const banner = document.getElementById('riskBanner');
    if (banner) {
      banner.style.display = 'block';
      banner.className = 'risk-banner danger';
      banner.textContent = `■ 请求失败（${err.message || '网络异常'}）｜Fail-Closed 保护已生效，已清除旧工单并禁用导出`;
    }
    const sb = document.getElementById('statusBadge');
    if (sb) {
      sb.textContent = '请求异常 · 未验证';
      sb.className = 'chip chip-AGGRESSIVE_TUNING';
    }
    const strip = document.getElementById('auditStrip');
    if (strip) {
      strip.innerHTML = `<span><b>审计:</b> UNVERIFIED · 请求未完成</span><span><b>deployment_authorized=false</b> · 隔离仿真专用</span>`;
    }
  } finally {
    if (seq === latestRequestSeq) {
      btn.disabled = false; btn.textContent = '执行诊断整定';
    }
  }
}

function renderResult(data) {
  currentData = data;
  const modeLabel = data.llm_mode === 'live_llm_api' ? '推理引擎: 在线模型' : '推理引擎: 离线规则';
  document.getElementById('topMode').textContent = modeLabel;
  const am0 = data.audit_meta || {};
  // Fail-Closed P1-A: cross-check audit_status, run_id, and complete constraint_audit
  const auditStatus = (am0.audit_verification && am0.audit_verification.audit_status) || 'UNVERIFIED';
  const hasValidRunId = Boolean(am0.run_id);
  const auditList = (data.safety && Array.isArray(data.safety.constraint_audit)) ? data.safety.constraint_audit : [];
  const allConstraintsPass = auditList.length >= 11 && auditList.every(c => c && c.passed === true);

  const apBtn = document.getElementById('approvalBtn');
  const bdBtn = document.getElementById('bundleBtn');
  if (apBtn) apBtn.disabled = !hasValidRunId;
  if (bdBtn) bdBtn.disabled = !hasValidRunId;

  const strip = document.getElementById('auditStrip');
  if (strip) {
    const rawDig = am0.record_digest_sha256 || am0.output_sha256 || '';
    const dig = rawDig ? `${escHtml(rawDig.slice(0, 12))}…` : '--';
    strip.innerHTML = `<span><b>工单:</b> ${escHtml(am0.run_id || '--')} &nbsp;|&nbsp; <b>状态码:</b> ${escHtml(data.final_status || 'UNKNOWN')} &nbsp;|&nbsp; <b>摘要:</b> ${dig} &nbsp;|&nbsp; <b>审计:</b> ${escHtml(auditStatus)}</span><span><b>deployment_authorized=false</b> · 隔离仿真专用</span>`;
  }
  if (hasValidRunId) {
    document.getElementById('rRunMeta').textContent = `当前工单: ${am0.run_id} | 哈希:${(am0.output_sha256 || '').slice(0, 8)}`;
  } else {
    document.getElementById('rRunMeta').textContent = '当前工单: -- (缺失工单号)';
  }
  renderPIDSchematic(data);

  const ip = data.initial_pid, fp = data.final_pid;
  const d0 = data.diagnosis, d1 = data.after_diagnosis || d0;
  const rawApprovedEnum = data.final_status === 'SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW';
  const isApprovedCand = rawApprovedEnum && (auditStatus === 'PASS') && hasValidRunId && allConstraintsPass;
  const pctBadge = (a, b) => {
    if (!isApprovedCand || a < 0.05) return '<span class="fp-delta hold">保持</span>';
    const pct = Math.round(((b - a) / a) * 100);
    return `<span class="fp-delta good">${pct}%</span>`;
  };
  document.getElementById('mPid').innerHTML = isApprovedCand
    ? `<span style="color:#64748b">(${ip.Kc},${ip.Ti})</span> → <span style="color:#046c4e">(${fp.Kc},${fp.Ti})</span>`
    : `<span style="color:#0f172a">(${ip.Kc}, ${ip.Ti})</span> <span class="fp-delta hold">不变</span>`;
  document.getElementById('mOi').innerHTML = `${d0.oscillation_index.toFixed(2)} → ${d1.oscillation_index.toFixed(2)}${pctBadge(d0.oscillation_index, d1.oscillation_index)}`;
  document.getElementById('mIae').innerHTML = `${d0.iae.toFixed(2)} → ${d1.iae.toFixed(2)}${pctBadge(d0.iae, d1.iae)}`;
  document.getElementById('mOp').innerHTML = `${d0.op_travel.toFixed(2)} → ${d1.op_travel.toFixed(2)}${pctBadge(d0.op_travel, d1.op_travel)}`;
  document.getElementById('mIdAcc').innerHTML = data.identification
    ? `<span style="color:${data.identification.allow_next_stage ? '#046c4e' : '#b91c1c'}">${data.identification.val_fit_pct}% / R²=${data.identification.val_r2}</span>`
    : '<span style="color:#5b6b7f">健康跳过</span>';
  if (data.safety && typeof data.safety.gain_margin === 'number') {
    const s = data.safety;
    const gmW = Math.min(100, Math.round((s.gain_margin / 4.0) * 100));
    const pmW = Math.min(100, Math.round((s.phase_margin_deg / 80.0) * 100));
    const msW = Math.min(100, Math.round((s.max_sensitivity_ms / 3.0) * 100));
    document.getElementById('mMargin').innerHTML = `<div class="mg-bars">
      <div class="mg-row"><span>GM ${s.gain_margin}</span><div class="mg-track"><div class="mg-fill ${s.gain_margin < 1.8 ? 'bad' : ''}" style="width:${gmW}%"></div></div></div>
      <div class="mg-row"><span>PM ${s.phase_margin_deg}°</span><div class="mg-track"><div class="mg-fill ${s.phase_margin_deg < 35 ? 'bad' : ''}" style="width:${pmW}%"></div></div></div>
      <div class="mg-row"><span>Ms ${s.max_sensitivity_ms}</span><div class="mg-track"><div class="mg-fill ${s.max_sensitivity_ms > 2.2 ? 'bad' : ''}" style="width:${msW}%"></div></div></div>
    </div>`;
  } else {
    document.getElementById('mMargin').textContent = '安全保持';
  }

  const sb = document.getElementById('statusBadge');
  const isHealthyStatus = ['HEALTHY_NO_CHANGE', 'NO_CHANGE_HEALTHY'].includes(data.final_status) && auditStatus === 'PASS' && hasValidRunId;
  const isOkKnown = isApprovedCand || isHealthyStatus;
  const isWarn = ['VALVE_MAINTENANCE_REQUIRED', 'PERFORMANCE_NOT_IMPROVED'].includes(data.final_status);
  // Fail-Closed: any unknown, rejected, or unverified-audit status renders danger style (never green!)
  const isRejected = !isOkKnown && !isWarn;
  sb.textContent = (rawApprovedEnum && !isApprovedCand) ? '审计未验 · 拒绝展示' : zhStatus(data.final_status);
  sb.title = `${data.final_status || 'UNKNOWN'} (audit=${auditStatus})`;
  sb.className = 'chip ' + (isRejected ? 'chip-AGGRESSIVE_TUNING' : (isWarn ? 'chip-VALVE_STICTION' : 'chip-NORMAL'));
  document.getElementById('elapsedTag').textContent = `闭环耗时 ${data.elapsed_s}s`;

  const setSt = (id, cls) => { document.getElementById(id).className = 'st-step ' + cls; };
  setSt('st1', 'done');
  setSt('st2', 'done');
  setSt('st3', data.identification ? (data.identification.allow_next_stage ? 'done' : 'fail') : 'done');
  setSt('st4', data.tuning ? 'done' : (isRejected ? 'fail' : 'warn'));
  setSt('st5', isRejected ? 'fail' : (isWarn ? 'warn' : 'done'));

  const banner = document.getElementById('riskBanner');
  banner.style.display = 'block';
  banner.className = 'risk-banner ' + (isRejected ? 'danger' : (isWarn ? '' : 'ok'));
  if (isApprovedCand) {
    const strat = (data.tuning && data.tuning.strategy) ? data.tuning.strategy : 'balanced';
    const passCnt = auditList.filter(c => c && c.passed === true).length;
    const totalCnt = auditList.length;
    banner.textContent = `● 仿真校验通过 · 待人工复核（${passCnt}/${totalCnt} 约束通过 · 策略: ${strat}）｜仅限离线仿真验证，严禁未审批写入真实 DCS`;
  } else if (rawApprovedEnum && !isApprovedCand) {
    banner.textContent = `■ 审批证据不完整（审计=${auditStatus}，工单=${hasValidRunId ? '有效' : '缺失'}，约束=${auditList.length}项）｜Fail-Closed 拦截，禁止作为仿真通过展示`;
  } else if (isHealthyStatus) {
    banner.textContent = '● 回路运行平稳健康 · 无需整定变更｜保持当前 DCS 参数';
  } else if (data.final_status === 'VALVE_MAINTENANCE_REQUIRED') {
    banner.textContent = '▲ 调节阀机械粘滞 · 建议仪表检修｜PID 整定无法根除阀杆摩擦，保持原 DCS 参数';
  } else if (data.final_status === 'PERFORMANCE_NOT_IMPROVED') {
    banner.textContent = '▲ 外部周期扰动 · 整定未改善｜保持原 DCS 参数，建议排查上游工艺扰动源';
  } else {
    banner.textContent = `■ 拒绝参数变更 · 保持原 DCS 参数｜${(data.decision_reason || '模型验证、审计或安全约束未通过').split('。')[0]}`;
  }

  // Compact bottom telemetry strip (no bulky progress bar)
  const ab = data.anti_bloat_metrics;
  document.getElementById('abComp').textContent = `黑板压缩 ${ab.compression_ratio_pct}%`;
  document.getElementById('abBytes').textContent = `${ab.raw_timeseries_bytes}B→${ab.compact_handoff_bytes}B`;
  document.getElementById('abCalls').textContent = `工具 ${ab.total_tool_calls}次`;

  const AGENT_ZH = {
    DiagnosisAgent: '异常诊断',
    IdentificationAgent: '过程模型辨识',
    TuningAgent: 'PID 整定优化',
    SafetyAgent: '安全与鲁棒校验',
    SafetyVerificationAgent: '安全与鲁棒校验',
    FinalDecisionEngine: '独立审批决策',
    DecisionAgent: '独立审批决策',
  };
  const TRACE_ST_ZH = {
    DONE: '完成', APPROVED: '通过', CONSTRAINTS_PASS: '通过',
    WARNING: '警示', REJECTED: '拦截', FAILED: '失败',
  };

  // Connected Vertical Timeline with Collapsible Technical Details
  const traceEl = document.getElementById('traceList');
  traceEl.innerHTML = '';
  data.trace.forEach((t, idx) => {
    const item = document.createElement('div');
    item.className = 'trace-item';
    const preId = `mcp-json-${idx}`;
    const lt = t.llm_telemetry;
    const techMeta = {
      agent: t.agent,
      skill: t.skill,
      latency_ms: t.latency_ms,
      ...(lt ? { llm: { mode: lt.mode, model: lt.model, latency_ms: lt.latency_ms, tokens: lt.total_tokens } } : {}),
      metrics: t.metrics || {},
    };
    const agentLabel = AGENT_ZH[t.agent] || t.agent;
    const stLabel = TRACE_ST_ZH[t.status] || t.status;
    item.innerHTML = `
      <div class="trace-node ${escHtml(t.status)}"></div>
      <div class="trace-card ${escHtml(t.status)}">
        <div class="trace-top"><span title="${escHtml(t.agent)}">#${escHtml(t.step)} ${escHtml(agentLabel)}</span><span class="chip">${escHtml(stLabel)}</span></div>
        <div class="trace-meta">${escHtml(t.stage || '-')} · ${escHtml(t.latency_ms ?? '-')}ms</div>
        <div class="trace-txt">${escHtml(t.summary)}</div>
        <button class="trace-json-btn" onclick="const el=document.getElementById('${preId}');el.style.display=el.style.display==='block'?'none':'block'">▸ 展开技术详情</button>
        <pre class="trace-json-pre" id="${preId}">${escHtml(JSON.stringify(techMeta, null, 2))}</pre>
      </div>`;
    traceEl.appendChild(item);
  });

  // 11-Item Safety Audit
  const auditBody = document.getElementById('auditBody');
  auditBody.innerHTML = '';
  if (data.safety && Array.isArray(data.safety.constraint_audit) && data.safety.constraint_audit.length > 0) {
    data.safety.constraint_audit.forEach(c => {
      auditBody.innerHTML += `<tr><td><b>${escHtml(c.constraint_id)}</b></td><td>${escHtml(c.category)}</td><td>${escHtml(c.rule_name)}</td><td>${escHtml(c.measured_value)}</td><td>${escHtml(c.threshold)}</td><td class="${c.passed ? 'st-pass':'st-fail'}">${c.passed ? 'PASS':'FAIL'}</td></tr>`;
    });
  } else {
    auditBody.innerHTML = '<tr><td colspan="6" style="color:var(--muted)">无完整安全约束记录（健康回路或审计未通过），保持原 DCS 参数</td></tr>';
  }

  // 5-Regime Table
  const regimeBody = document.getElementById('regimeBody');
  regimeBody.innerHTML = '';
  if (data.safety && Array.isArray(data.safety.operating_point_checks) && data.safety.operating_point_checks.length > 0) {
    data.safety.operating_point_checks.forEach(r => {
      regimeBody.innerHTML += `<tr><td><b>${escHtml(r.regime_name)}</b></td><td>${escHtml(r.plant_K)} / ${escHtml(r.plant_tau)} / ${escHtml(r.plant_theta)}</td><td>${escHtml(r.overshoot_pct)}% / ≤${escHtml(r.overshoot_limit_pct)}%</td><td>${escHtml(r.oscillation_index)} / ≤${escHtml(r.oi_limit)}</td><td>${escHtml(r.iae)}</td><td class="${r.passed ? 'st-pass':'st-fail'}">${r.passed ? 'PASS':'FAIL'}</td></tr>`;
    });
  } else {
    regimeBody.innerHTML = '<tr><td colspan="6" style="color:var(--muted)">无跨工况鲁棒验证记录，保持原 DCS 参数</td></tr>';
  }

  // Fair Baseline Comparison Table
  const baseBody = document.getElementById('baselineBody');
  baseBody.innerHTML = '';
  if (data.baseline_comparison) {
    const bc = data.baseline_comparison;
    [
      ['原始 PID 参数 (Original)', bc.original_pid],
      ['传统解析 SIMC 基线', bc.traditional_simc],
      [`本系统优化+安全门控 (${bc.optimized_candidate.strategy})`, bc.optimized_candidate],
    ].forEach(([name, m]) => {
      baseBody.innerHTML += `<tr><td><b>${name}</b></td><td>${m.Kc}</td><td>${m.Ti}</td><td><b>${m.iae}</b></td><td>${m.oi}</td><td>${m.harris}</td><td>${m.overshoot_pct}%</td><td>${m.op_travel}</td></tr>`;
    });
  } else {
    baseBody.innerHTML = '<tr><td colspan="8" style="color:var(--muted)">当前回路未进入参数整定阶段（健康 / 模型验证未通过 / 阀门粘滞拦截）。</td></tr>';
  }

  renderActiveChart();
}

function setupCanvas(id) {
  const canvas = document.getElementById(id);
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = Math.max(300, rect.width) * dpr;
  canvas.height = Math.max(220, rect.height) * dpr;
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  return { ctx, W: Math.max(300, rect.width), H: Math.max(220, rect.height) };
}

function renderActiveChart() {
  if (!currentData) return;
  const legend = document.getElementById('chartLegend');
  if (activeChart === 'time') {
    drawTimeChart('mainCanvas', currentData.waveforms, hoverIdx, replayProgress);
    legend.innerHTML = `
      <span><i style="background:#1d4ed8"></i>设定值 SP (虚线)</span>
      <span><i style="background:#b91c1c"></i>整定前 PV / OP</span>
      <span><i style="background:#047857"></i>整定后 PV / OP（下方为调节阀开度 OP 0–100%）</span>`;
  } else if (activeChart === 'ident') {
    drawIdentChart('mainCanvas', currentData.identification_plot, currentData.identification, hoverIdx);
    legend.innerHTML = `
      <span><i style="background:#0f172a"></i>实测过程变量 PV</span>
      <span><i style="background:#1d4ed8"></i>FOPDT 预测 PV̂</span>
      <span><i style="background:#b45309"></i>65% 训练 / 35% 独立验证分界线</span>`;
  } else if (activeChart === 'phase') {
    drawPhaseChart('mainCanvas', currentData.phase_portrait, currentData.diagnosis);
    legend.innerHTML = `<span><i style="background:#6d28d9"></i>恒定 SP 区间 PV–OP 相轨迹（粘滞呈现滞回环与滑跳冲击特征）</span>`;
  } else if (activeChart === 'nyquist') {
    drawNyquistChart('mainCanvas', currentData.nyquist_plot);
    legend.innerHTML = `
      <span><i style="background:#b91c1c"></i>整定前 L(jω)</span>
      <span><i style="background:#047857"></i>整定后 L(jω)</span>
      <span><i style="background:#b45309"></i>Ms=${currentData.nyquist_plot.max_ms} 禁止侵入安全圆（中心 -1, 0）</span>`;
  }
}

function drawTimeChart(canvasId, w, cursorIdx = null, progress = 1.0) {
  const { ctx, W, H } = setupCanvas(canvasId);
  ctx.clearRect(0, 0, W, H);
  const padL = 54, padR = 18;
  const maxIdx = Math.max(2, Math.floor((w.t.length - 1) * progress));
  const mapX = i => padL + (i / (w.t.length - 1)) * (W - padL - padR);

  const drawSub = (yTop, yBot, seriesList, labelY, clampRange = null, fillAfter = false) => {
    const allY = seriesList.flatMap(s => s.arr);
    let lo = Math.min(...allY), hi = Math.max(...allY);
    const m = Math.max(0.5, (hi - lo) * 0.12); lo -= m; hi += m;
    if (clampRange) {
      lo = Math.max(clampRange[0], lo); hi = Math.min(clampRange[1], hi);
      if (hi - lo < 6) { lo = Math.max(0, lo - 5); hi = Math.min(100, hi + 5); }
    }
    const mapY = v => yBot - ((v - lo) / (hi - lo)) * (yBot - yTop);

    ctx.strokeStyle = '#edf2f7'; ctx.lineWidth = 1;
    ctx.fillStyle = '#64748b'; ctx.font = '10.5px Consolas, monospace';
    for (let k = 0; k <= 3; k++) {
      const v = lo + (k / 3) * (hi - lo);
      const y = mapY(v);
      ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(W - padR, y); ctx.stroke();
      ctx.fillText(v.toFixed(1), 6, y + 3);
    }
    ctx.fillStyle = '#334155'; ctx.font = 'bold 11px sans-serif';
    ctx.fillText(labelY, padL + 6, yTop + 12);

    // ±2% ΔSP settling reference band (derived strictly from SP step span, not chart viewport)
    if (fillAfter && seriesList[2]) {
      const spArr = seriesList[2].arr;
      const spStep = Math.max(...spArr) - Math.min(...spArr);
      const band = spStep > 1e-6 ? 0.02 * spStep : 0.02 * Math.max(1, Math.abs(spArr[0]));
      ctx.fillStyle = 'rgba(29, 78, 216, 0.07)';
      ctx.beginPath();
      for (let i = 0; i <= maxIdx; i++) {
        const x = mapX(i), y = mapY(spArr[i] + band);
        i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      }
      for (let i = maxIdx; i >= 0; i--) {
        ctx.lineTo(mapX(i), mapY(spArr[i] - band));
      }
      ctx.closePath(); ctx.fill();
    }

    // Soft area fill under tuned curve
    if (fillAfter && seriesList[1]) {
      const arr = seriesList[1].arr;
      const grad = ctx.createLinearGradient(0, yTop, 0, yBot);
      grad.addColorStop(0, 'rgba(4, 120, 87, 0.12)');
      grad.addColorStop(1, 'rgba(4, 120, 87, 0.00)');
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.moveTo(mapX(0), yBot);
      for (let i = 0; i <= maxIdx; i++) ctx.lineTo(mapX(i), mapY(arr[i]));
      ctx.lineTo(mapX(maxIdx), yBot);
      ctx.closePath(); ctx.fill();
    }

    seriesList.forEach(s => {
      ctx.save(); ctx.strokeStyle = s.color; ctx.lineWidth = s.width;
      if (s.dash) ctx.setLineDash([5, 3]);
      ctx.beginPath();
      for (let i = 0; i <= maxIdx; i++) {
        const x = mapX(i), y = mapY(s.arr[i]);
        i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      }
      ctx.stroke(); ctx.restore();

      // Precision dot markers at hover crosshair
      if (cursorIdx !== null && cursorIdx <= maxIdx) {
        const cx = mapX(cursorIdx), cy = mapY(s.arr[cursorIdx]);
        ctx.fillStyle = '#ffffff'; ctx.strokeStyle = s.color; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.arc(cx, cy, 3.8, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
      }
    });
  };

  drawSub(12, H * 0.58, [
    { arr: w.pv_before, color: 'rgba(185,28,28,0.82)', width: 1.6 },
    { arr: w.pv_after, color: '#047857', width: 2.3 },
    { arr: w.sp, color: '#1d4ed8', width: 1.5, dash: true },
  ], '被控变量 PV / 设定值 SP', null, true);

  drawSub(H * 0.65, H - 24, [
    { arr: w.op_before, color: 'rgba(185,28,28,0.65)', width: 1.4 },
    { arr: w.op_after, color: '#047857', width: 1.8 },
  ], '调节阀输出 OP (%)', [0, 100], false);

  ctx.fillStyle = '#64748b'; ctx.font = '10.5px Consolas, monospace';
  for (let k = 0; k <= 4; k++) {
    const idx = Math.round((k / 4) * (w.t.length - 1));
    ctx.fillText(`${w.t[idx]}s`, Math.min(mapX(idx) - 10, W - 36), H - 6);
  }

  if (cursorIdx !== null && cursorIdx <= maxIdx) {
    const cx = mapX(cursorIdx);
    ctx.save(); ctx.strokeStyle = '#94a3b8'; ctx.setLineDash([3, 3]); ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(cx, 10); ctx.lineTo(cx, H - 22); ctx.stroke(); ctx.restore();
  }
}

function drawIdentChart(canvasId, ip, metaId, cursorIdx = null) {
  const { ctx, W, H } = setupCanvas(canvasId);
  ctx.clearRect(0, 0, W, H);
  if (!ip) {
    ctx.fillStyle = '#64748b'; ctx.font = '13px sans-serif';
    ctx.fillText('健康回路跳过在线过程辨识。请选择异常回路查看 65% 训练 / 35% 独立验证拟合曲线。', 30, H / 2);
    return;
  }
  const padL = 54, padR = 18, padT = 20, padB = 28;
  const allY = [...ip.pv_actual, ...ip.pv_predicted];
  let lo = Math.min(...allY), hi = Math.max(...allY);
  const m = Math.max(0.5, (hi - lo) * 0.12); lo -= m; hi += m;
  const mapX = i => padL + (i / (ip.t.length - 1)) * (W - padL - padR);
  const mapY = v => H - padB - ((v - lo) / (hi - lo)) * (H - padT - padB);

  ctx.strokeStyle = '#edf2f7'; ctx.lineWidth = 1;
  ctx.fillStyle = '#64748b'; ctx.font = '10.5px Consolas, monospace';
  for (let k = 0; k <= 4; k++) {
    const v = lo + (k / 4) * (hi - lo);
    const y = mapY(v);
    ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(W - padR, y); ctx.stroke();
    ctx.fillText(v.toFixed(1), 6, y + 3);
  }

  const splitIdx = Math.floor(ip.t.length * 0.65);
  const sx = mapX(splitIdx);
  ctx.fillStyle = metaId.allow_next_stage ? 'rgba(29, 78, 216, 0.06)' : 'rgba(185, 28, 28, 0.08)';
  ctx.fillRect(sx, padT, W - padR - sx, H - padT - padB);
  ctx.strokeStyle = '#b45309'; ctx.setLineDash([5, 4]); ctx.lineWidth = 1.4;
  ctx.beginPath(); ctx.moveTo(sx, padT); ctx.lineTo(sx, H - padB); ctx.stroke();
  ctx.setLineDash([]);
  ctx.fillStyle = metaId.allow_next_stage ? '#b45309' : '#b91c1c';
  ctx.font = 'bold 11px sans-serif';
  ctx.textAlign = 'right';
  ctx.fillText(`验证段(35%) · Fit ${metaId.val_fit_pct}% | R²=${metaId.val_r2}`, W - padR - 6, padT + 14);
  ctx.textAlign = 'left';

  const plot = (arr, color, w) => {
    ctx.strokeStyle = color; ctx.lineWidth = w; ctx.beginPath();
    arr.forEach((v, i) => { const x = mapX(i), y = mapY(v); i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y); });
    ctx.stroke();
    if (cursorIdx !== null && cursorIdx < arr.length) {
      ctx.fillStyle = '#fff'; ctx.strokeStyle = color; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.arc(mapX(cursorIdx), mapY(arr[cursorIdx]), 3.8, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    }
  };
  plot(ip.pv_actual, '#0f172a', 1.6);
  plot(ip.pv_predicted, '#1d4ed8', 2.1);

  if (cursorIdx !== null && cursorIdx < ip.t.length) {
    const cx = mapX(cursorIdx);
    ctx.save(); ctx.strokeStyle = '#94a3b8'; ctx.setLineDash([3, 3]); ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(cx, padT); ctx.lineTo(cx, H - padB); ctx.stroke(); ctx.restore();
  }
}

function drawPhaseChart(canvasId, ph, diag) {
  const { ctx, W, H } = setupCanvas(canvasId);
  ctx.clearRect(0, 0, W, H);
  const padL = 52, padR = 24, padT = 32, padB = 34;
  const xs = ph.op, ys = ph.pv;
  let x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  if (x1 - x0 < 0.2) { x0 -= 1; x1 += 1; }
  if (y1 - y0 < 0.2) { y0 -= 1; y1 += 1; }
  const mapX = v => padL + ((v - x0) / (x1 - x0)) * (W - padL - padR);
  const mapY = v => H - padB - ((v - y0) / (y1 - y0)) * (H - padT - padB);

  // Coordinate grid + tick labels
  ctx.strokeStyle = '#edf2f7'; ctx.lineWidth = 1;
  ctx.fillStyle = '#64748b'; ctx.font = '10px Consolas, monospace';
  for (let k = 0; k <= 4; k++) {
    const xv = x0 + (k / 4) * (x1 - x0);
    const yv = y0 + (k / 4) * (y1 - y0);
    const gx = mapX(xv), gy = mapY(yv);
    ctx.beginPath(); ctx.moveTo(gx, padT); ctx.lineTo(gx, H - padB); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(padL, gy); ctx.lineTo(W - padR, gy); ctx.stroke();
    ctx.fillText(xv.toFixed(1), gx - 10, H - padB + 14);
    ctx.fillText(yv.toFixed(1), 6, gy + 3);
  }
  ctx.strokeStyle = '#cbd5e1'; ctx.strokeRect(padL, padT, W - padL - padR, H - padT - padB);

  // Header engineering readout
  ctx.fillStyle = '#0f172a'; ctx.font = 'bold 11px Consolas, monospace';
  ctx.fillText(`PV-OP 阀门迟滞相图 | 粘滞指数 SI = ${diag.stiction_index.toFixed(2)} (${diag.anomaly_type === 'VALVE_STICTION' ? '存在明显滞环' : '无典型矩形粘滞'})`, padL, 19);
  ctx.fillStyle = '#475569'; ctx.font = '10.5px sans-serif';
  ctx.fillText('调节阀开度 OP (%) →', W / 2 - 48, H - 6);

  // Time-progressed trajectory (early slate -> late purple/blue) + directional arrowheads
  const isStic = diag.anomaly_type === 'VALVE_STICTION';
  const n = xs.length;
  for (let i = 1; i < n; i++) {
    const t = i / Math.max(1, n - 1);
    const r = Math.round(148 + ((isStic ? 109 : 29) - 148) * t);
    const g = Math.round(163 + ((isStic ? 40 : 78) - 163) * t);
    const b = Math.round(184 + ((isStic ? 217 : 216) - 184) * t);
    ctx.strokeStyle = `rgb(${r},${g},${b})`;
    ctx.lineWidth = 1.4 + t * 0.9;
    ctx.beginPath();
    ctx.moveTo(mapX(xs[i - 1]), mapY(ys[i - 1]));
    ctx.lineTo(mapX(xs[i]), mapY(ys[i]));
    ctx.stroke();

    // Directional arrowheads along trajectory
    if (i > 10 && i % Math.max(12, Math.floor(n / 10)) === 0) {
      const xA = mapX(xs[i - 1]), yA = mapY(ys[i - 1]);
      const xB = mapX(xs[i]), yB = mapY(ys[i]);
      const ang = Math.atan2(yB - yA, xB - xA);
      if (Math.hypot(xB - xA, yB - yA) > 1.2) {
        ctx.fillStyle = `rgb(${r},${g},${b})`;
        ctx.beginPath();
        ctx.moveTo(xB, yB);
        ctx.lineTo(xB - 7 * Math.cos(ang - 0.45), yB - 7 * Math.sin(ang - 0.45));
        ctx.lineTo(xB - 7 * Math.cos(ang + 0.45), yB - 7 * Math.sin(ang + 0.45));
        ctx.closePath(); ctx.fill();
      }
    }
  }
}

function drawNyquistChart(canvasId, nq) {
  const { ctx, W, H } = setupCanvas(canvasId);
  ctx.clearRect(0, 0, W, H);
  const pad = 38;
  const reMin = -2.2, reMax = 0.8, imMin = -1.8, imMax = 0.8;
  const scale = Math.min((W - 2 * pad) / (reMax - reMin), (H - 2 * pad) / (imMax - imMin));
  const cx = pad + (W - 2 * pad - (reMax - reMin) * scale) / 2;
  const mapX = re => cx + (re - reMin) * scale;
  const mapY = im => H - pad - (im - imMin) * scale;

  // Light coordinate grid + numeric ticks
  ctx.strokeStyle = '#edf2f7'; ctx.lineWidth = 1;
  ctx.fillStyle = '#64748b'; ctx.font = '10px Consolas, monospace';
  [-2, -1.5, -1, -0.5, 0, 0.5].forEach(re => {
    const x = mapX(re);
    ctx.beginPath(); ctx.moveTo(x, pad); ctx.lineTo(x, H - pad); ctx.stroke();
    if (re % 1 === 0) ctx.fillText(String(re), x - 6, mapY(0) + 12);
  });
  [-1.5, -1, -0.5, 0, 0.5].forEach(im => {
    const y = mapY(im);
    ctx.beginPath(); ctx.moveTo(pad, y); ctx.lineTo(W - pad, y); ctx.stroke();
    if (im !== 0 && im % 1 === 0) ctx.fillText(`${im}j`, mapX(0) + 5, y + 3);
  });

  // Real & Imag axes
  ctx.strokeStyle = '#94a3b8'; ctx.lineWidth = 1.2;
  ctx.beginPath(); ctx.moveTo(pad, mapY(0)); ctx.lineTo(W - pad, mapY(0)); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(mapX(0), pad); ctx.lineTo(mapX(0), H - pad); ctx.stroke();
  ctx.fillStyle = '#334155'; ctx.font = 'bold 10.5px Consolas, monospace';
  ctx.fillText('Re(L)', W - pad - 30, mapY(0) - 6);
  ctx.fillText('Im(L)', mapX(0) + 6, pad + 10);

  // Unit circle |L(jω)| = 1 (for reading Phase Margin PM)
  ctx.save();
  ctx.strokeStyle = '#94a3b8'; ctx.lineWidth = 1.1; ctx.setLineDash([3, 3]);
  ctx.beginPath(); ctx.arc(mapX(0), mapY(0), 1.0 * scale, 0, Math.PI * 2); ctx.stroke();
  ctx.restore();
  ctx.fillStyle = '#64748b'; ctx.font = '10px Consolas, monospace';
  ctx.fillText('|L|=1', mapX(0.72), mapY(0.72));

  // Ms forbidden circle centered at (-1, 0)
  const rPx = nq.ms_radius * scale;
  ctx.fillStyle = 'rgba(180, 83, 9, 0.11)';
  ctx.strokeStyle = '#b45309'; ctx.lineWidth = 1.5; ctx.setLineDash([4, 3]);
  ctx.beginPath(); ctx.arc(mapX(-1), mapY(0), rPx, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
  ctx.setLineDash([]);
  ctx.fillStyle = '#b91c1c'; ctx.beginPath(); ctx.arc(mapX(-1), mapY(0), 4.2, 0, Math.PI * 2); ctx.fill();
  ctx.font = 'bold 10.5px Consolas, monospace'; ctx.fillText('(-1, j0) 临界点', mapX(-1) - 42, mapY(0) - rPx - 8);

  const plotLocus = (pts, color, w) => {
    if (!pts || pts.length < 2) return;
    ctx.strokeStyle = color; ctx.lineWidth = w; ctx.beginPath();
    pts.forEach((p, i) => { const x = mapX(p.re), y = mapY(p.im); i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y); });
    ctx.stroke();
  };
  plotLocus(nq.before, '#b91c1c', 1.8);
  plotLocus(nq.after, '#047857', 2.5);

  // Top-right engineering stability margin callout box
  if (currentData && currentData.safety) {
    const s = currentData.safety;
    const bx = W - 168, by = 12, bw = 156, bh = 58;
    ctx.fillStyle = 'rgba(248,250,252,0.94)'; ctx.strokeStyle = '#cbd5e1'; ctx.lineWidth = 1;
    ctx.fillRect(bx, by, bw, bh); ctx.strokeRect(bx, by, bw, bh);
    ctx.fillStyle = '#0f172a'; ctx.font = 'bold 10.5px Consolas, monospace';
    ctx.fillText(`增益裕度 GM: ${s.gain_margin} (≥1.8)`, bx + 8, by + 17);
    ctx.fillText(`相位裕度 PM: ${s.phase_margin_deg}° (≥35°)`, bx + 8, by + 34);
    ctx.fillText(`敏感度峰 Ms: ${s.max_sensitivity_ms} (≤2.2)`, bx + 8, by + 51);
  }
}

function formatMd(text) {
  const esc = String(text).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  return esc
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code style="background:#eef2f6;padding:1px 4px;border-radius:3px;font-family:Consolas,monospace;font-size:11px">$1</code>');
}

async function sendCopilot() {
  const input = document.getElementById('copilotInput');
  const msg = input.value.trim();
  if (!msg) return;
  input.value = '';
  const log = document.getElementById('copilotLog');
  log.innerHTML += `<div class="msg msg-user">${formatMd(msg)}</div>`;
  log.scrollTop = log.scrollHeight;

  try {
    const resp = await fetch('/api/copilot', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: msg, current_loop_id: selectedLoop ? selectedLoop.loop_id : 'LOOP-006' }),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const res = await resp.json();

    log.innerHTML += `<div class="msg msg-bot">${formatMd(res.reply || '无返回内容')}</div>`;
    log.scrollTop = log.scrollHeight;

    if (res.action && res.action.type === 'UPDATE_RESULT') {
      renderResult(res.action.data);
    } else if (res.action && (res.action.type === 'SELECT_LOOP' || res.action.type === 'HIGHLIGHT_LOOP')) {
      const target = allLoops.find(l => l.loop_id === res.action.loop_id);
      if (target) { selectLoop(target); runWorkflow(target.loop_id); }
    }
  } catch (err) {
    log.innerHTML += `<div class="msg msg-bot" style="color:#b91c1c;border-color:#fecaca;background:#fef2f2">■ 指令请求失败（${escHtml(err.message || '网络异常')}），请稍后重试。</div>`;
    log.scrollTop = log.scrollHeight;
  }
}

async function runSandbox() {
  const btn = document.getElementById('runSandboxBtn');
  btn.disabled = true; btn.textContent = '实时仿真校验中...';
  const payload = {
    K: +document.getElementById('sK').value,
    tau: +document.getElementById('sTau').value,
    theta: +document.getElementById('sTheta').value,
    init_Kc: +document.getElementById('sKc').value,
    init_Ti: +document.getElementById('sTi').value,
    stiction_S: +document.getElementById('sS').value,
    stiction_J: +document.getElementById('sS').value * 0.65,
    max_overshoot_pct: +document.getElementById('sOs').value,
  };
  try {
    const resp = await fetch('/api/sandbox', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    renderSandboxOutput(data);
  } catch (err) {
    const sbEl = document.getElementById('sbStatus');
    sbEl.textContent = '沙盒请求异常';
    sbEl.className = 'chip chip-AGGRESSIVE_TUNING';
    document.getElementById('sbSummary').innerHTML = `<b style="color:#b91c1c">■ 沙盒仿真请求失败（${escHtml(err.message || '网络异常')}）</b>，未更新参数结论。`;
  } finally {
    btn.disabled = false; btn.textContent = '注入自定义工况并执行闭环校验';
  }
}

function buildSampleCsv(kind) {
  const rows = ['t,sp,pv,op'];
  let pv = 500.0, op = 50.0, integ = 0.0, vpos = 50.0;
  const delayBuf = new Array(6).fill(50.0);
  for (let i = 0; i < 300; i++) {
    const t = i * 2;
    const sp = i < 40 ? 500.0 : (i < 170 ? 506.0 : 502.0);
    const err = sp - pv;
    if (kind === 'stic') {
      integ += err * 2.0 / 12.0;
      op = Math.max(5, Math.min(95, 50.0 + 0.9 * err + 0.9 * integ));
      if (Math.abs(op - vpos) >= 4.2) vpos = op;
      delayBuf.push(vpos);
    } else {
      integ += err * 2.0 / 8.5;
      op = Math.max(5, Math.min(95, 50.0 + 2.15 * err + 2.15 * integ));
      delayBuf.push(op);
    }
    const uDel = delayBuf.shift();
    pv += ((1.4 * (uDel - 50.0) - (pv - 500.0)) / 15.0) * 2.0;
    rows.push(`${t},${sp.toFixed(2)},${pv.toFixed(3)},${op.toFixed(3)}`);
  }
  return rows.join('\n');
}

async function submitCsvText(filename, text) {
  const sbEl = document.getElementById('sbStatus');
  sbEl.textContent = 'CSV 解析与诊断中...';
  sbEl.className = 'chip chip-SLUGGISH_TUNING';
  const res = await fetch('/api/upload_csv', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      filename,
      csv_text: text,
      init_Kc: +document.getElementById('sKc').value,
      init_Ti: +document.getElementById('sTi').value,
    }),
  });
  const data = await res.json();
  if (!res.ok) {
    sbEl.textContent = `CSV 拦截 (HTTP ${res.status})`;
    sbEl.className = 'chip chip-AGGRESSIVE_TUNING';
    document.getElementById('sbSummary').innerHTML = `<b style="color:#b91c1c">■ Fail-Closed 输入校验拦截 (${escHtml(filename)})：</b>${escHtml(data.detail || 'CSV 解析失败')}`;
    document.getElementById('sbAuditBody').innerHTML = '<tr><td colspan="6" class="st-fail">输入数据格式不合格，已触发 Fail-Closed 拦截，未进入参数辨识与整定阶段。</td></tr>';
    return;
  }
  sbEl.className = 'chip chip-NORMAL';
  renderSandboxOutput(data);
}

async function handleCSVUpload(e) {
  const file = e.target.files[0];
  if (!file) return;
  const text = await file.text();
  await submitCsvText(file.name, text);
}

function renderSandboxOutput(data) {
  const sbEl = document.getElementById('sbStatus');
  sbEl.textContent = zhStatus(data.final_status);
  sbEl.title = data.final_status;
  drawTimeChart('sandboxCanvas', data.waveforms, null, 1.0);
  const am = data.audit_meta || {};
  if (am.run_id) {
    document.getElementById('rRunMeta').textContent = `当前工单: ${am.run_id} | 哈希:${(am.output_sha256||'').slice(0,8)}`;
  }
  document.getElementById('sbSummary').innerHTML = `
    <b>运行溯源：</b><code>${escHtml(am.run_id || '-')}</code> | 时间：${escHtml(am.timestamp || '-')} | inHash:<code>${escHtml((am.input_sha256||'').slice(0,10))}</code> | outHash:<code>${escHtml((am.output_sha256||'').slice(0,10))}</code><br/>
    <b>现场诊断：</b>${escHtml(zhAnomaly(data.diagnosis.anomaly_type))} (OI=${escHtml(data.diagnosis.oscillation_index)}, SI=${escHtml(data.diagnosis.stiction_index)})<br/>
    <b>实时辨识：</b>K=${escHtml(data.identification ? data.identification.K : '-')}, τ=${escHtml(data.identification ? data.identification.tau : '-')}s, θ=${escHtml(data.identification ? data.identification.theta : '-')}s (Fit ${escHtml(data.identification ? data.identification.val_fit_pct : '-')}%, R²=${escHtml(data.identification ? data.identification.val_r2 : '-')})<br/>
    <b>最终结论：</b>${escHtml(data.decision_reason)}
  `;
  const sbAudit = document.getElementById('sbAuditBody');
  sbAudit.innerHTML = '';
  if (data.safety && data.safety.constraint_audit) {
    data.safety.constraint_audit.forEach(c => {
      sbAudit.innerHTML += `<tr><td><b>${escHtml(c.constraint_id)}</b></td><td>${escHtml(c.category)}</td><td>${escHtml(c.rule_name)}</td><td>${escHtml(c.measured_value)}</td><td>${escHtml(c.threshold)}</td><td class="${c.passed ? 'st-pass':'st-fail'}">${c.passed ? 'PASS':'FAIL'}</td></tr>`;
    });
  } else {
    sbAudit.innerHTML = '<tr><td colspan="6" style="color:var(--muted)">健康工况跳过安全变更审计。</td></tr>';
  }
}

function renderPlantTable(rows) {
  // 1. Render 5-Unit Control Health Heatmap (Honeywell CPA / PlantESP style)
  const hm = document.getElementById('unitHeatmap');
  if (hm) {
    hm.innerHTML = '';
    const byUnit = new Map();
    rows.forEach(r => {
      const u = r.unit_name || '未分组装置';
      if (!byUnit.has(u)) byUnit.set(u, []);
      byUnit.get(u).push(r);
    });
    byUnit.forEach((uRows, uName) => {
      const retuneCnt = uRows.filter(r => r.final_status === 'SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW').length;
      const card = document.createElement('div');
      card.className = 'hm-unit';
      card.innerHTML = `
        <div class="hm-unit-head">
          <span class="hm-unit-name">${uName}</span>
          <span class="hm-unit-stat">${uRows.length}路 · 复核${retuneCnt}</span>
        </div>
        <div class="hm-grid"></div>
      `;
      const grid = card.querySelector('.hm-grid');
      uRows.forEach(r => {
        const stCls = (r.final_status === 'HEALTHY_NO_CHANGE' || r.final_status === 'NO_CHANGE_HEALTHY') ? 'st-ok'
          : (r.final_status === 'SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW' ? 'st-retune'
          : (r.final_status === 'VALVE_MAINTENANCE_REQUIRED' ? 'st-valve' : 'st-block'));
        const tile = document.createElement('div');
        tile.className = `hm-tile ${stCls}`;
        tile.title = `${r.loop_id} (${r.tag_name}) | ${zhStatus(r.final_status)}`;
        tile.innerHTML = `
          <div class="hm-tile-top"><span>${r.tag_name}</span><span class="hm-tile-oi">OI ${r.oi_before.toFixed(1)}</span></div>
          <div class="hm-tile-sub">${zhAnomaly(r.pred_anomaly)} · ${zhStatus(r.final_status).split(' · ')[0]}</div>
        `;
        tile.onclick = () => {
          document.querySelector('[data-view="view-workbench"]').click();
          const target = allLoops.find(l => l.loop_id === r.loop_id);
          if (target) { selectLoop(target); runWorkflow(target.loop_id); }
        };
        grid.appendChild(tile);
      });
      hm.appendChild(card);
    });
  }

  // 2. Render 30-Loop Detail Table
  const tbody = document.getElementById('plantTableBody');
  tbody.innerHTML = '';
  rows.forEach(r => {
    const tr = document.createElement('tr');
    tr.style.cursor = 'pointer';
    tr.innerHTML = `
      <td><b>${r.loop_id}</b></td><td><b>${r.tag_name}</b></td><td>${r.unit_name}</td>
      <td><span class="chip chip-${r.true_anomaly}">${zhAnomaly(r.true_anomaly)}</span></td>
      <td class="${r.diag_correct ? 'st-pass':'st-fail'}">${zhAnomaly(r.pred_anomaly)}</td>
      <td>${r.val_fit_pct !== null ? `${r.val_fit_pct}% / ${r.val_r2}` : '—'}</td>
      <td>${r.oi_before.toFixed(2)} → <b>${r.oi_after.toFixed(2)}</b></td>
      <td>${r.iae_before.toFixed(2)} → <b>${r.iae_after.toFixed(2)}</b></td>
      <td>${r.multi_regime_pass_rate_pct !== null ? r.multi_regime_pass_rate_pct + '%' : '—'}</td>
      <td title="${r.final_status}"><span style="font-size:11.5px;font-weight:600;color:var(--ink-soft)">${zhStatus(r.final_status)}</span></td>
    `;
    tr.onclick = () => {
      document.querySelector('[data-view="view-workbench"]').click();
      const target = allLoops.find(l => l.loop_id === r.loop_id);
      if (target) { selectLoop(target); runWorkflow(target.loop_id); }
    };
    tbody.appendChild(tr);
  });
}

window.addEventListener('resize', () => { if (currentData) renderActiveChart(); });
init();
