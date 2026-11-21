/**
 * WarpWeb Client Widget
 * Shadow-DOM isolated command palette with deep semantic intent matching,
 * in-flight request cancellation (AbortController), ARIA accessibility (combobox/listbox),
 * focus trap, mobile responsiveness, click-through tracking, and result feedback.
 */
(function () {
  if (window.__warpweb_initialized) return;
  window.__warpweb_initialized = true;

  // Retrieve current script tags configuration
  const scriptTag = document.currentScript as HTMLScriptElement || 
    document.querySelector('script[data-site-id]');
  
  const siteId = scriptTag?.getAttribute('data-site-id') || 'apexcare-clinic';
  const apiHost = scriptTag?.getAttribute('data-api-host') || 'http://localhost:8000';

  // Inject target pulse-highlight CSS into main host document
  const pulseStyle = document.createElement('style');
  pulseStyle.textContent = `
    @keyframes warpweb-target-pulse {
      0% { outline: 3px solid #0284c7; background-color: rgba(2, 132, 199, 0.2); }
      50% { outline: 3px solid #38bdf8; background-color: rgba(56, 189, 248, 0.35); }
      100% { outline: 3px solid transparent; background-color: transparent; }
    }
    .warpweb-highlight-target {
      animation: warpweb-target-pulse 2.5s ease-out 1;
      border-radius: 6px;
    }
  `;
  document.head.appendChild(pulseStyle);

  // Check URL on page load for deep anchor pulse highlight
  window.addEventListener('DOMContentLoaded', () => {
    checkAndHighlightAnchor();
  });

  function checkAndHighlightAnchor() {
    const hash = window.location.hash.replace('#', '');
    if (!hash) return;
    setTimeout(() => {
      const target = document.getElementById(hash);
      if (target) {
        target.scrollIntoView({ behavior: 'smooth', block: 'center' });
        target.classList.add('warpweb-highlight-target');
      }
    }, 250);
  }

  // Create Isolated Shadow Root container
  const host = document.createElement('div');
  host.id = 'warpweb-widget-host';
  document.body.appendChild(host);
  const shadow = host.attachShadow({ mode: 'open' });

  // Stylesheet
  const style = document.createElement('style');
  style.textContent = `
    :host {
      --primary: #0284c7;
      --primary-hover: #0369a1;
      --text: #0f172a;
      --text-muted: #64748b;
      --bg: #ffffff;
      --border: #e2e8f0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }
    .warpweb-trigger-btn {
      position: fixed;
      bottom: 24px;
      right: 24px;
      z-index: 2147483640;
      display: flex;
      align-items: center;
      gap: 8px;
      background: #0f172a;
      color: #ffffff;
      border: 1px solid rgba(255, 255, 255, 0.12);
      border-radius: 9999px;
      padding: 10px 18px;
      font-size: 14px;
      font-weight: 500;
      cursor: pointer;
      box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3), 0 8px 10px -6px rgba(0, 0, 0, 0.2);
      transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
    }
    .warpweb-trigger-btn:hover {
      transform: translateY(-2px);
      box-shadow: 0 15px 30px -5px rgba(0, 0, 0, 0.4);
      background: #1e293b;
    }
    .warpweb-badge {
      font-size: 11px;
      background: #334155;
      padding: 2px 6px;
      border-radius: 4px;
      color: #94a3b8;
      font-weight: 600;
    }
    .warpweb-backdrop {
      position: fixed;
      inset: 0;
      background: rgba(15, 23, 42, 0.55);
      backdrop-filter: blur(4px);
      z-index: 2147483647;
      display: flex;
      justify-content: center;
      align-items: flex-start;
      padding-top: 10vh;
      opacity: 0;
      pointer-events: none;
      transition: opacity 0.2s ease;
    }
    .warpweb-backdrop.open {
      opacity: 1;
      pointer-events: auto;
    }
    .warpweb-modal {
      width: 640px;
      max-width: 95vw;
      background: #ffffff;
      border-radius: 14px;
      box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.35);
      border: 1px solid #e2e8f0;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      animation: warpweb-pop 0.2s cubic-bezier(0.16, 1, 0.3, 1);
    }
    @keyframes warpweb-pop {
      from { transform: scale(0.96) translateY(-8px); opacity: 0; }
      to { transform: scale(1) translateY(0); opacity: 1; }
    }
    .warpweb-search-bar {
      display: flex;
      align-items: center;
      padding: 16px 20px;
      border-bottom: 1px solid #e2e8f0;
      gap: 12px;
    }
    .warpweb-icon {
      width: 20px;
      height: 20px;
      color: #94a3b8;
      flex-shrink: 0;
    }
    .warpweb-input {
      flex: 1;
      border: none;
      outline: none;
      font-size: 16px;
      color: #0f172a;
      background: transparent;
    }
    .warpweb-input::placeholder {
      color: #94a3b8;
    }
    .warpweb-results {
      max-height: 420px;
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
    .warpweb-item:hover, .warpweb-item.active, .warpweb-item:focus {
      background: #f0f9ff;
      border-color: #38bdf8;
      outline: none;
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
      padding: 24px 16px;
      text-align: center;
      color: #64748b;
    }
    .warpweb-lead-box {
      margin-top: 14px;
      padding: 16px;
      border-radius: 10px;
      background: #f8fafc;
      border: 1px dashed #cbd5e1;
      display: flex;
      flex-direction: column;
      gap: 10px;
      text-align: left;
    }
    .warpweb-lead-input {
      padding: 10px 14px;
      border: 1px solid #cbd5e1;
      border-radius: 8px;
      font-size: 14px;
      outline: none;
      width: 100%;
    }
    .warpweb-lead-input:focus {
      border-color: #0284c7;
    }
    .warpweb-lead-submit {
      background: #0f172a;
      color: #ffffff;
      border: none;
      padding: 10px 16px;
      border-radius: 8px;
      font-size: 13px;
      font-weight: 500;
      cursor: pointer;
      align-self: flex-start;
    }
    .warpweb-footer {
      padding: 10px 16px;
      background: #f8fafc;
      border-top: 1px solid #e2e8f0;
      font-size: 11.5px;
      color: #64748b;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .warpweb-feedback-box {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 12px;
      color: #64748b;
    }
    .warpweb-feedback-btn {
      background: #f1f5f9;
      border: 1px solid #cbd5e1;
      border-radius: 6px;
      padding: 2px 8px;
      font-size: 12px;
      cursor: pointer;
      transition: background 0.15s ease;
    }
    .warpweb-feedback-btn:hover {
      background: #e2e8f0;
    }
    @media (max-width: 640px) {
      .warpweb-backdrop {
        padding-top: 0;
        align-items: flex-end;
      }
      .warpweb-modal {
        width: 100vw;
        max-width: 100vw;
        max-height: 85vh;
        border-radius: 16px 16px 0 0;
      }
      .warpweb-search-bar {
        padding: 14px 16px;
      }
      .warpweb-input {
        font-size: 16px;
      }
      .warpweb-results {
        max-height: 55vh;
      }
      .warpweb-trigger-btn {
        bottom: 16px;
        right: 16px;
        padding: 8px 14px;
        font-size: 13px;
      }
      .warpweb-actions-container {
        justify-content: flex-start;
        margin-top: 6px;
      }
    }
  `;
  shadow.appendChild(style);

  // Floating trigger button
  const btn = document.createElement('button');
  btn.className = 'warpweb-trigger-btn';
  btn.setAttribute('aria-haspopup', 'dialog');
  btn.setAttribute('aria-expanded', 'false');
  btn.setAttribute('aria-label', 'Open WarpWeb site search dialog');
  btn.innerHTML = `
    <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
      <path d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path>
    </svg>
    <span>Find anything</span>
    <span class="warpweb-badge">Ctrl+K</span>
  `;
  shadow.appendChild(btn);

  // Modal dialog
  const backdrop = document.createElement('div');
  backdrop.className = 'warpweb-backdrop';
  backdrop.setAttribute('role', 'dialog');
  backdrop.setAttribute('aria-modal', 'true');
  backdrop.setAttribute('aria-label', 'Search website intents and pages');

  backdrop.innerHTML = `
    <div class="warpweb-modal">
      <div class="warpweb-search-bar">
        <svg class="warpweb-icon" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
          <path d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path>
        </svg>
        <input type="text" class="warpweb-input" 
          role="combobox"
          aria-autocomplete="list"
          aria-expanded="false"
          aria-controls="warpweb-results-list"
          aria-activedescendant=""
          placeholder="Type intent (e.g. 'return policy', 'dr sharma timings', 'noise cancelling headphones')..." />
        <span class="warpweb-badge">ESC</span>
      </div>
      <div class="warpweb-results" id="warpweb-results-list" role="listbox" aria-label="Search suggestions"></div>
      <div class="warpweb-footer">
        <span>⚡ <strong>WarpWeb</strong> Cross-Page Intent Engine</span>
        <div id="warpweb-footer-extra">
          <span style="font-size: 11px; color: #94a3b8;">↑↓ Navigate • Enter Select • Esc Close</span>
        </div>
      </div>
    </div>
  `;
  shadow.appendChild(backdrop);

  const input = backdrop.querySelector('.warpweb-input') as HTMLInputElement;
  const resultsBox = backdrop.querySelector('.warpweb-results') as HTMLDivElement;

  // Accessibility & Navigation State
  let previousActiveElement: HTMLElement | null = null;
  let activeIndex = -1;
  let resultItemsElements: HTMLElement[] = [];
  let cachedSuggestions: Array<{ label: string; query: string }> = [];

  // In-flight request sequencing & cancellation
  let activeAbortController: AbortController | null = null;
  let latestRequestId = 0;

  function openModal() {
    previousActiveElement = document.activeElement as HTMLElement;
    backdrop.classList.add('open');
    btn.setAttribute('aria-expanded', 'true');
    input.setAttribute('aria-expanded', 'true');
    input.focus();
    if (!input.value.trim()) {
      renderWelcomeSuggestions();
    }
  }

  function closeModal() {
    backdrop.classList.remove('open');
    btn.setAttribute('aria-expanded', 'false');
    input.setAttribute('aria-expanded', 'false');
    input.setAttribute('aria-activedescendant', '');
    activeIndex = -1;
    if (activeAbortController) {
      activeAbortController.abort();
      activeAbortController = null;
    }
    if (previousActiveElement && typeof previousActiveElement.focus === 'function') {
      previousActiveElement.focus();
    }
  }

  btn.addEventListener('click', openModal);
  backdrop.addEventListener('click', (e) => {
    if (e.target === backdrop) closeModal();
  });

  // Global Keyboard Shortcuts & Modal Focus Trap
  window.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      backdrop.classList.contains('open') ? closeModal() : openModal();
    }
    if (e.key === 'Escape' && backdrop.classList.contains('open')) {
      closeModal();
    }
  });

  // Keyboard navigation within search input (ArrowUp, ArrowDown, Enter)
  input.addEventListener('keydown', (e) => {
    if (!resultItemsElements.length) return;

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      activeIndex = (activeIndex + 1) % resultItemsElements.length;
      updateActiveItem();
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      activeIndex = (activeIndex - 1 + resultItemsElements.length) % resultItemsElements.length;
      updateActiveItem();
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (activeIndex >= 0 && activeIndex < resultItemsElements.length) {
        resultItemsElements[activeIndex].click();
      }
    }
  });

  function updateActiveItem() {
    resultItemsElements.forEach((el, idx) => {
      if (idx === activeIndex) {
        el.classList.add('active');
        input.setAttribute('aria-activedescendant', el.id);
        el.scrollIntoView({ block: 'nearest' });
      } else {
        el.classList.remove('active');
      }
    });
  }

  // Debounced Search Input
  let debounceTimer: any = null;
  input.addEventListener('input', () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      fetchResults(input.value.trim());
    }, 100);
  });

  // Dynamic Suggestions from Backend
  async function loadDynamicSuggestions() {
    try {
      const res = await fetch(`${apiHost}/api/suggestions/${siteId}`);
      if (res.ok) {
        const data = await res.json();
        cachedSuggestions = data.suggestions || [];
      }
    } catch (e) {
      cachedSuggestions = [];
    }
  }
  loadDynamicSuggestions();

  function renderWelcomeSuggestions() {
    resultsBox.innerHTML = '';
    resultItemsElements = [];
    activeIndex = -1;

    const wrap = document.createElement('div');
    wrap.style.padding = '14px';

    const header = document.createElement('span');
    header.style.fontWeight = '600';
    header.style.textTransform = 'uppercase';
    header.style.fontSize = '11px';
    header.style.letterSpacing = '0.05em';
    header.style.color = '#94a3b8';
    header.textContent = 'Suggested cross-page intents';
    wrap.appendChild(header);

    const container = document.createElement('div');
    container.style.display = 'flex';
    container.style.gap = '8px';
    container.style.marginTop = '10px';
    container.style.flexWrap = 'wrap';

    const suggestions = (cachedSuggestions && cachedSuggestions.length) ? cachedSuggestions : [
      { label: 'Doctor Timings & OPD', query: 'timings' },
      { label: 'MRI Scan Pricing', query: 'mri scan price' },
      { label: '30-Day Return Policy', query: 'return policy' },
      { label: 'Active Noise Cancelling', query: 'wireless headphones anc' }
    ];

    suggestions.forEach((s) => {
      const btnItem = document.createElement('button');
      btnItem.className = 'warpweb-item';
      btnItem.style.padding = '6px 12px';
      btnItem.style.fontSize = '13px';
      btnItem.textContent = s.label;
      btnItem.addEventListener('click', () => {
        input.value = s.query;
        fetchResults(s.query);
      });
      container.appendChild(btnItem);
    });

    wrap.appendChild(container);
    resultsBox.appendChild(wrap);
  }

  async function fetchResults(query: string) {
    if (!query) {
      renderWelcomeSuggestions();
      return;
    }

    // Cancel in-flight request
    if (activeAbortController) {
      activeAbortController.abort();
    }
    activeAbortController = new AbortController();
    const currentRequestId = ++latestRequestId;

    try {
      const res = await fetch(`${apiHost}/api/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ site_id: siteId, query: query, top_k: 5 }),
        signal: activeAbortController.signal
      });

      // Ignore stale response if a newer query was issued
      if (currentRequestId !== latestRequestId) return;

      const data = await res.json();
      renderResults(data, query);
    } catch (err: any) {
      if (err.name === 'AbortError') return;
      console.error('WarpWeb search failed:', err);
    }
  }

  function renderResults(data: any, query: string) {
    resultsBox.innerHTML = '';
    resultItemsElements = [];
    activeIndex = -1;

    if (!data.results || data.results.length === 0) {
      const emptyDiv = document.createElement('div');
      emptyDiv.className = 'warpweb-empty';

      const pMsg = document.createElement('p');
      pMsg.textContent = 'No match found across website for "';
      const strongQuery = document.createElement('strong');
      strongQuery.textContent = query;
      pMsg.appendChild(strongQuery);
      pMsg.appendChild(document.createTextNode('".'));
      emptyDiv.appendChild(pMsg);

      // Lead capture fallback
      const leadBox = document.createElement('div');
      leadBox.className = 'warpweb-lead-box';

      const leadTitle = document.createElement('strong');
      leadTitle.style.fontSize = '13px';
      leadTitle.style.color = '#0f172a';
      leadTitle.textContent = 'Need immediate assistance?';
      leadBox.appendChild(leadTitle);

      const leadDesc = document.createElement('p');
      leadDesc.style.fontSize = '12px';
      leadDesc.style.color = '#64748b';
      leadDesc.textContent = 'Leave your WhatsApp or phone number and our team will get back to you with the answer:';
      leadBox.appendChild(leadDesc);

      const leadInput = document.createElement('input');
      leadInput.type = 'text';
      leadInput.className = 'warpweb-lead-input';
      leadInput.placeholder = 'Phone or WhatsApp number...';
      leadBox.appendChild(leadInput);

      const consentLabel = document.createElement('label');
      consentLabel.style.display = 'flex';
      consentLabel.style.alignItems = 'flex-start';
      consentLabel.style.gap = '8px';
      consentLabel.style.fontSize = '11.5px';
      consentLabel.style.color = '#64748b';
      consentLabel.style.cursor = 'pointer';

      const consentCheck = document.createElement('input');
      consentCheck.type = 'checkbox';
      consentCheck.checked = true;
      consentCheck.style.marginTop = '2px';

      const consentText = document.createElement('span');
      consentText.textContent = 'I consent to being contacted by site operators regarding this inquiry.';

      consentLabel.appendChild(consentCheck);
      consentLabel.appendChild(consentText);
      leadBox.appendChild(consentLabel);

      const leadSubmit = document.createElement('button');
      leadSubmit.className = 'warpweb-lead-submit';
      leadSubmit.textContent = 'Request Instant Callback';
      leadBox.appendChild(leadSubmit);

      emptyDiv.appendChild(leadBox);

      // Feedback on zero result
      const fbBox = createFeedbackWidget(query);
      fbBox.style.marginTop = '16px';
      fbBox.style.justifyContent = 'center';
      emptyDiv.appendChild(fbBox);

      resultsBox.appendChild(emptyDiv);

      leadSubmit.addEventListener('click', async () => {
        const leadContact = leadInput.value.trim();
        if (!leadContact) return;
        if (!consentCheck.checked) {
          leadDesc.textContent = 'Please check the consent box to submit your contact details.';
          leadDesc.style.color = '#ef4444';
          return;
        }
        try {
          await fetch(`${apiHost}/api/leads`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              site_id: siteId,
              query: query,
              visitor_contact: leadContact,
              consent: true,
              consent_text: consentText.textContent,
              consent_timestamp: Date.now() / 1000
            })
          });
            resultsBox.innerHTML = '';
            const successDiv = document.createElement('div');
            successDiv.className = 'warpweb-empty';
            const checkSpan = document.createElement('span');
            checkSpan.style.color = '#059669';
            checkSpan.style.fontSize = '28px';
            checkSpan.textContent = '✓';
            const pSuccess = document.createElement('p');
            pSuccess.style.marginTop = '8px';
            pSuccess.style.fontWeight = '600';
            pSuccess.textContent = 'Request logged!';
            const pDetail = document.createElement('p');
            pDetail.style.fontSize = '13px';
            pDetail.style.color = '#64748b';
            pDetail.textContent = `Our staff will contact ${leadContact} regarding your request.`;
            successDiv.appendChild(checkSpan);
            successDiv.appendChild(pSuccess);
            successDiv.appendChild(pDetail);
            resultsBox.appendChild(successDiv);
          } catch (e) {
            console.error('Lead submission failed:', e);
          }
      });
      return;
    }

    const currentPath = window.location.pathname;

    data.results.forEach((item: any, rankIdx: number) => {
      const el = document.createElement('div');
      el.className = 'warpweb-item';
      el.id = `warpweb-item-${rankIdx}`;
      el.setAttribute('role', 'option');
      el.setAttribute('tabindex', '-1');

      let targetPath = '';
      try {
        const u = new URL(item.target_url, window.location.href);
        targetPath = u.pathname;
      } catch (e) {
        targetPath = item.target_url || '';
      }

      const isCurrentPage = targetPath === currentPath || targetPath.endsWith(currentPath.split('/').pop() || '');

      let pageLabel = 'Page';
      const uStr = String(item.url || '');
      if (uStr.includes('doctors')) pageLabel = 'Doctors & OPD';
      else if (uStr.includes('diagnostics')) pageLabel = 'Diagnostics & Scans';
      else if (uStr.includes('departments')) pageLabel = 'Departments';
      else if (uStr.includes('products')) pageLabel = 'Catalog';
      else if (uStr.includes('policy')) pageLabel = 'Shipping & Policies';
      else if (uStr.includes('specs')) pageLabel = 'Tech Specs';

      const mainDiv = document.createElement('div');
      mainDiv.className = 'warpweb-item-main';

      const breadcrumbsDiv = document.createElement('div');
      breadcrumbsDiv.className = 'warpweb-item-breadcrumbs';

      const pageSpan = document.createElement('span');
      pageSpan.textContent = pageLabel;
      const arrowSpan = document.createElement('span');
      arrowSpan.textContent = '›';
      breadcrumbsDiv.appendChild(pageSpan);
      breadcrumbsDiv.appendChild(arrowSpan);

      const navBadge = document.createElement('span');
      if (!isCurrentPage) {
        navBadge.className = 'warpweb-cross-page-badge';
        navBadge.textContent = 'Cross-page';
      } else {
        navBadge.textContent = 'Current page';
      }
      breadcrumbsDiv.appendChild(navBadge);
      mainDiv.appendChild(breadcrumbsDiv);

      const titleDiv = document.createElement('div');
      titleDiv.className = 'warpweb-item-title';
      const titleSpan = document.createElement('span');
      titleSpan.textContent = item.title || '';
      titleDiv.appendChild(titleSpan);

      if (item.match_type === 'override') {
        const tag = document.createElement('span');
        tag.className = 'warpweb-tag';
        tag.style.background = '#fef3c7';
        tag.style.color = '#b45309';
        tag.textContent = 'Verified';
        titleDiv.appendChild(tag);
      } else if (item.match_type === 'hybrid') {
        const tag = document.createElement('span');
        tag.className = 'warpweb-tag';
        tag.textContent = 'High Confidence';
        titleDiv.appendChild(tag);
      }
      mainDiv.appendChild(titleDiv);

      const snippetDiv = document.createElement('div');
      snippetDiv.className = 'warpweb-item-snippet';
      snippetDiv.textContent = item.snippet || '';
      mainDiv.appendChild(snippetDiv);

      if (item.metadata && (item.metadata.timings || item.metadata.price)) {
        const metaDiv = document.createElement('div');
        metaDiv.className = 'warpweb-item-meta';
        if (item.metadata.timings) {
          const timingSpan = document.createElement('span');
          timingSpan.className = 'warpweb-meta-timings';
          timingSpan.textContent = `🕒 ${item.metadata.timings}`;
          metaDiv.appendChild(timingSpan);
        }
        if (item.metadata.price) {
          const priceSpan = document.createElement('span');
          priceSpan.className = 'warpweb-meta-price';
          priceSpan.textContent = `💰 ${item.metadata.price}`;
          metaDiv.appendChild(priceSpan);
        }
        mainDiv.appendChild(metaDiv);
      }

      el.appendChild(mainDiv);

      // Render Multiple Actions
      const actionsContainer = document.createElement('div');
      actionsContainer.className = 'warpweb-actions-container';

      const actionsList = (item.actions && item.actions.length > 0) ? item.actions : [{
        type: item.action_type || 'navigate',
        label: item.action_label || (isCurrentPage ? 'Jump' : 'Navigate'),
        url: item.target_url
      }];

      actionsList.forEach((act: any, aIdx: number) => {
        const actionBadge = document.createElement('div');
        actionBadge.className = `warpweb-action-badge ${aIdx > 0 ? 'warpweb-action-secondary' : ''}`;
        actionBadge.setAttribute('role', 'button');
        actionBadge.setAttribute('tabindex', '0');
        const actionText = document.createElement('span');
        actionText.textContent = act.label;
        actionBadge.appendChild(actionText);

        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('width', '11');
        svg.setAttribute('height', '11');
        svg.setAttribute('fill', 'none');
        svg.setAttribute('stroke', 'currentColor');
        svg.setAttribute('stroke-width', '2');
        svg.setAttribute('viewBox', '0 0 24 24');
        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.setAttribute('d', 'M5 12h14M12 5l7 7-7 7');
        svg.appendChild(path);
        actionBadge.appendChild(svg);

        actionBadge.addEventListener('click', (e) => {
          e.stopPropagation();
          trackClick(data.query_id, query, item.id, rankIdx + 1, act.url);
          closeModal();
          navigateToUrl(act.url);
        });

        actionsContainer.appendChild(actionBadge);
      });

      el.appendChild(actionsContainer);

      el.addEventListener('click', () => {
        trackClick(data.query_id, query, item.id, rankIdx + 1, item.target_url);
        closeModal();
        handleCrossPageNavigation(item, isCurrentPage);
      });

      resultItemsElements.push(el);
      resultsBox.appendChild(el);
    });

    // Feedback row at bottom of results
    const footerFeedback = document.createElement('div');
    footerFeedback.style.padding = '8px 14px';
    footerFeedback.style.display = 'flex';
    footerFeedback.style.justifyContent = 'flex-end';
    footerFeedback.appendChild(createFeedbackWidget(query));
    resultsBox.appendChild(footerFeedback);
  }

  function createFeedbackWidget(query: string): HTMLElement {
    const box = document.createElement('div');
    box.className = 'warpweb-feedback-box';

    const lbl = document.createElement('span');
    lbl.textContent = 'Was this helpful?';
    box.appendChild(lbl);

    const yesBtn = document.createElement('button');
    yesBtn.className = 'warpweb-feedback-btn';
    yesBtn.textContent = '👍 Yes';
    yesBtn.onclick = () => sendFeedback(query, true, box);
    box.appendChild(yesBtn);

    const noBtn = document.createElement('button');
    noBtn.className = 'warpweb-feedback-btn';
    noBtn.textContent = '👎 No';
    noBtn.onclick = () => sendFeedback(query, false, box);
    box.appendChild(noBtn);

    return box;
  }

  function sendFeedback(query: string, isPositive: boolean, container: HTMLElement) {
    try {
      fetch(`${apiHost}/api/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ site_id: siteId, query: query, is_positive: isPositive })
      });
      container.innerHTML = '<span style="color: #059669; font-weight: 500;">Thank you for your feedback!</span>';
    } catch (e) {
      console.error(e);
    }
  }

  function trackClick(queryId: any, query: string, resultId: string, rank: number, targetUrl: string) {
    try {
      fetch(`${apiHost}/api/clicks`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          site_id: siteId,
          query_id: queryId || null,
          query: query,
          result_id: resultId,
          rank: rank,
          target_url: targetUrl
        })
      });
    } catch (e) {
      // Non-blocking telemetry
    }
  }

  function navigateToUrl(destinationUrl: string) {
    try {
      const parsedUrl = new URL(destinationUrl, window.location.href);
      if (parsedUrl.protocol === 'http:' || parsedUrl.protocol === 'https:' || parsedUrl.protocol === 'tel:') {
        window.location.href = parsedUrl.href;
      } else {
        console.warn('WarpWeb blocked navigation to unsafe URL protocol:', destinationUrl);
      }
    } catch (e) {
      console.warn('WarpWeb invalid destination URL:', destinationUrl);
    }
  }

  function handleCrossPageNavigation(item: any, isCurrentPage: boolean) {
    if (isCurrentPage && item.anchor_id) {
      const targetElem = document.getElementById(item.anchor_id);
      if (targetElem) {
        targetElem.scrollIntoView({ behavior: 'smooth', block: 'center' });
        targetElem.classList.remove('warpweb-highlight-target');
        void targetElem.offsetWidth;
        targetElem.classList.add('warpweb-highlight-target');
        return;
      }
    }

    let destinationUrl = item.target_url || '';
    if (item.anchor_id && !destinationUrl.includes('#')) {
      destinationUrl += `#${item.anchor_id}`;
    }

    navigateToUrl(destinationUrl);
  }

  (window as any).__warpwebQuick = function (q: string) {
    input.value = q;
    fetchResults(q);
  };
})();
