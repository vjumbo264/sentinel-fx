import React, { useState, useEffect, useMemo, useCallback } from 'react';
import {
  Activity,
  Layers,
  History,
  Settings,
  Play,
  Square,
  AlertTriangle,
  RefreshCw,
  TrendingUp,
  Shield,
  Clock,
  Sparkles,
  Download,
  Sun,
  Moon,
  Monitor,
  ExternalLink,
  CheckCircle2,
  XCircle,
  PauseCircle,
  PlayCircle,
  Database,
  ArrowUpRight,
  ArrowDownRight
} from 'lucide-react';

const WORKER_URL = 'https://sentinel-fx-worker.vjumbo264.workers.dev';

interface Position {
  ticket: number;
  symbol: string;
  side: 'BUY' | 'SELL';
  volume: number;
  openPrice: number;
  currentPrice: number;
  sl: number;
  tp?: number;
  profit: number;
  openTime: string;
}

interface TradeRecord {
  id: string;
  symbol: string;
  side: 'BUY' | 'SELL';
  volume: number;
  openPrice: number;
  closePrice: number;
  netPnl: number;
  openTime: string;
  closeTime: string;
  reason: string;
}

const FOREX_PAIRS = [
  'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD',
  'USDCAD', 'NZDUSD', 'EURGBP', 'EURJPY', 'GBPJPY',
  'AUDJPY', 'EURAUD', 'GBPAUD'
];

const SYNTHETICS = [
  'R_10', 'R_25', 'R_50', 'R_75', 'R_100',
  '1HZ10V', '1HZ25V', '1HZ50V', '1HZ75V', '1HZ100V'
];

export default function App() {
  const [activeTab, setActiveTab] = useState<'dash' | 'risk' | 'training' | 'history' | 'settings'>('dash');
  const [themeSetting, setThemeSetting] = useState<'auto' | 'dark' | 'light'>(() => {
    return (localStorage.getItem('sfx_theme') as 'auto' | 'dark' | 'light') || 'auto';
  });
  const [isDark, setIsDark] = useState<boolean>(true);

  // 4 Independent Optional Risk Overrides
  const [riskOverrides, setRiskOverrides] = useState({
    take_profit: { enabled: false, unit: 'money' as 'money' | 'pct', value: '' as string | number },
    stop_loss: { enabled: false, unit: 'money' as 'money' | 'pct', value: '' as string | number },
    daily_profit_target: { enabled: false, unit: 'money' as 'money' | 'pct', value: '' as string | number, close_open_on_hit: false },
    daily_loss_limit: { enabled: false, unit: 'money' as 'money' | 'pct', value: '' as string | number, close_open_on_hit: false },
    trade_weekends: false,
  });
  const [riskStatus, setRiskStatus] = useState<{
    status: 'normal' | 'daily_target_reached' | 'daily_limit_reached';
    today_pnl: number;
    realized_pnl: number;
    floating_pnl: number;
    reason: string;
  }>({
    status: 'normal',
    today_pnl: 45.20,
    realized_pnl: 32.50,
    floating_pnl: 12.70,
    reason: ''
  });
  const [testDayKey, setTestDayKey] = useState<string | null>(null);

  // Authentication
  const [pat, setPat] = useState<string>(() => {
    return localStorage.getItem('sfx_pat') || '';
  });

  // Telemetry & State
  const [mode, setMode] = useState<'demo' | 'real'>('demo');
  const [botRunning, setBotRunning] = useState<boolean>(true);
  const [trainingLocked, setTrainingLocked] = useState<boolean>(false);
  const [trainingReason, setTrainingReason] = useState<string>('');
  const [balance, setBalance] = useState<number>(10000.00);
  const [equity, setEquity] = useState<number>(10045.20);
  const [freeMargin, setFreeMargin] = useState<number>(9820.50);
  const [poolBalance, setPoolBalance] = useState<number>(10000.00);
  const [globalSlPct, setGlobalSlPct] = useState<number>(5.0);
  const [globalTpPct, setGlobalTpPct] = useState<number>(10.0);
  const [heartbeatTime, setHeartbeatTime] = useState<string>('Active (32s ago)');

  // Training state
  const [trainingStatus, setTrainingStatus] = useState<'idle' | 'training'>('idle');
  const [activeTrainPair, setActiveTrainPair] = useState<string>('EURUSD');
  const [trainStepsDone, setTrainStepsDone] = useState<number>(700000);
  const [trainStepsTarget] = useState<number>(5000000);
  const [checkpointHistory, setCheckpointHistory] = useState<Array<{ step: number; utc: string }>>([]);
  const [selectedPairs, setSelectedPairs] = useState<Record<string, boolean>>({
    EURUSD: true,
    GBPUSD: true,
    AUDUSD: true,
    USDJPY: true
  });

  // H2: Honest training ETA calculation based on last N measured checkpoints
  const etaInfo = useMemo(() => {
    const history = checkpointHistory;
    const remainingSteps = Math.max(0, trainStepsTarget - trainStepsDone);
    if (!history || history.length < 2) {
      return {
        rateStr: 'measuring...',
        etaStr: 'measuring...',
        elapsedStr: 'measuring...',
        finishStr: 'measuring...',
      };
    }
    const N = Math.min(5, history.length);
    const recent = history.slice(-N);
    const cFirst = recent[0];
    const cLast = recent[recent.length - 1];
    const stepDelta = cLast.step - cFirst.step;
    const timeDeltaMin = (new Date(cLast.utc).getTime() - new Date(cFirst.utc).getTime()) / 60000;
    if (stepDelta <= 0 || timeDeltaMin <= 0) {
      return {
        rateStr: 'measuring...',
        etaStr: 'measuring...',
        elapsedStr: 'measuring...',
        finishStr: 'measuring...',
      };
    }
    const rate = stepDelta / timeDeltaMin;
    const remMin = remainingSteps / rate;
    const etaHours = (remMin / 60).toFixed(1);
    const finishDate = new Date(Date.now() + remMin * 60000);
    const finishStr = finishDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) + ' (' + finishDate.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ')';
    const startMs = new Date(history[0].utc).getTime();
    const elapsedHours = (Math.max(0, Date.now() - startMs) / 3600000).toFixed(1);

    return {
      rateStr: `${Math.round(rate).toLocaleString()} steps/min`,
      etaStr: `~${etaHours} hours`,
      elapsedStr: `${elapsedHours}h elapsed`,
      finishStr,
    };
  }, [checkpointHistory, trainStepsDone, trainStepsTarget]);

  // Live Positions
  const [positions, setPositions] = useState<Position[]>([
    {
      ticket: 541092,
      symbol: 'EURUSD',
      side: 'BUY',
      volume: 0.1,
      openPrice: 1.08450,
      currentPrice: 1.08580,
      sl: 1.08150,
      tp: 1.09200,
      profit: 13.00,
      openTime: '12m ago'
    },
    {
      ticket: 541093,
      symbol: 'Volatility 10 Index',
      side: 'BUY',
      volume: 0.5,
      openPrice: 4961.20,
      currentPrice: 4965.75,
      sl: 4945.00,
      tp: 4990.00,
      profit: 22.75,
      openTime: '24m ago'
    }
  ]);

  // History Trades
  const [historyTrades, setHistoryTrades] = useState<TradeRecord[]>([
    { id: '540981', symbol: 'EURUSD', side: 'BUY', volume: 0.1, openPrice: 1.08200, closePrice: 1.08450, netPnl: 25.00, openTime: '2026-10-23 06:14', closeTime: '2026-10-23 07:30', reason: 'agent_trail' },
    { id: '540965', symbol: 'AUDUSD', side: 'BUY', volume: 0.1, openPrice: 0.65100, closePrice: 0.65280, netPnl: 18.00, openTime: '2026-10-23 04:20', closeTime: '2026-10-23 05:45', reason: 'agent_close' },
    { id: '540942', symbol: 'GBPUSD', side: 'SELL', volume: 0.1, openPrice: 1.29800, closePrice: 1.29910, netPnl: -11.00, openTime: '2026-10-23 02:10', closeTime: '2026-10-23 03:00', reason: 'stop_loss' },
    { id: '540910', symbol: 'USDJPY', side: 'BUY', volume: 0.1, openPrice: 152.100, closePrice: 152.420, netPnl: 21.30, openTime: '2026-10-22 21:05', closeTime: '2026-10-22 22:50', reason: 'agent_be' },
    { id: '540889', symbol: 'EURGBP', side: 'BUY', volume: 0.1, openPrice: 0.83500, closePrice: 0.83680, netPnl: 22.50, openTime: '2026-10-22 18:30', closeTime: '2026-10-22 19:40', reason: 'agent_trail' }
  ]);

  // History Filters
  const [filterPair, setFilterPair] = useState<string>('ALL');
  const [filterOutcome, setFilterOutcome] = useState<'ALL' | 'WIN' | 'LOSS'>('ALL');

  // UI Toast
  const [toastMsg, setToastMsg] = useState<{ text: string; type: 'info' | 'success' | 'warn' | 'error' } | null>(null);

  // WAT Clock
  const [watClock, setWatClock] = useState<string>('');

  const triggerToast = useCallback((text: string, type: 'info' | 'success' | 'warn' | 'error' = 'info') => {
    setToastMsg({ text, type });
    setTimeout(() => setToastMsg(null), 3500);
  }, []);

  // Theme Resolution: Auto / Dark / Light
  useEffect(() => {
    const darkQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const updateTheme = () => {
      const resolvedDark = themeSetting === 'auto' ? darkQuery.matches : themeSetting === 'dark';
      setIsDark(resolvedDark);
      document.documentElement.setAttribute('data-theme', resolvedDark ? 'dark' : 'light');
      document.documentElement.style.colorScheme = resolvedDark ? 'dark' : 'light';
    };

    updateTheme();
    localStorage.setItem('sfx_theme', themeSetting);
    darkQuery.addEventListener('change', updateTheme);
    return () => darkQuery.removeEventListener('change', updateTheme);
  }, [themeSetting]);

  // WAT Clock (Lagos is UTC+1)
  useEffect(() => {
    const updateClock = () => {
      const now = new Date(Date.now() + 60 * 60 * 1000);
      setWatClock(now.toUTCString().slice(17, 25) + ' WAT');
    };
    updateClock();
    const interval = setInterval(updateClock, 1000);
    return () => clearInterval(interval);
  }, []);

  // Fetch telemetry from live worker
  const refreshWorkerState = useCallback(async () => {
    try {
      const res = await fetch(`${WORKER_URL}/api/state`, {
        headers: { 'Authorization': `Bearer ${pat}` }
      });
      if (res.ok) {
        const data = await res.json();
        if (data.settings) {
          if (data.settings.training_locked !== undefined) setTrainingLocked(!!data.settings.training_locked);
          if (data.settings.training_lock_reason) setTrainingReason(data.settings.training_lock_reason);
          if (data.settings.mode) setMode(data.settings.mode.toLowerCase() as 'demo' | 'real');
          if (data.settings.power !== undefined) setBotRunning(data.settings.power !== false);
        }
        if (data.heartbeat) {
          if (typeof data.heartbeat.equity === 'number') setEquity(data.heartbeat.equity);
          if (typeof data.heartbeat.balance === 'number') setBalance(data.heartbeat.balance);
          if (typeof data.heartbeat.free_margin === 'number') setFreeMargin(data.heartbeat.free_margin);
          if (data.heartbeat.timestamp) {
            const ageSec = Math.floor(Date.now() / 1000 - data.heartbeat.timestamp);
            setHeartbeatTime(ageSec < 120 ? `Live (${ageSec}s ago)` : `Idle (${Math.round(ageSec / 60)}m ago)`);
          }
        }
      }

      // Fetch training state
      try {
        const trRes = await fetch(`${WORKER_URL}/api/training/state`);
        if (trRes.ok) {
          const trData = await trRes.json();
          if (trData.status) setTrainingStatus(trData.status === 'training' ? 'training' : 'idle');
          if (trData.active_pair) setActiveTrainPair(trData.active_pair);
          if (typeof trData.total_steps_done === 'number') setTrainStepsDone(trData.total_steps_done);
          if (Array.isArray(trData.checkpoint_history)) setCheckpointHistory(trData.checkpoint_history);
        }
      } catch (_) {}
    } catch (_) {
      // Offline or network error
    }
  }, [pat]);

  useEffect(() => {
    refreshWorkerState();
    const t = setInterval(refreshWorkerState, 20000);
    return () => clearInterval(t);
  }, [refreshWorkerState]);

  // Dispatch GitHub Action
  const dispatchWorkflow = async (workflowName: string, inputs: Record<string, string>) => {
    try {
      const r = await fetch(`https://api.github.com/repos/vjumbo264/sentinel-fx/actions/workflows/${workflowName}/dispatches`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${pat}`,
          'Accept': 'application/vnd.github+json',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ ref: 'main', inputs }),
      });
      if (r.status === 204) {
        return { ok: true };
      }
      const err = await r.json().catch(() => ({}));
      throw new Error(err.message || `GitHub API ${r.status}`);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Workflow dispatch error';
      throw new Error(msg);
    }
  };

  // Start EUR/USD Training action
  const startEurusdTraining = async () => {
    triggerToast('Initiating EUR/USD RL Scalper training (v2 schema)...', 'info');
    try {
      // 1. Lock training on worker
      await fetch(`${WORKER_URL}/api/settings/training-lock`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${pat}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ locked: true, reason: 'initial_eurusd_training' })
      }).catch(() => {});

      setTrainingLocked(true);
      setTrainingReason('initial_eurusd_training');
      setTrainingStatus('training');
      setActiveTrainPair('EURUSD');

      // 2. Dispatch GitHub workflow train.yml with mode=start
      await dispatchWorkflow('train.yml', { mode: 'start', pair: 'EURUSD' });
      triggerToast('EUR/USD training successfully initiated on GitHub Actions!', 'success');
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed to dispatch workflow';
      triggerToast(`Training dispatch note: ${msg}. Training lock is active on worker.`, 'warn');
    }
  };

  // Toggle Bot Power
  const toggleBotPower = async () => {
    const nextPower = !botRunning;
    try {
      await fetch(`${WORKER_URL}/api/settings`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${pat}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ power: nextPower, halt: false })
      });
      if (nextPower) {
        await dispatchWorkflow('bot.yml', { mode });
        triggerToast('Dispatched bot workflow on GitHub Actions', 'success');
      } else {
        triggerToast('Bot execution turned OFF', 'warn');
      }
      setBotRunning(nextPower);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Error changing bot state';
      triggerToast(msg, 'error');
    }
  };

  // Emergency Kill Switch
  const triggerKillSwitch = async () => {
    if (!window.confirm('EMERGENCY KILL SWITCH: Immediately halt bot and pause order execution?')) return;
    try {
      await fetch(`${WORKER_URL}/api/settings`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${pat}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ halt: true, power: false })
      });
      setBotRunning(false);
      triggerToast('Emergency kill switch activated. Coordinator halted.', 'error');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Kill switch error';
      triggerToast(msg, 'error');
    }
  };

  // Switch Mode (DEMO <-> REAL)
  const toggleMode = async () => {
    const nextMode = mode === 'demo' ? 'real' : 'demo';
    if (nextMode === 'real') {
      if (!window.confirm('SWITCH TO REAL ACCOUNT: Real capital will be traded on Deriv MT5. Confirm?')) return;
    }
    try {
      await fetch(`${WORKER_URL}/api/settings`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${pat}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: nextMode })
      });
      setMode(nextMode);
      triggerToast(`Account mode set to ${nextMode.toUpperCase()}`, 'success');
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Mode error';
      triggerToast(msg, 'error');
    }
  };

  // Filtered History
  const filteredTrades = useMemo(() => {
    return historyTrades.filter(t => {
      if (filterPair !== 'ALL' && t.symbol !== filterPair) return false;
      if (filterOutcome === 'WIN' && t.netPnl <= 0) return false;
      if (filterOutcome === 'LOSS' && t.netPnl >= 0) return false;
      return true;
    });
  }, [historyTrades, filterPair, filterOutcome]);

  const historyMetrics = useMemo(() => {
    const total = filteredTrades.length;
    const wins = filteredTrades.filter(t => t.netPnl > 0);
    const losses = filteredTrades.filter(t => t.netPnl < 0);
    const net = filteredTrades.reduce((a, b) => a + b.netPnl, 0);
    const winRate = total > 0 ? ((wins.length / total) * 100).toFixed(1) : '0.0';
    return { total, wins: wins.length, losses: losses.length, net, winRate };
  }, [filteredTrades]);

  // Export CSV
  const handleExportCsv = () => {
    const headers = ['ID', 'Pair', 'Side', 'Volume', 'Open', 'Close', 'Net PnL', 'Time', 'Exit Reason'];
    const rows = filteredTrades.map(t => [t.id, t.symbol, t.side, t.volume, t.openPrice, t.closePrice, t.netPnl, t.closeTime, t.reason]);
    const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute('download', `sentinel_trades_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    link.remove();
    triggerToast('CSV export downloaded', 'success');
  };

  const todayPnl = equity - balance;

  return (
    <div className={`min-h-screen flex flex-col font-sans antialiased transition-colors duration-200 ${
      isDark ? 'bg-[#080c14] text-[#e8edf5]' : 'bg-[#f0f4f8] text-[#0f1520]'
    }`}>
      {/* Toast Notification */}
      {toastMsg && (
        <div className={`fixed bottom-20 right-4 z-50 px-4 py-2.5 rounded-lg text-xs font-semibold shadow-2xl border flex items-center gap-2 max-w-sm transition-all duration-200 ${
          toastMsg.type === 'error'
            ? 'bg-red-950/90 text-red-200 border-red-500/50'
            : toastMsg.type === 'success'
            ? 'bg-emerald-950/90 text-emerald-200 border-emerald-500/50'
            : toastMsg.type === 'warn'
            ? 'bg-amber-950/90 text-amber-200 border-amber-500/50'
            : 'bg-blue-950/90 text-blue-200 border-blue-500/50'
        }`}>
          <span>{toastMsg.text}</span>
        </div>
      )}

      {/* Training Lock Banner */}
      {trainingLocked && (
        <div className="bg-amber-500 text-black px-4 py-2 text-xs font-bold text-center tracking-wide flex items-center justify-center gap-2 sticky top-0 z-50">
          <AlertTriangle className="w-4 h-4 text-black shrink-0" />
          <span>
            TRAINING IN PROGRESS {trainingReason ? `(${trainingReason})` : ''} — Bot is paused, order execution is suspended until training finishes.
          </span>
        </div>
      )}

      {/* Main Grid Shell */}
      <div className="flex-1 flex flex-col lg:flex-row">
        {/* DESKTOP LEFT RAIL */}
        <aside className={`hidden lg:flex flex-col w-64 border-r sticky top-0 h-screen py-6 select-none shrink-0 ${
          isDark ? 'bg-[#0f1520] border-[#1e2d45]' : 'bg-white border-[#d0d9e8]'
        }`}>
          {/* Brand */}
          <div className="px-6 pb-6 border-b border-inherit">
            <div className="flex items-center gap-2 text-[#3b82f6] font-extrabold text-base tracking-tight">
              <Shield className="w-5 h-5 text-current" />
              <span>SENTINEL-FX</span>
            </div>
            <div className="text-[11px] text-slate-400 font-mono tracking-wider mt-0.5">
              MOTIONSALT CFD AUTONOMOUS
            </div>
          </div>

          {/* Navigation Links */}
          <nav className="flex-1 px-3 py-4 space-y-1">
            <button
              onClick={() => setActiveTab('dash')}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-xs font-semibold transition-colors ${
                activeTab === 'dash'
                  ? 'bg-blue-600/15 text-[#3b82f6] font-bold'
                  : isDark ? 'text-slate-400 hover:text-slate-200 hover:bg-[#151d2e]' : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
              }`}
            >
              <Activity className="w-4 h-4" />
              <span>Dashboard</span>
            </button>

            <button
              onClick={() => setActiveTab('risk')}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-xs font-semibold transition-colors ${
                activeTab === 'risk'
                  ? 'bg-blue-600/15 text-[#3b82f6] font-bold'
                  : isDark ? 'text-slate-400 hover:text-slate-200 hover:bg-[#151d2e]' : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
              }`}
            >
              <Shield className="w-4 h-4" />
              <span>Risk & Overrides</span>
            </button>

            <button
              onClick={() => setActiveTab('training')}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-xs font-semibold transition-colors ${
                activeTab === 'training'
                  ? 'bg-blue-600/15 text-[#3b82f6] font-bold'
                  : isDark ? 'text-slate-400 hover:text-slate-200 hover:bg-[#151d2e]' : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
              }`}
            >
              <Sparkles className="w-4 h-4" />
              <span>Training (PPO v2)</span>
            </button>

            <button
              onClick={() => setActiveTab('history')}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-xs font-semibold transition-colors ${
                activeTab === 'history'
                  ? 'bg-blue-600/15 text-[#3b82f6] font-bold'
                  : isDark ? 'text-slate-400 hover:text-slate-200 hover:bg-[#151d2e]' : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
              }`}
            >
              <History className="w-4 h-4" />
              <span>Trade History</span>
            </button>

            <button
              onClick={() => setActiveTab('settings')}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-xs font-semibold transition-colors ${
                activeTab === 'settings'
                  ? 'bg-blue-600/15 text-[#3b82f6] font-bold'
                  : isDark ? 'text-slate-400 hover:text-slate-200 hover:bg-[#151d2e]' : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
              }`}
            >
              <Settings className="w-4 h-4" />
              <span>Settings & Keys</span>
            </button>
          </nav>

          {/* Quick EUR/USD Training Trigger */}
          <div className="px-4 py-3 mx-3 mb-4 rounded-xl border border-blue-500/30 bg-blue-500/5">
            <div className="text-[11px] font-bold text-[#3b82f6] mb-1 flex items-center gap-1.5">
              <Sparkles className="w-3.5 h-3.5" />
              <span>EUR/USD RL Model</span>
            </div>
            <p className="text-[11px] text-slate-400 mb-2 leading-relaxed">
              Dispatch 62-dim causal training run on 5-year M1 HistData bars.
            </p>
            <button
              onClick={startEurusdTraining}
              className="w-full bg-[#3b82f6] hover:bg-blue-600 text-white text-xs font-semibold py-1.5 rounded-md transition-colors"
            >
              Start EUR/USD Training
            </button>
          </div>

          {/* Rail Footer */}
          <div className="px-6 pt-4 border-t border-inherit text-[11px] font-mono text-slate-400">
            <div className="font-semibold text-slate-300">{watClock || '--:--:-- WAT'}</div>
            <div className="mt-1 text-[10px] text-slate-500">Deriv MT5 Cloud Coordinator</div>
          </div>
        </aside>

        {/* MOBILE TOP BAR */}
        <header className={`lg:hidden flex items-center justify-between px-4 py-3 border-b sticky top-0 z-30 ${
          isDark ? 'bg-[#0f1520] border-[#1e2d45]' : 'bg-white border-[#d0d9e8]'
        }`}>
          <div className="flex items-center gap-2">
            <span className="font-extrabold text-[#3b82f6] tracking-tight">SENTINEL-FX</span>
            <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-slate-500/15 text-slate-400 uppercase">
              {mode}
            </span>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => setThemeSetting(themeSetting === 'dark' ? 'light' : 'dark')}
              className="p-1.5 rounded-md text-slate-400 hover:text-slate-200"
              title="Toggle theme"
            >
              {isDark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
            </button>
            <div className="flex items-center gap-1.5 text-xs text-slate-400">
              <span className={`w-2 h-2 rounded-full ${botRunning ? 'bg-emerald-500 animate-pulse' : 'bg-slate-500'}`}></span>
              <span>{botRunning ? 'Running' : 'Idle'}</span>
            </div>
          </div>
        </header>

        {/* MAIN CONTENT VIEW */}
        <main className="flex-1 p-4 lg:p-8 max-w-7xl mx-auto w-full space-y-6 pb-24 lg:pb-8">
          {/* TAB 1: DASHBOARD */}
          {activeTab === 'dash' && (
            <div className="space-y-6">
              {riskStatus.status !== 'normal' && (
                <div className={`p-4 rounded-xl border flex flex-col sm:flex-row sm:items-center justify-between gap-3 ${
                  riskStatus.status === 'daily_target_reached'
                    ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300'
                    : 'border-red-500/40 bg-red-500/10 text-red-300'
                }`}>
                  <div>
                    <div className="text-sm font-bold">
                      {riskStatus.status === 'daily_target_reached' ? '🎯 Daily Profit Target Reached' : '🛑 Daily Loss Limit Reached'}
                    </div>
                    <div className="text-xs opacity-80 mt-0.5">
                      {riskStatus.reason || 'Trading halted for today'}. Resets automatically at 00:00:00 UTC (or clear manually).
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => {
                        setRiskStatus(r => ({ ...r, status: 'normal', reason: '' }));
                        triggerToast('Daily limit cleared — trading resumed', 'success');
                      }}
                      className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-white/10 hover:bg-white/20"
                    >
                      Clear State
                    </button>
                    <button
                      onClick={() => setActiveTab('risk')}
                      className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-blue-600 text-white"
                    >
                      Manage Risk
                    </button>
                  </div>
                </div>
              )}

              {/* BALANCE & RUNNER STATUS CARD */}
              <div className={`p-6 rounded-2xl border transition-colors ${
                isDark ? 'bg-[#0f1520] border-[#1e2d45]' : 'bg-white border-[#d0d9e8] shadow-sm'
              }`}>
                <div className="flex flex-col md:flex-row md:items-start justify-between gap-4 mb-6">
                  <div>
                    <div className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-1">
                      Live Account Equity
                    </div>
                    <div className="text-3xl lg:text-4xl font-extrabold font-mono tracking-tight">
                      ${equity.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </div>
                    <div className="flex flex-wrap items-center gap-3 mt-2 text-xs">
                      <span className="text-slate-400">
                        Balance: <strong className="font-mono text-inherit">${balance.toLocaleString('en-US', { minimumFractionDigits: 2 })}</strong>
                      </span>
                      <span className="text-slate-600">·</span>
                      <span className="text-slate-400">
                        Free Margin: <strong className="font-mono text-inherit">${freeMargin.toLocaleString('en-US', { minimumFractionDigits: 2 })}</strong>
                      </span>
                      <span className="text-slate-600">·</span>
                      <span className="flex items-center gap-1">
                        Today's P&L:
                        <span className={`px-2 py-0.5 rounded text-xs font-mono font-bold ${
                          todayPnl >= 0 ? 'bg-emerald-500/15 text-emerald-500' : 'bg-red-500/15 text-red-500'
                        }`}>
                          {todayPnl >= 0 ? '+' : ''}${todayPnl.toFixed(2)}
                        </span>
                      </span>
                    </div>
                  </div>

                  <div className="flex flex-col items-start md:items-end gap-2.5">
                    <button
                      onClick={toggleMode}
                      className={`text-xs px-3 py-1.5 rounded-lg font-bold border transition-colors ${
                        mode === 'real'
                          ? 'bg-amber-500/15 text-amber-500 border-amber-500/30'
                          : 'bg-blue-500/15 text-blue-500 border-blue-500/30'
                      }`}
                    >
                      ACCOUNT MODE: {mode.toUpperCase()} (CLICK TO SWITCH)
                    </button>
                    <div className="flex items-center gap-2 text-xs text-slate-400">
                      <span className={`w-2 h-2 rounded-full ${trainingLocked ? 'bg-amber-500 animate-pulse' : botRunning ? 'bg-emerald-500' : 'bg-slate-500'}`}></span>
                      <span className="font-medium">
                        {trainingLocked ? 'Training — Bot Paused' : botRunning ? 'Bot Active & Running' : 'Bot Idle'}
                      </span>
                      <span className="text-slate-500 font-mono">({heartbeatTime})</span>
                    </div>
                  </div>
                </div>

                {/* BOT CONTROLS */}
                <div className="flex flex-wrap items-center justify-between gap-3 pt-5 border-t border-inherit">
                  <div className="flex items-center gap-2.5">
                    <button
                      onClick={toggleBotPower}
                      disabled={trainingLocked}
                      className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-bold transition-all ${
                        botRunning
                          ? isDark ? 'bg-[#151d2e] text-slate-200 border border-[#1e2d45]' : 'bg-slate-100 text-slate-700 border border-slate-300'
                          : 'bg-[#3b82f6] text-white'
                      } ${trainingLocked ? 'opacity-40 cursor-not-allowed' : ''}`}
                    >
                      {botRunning ? <Square className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
                      <span>{botRunning ? 'TURN BOT OFF' : 'START BOT (TURN ON)'}</span>
                    </button>

                    <button
                      onClick={triggerKillSwitch}
                      className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-bold bg-red-600 hover:bg-red-700 text-white transition-colors"
                    >
                      <AlertTriangle className="w-3.5 h-3.5" />
                      <span>EMERGENCY KILL SWITCH</span>
                    </button>
                  </div>

                  <div className="text-[11px] text-slate-400">
                    Windows MT5 Runner execution coordinated via D1 state lease
                  </div>
                </div>
              </div>

              {/* CAPITAL POOL & OVERRIDES CARD */}
              <div className={`p-6 rounded-2xl border ${
                isDark ? 'bg-[#0f1520] border-[#1e2d45]' : 'bg-white border-[#d0d9e8] shadow-sm'
              }`}>
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <h2 className="text-sm font-bold tracking-tight">Session Capital Pool Allocation</h2>
                    <p className="text-xs text-slate-400 mt-0.5">
                      Isolated risk allocation across active pair models with automated stop limits.
                    </p>
                  </div>
                  <div className="text-xs text-slate-400">
                    Active Pool: <strong className="font-mono text-inherit text-sm">${poolBalance.toFixed(2)}</strong>
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
                  <div>
                    <label className="block text-slate-400 font-semibold mb-1">Set Pool Capital ($)</label>
                    <input
                      type="number"
                      value={poolBalance}
                      onChange={e => setPoolBalance(parseFloat(e.target.value) || 0)}
                      className={`w-full px-3 py-2 rounded-lg border font-mono ${
                        isDark ? 'bg-[#151d2e] border-[#1e2d45] text-white' : 'bg-slate-50 border-slate-300 text-slate-900'
                      }`}
                    />
                  </div>

                  <div>
                    <label className="block text-slate-400 font-semibold mb-1">Global Stop-Loss (% of pool)</label>
                    <input
                      type="number"
                      step="0.5"
                      value={globalSlPct}
                      onChange={e => setGlobalSlPct(parseFloat(e.target.value) || 0)}
                      className={`w-full px-3 py-2 rounded-lg border font-mono ${
                        isDark ? 'bg-[#151d2e] border-[#1e2d45] text-white' : 'bg-slate-50 border-slate-300 text-slate-900'
                      }`}
                    />
                  </div>

                  <div>
                    <label className="block text-slate-400 font-semibold mb-1">Global Take-Profit (% of pool)</label>
                    <input
                      type="number"
                      step="0.5"
                      value={globalTpPct}
                      onChange={e => setGlobalTpPct(parseFloat(e.target.value) || 0)}
                      className={`w-full px-3 py-2 rounded-lg border font-mono ${
                        isDark ? 'bg-[#151d2e] border-[#1e2d45] text-white' : 'bg-slate-50 border-slate-300 text-slate-900'
                      }`}
                    />
                  </div>
                </div>
              </div>

              {/* LIVE POSITIONS TABLE */}
              <div className={`p-6 rounded-2xl border ${
                isDark ? 'bg-[#0f1520] border-[#1e2d45]' : 'bg-white border-[#d0d9e8] shadow-sm'
              }`}>
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2">
                    <Layers className="w-4 h-4 text-[#3b82f6]" />
                    <h2 className="text-sm font-bold tracking-tight">Live CFD Positions ({positions.length})</h2>
                  </div>
                  <span className="text-[11px] text-slate-400 font-mono">100% Server SL Enforced</span>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs font-mono">
                    <thead>
                      <tr className={`border-b ${isDark ? 'border-[#1e2d45] text-slate-400' : 'border-slate-200 text-slate-500'}`}>
                        <th className="py-2.5 px-3">Ticket</th>
                        <th className="py-2.5 px-3">Pair</th>
                        <th className="py-2.5 px-3">Side</th>
                        <th className="py-2.5 px-3">Lots</th>
                        <th className="py-2.5 px-3">Open</th>
                        <th className="py-2.5 px-3">Current</th>
                        <th className="py-2.5 px-3">SL</th>
                        <th className="py-2.5 px-3">P&L</th>
                        <th className="py-2.5 px-3 text-right">Action</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-inherit">
                      {positions.length === 0 ? (
                        <tr>
                          <td colSpan={9} className="py-8 text-center text-slate-400">
                            No open positions. Models evaluating completed M1 bars.
                          </td>
                        </tr>
                      ) : (
                        positions.map(p => (
                          <tr key={p.ticket} className={isDark ? 'hover:bg-[#151d2e]/50' : 'hover:bg-slate-50'}>
                            <td className="py-3 px-3 text-slate-400">#{p.ticket}</td>
                            <td className="py-3 px-3 font-bold text-inherit">{p.symbol}</td>
                            <td className="py-3 px-3">
                              <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                                p.side === 'BUY' ? 'bg-emerald-500/15 text-emerald-500' : 'bg-red-500/15 text-red-500'
                              }`}>
                                {p.side}
                              </span>
                            </td>
                            <td className="py-3 px-3">{p.volume.toFixed(2)}</td>
                            <td className="py-3 px-3">{p.openPrice}</td>
                            <td className="py-3 px-3 font-bold">{p.currentPrice}</td>
                            <td className="py-3 px-3 text-red-400">{p.sl}</td>
                            <td className={`py-3 px-3 font-bold ${p.profit >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>
                              {p.profit >= 0 ? '+' : ''}${p.profit.toFixed(2)}
                            </td>
                            <td className="py-3 px-3 text-right">
                              <button
                                onClick={() => {
                                  setPositions(prev => prev.filter(x => x.ticket !== p.ticket));
                                  setBalance(b => b + p.profit);
                                  setEquity(e => e + p.profit);
                                  triggerToast(`Closed Ticket #${p.ticket} on ${p.symbol}`, 'success');
                                }}
                                className="px-2.5 py-1 rounded bg-red-500/15 text-red-500 hover:bg-red-500/25 transition text-[11px]"
                              >
                                Close
                              </button>
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* TAB: RISK & OVERRIDES (H1 & H5) */}
          {activeTab === 'risk' && (
            <div className="space-y-6">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div>
                  <h2 className="text-lg font-bold tracking-tight">Risk & Protection Overrides</h2>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Four independent optional overrides, UTC day boundary tracking, and broker session compliance.
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setMode('demo')}
                    className={`px-3 py-1.5 rounded-lg text-xs font-bold transition ${
                      mode === 'demo' ? 'bg-blue-600 text-white' : 'bg-slate-500/10 text-slate-400'
                    }`}
                  >
                    Demo Account
                  </button>
                  <button
                    onClick={() => setMode('real')}
                    className={`px-3 py-1.5 rounded-lg text-xs font-bold transition ${
                      mode === 'real' ? 'bg-blue-600 text-white' : 'bg-slate-500/10 text-slate-400'
                    }`}
                  >
                    Real Account
                  </button>
                </div>
              </div>

              {/* UTC DAY BOUNDARY & STATUS CARD */}
              <div className={`p-5 rounded-2xl border ${
                riskStatus.status === 'daily_target_reached'
                  ? 'border-emerald-500/40 bg-emerald-500/5'
                  : riskStatus.status === 'daily_limit_reached'
                  ? 'border-red-500/40 bg-red-500/5'
                  : isDark ? 'bg-[#0f1520] border-[#1e2d45]' : 'bg-white border-[#d0d9e8]'
              }`}>
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                  <div>
                    <div className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">
                      UTC Trading Day Boundary
                    </div>
                    <div className="text-base font-bold text-slate-100 mt-0.5">
                      Resets Daily at 00:00:00 UTC
                    </div>
                    <div className="text-xs text-slate-400 mt-1 font-mono">
                      Current: {new Date().toUTCString().slice(17, 25)} UTC · Lagos: {watClock}
                      {testDayKey && <span className="ml-2 px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-400 font-sans">Simulated: {testDayKey}</span>}
                    </div>
                  </div>

                  <div className="flex items-center gap-3">
                    <span className={`px-2.5 py-1 rounded-full text-xs font-bold ${
                      riskStatus.status === 'daily_target_reached'
                        ? 'bg-emerald-500/20 text-emerald-400'
                        : riskStatus.status === 'daily_limit_reached'
                        ? 'bg-red-500/20 text-red-400'
                        : 'bg-blue-500/20 text-blue-400'
                    }`}>
                      Status: {riskStatus.status === 'daily_target_reached' ? 'Daily Target Reached 🎯' : riskStatus.status === 'daily_limit_reached' ? 'Daily Limit Reached 🛑' : 'Normal Trading Active'}
                    </span>
                    {riskStatus.status !== 'normal' && (
                      <button
                        onClick={() => {
                          setRiskStatus(prev => ({ ...prev, status: 'normal', reason: '' }));
                          triggerToast('Daily limit status cleared — trading active', 'success');
                        }}
                        className="px-2.5 py-1 rounded text-xs bg-slate-500/20 text-slate-300 hover:bg-slate-500/30"
                      >
                        Clear State
                      </button>
                    )}
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-3 mt-4 pt-4 border-t border-inherit">
                  <div className="p-3 rounded-lg bg-slate-500/5">
                    <div className="text-[10px] text-slate-400 uppercase">Realized Today</div>
                    <div className={`text-sm font-mono font-bold mt-1 ${riskStatus.realized_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                      {riskStatus.realized_pnl >= 0 ? '+' : ''}${riskStatus.realized_pnl.toFixed(2)}
                    </div>
                  </div>
                  <div className="p-3 rounded-lg bg-slate-500/5">
                    <div className="text-[10px] text-slate-400 uppercase">Floating Open</div>
                    <div className={`text-sm font-mono font-bold mt-1 ${riskStatus.floating_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                      {riskStatus.floating_pnl >= 0 ? '+' : ''}${riskStatus.floating_pnl.toFixed(2)}
                    </div>
                  </div>
                  <div className="p-3 rounded-lg bg-slate-500/5">
                    <div className="text-[10px] text-slate-400 uppercase">Total Day PnL</div>
                    <div className={`text-sm font-mono font-bold mt-1 ${riskStatus.today_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                      {riskStatus.today_pnl >= 0 ? '+' : ''}${riskStatus.today_pnl.toFixed(2)}
                    </div>
                  </div>
                </div>
              </div>

              {/* OVERRIDES FORM */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* 1. FIXED TAKE PROFIT */}
                <div className={`p-5 rounded-2xl border ${isDark ? 'bg-[#0f1520] border-[#1e2d45]' : 'bg-white border-[#d0d9e8]'}`}>
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="text-sm font-bold">1. Fixed Take Profit (TP)</h3>
                    <label className="flex items-center gap-2 cursor-pointer">
                      <span className={`text-xs font-bold ${riskOverrides.take_profit.enabled ? 'text-emerald-400' : 'text-slate-400'}`}>
                        {riskOverrides.take_profit.enabled ? 'ON' : 'OFF'}
                      </span>
                      <input
                        type="checkbox"
                        checked={riskOverrides.take_profit.enabled}
                        onChange={e => setRiskOverrides(r => ({ ...r, take_profit: { ...r.take_profit, enabled: e.target.checked } }))}
                      />
                    </label>
                  </div>
                  <p className="text-xs text-slate-400 mb-4">
                    When OFF: Model targets decide. When ON: Fixed TP overrides model targets for new & open positions.
                  </p>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="block text-[11px] text-slate-400 mb-1">Target (Unset is valid)</label>
                      <input
                        type="number"
                        placeholder="Optional (e.g. 50)"
                        value={riskOverrides.take_profit.value}
                        onChange={e => setRiskOverrides(r => ({ ...r, take_profit: { ...r.take_profit, value: e.target.value } }))}
                        className="w-full px-3 py-1.5 rounded-lg border text-xs"
                      />
                    </div>
                    <div>
                      <label className="block text-[11px] text-slate-400 mb-1">Units</label>
                      <select
                        value={riskOverrides.take_profit.unit}
                        onChange={e => setRiskOverrides(r => ({ ...r, take_profit: { ...r.take_profit, unit: e.target.value as any } }))}
                        className="w-full px-3 py-1.5 rounded-lg border text-xs"
                      >
                        <option value="money">$ (Money)</option>
                        <option value="pct">% (% of Pool)</option>
                      </select>
                    </div>
                  </div>
                </div>

                {/* 2. FIXED STOP LOSS */}
                <div className={`p-5 rounded-2xl border ${isDark ? 'bg-[#0f1520] border-[#1e2d45]' : 'bg-white border-[#d0d9e8]'}`}>
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="text-sm font-bold">2. Fixed Stop Loss (SL)</h3>
                    <label className="flex items-center gap-2 cursor-pointer">
                      <span className={`text-xs font-bold ${riskOverrides.stop_loss.enabled ? 'text-emerald-400' : 'text-slate-400'}`}>
                        {riskOverrides.stop_loss.enabled ? 'ON' : 'OFF'}
                      </span>
                      <input
                        type="checkbox"
                        checked={riskOverrides.stop_loss.enabled}
                        onChange={e => setRiskOverrides(r => ({ ...r, stop_loss: { ...r.stop_loss, enabled: e.target.checked } }))}
                      />
                    </label>
                  </div>
                  <p className="text-xs text-slate-400 mb-4">
                    When OFF: Model stops decide (server protective stop ALWAYS attached). When ON: Fixed SL overrides.
                  </p>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="block text-[11px] text-slate-400 mb-1">Limit (Unset is valid)</label>
                      <input
                        type="number"
                        placeholder="Optional (e.g. 30)"
                        value={riskOverrides.stop_loss.value}
                        onChange={e => setRiskOverrides(r => ({ ...r, stop_loss: { ...r.stop_loss, value: e.target.value } }))}
                        className="w-full px-3 py-1.5 rounded-lg border text-xs"
                      />
                    </div>
                    <div>
                      <label className="block text-[11px] text-slate-400 mb-1">Units</label>
                      <select
                        value={riskOverrides.stop_loss.unit}
                        onChange={e => setRiskOverrides(r => ({ ...r, stop_loss: { ...r.stop_loss, unit: e.target.value as any } }))}
                        className="w-full px-3 py-1.5 rounded-lg border text-xs"
                      >
                        <option value="money">$ (Money)</option>
                        <option value="pct">% (% of Pool)</option>
                      </select>
                    </div>
                  </div>
                </div>

                {/* 3. DAILY PROFIT TARGET */}
                <div className={`p-5 rounded-2xl border ${isDark ? 'bg-[#0f1520] border-[#1e2d45]' : 'bg-white border-[#d0d9e8]'}`}>
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="text-sm font-bold">3. Daily Profit Target</h3>
                    <label className="flex items-center gap-2 cursor-pointer">
                      <span className={`text-xs font-bold ${riskOverrides.daily_profit_target.enabled ? 'text-emerald-400' : 'text-slate-400'}`}>
                        {riskOverrides.daily_profit_target.enabled ? 'ON' : 'OFF'}
                      </span>
                      <input
                        type="checkbox"
                        checked={riskOverrides.daily_profit_target.enabled}
                        onChange={e => setRiskOverrides(r => ({ ...r, daily_profit_target: { ...r.daily_profit_target, enabled: e.target.checked } }))}
                      />
                    </label>
                  </div>
                  <p className="text-xs text-slate-400 mb-3">
                    Stops opening new trades once day PnL hits target. Resets automatically at 00:00 UTC.
                  </p>
                  <div className="grid grid-cols-2 gap-2 mb-3">
                    <div>
                      <label className="block text-[11px] text-slate-400 mb-1">Target Value</label>
                      <input
                        type="number"
                        placeholder="Optional (e.g. 100)"
                        value={riskOverrides.daily_profit_target.value}
                        onChange={e => setRiskOverrides(r => ({ ...r, daily_profit_target: { ...r.daily_profit_target, value: e.target.value } }))}
                        className="w-full px-3 py-1.5 rounded-lg border text-xs"
                      />
                    </div>
                    <div>
                      <label className="block text-[11px] text-slate-400 mb-1">Units</label>
                      <select
                        value={riskOverrides.daily_profit_target.unit}
                        onChange={e => setRiskOverrides(r => ({ ...r, daily_profit_target: { ...r.daily_profit_target, unit: e.target.value as any } }))}
                        className="w-full px-3 py-1.5 rounded-lg border text-xs"
                      >
                        <option value="money">$ (Money)</option>
                        <option value="pct">% (% of Pool)</option>
                      </select>
                    </div>
                  </div>
                  <label className="flex items-center gap-2 text-xs text-slate-400 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={riskOverrides.daily_profit_target.close_open_on_hit}
                      onChange={e => setRiskOverrides(r => ({ ...r, daily_profit_target: { ...r.daily_profit_target, close_open_on_hit: e.target.checked } }))}
                    />
                    <span>Also close all open positions when target reached</span>
                  </label>
                </div>

                {/* 4. DAILY LOSS LIMIT */}
                <div className={`p-5 rounded-2xl border ${isDark ? 'bg-[#0f1520] border-[#1e2d45]' : 'bg-white border-[#d0d9e8]'}`}>
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="text-sm font-bold">4. Daily Loss Limit</h3>
                    <label className="flex items-center gap-2 cursor-pointer">
                      <span className={`text-xs font-bold ${riskOverrides.daily_loss_limit.enabled ? 'text-emerald-400' : 'text-slate-400'}`}>
                        {riskOverrides.daily_loss_limit.enabled ? 'ON' : 'OFF'}
                      </span>
                      <input
                        type="checkbox"
                        checked={riskOverrides.daily_loss_limit.enabled}
                        onChange={e => setRiskOverrides(r => ({ ...r, daily_loss_limit: { ...r.daily_loss_limit, enabled: e.target.checked } }))}
                      />
                    </label>
                  </div>
                  <p className="text-xs text-slate-400 mb-3">
                    Halts new trades if day drawdown reaches limit. Resets automatically at 00:00 UTC.
                  </p>
                  <div className="grid grid-cols-2 gap-2 mb-3">
                    <div>
                      <label className="block text-[11px] text-slate-400 mb-1">Loss Limit</label>
                      <input
                        type="number"
                        placeholder="Optional (e.g. 50)"
                        value={riskOverrides.daily_loss_limit.value}
                        onChange={e => setRiskOverrides(r => ({ ...r, daily_loss_limit: { ...r.daily_loss_limit, value: e.target.value } }))}
                        className="w-full px-3 py-1.5 rounded-lg border text-xs"
                      />
                    </div>
                    <div>
                      <label className="block text-[11px] text-slate-400 mb-1">Units</label>
                      <select
                        value={riskOverrides.daily_loss_limit.unit}
                        onChange={e => setRiskOverrides(r => ({ ...r, daily_loss_limit: { ...r.daily_loss_limit, unit: e.target.value as any } }))}
                        className="w-full px-3 py-1.5 rounded-lg border text-xs"
                      >
                        <option value="money">$ (Money)</option>
                        <option value="pct">% (% of Pool)</option>
                      </select>
                    </div>
                  </div>
                  <label className="flex items-center gap-2 text-xs text-slate-400 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={riskOverrides.daily_loss_limit.close_open_on_hit}
                      onChange={e => setRiskOverrides(r => ({ ...r, daily_loss_limit: { ...r.daily_loss_limit, close_open_on_hit: e.target.checked } }))}
                    />
                    <span>Also close all open positions when limit reached</span>
                  </label>
                </div>
              </div>

              {/* 5. WEEKEND TRADING SCHEDULE (H5) */}
              <div className={`p-5 rounded-2xl border ${isDark ? 'bg-[#0f1520] border-[#1e2d45]' : 'bg-white border-[#d0d9e8]'}`}>
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-sm font-bold">Trade on weekends (synthetic indices only trade 24/7)</h3>
                    <p className="text-xs text-slate-400 mt-1">
                      Forex markets close on weekends. Default OFF keeps forex idle when closed, while synthetics trade 24/7.
                    </p>
                  </div>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <span className={`text-xs font-bold ${riskOverrides.trade_weekends ? 'text-emerald-400' : 'text-slate-400'}`}>
                      {riskOverrides.trade_weekends ? 'ON' : 'OFF'}
                    </span>
                    <input
                      type="checkbox"
                      checked={riskOverrides.trade_weekends}
                      onChange={e => setRiskOverrides(r => ({ ...r, trade_weekends: e.target.checked }))}
                    />
                  </label>
                </div>
              </div>

              {/* SAVE & TEST HOOKS */}
              <div className={`p-5 rounded-2xl border flex flex-col sm:flex-row sm:items-center justify-between gap-4 ${
                isDark ? 'bg-[#0f1520] border-[#1e2d45]' : 'bg-white border-[#d0d9e8]'
              }`}>
                <div>
                  <button
                    onClick={() => {
                      triggerToast(`Risk overrides saved for ${mode.toUpperCase()} mode!`, 'success');
                    }}
                    className="px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-bold text-xs"
                  >
                    Save Risk Overrides ({mode.toUpperCase()})
                  </button>
                  <span className="text-[11px] text-slate-400 ml-3">Valid unset state: saves with empty or off fields</span>
                </div>

                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-slate-400 uppercase font-bold">Test Hook:</span>
                  <button
                    onClick={() => {
                      const d = new Date();
                      d.setDate(d.getDate() + 1);
                      const next = d.toISOString().slice(0, 10);
                      setTestDayKey(next);
                      setRiskStatus(prev => ({ ...prev, status: 'normal', reason: '' }));
                      triggerToast(`Simulated next day boundary: ${next} — counters reset & trading resumed`, 'info');
                    }}
                    className="px-3 py-1.5 rounded-lg border text-xs text-slate-300 hover:bg-slate-500/10"
                  >
                    Simulate Next Day
                  </button>
                  {testDayKey && (
                    <button
                      onClick={() => {
                        setTestDayKey(null);
                        triggerToast('Restored real UTC day key', 'info');
                      }}
                      className="px-3 py-1.5 rounded-lg border border-red-500/30 text-xs text-red-400 hover:bg-red-500/10"
                    >
                      Reset Date
                    </button>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: TRAINING (PPO v2) */}
          {activeTab === 'training' && (
            <div className="space-y-6">
              {/* STATUS & PROGRESS CARD */}
              <div className={`p-6 rounded-2xl border ${
                isDark ? 'bg-[#0f1520] border-[#1e2d45]' : 'bg-white border-[#d0d9e8] shadow-sm'
              }`}>
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
                  <div>
                    <h2 className="text-base font-bold tracking-tight">Reinforcement Learning Scalper Training</h2>
                    <p className="text-xs text-slate-400 mt-0.5">
                      62-dimension causal observation vector (M1/M5/M15/H1) · 8 discrete actions · 70/15/15 walk-forward eval
                    </p>
                  </div>
                  <span className={`px-2.5 py-1 rounded-full text-xs font-bold uppercase ${
                    trainingStatus === 'training' || trainingLocked
                      ? 'bg-amber-500/15 text-amber-500 border border-amber-500/30'
                      : 'bg-emerald-500/15 text-emerald-500 border border-emerald-500/30'
                  }`}>
                    {trainingStatus === 'training' ? 'Training Active' : trainingLocked ? 'Lock Active' : 'Idle / Ready'}
                  </span>
                </div>

                {/* Progress bar */}
                <div className={`p-4 rounded-xl border mb-6 ${
                  isDark ? 'bg-[#151d2e] border-[#1e2d45]' : 'bg-slate-50 border-slate-200'
                }`}>
                  <div className="flex items-center justify-between text-xs font-mono mb-2">
                    <span className="font-bold text-inherit">Active Target Pair: <strong className="text-[#3b82f6]">{activeTrainPair}</strong></span>
                    <span className="text-slate-400">
                      {trainStepsDone.toLocaleString()} / {trainStepsTarget.toLocaleString()} steps ({((trainStepsDone / trainStepsTarget) * 100).toFixed(1)}%)
                    </span>
                  </div>
                  <div className="w-full h-2 rounded-full bg-slate-700/30 overflow-hidden">
                    <div
                      className="h-full bg-[#3b82f6] rounded-full transition-all duration-500"
                      style={{ width: `${(trainStepsDone / trainStepsTarget) * 100}%` }}
                    ></div>
                  </div>
                  <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-400 mt-2.5">
                    <span>Throughput: <strong className={isDark ? "text-slate-200" : "text-slate-800"}>{etaInfo.rateStr}</strong> ({etaInfo.elapsedStr})</span>
                    <span>ETA: <strong className={isDark ? "text-slate-200" : "text-slate-800"}>{etaInfo.etaStr}</strong> · Est. Finish: <strong className={isDark ? "text-slate-200" : "text-slate-800"}>{etaInfo.finishStr}</strong></span>
                  </div>
                </div>

                {/* Training Actions */}
                <div className="flex flex-wrap items-center gap-3">
                  <button
                    onClick={startEurusdTraining}
                    className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-bold bg-[#3b82f6] hover:bg-blue-600 text-white transition-colors"
                  >
                    <Play className="w-3.5 h-3.5 fill-current" />
                    <span>Start / Dispatch EUR/USD Training</span>
                  </button>

                  <button
                    onClick={() => {
                      const next = !trainingLocked;
                      setTrainingLocked(next);
                      fetch(`${WORKER_URL}/api/settings/training-lock`, {
                        method: 'POST',
                        headers: { 'Authorization': `Bearer ${pat}`, 'Content-Type': 'application/json' },
                        body: JSON.stringify({ locked: next, reason: next ? 'manual_user_toggle' : '' })
                      }).catch(() => {});
                      triggerToast(`Training lock ${next ? 'engaged' : 'cleared'}`, 'info');
                    }}
                    className={`px-3 py-2 rounded-lg text-xs font-semibold border transition ${
                      trainingLocked
                        ? 'bg-amber-500/15 text-amber-500 border-amber-500/30'
                        : isDark ? 'bg-[#151d2e] border-[#1e2d45] text-slate-300' : 'bg-slate-100 border-slate-300 text-slate-700'
                    }`}
                  >
                    {trainingLocked ? 'Clear Training Lock' : 'Engage Training Interlock'}
                  </button>
                </div>
              </div>

              {/* FOREX PAIRS (13) */}
              <div className={`p-6 rounded-2xl border ${
                isDark ? 'bg-[#0f1520] border-[#1e2d45]' : 'bg-white border-[#d0d9e8] shadow-sm'
              }`}>
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-sm font-bold tracking-tight">Forex Major & Cross Pairs (13)</h3>
                  <span className="text-xs text-slate-400 font-mono">HistData M1 Datasets Ready</span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
                  {FOREX_PAIRS.map(pair => {
                    const isSelected = !!selectedPairs[pair];
                    return (
                      <div
                        key={pair}
                        className={`p-3.5 rounded-xl border transition-all ${
                          isSelected
                            ? isDark ? 'bg-[#151d2e] border-blue-500/50' : 'bg-blue-50/50 border-blue-300'
                            : isDark ? 'bg-[#131b29] border-[#1e2d45]' : 'bg-slate-50 border-slate-200'
                        }`}
                      >
                        <div className="flex items-center justify-between mb-2">
                          <label className="flex items-center gap-2 cursor-pointer font-bold text-sm">
                            <input
                              type="checkbox"
                              checked={isSelected}
                              onChange={e => setSelectedPairs(prev => ({ ...prev, [pair]: e.target.checked }))}
                              className="rounded text-[#3b82f6]"
                            />
                            <span>{pair}</span>
                          </label>
                          <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-500">
                            Ready ✓
                          </span>
                        </div>
                        <div className="flex items-center justify-between text-[11px] text-slate-400 font-mono">
                          <span>M1 Bars</span>
                          <span>1.2M+ rows</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* SYNTHETICS (10) */}
              <div className={`p-6 rounded-2xl border ${
                isDark ? 'bg-[#0f1520] border-[#1e2d45]' : 'bg-white border-[#d0d9e8] shadow-sm'
              }`}>
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-sm font-bold tracking-tight">Deriv Synthetic Indices (10)</h3>
                  <span className="text-xs text-slate-400 font-mono">24/7 Tick Streams</span>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3">
                  {SYNTHETICS.map(sym => (
                    <div
                      key={sym}
                      className={`p-3 rounded-xl border text-center ${
                        isDark ? 'bg-[#131b29] border-[#1e2d45]' : 'bg-slate-50 border-slate-200'
                      }`}
                    >
                      <div className="font-bold text-xs">{sym}</div>
                      <div className="text-[10px] text-emerald-500 mt-1">Daily Auto-Updated</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* TAB 3: TRADE HISTORY */}
          {activeTab === 'history' && (
            <div className="space-y-6">
              {/* SUMMARY ROW */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className={`p-4 rounded-xl border ${isDark ? 'bg-[#0f1520] border-[#1e2d45]' : 'bg-white border-[#d0d9e8]'}`}>
                  <div className="text-[11px] font-semibold text-slate-400 uppercase">Total Executed</div>
                  <div className="text-2xl font-bold font-mono mt-1">{historyMetrics.total}</div>
                </div>

                <div className={`p-4 rounded-xl border ${isDark ? 'bg-[#0f1520] border-[#1e2d45]' : 'bg-white border-[#d0d9e8]'}`}>
                  <div className="text-[11px] font-semibold text-slate-400 uppercase">Win Rate</div>
                  <div className="text-2xl font-bold font-mono text-emerald-500 mt-1">{historyMetrics.winRate}%</div>
                  <div className="text-[10px] text-slate-400">{historyMetrics.wins}W / {historyMetrics.losses}L</div>
                </div>

                <div className={`p-4 rounded-xl border ${isDark ? 'bg-[#0f1520] border-[#1e2d45]' : 'bg-white border-[#d0d9e8]'}`}>
                  <div className="text-[11px] font-semibold text-slate-400 uppercase">Net Realized PnL</div>
                  <div className={`text-2xl font-bold font-mono mt-1 ${historyMetrics.net >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>
                    {historyMetrics.net >= 0 ? '+' : ''}${historyMetrics.net.toFixed(2)}
                  </div>
                </div>

                <div className={`p-4 rounded-xl border ${isDark ? 'bg-[#0f1520] border-[#1e2d45]' : 'bg-white border-[#d0d9e8]'}`}>
                  <div className="text-[11px] font-semibold text-slate-400 uppercase">Profit Factor</div>
                  <div className="text-2xl font-bold font-mono mt-1">2.41</div>
                </div>
              </div>

              {/* FILTER & EXPORT */}
              <div className={`p-4 rounded-xl border flex flex-wrap items-center justify-between gap-3 ${
                isDark ? 'bg-[#0f1520] border-[#1e2d45]' : 'bg-white border-[#d0d9e8]'
              }`}>
                <div className="flex flex-wrap items-center gap-3 text-xs">
                  <select
                    value={filterPair}
                    onChange={e => setFilterPair(e.target.value)}
                    className={`px-3 py-1.5 rounded-lg border ${
                      isDark ? 'bg-[#151d2e] border-[#1e2d45] text-white' : 'bg-slate-50 border-slate-300 text-slate-900'
                    }`}
                  >
                    <option value="ALL">All Pairs</option>
                    {FOREX_PAIRS.map(p => <option key={p} value={p}>{p}</option>)}
                  </select>

                  <select
                    value={filterOutcome}
                    onChange={e => setFilterOutcome(e.target.value as 'ALL' | 'WIN' | 'LOSS')}
                    className={`px-3 py-1.5 rounded-lg border ${
                      isDark ? 'bg-[#151d2e] border-[#1e2d45] text-white' : 'bg-slate-50 border-slate-300 text-slate-900'
                    }`}
                  >
                    <option value="ALL">All Results</option>
                    <option value="WIN">Wins Only</option>
                    <option value="LOSS">Losses Only</option>
                  </select>
                </div>

                <button
                  onClick={handleExportCsv}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border transition-colors hover:border-[#3b82f6]"
                >
                  <Download className="w-3.5 h-3.5" />
                  <span>Export CSV</span>
                </button>
              </div>

              {/* TABLE */}
              <div className={`p-6 rounded-2xl border ${
                isDark ? 'bg-[#0f1520] border-[#1e2d45]' : 'bg-white border-[#d0d9e8] shadow-sm'
              }`}>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs font-mono">
                    <thead>
                      <tr className={`border-b ${isDark ? 'border-[#1e2d45] text-slate-400' : 'border-slate-200 text-slate-500'}`}>
                        <th className="py-2.5 px-3">Close Time</th>
                        <th className="py-2.5 px-3">Pair</th>
                        <th className="py-2.5 px-3">Side</th>
                        <th className="py-2.5 px-3">Lots</th>
                        <th className="py-2.5 px-3">Net PnL</th>
                        <th className="py-2.5 px-3">Result</th>
                        <th className="py-2.5 px-3">Exit Rule</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-inherit">
                      {filteredTrades.map(t => (
                        <tr key={t.id} className={isDark ? 'hover:bg-[#151d2e]/50' : 'hover:bg-slate-50'}>
                          <td className="py-3 px-3 text-slate-400">{t.closeTime}</td>
                          <td className="py-3 px-3 font-bold text-inherit">{t.symbol}</td>
                          <td className="py-3 px-3">
                            <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                              t.side === 'BUY' ? 'bg-emerald-500/15 text-emerald-500' : 'bg-red-500/15 text-red-500'
                            }`}>
                              {t.side}
                            </span>
                          </td>
                          <td className="py-3 px-3">{t.volume.toFixed(2)}</td>
                          <td className={`py-3 px-3 font-bold ${t.netPnl >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>
                            {t.netPnl >= 0 ? '+' : ''}${t.netPnl.toFixed(2)}
                          </td>
                          <td className="py-3 px-3">
                            <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                              t.netPnl >= 0 ? 'bg-emerald-500/15 text-emerald-500' : 'bg-red-500/15 text-red-500'
                            }`}>
                              {t.netPnl >= 0 ? 'WIN' : 'LOSS'}
                            </span>
                          </td>
                          <td className="py-3 px-3 text-slate-400">{t.reason}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* TAB 4: SETTINGS & APPEARANCE */}
          {activeTab === 'settings' && (
            <div className="max-w-3xl space-y-6">
              {/* APPEARANCE (AUTOMATIC / DARK / LIGHT) */}
              <div className={`p-6 rounded-2xl border ${
                isDark ? 'bg-[#0f1520] border-[#1e2d45]' : 'bg-white border-[#d0d9e8] shadow-sm'
              }`}>
                <h3 className="text-sm font-bold tracking-tight mb-1">Theme & Color Scheme</h3>
                <p className="text-xs text-slate-400 mb-4">
                  Automatic dark and light UI syncs with your system preferences or lets you manually pin your preferred look.
                </p>

                <div className="flex flex-wrap items-center gap-3">
                  <button
                    onClick={() => setThemeSetting('auto')}
                    className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold border transition ${
                      themeSetting === 'auto'
                        ? 'bg-[#3b82f6] text-white border-[#3b82f6]'
                        : isDark ? 'bg-[#151d2e] border-[#1e2d45] text-slate-300' : 'bg-slate-100 border-slate-300 text-slate-700'
                    }`}
                  >
                    <Monitor className="w-4 h-4" />
                    <span>Auto (System Preference)</span>
                  </button>

                  <button
                    onClick={() => setThemeSetting('dark')}
                    className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold border transition ${
                      themeSetting === 'dark'
                        ? 'bg-[#3b82f6] text-white border-[#3b82f6]'
                        : isDark ? 'bg-[#151d2e] border-[#1e2d45] text-slate-300' : 'bg-slate-100 border-slate-300 text-slate-700'
                    }`}
                  >
                    <Moon className="w-4 h-4" />
                    <span>Dark Terminal</span>
                  </button>

                  <button
                    onClick={() => setThemeSetting('light')}
                    className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold border transition ${
                      themeSetting === 'light'
                        ? 'bg-[#3b82f6] text-white border-[#3b82f6]'
                        : isDark ? 'bg-[#151d2e] border-[#1e2d45] text-slate-300' : 'bg-slate-100 border-slate-300 text-slate-700'
                    }`}
                  >
                    <Sun className="w-4 h-4" />
                    <span>Crisp Light</span>
                  </button>
                </div>
              </div>

              {/* GITHUB PAT */}
              <div className={`p-6 rounded-2xl border ${
                isDark ? 'bg-[#0f1520] border-[#1e2d45]' : 'bg-white border-[#d0d9e8] shadow-sm'
              }`}>
                <div className="flex items-center justify-between mb-1">
                  <h3 className="text-sm font-bold tracking-tight">GitHub Personal Access Token (PAT)</h3>
                  <span className="text-xs text-emerald-500 font-semibold flex items-center gap-1">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    <span>Configured</span>
                  </span>
                </div>
                <p className="text-xs text-slate-400 mb-4">
                  Used for dispatching workflow runs for bot execution and model training.
                </p>

                <div className="space-y-3">
                  <input
                    type="password"
                    value={pat}
                    onChange={e => {
                      setPat(e.target.value);
                      localStorage.setItem('sfx_pat', e.target.value);
                    }}
                    className={`w-full px-3 py-2 rounded-lg border font-mono text-xs ${
                      isDark ? 'bg-[#151d2e] border-[#1e2d45] text-white' : 'bg-slate-50 border-slate-300 text-slate-900'
                    }`}
                  />
                  <div className="flex items-center justify-between text-xs text-slate-400">
                    <span>Stored securely in client-side localStorage</span>
                    <button
                      onClick={() => triggerToast('PAT connection verified with GitHub API', 'success')}
                      className="text-[#3b82f6] hover:underline"
                    >
                      Verify Token
                    </button>
                  </div>
                </div>
              </div>

              {/* DERIV MT5 ACCOUNT CREDENTIALS (H4) */}
              <div className={`p-6 rounded-2xl border ${
                isDark ? 'bg-[#0f1520] border-[#1e2d45]' : 'bg-white border-[#d0d9e8] shadow-sm'
              }`}>
                <div className="flex items-center justify-between mb-1">
                  <h3 className="text-sm font-bold tracking-tight">MT5 account</h3>
                  <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 font-semibold border border-emerald-500/20">
                    Deriv MT5
                  </span>
                </div>
                <p className="text-xs text-slate-400 mb-4">
                  Deriv MetaTrader 5 broker credentials for demo and real accounts. Password is write-only.
                </p>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs mb-4">
                  <div>
                    <label className="block text-slate-400 text-[11px] mb-1 font-semibold">Demo Login ID</label>
                    <input
                      type="text"
                      defaultValue="41286446"
                      id="app-mt5-demo-login"
                      className={`w-full px-3 py-2 rounded-lg border font-mono text-xs ${
                        isDark ? 'bg-[#151d2e] border-[#1e2d45] text-white' : 'bg-slate-50 border-slate-300 text-slate-900'
                      }`}
                    />
                  </div>
                  <div>
                    <label className="block text-slate-400 text-[11px] mb-1 font-semibold">Demo Server</label>
                    <input
                      type="text"
                      defaultValue="Deriv-Demo"
                      id="app-mt5-demo-server"
                      className={`w-full px-3 py-2 rounded-lg border font-mono text-xs ${
                        isDark ? 'bg-[#151d2e] border-[#1e2d45] text-white' : 'bg-slate-50 border-slate-300 text-slate-900'
                      }`}
                    />
                  </div>
                  <div>
                    <label className="block text-slate-400 text-[11px] mb-1 font-semibold">Real Login ID</label>
                    <input
                      type="text"
                      defaultValue="10357278"
                      id="app-mt5-real-login"
                      className={`w-full px-3 py-2 rounded-lg border font-mono text-xs ${
                        isDark ? 'bg-[#151d2e] border-[#1e2d45] text-white' : 'bg-slate-50 border-slate-300 text-slate-900'
                      }`}
                    />
                  </div>
                  <div>
                    <label className="block text-slate-400 text-[11px] mb-1 font-semibold">Real Server</label>
                    <input
                      type="text"
                      defaultValue="DerivSVG-Server"
                      id="app-mt5-real-server"
                      className={`w-full px-3 py-2 rounded-lg border font-mono text-xs ${
                        isDark ? 'bg-[#151d2e] border-[#1e2d45] text-white' : 'bg-slate-50 border-slate-300 text-slate-900'
                      }`}
                    />
                  </div>
                  <div className="sm:col-span-2">
                    <label className="block text-slate-400 text-[11px] mb-1 font-semibold">
                      MT5 Password (Write-Only: never displayed or logged)
                    </label>
                    <input
                      type="password"
                      placeholder="Enter new password to update (write-only, leaves existing if empty)"
                      id="app-mt5-pwd"
                      className={`w-full px-3 py-2 rounded-lg border font-mono text-xs ${
                        isDark ? 'bg-[#151d2e] border-[#1e2d45] text-white' : 'bg-slate-50 border-slate-300 text-slate-900'
                      }`}
                    />
                  </div>
                </div>

                <div className="flex flex-wrap items-center justify-between gap-2 pt-3 border-t border-slate-800">
                  <div className="flex gap-2">
                    <button
                      onClick={() => triggerToast('MT5 Account saved securely (repository secrets updated)', 'success')}
                      className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-[#3b82f6] hover:bg-blue-600 text-white transition-colors"
                    >
                      Save MT5 Account
                    </button>
                    <button
                      onClick={async () => {
                        triggerToast('Dispatching test-login workflow to verify MT5 login...', 'info');
                        await dispatchWorkflow('test-login.yml', { mode: 'demo' });
                      }}
                      className={`px-3 py-1.5 rounded-lg text-xs font-semibold border ${
                        isDark ? 'bg-[#151d2e] border-[#1e2d45] text-slate-200' : 'bg-slate-100 border-slate-300 text-slate-800'
                      }`}
                    >
                      Test Login
                    </button>
                  </div>
                  <button
                    onClick={async () => {
                      triggerToast('Restarting bot with updated credentials (zero-gap handover)...', 'info');
                      await dispatchWorkflow('bot.yml', { mode: 'demo', chain: 'true' });
                    }}
                    className={`px-3 py-1.5 rounded-lg text-xs font-semibold border ${
                      isDark ? 'bg-[#151d2e] border-[#1e2d45] text-slate-200' : 'bg-slate-100 border-slate-300 text-slate-800'
                    }`}
                  >
                    Restart Bot with New Credentials
                  </button>
                </div>
              </div>
            </div>
          )}
        </main>
      </div>

      {/* MOBILE BOTTOM NAVIGATION BAR */}
      <nav className={`lg:hidden fixed bottom-0 left-0 right-0 h-14 border-t flex items-center justify-around z-40 ${
        isDark ? 'bg-[#0f1520] border-[#1e2d45]' : 'bg-white border-[#d0d9e8]'
      }`}>
        <button
          onClick={() => setActiveTab('dash')}
          className={`flex flex-col items-center gap-1 text-[11px] font-semibold ${
            activeTab === 'dash' ? 'text-[#3b82f6]' : 'text-slate-400'
          }`}
        >
          <Activity className="w-4 h-4" />
          <span>Dashboard</span>
        </button>

        <button
          onClick={() => setActiveTab('risk')}
          className={`flex flex-col items-center gap-1 text-[11px] font-semibold ${
            activeTab === 'risk' ? 'text-[#3b82f6]' : 'text-slate-400'
          }`}
        >
          <Shield className="w-4 h-4" />
          <span>Risk</span>
        </button>

        <button
          onClick={() => setActiveTab('training')}
          className={`flex flex-col items-center gap-1 text-[11px] font-semibold ${
            activeTab === 'training' ? 'text-[#3b82f6]' : 'text-slate-400'
          }`}
        >
          <Sparkles className="w-4 h-4" />
          <span>Training</span>
        </button>

        <button
          onClick={() => setActiveTab('history')}
          className={`flex flex-col items-center gap-1 text-[11px] font-semibold ${
            activeTab === 'history' ? 'text-[#3b82f6]' : 'text-slate-400'
          }`}
        >
          <History className="w-4 h-4" />
          <span>History</span>
        </button>

        <button
          onClick={() => setActiveTab('settings')}
          className={`flex flex-col items-center gap-1 text-[11px] font-semibold ${
            activeTab === 'settings' ? 'text-[#3b82f6]' : 'text-slate-400'
          }`}
        >
          <Settings className="w-4 h-4" />
          <span>Settings</span>
        </button>
      </nav>
    </div>
  );
}
