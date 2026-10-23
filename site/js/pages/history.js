import { api } from '../api.js';
import { toast } from '../toast.js';

export async function historyPage() {
  const root = document.getElementById('page-container');
  if (!root) return;

  root.innerHTML = `<div style="text-align:center; padding:40px; color:var(--text-2);">Loading trade history records...</div>`;

  let allTrades = [];
  let filteredTrades = [];
  let currentPage = 1;
  const pageSize = 50;

  // Filter states
  let selectedPair = 'ALL';
  let selectedOutcome = 'ALL';
  let fromDate = '';
  let toDate = '';

  try {
    const res = await api.getTrades().catch(() => ({ trades: [] }));
    const raw = Array.isArray(res) ? res : (res.trades || []);
    // Filter closed trades only
    allTrades = raw.filter(t => t.close_utc || t.closed_at || t.close_time);
    allTrades.sort((a, b) => {
      const ta = new Date(a.close_utc || a.closed_at || a.time || 0).getTime();
      const tb = new Date(b.close_utc || b.closed_at || b.time || 0).getTime();
      return tb - ta;
    });
    applyFilters();
  } catch(err) {
    toast(err.message || 'Error loading trades', 'error');
  }

  function tradePnl(t) {
    return Number(t.pnl ?? t.net_pnl ?? t.profit ?? 0);
  }

  function applyFilters() {
    filteredTrades = allTrades.filter(t => {
      const pair = (t.symbol || t.pair || '').toUpperCase();
      if (selectedPair !== 'ALL' && pair !== selectedPair) return false;

      const pnl = tradePnl(t);
      if (selectedOutcome === 'WIN' && pnl <= 0) return false;
      if (selectedOutcome === 'LOSS' && pnl >= 0) return false;

      const tDate = (t.close_utc || t.closed_at || t.open_utc || '').slice(0, 10);
      if (fromDate && tDate && tDate < fromDate) return false;
      if (toDate && tDate && tDate > toDate) return false;

      return true;
    });
    currentPage = 1;
    render();
  }

  function render() {
    // Unique pairs for filter dropdown
    const pairs = Array.from(new Set(allTrades.map(t => (t.symbol || t.pair || '').toUpperCase()).filter(Boolean)));

    // Calculate Summary Metrics
    const totalTrades = filteredTrades.length;
    const wins = filteredTrades.filter(t => tradePnl(t) > 0);
    const losses = filteredTrades.filter(t => tradePnl(t) < 0);
    const winRate = totalTrades > 0 ? ((wins.length / totalTrades) * 100).toFixed(1) : '0.0';

    const netPnl = filteredTrades.reduce((acc, t) => acc + tradePnl(t), 0);
    const grossProfit = wins.reduce((acc, t) => acc + tradePnl(t), 0);
    const grossLoss = Math.abs(losses.reduce((acc, t) => acc + tradePnl(t), 0));
    const profitFactor = grossLoss > 0 ? (grossProfit / grossLoss).toFixed(2) : (grossProfit > 0 ? '∞' : '0.00');

    // Pagination
    const totalPages = Math.max(1, Math.ceil(filteredTrades.length / pageSize));
    const startIdx = (currentPage - 1) * pageSize;
    const pageTrades = filteredTrades.slice(startIdx, startIdx + pageSize);

    root.innerHTML = `
      <!-- SUMMARY KPI METRICS -->
      <div class="grid-4" style="margin-bottom:20px;">
        <div class="card" style="margin-bottom:0; padding:16px;">
          <div style="font-size:11px; font-weight:600; color:var(--text-3); text-transform:uppercase;">Total Trades</div>
          <div class="tabular" style="font-size:24px; font-weight:800; color:var(--text); margin-top:4px;">
            ${totalTrades.toLocaleString()}
          </div>
        </div>

        <div class="card" style="margin-bottom:0; padding:16px;">
          <div style="font-size:11px; font-weight:600; color:var(--text-3); text-transform:uppercase;">Win Rate</div>
          <div class="tabular" style="font-size:24px; font-weight:800; color:var(--profit); margin-top:4px;">
            ${winRate}%
          </div>
          <div style="font-size:11px; color:var(--text-3); margin-top:2px;">${wins.length}W / ${losses.length}L</div>
        </div>

        <div class="card" style="margin-bottom:0; padding:16px;">
          <div style="font-size:11px; font-weight:600; color:var(--text-3); text-transform:uppercase;">Net Realized P&L</div>
          <div class="tabular" style="font-size:24px; font-weight:800; color:${netPnl >= 0 ? 'var(--profit)' : 'var(--loss)'}; margin-top:4px;">
            ${netPnl >= 0 ? '+' : ''}$${netPnl.toFixed(2)}
          </div>
        </div>

        <div class="card" style="margin-bottom:0; padding:16px;">
          <div style="font-size:11px; font-weight:600; color:var(--text-3); text-transform:uppercase;">Profit Factor</div>
          <div class="tabular" style="font-size:24px; font-weight:800; color:var(--text); margin-top:4px;">
            ${profitFactor}
          </div>
          <div style="font-size:11px; color:var(--text-3); margin-top:2px;">Gross P/L: $${grossProfit.toFixed(0)} / $${grossLoss.toFixed(0)}</div>
        </div>
      </div>

      <!-- FILTER CONTROLS & EXPORT -->
      <div class="card">
        <div style="display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:12px;">
          <div style="display:flex; flex-wrap:wrap; align-items:center; gap:10px;">
            <div>
              <select id="pair-filter" style="min-width:130px;">
                <option value="ALL">All Pairs</option>
                ${pairs.map(p => `<option value="${p}" ${selectedPair === p ? 'selected' : ''}>${p}</option>`).join('')}
              </select>
            </div>

            <div>
              <select id="outcome-filter" style="min-width:110px;">
                <option value="ALL" ${selectedOutcome === 'ALL' ? 'selected' : ''}>All Results</option>
                <option value="WIN" ${selectedOutcome === 'WIN' ? 'selected' : ''}>Wins Only</option>
                <option value="LOSS" ${selectedOutcome === 'LOSS' ? 'selected' : ''}>Losses Only</option>
              </select>
            </div>

            <div style="display:flex; align-items:center; gap:6px; font-size:12px; color:var(--text-2);">
              <span>From:</span>
              <input type="date" id="from-date" value="${fromDate}" style="font-size:12px; padding:6px 10px;" />
              <span>To:</span>
              <input type="date" id="to-date" value="${toDate}" style="font-size:12px; padding:6px 10px;" />
            </div>
          </div>

          <button id="export-csv-btn" class="btn btn-ghost btn-sm">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            <span>Export CSV</span>
          </button>
        </div>
      </div>

      <!-- TRADES TABLE -->
      <div class="card">
        <div class="card-header">
          <div class="card-title">Closed Trade History (${filteredTrades.length} trades)</div>
          <div style="font-size:12px; color:var(--text-2);">
            Page ${currentPage} of ${totalPages}
          </div>
        </div>

        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Close Date / Time</th>
                <th>Pair</th>
                <th>Side</th>
                <th>Lots</th>
                <th>Net P&L</th>
                <th>Result</th>
                <th>Duration / Reason</th>
              </tr>
            </thead>
            <tbody>
              ${
                pageTrades.length === 0
                  ? `
                    <tr>
                      <td colspan="7" style="text-align:center; padding:36px; color:var(--text-2);">
                        No trades match the selected filters.
                      </td>
                    </tr>
                  `
                  : pageTrades.map(t => {
                    const pnl = tradePnl(t);
                    const isWin = pnl > 0;
                    const dateStr = t.close_utc || t.closed_at || t.open_utc || t.time || '-';
                    return `
                      <tr>
                        <td class="tabular" style="color:var(--text-2); font-size:12px;">${dateStr.slice(0, 19).replace('T', ' ')}</td>
                        <td><strong>${t.symbol || t.pair || '-'}</strong></td>
                        <td>
                          <span class="badge ${t.side === 'buy' || t.side === 'BUY' ? 'badge-profit' : 'badge-loss'}">
                            ${(t.side || 'BUY').toUpperCase()}
                          </span>
                        </td>
                        <td class="tabular">${t.stake ?? t.volume ?? t.lots ?? 0.01}</td>
                        <td class="tabular font-bold ${isWin ? 'badge-profit' : 'badge-loss'}" style="font-size:13px;">
                          ${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}
                        </td>
                        <td>
                          <span class="badge ${isWin ? 'badge-profit' : 'badge-loss'}">
                            ${isWin ? 'WIN' : 'LOSS'}
                          </span>
                        </td>
                        <td style="font-size:12px; color:var(--text-3);">
                          ${t.reason || t.exit_reason || t.comment || 'Agent Closed'}
                        </td>
                      </tr>
                    `;
                  }).join('')
              }
            </tbody>
          </table>
        </div>

        <!-- PAGINATION -->
        ${
          totalPages > 1
            ? `
              <div style="display:flex; justify-content:space-between; align-items:center; margin-top:16px;">
                <button id="prev-page-btn" class="btn btn-ghost btn-sm" ${currentPage <= 1 ? 'disabled' : ''}>
                  Previous
                </button>
                <span style="font-size:12px; color:var(--text-2);">
                  Page ${currentPage} of ${totalPages}
                </span>
                <button id="next-page-btn" class="btn btn-ghost btn-sm" ${currentPage >= totalPages ? 'disabled' : ''}>
                  Next
                </button>
              </div>
            `
            : ''
        }
      </div>
    `;

    bindEvents();
  }

  function bindEvents() {
    document.getElementById('pair-filter')?.addEventListener('change', (e) => {
      selectedPair = e.target.value;
      applyFilters();
    });

    document.getElementById('outcome-filter')?.addEventListener('change', (e) => {
      selectedOutcome = e.target.value;
      applyFilters();
    });

    document.getElementById('from-date')?.addEventListener('change', (e) => {
      fromDate = e.target.value;
      applyFilters();
    });

    document.getElementById('to-date')?.addEventListener('change', (e) => {
      toDate = e.target.value;
      applyFilters();
    });

    document.getElementById('prev-page-btn')?.addEventListener('click', () => {
      if (currentPage > 1) {
        currentPage--;
        render();
      }
    });

    document.getElementById('next-page-btn')?.addEventListener('click', () => {
      const totalPages = Math.ceil(filteredTrades.length / pageSize);
      if (currentPage < totalPages) {
        currentPage++;
        render();
      }
    });

    document.getElementById('export-csv-btn')?.addEventListener('click', () => {
      exportCsv();
    });
  }

  function exportCsv() {
    if (filteredTrades.length === 0) {
      toast('No trades to export', 'warn');
      return;
    }

    const headers = ['Close Time', 'Pair', 'Side', 'Lots', 'Open Price', 'Close Price', 'Net PnL', 'Exit Reason'];
    const rows = filteredTrades.map(t => [
      t.close_utc || t.closed_at || '',
      t.symbol || t.pair || '',
      t.side || '',
      t.stake ?? t.volume ?? t.lots ?? '',
      t.open_price || '',
      t.close_price || '',
      tradePnl(t),
      t.reason || t.exit_reason || t.comment || ''
    ]);

    const csvContent = 'data:text/csv;charset=utf-8,' +
      [headers.join(','), ...rows.map(r => r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(','))].join('\n');

    const encodedUri = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute('download', `sentinel_trades_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    link.remove();
    toast('CSV downloaded successfully', 'success');
  }

  render();
}
