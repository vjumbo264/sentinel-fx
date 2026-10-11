/**
 * SENTINEL-FX · Upload Model Page
 * Drag-and-drop / tap-to-pick uploader for .sfxmodel.zip bundles.
 * 3-step validation pipeline and checker report viewer.
 */

import { icons } from "../icons.js";
import { store } from "../store.js";
import { api } from "../api.js";
import { sfxBusy, showToast, showConfirmSheet } from "../ui.js";

export const uploadView = {
  selectedFile: null,
  uploadStep: 1, // 1: Pick, 2: Upload, 3: Validate, 4: Install
  validationReport: null,

  async render(container) {
    this.container = container;
    this.updateDom();
  },

  updateDom() {
    if (!this.container) return;

    this.container.innerHTML = `
      <div style="display:flex; flex-direction:column; gap:var(--space-4);">

        <!-- HEADER -->
        <div>
          <h2 class="card-title">INSTALL CFD MODEL BUNDLE</h2>
          <p style="font-size:var(--text-sm); color:var(--text-secondary); margin-top:2px;">
            Deploy trained <code>.sfxmodel.zip</code> packages into the autonomous execution pool.
          </p>
        </div>

        <!-- PIPELINE STEPPER -->
        <div class="card" style="padding:var(--space-3) var(--space-4);">
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <div style="display:flex; align-items:center; gap:6px;">
              <span style="width:24px; height:24px; border-radius:50%; background:${this.uploadStep >= 1 ? "var(--accent-primary)" : "var(--bg-inset)"}; color:#fff; display:flex; align-items:center; justify-content:center; font-size:12px; font-weight:700;">1</span>
              <span style="font-size:var(--text-xs); font-weight:600;">Pick Bundle</span>
            </div>
            <div style="flex:1; height:2px; background:var(--border-subtle); margin:0 var(--space-2);"></div>
            <div style="display:flex; align-items:center; gap:6px;">
              <span style="width:24px; height:24px; border-radius:50%; background:${this.uploadStep >= 2 ? "var(--accent-primary)" : "var(--bg-inset)"}; color:#fff; display:flex; align-items:center; justify-content:center; font-size:12px; font-weight:700;">2</span>
              <span style="font-size:var(--text-xs); font-weight:600;">Check Safety</span>
            </div>
            <div style="flex:1; height:2px; background:var(--border-subtle); margin:0 var(--space-2);"></div>
            <div style="display:flex; align-items:center; gap:6px;">
              <span style="width:24px; height:24px; border-radius:50%; background:${this.uploadStep >= 3 ? "var(--profit)" : "var(--bg-inset)"}; color:#fff; display:flex; align-items:center; justify-content:center; font-size:12px; font-weight:700;">3</span>
              <span style="font-size:var(--text-xs); font-weight:600;">Install Active</span>
            </div>
          </div>
        </div>

        <!-- DRAG AND DROP DROPZONE -->
        <div id="dropzone" class="card" style="border:2px dashed var(--border-medium); text-align:center; padding:var(--space-8) var(--space-4); cursor:pointer; background:var(--bg-surface-elevated); transition:border-color var(--duration-fast) ease;">
          <input type="file" id="file-input" accept=".zip,.sfxmodel.zip,.json" style="display:none;">

          <div style="color:var(--accent-primary); margin-bottom:var(--space-3);">
            ${icons.upload("w-12 h-12")}
          </div>

          <h3 style="font-family:var(--font-display); font-size:var(--text-base); font-weight:700; margin-bottom:var(--space-1);">
            ${this.selectedFile ? this.selectedFile.name : "Tap to pick or drag & drop bundle"}
          </h3>

          <p style="font-size:var(--text-xs); color:var(--text-muted); max-width:380px; margin:0 auto var(--space-3);">
            Accepts <code>.sfxmodel.zip</code> containing <code>bundle.py</code> and <code>plan.py</code> with mandatory Stop Loss logic.
          </p>

          <button id="btn-pick-file" class="btn btn-secondary btn-sm" style="min-height:36px;">
            Browse Files
          </button>
        </div>

        <!-- SELECTED FILE DETAILS & VALIDATION STATUS -->
        ${this.selectedFile ? `
          <div class="card" style="padding:var(--space-4);">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:var(--space-3);">
              <div>
                <div style="font-weight:700; font-size:var(--text-sm);">${this.selectedFile.name}</div>
                <div style="font-size:var(--text-xs); color:var(--text-muted);">Size: ${(this.selectedFile.size / 1024).toFixed(1)} KB</div>
              </div>
              <span class="badge-profit" style="font-size:11px;">READY TO UPLOAD</span>
            </div>

            <!-- Upload & Validate Button -->
            <button id="btn-upload-submit" class="btn btn-primary" style="width:100%; min-height:44px;">
              ${icons.upload("w-4 h-4")} <span>Upload &amp; Run Model Validator</span>
            </button>
          </div>
        ` : ""}

        <!-- SPECIFICATION HINT -->
        <div class="card" style="padding:var(--space-4); background:var(--bg-subtle);">
          <div style="display:flex; align-items:center; gap:var(--space-2); margin-bottom:var(--space-2);">
            <span style="color:var(--accent-primary);">${icons.sentinel("w-4 h-4")}</span>
            <span style="font-weight:700; font-size:var(--text-xs); text-transform:uppercase;">CFD Safety Contract</span>
          </div>
          <p style="font-size:var(--text-xs); color:var(--text-secondary); line-height:1.5;">
            The model validator executes dynamic sandbox checks: all BUY/SELL proposals must emit a positive, server-side Stop Loss within 5–50 pips. Bundles that attempt open-ended risk without SL fail verification automatically.
          </p>
        </div>

      </div>
    `;

    this.bindEvents();
  },

  bindEvents() {
    const dropzone = document.getElementById("dropzone");
    const fileInput = document.getElementById("file-input");
    const pickBtn = document.getElementById("btn-pick-file");

    if (dropzone && fileInput) {
      dropzone.addEventListener("click", () => fileInput.click());
      dropzone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropzone.style.borderColor = "var(--accent-primary)";
      });
      dropzone.addEventListener("dragleave", () => {
        dropzone.style.borderColor = "var(--border-medium)";
      });
      dropzone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropzone.style.borderColor = "var(--border-medium)";
        if (e.dataTransfer.files && e.dataTransfer.files[0]) {
          this.selectedFile = e.dataTransfer.files[0];
          this.uploadStep = 2;
          this.updateDom();
        }
      });
    }

    if (fileInput) {
      fileInput.addEventListener("change", (e) => {
        if (e.target.files && e.target.files[0]) {
          this.selectedFile = e.target.files[0];
          this.uploadStep = 2;
          this.updateDom();
        }
      });
    }

    if (pickBtn && fileInput) {
      pickBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        fileInput.click();
      });
    }

    const uploadBtn = document.getElementById("btn-upload-submit");
    if (uploadBtn && this.selectedFile) {
      uploadBtn.addEventListener("click", () => {
        sfxBusy(uploadBtn, async () => {
          const buffer = await this.selectedFile.arrayBuffer();
          await api.uploadStagingAsset(this.selectedFile.name, buffer);
          showToast("Model uploaded to staging! Validation running in background.", "success");
          this.uploadStep = 3;
          this.updateDom();
        }, { pending: "Uploading bundle...", ok: "Uploaded & validated" });
      });
    }
  }
};
