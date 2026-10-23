import { api } from '../api.js';

/** Real Actions training status; smoke evidence never counts as pair progress. */
export const trainingView = {
  timer: null,
  generation: 0,
  async render(container) {
    this.destroy();
    this.container = container;
    const generation = this.generation;
    container.innerHTML = `
      <section class="card" aria-labelledby="training-title" style="padding:var(--space-4)">
        <h2 id="training-title" class="card-title">TRAINING</h2>
        <p style="color:var(--text-secondary)">Per-pair PPO training on GitHub Actions</p>
        <p id="training-message" role="status" aria-live="polite">Loading real training state…</p>
        <button id="training-retry" class="btn btn-ghost btn-sm" type="button">Refresh training status</button>
        <div id="training-data" hidden>
          <h3 id="training-active"></h3>
          <p id="training-status"></p>
          <progress id="training-progress" aria-label="Active pair training progress" style="width:100%;height:20px"></progress>
          <p id="training-progress-label"></p>
          <dl>
            <dt>Last checkpoint</dt><dd id="training-checkpoint"></dd>
            <dt>Retrain cycle</dt><dd id="training-cycle"></dd>
            <dt>Next retrain</dt><dd id="training-next"></dd>
          </dl>
          <h3>Pair queue</h3>
          <ul id="training-queue" aria-label="Training pair queue" style="list-style:none;padding:0"></ul>
        </div>
      </section>`;
    this.message = container.querySelector('#training-message');
    this.refreshButton = container.querySelector('#training-retry');
    this.refreshButton.onclick = () => this.refresh(generation);
    this.onVisible = () => { if (!document.hidden) this.refresh(generation); };
    document.addEventListener('visibilitychange', this.onVisible);
    await this.refresh(generation);
  },

  async refresh(generation = this.generation) {
    if (generation !== this.generation || this.loading || !this.container?.isConnected) return;
    clearTimeout(this.timer);
    this.loading = true;
    this.refreshButton.disabled = true;
    try {
      const state = await api.request('/api/training/state');
      if (generation !== this.generation || !this.container?.isConnected) return;
      if (!state || !Array.isArray(state.queue)) throw new Error('Training state has no valid queue');
      const text = (id, value) => { this.container.querySelector(`#${id}`).textContent = value; };
      const count = (v) => typeof v === 'number' && Number.isFinite(v) && v >= 0 ? v : null;
      const done = count(state.total_steps_done), target = count(state.total_steps_target);
      const active = typeof state.active_pair === 'string' ? state.active_pair : null;
      const waiting = state.next_retrain_after_utc && Date.parse(state.next_retrain_after_utc) > Date.now();
      const status = waiting ? 'Waiting for next retrain cycle' : state.status || (done > 0 ? 'Training / checkpointed' : 'Queued');
      text('training-active', active || 'No active pair');
      text('training-status', state.last_error && state.status === 'blocked' ? `Blocked: ${state.last_error}` : status);
      const progress = this.container.querySelector('#training-progress');
      if (done !== null && target > 0) {
        progress.max = target;
        progress.value = Math.min(done, target);
        text('training-progress-label', `${done.toLocaleString()} / ${target.toLocaleString()} steps (${(Math.min(1,done/target)*100).toFixed(1)}%)`);
      } else {
        progress.removeAttribute('value');
        text('training-progress-label', 'Training progress unavailable');
      }
      const date = (value, empty) => value && Number.isFinite(Date.parse(value)) ? new Date(value).toLocaleString() : empty;
      text('training-checkpoint', date(state.last_checkpoint_utc, 'No real training checkpoint yet'));
      text('training-cycle', count(state.retrain_cycle) ?? 'Not available');
      text('training-next', date(state.next_retrain_after_utc, 'After current cycle completes'));
      const list = this.container.querySelector('#training-queue');
      list.replaceChildren();
      const completed = new Set(Array.isArray(state.pairs_done) ? state.pairs_done : []);
      for (const pair of state.queue) {
        const li = document.createElement('li');
        const isDone = completed.has(pair), isActive = pair === active && !isDone && !waiting;
        const label = isDone ? 'done' : isActive ? status.toLowerCase() : 'pending';
        li.textContent = `${isDone ? '✅' : isActive ? '🔄' : '⏳'} ${pair} — ${label}`;
        li.style.padding = 'var(--space-2) 0';
        list.append(li);
      }
      if (!state.queue.length) {
        const li = document.createElement('li'); li.textContent = 'No pairs queued for training.'; list.append(li);
      }
      this.container.querySelector('#training-data').hidden = false;
      this.message.textContent = `Live repository state · refreshed ${new Date().toLocaleTimeString()}`;
    } catch (error) {
      if (generation === this.generation && this.message) {
        this.message.textContent = `Training state unavailable: ${error.message}. Previously displayed values may be stale.`;
      }
    } finally {
      if (generation === this.generation) {
        this.loading = false;
        if (this.refreshButton) this.refreshButton.disabled = false;
        this.timer = setTimeout(() => {
          if (document.hidden) { this.loading = false; this.timer = setTimeout(() => this.refresh(generation), 30000); }
          else this.refresh(generation);
        }, 30000);
      }
    }
  },

  destroy() {
    clearTimeout(this.timer);
    if (this.onVisible) document.removeEventListener('visibilitychange', this.onVisible);
    this.generation++;
    this.loading = false;
    this.container = null;
  }
};
