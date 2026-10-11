/**
 * SENTINEL-FX · Client-Side Hash Router
 * Deep-linkable hash routes, scroll position restoration, and active state sync.
 */

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
    // Save previous scroll position
    if (this.currentRoute) {
      this.scrollPositions[this.currentRoute] = window.scrollY;
    }

    const routeName = this.getCleanRoute();
    const page = this.routes[routeName] || this.routes["dash"];

    this.currentRoute = routeName;

    // Update navigation active states
    this.updateNavLinks(routeName);

    const appView = document.getElementById("app-view");
    if (!appView) return;

    if (page && typeof page.render === "function") {
      try {
        await page.render(appView);
        // Restore scroll position or scroll to top
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

  updateNavLinks(activeRoute) {
    // Desktop Rail
    document.querySelectorAll(".rail-link").forEach((link) => {
      const target = link.getAttribute("href")?.replace(/^#\/?/, "");
      if (target === activeRoute) {
        link.classList.add("active");
      } else {
        link.classList.remove("active");
      }
    });

    // Mobile Bottom Nav
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
