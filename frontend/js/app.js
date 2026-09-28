const API_BASE = '/api/v1';

let currentDocument = null;
let documentsList = [];
let vendorChart = null;
let categoryChart = null;
let confidenceChart = null;
let monthlyChart = null;
let searchDebounceTimer = null;
let currentSearchTerm = '';

// ─── Initialize App ────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  if (window.lucide) lucide.createIcons();
  setupEventListeners();
  setupNavigationTabs();
  setupInspectorTabs();
  loadSystemStatus();
  loadAnalytics();
  loadDocumentsQueue();
});

// ─── System Status Badge ───────────────────────────────────────────────────────
async function loadSystemStatus() {
  try {
    const res = await fetch('/api/v1/status');
    if (!res.ok) return;
    const s = await res.json();
    const el = document.getElementById('provider-status-text');
    if (!el) return;

    const providerLabels = {
      'groq_llama3': '⚡ Groq LLaMA3',
      'openai_gpt4o': '🧠 OpenAI GPT-4o',
      'gemini_flash': '✨ Gemini Flash',
      'demo/fallback': '🎭 Demo Engine',
    };
    const ocrLabel = s.ocr_backend === 'easyocr' ? '🔍 EasyOCR' : s.ocr_backend === 'tesseract' ? '🔬 Tesseract' : '🖼 PIL Fallback';
    el.textContent = `${providerLabels[s.ai_provider] || s.ai_provider} · ${ocrLabel}`;

    // Update integrations icons in modal if they exist
    updateIntegrationStatus(s.integrations);
  } catch (e) {
    console.warn('Could not load system status:', e);
  }
}

function updateIntegrationStatus(integrations) {
  const sheetsBtn = document.getElementById('btn-export-sheets');
  const airtableBtn = document.getElementById('btn-export-airtable');
  if (sheetsBtn) {
    sheetsBtn.title = integrations?.google_sheets ? 'Export to Google Sheets' : 'Google Sheets not configured — set GOOGLE_SHEET_ID in .env';
  }
  if (airtableBtn) {
    airtableBtn.title = integrations?.airtable ? 'Export to Airtable' : 'Airtable not configured — set AIRTABLE_API_KEY in .env';
  }
}

// ─── Navigation Tabs ──────────────────────────────────────────────────────────
function setupNavigationTabs() {
  const dashBtn = document.getElementById('tab-btn-dashboard');
  const analyticsBtn = document.getElementById('tab-btn-analytics');
  const dashView = document.getElementById('view-dashboard');
  const analyticsView = document.getElementById('view-analytics');

  dashBtn.addEventListener('click', () => {
    dashBtn.classList.add('active');
    analyticsBtn.classList.remove('active');
    dashView.classList.add('active');
    analyticsView.classList.remove('active');
  });

  analyticsBtn.addEventListener('click', () => {
    analyticsBtn.classList.add('active');
    dashBtn.classList.remove('active');
    analyticsView.classList.add('active');
    dashView.classList.remove('active');
    loadAnalytics();
    loadConfidenceChart();
  });
}

// ─── Inspector Tabs ────────────────────────────────────────────────────────────
function setupInspectorTabs() {
  const tabButtons = document.querySelectorAll('.i-tab-btn');
  tabButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.i-tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.inspector-tab-content').forEach(c => c.classList.remove('active'));
      btn.classList.add('active');
      const targetId = btn.getAttribute('data-target');
      document.getElementById(targetId).classList.add('active');

      // Load audit log when audit tab selected
      if (targetId === 'i-tab-audit' && currentDocument) {
        loadAuditLog(currentDocument.id);
      }
    });
  });
}

function triggerScanLaserEffect() {
  const laser = document.getElementById('scanner-laser-line');
  if (!laser) return;
  laser.classList.add('scanning');
  setTimeout(() => laser.classList.remove('scanning'), 2000);
}

// ─── Event Listeners ──────────────────────────────────────────────────────────
function setupEventListeners() {
  const dropzone = document.getElementById('file-dropzone');
  const fileInput = document.getElementById('file-input');

  dropzone.addEventListener('click', () => fileInput.click());
  dropzone.addEventListener('dragover', (e) => { e.preventDefault(); dropzone.classList.add('dragover'); });
  dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
  dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.classList.remove('dragover');
    if (e.dataTransfer.files?.length > 0) handleFileUpload(e.dataTransfer.files);
  });
  fileInput.addEventListener('change', (e) => {
    if (e.target.files?.length > 0) handleFileUpload(e.target.files);
  });

  document.getElementById('btn-refresh-list').addEventListener('click', () => {
    loadDocumentsQueue();
    loadAnalytics();
  });
  document.getElementById('btn-open-upload').addEventListener('click', () => fileInput.click());
  document.getElementById('btn-quick-sample').addEventListener('click', handleQuickSampleUpload);
  document.getElementById('btn-save-verify').addEventListener('click', handleSaveVerification);
  document.getElementById('btn-add-line-item').addEventListener('click', addLineItemRow);

  // ── Search box ──
  const searchInput = document.querySelector('.search-input');
  if (searchInput) {
    searchInput.addEventListener('input', (e) => {
      clearTimeout(searchDebounceTimer);
      currentSearchTerm = e.target.value.trim();
      searchDebounceTimer = setTimeout(() => {
        loadDocumentsQueue(currentSearchTerm);
      }, 300);
    });
  }

  // ── Exports ──
  document.getElementById('btn-export-csv').addEventListener('click', () => {
    if (currentDocument) window.open(`${API_BASE}/documents/${currentDocument.id}/export/csv`, '_blank');
  });
  document.getElementById('btn-export-json').addEventListener('click', () => {
    if (currentDocument) window.open(`${API_BASE}/documents/${currentDocument.id}/export/json`, '_blank');
  });

  // ── Google Sheets Export ──
  const sheetsBtn = document.getElementById('btn-export-sheets');
  if (sheetsBtn) {
    sheetsBtn.addEventListener('click', async () => {
      if (!currentDocument) return;
      sheetsBtn.disabled = true;
      sheetsBtn.innerHTML = '<i data-lucide="loader-2" class="spin"></i> Exporting...';
      if (window.lucide) lucide.createIcons();
      try {
        const res = await fetch(`${API_BASE}/documents/${currentDocument.id}/export/sheets`, { method: 'POST' });
        const data = await res.json();
        if (res.ok) {
          showToast(`✅ Exported to Google Sheets!`, 'success');
          if (data.sheet_url) window.open(data.sheet_url, '_blank');
        } else {
          showToast(`❌ Sheets error: ${data.detail || 'Unknown error'}`, 'error');
        }
      } catch (e) {
        showToast(`❌ Sheets export failed: ${e}`, 'error');
      } finally {
        sheetsBtn.disabled = false;
        sheetsBtn.innerHTML = '<i data-lucide="table-2"></i> Sheets';
        if (window.lucide) lucide.createIcons();
      }
    });
  }

  // ── Airtable Export ──
  const airtableBtn = document.getElementById('btn-export-airtable');
  if (airtableBtn) {
    airtableBtn.addEventListener('click', async () => {
      if (!currentDocument) return;
      airtableBtn.disabled = true;
      airtableBtn.innerHTML = '<i data-lucide="loader-2" class="spin"></i> Syncing...';
      if (window.lucide) lucide.createIcons();
      try {
        const res = await fetch(`${API_BASE}/documents/${currentDocument.id}/export/airtable`, { method: 'POST' });
        const data = await res.json();
        if (res.ok) {
          showToast(`✅ Synced to Airtable! Record: ${data.record_id || ''}`, 'success');
          if (data.airtable_url) window.open(data.airtable_url, '_blank');
        } else {
          showToast(`❌ Airtable error: ${data.detail || 'Unknown error'}`, 'error');
        }
      } catch (e) {
        showToast(`❌ Airtable sync failed: ${e}`, 'error');
      } finally {
        airtableBtn.disabled = false;
        airtableBtn.innerHTML = '<i data-lucide="grid-3x3"></i> Airtable';
        if (window.lucide) lucide.createIcons();
      }
    });
  }

  // ── Webhook Modal ──
  const modal = document.getElementById('export-modal');
  document.getElementById('btn-trigger-webhook').addEventListener('click', () => {
    if (!currentDocument) return;
    fetch(`${API_BASE}/documents/${currentDocument.id}/export/json`)
      .then(r => r.json())
      .then(data => {
        document.getElementById('modal-json-preview').textContent = JSON.stringify(data, null, 2);
        modal.classList.add('active');
      });
  });
  document.getElementById('btn-close-modal').addEventListener('click', () => modal.classList.remove('active'));
  document.getElementById('btn-modal-close').addEventListener('click', () => modal.classList.remove('active'));
  document.getElementById('btn-modal-dispatch').addEventListener('click', async () => {
    if (!currentDocument) return;
    const url = document.getElementById('modal-webhook-url').value;
    try {
      const resp = await fetch(`${API_BASE}/documents/${currentDocument.id}/export/webhook`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ webhook_url: url, document_id: currentDocument.id })
      });
      const resData = await resp.json();
      showToast(`Webhook dispatched! Status: ${resData.status_code || 'sent'}`, resData.success ? 'success' : 'error');
      modal.classList.remove('active');
    } catch (err) {
      showToast(`Webhook failed: ${err}`, 'error');
    }
  });

  // ── Analytics date range filters ──
  const applyFiltersBtn = document.getElementById('btn-apply-filters');
  if (applyFiltersBtn) {
    applyFiltersBtn.addEventListener('click', () => {
      loadAnalytics();
      loadConfidenceChart();
    });
  }
}

// ─── Analytics ─────────────────────────────────────────────────────────────────
async function loadAnalytics() {
  try {
    const startDate = document.getElementById('filter-start-date')?.value || '';
    const endDate = document.getElementById('filter-end-date')?.value || '';
    const currency = document.getElementById('filter-currency')?.value || '';

    let url = `${API_BASE}/analytics/summary`;
    const params = new URLSearchParams();
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);
    if (currency) params.append('currency', currency);
    if (params.toString()) url += `?${params.toString()}`;

    const res = await fetch(url);
    if (!res.ok) return;
    const data = await res.json();

    const currSymbol = getCurrencySymbol(data.currency);
    document.getElementById('stat-docs').textContent = data.total_documents;
    document.getElementById('stat-spend').textContent = `${currSymbol}${data.total_spend.toLocaleString('en-US', { minimumFractionDigits: 2 })}`;
    document.getElementById('stat-confidence').textContent = `${data.avg_confidence}%`;

    renderVendorChart(data.vendor_breakdown, currSymbol);
    renderCategoryChart(data.category_breakdown);
    renderMonthlyChart(data.monthly_trend, currSymbol);
  } catch (e) {
    console.error('Error loading analytics:', e);
  }
}

async function loadConfidenceChart() {
  try {
    const res = await fetch(`${API_BASE}/analytics/confidence-history?limit=30`);
    if (!res.ok) return;
    const data = await res.json();
    renderConfidenceChart(data);
  } catch (e) {
    console.error('Error loading confidence history:', e);
  }
}

function getCurrencySymbol(code) {
  const symbols = { USD: '$', EUR: '€', GBP: '£', TND: 'DT ', CAD: 'CA$', AUD: 'A$', JPY: '¥', CHF: 'CHF ' };
  return symbols[code] || (code + ' ');
}

// ─── Documents Queue ──────────────────────────────────────────────────────────
async function loadDocumentsQueue(search = '') {
  try {
    let url = `${API_BASE}/documents`;
    if (search) url += `?search=${encodeURIComponent(search)}`;
    const res = await fetch(url);
    if (!res.ok) return;
    documentsList = await res.json();

    const queueContainer = document.getElementById('documents-tbody');
    queueContainer.innerHTML = '';

    if (documentsList.length === 0) {
      queueContainer.innerHTML = `
        <div class="pipeline-empty">
          <i data-lucide="inbox"></i>
          <p>${search ? `No results for "<strong>${escapeHtml(search)}</strong>"` : 'Pipeline is currently empty. Drop a scan or load demo data.'}</p>
        </div>
      `;
      if (window.lucide) lucide.createIcons();
      return;
    }

    documentsList.forEach((doc, idx) => {
      const ext = doc.extraction || {};
      const card = document.createElement('div');
      card.className = 'pipeline-row-card';
      if (currentDocument && currentDocument.id === doc.id) card.classList.add('selected');

      let badgeClass = 'badge-high';
      if (ext.confidence_status === 'NEEDS_REVIEW') badgeClass = 'badge-review';
      if (ext.confidence_status === 'FLAG') badgeClass = 'badge-flag';

      const dupTag = ext.is_duplicate ? '<span class="badge badge-dup">DUP</span>' : '';
      const docTypeIcon = doc.mime_type?.includes('pdf') ? 'file-text' : 'image';
      const isError = doc.status === 'error';
      const statusClass = isError ? 'badge badge-flag' : '';

      card.innerHTML = `
        <div class="doc-info">
          <div class="doc-icon-frame ${isError ? 'error' : ''}">
            <i data-lucide="${isError ? 'alert-triangle' : docTypeIcon}" style="width: 18px; height: 18px;"></i>
          </div>
          <div class="doc-meta">
            <span class="doc-name">${escapeHtml(doc.filename)}</span>
            <span class="doc-sub">${escapeHtml(ext.vendor_name || (isError ? '⚠ Extraction failed' : 'Processing...'))}</span>
          </div>
        </div>
        <div class="doc-financials">
          <span class="doc-amount">${ext.currency || ''} ${(ext.total_amount || 0).toFixed(2)}</span>
          ${isError
            ? `<button class="btn btn-secondary btn-sm btn-retry" data-id="${doc.id}"><i data-lucide="refresh-cw" style="width:12px"></i> Retry</button>`
            : `<span class="badge ${badgeClass}">${ext.confidence_score || 0}%</span>`
          }
          ${dupTag}
        </div>
      `;

      // Retry button handler
      const retryBtn = card.querySelector('.btn-retry');
      if (retryBtn) {
        retryBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          handleRetryExtraction(doc.id, retryBtn);
        });
      }

      card.addEventListener('click', () => inspectDocument(doc.id));
      queueContainer.appendChild(card);

      if (idx === 0 && !currentDocument) inspectDocument(doc.id);
    });

    if (window.lucide) lucide.createIcons();
  } catch (e) {
    console.error('Error loading document queue:', e);
  }
}

// ─── Retry Extraction ─────────────────────────────────────────────────────────
async function handleRetryExtraction(docId, btn) {
  btn.disabled = true;
  btn.innerHTML = '<i data-lucide="loader-2" style="width:12px" class="spin"></i>';
  if (window.lucide) lucide.createIcons();
  try {
    const res = await fetch(`${API_BASE}/documents/${docId}/retry`, { method: 'POST' });
    if (res.ok) {
      showToast('✅ Retry successful!', 'success');
      loadDocumentsQueue(currentSearchTerm);
      loadAnalytics();
      inspectDocument(docId);
    } else {
      const err = await res.json().catch(() => ({}));
      showToast(`❌ Retry failed: ${err.detail || 'Unknown error'}`, 'error');
    }
  } catch (e) {
    showToast(`❌ Retry error: ${e}`, 'error');
  } finally {
    if (btn) { btn.disabled = false; }
  }
}

// ─── Inspect Document ─────────────────────────────────────────────────────────
async function inspectDocument(docId) {
  try {
    const res = await fetch(`${API_BASE}/documents/${docId}`);
    if (!res.ok) return;
    currentDocument = await res.json();

    triggerScanLaserEffect();

    document.querySelectorAll('.pipeline-row-card').forEach((card, idx) => {
      if (documentsList[idx]?.id === docId) card.classList.add('selected');
      else card.classList.remove('selected');
    });

    document.getElementById('btn-export-csv').disabled = false;
    document.getElementById('btn-export-json').disabled = false;
    document.getElementById('btn-trigger-webhook').disabled = false;
    document.getElementById('btn-save-verify').disabled = false;
    const sheetsBtn = document.getElementById('btn-export-sheets');
    const airtableBtn = document.getElementById('btn-export-airtable');
    if (sheetsBtn) sheetsBtn.disabled = false;
    if (airtableBtn) airtableBtn.disabled = false;

    // Image preview
    const imgEl = document.getElementById('document-preview-img');
    const placeholderText = document.getElementById('image-placeholder-text');
    const filenameOnDisk = currentDocument.file_path.split(/[\/\\]/).pop();
    imgEl.src = `/uploads/${filenameOnDisk}`;
    imgEl.onerror = () => { imgEl.style.display = 'none'; placeholderText.style.display = 'flex'; };
    imgEl.onload = () => { imgEl.style.display = 'block'; placeholderText.style.display = 'none'; };

    document.getElementById('inspector-doc-name').textContent = currentDocument.filename;

    const ext = currentDocument.extraction || {};
    document.getElementById('input-vendor').value = ext.vendor_name || '';
    document.getElementById('input-vendor-addr').value = ext.vendor_address || '';
    document.getElementById('input-inv-num').value = ext.invoice_number || '';
    document.getElementById('input-date').value = ext.invoice_date || '';
    document.getElementById('input-due-date').value = ext.due_date || '';
    document.getElementById('input-currency').value = ext.currency || 'USD';
    document.getElementById('input-subtotal').value = ext.subtotal || 0;
    document.getElementById('input-tax').value = ext.tax_amount || 0;
    document.getElementById('input-total').value = ext.total_amount || 0;

    // Confidence badge
    const confBadge = document.getElementById('confidence-badge');
    if (confBadge) {
      confBadge.style.display = '';
      const statusClass = { HIGH: 'badge-high', NEEDS_REVIEW: 'badge-review', FLAG: 'badge-flag' }[ext.confidence_status] || 'badge-review';
      confBadge.className = `badge ${statusClass}`;
      confBadge.textContent = `${ext.confidence_score || 0}% · ${ext.confidence_status || 'PENDING'}`;
    }

    // Provider badge
    const providerBadge = document.getElementById('provider-badge');
    if (providerBadge) {
      providerBadge.style.display = '';
      providerBadge.textContent = ext.extraction_provider || 'unknown';
    }

    // Math status
    const mathBanner = document.getElementById('math-status-banner');
    if (ext.math_valid) {
      mathBanner.className = 'math-status-badge valid';
      mathBanner.innerHTML = '<i data-lucide="shield-check"></i> Math Consistent';
    } else {
      mathBanner.className = 'math-status-badge invalid';
      mathBanner.innerHTML = '<i data-lucide="shield-alert"></i> Discrepancy Found';
    }

    renderLineItemsTable(currentDocument.line_items || []);
    if (window.lucide) lucide.createIcons();

  } catch (e) {
    console.error('Error inspecting document:', e);
  }
}

// ─── Audit Log ────────────────────────────────────────────────────────────────
async function loadAuditLog(docId) {
  const container = document.getElementById('audit-log-container');
  if (!container) return;
  container.innerHTML = '<p style="color:var(--text-muted);font-size:0.8rem;padding:1rem;">Loading audit history...</p>';

  try {
    const res = await fetch(`${API_BASE}/documents/${docId}/audit`);
    if (!res.ok) { container.innerHTML = '<p style="color:var(--text-muted)">No audit data available.</p>'; return; }
    const logs = await res.json();

    if (logs.length === 0) {
      container.innerHTML = '<p style="color:var(--text-muted);font-size:0.8rem;padding:1rem;text-align:center;">No audit events recorded yet.</p>';
      return;
    }

    container.innerHTML = logs.map(log => `
      <div class="audit-entry">
        <div class="audit-action">${escapeHtml(log.action)}</div>
        <div class="audit-details">${escapeHtml(log.details || '')}</div>
        <div class="audit-timestamp">${log.timestamp ? log.timestamp.replace('T', ' ').substring(0, 19) : ''}</div>
      </div>
    `).join('');
  } catch (e) {
    container.innerHTML = '<p style="color:var(--color-danger);font-size:0.8rem;padding:1rem;">Failed to load audit log.</p>';
  }
}

// ─── Line Items Table ─────────────────────────────────────────────────────────
function renderLineItemsTable(items) {
  const tbody = document.getElementById('line-items-tbody');
  tbody.innerHTML = '';

  if (!items || items.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;color:var(--text-muted);font-size:0.8rem;padding:2rem;">No line items extracted. Click "Add Item" to add one manually.</td></tr>`;
    return;
  }

  items.forEach(item => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><input type="text" class="item-desc" value="${escapeHtml(item.description || '')}" style="width:100%;"></td>
      <td><input type="number" step="0.1" class="item-qty" value="${item.quantity || 1}" style="width:100%;"></td>
      <td><input type="number" step="0.01" class="item-price" value="${item.unit_price || 0}" style="width:100%;"></td>
      <td><input type="number" step="0.01" class="item-total" value="${item.total_price || 0}" style="width:100%;"></td>
      <td>
        <select class="item-cat" style="width:100%;">
          ${['Software & Subscriptions','Office Supplies & Hardware','Travel & Dining','Utilities & Infrastructure','Professional Services','General Expense']
            .map(c => `<option value="${c}" ${item.category === c ? 'selected' : ''}>${c}</option>`).join('')}
        </select>
      </td>
      <td>
        <button type="button" class="btn-icon-only btn-del-item" style="color:var(--color-danger);height:28px;width:28px;">
          <i data-lucide="trash-2" style="width:14px;"></i>
        </button>
      </td>
    `;

    const qtyInput = tr.querySelector('.item-qty');
    const priceInput = tr.querySelector('.item-price');
    const totalInput = tr.querySelector('.item-total');
    const updateLineTotal = () => {
      totalInput.value = ((parseFloat(qtyInput.value) || 0) * (parseFloat(priceInput.value) || 0)).toFixed(2);
      recalculateSubtotalAndTotal();
    };
    qtyInput.addEventListener('input', updateLineTotal);
    priceInput.addEventListener('input', updateLineTotal);
    totalInput.addEventListener('input', recalculateSubtotalAndTotal);
    tr.querySelector('.btn-del-item').addEventListener('click', () => { tr.remove(); recalculateSubtotalAndTotal(); });

    tbody.appendChild(tr);
  });
  if (window.lucide) lucide.createIcons();
}

function addLineItemRow() {
  const tbody = document.getElementById('line-items-tbody');
  if (tbody.children.length === 1 && tbody.children[0].cells.length <= 1) tbody.innerHTML = '';
  const tr = document.createElement('tr');
  tr.innerHTML = `
    <td><input type="text" class="item-desc" value="New Line Item" style="width:100%;"></td>
    <td><input type="number" step="0.1" class="item-qty" value="1.0" style="width:100%;"></td>
    <td><input type="number" step="0.01" class="item-price" value="25.00" style="width:100%;"></td>
    <td><input type="number" step="0.01" class="item-total" value="25.00" style="width:100%;"></td>
    <td>
      <select class="item-cat" style="width:100%;">
        ${['General Expense','Software & Subscriptions','Office Supplies & Hardware','Travel & Dining','Utilities & Infrastructure','Professional Services']
          .map(c => `<option value="${c}">${c}</option>`).join('')}
      </select>
    </td>
    <td>
      <button type="button" class="btn-icon-only btn-del-item" style="color:var(--color-danger);height:28px;width:28px;">
        <i data-lucide="trash-2" style="width:14px;"></i>
      </button>
    </td>
  `;
  tr.querySelector('.btn-del-item').addEventListener('click', () => { tr.remove(); recalculateSubtotalAndTotal(); });
  tbody.appendChild(tr);
  if (window.lucide) lucide.createIcons();
  recalculateSubtotalAndTotal();
}

function recalculateSubtotalAndTotal() {
  let sum = 0;
  document.querySelectorAll('#line-items-tbody tr').forEach(r => {
    const totIn = r.querySelector('.item-total');
    if (totIn) sum += parseFloat(totIn.value) || 0;
  });
  const subInput = document.getElementById('input-subtotal');
  const taxInput = document.getElementById('input-tax');
  const totalInput = document.getElementById('input-total');
  subInput.value = sum.toFixed(2);
  const tax = parseFloat(taxInput.value) || 0;
  totalInput.value = (sum + tax).toFixed(2);

  const mathBanner = document.getElementById('math-status-banner');
  const diff = Math.abs((sum + tax) - parseFloat(totalInput.value));
  mathBanner.className = diff <= 0.05 ? 'math-status-badge valid' : 'math-status-badge invalid';
  mathBanner.innerHTML = diff <= 0.05
    ? '<i data-lucide="shield-check"></i> Math Consistent'
    : '<i data-lucide="shield-alert"></i> Discrepancy Found';
  if (window.lucide) lucide.createIcons();
}

// ─── Save & Verify ────────────────────────────────────────────────────────────
async function handleSaveVerification() {
  if (!currentDocument) return;
  const rows = document.querySelectorAll('#line-items-tbody tr');
  const lineItemsPayload = [];
  rows.forEach(r => {
    const desc = r.querySelector('.item-desc')?.value;
    if (desc) lineItemsPayload.push({
      description: desc,
      quantity: parseFloat(r.querySelector('.item-qty').value) || 1.0,
      unit_price: parseFloat(r.querySelector('.item-price').value) || 0.0,
      total_price: parseFloat(r.querySelector('.item-total').value) || 0.0,
      category: r.querySelector('.item-cat').value || 'General Expense'
    });
  });

  const payload = {
    extraction: {
      vendor_name: document.getElementById('input-vendor').value,
      vendor_address: document.getElementById('input-vendor-addr').value,
      invoice_number: document.getElementById('input-inv-num').value,
      invoice_date: document.getElementById('input-date').value,
      due_date: document.getElementById('input-due-date').value,
      currency: document.getElementById('input-currency').value,
      subtotal: parseFloat(document.getElementById('input-subtotal').value) || 0.0,
      tax_amount: parseFloat(document.getElementById('input-tax').value) || 0.0,
      discount_amount: 0.0,
      total_amount: parseFloat(document.getElementById('input-total').value) || 0.0,
      detected_language: 'English',
      line_items: lineItemsPayload
    },
    mark_verified: true
  };

  try {
    const res = await fetch(`${API_BASE}/documents/${currentDocument.id}/verify`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      currentDocument = await res.json();
      showToast('✅ Document verified & saved!', 'success');
      loadDocumentsQueue(currentSearchTerm);
      loadAnalytics();
    } else {
      showToast('❌ Failed to save document verification.', 'error');
    }
  } catch (e) {
    showToast(`❌ Error: ${e}`, 'error');
  }
}

// ─── File Upload with Progress ────────────────────────────────────────────────
async function handleFileUpload(files) {
  const formData = new FormData();
  for (let i = 0; i < files.length; i++) formData.append('files', files[i]);

  // Show upload progress state
  const laser = document.getElementById('scanner-laser-line');
  if (laser) laser.classList.add('scanning');

  showUploadProgress(files.length);

  try {
    const res = await fetch(`${API_BASE}/documents/upload`, { method: 'POST', body: formData });
    if (laser) laser.classList.remove('scanning');
    hideUploadProgress();

    if (res.ok) {
      const uploadedDocs = await res.json();
      showToast(`✅ ${uploadedDocs.length} document${uploadedDocs.length > 1 ? 's' : ''} processed!`, 'success');
      loadDocumentsQueue(currentSearchTerm);
      loadAnalytics();
      if (uploadedDocs.length > 0) inspectDocument(uploadedDocs[0].id);
    } else {
      const errData = await res.json().catch(() => ({}));
      showToast(`❌ Upload failed: ${errData.detail || 'Server error'}`, 'error');
    }
  } catch (e) {
    if (laser) laser.classList.remove('scanning');
    hideUploadProgress();
    showToast(`❌ Upload error: ${e}`, 'error');
  }
}

function showUploadProgress(fileCount) {
  const dropzone = document.getElementById('file-dropzone');
  if (!dropzone) return;
  dropzone.classList.add('uploading');
  const existingBar = dropzone.querySelector('.upload-progress-bar');
  if (!existingBar) {
    const bar = document.createElement('div');
    bar.className = 'upload-progress-bar';
    bar.innerHTML = `<div class="upload-progress-fill"></div><span class="upload-progress-label">Extracting ${fileCount} file${fileCount > 1 ? 's' : ''}...</span>`;
    dropzone.appendChild(bar);
  }
}

function hideUploadProgress() {
  const dropzone = document.getElementById('file-dropzone');
  if (!dropzone) return;
  dropzone.classList.remove('uploading');
  const bar = dropzone.querySelector('.upload-progress-bar');
  if (bar) bar.remove();
}

// ─── Quick Sample ─────────────────────────────────────────────────────────────
async function handleQuickSampleUpload() {
  const canvas = document.createElement('canvas');
  canvas.width = 600; canvas.height = 800;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#fafaf8'; ctx.fillRect(0, 0, 600, 800);
  ctx.fillStyle = '#1e293b'; ctx.font = '24px sans-serif';
  ctx.fillText('AWS CLOUD SERVICES FACTURE', 100, 100);
  ctx.font = '16px sans-serif';
  ctx.fillText('Invoice #: INV-AWS-2026-X88', 100, 140);
  ctx.fillText('Date: 2026-07-26', 100, 170);
  ctx.fillText('EC2 Instances: $220.00', 100, 240);
  ctx.fillText('S3 Storage: $45.00', 100, 280);
  ctx.fillText('TOTAL DUE: $265.00', 100, 360);
  canvas.toBlob(blob => {
    handleFileUpload([new File([blob], 'aws_sample_invoice.png', { type: 'image/png' })]);
  }, 'image/png');
}

// ─── Charts ───────────────────────────────────────────────────────────────────
const CHART_COLORS = ['#6366f1', '#10b981', '#f59e0b', '#06b6d4', '#ec4899', '#8b5cf6', '#f97316', '#14b8a6'];
const CHART_GRID = 'rgba(255,255,255,0.04)';
const TICK_COLOR = '#64748b';

function renderVendorChart(data, currSymbol = '$') {
  const ctx = document.getElementById('chart-vendor').getContext('2d');
  if (vendorChart) vendorChart.destroy();
  vendorChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: data.map(d => d.vendor),
      datasets: [{ label: `Total Spend (${currSymbol})`, data: data.map(d => d.total_spend),
        backgroundColor: 'rgba(99, 102, 241, 0.45)', borderColor: '#6366f1',
        borderWidth: 1.5, borderRadius: 8 }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: TICK_COLOR, font: { size: 10 } }, grid: { color: CHART_GRID } },
        y: { ticks: { color: TICK_COLOR, font: { size: 10 }, callback: v => currSymbol + v.toLocaleString() }, grid: { color: CHART_GRID } }
      }
    }
  });
}

function renderCategoryChart(data) {
  const ctx = document.getElementById('chart-category').getContext('2d');
  if (categoryChart) categoryChart.destroy();
  categoryChart = new Chart(ctx, {
    type: 'doughnut',
    data: { labels: data.map(d => d.category), datasets: [{ data: data.map(d => d.total_spend), backgroundColor: CHART_COLORS, borderWidth: 0 }] },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { position: 'right', labels: { color: '#94a3b8', font: { size: 10 } } } }
    }
  });
}

function renderMonthlyChart(data, currSymbol = '$') {
  const canvas = document.getElementById('chart-monthly');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  if (monthlyChart) monthlyChart.destroy();
  monthlyChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: data.map(d => d.month),
      datasets: [{ label: `Monthly Spend (${currSymbol})`, data: data.map(d => d.spend),
        borderColor: '#10b981', backgroundColor: 'rgba(16,185,129,0.1)',
        borderWidth: 2.5, pointRadius: 4, pointBackgroundColor: '#10b981',
        fill: true, tension: 0.35 }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: TICK_COLOR, font: { size: 10 } }, grid: { color: CHART_GRID } },
        y: { ticks: { color: TICK_COLOR, font: { size: 10 }, callback: v => currSymbol + v.toLocaleString() }, grid: { color: CHART_GRID } }
      }
    }
  });
}

function renderConfidenceChart(data) {
  const canvas = document.getElementById('chart-confidence');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  if (confidenceChart) confidenceChart.destroy();

  const colors = data.map(d => {
    if (d.confidence_status === 'HIGH') return '#10b981';
    if (d.confidence_status === 'FLAG') return '#ef4444';
    return '#f59e0b';
  });

  confidenceChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: data.map(d => d.filename?.substring(0, 15) || d.document_id),
      datasets: [{ label: 'Confidence Score (%)', data: data.map(d => d.confidence_score),
        borderColor: '#6366f1', backgroundColor: 'rgba(99,102,241,0.08)',
        borderWidth: 2, pointRadius: 5, pointBackgroundColor: colors,
        fill: true, tension: 0.3 }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false },
        tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y}% (${data[ctx.dataIndex]?.confidence_status})` } }
      },
      scales: {
        x: { ticks: { color: TICK_COLOR, font: { size: 9 }, maxRotation: 45 }, grid: { color: CHART_GRID } },
        y: { min: 0, max: 100, ticks: { color: TICK_COLOR, font: { size: 10 }, callback: v => v + '%' }, grid: { color: CHART_GRID } }
      }
    }
  });
}

// ─── Toast Notifications ──────────────────────────────────────────────────────
function showToast(message, type = 'info') {
  const existing = document.getElementById('toast-container');
  const container = existing || (() => {
    const el = document.createElement('div');
    el.id = 'toast-container';
    el.style.cssText = 'position:fixed;bottom:1.5rem;right:1.5rem;z-index:9999;display:flex;flex-direction:column;gap:0.5rem;';
    document.body.appendChild(el);
    return el;
  })();

  const toast = document.createElement('div');
  const colors = { success: '#10b981', error: '#ef4444', info: '#6366f1' };
  toast.style.cssText = `background:var(--bg-elevated,#1e293b);border:1px solid ${colors[type] || '#6366f1'};color:#f1f5f9;padding:0.75rem 1.25rem;border-radius:10px;font-size:0.85rem;max-width:320px;box-shadow:0 8px 32px rgba(0,0,0,0.4);animation:slideInToast 0.25s ease;`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => { toast.style.opacity = '0'; toast.style.transition = 'opacity 0.3s'; setTimeout(() => toast.remove(), 300); }, 3500);
}

// ─── HTML Escape ──────────────────────────────────────────────────────────────
function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

