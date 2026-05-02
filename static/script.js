/* ─── Global State ─── */
let globalResults = [];
let activeSidebarBrand = null; // tracks which brand is selected in sidebar

/* ─── Brand Presets (localStorage) ─── */
const PRESETS_KEY = 'multifind_brand_presets';

function getPresets() {
    try { return JSON.parse(localStorage.getItem(PRESETS_KEY) || '[]'); }
    catch (e) { return []; }
}

function savePresets(presets) {
    localStorage.setItem(PRESETS_KEY, JSON.stringify(presets));
}

/* ─── Sidebar Brand List ─── */

function renderSidebarBrands() {
    const list = document.getElementById('sidebarBrandList');
    if (!list) return;

    const presets = getPresets();
    list.innerHTML = '';

    if (!presets.length) {
        list.innerHTML = `<p class="sidebar-no-brands">Click 'Save as Config' on the right to save your setup here.</p>`;
        return;
    }

    presets.forEach((preset, idx) => {
        const item = document.createElement('div');
        item.className = 'sidebar-brand-item' + (activeSidebarBrand === idx ? ' active-brand' : '');
        item.title = `Setup: ${preset.brandName} (${preset.rules.length} rules)`;

        const displayName = preset.brandName;
        const preview = `${preset.rules.length} rule${preset.rules.length > 1 ? 's' : ''}`;

        item.innerHTML = `
            <div style="flex:1;min-width:0;">
                <div class="brand-name">${escHtml(displayName)}</div>
                <div class="brand-kw-preview" style="color:var(--accent-color);">${preview}</div>
            </div>
            <button class="sidebar-brand-del" onclick="deleteSidebarBrand(event, ${idx})" title="Remove brand">
                <i class="fa-solid fa-xmark"></i>
            </button>
        `;

        item.addEventListener('click', () => loadBrandIntoMultifind(idx));
        list.appendChild(item);
    });
}

/* Load a saved brand's multi-rule setup into MultiFIND */
function loadBrandIntoMultifind(idx) {
    const presets = getPresets();
    const preset = presets[idx];
    if (!preset) return;

    // Highlight active
    activeSidebarBrand = idx;
    renderSidebarBrands();

    // If NOT on the MultiFIND page, navigate there with brand index in URL
    const isMultifind = !!document.getElementById('keywordRulesContainer');
    if (!isMultifind) {
        window.location.href = `/?brand=${idx}`;
        return;
    }

    const container = document.getElementById('keywordRulesContainer');

    // Clear existing rules entirely
    container.innerHTML = '';

    // Add a rule box for each rule in the preset
    if (preset.rules && preset.rules.length > 0) {
        preset.rules.forEach(rule => {
            addRuleBox(rule);
        });
    } else {
        addRuleBox(); // fallback if corrupted
    }

    // Brief highlight flash on the whole container
    container.style.transition = 'box-shadow 0.3s, background 0.3s';
    container.style.boxShadow = '0 0 15px rgba(0,210,255,0.4)';
    container.style.background = 'rgba(0,210,255,0.02)';
    setTimeout(() => {
        container.style.boxShadow = '';
        container.style.background = '';
    }, 800);
}

/* Delete a brand from the sidebar */
function deleteSidebarBrand(event, idx) {
    event.stopPropagation(); // don't trigger the item click
    const presets = getPresets();
    const preset = presets[idx];
    if (!preset) return;
    if (!confirm(`Remove "${preset.brandName}"?`)) return;
    presets.splice(idx, 1);
    savePresets(presets);
    if (activeSidebarBrand === idx) activeSidebarBrand = null;
    renderSidebarBrands();
}

/* Save the entire page's current setup as a single Brand Config */
function saveCurrentSetup() {
    const boxes = document.querySelectorAll('.rule-box');
    const rulesToSave = [];

    // Collect data from every empty/filled rule box
    boxes.forEach(box => {
        const brandInput = box.querySelector('.brandKeyword');
        const mustInput = box.querySelector('.mustHave');
        const shldInput = box.querySelector('.shouldntHave');

        const brandKeyword = brandInput ? brandInput.value.trim() : '';
        const mustHave = mustInput ? mustInput.value.trim() : '';
        const shouldntHave = shldInput ? shldInput.value.trim() : '';

        // Only save rows that have at least a Brand Keyword
        if (brandKeyword) {
            rulesToSave.push({ brandKeyword, mustHave, shouldntHave });
        }
    });

    if (rulesToSave.length === 0) {
        alert('There are no filled rules to save! Please enter at least one Brand Keyword.');
        return;
    }

    const brandName = prompt(`You are saving ${rulesToSave.length} rule(s).\nEnter a name for this Brand Setup (e.g. "Zoya"):`);
    if (!brandName || !brandName.trim()) return;

    const finalName = brandName.trim();
    const presets = getPresets();

    // Check for duplicate brand name
    const exists = presets.some(p => p.brandName.toLowerCase() === finalName.toLowerCase());
    if (exists) {
        if (!confirm(`A setup named "${finalName}" already exists. Overwrite it?`)) return;
        const idx = presets.findIndex(p => p.brandName.toLowerCase() === finalName.toLowerCase());
        presets.splice(idx, 1);
    }

    presets.push({ brandName: finalName, rules: rulesToSave, savedAt: Date.now() });
    savePresets(presets);
    renderSidebarBrands();

    alert(`Successfully saved "${finalName}" with ${rulesToSave.length} rule(s)!`);
}

/* ─── UI Management ─── */

/* ── CSV parser helper — handles quoted fields, BOM, and auto-detects delimiter ── */
function parseCsvFirstColumn(text) {
    // Strip BOM if present
    if (text.charCodeAt(0) === 0xFEFF) text = text.slice(1);

    const lines = text.split(/\r?\n/);
    if (!lines.length) return [];

    // Auto-detect delimiter from first non-empty line
    const firstLine = lines.find(l => l.trim()) || '';
    let delim = ',';
    if ((firstLine.match(/;/g) || []).length > (firstLine.match(/,/g) || []).length) delim = ';';
    else if ((firstLine.match(/\t/g) || []).length > (firstLine.match(/,/g) || []).length) delim = '\t';

    const results = [];
    lines.forEach((line, idx) => {
        if (!line.trim()) return;

        // Proper CSV field parser for quoted fields
        const fields = [];
        let cur = '', inQuote = false;
        for (let i = 0; i < line.length; i++) {
            const ch = line[i];
            if (inQuote) {
                if (ch === '"' && line[i + 1] === '"') { cur += '"'; i++; }
                else if (ch === '"') { inQuote = false; }
                else { cur += ch; }
            } else {
                if (ch === '"') { inQuote = true; }
                else if (ch === delim) { fields.push(cur); cur = ''; }
                else { cur += ch; }
            }
        }
        fields.push(cur);

        const kw = (fields[0] || '').trim();
        if (!kw) return;
        // Skip header row
        if (idx === 0 && /keyword|topic|name|search|term|query/i.test(kw)) return;
        results.push(kw);
    });
    return results;
}

/* ── Import keywords from CSV into Multifind rule boxes ── */
function importKeywordsCsv(input) {
    if (!input.files || !input.files[0]) return;
    const file = input.files[0];
    const reader = new FileReader();
    reader.onload = function(e) {
        const keywords = parseCsvFirstColumn(e.target.result);
        const container = document.getElementById('keywordRulesContainer');

        const BATCH = 50;  // max rules from CSV to avoid DOM overload
        let added = 0;

        keywords.forEach(kw => {
            if (added >= BATCH) return;
            addRuleBox({ brandKeyword: kw });
            added++;
        });

        const total = keywords.length;
        const statusEl = document.getElementById('mfCsvImportStatus');
        const msgEl    = document.getElementById('mfCsvImportMsg');
        if (statusEl && msgEl) {
            const skipped = total > BATCH ? ` (${total - BATCH} skipped — max ${BATCH} at a time to keep things fast)` : '';
            msgEl.textContent = `Imported ${added} keyword rule${added !== 1 ? 's' : ''} from "${file.name}"${skipped}. Review rules below, then click Analyze.`;
            statusEl.style.display = 'block';
        }
    };
    reader.readAsText(file);
    // Reset input so the same file can be re-imported
    input.value = '';
}

function addRuleBox(prefill = {}) {
    const container = document.getElementById('keywordRulesContainer');
    const box = document.createElement('div');
    box.className = 'single-brand-row rule-box';
    box.dataset.locked = 'false';

    box.innerHTML = `
        <!-- Brand Keyword -->
        <div class="mf-field-group" style="flex: 1;">
            <label class="cell-label">Brand Keyword</label>
            <div class="input-with-lock">
                <input type="text" class="mf-input single-input brandKeyword" placeholder="e.g. Zoya" value="${escHtml(prefill.brandKeyword || '')}">
                <button class="icon-btn single-lock-btn lockBtn" onclick="toggleLockBox(this)" title="Lock/Unlock fields">
                    <i class="fa-solid fa-unlock"></i>
                </button>
            </div>
        </div>

        <!-- Must Have -->
        <div class="mf-field-group" style="flex: 1.2;">
            <label class="cell-label">Must Have - Keywords</label>
            <div class="field-container mustHaveContainer">
                <input type="text" class="mf-input single-input mustHave" placeholder="e.g. Titan, Jewelry" value="${escHtml(prefill.mustHave || '')}">
            </div>
        </div>

        <!-- Shouldn't Have -->
        <div class="mf-field-group" style="flex: 1.5;">
            <label class="cell-label">Shouldn't Have Keywords</label>
            <div class="field-container shouldntHaveContainer">
                <input type="text" class="mf-input single-input shouldntHave" placeholder="e.g. Imran" value="${escHtml(prefill.shouldntHave || '')}">
            </div>
        </div>

        <!-- Action Buttons -->
        <div class="mf-field-group" style="justify-content: flex-end; padding-bottom: 2px;">
            <button class="icon-btn delete-btn" onclick="deleteRuleBox(this)" title="Delete rule"
                style="height: 35px; width: 35px; min-width: 35px; background: rgba(255,0,0,0.05) !important;">
                <i class="fa-solid fa-trash"></i>
            </button>
        </div>
    `;
    container.appendChild(box);
}

function deleteRuleBox(btn) {
    const box = btn.closest('.rule-box');
    box.style.opacity = '0';
    box.style.transition = 'opacity 0.2s';
    setTimeout(() => box.remove(), 200);
}

function toggleLockBox(btn) {
    const box = btn.closest('.rule-box');
    const isLocked = box.dataset.locked === 'true';
    const icon = btn.querySelector('i');

    const brandInput = box.querySelector('.brandKeyword');
    const mustHaveContainer = box.querySelector('.mustHaveContainer');
    const shouldntHaveContainer = box.querySelector('.shouldntHaveContainer');

    if (!isLocked) {
        // LOCK
        box.dataset.locked = 'true';
        icon.className = 'fa-solid fa-lock';
        btn.classList.add('locked');
        btn.title = 'Unlock fields';
        if (brandInput) brandInput.setAttribute('readonly', true);

        // Pillify Must Have
        const mustHaveInput = box.querySelector('.mustHave');
        if (mustHaveInput) {
            const val = mustHaveInput.value.trim();
            const pd = buildPillDisplay('mustHave', val, 'pill-blue');
            mustHaveContainer.replaceChild(pd, mustHaveInput);
        }

        // Pillify Shouldn't Have
        const shouldntInput = box.querySelector('.shouldntHave');
        if (shouldntInput) {
            const val = shouldntInput.value.trim();
            const pd = buildPillDisplay('shouldntHave', val, 'pill-red');
            shouldntHaveContainer.replaceChild(pd, shouldntInput);
        }
    } else {
        // UNLOCK
        box.dataset.locked = 'false';
        icon.className = 'fa-solid fa-unlock';
        btn.classList.remove('locked');
        btn.title = 'Lock/Unlock fields';
        if (brandInput) brandInput.removeAttribute('readonly');

        // Restore Must Have
        const mustPd = box.querySelector('.pill-display[data-field="mustHave"]');
        if (mustPd) {
            const val = mustPd.dataset.value;
            const input = document.createElement('input');
            input.type = 'text';
            input.className = 'mf-input single-input mustHave';
            input.placeholder = 'e.g. Titan, Jewelry';
            input.value = val;
            mustHaveContainer.replaceChild(input, mustPd);
        }

        // Restore Shouldn't Have
        const shouldntPd = box.querySelector('.pill-display[data-field="shouldntHave"]');
        if (shouldntPd) {
            const val = shouldntPd.dataset.value;
            const input = document.createElement('input');
            input.type = 'text';
            input.className = 'mf-input single-input shouldntHave';
            input.placeholder = 'e.g. Imran';
            input.value = val;
            shouldntHaveContainer.replaceChild(input, shouldntPd);
        }
    }
}

function buildPillDisplay(field, value, pillClass) {
    const pd = document.createElement('div');
    pd.className = 'pill-display';
    pd.dataset.field = field;
    pd.dataset.value = value;

    if (value) {
        value.split(',').map(v => v.trim()).filter(Boolean).forEach(kw => {
            const pill = document.createElement('span');
            pill.className = `pill ${pillClass}`;
            pill.textContent = kw;
            pd.appendChild(pill);
        });
    } else {
        pd.innerHTML = `<span style="color:var(--text-secondary);font-size:0.75rem;font-style:italic;">None</span>`;
    }
    return pd;
}

function getAllConfigs() {
    const boxes = document.querySelectorAll('.rule-box');
    const configs = [];

    boxes.forEach(box => {
        const getVal = (inputClass, pdField) => {
            const input = box.querySelector(`.${inputClass}`);
            if (input) return input.value.trim();
            const pd = box.querySelector(`.pill-display[data-field="${pdField}"]`);
            if (pd) return pd.dataset.value || '';
            return '';
        };

        const brandInput = box.querySelector('.brandKeyword');
        const brandKeyword = brandInput ? brandInput.value.trim() : '';
        const mustHave = getVal('mustHave', 'mustHave');
        const shouldntHave = getVal('shouldntHave', 'shouldntHave');

        if (!brandKeyword && !mustHave) return;

        configs.push({
            brandName: brandKeyword || 'Unknown Brand',
            keywords: brandKeyword.split(',').map(k => k.trim()).filter(Boolean),
            mustHave: mustHave.split(',').map(k => k.trim()).filter(Boolean),
            shouldntHave: shouldntHave.split(',').map(k => k.trim()).filter(Boolean)
        });
    });

    return configs;
}

/* ─── Analysis ─── */

async function analyzeLinks() {
    const linksInput = document.getElementById('links').value;
    const loader = document.getElementById('loader');
    const btn = document.getElementById('analyzeBtn');
    const progress = document.getElementById('progressText');
    const resultsPanel = document.getElementById('resultsPanel');
    const tableBody = document.querySelector('#resultsTable tbody');

    const links = linksInput.split('\n').map(l => l.trim()).filter(Boolean);
    const configs = getAllConfigs();

    if (configs.length === 0) {
        alert('Please add at least one Keyword Rule before analyzing.');
        return;
    }
    if (links.length === 0) {
        alert('Please paste at least one link to analyze.');
        return;
    }

    // UI: Loading state — swap button content to spinner
    const originalBtnHTML = btn.innerHTML;
    btn.innerHTML = `<span style="display:inline-flex;align-items:center;gap:10px;">
        <span style="width:18px;height:18px;border:3px solid rgba(255,255,255,0.3);border-top-color:#fff;
            border-radius:50%;display:inline-block;animation:spin 0.8s linear infinite;flex-shrink:0;"></span>
        Analyzing ${links.length} link${links.length > 1 ? 's' : ''}...
    </span>`;
    btn.disabled = true;
    resultsPanel.classList.add('hidden');
    tableBody.innerHTML = '';
    globalResults = [];
    progress.style.display = 'none';

    try {
        const response = await fetch('/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                configs: configs,
                links: links
            })
        });

        if (response.status === 402) {
            if (typeof showPaywallModal === 'function') {
                showPaywallModal();
            } else {
                alert('Out of tokens. Please upgrade your plan.');
            }
            return;
        }

        const data = await response.json();

        if (data.error) {
            console.warn(`Error returned from server:`, data.error);
        }

        if (data.results) {
            data.results.forEach(result => {
                globalResults.push({
                    brandName: result.brandName || "Unknown",
                    URL: result.URL || "N/A",
                    Status: result.Status || "Unknown",
                    'Match Count': result['Match Count'] || 0,
                    'Found Keywords': result['Found Keywords'] || ''
                });
            });
        }

        renderTable(globalResults);
        resultsPanel.classList.remove('hidden');
        progress.style.display = 'inline';
        progress.textContent = `✓ Done! Found ${globalResults.filter(r => r.Status.startsWith('Relevant')).length} relevant result(s).`;

    } catch (error) {
        console.error('Error:', error);
        alert('An unexpected error occurred. Please try again.');
        progress.style.display = 'none';
    } finally {
        btn.innerHTML = originalBtnHTML;
        btn.disabled = false;
        loader.classList.add('hidden');
    }
}
const _NEWS_PAGE_SIZE = 300; // rows above this get paginated to avoid DOM lag

function renderTable(results) {
    const tableBody = document.querySelector('#resultsTable tbody');
    tableBody.innerHTML = '';

    if (!results.length) {
        tableBody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--text-secondary);">No results found.</td></tr>';
        return;
    }

    // For very large result sets, render first chunk immediately then stream the rest
    const renderChunk = (items, startIdx) => {
        const frag = document.createDocumentFragment();
        items.forEach(row => {
            const tr = document.createElement('tr');
            let statusClass = 'status-badge ';
            if (row.Status.startsWith('Relevant')) statusClass += 'status-relevant';
            else if (row.Status === 'Irrelevant (Excluded)') statusClass += 'status-missing';
            else if (row.Status.startsWith('Irrelevant')) statusClass += 'status-irrelevant';
            else statusClass += 'status-missing';

            tr.innerHTML = `
                <td style="font-weight:600;">${escHtml(row.brandName)}</td>
                <td><span class="${statusClass}">${escHtml(row.Status)}</span></td>
                <td class="url-cell"><a href="${escHtml(row.URL)}" target="_blank" title="${escHtml(row.URL)}">${escHtml(row.URL)}</a></td>
                <td style="font-size:0.82rem;">${escHtml(row['Found Keywords'] || '–')}</td>
            `;
            frag.appendChild(tr);
        });
        tableBody.appendChild(frag);
    };

    if (results.length <= _NEWS_PAGE_SIZE) {
        renderChunk(results, 0);
    } else {
        // Render first 300 immediately, stream rest in idle chunks
        renderChunk(results.slice(0, _NEWS_PAGE_SIZE), 0);
        let offset = _NEWS_PAGE_SIZE;
        function streamNext() {
            if (offset >= results.length) return;
            const chunk = results.slice(offset, offset + _NEWS_PAGE_SIZE);
            renderChunk(chunk, offset);
            offset += _NEWS_PAGE_SIZE;
            if (offset < results.length) {
                if (typeof requestIdleCallback === 'function') {
                    requestIdleCallback(streamNext, { timeout: 200 });
                } else {
                    setTimeout(streamNext, 0);
                }
            }
        }
        if (typeof requestIdleCallback === 'function') {
            requestIdleCallback(streamNext, { timeout: 200 });
        } else {
            setTimeout(streamNext, 0);
        }
    }
}

function downloadCSV() {
    if (!globalResults.length) return;

    let csv = 'Brand Name,Status,URL,Found Keywords\n';
    globalResults.forEach(row => {
        const kw = (row['Found Keywords'] || '').replace(/"/g, '""');
        const url = row.URL.replace(/"/g, '""');
        csv += `"${row.brandName}","${row.Status}","${url}","${kw}"\n`;
    });

    const blob = new Blob([csv], { type: 'text/csv' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = 'multifind_report.csv';
    link.click();
}

/* ─── Helpers ─── */

function escHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

/* ─── Init ─── */

document.addEventListener('DOMContentLoaded', () => {
    // Render sidebar brands
    renderSidebarBrands();

    // Check if we arrived here from sidebar brand click on another page
    const urlParams = new URLSearchParams(window.location.search);
    const brandIdx = urlParams.get('brand');
    if (brandIdx !== null) {
        // Small delay so page is ready
        setTimeout(() => loadBrandIntoMultifind(parseInt(brandIdx)), 100);
    } else if (document.getElementById('keywordRulesContainer')) {
        // Pre-populate with a single empty rule box if no brand is loaded (MultiFIND page only)
        addRuleBox();
    }
});
