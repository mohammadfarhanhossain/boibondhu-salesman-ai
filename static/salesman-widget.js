/**
 * বইবন্ধু AI (BoiBondhu AI) - Embeddable Bookstore Salesman & Live Price Comparator Widget
 * -------------------------------------------------------------------------------------------
 * Embed this widget on any website by adding a single line of script:
 *   <script src="http://localhost:5000/widget.js" async></script>
 * 
 * Features:
 * - Scoped styling (no conflicts with host CSS)
 * - Real-time Bengali conversational book recommendations
 * - Direct integration with 17-store live price & stock comparison
 * - Session credit tracking (15 free credits/session)
 * - Optional BYOK (Bring Your Own Gemini Key) setting
 * - Mobile responsive drawer & floating launcher
 */

(function () {
  'use strict';

  if (window.__BOIBONDHU_WIDGET_LOADED__) return;
  window.__BOIBONDHU_WIDGET_LOADED__ = true;

  // 1. Determine Backend API Host
  var scripts = document.getElementsByTagName('script');
  var currentScript = scripts[scripts.length - 1];
  var scriptSrc = currentScript ? currentScript.src : '';
  var defaultHost = 'http://localhost:5000';

  if (scriptSrc && scriptSrc.indexOf('http') === 0) {
    try {
      var url = new URL(scriptSrc);
      defaultHost = url.origin;
    } catch (e) {}
  }

  var API_HOST = window.BOIBONDHU_API_HOST || defaultHost;

  // 1.1 Multi-Tenant Merchant Resolution
  var merchantId = 'default';
  if (currentScript) {
    merchantId = currentScript.getAttribute('data-merchant') || currentScript.getAttribute('data-store') || 'default';
  }
  if (window.BoiBondhuConfig && window.BoiBondhuConfig.merchantId) {
    merchantId = window.BoiBondhuConfig.merchantId;
  }
  try {
    var urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('merchant')) {
      merchantId = urlParams.get('merchant');
    }
  } catch (e) {}

  // 2. Local State Management
  var STORAGE_KEY_SESSION = 'boibondhu_sess_id';
  var STORAGE_KEY_KEY = 'boibondhu_api_key';

  var sessionId = localStorage.getItem(STORAGE_KEY_SESSION);
  if (!sessionId) {
    sessionId = 'bb_' + Math.random().toString(36).substring(2, 9) + '_' + Date.now();
    localStorage.setItem(STORAGE_KEY_SESSION, sessionId);
  }

  var userApiKey = localStorage.getItem(STORAGE_KEY_KEY) || '';
  var creditsLeft = 15;
  var isOpen = false;
  var isTyping = false;

  // 3. Inject Scoped CSS
  var style = document.createElement('style');
  style.id = 'bb-widget-styles';
  style.textContent = `
    @import url('https://fonts.googleapis.com/css2?family=Hind+Siliguri:wght@400;500;600;700&display=swap');

    #bb-root {
      font-family: 'Hind Siliguri', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      font-size: 14px;
      line-height: 1.5;
      color: #1e293b;
      position: fixed;
      bottom: 24px;
      right: 24px;
      z-index: 999999;
      pointer-events: none;
    }

    #bb-root * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }

    /* Floating Launcher Button */
    .bb-launcher {
      pointer-events: auto;
      background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%);
      color: white;
      border: none;
      padding: 14px 26px;
      border-radius: 999px;
      display: flex;
      align-items: center;
      gap: 12px;
      cursor: pointer;
      box-shadow: 0 10px 28px rgba(30, 58, 138, 0.4);
      transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
      position: absolute;
      bottom: 0;
      right: 0;
      font-family: inherit;
      font-weight: 700;
      font-size: 16.5px;
    }

    .bb-launcher:hover {
      transform: translateY(-2px) scale(1.03);
      box-shadow: 0 14px 34px rgba(30, 58, 138, 0.5);
    }

    .bb-launcher-icon {
      font-size: 28px;
      display: inline-block;
      animation: bb-bounce 2s infinite ease-in-out;
    }

    .bb-launcher-badge {
      background: #10b981;
      width: 12px;
      height: 12px;
      border-radius: 50%;
      border: 2px solid white;
      position: absolute;
      top: -2px;
      right: -2px;
      animation: bb-pulse 2s infinite;
    }

    @keyframes bb-bounce {
      0%, 100% { transform: translateY(0); }
      50% { transform: translateY(-4px); }
    }

    @keyframes bb-pulse {
      0% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
      70% { box-shadow: 0 0 0 8px rgba(16, 185, 129, 0); }
      100% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
    }

    /* Chat Drawer Container */
    .bb-window {
      pointer-events: auto;
      position: absolute;
      bottom: 78px;
      right: 0;
      width: 480px;
      max-width: calc(100vw - 28px);
      height: 720px;
      max-height: calc(100vh - 96px);
      background: #ffffff;
      border-radius: 22px;
      box-shadow: 0 24px 48px rgba(15, 23, 42, 0.24), 0 0 0 1px rgba(15, 23, 42, 0.08);
      display: flex;
      flex-direction: column;
      overflow: hidden;
      opacity: 0;
      transform: translateY(16px) scale(0.96);
      transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
      visibility: hidden;
    }

    .bb-window.bb-open {
      opacity: 1;
      transform: translateY(0) scale(1);
      visibility: visible;
    }

    /* Window Header */
    .bb-header {
      background: linear-gradient(135deg, #1e3a8a, #0f172a);
      color: white;
      padding: 18px 20px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      border-bottom: 1px solid rgba(255, 255, 255, 0.1);
    }

    .bb-header-info {
      display: flex;
      align-items: center;
      gap: 14px;
    }

    .bb-avatar {
      width: 56px;
      height: 56px;
      border-radius: 16px;
      background: rgba(255, 255, 255, 0.18);
      backdrop-filter: blur(6px);
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 32px;
      border: 1.5px solid rgba(255, 255, 255, 0.25);
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
      flex-shrink: 0;
    }

    .bb-title-area h3 {
      font-size: 18px;
      font-weight: 700;
      color: #ffffff;
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .bb-title-area p {
      font-size: 13px;
      color: #94a3b8;
    }

    .bb-header-actions {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .bb-icon-btn {
      background: rgba(255, 255, 255, 0.14);
      border: none;
      color: white;
      width: 36px;
      height: 36px;
      border-radius: 10px;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: background 0.2s;
      font-size: 16px;
    }

    .bb-icon-btn:hover {
      background: rgba(255, 255, 255, 0.28);
    }

    /* Credit Strip */
    .bb-credit-strip {
      background: #f1f5f9;
      padding: 6px 16px;
      font-size: 12px;
      color: #475569;
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid #e2e8f0;
    }

    .bb-credit-badge {
      background: #e0e7ff;
      color: #3730a3;
      padding: 2px 8px;
      border-radius: 999px;
      font-weight: 600;
      font-size: 11px;
    }

    /* Messages Area */
    .bb-messages {
      flex: 1;
      padding: 18px;
      overflow-y: auto;
      background: #f8fafc;
      display: flex;
      flex-direction: column;
      gap: 14px;
    }

    .bb-msg {
      max-width: 88%;
      padding: 12px 16px;
      border-radius: 18px;
      line-height: 1.55;
      font-size: 14.5px;
      word-wrap: break-word;
      animation: bb-fadein 0.2s ease-out;
    }

    @keyframes bb-fadein {
      from { opacity: 0; transform: translateY(6px); }
      to { opacity: 1; transform: translateY(0); }
    }

    .bb-msg-user {
      align-self: flex-end;
      background: linear-gradient(135deg, #1e3a8a, #2563eb);
      color: white;
      border-bottom-right-radius: 4px;
    }

    .bb-msg-assistant {
      align-self: flex-start;
      background: white;
      color: #1e293b;
      border: 1px solid #e2e8f0;
      border-bottom-left-radius: 4px;
      box-shadow: 0 2px 4px rgba(0,0,0,0.02);
    }

    .bb-msg-assistant p {
      margin-bottom: 6px;
    }
    .bb-msg-assistant p:last-child {
      margin-bottom: 0;
    }

    .bb-msg-assistant strong {
      color: #0f172a;
      font-weight: 600;
    }

    .bb-msg-assistant a {
      color: #2563eb;
      text-decoration: none;
      font-weight: 600;
    }

    .bb-msg-assistant a:hover {
      text-decoration: underline;
    }

    /* Live Deal Cards in chat */
    .bb-deals-container {
      margin-top: 10px;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }

    .bb-deal-card {
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 10px;
      padding: 8px 12px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
    }

    .bb-deal-info {
      display: flex;
      flex-direction: column;
      gap: 2px;
    }

    .bb-deal-store {
      font-weight: 700;
      font-size: 13px;
      color: #0f172a;
      display: flex;
      align-items: center;
      gap: 6px;
    }

    .bb-deal-price {
      font-size: 14px;
      font-weight: 700;
      color: #16a34a;
    }

    .bb-deal-stock {
      font-size: 11px;
      color: #059669;
      font-weight: 500;
    }

    .bb-deal-btn {
      background: #2563eb;
      color: white !important;
      text-decoration: none !important;
      padding: 5px 12px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
      white-space: nowrap;
      transition: background 0.2s;
    }

    .bb-deal-btn:hover {
      background: #1d4ed8;
    }

    /* Suggestion Chips */
    .bb-chips {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 6px;
    }

    .bb-chip {
      background: #ffffff;
      border: 1px solid #cbd5e1;
      color: #334155;
      padding: 5px 10px;
      border-radius: 999px;
      font-size: 12px;
      cursor: pointer;
      transition: all 0.2s;
      font-family: inherit;
    }

    .bb-chip:hover {
      background: #eff6ff;
      border-color: #3b82f6;
      color: #1d4ed8;
      transform: translateY(-1px);
    }

    /* Typing Dots */
    .bb-typing {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 8px 14px;
      background: white;
      border: 1px solid #e2e8f0;
      border-radius: 16px;
      width: fit-content;
    }

    .bb-dot {
      width: 6px;
      height: 6px;
      background: #94a3b8;
      border-radius: 50%;
      animation: bb-typing-blink 1.4s infinite;
    }

    .bb-dot:nth-child(2) { animation-delay: 0.2s; }
    .bb-dot:nth-child(3) { animation-delay: 0.4s; }

    @keyframes bb-typing-blink {
      0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
      40% { transform: scale(1); opacity: 1; }
    }

    /* Input Footer */
    .bb-footer {
      padding: 12px;
      background: white;
      border-top: 1px solid #e2e8f0;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }

    .bb-input-row {
      display: flex;
      gap: 10px;
      align-items: center;
    }

    .bb-input {
      flex: 1;
      padding: 12px 16px;
      border: 1px solid #cbd5e1;
      border-radius: 14px;
      font-size: 14.5px;
      outline: none;
      font-family: inherit;
      transition: border-color 0.2s;
    }

    .bb-input:focus {
      border-color: #2563eb;
      box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
    }

    .bb-send-btn {
      background: #1e3a8a;
      border: none;
      color: white;
      width: 46px;
      height: 46px;
      border-radius: 14px;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: background 0.2s, transform 0.1s;
      flex-shrink: 0;
    }

    .bb-send-btn:hover {
      background: #2563eb;
    }

    .bb-send-btn:active {
      transform: scale(0.95);
    }

    .bb-send-btn:disabled {
      background: #94a3b8;
      cursor: not-allowed;
    }

    .bb-btn-sm {
      padding: 6px 12px;
      font-size: 12px;
      border-radius: 6px;
      border: none;
      cursor: pointer;
      font-family: inherit;
      font-weight: 600;
    }

    .bb-btn-primary { background: #2563eb; color: white; }
    .bb-btn-secondary { background: #f1f5f9; color: #475569; }

    /* Mobile Responsive */
    @media (max-width: 520px) {
      #bb-root {
        bottom: 16px;
        right: 16px;
      }
      .bb-window {
        width: calc(100vw - 24px);
        height: calc(100vh - 84px);
        bottom: 64px;
        border-radius: 18px;
      }
      .bb-header {
        padding: 14px 16px;
      }
      .bb-avatar {
        width: 48px;
        height: 48px;
        font-size: 28px;
      }
      .bb-title-area h3 {
        font-size: 16.5px;
      }
    }
  `;
  document.head.appendChild(style);

  // 4. Construct Widget DOM
  var root = document.createElement('div');
  root.id = 'bb-root';
  root.innerHTML = `
    <!-- Floating Launcher -->
    <button class="bb-launcher" id="bb-launcher-btn" aria-label="বইবন্ধু AI খুলুন">
      <span class="bb-launcher-icon">📚</span>
      <span>বইবন্ধু AI</span>
      <div class="bb-launcher-badge"></div>
    </button>

    <!-- Main Chat Window -->
    <div class="bb-window" id="bb-chat-window">
      <!-- Header -->
      <div class="bb-header">
        <div class="bb-header-info">
          <div class="bb-avatar">🤖</div>
          <div class="bb-title-area">
            <h3>বইবন্ধু AI <span style="font-size:11px; font-weight:normal; background:rgba(255,255,255,0.2); padding:2px 6px; border-radius:4px;">২১+ শপ ও প্রকাশনী</span></h3>
            <p>আপনার ব্যক্তিগত বই সেলসম্যান ও প্রাইস ফাইন্ডার</p>
          </div>
        </div>
        <div class="bb-header-actions">
          <button class="bb-icon-btn" id="bb-close-btn" title="বন্ধ করুন">✕</button>
        </div>
      </div>

      <!-- Credit Strip -->
      <div class="bb-credit-strip">
        <span>স্মার্ট বই সেলসম্যান ও প্রাইস অ্যাসিস্ট্যান্ট</span>
        <span class="bb-credit-badge" id="bb-credit-display">অনলাইন একটিভ</span>
      </div>

      <!-- Messages Area -->
      <div class="bb-messages" id="bb-messages-list">
        <!-- Initial Assistant Message -->
        <div class="bb-msg bb-msg-assistant">
          <p>সালাম/নমস্কার প্রিয় পাঠক! 👋</p>
          <p>আমি <strong>বইবন্ধু</strong>—আপনার পছন্দের বই খুঁজে দিতে এবং বাংলাদেশের <strong>২১টি অনলাইন বুকশপ ও শীর্ষ প্রকাশনী</strong> থেকে সবচেয়ে কম দামে স্টকে থাকা সেরা ডিল বের করে দিতে প্রস্তুত।</p>
          <p style="margin-top:6px; color:#64748b; font-size:12.5px;">নিচের টপিকগুলোতে চাপ দিন অথবা আপনার মনের মতো যেকোনো বইয়ের কথা লিখুন:</p>
          <div class="bb-chips">
            <button class="bb-chip" data-prompt="হতাশা ও দুশ্চিন্তা কাটানোর ভালো বই">🌱 হতাশা ও দুশ্চিন্তা কাটানোর বই</button>
            <button class="bb-chip" data-prompt="৫০০ টাকার মধ্যে সেরা ইসলামিক বই">📖 ৫০০ টাকার মধ্যে ইসলামিক বই</button>
            <button class="bb-chip" data-prompt="রহস্য রোমাঞ্চ ও থ্রিলার বই">🕵️‍♂️ থ্রিলার ও গোয়েন্দা বই</button>
            <button class="bb-chip" data-prompt="হুমায়ূন আহমেদের জনপ্রিয় উপন্যাস">✨ হুমায়ূন আহমেদের উপন্যাস</button>
          </div>
        </div>
      </div>

      <!-- Input Bar -->
      <div class="bb-footer">
        <div class="bb-input-row">
          <input type="text" class="bb-input" id="bb-chat-input" placeholder="যেমন: ক্যারিয়ারের জন্য ভালো বই..." autocomplete="off">
          <button class="bb-send-btn" id="bb-send-btn" aria-label="পাঠান">
            <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round">
              <line x1="22" y1="2" x2="11" y2="13"></line>
              <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
            </svg>
          </button>
        </div>
      </div>
    </div>
  `;
  document.body.appendChild(root);

  // 5. Select UI Elements
  var launcherBtn = document.getElementById('bb-launcher-btn');
  var chatWindow = document.getElementById('bb-chat-window');
  var closeBtn = document.getElementById('bb-close-btn');
  var creditDisplay = document.getElementById('bb-credit-display');
  var messagesList = document.getElementById('bb-messages-list');
  var chatInput = document.getElementById('bb-chat-input');
  var sendBtn = document.getElementById('bb-send-btn');

  // Toggle Window
  function toggleWindow(open) {
    isOpen = typeof open === 'boolean' ? open : !isOpen;
    if (isOpen) {
      chatWindow.classList.add('bb-open');
      launcherBtn.style.display = 'none';
      setTimeout(function () { chatInput.focus(); }, 150);
    } else {
      chatWindow.classList.remove('bb-open');
      launcherBtn.style.display = 'flex';
    }
  }

  launcherBtn.addEventListener('click', function () { toggleWindow(true); });
  closeBtn.addEventListener('click', function () { toggleWindow(false); });

  // Markdown Formatter Helper
  function formatMarkdown(text) {
    if (!text) return '';
    var safe = text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');

    // Bold **text**
    safe = safe.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    // Italic *text*
    safe = safe.replace(/\*(.*?)\*/g, '<em>$1</em>');
    // Links [title](url)
    safe = safe.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1 ↗</a>');
    // Bullet points
    safe = safe.replace(/^[•\-\*]\s+(.*)$/gm, '<li style="margin-left:16px;">$1</li>');
    // Paragraphs / line breaks
    safe = safe.replace(/\n\n+/g, '</p><p>');
    safe = safe.replace(/\n/g, '<br>');

    return '<p>' + safe + '</p>';
  }

  // Scroll to bottom
  function scrollToBottom() {
    messagesList.scrollTop = messagesList.scrollHeight;
  }

  // Append User Message
  function appendUserMessage(text) {
    var msg = document.createElement('div');
    msg.className = 'bb-msg bb-msg-user';
    msg.textContent = text;
    messagesList.appendChild(msg);
    scrollToBottom();
  }

  // Append Assistant Message with Deals or Action Chips
  function appendAssistantMessage(text, deals, recommendedBooks, wantsPrice, humanHandover) {
    var msg = document.createElement('div');
    msg.className = 'bb-msg bb-msg-assistant';
    msg.innerHTML = formatMarkdown(text);

    // 0. Human Handover Action Card
    if (humanHandover) {
      var handoverWrap = document.createElement('div');
      handoverWrap.style.marginTop = '10px';
      handoverWrap.innerHTML = `
        <a href="https://wa.me/8801700000000" target="_blank" rel="noopener noreferrer" class="bb-deal-btn" style="background:#059669; padding:8px 16px; font-size:13px; display:inline-flex; align-items:center; gap:8px; border-radius:8px; box-shadow:0 4px 12px rgba(5,150,105,0.25);">
          <span>💬</span> প্রতিনিধির সাথে সরাসরি কথা বলুন (WhatsApp / কল) ↗
        </a>
      `;
      msg.appendChild(handoverWrap);
    }

    // 1. If top deals exist (price query), render live deal cards
    if (deals && deals.length > 0) {
      var dealsWrap = document.createElement('div');
      dealsWrap.className = 'bb-deals-container';

      // If top deal has metadata (image, author, publisher, subject), display Book Profile Header
      var topDeal = deals[0];
      if (topDeal && (topDeal.image || topDeal.author || topDeal.publisher || topDeal.subject)) {
        var bookHeader = document.createElement('div');
        bookHeader.style.cssText = 'background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px; padding:10px; margin-bottom:8px; display:flex; gap:10px; align-items:flex-start;';
        
        var imgTag = topDeal.image ? 
          `<img src="${topDeal.image}" alt="${topDeal.title || ''}" style="width:50px; height:70px; object-fit:cover; border-radius:6px; box-shadow:0 2px 5px rgba(0,0,0,0.12); flex-shrink:0;" onerror="this.style.display='none'">` :
          `<div style="width:50px; height:70px; background:#e0e7ff; color:#3730a3; border-radius:6px; display:flex; align-items:center; justify-content:center; font-size:24px; flex-shrink:0;">📖</div>`;
        
        var metaAuth = topDeal.author ? `<div style="font-size:12px; color:#475569; margin-top:2px;">👤 <strong>লেখক:</strong> ${topDeal.author}</div>` : '';
        var metaPub = topDeal.publisher ? `<div style="font-size:11.5px; color:#64748b; margin-top:1px;">🏢 <strong>প্রকাশনী:</strong> ${topDeal.publisher}</div>` : '';
        var metaSubj = topDeal.subject ? `<div style="font-size:11px; color:#2563eb; background:#eff6ff; display:inline-block; padding:1px 6px; border-radius:4px; margin-top:3px;">🏷️ ${topDeal.subject}</div>` : '';
        
        bookHeader.innerHTML = `
          ${imgTag}
          <div style="flex:1; min-width:0;">
            <div style="font-size:13.5px; font-weight:700; color:#0f172a; line-height:1.3;">${topDeal.title || 'বইয়ের বিবরণ'}</div>
            ${metaAuth}
            ${metaPub}
            ${metaSubj}
          </div>
        `;
        dealsWrap.appendChild(bookHeader);
      }

      deals.slice(0, 5).forEach(function (deal, idx) {
        var card = document.createElement('div');
        card.className = 'bb-deal-card';

        var badgeIcons = ['🥇 ১ম', '🥈 ২য়', '🥉 ৩য়', '🎖️ ৪র্থ', '⭐ ৫ম'];
        var badge = idx < badgeIcons.length ? badgeIcons[idx] : `#${idx + 1}`;
        var regPrice = deal.regular_price ? `<span style="text-decoration:line-through; color:#94a3b8; font-size:11px; margin-left:4px;">৳${deal.regular_price}</span>` : '';

        card.innerHTML = `
          <div class="bb-deal-info">
            <span class="bb-deal-store">${badge} ${deal.store}</span>
            <div>
              <span class="bb-deal-price">৳${deal.price}</span>
              ${regPrice}
            </div>
            <span class="bb-deal-stock">${deal.stock_text || (deal.in_stock ? '● স্টকে আছে' : '○ স্টক সীমিত')}</span>
          </div>
          ${deal.url ? `<a href="${deal.url}" target="_blank" rel="noopener noreferrer" class="bb-deal-btn">অর্ডার লিংক ↗</a>` : ''}
        `;
        dealsWrap.appendChild(card);
      });

      msg.appendChild(dealsWrap);

      // Add instant 1-tap quick inquiry chips
      var actionChips = document.createElement('div');
      actionChips.className = 'bb-chips';
      actionChips.style.marginTop = '8px';
      actionChips.innerHTML = `
        <button class="bb-chip" data-prompt="বইটির বিস্তারিত বিষয়বস্তু ও সূচিপত্র দেখতে চাই">📑 সূচিপত্র ও বিষয়বস্তু জানুন</button>
        <button class="bb-chip" data-prompt="বইটির পাঠক রিভিউ ও রেটিং কেমন?">⭐ পাঠক রিভিউ জানুন</button>
      `;
      msg.appendChild(actionChips);
    } else if (recommendedBooks && recommendedBooks.length > 0) {
      // 2. Stage 1: Recommendation flow. Provide rich book showcase cards with Cover Image, Author, Publisher, Topic & Price!
      var recContainer = document.createElement('div');
      recContainer.style.cssText = 'display:flex; flex-direction:column; gap:10px; margin-top:12px;';

      recommendedBooks.slice(0, 4).forEach(function (book) {
        var card = document.createElement('div');
        card.style.cssText = 'background:#ffffff; border:1px solid #e2e8f0; border-radius:10px; padding:10px; display:flex; gap:10px; align-items:flex-start; box-shadow:0 2px 6px rgba(0,0,0,0.03);';

        var imgTag = book.image ? 
          `<img src="${book.image}" alt="${book.title}" style="width:48px; height:68px; object-fit:cover; border-radius:6px; box-shadow:0 2px 4px rgba(0,0,0,0.1); flex-shrink:0;" onerror="this.style.display='none'">` :
          `<div style="width:48px; height:68px; background:#eff6ff; color:#1d4ed8; border-radius:6px; display:flex; align-items:center; justify-content:center; font-size:22px; flex-shrink:0;">📖</div>`;

        var authHtml = book.author ? `<div style="font-size:12px; color:#475569; margin-top:2px;">👤 <strong>লেখক:</strong> ${book.author}</div>` : '';
        var pubHtml = book.publisher ? `<div style="font-size:11.5px; color:#64748b; margin-top:1px;">🏢 <strong>প্রকাশনী:</strong> ${book.publisher}</div>` : '';
        var subjHtml = book.subject ? `<div style="font-size:11px; color:#2563eb; background:#eff6ff; display:inline-block; padding:1px 6px; border-radius:4px; margin-top:3px;">🏷️ ${book.subject}</div>` : '';
        var priceHtml = book.price ? `<div style="font-size:12.5px; font-weight:700; color:#059669; margin-top:3px;">💰 আনুমানিক মূল্য: ৳${book.price}</div>` : '';

        card.innerHTML = `
          ${imgTag}
          <div style="flex:1; min-width:0;">
            <div style="font-size:13.5px; font-weight:700; color:#0f172a; line-height:1.3;">${book.title}</div>
            ${authHtml}
            ${pubHtml}
            ${subjHtml}
            ${priceHtml}
            <div style="display:flex; flex-wrap:wrap; gap:6px; margin-top:8px;">
              <button class="bb-chip" style="padding:4px 8px; font-size:11px;" data-prompt="${book.title} বইটির দাম কত?">💰 লাইভ দাম দেখুন</button>
              <button class="bb-chip" style="padding:4px 8px; font-size:11px;" data-prompt="${book.title} বইটির সূচিপত্র ও বিষয়বস্তু কি?">📑 সূচিপত্র</button>
            </div>
          </div>
        `;
        recContainer.appendChild(card);
      });

      msg.appendChild(recContainer);
    }

    messagesList.appendChild(msg);
    scrollToBottom();
  }

  // Show / Hide Typing Indicator
  var typingElement = null;
  function showTyping() {
    if (typingElement) return;
    typingElement = document.createElement('div');
    typingElement.className = 'bb-typing';
    typingElement.innerHTML = `
      <div class="bb-dot"></div><div class="bb-dot"></div><div class="bb-dot"></div>
      <span style="font-size:12px; color:#64748b; margin-left:6px; font-weight:500;">২১টি শপ ও প্রকাশনীতে লাইভ সেরা দাম যাচাই হচ্ছে...</span>
    `;
    messagesList.appendChild(typingElement);
    scrollToBottom();
  }

  function hideTyping() {
    if (typingElement && typingElement.parentNode) {
      typingElement.parentNode.removeChild(typingElement);
      typingElement = null;
    }
  }

  // Handle Quick Chips Click
  messagesList.addEventListener('click', function (e) {
    var chip = e.target.closest('.bb-chip');
    if (chip && !isTyping) {
      var prompt = chip.getAttribute('data-prompt') || chip.textContent.trim();
      chatInput.value = prompt;
      handleSendMessage();
    }
  });

  // Send Message Logic
  function handleSendMessage() {
    var message = chatInput.value.trim();
    if (!message || isTyping) return;

    chatInput.value = '';
    appendUserMessage(message);

    isTyping = true;
    sendBtn.disabled = true;
    showTyping();

    var payload = {
      message: message,
      session_id: sessionId,
      api_key: userApiKey || undefined,
      merchant_id: merchantId
    };

    fetch(API_HOST + '/api/salesman/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    })
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (data) {
        hideTyping();
        isTyping = false;
        sendBtn.disabled = false;

        if (data.session_id) {
          sessionId = data.session_id;
          localStorage.setItem(STORAGE_KEY_SESSION, sessionId);
        }

        if (typeof data.credits_left === 'number') {
          creditsLeft = data.credits_left;
          creditDisplay.textContent = creditsLeft + ' ক্রেডিট বাকি';
          if (creditsLeft <= 0) {
            creditDisplay.style.background = '#fee2e2';
            creditDisplay.style.color = '#991b1b';
          }
        }

        appendAssistantMessage(data.reply, data.live_deals, data.recommended_books, data.wants_price, data.human_handover);
      })
      .catch(function (err) {
        console.error('[BoiBondhu]', err);
        hideTyping();
        isTyping = false;
        sendBtn.disabled = false;
        appendAssistantMessage('দুঃখিত, সংযোগে কিছুটা সমস্যা হয়েছে। দয়া করে আরেকবার চেষ্টা করুন।');
      });
  }

  sendBtn.addEventListener('click', handleSendMessage);
  chatInput.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleSendMessage();
    }
  });

  function fetchMerchantConfig() {
    if (!merchantId || merchantId === 'default') return;
    fetch(API_HOST + '/api/merchant/config?id=' + encodeURIComponent(merchantId))
      .then(function (r) { return r.json(); })
      .then(function (m) {
        if (!m || !m.name) return;
        var launcherBtn = document.getElementById('bb-launcher-btn');
        var launcherText = launcherBtn.querySelector('span:nth-child(2)');
        var launcherIcon = launcherBtn.querySelector('.bb-launcher-icon');
        var header = document.querySelector('.bb-header');
        var avatar = document.querySelector('.bb-avatar');
        var titleElem = document.querySelector('.bb-title-area h3');
        var subtitleElem = document.querySelector('.bb-title-area p');
        var initMsg = document.querySelector('.bb-messages .bb-msg-assistant p:nth-child(2)');

        if (m.theme_gradient) {
          launcherBtn.style.background = m.theme_gradient;
          header.style.background = m.theme_gradient;
        }
        if (m.logo_emoji) {
          launcherIcon.textContent = m.logo_emoji;
          avatar.textContent = m.logo_emoji;
        }
        if (m.name) {
          launcherText.textContent = m.name.split(' ')[0] + ' AI';
          titleElem.innerHTML = m.name + (m.mode === 'store_exclusive' ? ' <span style="font-size:11px; font-weight:normal; background:rgba(255,255,255,0.2); padding:2px 6px; border-radius:4px;">অফিসিয়াল স্টোর</span>' : ' <span style="font-size:11px; font-weight:normal; background:rgba(255,255,255,0.2); padding:2px 6px; border-radius:4px;">২১+ শপ ও প্রকাশনী</span>');
        }
        if (m.mode === 'store_exclusive') {
          subtitleElem.textContent = 'আপনার পছন্দের বই খুঁজে পেতে এবং সরাসরি অর্ডার করতে সাহায্য করছি';
          if (initMsg && m.greeting) {
            initMsg.innerHTML = m.greeting;
          }
        }
      })
      .catch(function (e) {});
  }
  fetchMerchantConfig();

  // Expose global controller if website wants to open it programmatically
  window.BoiBondhu = {
    open: function () { toggleWindow(true); },
    close: function () { toggleWindow(false); },
    toggle: function () { toggleWindow(); },
    sendMessage: function (text) {
      chatInput.value = text;
      handleSendMessage();
    }
  };

  console.log('[BoiBondhu AI] Widget initialized on ' + window.location.hostname);
})();
