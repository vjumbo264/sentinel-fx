/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState, useEffect, useMemo } from 'react';
import {
  TrendingUp,
  Shield,
  Activity,
  Cpu,
  Sliders,
  Calendar,
  Terminal,
  Play,
  Square,
  RefreshCw,
  AlertTriangle,
  CheckCircle,
  Copy,
  ChevronRight,
  DollarSign,
  Layers,
  ArrowUpRight,
  ArrowDownRight,
  Lock,
  Unlock,
  Radio,
  Clock,
  Sparkles,
  Award,
  Zap,
  BarChart2,
  FileText
} from 'lucide-react';

interface Position {
  ticket: number;
  symbol: string;
  side: 'BUY' | 'SELL';
  volume: number;
  openPrice: number;
  currentPrice: number;
  sl: number;
  tp: number;
  profit: number;
  magic: number;
  modelId: string;
  openTime: string;
}

interface ModelCard {
  symbol: string;
  name: string;
  category: 'forex' | 'volatility';
  version: number;
  enabled: boolean;
  circuitBreaker: boolean;
  confluenceScore: number;
  lastAction: 'BUY' | 'SELL' | 'HOLD' | 'STAY_OUT';
  lastActionTime: string;
  growthMultiple: number;
  maxDrawdown: number;
  tradesToday: number;
  openPositionsCount: number;
}

interface NewsItem {
  id: string;
  time: string;
  currency: string;
  impact: 'HIGH' | 'MEDIUM' | 'LOW';
  title: string;
  forecast?: string;
  previous?: string;
  actionTaken: string;
}

interface OverridesState {
  maxExposureEnabled: boolean;
  maxExposureLots: number;
  dailyTpEnabled: boolean;
  dailyTpUsd: number;
  dailySlEnabled: boolean;
  dailySlUsd: number;
  repeatDaily: boolean;
}

export default function App() {
  const [activeTab, setActiveTab] = useState<'dash' | 'models' | 'desk' | 'risk' | 'train' | 'news' | 'logs'>('dash');
  const [mode, setMode] = useState<'demo' | 'real'>('demo');
  const [botRunning, setBotRunning] = useState<boolean>(true);
  const [killSwitch, setKillSwitch] = useState<boolean>(false);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  // Account State
  const [balance, setBalance] = useState<number>(10007.18);
  const [equity, setEquity] = useState<number>(10042.85);
  const [margin, setMargin] = useState<number>(185.40);
  const [freeMargin, setFreeMargin] = useState<number>(9857.45);
  const [leverage] = useState<number>(1000);
  const [serverName] = useState<string>('Deriv-Demo');
  const [loginId] = useState<string>('41286446');

  // Runner Handover State (3h50m boundary)
  const [runnerTimeRemaining, setRunnerTimeRemaining] = useState<number>(11420); // seconds
  const [runnerId] = useState<string>('runner-alpha-mt5-3809');

  // Overrides State
  const [overrides, setOverrides] = useState<OverridesState>({
    maxExposureEnabled: false,
    maxExposureLots: 1.5,
    dailyTpEnabled: false,
    dailyTpUsd: 500,
    dailySlEnabled: false,
    dailySlUsd: 250,
    repeatDaily: true
  });

  // Open Positions
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
      magic: 999101,
      modelId: 'eurusd_v2',
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
      magic: 999102,
      modelId: 'vol10_v2',
      openTime: '24m ago'
    }
  ]);

  // Model Cards
  const [models, setModels] = useState<ModelCard[]>([
    {
      symbol: 'EURUSD',
      name: 'EUR / USD',
      category: 'forex',
      version: 2,
      enabled: true,
      circuitBreaker: false,
      confluenceScore: 88,
      lastAction: 'BUY',
      lastActionTime: '12m ago',
      growthMultiple: 1.28,
      maxDrawdown: 4.8,
      tradesToday: 4,
      openPositionsCount: 1
    },
    {
      symbol: 'GBPUSD',
      name: 'GBP / USD',
      category: 'forex',
      version: 1,
      enabled: true,
      circuitBreaker: false,
      confluenceScore: 74,
      lastAction: 'STAY_OUT',
      lastActionTime: '4m ago',
      growthMultiple: 1.19,
      maxDrawdown: 5.2,
      tradesToday: 2,
      openPositionsCount: 0
    },
    {
      symbol: 'USDJPY',
      name: 'USD / JPY',
      category: 'forex',
      version: 2,
      enabled: true,
      circuitBreaker: false,
      confluenceScore: 82,
      lastAction: 'HOLD',
      lastActionTime: '8m ago',
      growthMultiple: 1.34,
      maxDrawdown: 3.9,
      tradesToday: 3,
      openPositionsCount: 0
    },
    {
      symbol: 'AUDUSD',
      name: 'AUD / USD',
      category: 'forex',
      version: 1,
      enabled: false,
      circuitBreaker: false,
      confluenceScore: 61,
      lastAction: 'STAY_OUT',
      lastActionTime: '1h ago',
      growthMultiple: 1.12,
      maxDrawdown: 6.1,
      tradesToday: 1,
      openPositionsCount: 0
    },
    {
      symbol: 'Volatility 10 Index',
      name: 'Volatility 10 Index',
      category: 'volatility',
      version: 2,
      enabled: true,
      circuitBreaker: false,
      confluenceScore: 91,
      lastAction: 'BUY',
      lastActionTime: '24m ago',
      growthMultiple: 1.45,
      maxDrawdown: 4.2,
      tradesToday: 6,
      openPositionsCount: 1
    },
    {
      symbol: 'Volatility 100 Index',
      name: 'Volatility 100 Index',
      category: 'volatility',
      version: 2,
      enabled: true,
      circuitBreaker: false,
      confluenceScore: 69,
      lastAction: 'STAY_OUT',
      lastActionTime: '15m ago',
      growthMultiple: 1.22,
      maxDrawdown: 7.1,
      tradesToday: 3,
      openPositionsCount: 0
    }
  ]);

  // Train tab state
  const [selectedTrainSymbols, setSelectedTrainSymbols] = useState<string[]>(['EURUSD', 'USDJPY']);
  const [publishPat, setPublishPat] = useState<string>('');
  const [promptCopied, setPromptCopied] = useState<boolean>(false);

  // News items
  const [newsEvents] = useState<NewsItem[]>([
    {
      id: 'news-1',
      time: '13:30 UTC',
      currency: 'USD',
      impact: 'HIGH',
      title: 'US Core CPI m/m',
      forecast: '0.3%',
      previous: '0.3%',
      actionTaken: 'Models widened stops 15m prior; resumed normal sizing'
    },
    {
      id: 'news-2',
      time: '15:00 UTC',
      currency: 'EUR',
      impact: 'HIGH',
      title: 'ECB Monetary Policy Statement',
      forecast: '3.25%',
      previous: '3.50%',
      actionTaken: 'EURUSD stood down (STAY_OUT) during press conference'
    },
    {
      id: 'news-3',
      time: '23:30 UTC',
      currency: 'JPY',
      impact: 'MEDIUM',
      title: 'Tokyo Core CPI y/y',
      forecast: '1.8%',
      previous: '2.0%',
      actionTaken: 'USDJPY volatility factor updated'
    }
  ]);

  // Decision Logs
  const [logs, setLogs] = useState<{ id: string; time: string; symbol: string; text: string; type: 'info' | 'trade' | 'warn' }[]>([
    { id: '1', time: '17:20:15', symbol: 'EURUSD', text: 'Confluence 88% (Trend M15 + Breakout M1). Evaluated order_check OK. Dispatched BUY 0.1 lots @ 1.08450 with mandatory SL 1.08150. Ticket #541092', type: 'trade' },
    { id: '2', time: '17:18:40', symbol: 'Volatility 10 Index', text: 'Trailing stop adjusted on Ticket #541093 to 4945.00 (+25.00 buffer lock-in)', type: 'info' },
    { id: '3', time: '17:15:00', symbol: 'GBPUSD', text: 'Structure flat, spread at 22pts. Plan evaluator stood down (STAY_OUT). Capital protected.', type: 'info' },
    { id: '4', time: '17:10:22', symbol: 'SUPERVISOR', text: 'Runner lease renewed with D1 coordinator. Zero orphan tickets. Health ping 0.025s.', type: 'info' }
  ]);

  // Toast feedback
  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3500);
  };

  // Periodic runner countdown & tick simulation
  useEffect(() => {
    const interval = setInterval(() => {
      setRunnerTimeRemaining(prev => Math.max(0, prev - 1));
      // Small simulated tick movement
      setPositions(prev =>
        prev.map(p => {
          const delta = (Math.random() - 0.49) * (p.symbol.includes('Volatility') ? 0.35 : 0.00008);
          const newPrice = Number((p.currentPrice + delta).toFixed(p.symbol.includes('Volatility') ? 2 : 5));
          const profitDiff = (p.side === 'BUY' ? newPrice - p.openPrice : p.openPrice - newPrice) * (p.symbol.includes('Volatility') ? 10 : 100000) * p.volume;
          return {
            ...p,
            currentPrice: newPrice,
            profit: Number(profitDiff.toFixed(2))
          };
        })
      );
    }, 2000);
    return () => clearInterval(interval);
  }, []);

  const totalOpenProfit = useMemo(() => {
    return positions.reduce((acc, p) => acc + p.profit, 0);
  }, [positions]);

  const activeExposureLots = useMemo(() => {
    return positions.reduce((acc, p) => acc + p.volume, 0);
  }, [positions]);

  // Handle Mode Switch
  const toggleMode = () => {
    if (positions.length > 0) {
      showToast('Cannot switch mode while open positions exist! Close trades first.');
      return;
    }
    const nextMode = mode === 'demo' ? 'real' : 'demo';
    setMode(nextMode);
    showToast(`Switched account mode to ${nextMode.toUpperCase()}`);
  };

  // Reset Demo Balance
  const resetDemoBalance = () => {
    setBalance(10000.0);
    setEquity(10000.0 + totalOpenProfit);
    showToast('Demo balance reset to $10,000.00');
  };

  // Close Position
  const closePosition = (ticket: number) => {
    const pos = positions.find(p => p.ticket === ticket);
    if (!pos) return;
    setPositions(prev => prev.filter(p => p.ticket !== ticket));
    setBalance(b => Number((b + pos.profit).toFixed(2)));
    setEquity(e => Number((e + pos.profit).toFixed(2)));
    showToast(`Closed Ticket #${ticket} on ${pos.symbol} (${pos.profit >= 0 ? '+' : ''}$${pos.profit.toFixed(2)})`);
    setLogs(l => [
      {
        id: String(Date.now()),
        time: new Date().toLocaleTimeString(),
        symbol: pos.symbol,
        text: `Full position close executed for Ticket #${ticket} at ${pos.currentPrice} (PnL: $${pos.profit.toFixed(2)})`,
        type: 'trade'
      },
      ...l
    ]);
  };

  // Modify Stop Loss
  const promptModifyStop = (ticket: number) => {
    const pos = positions.find(p => p.ticket === ticket);
    if (!pos) return;
    const newSl = prompt(`Enter new Stop Loss for ${pos.symbol} Ticket #${ticket} (Current SL: ${pos.sl}):`, String(pos.sl));
    if (newSl && !isNaN(Number(newSl)) && Number(newSl) > 0) {
      const slVal = Number(newSl);
      setPositions(prev => prev.map(p => p.ticket === ticket ? { ...p, sl: slVal } : p));
      showToast(`Stop Loss for #${ticket} modified to ${slVal}`);
      setLogs(l => [
        {
          id: String(Date.now()),
          time: new Date().toLocaleTimeString(),
          symbol: pos.symbol,
          text: `Modified Stop Loss on broker for Ticket #${ticket} to ${slVal}`,
          type: 'info'
        },
        ...l
      ]);
    }
  };

  // Toggle Model Enabled
  const toggleModel = (symbol: string) => {
    setModels(prev =>
      prev.map(m => {
        if (m.symbol === symbol) {
          const next = !m.enabled;
          showToast(`Model ${symbol} ${next ? 'ENABLED' : 'DISABLED'}`);
          return { ...m, enabled: next };
        }
        return m;
      })
    );
  };

  // Generate Training Prompt
  const generatePrompt = () => {
    const symList = selectedTrainSymbols.join(', ');
    return `# SENTINEL-FX AUTONOMOUS CFD MODEL TRAINING MISSION
Target Pairs: [${symList}]
Objective: GROW THE BALANCE (Compounding Capital Growth)
Platform: MetaTrader 5 (MT5) CFD via bot/mt5_broker.py
Account Margin Mode: Retail Hedging (concurrent multi-position support)

STRICT MANDATORY SAFETY RULE:
Every opened position MUST carry a server-side Stop Loss (sl > 0).

1. Data Source: Dukascopy (forex) / Deriv ticks_history (synthetics) from data/index.json.
2. News Confluence: news_archive.jsonl.gz (widen stops / stand down around high-impact news).
3. Strategy: Hybrid Committee (Trend, Momentum, Key Levels, Volatility ATR, Regime).
4. Freedom: Open multiple positions, scale in/out, trailing stop, break-even moves, early exit, or STAY_OUT.
5. Export: ONNX or pure JSON plan (analysis_plan.json, policy.json, risk_brain.json, manifest.json). NO PICKLE.
6. Verify: python3 -m sentinel_engine.check <bundle>.sfxmodel.zip
${publishPat ? `\nPUBLISH ACCESS:\nToken: ${publishPat}\nCommand: python3 tools/publish_model.py <bundle>.sfxmodel.zip --symbol <PAIR> --version 1 --token <PAT>` : ''}`;
  };

  const copyPromptToClipboard = () => {
    navigator.clipboard.writeText(generatePrompt());
    setPromptCopied(true);
    showToast('Playbook training prompt copied to clipboard!');
    setTimeout(() => setPromptCopied(false), 3000);
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans antialiased selection:bg-emerald-500 selection:text-slate-950">
      {/* Toast Notification */}
      {toastMessage && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 bg-slate-900 border border-emerald-500/50 text-emerald-400 px-5 py-3 rounded-xl shadow-2xl shadow-emerald-950/50 flex items-center gap-3 backdrop-blur-md text-sm font-medium animate-in fade-in slide-in-from-bottom-2">
          <Sparkles className="w-4 h-4 text-emerald-400" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* HEADER */}
      <header className="border-b border-slate-800 bg-slate-900/60 backdrop-blur-md sticky top-0 z-40 px-4 lg:px-8 py-3.5 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-emerald-600 to-teal-400 flex items-center justify-center font-bold text-slate-950 shadow-lg shadow-emerald-500/20">
            <TrendingUp className="w-5 h-5 text-slate-950" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-base font-bold tracking-tight text-white">SENTINEL-FX</h1>
              <span className="text-[10px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-2 py-0.5 rounded-full">
                MT5 CFD
              </span>
            </div>
            <p className="text-xs text-slate-400 font-mono">MOTIONSALT AUTONOMOUS HYBRID</p>
          </div>
        </div>

        {/* Global Controls & Status */}
        <div className="flex items-center flex-wrap gap-2 text-xs">
          {/* Mode Pill */}
          <button
            onClick={toggleMode}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-semibold transition-all border ${
              mode === 'real'
                ? 'bg-amber-500/20 text-amber-300 border-amber-500/40 hover:bg-amber-500/30'
                : 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40 hover:bg-emerald-500/30'
            }`}
          >
            {mode === 'real' ? <Lock className="w-3.5 h-3.5" /> : <Unlock className="w-3.5 h-3.5" />}
            <span>MODE: {mode.toUpperCase()}</span>
          </button>

          {/* Bot Power */}
          <button
            onClick={() => {
              setBotRunning(!botRunning);
              showToast(`Bot execution ${!botRunning ? 'RESUMED' : 'PAUSED'}`);
            }}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-semibold transition-all border ${
              botRunning
                ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30'
                : 'bg-slate-800 text-slate-400 border-slate-700'
            }`}
          >
            {botRunning ? <Play className="w-3.5 h-3.5 fill-current" /> : <Square className="w-3.5 h-3.5" />}
            <span>{botRunning ? 'BOT ACTIVE' : 'BOT PAUSED'}</span>
          </button>

          {/* Kill Switch */}
          <button
            onClick={() => {
              setKillSwitch(!killSwitch);
              showToast(killSwitch ? 'Kill switch DEACTIVATED' : 'EMERGENCY KILL SWITCH ACTIVATED');
            }}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-semibold transition-all border ${
              killSwitch
                ? 'bg-rose-600 text-white border-rose-500 animate-pulse'
                : 'bg-rose-500/10 text-rose-400 border-rose-500/30 hover:bg-rose-500/20'
            }`}
          >
            <AlertTriangle className="w-3.5 h-3.5" />
            <span>KILL SWITCH</span>
          </button>

          {/* Reset Demo $10k */}
          {mode === 'demo' && (
            <button
              onClick={resetDemoBalance}
              className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition"
              title="Top up demo account back to $10,000"
            >
              <RefreshCw className="w-3 h-3 text-slate-400" />
              <span>Reset $10k</span>
            </button>
          )}
        </div>
      </header>

      {/* NAVIGATION TABS */}
      <nav className="border-b border-slate-800 bg-slate-900/30 px-4 lg:px-8 py-2 overflow-x-auto flex gap-1.5 text-xs font-medium scrollbar-none">
        <button
          onClick={() => setActiveTab('dash')}
          className={`flex items-center gap-2 px-3.5 py-2 rounded-lg transition whitespace-nowrap ${
            activeTab === 'dash' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
          }`}
        >
          <Activity className="w-4 h-4" />
          <span>Dashboard & Pool</span>
        </button>

        <button
          onClick={() => setActiveTab('desk')}
          className={`flex items-center gap-2 px-3.5 py-2 rounded-lg transition whitespace-nowrap ${
            activeTab === 'desk' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
          }`}
        >
          <Layers className="w-4 h-4" />
          <span>CFD Order Desk ({positions.length})</span>
        </button>

        <button
          onClick={() => setActiveTab('models')}
          className={`flex items-center gap-2 px-3.5 py-2 rounded-lg transition whitespace-nowrap ${
            activeTab === 'models' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
          }`}
        >
          <Cpu className="w-4 h-4" />
          <span>Hybrid Models ({models.filter(m => m.enabled).length} Active)</span>
        </button>

        <button
          onClick={() => setActiveTab('risk')}
          className={`flex items-center gap-2 px-3.5 py-2 rounded-lg transition whitespace-nowrap ${
            activeTab === 'risk' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
          }`}
        >
          <Sliders className="w-4 h-4" />
          <span>Risk & Overrides</span>
        </button>

        <button
          onClick={() => setActiveTab('train')}
          className={`flex items-center gap-2 px-3.5 py-2 rounded-lg transition whitespace-nowrap ${
            activeTab === 'train' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
          }`}
        >
          <Sparkles className="w-4 h-4" />
          <span>Train AI Playbook</span>
        </button>

        <button
          onClick={() => setActiveTab('news')}
          className={`flex items-center gap-2 px-3.5 py-2 rounded-lg transition whitespace-nowrap ${
            activeTab === 'news' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
          }`}
        >
          <Calendar className="w-4 h-4" />
          <span>News Radar</span>
        </button>

        <button
          onClick={() => setActiveTab('logs')}
          className={`flex items-center gap-2 px-3.5 py-2 rounded-lg transition whitespace-nowrap ${
            activeTab === 'logs' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
          }`}
        >
          <Terminal className="w-4 h-4" />
          <span>Live Logs</span>
        </button>
      </nav>

      {/* MAIN CONTENT AREA */}
      <main className="flex-1 p-4 lg:p-8 max-w-7xl mx-auto w-full space-y-6">
        {/* TAB: DASHBOARD */}
        {activeTab === 'dash' && (
          <div className="space-y-6">
            {/* Top Stat Cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 lg:gap-4">
              <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-2xl relative overflow-hidden">
                <div className="text-slate-400 text-xs font-medium mb-1">Compounding Balance</div>
                <div className="text-2xl lg:text-3xl font-extrabold text-white tracking-tight font-mono">
                  ${balance.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                </div>
                <div className="text-[11px] text-emerald-400 mt-2 flex items-center gap-1 font-medium">
                  <TrendingUp className="w-3.5 h-3.5" />
                  <span>Pool Multiplier: 1.32x</span>
                </div>
              </div>

              <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-2xl relative overflow-hidden">
                <div className="text-slate-400 text-xs font-medium mb-1">Live Account Equity</div>
                <div className="text-2xl lg:text-3xl font-extrabold text-emerald-400 tracking-tight font-mono">
                  ${equity.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                </div>
                <div className="text-[11px] text-slate-400 mt-2 flex items-center gap-1">
                  <span>Open PnL: </span>
                  <span className={totalOpenProfit >= 0 ? 'text-emerald-400 font-bold' : 'text-rose-400 font-bold'}>
                    {totalOpenProfit >= 0 ? '+' : ''}${totalOpenProfit.toFixed(2)}
                  </span>
                </div>
              </div>

              <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-2xl relative overflow-hidden">
                <div className="text-slate-400 text-xs font-medium mb-1">Free Margin / Margin</div>
                <div className="text-xl lg:text-2xl font-bold text-white tracking-tight font-mono">
                  ${freeMargin.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                </div>
                <div className="text-[11px] text-slate-400 mt-2">
                  Margin: ${margin.toFixed(2)} | Lev 1:{leverage}
                </div>
              </div>

              <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-2xl relative overflow-hidden">
                <div className="text-slate-400 text-xs font-medium mb-1">MT5 Terminal & Runner</div>
                <div className="flex items-center gap-2 mt-1">
                  <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse"></span>
                  <span className="font-semibold text-white text-sm">CONNECTED</span>
                </div>
                <div className="text-[11px] text-slate-400 mt-2 font-mono">
                  {serverName} | {loginId}
                </div>
              </div>
            </div>

            {/* Zero-Gap Runner Handover Bar */}
            <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4 flex flex-col md:flex-row items-center justify-between gap-4">
              <div className="flex items-center gap-3 w-full md:w-auto">
                <div className="w-10 h-10 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400">
                  <Clock className="w-5 h-5" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-white">Actions Zero-Gap Runner</span>
                    <span className="text-[10px] bg-slate-800 text-slate-300 px-2 py-0.5 rounded font-mono">
                      {runnerId}
                    </span>
                  </div>
                  <div className="text-xs text-slate-400">
                    Handover window dispatches automatically at T-300s. Invariants: Server-side SL intact, 0 orphan positions.
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-3 w-full md:w-auto justify-between md:justify-end">
                <div className="text-right">
                  <div className="text-xs text-slate-400 font-medium">Session Wall Time Remaining</div>
                  <div className="text-base font-bold font-mono text-emerald-400">
                    {Math.floor(runnerTimeRemaining / 3600)}h {Math.floor((runnerTimeRemaining % 3600) / 60)}m {runnerTimeRemaining % 60}s
                  </div>
                </div>
                <div className="w-24 bg-slate-800 h-2 rounded-full overflow-hidden">
                  <div
                    className="bg-emerald-500 h-full rounded-full transition-all duration-1000"
                    style={{ width: `${(runnerTimeRemaining / 13800) * 100}%` }}
                  ></div>
                </div>
              </div>
            </div>

            {/* Active Positions Summary */}
            <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <Layers className="w-4 h-4 text-emerald-400" />
                  <h2 className="text-sm font-bold text-white tracking-wide">LIVE CFD POSITIONS ({positions.length})</h2>
                </div>
                <div className="text-xs text-slate-400 font-mono">
                  Total Exposure: {activeExposureLots.toFixed(2)} Lots
                </div>
              </div>

              {positions.length === 0 ? (
                <div className="text-center py-8 text-slate-500 text-xs">
                  No open positions currently. Models evaluating next completed M1 bar.
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs font-mono">
                    <thead>
                      <tr className="text-slate-400 border-b border-slate-800 pb-2">
                        <th className="py-2">Ticket</th>
                        <th className="py-2">Symbol</th>
                        <th className="py-2">Side</th>
                        <th className="py-2">Volume</th>
                        <th className="py-2">Open Price</th>
                        <th className="py-2">Current</th>
                        <th className="py-2">Stop Loss</th>
                        <th className="py-2">Take Profit</th>
                        <th className="py-2">Floating PnL</th>
                        <th className="py-2 text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60">
                      {positions.map(p => (
                        <tr key={p.ticket} className="hover:bg-slate-800/30 transition">
                          <td className="py-3 text-slate-400">#{p.ticket}</td>
                          <td className="py-3 font-bold text-white">{p.symbol}</td>
                          <td className="py-3">
                            <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                              p.side === 'BUY' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'
                            }`}>
                              {p.side}
                            </span>
                          </td>
                          <td className="py-3 text-slate-300">{p.volume.toFixed(2)}</td>
                          <td className="py-3 text-slate-300">{p.openPrice}</td>
                          <td className="py-3 text-white font-bold">{p.currentPrice}</td>
                          <td className="py-3 text-rose-400 flex items-center gap-1">
                            <Shield className="w-3 h-3 text-emerald-400" />
                            <span>{p.sl}</span>
                          </td>
                          <td className="py-3 text-emerald-400">{p.tp || '—'}</td>
                          <td className={`py-3 font-bold ${p.profit >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                            {p.profit >= 0 ? '+' : ''}${p.profit.toFixed(2)}
                          </td>
                          <td className="py-3 text-right space-x-1.5">
                            <button
                              onClick={() => promptModifyStop(p.ticket)}
                              className="px-2 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded text-[11px] transition"
                            >
                              Edit SL
                            </button>
                            <button
                              onClick={() => closePosition(p.ticket)}
                              className="px-2 py-1 bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 rounded text-[11px] transition"
                            >
                              Close
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        )}

        {/* TAB: CFD ORDER DESK */}
        {activeTab === 'desk' && (
          <div className="space-y-6">
            <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h2 className="text-base font-bold text-white">CFD Order Execution Desk</h2>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Live MT5 Hedging positions. Every order carries a mandatory server-side Stop Loss.
                  </p>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => {
                      // Simulate opening a test trade on DEMO
                      const newTicket = Math.floor(500000 + Math.random() * 50000);
                      const isForex = Math.random() > 0.5;
                      const sym = isForex ? 'EURUSD' : 'Volatility 10 Index';
                      const newPos: Position = {
                        ticket: newTicket,
                        symbol: sym,
                        side: 'BUY',
                        volume: isForex ? 0.05 : 0.2,
                        openPrice: isForex ? 1.08500 : 4963.12,
                        currentPrice: isForex ? 1.08505 : 4963.20,
                        sl: isForex ? 1.08250 : 4940.00,
                        tp: isForex ? 1.09000 : 4995.00,
                        profit: 0.50,
                        magic: 999300,
                        modelId: 'test_demo',
                        openTime: 'Just now'
                      };
                      setPositions(prev => [newPos, ...prev]);
                      showToast(`Dispatched test order on ${sym} with mandatory SL`);
                    }}
                    className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-slate-950 font-bold text-xs transition"
                  >
                    + Manual Demo Test Buy
                  </button>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
                <div className="bg-slate-950/60 p-3.5 rounded-xl border border-slate-800/80">
                  <div className="text-xs text-slate-400">Mandatory SL Enforcement</div>
                  <div className="text-emerald-400 font-bold text-sm mt-1 flex items-center gap-1.5">
                    <CheckCircle className="w-4 h-4" />
                    <span>100% Guaranteed Active</span>
                  </div>
                  <div className="text-[11px] text-slate-500 mt-1">Zero orders dispatched without broker SL</div>
                </div>

                <div className="bg-slate-950/60 p-3.5 rounded-xl border border-slate-800/80">
                  <div className="text-xs text-slate-400">Position Management Liberty</div>
                  <div className="text-white font-bold text-sm mt-1 flex items-center gap-1.5">
                    <Zap className="w-4 h-4 text-amber-400" />
                    <span>Scale in/out, Trailing, B/E</span>
                  </div>
                  <div className="text-[11px] text-slate-500 mt-1">Full liberty given to model reasoning</div>
                </div>

                <div className="bg-slate-950/60 p-3.5 rounded-xl border border-slate-800/80">
                  <div className="text-xs text-slate-400">Margin Maintenance</div>
                  <div className="text-emerald-400 font-bold text-sm mt-1 flex items-center gap-1.5">
                    <Shield className="w-4 h-4" />
                    <span>5,417% Margin Level</span>
                  </div>
                  <div className="text-[11px] text-slate-500 mt-1">Safe from 50% broker stop-out floor</div>
                </div>
              </div>

              {/* Positions List */}
              <div className="space-y-3">
                {positions.map(p => (
                  <div key={p.ticket} className="bg-slate-950/40 border border-slate-800 p-4 rounded-xl flex flex-wrap items-center justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <div className={`w-8 h-8 rounded-lg flex items-center justify-center font-bold text-xs ${
                        p.side === 'BUY' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'
                      }`}>
                        {p.side}
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-white text-sm">{p.symbol}</span>
                          <span className="text-[10px] bg-slate-800 text-slate-400 px-1.5 py-0.5 rounded font-mono">
                            #{p.ticket}
                          </span>
                        </div>
                        <div className="text-xs text-slate-400 font-mono mt-0.5">
                          {p.volume} Lots @ {p.openPrice} (Current: {p.currentPrice})
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-4 text-xs font-mono">
                      <div>
                        <div className="text-slate-500 text-[10px]">SERVER SL</div>
                        <div className="text-rose-400 font-bold">{p.sl}</div>
                      </div>
                      <div>
                        <div className="text-slate-500 text-[10px]">TAKE PROFIT</div>
                        <div className="text-emerald-400 font-bold">{p.tp || 'Open'}</div>
                      </div>
                      <div>
                        <div className="text-slate-500 text-[10px]">PROFIT</div>
                        <div className={`font-bold text-sm ${p.profit >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                          {p.profit >= 0 ? '+' : ''}${p.profit.toFixed(2)}
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => promptModifyStop(p.ticket)}
                        className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg text-xs transition"
                      >
                        Modify Stop
                      </button>
                      <button
                        onClick={() => closePosition(p.ticket)}
                        className="px-3 py-1.5 bg-rose-600 hover:bg-rose-500 text-white font-medium rounded-lg text-xs transition"
                      >
                        Close Position
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* TAB: HYBRID MODELS */}
        {activeTab === 'models' && (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-base font-bold text-white">Autonomous Per-Pair Hybrid Models</h2>
                <p className="text-xs text-slate-400 mt-0.5">
                  Single Purpose: GROW THE BALANCE. Each model trades its own allocated session share.
                </p>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {models.map(m => (
                <div
                  key={m.symbol}
                  className={`border rounded-2xl p-5 transition flex flex-col justify-between ${
                    m.enabled
                      ? 'bg-slate-900/80 border-slate-800'
                      : 'bg-slate-900/40 border-slate-800/60 opacity-70'
                  }`}
                >
                  <div>
                    <div className="flex items-start justify-between gap-2 mb-3">
                      <div>
                        <h3 className="font-bold text-white text-base">{m.name}</h3>
                        <div className="flex items-center gap-2 mt-1">
                          <span className="text-[10px] font-mono bg-slate-800 text-slate-300 px-2 py-0.5 rounded">
                            v{m.version}
                          </span>
                          <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                            m.category === 'forex' ? 'bg-indigo-500/20 text-indigo-300' : 'bg-purple-500/20 text-purple-300'
                          }`}>
                            {m.category.toUpperCase()}
                          </span>
                        </div>
                      </div>

                      {/* Enable/Disable Toggle */}
                      <button
                        onClick={() => toggleModel(m.symbol)}
                        className={`text-xs px-2.5 py-1 rounded-lg font-bold transition ${
                          m.enabled
                            ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                            : 'bg-slate-800 text-slate-400 border border-slate-700'
                        }`}
                      >
                        {m.enabled ? 'ACTIVE' : 'DISABLED'}
                      </button>
                    </div>

                    <div className="grid grid-cols-2 gap-2 my-4 text-xs font-mono">
                      <div className="bg-slate-950/60 p-2.5 rounded-xl border border-slate-800/50">
                        <div className="text-slate-500 text-[10px]">Growth Multiple</div>
                        <div className="text-emerald-400 font-bold text-sm mt-0.5">+{m.growthMultiple}x</div>
                      </div>
                      <div className="bg-slate-950/60 p-2.5 rounded-xl border border-slate-800/50">
                        <div className="text-slate-500 text-[10px]">Max Drawdown</div>
                        <div className="text-slate-300 font-bold text-sm mt-0.5">{m.maxDrawdown}%</div>
                      </div>
                      <div className="bg-slate-950/60 p-2.5 rounded-xl border border-slate-800/50">
                        <div className="text-slate-500 text-[10px]">Confluence Score</div>
                        <div className="text-white font-bold text-sm mt-0.5">{m.confluenceScore}%</div>
                      </div>
                      <div className="bg-slate-950/60 p-2.5 rounded-xl border border-slate-800/50">
                        <div className="text-slate-500 text-[10px]">Last Action</div>
                        <div className="text-amber-400 font-bold text-sm mt-0.5">{m.lastAction}</div>
                      </div>
                    </div>
                  </div>

                  <div className="border-t border-slate-800/80 pt-3 flex items-center justify-between text-xs text-slate-400">
                    <span className="text-[11px]">Updated {m.lastActionTime}</span>
                    <span className="text-emerald-400 font-medium text-[11px]">
                      {m.openPositionsCount > 0 ? `${m.openPositionsCount} Open Pos` : 'Flat'}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* TAB: RISK & OWNER OVERRIDES */}
        {activeTab === 'risk' && (
          <div className="max-w-3xl mx-auto space-y-6">
            <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6">
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400">
                  <Sliders className="w-5 h-5" />
                </div>
                <div>
                  <h2 className="text-base font-bold text-white">Owner Overrides (Default OFF)</h2>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Outside the model's reasoning. Models trade freely unless an enabled override limits them.
                  </p>
                </div>
              </div>

              <div className="space-y-6 divide-y divide-slate-800">
                {/* Max Exposure */}
                <div className="pt-4 flex items-center justify-between gap-4">
                  <div>
                    <div className="text-sm font-semibold text-white">Max Total Exposure Cap</div>
                    <div className="text-xs text-slate-400 mt-0.5">
                      Caps cumulative open lot volume across all pairs.
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    {overrides.maxExposureEnabled && (
                      <input
                        type="number"
                        step="0.1"
                        value={overrides.maxExposureLots}
                        onChange={e => setOverrides({ ...overrides, maxExposureLots: parseFloat(e.target.value) || 0.1 })}
                        className="w-20 bg-slate-950 border border-slate-700 px-2.5 py-1 rounded-lg text-sm font-mono text-white text-right"
                      />
                    )}
                    <button
                      onClick={() => setOverrides({ ...overrides, maxExposureEnabled: !overrides.maxExposureEnabled })}
                      className={`px-3 py-1.5 rounded-lg text-xs font-bold transition ${
                        overrides.maxExposureEnabled
                          ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                          : 'bg-slate-800 text-slate-400 border border-slate-700'
                      }`}
                    >
                      {overrides.maxExposureEnabled ? 'ENABLED' : 'OFF'}
                    </button>
                  </div>
                </div>

                {/* Daily Take Profit */}
                <div className="pt-4 flex items-center justify-between gap-4">
                  <div>
                    <div className="text-sm font-semibold text-white">Daily Take Profit Target</div>
                    <div className="text-xs text-slate-400 mt-0.5">
                      Shuts down trading when session profit reaches target.
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    {overrides.dailyTpEnabled && (
                      <div className="flex items-center gap-1">
                        <span className="text-slate-400 text-xs">$</span>
                        <input
                          type="number"
                          step="50"
                          value={overrides.dailyTpUsd}
                          onChange={e => setOverrides({ ...overrides, dailyTpUsd: parseFloat(e.target.value) || 100 })}
                          className="w-24 bg-slate-950 border border-slate-700 px-2.5 py-1 rounded-lg text-sm font-mono text-white text-right"
                        />
                      </div>
                    )}
                    <button
                      onClick={() => setOverrides({ ...overrides, dailyTpEnabled: !overrides.dailyTpEnabled })}
                      className={`px-3 py-1.5 rounded-lg text-xs font-bold transition ${
                        overrides.dailyTpEnabled
                          ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                          : 'bg-slate-800 text-slate-400 border border-slate-700'
                      }`}
                    >
                      {overrides.dailyTpEnabled ? 'ENABLED' : 'OFF'}
                    </button>
                  </div>
                </div>

                {/* Daily Stop Loss */}
                <div className="pt-4 flex items-center justify-between gap-4">
                  <div>
                    <div className="text-sm font-semibold text-white">Daily Stop Loss Threshold</div>
                    <div className="text-xs text-slate-400 mt-0.5">
                      Shuts down models for the day if drawdown reaches limit.
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    {overrides.dailySlEnabled && (
                      <div className="flex items-center gap-1">
                        <span className="text-slate-400 text-xs">$</span>
                        <input
                          type="number"
                          step="50"
                          value={overrides.dailySlUsd}
                          onChange={e => setOverrides({ ...overrides, dailySlUsd: parseFloat(e.target.value) || 100 })}
                          className="w-24 bg-slate-950 border border-slate-700 px-2.5 py-1 rounded-lg text-sm font-mono text-white text-right"
                        />
                      </div>
                    )}
                    <button
                      onClick={() => setOverrides({ ...overrides, dailySlEnabled: !overrides.dailySlEnabled })}
                      className={`px-3 py-1.5 rounded-lg text-xs font-bold transition ${
                        overrides.dailySlEnabled
                          ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                          : 'bg-slate-800 text-slate-400 border border-slate-700'
                      }`}
                    >
                      {overrides.dailySlEnabled ? 'ENABLED' : 'OFF'}
                    </button>
                  </div>
                </div>

                {/* Repeat Daily */}
                <div className="pt-4 flex items-center justify-between gap-4">
                  <div>
                    <div className="text-sm font-semibold text-white">Repeat Daily at Lagos Midnight</div>
                    <div className="text-xs text-slate-400 mt-0.5">
                      Automatically resets daily TP/SL limits each 00:00 UTC+1 for uninterrupted compounding.
                    </div>
                  </div>
                  <button
                    onClick={() => setOverrides({ ...overrides, repeatDaily: !overrides.repeatDaily })}
                    className={`px-3 py-1.5 rounded-lg text-xs font-bold transition ${
                      overrides.repeatDaily
                        ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                        : 'bg-slate-800 text-slate-400 border border-slate-700'
                    }`}
                  >
                    {overrides.repeatDaily ? 'REPEAT ON' : 'OFF'}
                  </button>
                </div>
              </div>

              <div className="mt-6 pt-4 border-t border-slate-800 flex justify-end">
                <button
                  onClick={() => showToast('Owner overrides synchronized with Cloudflare D1')}
                  className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-slate-950 font-bold rounded-xl text-xs transition"
                >
                  Save &amp; Apply Overrides
                </button>
              </div>
            </div>
          </div>
        )}

        {/* TAB: TRAIN AI PLAYBOOK (TRAINUI) */}
        {activeTab === 'train' && (
          <div className="space-y-6">
            <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6">
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-xl bg-purple-500/10 border border-purple-500/20 flex items-center justify-center text-purple-400">
                  <Sparkles className="w-5 h-5" />
                </div>
                <div>
                  <h2 className="text-base font-bold text-white">CFD AI Training Playbook Generator</h2>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Generate the self-contained prompt to paste into any LLM or AI trainer. Single purpose: GROW THE BALANCE.
                  </p>
                </div>
              </div>

              {/* Pair Multi-Select */}
              <div className="mb-5">
                <label className="text-xs font-semibold text-slate-300 block mb-2">
                  Select Instruments to Train:
                </label>
                <div className="flex flex-wrap gap-2">
                  {['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCAD', 'USDCHF', 'Volatility 10 Index', 'Volatility 100 Index'].map(sym => {
                    const sel = selectedTrainSymbols.includes(sym);
                    return (
                      <button
                        key={sym}
                        onClick={() => {
                          if (sel) {
                            setSelectedTrainSymbols(selectedTrainSymbols.filter(s => s !== sym));
                          } else {
                            setSelectedTrainSymbols([...selectedTrainSymbols, sym]);
                          }
                        }}
                        className={`px-3 py-1.5 rounded-lg text-xs font-mono font-medium transition ${
                          sel
                            ? 'bg-purple-600 text-white shadow-md shadow-purple-900/40'
                            : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
                        }`}
                      >
                        {sym}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Optional PAT */}
              <div className="mb-5">
                <label className="text-xs font-semibold text-slate-300 block mb-1">
                  Fine-Grained GitHub PAT (Optional - In Memory Only):
                </label>
                <input
                  type="password"
                  placeholder="github_pat_... (Only if AI should publish directly)"
                  value={publishPat}
                  onChange={e => setPublishPat(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 px-3.5 py-2 rounded-xl text-xs font-mono text-white focus:outline-none focus:border-purple-500"
                />
                <p className="text-[11px] text-slate-500 mt-1">
                  Kept in memory only. Allows the training AI to upload the validated .sfxmodel.zip bundle directly.
                </p>
              </div>

              {/* Generated Prompt Preview */}
              <div className="bg-slate-950 border border-slate-800 rounded-xl p-4 font-mono text-xs text-slate-300 relative group">
                <div className="flex items-center justify-between mb-2 pb-2 border-b border-slate-800 text-slate-400 text-[11px]">
                  <span>GENERATED PLAYBOOK PROMPT</span>
                  <button
                    onClick={copyPromptToClipboard}
                    className="flex items-center gap-1.5 px-3 py-1 rounded bg-purple-600 hover:bg-purple-500 text-white font-medium transition"
                  >
                    {promptCopied ? <CheckCircle className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                    <span>{promptCopied ? 'Copied!' : 'Copy Prompt'}</span>
                  </button>
                </div>
                <pre className="max-h-64 overflow-y-auto whitespace-pre-wrap text-[11px] text-slate-400 scrollbar-thin">
                  {generatePrompt()}
                </pre>
              </div>
            </div>
          </div>
        )}

        {/* TAB: NEWS RADAR */}
        {activeTab === 'news' && (
          <div className="space-y-6">
            <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6">
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400">
                  <Calendar className="w-5 h-5" />
                </div>
                <div>
                  <h2 className="text-base font-bold text-white">Economic Calendar &amp; High-Impact News Radar</h2>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Refreshed hourly from nfs.faireconomy.media. Models widen stops or stand down before releases.
                  </p>
                </div>
              </div>

              <div className="space-y-3">
                {newsEvents.map(evt => (
                  <div key={evt.id} className="bg-slate-950/60 border border-slate-800 p-4 rounded-xl flex flex-wrap items-center justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-lg bg-rose-500/20 text-rose-400 flex flex-col items-center justify-center font-bold text-xs">
                        <span>{evt.currency}</span>
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-white text-sm">{evt.title}</span>
                          <span className="text-[10px] bg-rose-500/20 text-rose-300 font-bold px-1.5 py-0.5 rounded">
                            {evt.impact}
                          </span>
                        </div>
                        <div className="text-xs text-slate-400 font-mono mt-0.5">
                          Scheduled: {evt.time} {evt.forecast && `| Forecast: ${evt.forecast}`} {evt.previous && `| Prev: ${evt.previous}`}
                        </div>
                      </div>
                    </div>

                    <div className="text-right">
                      <div className="text-[11px] text-emerald-400 font-medium">
                        Model Reaction
                      </div>
                      <div className="text-xs text-slate-300 max-w-xs mt-0.5">
                        {evt.actionTaken}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* TAB: LIVE LOGS */}
        {activeTab === 'logs' && (
          <div className="space-y-6">
            <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-slate-800 flex items-center justify-center text-slate-300">
                    <Terminal className="w-5 h-5" />
                  </div>
                  <div>
                    <h2 className="text-base font-bold text-white">Live MT5 CFD Decision Stream</h2>
                    <p className="text-xs text-slate-400 mt-0.5">
                      Real-time decisions with magic number tags (sfx:&lt;model_id&gt;:&lt;decision_id&gt;)
                    </p>
                  </div>
                </div>
                <button
                  onClick={() => {
                    const testLog = {
                      id: String(Date.now()),
                      time: new Date().toLocaleTimeString(),
                      symbol: 'EURUSD',
                      text: `Health tick 0.024s. Account balance $${balance.toFixed(2)}, free margin $${freeMargin.toFixed(2)}. No open drawdown.`,
                      type: 'info' as const
                    };
                    setLogs(prev => [testLog, ...prev]);
                  }}
                  className="px-3 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs font-mono transition"
                >
                  Refresh Logs
                </button>
              </div>

              <div className="bg-slate-950 border border-slate-800/80 rounded-xl p-4 font-mono text-xs max-h-96 overflow-y-auto space-y-2.5">
                {logs.map(log => (
                  <div key={log.id} className="flex items-start gap-2.5 leading-relaxed">
                    <span className="text-slate-500 shrink-0">[{log.time}]</span>
                    <span className="font-bold text-indigo-400 shrink-0">[{log.symbol}]</span>
                    <span className={log.type === 'trade' ? 'text-emerald-400 font-semibold' : 'text-slate-300'}>
                      {log.text}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </main>

      {/* FOOTER */}
      <footer className="border-t border-slate-800 py-4 px-6 text-center text-xs text-slate-500 font-mono">
        SENTINEL-FX CFD · Brand MOTIONSALT · Deriv MT5 Linux Bridge · Zero-Gap Autonomous Supervisor
      </footer>
    </div>
  );
}
