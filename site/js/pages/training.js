import { api } from '../api.js';
import { startPoll, stopPoll } from '../router.js';
import { toast } from '../toast.js';

const FOREX_PAIRS = [
  'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD',
  'USDCAD', 'NZDUSD', 'EURGBP', 'EURJPY', 'GBPJPY',
  'AUDJPY', 'EURAUD', 'GBPAUD'
];

const SYNTHETICS = [
  'R_10', 'R_25', 'R_50', 'R_75', 'R_100',
  '1HZ10V', '1HZ25V', '1HZ50V', '1HZ75V', '1HZ100V'
];

export async function trainingPage() {
  const root = document.getElementById('page-container');
  if (!root) return;

  root.innerHTML = `<div style="text-align:center; padding:40px; color:var(--text-2);">Loading training environment & pair datasets...</div>`;

  let trainingState = {};
  let dataIndex = {};
  let modelsIndex = {};
  let settings = {};

  async function loadData() {
    try {
      const [trSt, dtIdx, st] = await Promise.all([
        api.getTraining().catch(() => ({})),
        api.getDataIndex().catch(() => ({})),
        api.getState().catch(() => ({})),
      ]);
      trainingState = trSt || {};
      dataIndex = dtIdx || {};
      settings = st?.settings || {};

      // Try fetching models index if available
      try {
        const m = await api.get('/api/models/index');
        modelsIndex = m || {};
      } catch(_) {}

      render();
    } catch(err) {
      toast(err.message || 'Error loading training data', 'error');
    }
  }

  function render() {
    const isTraining = trainingState.status === 'training';
    const activePair = trainingState.active_pair || '';
    const stepsDone = trainingState.total_steps_done || 0;
    const stepsTarget = trainingState.total_steps_target || 5000000;
    const progressPct = Math.min(100, Math.round((stepsDone / Math.max(1, stepsTarget)) * 100));
    const isLocked = !!settings.training_locked;

    // H2 Honest training ETA calculation from last N checkpoints
    const remainingSteps = Math.max(0, stepsTarget - stepsDone);
    const history = (trainingState.checkpoint_history || []).filter(h =>
      (!h.pair || h.pair === activePair) &&
      (!h.version || h.version === trainingState.active_version) &&
      Number.isFinite(Date.parse(h.utc)) && Number.isFinite(h.step)
    ).sort((a, b) => a.step - b.step);
    let etaInfo = {
      rate: null,
      rateStr: 'measuring...',
      etaStr: 'measuring...',
      etaHours: null,
      elapsedStr: 'measuring...',
      finishStr: 'measuring...',
      queueStr: ''
    };

    if (history.length >= 2) {
      const N = Math.min(5, history.length);
      const recent = history.slice(-N);
      const cFirst = recent[0];
      const cLast = recent[recent.length - 1];
      const stepDelta = cLast.step - cFirst.step;
      const timeDeltaMin = (new Date(cLast.utc).getTime() - new Date(cFirst.utc).getTime()) / 60000;
      if (stepDelta > 0 && timeDeltaMin > 0) {
        const rate = stepDelta / timeDeltaMin;
        const remMin = remainingSteps / rate;
        const etaHours = (remMin / 60).toFixed(1);
        const finishDate = new Date(Date.parse(cLast.utc) + remMin * 60000);
        const timeZone = settings.timezone || 'Africa/Lagos';
        const finishStr = new Intl.DateTimeFormat([], { timeZone, month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZoneName: 'short' }).format(finishDate);
        const startMs = Date.parse(trainingState.cycle_started_utc || history[0].utc);
        const elapsedHours = (Math.max(0, Date.now() - startMs) / 3600000).toFixed(1);

        const queue = trainingState.queue || [];
        const pairsDone = trainingState.pairs_done || [];
        const waitingPairs = queue.filter(p => !pairsDone.includes(p) && p !== activePair);
        let queueStr = '';
        if (waitingPairs.length > 0) {
          const queueTotalHours = ((remMin + (waitingPairs.length * stepsTarget / rate)) / 60).toFixed(1);
          queueStr = ` · Queue: ${waitingPairs.length} pairs waiting (~${queueTotalHours}h total)`;
        }

        etaInfo = {
          rate,
          rateStr: `${Math.round(rate).toLocaleString()} steps/min`,
          etaStr: `~${etaHours} hours`,
          etaHours: parseFloat(etaHours),
          elapsedStr: `${elapsedHours}h ${trainingState.cycle_started_utc ? 'elapsed' : 'since first measured checkpoint'}`,
          finishStr: finishStr,
          queueStr
        };
      }
    }

    root.innerHTML = `
      <!-- TRAINING STATUS BANNER CARD -->
      <div class="card">
        <div class="card-header">
          <div>
            <div class="card-title">Reinforcement Learning Scalper Training (PPO v2)</div>
            <div style="font-size:12px; color:var(--text-2); margin-top:2px;">
              62-dimensional causal observation schema · 8 discrete execution actions · Walk-forward 70/15/15 validation
            </div>
          </div>
          <div>
            <span class="badge ${isTraining ? 'badge-warning' : isLocked ? 'badge-warning' : 'badge-muted'}">
              ${isTraining ? 'Training Active' : isLocked ? 'Training Queue Busy' : 'Engine Idle'}
            </span>
          </div>
        </div>

        ${
          isTraining
            ? `
              <div style="background:var(--bg-input); padding:16px; border-radius:var(--radius); border:1px solid var(--border);">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                  <div style="font-size:14px; font-weight:700;">
                    Active Pair: <span style="color:var(--accent);">${activePair}</span>
                  </div>
                  <div class="tabular" style="font-size:12px; color:var(--text-2);">
                    ${stepsDone.toLocaleString()} / ${stepsTarget.toLocaleString()} steps (${progressPct}%)
                  </div>
                </div>
                <div style="background:var(--bg-card); height:8px; border-radius:4px; overflow:hidden; border:1px solid var(--border);">
                  <div style="background:var(--accent); width:${progressPct}%; height:100%; transition:width 0.4s ease;"></div>
                </div>
                <div style="display:flex; justify-content:space-between; flex-wrap:wrap; gap:8px; margin-top:10px; font-size:11px; color:var(--text-3);">
                  <span id="training-throughput">Throughput: <strong style="color:var(--text);">${etaInfo.rateStr}</strong> (${etaInfo.elapsedStr})</span>
                  <span id="training-eta">Remaining at checkpoint: <strong style="color:var(--text);">${etaInfo.etaStr}</strong> · Est. Finish: <strong style="color:var(--text);">${etaInfo.finishStr}</strong>${etaInfo.queueStr}</span>
                </div>
              </div>
            `
            : isLocked
            ? `
              <div style="background:var(--warning-dim); border:1px solid var(--warning); padding:14px; border-radius:var(--radius); color:var(--warning); font-size:13px; font-weight:600;">
                Training busy flag active (${settings.training_lock_reason || 'training queued'}). This flag does not pause or stop live trading.
              </div>
            `
            : `
              <div style="color:var(--text-2); font-size:13px; padding:8px 0;">
                No training run currently executing. Select ready pairs below and dispatch a training cycle.
              </div>
            `
        }

        <div style="display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:12px; margin-top:20px; padding-top:16px; border-top:1px solid var(--border);">
          <div style="display:flex; gap:8px;">
            <button id="schedule-training-btn" class="btn btn-primary">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="5 3 19 12 5 21 5 3"/></svg>
              <span>Schedule Training for Selected</span>
            </button>
            <button id="toggle-lock-btn" class="btn btn-ghost btn-sm">
              ${isLocked ? 'Clear Training Lock' : 'Engage Training Lock'}
            </button>
          </div>
          <div style="font-size:11px; color:var(--text-3);">
            Manual starts only · Existing owner-started cycles may resume automatically
          </div>
        </div>
      </div>

      <!-- 13 FOREX PAIRS GRID -->
      <div class="card">
        <div class="card-header">
          <div class="card-title">Forex Major & Cross Pairs (13)</div>
          <span style="font-size:12px; color:var(--text-2);">HistData M1 Historical Ingestion</span>
        </div>

        <div class="grid-3">
          ${FOREX_PAIRS.map(pair => renderPairCard(pair, false)).join('')}
        </div>
      </div>

      <!-- SYNTHETICS GRID -->
      <div class="card">
        <div class="card-header">
          <div class="card-title">Deriv Synthetic Volatility Indices (10)</div>
          <span style="font-size:12px; color:var(--text-2);">Continuous 24/7 Tick/Bar History</span>
        </div>

        <div class="grid-3">
          ${SYNTHETICS.map(sym => renderPairCard(sym, true)).join('')}
        </div>
      </div>
    `;

    bindEvents();

    if (isTraining) {
      startPoll(async () => {
        try {
          const trSt = await api.getTraining();
          trainingState = trSt || {};
          render();
        } catch(_) {}
      }, 30000);
    } else {
      stopPoll();
    }
  }

  function renderPairCard(pair, isSynthetic) {
    const symbolKey = isSynthetic ? pair : `frx${pair}`;
    const pairData = dataIndex[symbolKey] || dataIndex[pair] || {};
    const rows = pairData.rows || pairData.total_rows || 0;
    const isDataReady = rows > 0;

    // Check models index for model verdict
    const model = modelsIndex[pair] || modelsIndex[symbolKey] || {};
    const hasModel = !!model.verdict || !!model.bundle_url;
    const verdict = model.verdict || (hasModel ? 'pass' : 'untrained');
    const isCurrentlyActive = (trainingState.active_pair === pair);

    let trainChip = 'badge-muted';
    let trainText = 'Untrained';

    if (verdict === 'retired') {
      trainChip = 'badge-muted';
      trainText = 'Retired, incompatible';
    } else if (isCurrentlyActive && trainingState.status === 'training') {
      trainChip = 'badge-warning';
      trainText = 'Training...';
    } else if (verdict === 'pass') {
      trainChip = 'badge-profit';
      trainText = 'Trained (Pass)';
    } else if (verdict === 'no_edge') {
      trainChip = 'badge-warning';
      trainText = 'No Edge';
    } else if (trainingState.queue && trainingState.queue.includes(pair)) {
      trainChip = 'badge-muted';
      trainText = 'Queued';
    }

    // H3 metrics for pair
    const isThisActive = (trainingState.active_pair === pair);
    const stepsDone = isThisActive ? (trainingState.total_steps_done || 0) : (model.steps || (verdict === 'pass' ? 5000000 : 0));
    const bestCp = (isThisActive && trainingState.best_checkpoint) ? trainingState.best_checkpoint : null;
    const holdoutLooks = (isThisActive && trainingState.holdout_looks !== undefined) ? trainingState.holdout_looks : (model.holdout_looks || 0);
    const releaseDecision = (isThisActive && trainingState.release_decision) ? trainingState.release_decision : (model.release_decision || (verdict === 'pass' ? 'Released' : verdict === 'no_edge' ? 'No proven edge, not released' : 'Pending 5M steps'));
    const lastDataDate = pairData.last_date || pairData.end_date || 'latest';

    return `
      <div style="background:var(--bg-card-sub); border:1px solid var(--border); border-radius:var(--radius); padding:14px; display:flex; flex-direction:column; justify-content:space-between; gap:12px;">
        <div style="display:flex; align-items:flex-start; justify-content:space-between; gap:8px;">
          <div>
            <div style="display:flex; align-items:center; gap:8px;">
              <input
                type="checkbox"
                class="pair-select-checkbox"
                data-pair="${pair}"
                data-has-data="${isDataReady}"
                ${isDataReady ? 'checked' : ''}
              />
              <span style="font-weight:700; font-size:15px; color:var(--text);">${pair}</span>
            </div>
            <div class="tabular" style="font-size:11px; color:var(--text-3); margin-top:4px;">
              ${rows > 0 ? `${rows.toLocaleString()} bars ready` : 'No local M1 bars'}
            </div>
          </div>

          <div style="display:flex; flex-direction:column; align-items:flex-end; gap:4px;">
            <span class="badge ${isDataReady ? 'badge-profit' : 'badge-loss'}">
              ${isDataReady ? 'Ready ✓' : 'No Data ✗'}
            </span>
            <span class="badge ${trainChip}">
              ${trainText}
            </span>
          </div>
        </div>

        <!-- H3 Training & Evaluation Stats -->
        <div style="font-size:11px; color:var(--text-2); background:var(--bg-input); padding:10px; border-radius:var(--radius-sm); border:1px solid var(--border-sub); display:flex; flex-direction:column; gap:4px;">
          <div style="display:flex; justify-content:space-between;">
            <span>Training Progress:</span>
            <strong class="tabular" style="color:var(--text);">${stepsDone.toLocaleString()} / 5,000,000 steps</strong>
          </div>
          ${
            bestCp
              ? `
                <div style="display:flex; justify-content:space-between;">
                  <span>Best Val Score:</span>
                  <strong class="tabular" style="color:var(--profit);">${bestCp.score} (step ${bestCp.step.toLocaleString()})</strong>
                </div>
              `
              : (model.sharpe_annualized !== undefined)
              ? `
                <div style="display:flex; justify-content:space-between;">
                  <span>Val Sharpe / Return:</span>
                  <strong class="tabular" style="color:var(--text);">${model.sharpe_annualized} (+${model.total_return_pct || 0}%)</strong>
                </div>
              `
              : `
                <div style="display:flex; justify-content:space-between;">
                  <span>Val Score:</span>
                  <span style="color:var(--text-3); font-style:italic;">evaluating at checkpoints</span>
                </div>
              `
          }
          <div style="display:flex; justify-content:space-between;">
            <span>Hold-out Looks:</span>
            <strong class="tabular" style="color:var(--text);">${holdoutLooks}</strong>
          </div>
          <div style="display:flex; justify-content:space-between; gap:6px;">
            <span>Release Decision:</span>
            <span style="color:${verdict === 'pass' ? 'var(--profit)' : verdict === 'no_edge' ? 'var(--warning)' : 'var(--text-3)'}; font-weight:600; text-align:right;">
              ${releaseDecision}
            </span>
          </div>
          <div style="display:flex; justify-content:space-between; margin-top:2px; font-size:10px; color:var(--text-3);">
            <span>Data Pool:</span>
            <span>Up to ${lastDataDate}</span>
          </div>
        </div>

        <div style="display:flex; align-items:center; justify-content:space-between; font-size:11px; color:var(--text-3); pt-1;">
          <span>${isSynthetic ? 'Synthetic CFD' : 'Forex Major/Cross'}</span>
          <button
            class="btn btn-ghost btn-sm single-train-btn"
            data-pair="${pair}"
            style="padding:2px 8px; font-size:11px; height:26px;"
          >
            Update Training (${pair})
          </button>
        </div>
      </div>
    `;
  }

  function bindEvents() {
    // Schedule training for all selected
    const scheduleBtn = document.getElementById('schedule-training-btn');
    if (scheduleBtn) {
      scheduleBtn.addEventListener('click', async () => {
        const checkboxes = Array.from(document.querySelectorAll('.pair-select-checkbox:checked'));
        const selectedPairs = checkboxes.map(cb => cb.dataset.pair);

        if (selectedPairs.length === 0) {
          toast('Please select at least one pair to train', 'warn');
          return;
        }

        scheduleBtn.disabled = true;
        scheduleBtn.textContent = 'Scheduling...';

        try {
          // 1. Set training lock via worker
          await api.setTrainLock(true, `user_scheduled: ${selectedPairs.join(',')}`);

          // 2. Dispatch train workflow
          await api.dispatchWorkflow('train.yml', {
            mode: 'start',
            pair: selectedPairs[0],
            queue: selectedPairs.join(',')
          });

          toast('Training dispatched. Live trading is not paused by training.', 'success');
          loadData();
        } catch(err) {
          toast(err.message || 'Failed to dispatch training workflow', 'error');
          scheduleBtn.disabled = false;
          scheduleBtn.textContent = 'Schedule Training for Selected';
        }
      });
    }

    // Single train buttons
    document.querySelectorAll('.single-train-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        const pair = btn.dataset.pair;
        if (!confirm(`Start training RL Scalper model for ${pair}?`)) return;

        try {
          await api.setTrainLock(true, `manual_train_${pair}`);
          await api.dispatchWorkflow('train.yml', {
            mode: 'start',
            pair: pair
          });
          toast(`Training dispatched for ${pair}!`, 'success');
          loadData();
        } catch(err) {
          toast(err.message || 'Error dispatching training', 'error');
        }
      });
    });

    // Toggle training lock button
    const toggleLockBtn = document.getElementById('toggle-lock-btn');
    if (toggleLockBtn) {
      toggleLockBtn.addEventListener('click', async () => {
        const currentLocked = !!settings.training_locked;
        try {
          await api.setTrainLock(!currentLocked, currentLocked ? '' : 'manual_lock');
          toast(`Training lock ${currentLocked ? 'cleared' : 'engaged'}`, 'info');
          loadData();
        } catch(err) {
          toast(err.message, 'error');
        }
      });
    }
  }

  loadData();
}
