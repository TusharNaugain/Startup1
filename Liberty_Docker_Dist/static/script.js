let globalResults = [];
let globalNewsResults = []; // Store news results separately

async function fetchNews() {
    const topic = document.getElementById('newsTopic').value;
    const startDate = document.getElementById('startDate').value;
    const endDate = document.getElementById('endDate').value;
    const loader = document.getElementById('newsLoader');
    const btn = document.getElementById('fetchNewsBtn');
    const resultsPanel = document.getElementById('newsResultsPanel');
    const tableBody = document.querySelector('#newsTable tbody');
    const countBadge = document.getElementById('articleCount');

    if (!topic) {
        alert("Please enter a Topic.");
        return;
    }

    // UI State: Loading
    loader.classList.remove('hidden');
    btn.disabled = true;
    resultsPanel.classList.add('hidden');
    tableBody.innerHTML = '';

    try {
        const response = await fetch('/api/fetch_news', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ topic, start_date: startDate, end_date: endDate })
        });

        const data = await response.json();

        if (data.error) {
            alert(data.error);
            return;
        }

        globalNewsResults = data.articles;
        countBadge.innerText = globalNewsResults.length;
        renderNewsTable(globalNewsResults);
        resultsPanel.classList.remove('hidden');

    } catch (error) {
        console.error('Error:', error);
        alert('An error occurred while fetching news.');
    } finally {
        loader.classList.add('hidden');
        btn.disabled = false;
    }
}

function renderNewsTable(articles) {
    const tableBody = document.querySelector('#newsTable tbody');
    tableBody.innerHTML = '';

    articles.forEach(row => {
        const tr = document.createElement('tr');
        // Parse date for better display if needed, but raw RSS date is OK
        const dateStr = new Date(row.Published).toLocaleDateString() || row.Published;

        tr.innerHTML = `
            <td>${dateStr}</td>
            <td>${row.Source}</td>
            <td>${row.Title}</td>
            <td class="url-cell"><a href="${row.Link}" target="_blank">Open Link</a></td>
        `;
        tableBody.appendChild(tr);
    });
}

function downloadNewsCSV() {
    if (!globalNewsResults.length) return;

    let csvContent = "data:text/csv;charset=utf-8,";
    csvContent += "Published Date,Source,Title,URL\n";

    globalNewsResults.forEach(row => {
        const title = row.Title.replace(/"/g, '""');
        const line = `"${row.Published}","${row.Source}","${title}","${row.Link}"`;
        csvContent += line + "\n";
    });

    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", "news_report.csv");
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

async function analyzeLinks() {
    const keywordsInput = document.getElementById('keywords').value;
    const contextKeywordsInput = document.getElementById('context_keywords').value;
    const linksInput = document.getElementById('links').value;
    const loader = document.getElementById('loader');
    const btn = document.getElementById('analyzeBtn');
    const resultsPanel = document.getElementById('resultsPanel');
    const tableBody = document.querySelector('#resultsTable tbody');

    // Validation
    const keywords = keywordsInput.split(',').map(k => k.trim()).filter(k => k);
    const context_keywords = contextKeywordsInput.split(',').map(k => k.trim()).filter(k => k); // Validate Context
    const links = linksInput.split('\n').map(l => l.trim()).filter(l => l);

    if (keywords.length === 0 || links.length === 0) {
        alert("Please enter both Keywords and Links.");
        return;
    }

    // UI State: Loading
    loader.classList.remove('hidden');
    btn.disabled = true;
    resultsPanel.classList.add('hidden');
    tableBody.innerHTML = '';

    try {
        const response = await fetch('/analyze', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ keywords, context_keywords, links }) // Send context
        });

        const data = await response.json();

        if (data.error) {
            alert(data.error);
            return;
        }

        globalResults = data.results;
        renderTable(globalResults);
        resultsPanel.classList.remove('hidden');

    } catch (error) {
        console.error('Error:', error);
        alert('An error occurred during analysis.');
    } finally {
        // UI State: Ready
        loader.classList.add('hidden');
        btn.disabled = false;
    }
}

function renderTable(results) {
    const tableBody = document.querySelector('#resultsTable tbody');
    tableBody.innerHTML = '';

    results.forEach(row => {
        const tr = document.createElement('tr');

        // Status Class
        let statusClass = 'status-badge ';
        if (row.Status === 'Relevant') statusClass += 'status-relevant';
        else if (row.Status === 'Irrelevant') statusClass += 'status-irrelevant';
        else statusClass += 'status-missing';

        tr.innerHTML = `
            <td><span class="${statusClass}">${row.Status}</span></td>
            <td class="url-cell"><a href="${row.URL}" target="_blank" title="${row.URL}">${row.URL}</a></td>
            <td>${row['Match Count']}</td>
            <td>${row['Found Keywords'] || '-'}</td>
        `;
        tableBody.appendChild(tr);
    });
}

function downloadCSV() {
    if (!globalResults.length) return;

    let csvContent = "data:text/csv;charset=utf-8,";
    csvContent += "URL,Status,Match Count,Found Keywords\n";

    globalResults.forEach(row => {
        // Escape quotes
        const keywords = row['Found Keywords'].replace(/"/g, '""');
        const line = `"${row.URL}","${row.Status}",${row['Match Count']},"${keywords}"`;
        csvContent += line + "\n";
    });

    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", "link_report.csv");
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}
