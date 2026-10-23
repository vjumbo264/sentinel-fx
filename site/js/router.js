/**
 * SENTINEL-FX · Client-Side Hash Router with Auth Gate
 * Deep-linkable hash routes, scroll position restoration, active state sync,
 * and first-run login gating.
 */

import { store } from "./store.js";
import { trainingView } from "./pages/training.js";
import { loginView } from "./pages/login.js";

class Router {
  constructor() {
    this.routes = {};
    this.currentRoute = null;
    this.scrollPositions = {};

    window.addEventListener("hashchange", () => this.handleRoute());
    window.addEventListener("load", () => this.handleRoute());
  }

  register(path, pageComponent) {
    this.routes[path] = pageComponent;
  }

  navigate(path) {
    window.location.hash = path.startsWith("#") ? path : `#${path}`;
  }

  getCleanRoute() {
    const hash = window.location.hash.replace(/^#\/?/, "").split("?")[0];
    return hash || "dash";
  }

  async handleRoute() {
    const appView = document.getElementById("app-view");
    if (!appView) return;
    if (this.activePage && typeof this.activePage.destroy === "function") this.activePage.destroy();
    this.activePage = null;

    // Gate unauthenticated sessions
    if (!store.state.isAuth) {
      this.currentRoute = "login";
      this.updateNavLinks("login");
      this.setNavVisibility(false);
      await loginView.render(appView);
      window.scrollTo({ top: 0, behavior: "instant" });
      return;
    }

    this.setNavVisibility(true);

    if (this.currentRoute && this.currentRoute !== "login") {
      this.scrollPositions[this.currentRoute] = window.scrollY;
    }

    let routeName = this.getCleanRoute();
    if (routeName === "login") routeName = "dash";

    const page = this.routes[routeName] || this.routes["dash"];
    this.currentRoute = routeName;
    this.activePage = page;

    this.updateNavLinks(routeName);

    // F3: pull a fresh snapshot (forced notify) BEFORE rendering so pages mount
    // with current data and never need to re-render themselves on later poll ticks.
    try { await store.fetchSnapshot(true); } catch (_) {}

    if (page && typeof page.render === "function") {
      try {
        await page.render(appView);
        const savedScroll = this.scrollPositions[routeName] || 0;
        window.scrollTo({ top: savedScroll, behavior: "instant" });
      } catch (err) {
        console.error(`Route render error [${routeName}]:`, err);
        appView.innerHTML = `
          <div class="card" style="margin: var(--space-6) auto; max-width: 600px; text-align: center;">
            <h3 style="color: var(--loss); margin-bottom: var(--space-2);">Failed to load page</h3>
            <p style="color: var(--text-muted); margin-bottom: var(--space-4);">${err.message || err}</p>
            <button class="btn btn-primary" onclick="window.location.reload()">Reload Terminal</button>
          </div>
        `;
      }
    }
  }

  setNavVisibility(visible) {
    const rail = document.querySelector(".desktop-rail");
    const bottomNav = document.querySelector(".bottom-nav");
    const modePill = document.getElementById("top-mode-pill");
    const refreshBtn = document.getElementById("btn-top-refresh");

    if (rail) rail.style.display = visible ? "" : "none";
    if (bottomNav) bottomNav.style.display = visible ? "" : "none";
    if (modePill) modePill.style.display = visible ? "" : "none";
    if (refreshBtn) refreshBtn.style.display = visible ? "" : "none";
    
    // adjust body padding on desktop when nav is hidden
    if (!visible) {
      document.body.style.paddingLeft = "0";
      document.body.style.paddingBottom = "0";
    } else {
      document.body.style.paddingLeft = "";
      document.body.style.paddingBottom = "";
    }
  }

  updateNavLinks(activeRoute) {
    document.querySelectorAll(".rail-link").forEach((link) => {
      const target = link.getAttribute("href")?.replace(/^#\/?/, "");
      if (target === activeRoute) link.classList.add("active");
      else link.classList.remove("active");
    });

    document.querySelectorAll(".bottom-tab").forEach((tab) => {
      const target = tab.getAttribute("data-route");
      if (target === activeRoute || (activeRoute === "dash" && target === "dash")) {
        tab.classList.add("active");
      } else {
        tab.classList.remove("active");
      }
    });
  }
}

export const router = new Router();

router.register("training", trainingView);
