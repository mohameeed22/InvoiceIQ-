const API_BASE = '/api/v1';

let currentDocument = null;
let documentsList = [];
let vendorChart = null;
let categoryChart = null;

// Initialize App on DOM Loaded
document.addEventListener('DOMContentLoaded', () => {
  if (window.lucide) {
    lucide.createIcons();
  }
  setupEventListeners();
  setupNavigationTabs();
  setupInspectorTabs();
  loadAnalytics();
  loadDocumentsQueue();
});

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
    // Force chart sizing re-computation
    loadAnalytics();
  });
}

function setupInspectorTabs() {
  const tabButtons = document.querySelectorAll('.i-tab-btn');
  tabButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      // Remove active from all buttons & contents
      document.querySelectorAll('.i-tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.inspector-tab-content').forEach(c => c.classList.remove('active'));

      // Add active to current
      btn.classList.add('active');
      const targetId = btn.getAttribute('data-target');
      document.getElementById(targetId).classList.add('active');
    });
  });
}

function triggerScanLaserEffect() {
  const laser = document.getElementById('scanner-laser-line');
  laser.classList.add('scanning');
  setTimeout(() => {
    laser.classList.remove('scanning');
  }, 2000);
}

function setupEventListeners() {
  // Drag & drop upload
  const dropzone = document.getElementById('file-dropzone');
  const fileInput = document.getElementById('file-input');

  dropzone.addEventListener('click', () => fileInput.click());
  
  dropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropzone.classList.add('dragover');
  });

  dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
  
  dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.classList.remove('dragover');
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFileUpload(e.dataTransfer.files);
    }
  });

  fileInput.addEventListener('change', (e) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFileUpload(e.target.files);
    }
  });

  // Buttons
  document.getElementById('btn-refresh-list').addEventListener('click', () => {
    loadDocumentsQueue();
    loadAnalytics();
  });

  document.getElementById('btn-open-upload').addEventListener('click', () => fileInput.click());

  document.getElementById('btn-quick-sample').addEventListener('click', handleQuickSampleUpload);

  document.getElementById('btn-save-verify').addEventListener('click', handleSaveVerification);

  document.getElementById('btn-add-line-item').addEventListener('click', addLineItemRow);

  // Exports
  document.getElementById('btn-export-csv').addEventListener('click', () => {
    if (currentDocument) {
      window.open(`${API_BASE}/documents/${currentDocument.id}/export/csv`, '_blank');
    }
  });

  document.getElementById('btn-export-json').addEventListener('click', () => {
    if (currentDocument) {
      window.open(`${API_BASE}/documents/${currentDocument.id}/export/json`, '_blank');
    }
  });

  // Webhook Modal
  const modal = document.getElementById('export-modal');
  document.getElementById('btn-trigger-webhook').addEventListener('click', () => {
    if (!currentDocument) return;
    fetch(`${API_BASE}/documents/${currentDocument.id}/export/json`)
      .then(res => res.json())
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
      alert(`Webhook dispatched! Result: ${JSON.stringify(resData)}`);
      modal.classList.remove('active');
    } catch (err) {
      alert(`Webhook failed: ${err}`);
    }
  });
}

// Analytics summary
async function loadAnalytics() {
  try {
    const res = await fetch(`${API_BASE}/analytics/summary`);
    if (!res.ok) return;
    const data = await res.json();

    document.getElementById('stat-docs').textContent = data.total_documents;
    document.getElementById('stat-spend').textContent = `$${data.total_spend.toLocaleString('en-US', { minimumFractionDigits: 2 })}`;
    document.getElementById('stat-confidence').textContent = `${data.avg_confidence}%`;

    // Render Charts
    renderVendorChart(data.vendor_breakdown);
    renderCategoryChart(data.category_breakdown);
  } catch (e) {
    console.error('Error loading analytics:', e);
  }
}

// Documents queue rendering as custom card layouts
async function loadDocumentsQueue() {
  try {
    const res = await fetch(`${API_BASE}/documents`);
    if (!res.ok) return;
    documentsList = await res.json();

    const queueContainer = document.getElementById('documents-tbody');
    queueContainer.innerHTML = '';

    if (documentsList.length === 0) {
      queueContainer.innerHTML = `
        <div class="pipeline-empty">
          <i data-lucide="inbox"></i>
          <p>Pipeline is currently empty. Drop a scan or load demo data.</p>
        </div>
      `;
      if (window.lucide) lucide.createIcons();
      return;
    }

    documentsList.forEach((doc, idx) => {
      const ext = doc.extraction || {};
      const card = document.createElement('div');
      card.className = 'pipeline-row-card';
      if (currentDocument && currentDocument.id === doc.id) {
        card.classList.add('selected');
      }

      // Confidence badge class
      let badgeClass = 'badge-high';
      if (ext.confidence_status === 'NEEDS_REVIEW') badgeClass = 'badge-review';
      if (ext.confidence_status === 'FLAG') badgeClass = 'badge-flag';

      const dupTag = ext.is_duplicate ? '<span class="badge badge-dup">DUP</span>' : '';
      const docTypeIcon = doc.mime_type.includes('pdf') ? 'file-text' : 'image';

      card.innerHTML = `
        <div class="doc-info">
          <div class="doc-icon-frame">
            <i data-lucide="${docTypeIcon}" style="width: 18px; height: 18px;"></i>
          </div>
          <div class="doc-meta">
            <span class="doc-name">${escapeHtml(doc.filename)}</span>
            <span class="doc-sub">${escapeHtml(ext.vendor_name || 'Processing...')}</span>
          </div>
        </div>
        <div class="doc-financials">
          <span class="doc-amount">${ext.currency || '$'} ${(ext.total_amount || 0).toFixed(2)}</span>
          <span class="badge ${badgeClass}">${ext.confidence_score || 0}%</span>
        </div>
      `;

      card.addEventListener('click', () => inspectDocument(doc.id));
      queueContainer.appendChild(card);

      // Auto-select first document if none selected
      if (idx === 0 && !currentDocument) {
        inspectDocument(doc.id);
      }
    });

    if (window.lucide) lucide.createIcons();

  } catch (e) {
    console.error('Error loading document queue:', e);
  }
}

// Inspect single document
async function inspectDocument(docId) {
  try {
    const res = await fetch(`${API_BASE}/documents/${docId}`);
    if (!res.ok) return;
    currentDocument = await res.json();

    // Trigger Scanning Laser effect
    triggerScanLaserEffect();

    // Refresh UI highlights
    document.querySelectorAll('.pipeline-row-card').forEach((card, idx) => {
      if (documentsList[idx] && documentsList[idx].id === docId) {
        card.classList.add('selected');
      } else {
        card.classList.remove('selected');
      }
    });

    // Enable action buttons
    document.getElementById('btn-export-csv').disabled = false;
    document.getElementById('btn-export-json').disabled = false;
    document.getElementById('btn-trigger-webhook').disabled = false;
    document.getElementById('btn-save-verify').disabled = false;

    // Load Preview Image
    const imgEl = document.getElementById('document-preview-img');
    const placeholderText = document.getElementById('image-placeholder-text');
    
    const filenameOnDisk = currentDocument.file_path.split(/[\/\\]/).pop();
    imgEl.src = `/uploads/${filenameOnDisk}`;
    imgEl.style.display = 'block';
    placeholderText.style.display = 'none';

    // Update title badge
    document.getElementById('inspector-doc-name').textContent = currentDocument.filename;

    // Populate Form Fields
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

    // Update Math Integrity indicator status
    const mathBanner = document.getElementById('math-status-banner');
    if (ext.math_valid) {
      mathBanner.className = 'math-status-badge valid';
      mathBanner.innerHTML = '<i data-lucide="shield-check"></i> Math Consistent';
    } else {
      mathBanner.className = 'math-status-badge invalid';
      mathBanner.innerHTML = '<i data-lucide="shield-alert"></i> Discrepancy Found';
    }

    // Render Line Items
    renderLineItemsTable(currentDocument.line_items || []);

  } catch (e) {
    console.error('Error inspecting document:', e);
  }
}

// Line items table
function renderLineItemsTable(items) {
  const tbody = document.getElementById('line-items-tbody');
  tbody.innerHTML = '';

  if (!items || items.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="6" style="text-align: center; color: var(--text-muted); font-size: 0.8rem; padding: 2rem;">
          No line items extracted. Click "Add Item" to add one manually.
        </td>
      </tr>
    `;
    return;
  }

  items.forEach((item, idx) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><input type="text" class="item-desc" value="${escapeHtml(item.description || '')}" style="width: 100%;"></td>
      <td><input type="number" step="0.1" class="item-qty" value="${item.quantity || 1}" style="width: 100%;"></td>
      <td><input type="number" step="0.01" class="item-price" value="${item.unit_price || 0}" style="width: 100%;"></td>
      <td><input type="number" step="0.01" class="item-total" value="${item.total_price || 0}" style="width: 100%;"></td>
      <td>
        <select class="item-cat" style="width: 100%;">
          <option value="Software & Subscriptions" ${item.category === 'Software & Subscriptions' ? 'selected' : ''}>Software & Subscriptions</option>
          <option value="Office Supplies & Hardware" ${item.category === 'Office Supplies & Hardware' ? 'selected' : ''}>Office Supplies & Hardware</option>
          <option value="Travel & Dining" ${item.category === 'Travel & Dining' ? 'selected' : ''}>Travel & Dining</option>
          <option value="Utilities & Infrastructure" ${item.category === 'Utilities & Infrastructure' ? 'selected' : ''}>Utilities & Infrastructure</option>
          <option value="Professional Services" ${item.category === 'Professional Services' ? 'selected' : ''}>Professional Services</option>
          <option value="General Expense" ${item.category === 'General Expense' ? 'selected' : ''}>General Expense</option>
        </select>
      </td>
      <td>
        <button type="button" class="btn-icon-only btn-del-item" style="color: var(--color-danger); height: 28px; width: 28px;">
          <i data-lucide="trash-2" style="width: 14px;"></i>
        </button>
      </td>
    `;

    // Recalculate line item total on qty/unit price change
    const qtyInput = tr.querySelector('.item-qty');
    const priceInput = tr.querySelector('.item-price');
    const totalInput = tr.querySelector('.item-total');

    const updateLineTotal = () => {
      const q = parseFloat(qtyInput.value) || 0;
      const p = parseFloat(priceInput.value) || 0;
      totalInput.value = (q * p).toFixed(2);
      recalculateSubtotalAndTotal();
    };

    qtyInput.addEventListener('input', updateLineTotal);
    priceInput.addEventListener('input', updateLineTotal);
    totalInput.addEventListener('input', recalculateSubtotalAndTotal);

    tr.querySelector('.btn-del-item').addEventListener('click', () => {
      tr.remove();
      recalculateSubtotalAndTotal();
    });

    tbody.appendChild(tr);
  });

  if (window.lucide) lucide.createIcons();
}

function addLineItemRow() {
  const tbody = document.getElementById('line-items-tbody');
  // Clear placeholder row if empty
  if (tbody.children.length === 1 && tbody.children[0].cells.length <= 1) {
    tbody.innerHTML = '';
  }

  const tr = document.createElement('tr');
  tr.innerHTML = `
    <td><input type="text" class="item-desc" value="New Line Item" style="width: 100%;"></td>
    <td><input type="number" step="0.1" class="item-qty" value="1.0" style="width: 100%;"></td>
    <td><input type="number" step="0.01" class="item-price" value="25.00" style="width: 100%;"></td>
    <td><input type="number" step="0.01" class="item-total" value="25.00" style="width: 100%;"></td>
    <td>
      <select class="item-cat" style="width: 100%;">
        <option value="General Expense">General Expense</option>
        <option value="Software & Subscriptions">Software & Subscriptions</option>
        <option value="Office Supplies & Hardware">Office Supplies & Hardware</option>
        <option value="Travel & Dining">Travel & Dining</option>
        <option value="Utilities & Infrastructure">Utilities & Infrastructure</option>
      </select>
    </td>
    <td>
      <button type="button" class="btn-icon-only btn-del-item" style="color: var(--color-danger); height: 28px; width: 28px;">
        <i data-lucide="trash-2" style="width: 14px;"></i>
      </button>
    </td>
  `;

  tr.querySelector('.btn-del-item').addEventListener('click', () => {
    tr.remove();
    recalculateSubtotalAndTotal();
  });

  tbody.appendChild(tr);
  if (window.lucide) lucide.createIcons();
  recalculateSubtotalAndTotal();
}

function recalculateSubtotalAndTotal() {
  const rows = document.querySelectorAll('#line-items-tbody tr');
  let sum = 0;
  rows.forEach(r => {
    const totIn = r.querySelector('.item-total');
    if (totIn) {
      sum += parseFloat(totIn.value) || 0;
    }
  });

  const subInput = document.getElementById('input-subtotal');
  const taxInput = document.getElementById('input-tax');
  const totalInput = document.getElementById('input-total');

  subInput.value = sum.toFixed(2);
  const tax = parseFloat(taxInput.value) || 0;
  totalInput.value = (sum + tax).toFixed(2);
  
  // Verify math consistency visually
  const mathBanner = document.getElementById('math-status-banner');
  const diff = Math.abs((sum + tax) - parseFloat(totalInput.value));
  if (diff <= 0.05) {
    mathBanner.className = 'math-status-badge valid';
    mathBanner.innerHTML = '<i data-lucide="shield-check"></i> Math Consistent';
  } else {
    mathBanner.className = 'math-status-badge invalid';
    mathBanner.innerHTML = '<i data-lucide="shield-alert"></i> Discrepancy Found';
  }
  if (window.lucide) lucide.createIcons();
}

// Save & verify document
async function handleSaveVerification() {
  if (!currentDocument) return;

  const rows = document.querySelectorAll('#line-items-tbody tr');
  const lineItemsPayload = [];

  rows.forEach(r => {
    const desc = r.querySelector('.item-desc')?.value;
    if (desc) {
      lineItemsPayload.push({
        description: desc,
        quantity: parseFloat(r.querySelector('.item-qty').value) || 1.0,
        unit_price: parseFloat(r.querySelector('.item-price').value) || 0.0,
        total_price: parseFloat(r.querySelector('.item-total').value) || 0.0,
        category: r.querySelector('.item-cat').value || 'General Expense'
      });
    }
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
      detected_language: "English",
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
      const updated = await res.json();
      currentDocument = updated;
      alert('Document verified & saved successfully!');
      loadDocumentsQueue();
      loadAnalytics();
    } else {
      alert('Failed to save document verification.');
    }
  } catch (e) {
    alert(`Error: ${e}`);
  }
}

// Upload Handler
async function handleFileUpload(files) {
  const formData = new FormData();
  for (let i = 0; i < files.length; i++) {
    formData.append('files', files[i]);
  }

  // Set scanning state
  const laser = document.getElementById('scanner-laser-line');
  laser.classList.add('scanning');

  try {
    const res = await fetch(`${API_BASE}/documents/upload`, {
      method: 'POST',
      body: formData
    });

    laser.classList.remove('scanning');

    if (res.ok) {
      const uploadedDocs = await res.json();
      loadDocumentsQueue();
      loadAnalytics();
      if (uploadedDocs.length > 0) {
        inspectDocument(uploadedDocs[0].id);
      }
    } else {
      const errData = await res.json().catch(() => ({}));
      alert(`Upload failed: ${errData.detail || 'Server error'}`);
    }
  } catch (e) {
    laser.classList.remove('scanning');
    alert(`Upload error: ${e}`);
  }
}

// Quick Sample Generator
async function handleQuickSampleUpload() {
  // Create a synthetic image canvas blob
  const canvas = document.createElement('canvas');
  canvas.width = 600;
  canvas.height = 800;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#fafaf8';
  ctx.fillRect(0, 0, 600, 800);
  ctx.fillStyle = '#1e293b';
  ctx.font = '24px sans-serif';
  ctx.fillText('AWS CLOUD SERVICES FACTURE', 100, 100);
  ctx.font = '16px sans-serif';
  ctx.fillText('Invoice #: INV-AWS-2026-X88', 100, 140);
  ctx.fillText('Date: 2026-07-26', 100, 170);
  ctx.fillText('EC2 Instances: $220.00', 100, 240);
  ctx.fillText('S3 Storage: $45.00', 100, 280);
  ctx.fillText('TOTAL DUE: $265.00', 100, 360);

  canvas.toBlob(async (blob) => {
    const file = new File([blob], "aws_sample_invoice.png", { type: "image/png" });
    handleFileUpload([file]);
  }, 'image/png');
}

// Chart.js Graphs
function renderVendorChart(data) {
  const ctx = document.getElementById('chart-vendor').getContext('2d');
  const labels = data.map(d => d.vendor);
  const values = data.map(d => d.total_spend);

  if (vendorChart) vendorChart.destroy();

  vendorChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [{
        label: 'Total Spend ($)',
        data: values,
        backgroundColor: 'rgba(99, 102, 241, 0.45)',
        borderColor: '#6366f1',
        borderWidth: 1.5,
        borderRadius: 8
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false }
      },
      scales: {
        x: { ticks: { color: '#64748b', font: { size: 10 } }, grid: { color: 'rgba(255,255,255,0.03)' } },
        y: { ticks: { color: '#64748b', font: { size: 10 } }, grid: { color: 'rgba(255,255,255,0.03)' } }
      }
    }
  });
}

function renderCategoryChart(data) {
  const ctx = document.getElementById('chart-category').getContext('2d');
  const labels = data.map(d => d.category);
  const values = data.map(d => d.total_spend);

  if (categoryChart) categoryChart.destroy();

  categoryChart = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: labels,
      datasets: [{
        data: values,
        backgroundColor: [
          '#6366f1', '#10b981', '#f59e0b', '#06b6d4', '#ec4899', '#8b5cf6'
        ],
        borderWidth: 0
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: 'right', labels: { color: '#94a3b8', font: { size: 10 } } }
      }
    }
  });
}

function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
