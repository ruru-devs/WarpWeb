(() => {
  var __getOwnPropNames = Object.getOwnPropertyNames;
  var __commonJS = (cb, mod) => function __require() {
    try {
      return mod || (0, cb[__getOwnPropNames(cb)[0]])((mod = { exports: {} }).exports, mod), mod.exports;
    } catch (e) {
      throw mod = 0, e;
    }
  };

  // widget/src/warpweb.ts
  var require_warpweb = __commonJS({
    "widget/src/warpweb.ts"() {
      (function() {
        const currentScript = document.currentScript;
        const siteId = currentScript && currentScript.getAttribute("data-site-id") || "apexcare-clinic";
        const apiHost = currentScript && currentScript.getAttribute("data-api-host") || "http://localhost:8000";
        if (!document.getElementById("warpweb-highlighter-style")) {
          const hlStyle = document.createElement("style");
          hlStyle.id = "warpweb-highlighter-style";
          hlStyle.textContent = `
      @keyframes warpwebPulse {
        0% { outline: 4px solid #38bdf8; background-color: rgba(56, 189, 248, 0.28); }
        50% { outline: 6px solid #0284c7; background-color: rgba(2, 132, 199, 0.38); }
        100% { outline: 4px solid transparent; background-color: transparent; }
      }
      .warpweb-highlight-target {
        animation: warpwebPulse 3s cubic-bezier(0.16, 1, 0.3, 1);
        scroll-margin-top: 90px;
        border-radius: 8px;
      }
    `;
          document.head.appendChild(hlStyle);
        }
        function checkLandingHighlight() {
          const hash = window.location.hash ? window.location.hash.substring(1) : "";
          const params = new URLSearchParams(window.location.search);
          const highlightTarget = hash || params.get("warpweb_highlight");
          if (highlightTarget) {
            setTimeout(() => {
              const el = document.getElementById(highlightTarget);
              if (el) {
                el.scrollIntoView({ behavior: "smooth", block: "center" });
                el.classList.remove("warpweb-highlight-target");
                void el.offsetWidth;
                el.classList.add("warpweb-highlight-target");
              }
            }, 250);
          }
        }
        if (document.readyState === "loading") {
          document.addEventListener("DOMContentLoaded", checkLandingHighlight);
        } else {
          checkLandingHighlight();
        }
        if (document.getElementById("warpweb-root")) return;
        const container = document.createElement("div");
        container.id = "warpweb-root";
        const shadow = container.attachShadow({ mode: "open" });
        document.body.appendChild(container);
        const style = document.createElement("style");
        style.textContent = `
    * { box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
    .warpweb-btn {
      position: fixed;
      bottom: 24px;
      right: 24px;
      display: flex;
      align-items: center;
      gap: 8px;
      background: #0f172a;
      color: #ffffff;
      padding: 10px 18px;
      border-radius: 9999px;
      cursor: pointer;
      box-shadow: 0 10px 25px -5px rgba(0,0,0,0.35);
      border: 1px solid #334155;
      z-index: 999999;
      font-size: 14px;
      font-weight: 500;
      transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
    }
    .warpweb-btn:hover {
      transform: translateY(-2px);
      box-shadow: 0 14px 28px -5px rgba(0,0,0,0.45);
      background: #1e293b;
    }
    .warpweb-badge {
      background: #334155;
      padding: 2px 6px;
      border-radius: 4px;
      font-size: 11px;
      color: #94a3b8;
    }
    .warpweb-backdrop {
      position: fixed;
      inset: 0;
      background: rgba(15, 23, 42, 0.65);
      backdrop-filter: blur(5px);
      display: flex;
      justify-content: center;
      align-items: flex-start;
      padding-top: 10vh;
      z-index: 1000000;
      opacity: 0;
      pointer-events: none;
      transition: opacity 0.2s ease;
    }
    .warpweb-backdrop.open {
      opacity: 1;
      pointer-events: auto;
    }
    .warpweb-modal {
      width: 100%;
      max-width: 650px;
      background: #ffffff;
      border-radius: 16px;
      box-shadow: 0 25px 50px -12px rgba(0,0,0,0.4);
      border: 1px solid #e2e8f0;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      animation: slideDown 0.2s cubic-bezier(0.16, 1, 0.3, 1);
    }
    @keyframes slideDown {
      from { transform: translateY(-12px) scale(0.98); }
      to { transform: translateY(0) scale(1); }
    }
    .warpweb-search-bar {
      display: flex;
      align-items: center;
      padding: 16px 20px;
      border-bottom: 1px solid #f1f5f9;
      gap: 12px;
    }
    .warpweb-icon {
      color: #64748b;
      width: 20px;
      height: 20px;
      flex-shrink: 0;
    }
    .warpweb-input {
      flex: 1;
      border: none;
      outline: none;
      font-size: 17px;
      color: #0f172a;
      background: transparent;
    }
    .warpweb-input::placeholder {
      color: #94a3b8;
    }
    .warpweb-results {
      max-height: 400px;
      overflow-y: auto;
      padding: 12px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .warpweb-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 12px 14px;
      border-radius: 10px;
      cursor: pointer;
      text-decoration: none;
      color: inherit;
      background: #ffffff;
      border: 1px solid #f1f5f9;
      transition: all 0.15s ease;
    }
    .warpweb-item:hover, .warpweb-item.active {
      background: #f8fafc;
      border-color: #cbd5e1;
      transform: translateX(2px);
    }
    .warpweb-item-main {
      flex: 1;
      padding-right: 12px;
    }
    .warpweb-item-breadcrumbs {
      font-size: 11px;
      font-weight: 600;
      color: #64748b;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      margin-bottom: 2px;
      display: flex;
      align-items: center;
      gap: 4px;
    }
    .warpweb-item-title {
      font-weight: 600;
      font-size: 15px;
      color: #0f172a;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .warpweb-tag {
      font-size: 11px;
      padding: 2px 6px;
      border-radius: 4px;
      background: #e0f2fe;
      color: #0369a1;
      font-weight: 500;
    }
    .warpweb-item-snippet {
      font-size: 13px;
      color: #64748b;
      line-height: 1.4;
      margin-top: 3px;
    }
    .warpweb-item-meta {
      display: flex;
      gap: 12px;
      font-size: 12px;
      margin-top: 4px;
      font-weight: 600;
    }
    .warpweb-meta-price { color: #0284c7; }
    .warpweb-meta-timings { color: #059669; }
    .warpweb-actions-container {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
      align-items: center;
      justify-content: flex-end;
      flex-shrink: 0;
    }
    .warpweb-action-badge {
      display: flex;
      align-items: center;
      gap: 4px;
      background: #0284c7;
      color: #ffffff;
      padding: 6px 12px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 500;
      white-space: nowrap;
      cursor: pointer;
      text-decoration: none;
      transition: background 0.15s ease;
    }
    .warpweb-action-badge:hover {
      background: #0369a1;
    }
    .warpweb-action-secondary {
      background: #f1f5f9;
      color: #0f172a;
      border: 1px solid #cbd5e1;
    }
    .warpweb-action-secondary:hover {
      background: #e2e8f0;
    }
    .warpweb-cross-page-badge {
      background: #f1f5f9;
      color: #475569;
      border: 1px solid #e2e8f0;
      padding: 2px 6px;
      border-radius: 4px;
      font-size: 10.5px;
      font-weight: 500;
    }
    .warpweb-empty {
      padding: 28px 16px;
      text-align: center;
      color: #64748b;
    }
    .warpweb-lead-box {
      margin-top: 14px;
      padding: 16px;
      background: #f8fafc;
      border-radius: 10px;
      border: 1px dashed #cbd5e1;
      text-align: left;
    }
    .warpweb-lead-input {
      width: 100%;
      padding: 9px 12px;
      border: 1px solid #cbd5e1;
      border-radius: 6px;
      font-size: 13px;
      margin-top: 8px;
      outline: none;
    }
    .warpweb-lead-submit {
      margin-top: 8px;
      background: #0f172a;
      color: #ffffff;
      border: none;
      padding: 8px 14px;
      border-radius: 6px;
      font-size: 13px;
      font-weight: 500;
      cursor: pointer;
    }
    .warpweb-footer {
      padding: 10px 18px;
      border-top: 1px solid #f1f5f9;
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 12px;
      color: #94a3b8;
      background: #fafafa;
    }
  `;
        shadow.appendChild(style);
        const btn = document.createElement("button");
        btn.className = "warpweb-btn";
        btn.innerHTML = `
    <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
      <path d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path>
    </svg>
    <span>Find anything</span>
    <span class="warpweb-badge">Ctrl+K</span>
  `;
        shadow.appendChild(btn);
        const backdrop = document.createElement("div");
        backdrop.className = "warpweb-backdrop";
        backdrop.innerHTML = `
    <div class="warpweb-modal">
      <div class="warpweb-search-bar">
        <svg class="warpweb-icon" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
          <path d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path>
        </svg>
        <input type="text" class="warpweb-input" placeholder="Type intent (e.g. 'return policy', 'dr sharma timings', 'noise cancelling headphones')..." />
        <span class="warpweb-badge">ESC</span>
      </div>
      <div class="warpweb-results"></div>
      <div class="warpweb-footer">
        <span>\u26A1 <strong>WarpWeb</strong> Cross-Page Intent Engine</span>
        <span>Instant jump & deep highlight</span>
      </div>
    </div>
  `;
        shadow.appendChild(backdrop);
        const input = backdrop.querySelector(".warpweb-input");
        const resultsBox = backdrop.querySelector(".warpweb-results");
        function openModal() {
          backdrop.classList.add("open");
          input.focus();
          if (!input.value.trim()) {
            renderWelcomeSuggestions();
          }
        }
        function closeModal() {
          backdrop.classList.remove("open");
        }
        btn.addEventListener("click", openModal);
        backdrop.addEventListener("click", (e) => {
          if (e.target === backdrop) closeModal();
        });
        window.addEventListener("keydown", (e) => {
          if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
            e.preventDefault();
            backdrop.classList.contains("open") ? closeModal() : openModal();
          }
          if (e.key === "Escape") closeModal();
        });
        let debounceTimer = null;
        input.addEventListener("input", () => {
          clearTimeout(debounceTimer);
          debounceTimer = setTimeout(() => {
            fetchResults(input.value.trim());
          }, 100);
        });
        function renderWelcomeSuggestions() {
          resultsBox.innerHTML = `
      <div style="padding: 12px; font-size: 13px; color: #64748b;">
        <span style="font-weight: 600; text-transform: uppercase; font-size: 11px; letter-spacing: 0.05em; color: #94a3b8;">Suggested cross-page intents</span>
        <div style="display: flex; gap: 8px; margin-top: 10px; flex-wrap: wrap;">
          <button class="warpweb-item" style="padding: 6px 12px; font-size: 13px;" onclick="window.__warpwebQuick('timings')">\u{1F552} Doctor Timings</button>
          <button class="warpweb-item" style="padding: 6px 12px; font-size: 13px;" onclick="window.__warpwebQuick('mri scan price')">\u{1F4B0} MRI Scan Price</button>
          <button class="warpweb-item" style="padding: 6px 12px; font-size: 13px;" onclick="window.__warpwebQuick('return policy')">\u{1F4E6} 30-Day Returns</button>
          <button class="warpweb-item" style="padding: 6px 12px; font-size: 13px;" onclick="window.__warpwebQuick('wireless headphones anc')">\u{1F3A7} Active Noise Cancelling</button>
        </div>
      </div>
    `;
        }
        async function fetchResults(query) {
          if (!query) {
            renderWelcomeSuggestions();
            return;
          }
          try {
            const res = await fetch(`${apiHost}/api/search`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ site_id: siteId, query, top_k: 5 })
            });
            const data = await res.json();
            renderResults(data, query);
          } catch (err) {
            console.error("WarpWeb search failed:", err);
          }
        }
        function renderResults(data, query) {
          resultsBox.innerHTML = "";
          if (!data.results || data.results.length === 0) {
            const emptyDiv = document.createElement("div");
            emptyDiv.className = "warpweb-empty";
            const pMsg = document.createElement("p");
            pMsg.textContent = 'No exact match found across the website for "';
            const strongQuery = document.createElement("strong");
            strongQuery.textContent = query;
            pMsg.appendChild(strongQuery);
            pMsg.appendChild(document.createTextNode('".'));
            emptyDiv.appendChild(pMsg);
            const leadBox = document.createElement("div");
            leadBox.className = "warpweb-lead-box";
            const leadTitle = document.createElement("strong");
            leadTitle.style.fontSize = "13px";
            leadTitle.style.color = "#0f172a";
            leadTitle.textContent = "Need immediate assistance?";
            leadBox.appendChild(leadTitle);
            const leadDesc = document.createElement("p");
            leadDesc.style.fontSize = "12px";
            leadDesc.style.color = "#64748b";
            leadDesc.style.margin = "4px 0";
            leadDesc.textContent = "Leave your WhatsApp or phone number and our team will get back to you with the answer:";
            leadBox.appendChild(leadDesc);
            const leadInput = document.createElement("input");
            leadInput.type = "text";
            leadInput.id = "warpweb-lead-input";
            leadInput.className = "warpweb-lead-input";
            leadInput.placeholder = "Phone or WhatsApp number...";
            leadBox.appendChild(leadInput);
            const leadSubmit = document.createElement("button");
            leadSubmit.id = "warpweb-lead-submit";
            leadSubmit.className = "warpweb-lead-submit";
            leadSubmit.textContent = "Request Instant Callback";
            leadBox.appendChild(leadSubmit);
            emptyDiv.appendChild(leadBox);
            resultsBox.appendChild(emptyDiv);
            leadSubmit.addEventListener("click", async () => {
              const leadContact = leadInput.value.trim();
              if (leadContact) {
                try {
                  await fetch(`${apiHost}/api/leads`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ site_id: siteId, query, visitor_contact: leadContact })
                  });
                  resultsBox.innerHTML = "";
                  const successDiv = document.createElement("div");
                  successDiv.className = "warpweb-empty";
                  const checkSpan = document.createElement("span");
                  checkSpan.style.color = "#059669";
                  checkSpan.style.fontSize = "28px";
                  checkSpan.textContent = "\u2713";
                  const pSuccess = document.createElement("p");
                  pSuccess.style.marginTop = "8px";
                  pSuccess.style.fontWeight = "600";
                  pSuccess.style.color = "#0f172a";
                  pSuccess.textContent = "Request logged!";
                  const pDetail = document.createElement("p");
                  pDetail.style.fontSize = "13px";
                  pDetail.style.color = "#64748b";
                  pDetail.textContent = `Our staff will contact ${leadContact} regarding your request.`;
                  successDiv.appendChild(checkSpan);
                  successDiv.appendChild(pSuccess);
                  successDiv.appendChild(pDetail);
                  resultsBox.appendChild(successDiv);
                } catch (e) {
                  console.error("Lead submission failed:", e);
                }
              }
            });
            return;
          }
          const currentPath = window.location.pathname;
          data.results.forEach((item) => {
            const el = document.createElement("div");
            el.className = "warpweb-item";
            let targetPath = "";
            try {
              const u = new URL(item.target_url, window.location.href);
              targetPath = u.pathname;
            } catch (e) {
              targetPath = item.target_url || "";
            }
            const isCurrentPage = targetPath === currentPath || targetPath.endsWith(currentPath.split("/").pop() || "");
            let pageLabel = "Page";
            const uStr = String(item.url || "");
            if (uStr.includes("doctors")) pageLabel = "Doctors & OPD";
            else if (uStr.includes("diagnostics")) pageLabel = "Diagnostics & Scans";
            else if (uStr.includes("departments")) pageLabel = "Departments";
            else if (uStr.includes("products")) pageLabel = "Catalog";
            else if (uStr.includes("policy")) pageLabel = "Shipping & Policies";
            else if (uStr.includes("specs")) pageLabel = "Tech Specs";
            const mainDiv = document.createElement("div");
            mainDiv.className = "warpweb-item-main";
            const breadcrumbsDiv = document.createElement("div");
            breadcrumbsDiv.className = "warpweb-item-breadcrumbs";
            const pageSpan = document.createElement("span");
            pageSpan.textContent = pageLabel;
            const arrowSpan = document.createElement("span");
            arrowSpan.textContent = "\u203A";
            breadcrumbsDiv.appendChild(pageSpan);
            breadcrumbsDiv.appendChild(arrowSpan);
            const navBadge = document.createElement("span");
            if (!isCurrentPage) {
              navBadge.className = "warpweb-cross-page-badge";
              navBadge.textContent = "Cross-page navigation";
            } else {
              navBadge.textContent = "Current page";
            }
            breadcrumbsDiv.appendChild(navBadge);
            mainDiv.appendChild(breadcrumbsDiv);
            const titleDiv = document.createElement("div");
            titleDiv.className = "warpweb-item-title";
            const titleSpan = document.createElement("span");
            titleSpan.textContent = item.title || "";
            titleDiv.appendChild(titleSpan);
            if (item.match_type === "override") {
              const tag = document.createElement("span");
              tag.className = "warpweb-tag";
              tag.style.background = "#fef3c7";
              tag.style.color = "#b45309";
              tag.textContent = "Verified";
              titleDiv.appendChild(tag);
            }
            mainDiv.appendChild(titleDiv);
            const snippetDiv = document.createElement("div");
            snippetDiv.className = "warpweb-item-snippet";
            snippetDiv.textContent = item.snippet || "";
            mainDiv.appendChild(snippetDiv);
            if (item.metadata && (item.metadata.timings || item.metadata.price)) {
              const metaDiv = document.createElement("div");
              metaDiv.className = "warpweb-item-meta";
              if (item.metadata.timings) {
                const timingSpan = document.createElement("span");
                timingSpan.className = "warpweb-meta-timings";
                timingSpan.textContent = `\u{1F552} ${item.metadata.timings}`;
                metaDiv.appendChild(timingSpan);
              }
              if (item.metadata.price) {
                const priceSpan = document.createElement("span");
                priceSpan.className = "warpweb-meta-price";
                priceSpan.textContent = `\u{1F4B0} ${item.metadata.price}`;
                metaDiv.appendChild(priceSpan);
              }
              mainDiv.appendChild(metaDiv);
            }
            el.appendChild(mainDiv);
            const actionsContainer = document.createElement("div");
            actionsContainer.className = "warpweb-actions-container";
            const actionsList = item.actions && item.actions.length > 0 ? item.actions : [{
              type: item.action_type || "navigate",
              label: item.action_label || (isCurrentPage ? "Jump" : "Navigate"),
              url: item.target_url
            }];
            actionsList.forEach((act, aIdx) => {
              const actionBadge = document.createElement("div");
              actionBadge.className = `warpweb-action-badge ${aIdx > 0 ? "warpweb-action-secondary" : ""}`;
              const actionText = document.createElement("span");
              actionText.textContent = act.label;
              actionBadge.appendChild(actionText);
              const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
              svg.setAttribute("width", "11");
              svg.setAttribute("height", "11");
              svg.setAttribute("fill", "none");
              svg.setAttribute("stroke", "currentColor");
              svg.setAttribute("stroke-width", "2");
              svg.setAttribute("viewBox", "0 0 24 24");
              const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
              path.setAttribute("d", "M5 12h14M12 5l7 7-7 7");
              svg.appendChild(path);
              actionBadge.appendChild(svg);
              actionBadge.addEventListener("click", (e) => {
                e.stopPropagation();
                closeModal();
                navigateToUrl(act.url);
              });
              actionsContainer.appendChild(actionBadge);
            });
            el.appendChild(actionsContainer);
            el.addEventListener("click", () => {
              closeModal();
              handleCrossPageNavigation(item, isCurrentPage);
            });
            resultsBox.appendChild(el);
          });
        }
        function navigateToUrl(destinationUrl) {
          try {
            const parsedUrl = new URL(destinationUrl, window.location.href);
            if (parsedUrl.protocol === "http:" || parsedUrl.protocol === "https:" || parsedUrl.protocol === "tel:") {
              window.location.href = parsedUrl.href;
            } else {
              console.warn("WarpWeb blocked navigation to unsafe URL protocol:", destinationUrl);
            }
          } catch (e) {
            console.warn("WarpWeb invalid destination URL:", destinationUrl);
          }
        }
        function handleCrossPageNavigation(item, isCurrentPage) {
          if (isCurrentPage && item.anchor_id) {
            const targetElem = document.getElementById(item.anchor_id);
            if (targetElem) {
              targetElem.scrollIntoView({ behavior: "smooth", block: "center" });
              targetElem.classList.remove("warpweb-highlight-target");
              void targetElem.offsetWidth;
              targetElem.classList.add("warpweb-highlight-target");
              return;
            }
          }
          let destinationUrl = item.target_url || "";
          if (item.anchor_id && !destinationUrl.includes("#")) {
            destinationUrl += `#${item.anchor_id}`;
          }
          navigateToUrl(destinationUrl);
        }
        window.__warpwebQuick = function(q) {
          input.value = q;
          fetchResults(q);
        };
      })();
    }
  });
  require_warpweb();
})();
