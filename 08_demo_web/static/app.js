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

async function init() {
  const [benchRes, loopsRes, ojwRes] = await Promise.all([
    fetch('/api/benchmark').then(r => r.json()),
    fetch('/api/loops').then(r => r.json()),
    fetch('/api/openjiuwen').then(r => r.json()),
  ]);

  // Transparent Ribbon stats (exact 5-class breakdown + dual denominators)
  const d = benchRes.denominators || {};
  document.getElementById('rDist').textContent = `${d.healthy_no_change_loops}健康 / ${d.simulation_validated_retuned_loops}复核 / ${d.model_validation_failed_loops}模型拒 / ${d.valve_maintenance_required_loops}阀检 / ${d.performance_not_improved_loops}外扰拒`;
  document.getElementById('rDiag').textContent = `${benchRes.diagnosis_accuracy_pct}%`;
  document.getElementById('rId').textContent = `${benchRes.avg_id_val_accuracy_pct}% / ${benchRes.avg_id_val_accuracy_all_25_non_healthy_pct}%`;
  document.getElementById('rMulti').textContent = `${benchRes.avg_multi_regime_pass_rate_pct}% / ${benchRes.avg_multi_regime_pass_rate_all_checked_pct}%`;
  document.getElementById('rOjw').textContent = ojwRes.native_tool_layer_verified ? `v${ojwRes.sdk_version} 原生工具层已验证` : '兼容运行时(native=false)';

  // View 3 Plant KPI Cards
  document.getElementById('pkSuccess').textContent = `${benchRes.task_success_rate_pct}%`;
  document.getElementById('pkDiag').textContent = `${benchRes.diagnosis_accuracy_pct}%`;
  document.getElementById('pkId').textContent = `${benchRes.avg_id_val_accuracy_pct}%`;
  document.getElementById('pkIdSub').textContent = `有效 n=19 (全25非健康 ${benchRes.avg_id_val_accuracy_all_25_non_healthy_pct}%)`;
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
  document.querySelectorAll('.q-chip').forEach(c => {
    c.onclick = () => {
      document.getElementById('copilotInput').value = c.dataset.q;
      sendCopilot();
    };
  });

  document.querySelectorAll('.demo-btn').forEach(btn => {
    btn.onclick = () => {
      document.querySelectorAll('.demo-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      if (btn.dataset.demoView) {
        document.querySelector(`.nav-tab[data-view="${btn.dataset.demoView}"]`)?.click();
        return;
      }
      if (btn.dataset.demoChart) {
        activeChart = btn.dataset.demoChart;
        document.querySelectorAll('.c-tab').forEach(x => x.classList.toggle('active', x.dataset.chart === activeChart));
      }
      if (btn.dataset.demoLoop) {
        const target = allLoops.find(x => x.loop_id === btn.dataset.demoLoop);
        if (target) {
          selectLoop(target);
          runWorkflow(target.loop_id, { preferred_strategy: null });
        }
      }
    };
  });

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
    if (q && !(`${l.loop_id} ${l.tag_name} ${l.unit_name} ${l.description} ${l.anomaly_type}`.toLowerCase().includes(q))) return false;
    return true;
  });
  document.getElementById('loopCountTag').textContent = `${items.length}/${allLoops.length}`;
  items.forEach(loop => {
    const row = document.createElement('div');
    row.className = 'loop-row' + (selectedLoop && selectedLoop.loop_id === loop.loop_id ? ' active' : '');
    row.innerHTML = `
      <div class="loop-row-top">
        <span class="tag-code">${loop.loop_id} · ${loop.tag_name}</span>
        <span class="chip chip-${loop.anomaly_type}">${loop.anomaly_type.replace('_TUNING','').replace('EXTERNAL_','EXT_')}</span>
      </div>
      <div class="loop-desc">${loop.unit_name} · ${loop.description}</div>
    `;
    row.onclick = () => {
      selectLoop(loop);
      document.getElementById('strategySelect').value = '';
      runWorkflow(loop.loop_id);
    };
    list.appendChild(row);
  });
}

function selectLoop(loop) {
  selectedLoop = loop;
  document.getElementById('selectedTitle').textContent = `${loop.loop_id} · ${loop.tag_name} — ${loop.description} (${loop.unit_name})`;
  renderLoopList();
}

function renderUnitSVG(unitName) {
  if (unitName.includes('精馏') || unitName.includes('CDU')) {
    return `
      <rect x="24" y="10" width="38" height="72" rx="16" fill="#dbeafe" stroke="#1e3a8a" stroke-width="1.8"/>
      <line x1="26" y1="28" x2="60" y2="28" stroke="#64748b" stroke-dasharray="3,2"/>
      <line x1="26" y1="44" x2="60" y2="44" stroke="#64748b" stroke-dasharray="3,2"/>
      <line x1="26" y1="60" x2="60" y2="60" stroke="#64748b" stroke-dasharray="3,2"/>
      <text x="43" y="94" text-anchor="middle" font-size="9" font-weight="700" fill="#0f172a">常减压精馏塔</text>`;
  }
  if (unitName.includes('催化') || unitName.includes('FCC')) {
    return `
      <rect x="16" y="16" width="24" height="62" rx="8" fill="#fef3c7" stroke="#92400e" stroke-width="1.6"/>
      <rect x="48" y="12" width="30" height="66" rx="10" fill="#fee2e2" stroke="#991b1b" stroke-width="1.6"/>
      <line x1="40" y1="44" x2="48" y2="44" stroke="#334155" stroke-width="2"/>
      <text x="47" y="94" text-anchor="middle" font-size="9" font-weight="700" fill="#0f172a">FCC 反应-再生</text>`;
  }
  if (unitName.includes('裂解') || unitName.includes('Cracker')) {
    return `
      <polygon points="18,78 18,30 46,12 74,30 74,78" fill="#ffedd5" stroke="#9a3412" stroke-width="1.7"/>
      <path d="M28,68 L28,38 L46,26 L64,38 L64,68" fill="none" stroke="#ea580c" stroke-width="2"/>
      <text x="46" y="94" text-anchor="middle" font-size="9" font-weight="700" fill="#0f172a">乙烯裂解炉</text>`;
  }
  if (unitName.includes('反应釜') || unitName.includes('CSTR')) {
    return `
      <rect x="20" y="18" width="48" height="60" rx="12" fill="#e0e7ff" stroke="#3730a3" stroke-width="1.7"/>
      <line x1="44" y1="10" x2="44" y2="62" stroke="#1e293b" stroke-width="1.8"/>
      <line x1="30" y1="62" x2="58" y2="62" stroke="#1e293b" stroke-width="2.2"/>
      <text x="44" y="94" text-anchor="middle" font-size="9" font-weight="700" fill="#0f172a">连续搅拌釜 CSTR</text>`;
  }
  return `
    <rect x="22" y="12" width="42" height="68" rx="14" fill="#d1fae5" stroke="#065f46" stroke-width="1.7"/>
    <rect x="27" y="26" width="32" height="14" fill="#6ee7b7" opacity="0.7"/>
    <rect x="27" y="48" width="32" height="14" fill="#6ee7b7" opacity="0.7"/>
    <text x="43" y="94" text-anchor="middle" font-size="9" font-weight="700" fill="#0f172a">加氢精制床层</text>`;
}

function renderPIDSchematic(data) {
  const meta = data.loop_meta;
  const d = data.diagnosis;
  const isStic = d.anomaly_type === 'VALVE_STICTION';
  const valveColor = isStic ? '#b91c1c' : '#047857';
  const pipeColor = isStic ? '#b91c1c' : '#1d4ed8';
  document.getElementById('pidSchematic').innerHTML = `
    <svg viewBox="0 0 410 100" width="100%" height="100">
      ${renderUnitSVG(meta.unit_name)}
      <!-- Animated process pipe -->
      <line x1="80" y1="45" x2="255" y2="45" stroke="#cbd5e1" stroke-width="5"/>
      <line x1="80" y1="45" x2="255" y2="45" stroke="${pipeColor}" stroke-width="2" class="flow-pipe"/>
      <!-- Transmitter tap & ISA Controller Bubble -->
      <line x1="170" y1="45" x2="170" y2="28" stroke="#475569" stroke-width="1.4"/>
      <circle cx="170" cy="24" r="20" fill="#ffffff" stroke="#1d4ed8" stroke-width="2"/>
      <line x1="151" y1="24" x2="189" y2="24" stroke="#bfdbfe" stroke-width="1"/>
      <text x="170" y="21" text-anchor="middle" font-size="8.5" font-weight="800" fill="#1d4ed8">${meta.tag_name}</text>
      <text x="170" y="34" text-anchor="middle" font-size="7.5" font-weight="700" fill="#475569">DCS PID</text>
      <!-- Signal line to pneumatic control valve -->
      <path d="M190,24 L278,24 L278,34" fill="none" stroke="#1d4ed8" stroke-width="1.4" stroke-dasharray="3,2"/>
      <!-- Pneumatic Globe Valve -->
      <rect x="266" y="16" width="24" height="10" rx="3" fill="#e2e8f0" stroke="#334155" stroke-width="1.3"/>
      <line x1="278" y1="26" x2="278" y2="45" stroke="#334155" stroke-width="1.6"/>
      <polygon points="256,34 278,45 256,56" fill="${valveColor}" opacity="0.9"/>
      <polygon points="300,34 278,45 300,56" fill="${valveColor}" opacity="0.9"/>
      <line x1="300" y1="45" x2="338" y2="45" stroke="#cbd5e1" stroke-width="5"/>
      <line x1="300" y1="45" x2="338" y2="45" stroke="${valveColor}" stroke-width="2" class="flow-pipe"/>
      <text x="278" y="72" text-anchor="middle" font-size="9.5" font-weight="800" fill="${valveColor}">${isStic ? '⚠ 调节阀粘滞告警' : '● 调节阀动作正常'}</text>
      <!-- Right Live Tag Box -->
      <rect x="342" y="16" width="64" height="56" rx="5" fill="#ffffff" stroke="#cbd5e1"/>
      <text x="374" y="32" text-anchor="middle" font-size="8.5" fill="#64748b">SP 设定</text>
      <text x="374" y="45" text-anchor="middle" font-size="10" font-weight="800" fill="#1d4ed8">${meta.pv_bias}${meta.pv_unit}</text>
      <text x="374" y="62" text-anchor="middle" font-size="9" font-weight="700" fill="#0f172a">OP ${meta.op_bias}%</text>
    </svg>
  `;
}

async function runWorkflow(loopId, opts = {}) {
  const seq = ++latestRequestSeq;
  const btn = document.getElementById('runBtn');
  btn.disabled = true; btn.textContent = '5-Agent 协同推理中...';
  try {
    const res = await fetch(`/api/run/${loopId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(opts),
    });
    const data = await res.json();
    // Stale-response guard: discard out-of-order response if user already switched loops!
    if (seq !== latestRequestSeq) return;
    replayProgress = 1.0;
    renderResult(data);
  } finally {
    if (seq === latestRequestSeq) {
      btn.disabled = false; btn.textContent = '执行 5-Agent 闭环';
    }
  }
}

function renderResult(data) {
  currentData = data;
  document.getElementById('topMode').textContent = `Engine: ${data.llm_mode}`;
  const am0 = data.audit_meta || {};
  const strip = document.getElementById('auditStrip');
  if (strip) {
    const dig = am0.record_digest_sha256 ? am0.record_digest_sha256.slice(0, 12) : '--';
    const av = (am0.audit_verification && am0.audit_verification.audit_status) || '--';
    strip.innerHTML = `<span><b>RunID:</b> ${am0.run_id || '--'} &nbsp;|&nbsp; <b>RecordDigest:</b> ${dig}… &nbsp;|&nbsp; <b>Audit:</b> ${av}</span><span><b>deployment_authorized=false</b> · 隔离仿真专用</span>`;
  }
  if (data.audit_meta) {
    document.getElementById('rRunMeta').textContent = `${data.audit_meta.run_id} | in:${data.audit_meta.input_sha256.slice(0,8)} out:${data.audit_meta.output_sha256.slice(0,8)}`;
  }
  renderPIDSchematic(data);

  const ip = data.initial_pid, fp = data.final_pid;
  const d0 = data.diagnosis, d1 = data.after_diagnosis || d0;
  document.getElementById('mPid').innerHTML = `<span style="color:#b45309">(${ip.Kc}, ${ip.Ti})</span> → <span style="color:#047857">(${fp.Kc}, ${fp.Ti})</span>`;
  document.getElementById('mOi').innerHTML = `${d0.oscillation_index.toFixed(2)} → <span style="color:#047857">${d1.oscillation_index.toFixed(2)}</span>`;
  document.getElementById('mIae').innerHTML = `${d0.iae.toFixed(2)} → <span style="color:#047857">${d1.iae.toFixed(2)}</span>`;
  document.getElementById('mOp').innerHTML = `${d0.op_travel.toFixed(2)} → <span style="color:#047857">${d1.op_travel.toFixed(2)}</span>`;
  document.getElementById('mIdAcc').textContent = data.identification ? `${data.identification.val_fit_pct}% / R²=${data.identification.val_r2}` : '健康跳过';
  document.getElementById('mMargin').textContent = data.safety ? `${data.safety.gain_margin}/${data.safety.phase_margin_deg}°/${data.safety.max_sensitivity_ms}` : '安全保持';

  const sb = document.getElementById('statusBadge');
  sb.textContent = data.final_status;
  const isRejected = ['MODEL_VALIDATION_FAILED', 'SAFETY_CONSTRAINT_FAILED', 'REJECTED_WITH_REASON'].includes(data.final_status);
  const isWarn = ['VALVE_MAINTENANCE_REQUIRED', 'PERFORMANCE_NOT_IMPROVED'].includes(data.final_status);
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
  const prefix = isRejected ? '【拒绝推荐 · 保持原参数】' : (isWarn ? '【工程警示 · 非纯 PID 整定场景】' : '【仿真校验通过 · 待人工工程复核】');
  banner.className = 'risk-banner ' + (isRejected ? 'danger' : (isWarn ? '' : 'ok'));
  banner.textContent = `${prefix} ${data.decision_reason}`;

  // Visual Context Compression Bar
  const ab = data.anti_bloat_metrics;
  document.getElementById('abComp').textContent = `压缩 ${ab.compression_ratio_pct}%`;
  document.getElementById('compFill').style.width = `${Math.min(100, Math.max(5, ab.compression_ratio_pct))}%`;
  document.getElementById('abBytes').textContent = `${ab.raw_timeseries_bytes} B → ${ab.compact_handoff_bytes} B`;
  document.getElementById('abCalls').textContent = `MCP ${ab.total_tool_calls} 次 (防重 ${ab.duplicate_tool_calls_prevented})`;

  // Connected Vertical Timeline with Collapsible MCP JSON Inspector
  const traceEl = document.getElementById('traceList');
  traceEl.innerHTML = '';
  data.trace.forEach((t, idx) => {
    const item = document.createElement('div');
    item.className = 'trace-item';
    const preId = `mcp-json-${idx}`;
    const lt = t.llm_telemetry;
    const llmPill = (lt && lt.mode === 'live_llm_api')
      ? `<div class="trace-meta" style="color:#0369a1;font-weight:600">LLM: ${lt.model} · ${lt.latency_ms ?? '-'}ms · ${lt.total_tokens ?? '-'} tok${lt.request_id ? ' · req:' + lt.request_id.slice(0, 8) : ''}</div>`
      : '';
    item.innerHTML = `
      <div class="trace-node ${t.status}"></div>
      <div class="trace-card ${t.status}">
        <div class="trace-top"><span>#${t.step} ${t.agent}</span><span class="chip">${t.status}</span></div>
        <div class="trace-meta">${t.stage || '-'} · ${t.skill} · ${t.latency_ms ?? '-'}ms</div>
        ${llmPill}
        <div class="trace-txt">${t.summary}</div>
        <button class="trace-json-btn" onclick="const el=document.getElementById('${preId}');el.style.display=el.style.display==='block'?'none':'block'">▸ 查看结构化 MCP 输出</button>
        <pre class="trace-json-pre" id="${preId}">${JSON.stringify(t.metrics || {}, null, 2)}</pre>
      </div>`;
    traceEl.appendChild(item);
  });

  // 11-Item Safety Audit
  const auditBody = document.getElementById('auditBody');
  auditBody.innerHTML = '';
  if (data.safety) {
    data.safety.constraint_audit.forEach(c => {
      auditBody.innerHTML += `<tr><td><b>${c.constraint_id}</b></td><td>${c.category}</td><td>${c.rule_name}</td><td>${c.measured_value}</td><td>${c.threshold}</td><td class="${c.passed ? 'st-pass':'st-fail'}">${c.passed ? 'PASS':'FAIL'}</td></tr>`;
    });
  } else {
    auditBody.innerHTML = '<tr><td colspan="6" style="color:var(--muted)">健康回路，保持原 DCS 参数</td></tr>';
  }

  // 5-Regime Table
  const regimeBody = document.getElementById('regimeBody');
  regimeBody.innerHTML = '';
  if (data.safety) {
    data.safety.operating_point_checks.forEach(r => {
      regimeBody.innerHTML += `<tr><td><b>${r.regime_name}</b></td><td>${r.plant_K} / ${r.plant_tau} / ${r.plant_theta}</td><td>${r.overshoot_pct}% / ≤${r.overshoot_limit_pct}%</td><td>${r.oscillation_index} / ≤${r.oi_limit}</td><td>${r.iae}</td><td class="${r.passed ? 'st-pass':'st-fail'}">${r.passed ? 'PASS':'FAIL'}</td></tr>`;
    });
  } else {
    regimeBody.innerHTML = '<tr><td colspan="6" style="color:var(--muted)">健康回路，无需跨工况验证</td></tr>';
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
  const pad = 46;
  const xs = ph.op, ys = ph.pv;
  let x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  if (x1 - x0 < 0.2) { x0 -= 1; x1 += 1; }
  if (y1 - y0 < 0.2) { y0 -= 1; y1 += 1; }
  const mapX = v => pad + ((v - x0) / (x1 - x0)) * (W - 2 * pad);
  const mapY = v => H - pad - ((v - y0) / (y1 - y0)) * (H - 2 * pad);

  ctx.strokeStyle = '#e2e8f0'; ctx.strokeRect(pad, pad, W - 2 * pad, H - 2 * pad);
  ctx.fillStyle = '#334155'; ctx.font = '11px Consolas, monospace';
  ctx.fillText(`OP (%) [${x0.toFixed(1)} ~ ${x1.toFixed(1)}]`, W / 2 - 55, H - 14);
  ctx.fillText(`PV [${y0.toFixed(1)} ~ ${y1.toFixed(1)}] | 粘滞指数 SI = ${diag.stiction_index.toFixed(2)}`, pad, 22);

  ctx.strokeStyle = diag.anomaly_type === 'VALVE_STICTION' ? '#6d28d9' : '#1d4ed8';
  ctx.lineWidth = 1.8; ctx.beginPath();
  xs.forEach((v, i) => { const x = mapX(v), y = mapY(ys[i]); i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y); });
  ctx.stroke();
}

function drawNyquistChart(canvasId, nq) {
  const { ctx, W, H } = setupCanvas(canvasId);
  ctx.clearRect(0, 0, W, H);
  const pad = 40;
  const reMin = -2.2, reMax = 0.8, imMin = -1.8, imMax = 0.8;
  const scale = Math.min((W - 2 * pad) / (reMax - reMin), (H - 2 * pad) / (imMax - imMin));
  const cx = pad + (W - 2 * pad - (reMax - reMin) * scale) / 2;
  const mapX = re => cx + (re - reMin) * scale;
  const mapY = im => H - pad - (im - imMin) * scale;

  ctx.strokeStyle = '#cbd5e1'; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(pad, mapY(0)); ctx.lineTo(W - pad, mapY(0)); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(mapX(0), pad); ctx.lineTo(mapX(0), H - pad); ctx.stroke();
  ctx.fillStyle = '#64748b'; ctx.font = '10.5px Consolas, monospace';
  ctx.fillText('Re(L)', W - pad - 28, mapY(0) - 6);
  ctx.fillText('Im(L)', mapX(0) + 6, pad + 10);

  const rPx = nq.ms_radius * scale;
  ctx.fillStyle = 'rgba(180, 83, 9, 0.11)';
  ctx.strokeStyle = '#b45309'; ctx.lineWidth = 1.5; ctx.setLineDash([4, 3]);
  ctx.beginPath(); ctx.arc(mapX(-1), mapY(0), rPx, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
  ctx.setLineDash([]);
  ctx.fillStyle = '#b91c1c'; ctx.beginPath(); ctx.arc(mapX(-1), mapY(0), 4.5, 0, Math.PI * 2); ctx.fill();
  ctx.font = 'bold 11px Consolas, monospace'; ctx.fillText('(-1, j0) 临界失稳点', mapX(-1) - 52, mapY(0) - rPx - 12);

  const plotLocus = (pts, color, w) => {
    if (!pts || pts.length < 2) return;
    ctx.strokeStyle = color; ctx.lineWidth = w; ctx.beginPath();
    pts.forEach((p, i) => { const x = mapX(p.re), y = mapY(p.im); i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y); });
    ctx.stroke();
  };
  plotLocus(nq.before, '#b91c1c', 1.8);
  plotLocus(nq.after, '#047857', 2.5);
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

  const res = await fetch('/api/copilot', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message: msg, current_loop_id: selectedLoop ? selectedLoop.loop_id : 'LOOP-006' }),
  }).then(r => r.json());

  log.innerHTML += `<div class="msg msg-bot">${formatMd(res.reply)}</div>`;
  log.scrollTop = log.scrollHeight;

  if (res.action && res.action.type === 'UPDATE_RESULT') {
    renderResult(res.action.data);
  } else if (res.action && (res.action.type === 'SELECT_LOOP' || res.action.type === 'HIGHLIGHT_LOOP')) {
    const target = allLoops.find(l => l.loop_id === res.action.loop_id);
    if (target) { selectLoop(target); runWorkflow(target.loop_id); }
  }
}

async function runSandbox() {
  const btn = document.getElementById('runSandboxBtn');
  btn.disabled = true; btn.textContent = '5-Agent 实时仿真与救场中...';
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
    const data = await fetch('/api/sandbox', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    }).then(r => r.json());
    renderSandboxOutput(data);
  } finally {
    btn.disabled = false; btn.textContent = '注入自定义工况并启动 5-Agent 现场救场';
  }
}

async function handleCSVUpload(e) {
  const file = e.target.files[0];
  if (!file) return;
  const text = await file.text();
  document.getElementById('sbStatus').textContent = 'CSV 解析与 5-Agent 诊断中...';
  const res = await fetch('/api/upload_csv', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      filename: file.name,
      csv_text: text,
      init_Kc: +document.getElementById('sKc').value,
      init_Ti: +document.getElementById('sTi').value,
    }),
  });
  const data = await res.json();
  if (!res.ok) {
    document.getElementById('sbStatus').textContent = 'CSV 错误';
    document.getElementById('sbSummary').textContent = data.detail || 'CSV 解析失败';
    return;
  }
  renderSandboxOutput(data);
}

function renderSandboxOutput(data) {
  document.getElementById('sbStatus').textContent = data.final_status;
  drawTimeChart('sandboxCanvas', data.waveforms, null, 1.0);
  const am = data.audit_meta || {};
  if (am.run_id) {
    document.getElementById('rRunMeta').textContent = `${am.run_id} | in:${(am.input_sha256||'').slice(0,8)} out:${(am.output_sha256||'').slice(0,8)}`;
  }
  document.getElementById('sbSummary').innerHTML = `
    <b>运行溯源：</b><code>${am.run_id || '-'}</code> | 时间：${am.timestamp || '-'} | inHash:<code>${(am.input_sha256||'').slice(0,10)}</code> | outHash:<code>${(am.output_sha256||'').slice(0,10)}</code><br/>
    <b>现场诊断：</b>${data.diagnosis.anomaly_type} (OI=${data.diagnosis.oscillation_index}, SI=${data.diagnosis.stiction_index})<br/>
    <b>实时辨识：</b>K=${data.identification ? data.identification.K : '-'}, τ=${data.identification ? data.identification.tau : '-'}s, θ=${data.identification ? data.identification.theta : '-'}s (Fit ${data.identification ? data.identification.val_fit_pct : '-'}%, R²=${data.identification ? data.identification.val_r2 : '-'})<br/>
    <b>最终结论：</b>${data.decision_reason}
  `;
  const sbAudit = document.getElementById('sbAuditBody');
  sbAudit.innerHTML = '';
  if (data.safety && data.safety.constraint_audit) {
    data.safety.constraint_audit.forEach(c => {
      sbAudit.innerHTML += `<tr><td><b>${c.constraint_id}</b></td><td>${c.category}</td><td>${c.rule_name}</td><td>${c.measured_value}</td><td>${c.threshold}</td><td class="${c.passed ? 'st-pass':'st-fail'}">${c.passed ? 'PASS':'FAIL'}</td></tr>`;
    });
  } else {
    sbAudit.innerHTML = '<tr><td colspan="6" style="color:var(--muted)">健康工况跳过安全变更审计。</td></tr>';
  }
}

function renderPlantTable(rows) {
  const tbody = document.getElementById('plantTableBody');
  tbody.innerHTML = '';
  rows.forEach(r => {
    const tr = document.createElement('tr');
    tr.style.cursor = 'pointer';
    tr.innerHTML = `
      <td><b>${r.loop_id}</b></td><td>${r.tag_name}</td><td>${r.unit_name}</td>
      <td><span class="chip chip-${r.true_anomaly}">${r.true_anomaly}</span></td>
      <td class="${r.diag_correct ? 'st-pass':'st-fail'}">${r.pred_anomaly}</td>
      <td>${r.val_fit_pct !== null ? `${r.val_fit_pct}% / ${r.val_r2}` : '—'}</td>
      <td>${r.oi_before.toFixed(2)} → <b>${r.oi_after.toFixed(2)}</b></td>
      <td>${r.iae_before.toFixed(2)} → <b>${r.iae_after.toFixed(2)}</b></td>
      <td>${r.multi_regime_pass_rate_pct !== null ? r.multi_regime_pass_rate_pct + '%' : '—'}</td>
      <td><code>${r.final_status}</code></td>
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
