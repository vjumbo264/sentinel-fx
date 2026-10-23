export function toast(msg, type = 'info') {
  const container = document.getElementById('toasts');
  if (!container) return;

  const el = document.createElement('div');
  el.style.cssText = `
    background: var(--bg-card);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 10px 16px;
    border-radius: var(--radius);
    font-size: 13px;
    font-weight: 500;
    max-width: 320px;
    box-shadow: 0 10px 25px rgba(0,0,0,0.3);
    pointer-events: auto;
    border-left: 4px solid ${
      type === 'error' ? 'var(--loss)' :
      type === 'success' ? 'var(--profit)' :
      type === 'warn' ? 'var(--warning)' : 'var(--accent)'
    };
    transition: opacity 0.2s, transform 0.2s;
  `;
  el.textContent = msg;
  container.appendChild(el);

  setTimeout(() => {
    el.style.opacity = '0';
    el.style.transform = 'translateY(10px)';
    setTimeout(() => el.remove(), 250);
  }, 3500);
}
