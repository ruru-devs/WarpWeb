"use strict";
/**
 * WarpWeb Embeddable Widget (<15KB standalone)
 * Injected on client websites via:
 * <script src="http://localhost:8000/warpweb.js" data-site-id="xyz" data-api-host="http://localhost:8000"></script>
 *
 * Supports:
 * 1. Same-page smooth scroll + pulse highlight
 * 2. Cross-page deep navigation with auto-highlighting upon page landing
 * 3. Sub-150ms instant search palette (Ctrl+K or floating badge)
 * 4. Fallback lead capture for zero matches
 */
(function () {
    const currentScript = document.currentScript;
    const siteId = (currentScript && currentScript.getAttribute('data-site-id')) || 'apexcare-clinic';
    const apiHost = (currentScript && currentScript.getAttribute('data-api-host')) || 'http://localhost:8000';
    // Highlight style injected into parent window
    if (!document.getElementById('warpweb-highlighter-style')) {
        const hlStyle = document.createElement('style');
        hlStyle.id = 'warpweb-highlighter-style';
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
    // Check URL hash or search params on page load for auto-highlighting after cross-page navigation
    function checkLandingHighlight() {
        const hash = window.location.hash ? window.location.hash.substring(1) : '';
        const params = new URLSearchParams(window.location.search);
        const highlightTarget = hash || params.get('warpweb_highlight');
        if (highlightTarget) {
            setTimeout(() => {
                const el = document.getElementById(highlightTarget);
                if (el) {
                    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    el.classList.remove('warpweb-highlight-target');
                    void el.offsetWidth;
                    el.classList.add('warpweb-highlight-target');
                }
            }, 250);
        }
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', checkLandingHighlight);
    }
    else {
        checkLandingHighlight();
    }
    // Prevent multiple mountings
    if (document.getElementById('warpweb-root'))
        return;
    const container = document.createElement('div');
    container.id = 'warpweb-root';
    const shadow = container.attachShadow({ mode: 'open' });
    document.body.appendChild(container);
    // Styles isolated in Shadow DOM
    const style = document.createElement('style');
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
      flex-shrink: 0;
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
    // Floating Trigger Button
    const btn = document.createElement('button');
    btn.className = 'warpweb-btn';
    btn.innerHTML = `
    <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
      <path d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path>
    </svg>
    <span>Find anything</span>
    <span class="warpweb-badge">Ctrl+K</span>
  `;
    shadow.appendChild(btn);
    // Modal
    const backdrop = document.createElement('div');
    backdrop.className = 'warpweb-backdrop';
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
        <span>⚡ <strong>WarpWeb</strong> Cross-Page Intent Engine</span>
        <span>Instant jump & deep highlight</span>
      </div>
    </div>
  `;
    shadow.appendChild(backdrop);
    const input = backdrop.querySelector('.warpweb-input');
    const resultsBox = backdrop.querySelector('.warpweb-results');
    function openModal() {
        backdrop.classList.add('open');
        input.focus();
        if (!input.value.trim()) {
            renderWelcomeSuggestions();
        }
    }
    function closeModal() {
        backdrop.classList.remove('open');
    }
    btn.addEventListener('click', openModal);
    backdrop.addEventListener('click', (e) => {
        if (e.target === backdrop)
            closeModal();
    });
    window.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
            e.preventDefault();
            backdrop.classList.contains('open') ? closeModal() : openModal();
        }
        if (e.key === 'Escape')
            closeModal();
    });
    let debounceTimer = null;
    input.addEventListener('input', () => {
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
          <button class="warpweb-item" style="padding: 6px 12px; font-size: 13px;" onclick="window.__warpwebQuick('timings')">🕒 Doctor Timings</button>
          <button class="warpweb-item" style="padding: 6px 12px; font-size: 13px;" onclick="window.__warpwebQuick('mri scan price')">💰 MRI Scan Price</button>
          <button class="warpweb-item" style="padding: 6px 12px; font-size: 13px;" onclick="window.__warpwebQuick('return policy')">📦 30-Day Returns</button>
          <button class="warpweb-item" style="padding: 6px 12px; font-size: 13px;" onclick="window.__warpwebQuick('wireless headphones anc')">🎧 Active Noise Cancelling</button>
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
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ site_id: siteId, query: query, top_k: 5 })
            });
            const data = await res.json();
            renderResults(data, query);
        }
        catch (err) {
            console.error('WarpWeb search failed:', err);
        }
    }
    function renderResults(data, query) {
        resultsBox.innerHTML = '';
        if (!data.results || data.results.length === 0) {
            resultsBox.innerHTML = `
        <div class="warpweb-empty">
          <p>No exact match found across the website for <strong>"${query}"</strong>.</p>
          <div class="warpweb-lead-box">
            <strong style="font-size: 13px; color: #0f172a;">Need immediate assistance?</strong>
            <p style="font-size: 12px; color: #64748b; margin: 4px 0;">Leave your WhatsApp or phone number and our team will get back to you with the answer:</p>
            <input type="text" id="warpweb-lead-input" class="warpweb-lead-input" placeholder="Phone or WhatsApp number..." />
            <button id="warpweb-lead-submit" class="warpweb-lead-submit">Request Instant Callback</button>
          </div>
        </div>
      `;
            const leadBtn = resultsBox.querySelector('#warpweb-lead-submit');
            if (leadBtn) {
                leadBtn.addEventListener('click', async () => {
                    const leadContact = resultsBox.querySelector('#warpweb-lead-input').value;
                    if (leadContact) {
                        await fetch(`${apiHost}/api/leads`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ site_id: siteId, query: query, visitor_contact: leadContact })
                        });
                        resultsBox.innerHTML = `
              <div class="warpweb-empty">
                <span style="color: #059669; font-size: 28px;">✓</span>
                <p style="margin-top: 8px; font-weight: 600; color: #0f172a;">Request logged!</p>
                <p style="font-size: 13px; color: #64748b;">Our staff will contact ${leadContact} regarding your request.</p>
              </div>
            `;
                    }
                });
            }
            return;
        }
        const currentPath = window.location.pathname;
        data.results.forEach((item) => {
            const el = document.createElement('div');
            el.className = 'warpweb-item';
            // Determine if destination is on current page or another page
            let targetPath = '';
            try {
                const u = new URL(item.target_url, window.location.href);
                targetPath = u.pathname;
            }
            catch (e) {
                targetPath = item.target_url;
            }
            const isCurrentPage = targetPath === currentPath || targetPath.endsWith(currentPath.split('/').pop() || '');
            let metaInfo = '';
            if (item.metadata && item.metadata.timings) {
                metaInfo += `<span class="warpweb-meta-timings">🕒 ${item.metadata.timings}</span>`;
            }
            if (item.metadata && item.metadata.price) {
                metaInfo += `<span class="warpweb-meta-price">💰 ${item.metadata.price}</span>`;
            }
            // Readable breadcrumbs / page tag
            let pageLabel = 'Page';
            if (item.url.includes('doctors'))
                pageLabel = 'Doctors & OPD';
            else if (item.url.includes('diagnostics'))
                pageLabel = 'Diagnostics & Scans';
            else if (item.url.includes('departments'))
                pageLabel = 'Departments';
            else if (item.url.includes('products'))
                pageLabel = 'Catalog';
            else if (item.url.includes('policy'))
                pageLabel = 'Shipping & Policies';
            else if (item.url.includes('specs'))
                pageLabel = 'Tech Specs';
            el.innerHTML = `
        <div class="warpweb-item-main">
          <div class="warpweb-item-breadcrumbs">
            <span>${pageLabel}</span>
            <span>›</span>
            ${!isCurrentPage ? `<span class="warpweb-cross-page-badge">Cross-page navigation</span>` : `<span>Current page</span>`}
          </div>
          <div class="warpweb-item-title">
            <span>${item.title}</span>
            ${item.match_type === 'override' ? '<span class="warpweb-tag" style="background:#fef3c7; color:#b45309;">Verified</span>' : ''}
          </div>
          <div class="warpweb-item-snippet">${item.snippet}</div>
          ${metaInfo ? `<div class="warpweb-item-meta">${metaInfo}</div>` : ''}
        </div>
        <div class="warpweb-action-badge">
          <span>${item.action_label || (isCurrentPage ? 'Jump' : 'Navigate')}</span>
          <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <path d="M5 12h14M12 5l7 7-7 7"></path>
          </svg>
        </div>
      `;
            el.addEventListener('click', () => {
                closeModal();
                handleCrossPageNavigation(item, isCurrentPage);
            });
            resultsBox.appendChild(el);
        });
    }
    function handleCrossPageNavigation(item, isCurrentPage) {
        if (isCurrentPage && item.anchor_id) {
            // Same-page smooth scroll + pulse highlight
            const targetElem = document.getElementById(item.anchor_id);
            if (targetElem) {
                targetElem.scrollIntoView({ behavior: 'smooth', block: 'center' });
                targetElem.classList.remove('warpweb-highlight-target');
                void targetElem.offsetWidth;
                targetElem.classList.add('warpweb-highlight-target');
                return;
            }
        }
        // Cross-page navigation: ensure anchor or highlight param is carried over
        let destinationUrl = item.target_url;
        if (item.anchor_id && !destinationUrl.includes('#')) {
            destinationUrl += `#${item.anchor_id}`;
        }
        window.location.href = destinationUrl;
    }
    window.__warpwebQuick = function (q) {
        input.value = q;
        fetchResults(q);
    };
})();
