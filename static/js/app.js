// Use relative paths - works with any host/port
const API_BASE = '';

// Helper function to escape HTML
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// State
let currentPage = 0;
let pageSize = 50;
let totalHoldings = 0;
let filters = {
    ticker: '',
    asset_type: '',
    currency: '',
    hide_zero: true  // Default: hide zero balances
};
let chartAssetType = null;
let sortColumn = null;
let sortDirection = 'asc'; // 'asc' or 'desc'
let allHoldings = []; // Store all holdings for client-side sorting

// Format currency
function formatCurrency(value, currency = 'RUB') {
    const formatter = new Intl.NumberFormat('ru-RU', {
        style: 'currency',
        currency: currency,
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
    return formatter.format(value);
}

// Format number
function formatNumber(value, decimals = 2) {
    return new Intl.NumberFormat('ru-RU', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals
    }).format(value);
}

// Format percentage
function formatPercent(value) {
    const sign = value >= 0 ? '+' : '';
    return `${sign}${formatNumber(value)}%`;
}

// Format date
function formatDate(dateString) {
    const date = new Date(dateString);
    return new Intl.DateTimeFormat('ru-RU', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    }).format(date);
}

// Get badge class for asset type
function getAssetTypeBadge(assetType) {
    const badges = {
        'stock': 'badge-stock',
        'bond': 'badge-bond',
        'asset': 'badge-asset',
        'crypto': 'badge-crypto',
        'cash': 'badge-cash'
    };
    return badges[assetType] || 'badge-asset';
}

// Get PnL class
function getPnLClass(value) {
    if (value > 0) return 'pnl-positive';
    if (value < 0) return 'pnl-negative';
    return 'pnl-zero';
}

// Load statistics
async function loadStatistics() {
    try {
        const response = await fetch(`${API_BASE}/stats`);
        const stats = await response.json();

        document.getElementById('stat-total-holdings').textContent = stats.total_holdings;
        document.getElementById('stat-invested').textContent = formatCurrency(stats.total_invested_value, 'RUB');
        document.getElementById('stat-current').textContent = formatCurrency(stats.total_current_value, 'RUB');
        document.getElementById('stat-pnl-value').textContent = formatCurrency(stats.total_pnl_value, 'RUB');
        document.getElementById('stat-pnl-pct').textContent = formatPercent(stats.total_pnl_pct);
        document.getElementById('stat-pnl-pct').className = `stat-value ${getPnLClass(stats.total_pnl_pct)}`;
        
        // Update last sync date
        if (stats.last_sync) {
            document.getElementById('stat-last-sync').textContent = formatDate(stats.last_sync);
        } else {
            document.getElementById('stat-last-sync').textContent = 'Never';
        }

        // Update pie charts
        updatePieCharts(stats);

        // Breakdown by asset type - show value instead of count
        const assetTypeDiv = document.getElementById('breakdown-asset-type');
        assetTypeDiv.innerHTML = '';
        Object.entries(stats.by_asset_type).forEach(([type, data]) => {
            // Use value field for display, with value_pct for percentage
            let value = 0;
            if (data && typeof data === 'object') {
                if ('value' in data && data.value !== null && data.value !== undefined) {
                    value = parseFloat(data.value) || 0;
                }
            }
            
            // Skip if value is zero or very small (less than 1 ruble)
            if (value < 1.0) {
                return;
            }
            
            const valuePct = (data && typeof data === 'object' && 'value_pct' in data) ? parseFloat(data.value_pct) : null;
            const pct = valuePct !== null ? valuePct : null;
            
            const item = document.createElement('div');
            item.className = 'breakdown-item';
            item.innerHTML = `
                <span class="breakdown-item-label">${type}</span>
                <span class="breakdown-item-value">
                    ${formatCurrency(value, 'RUB')}${pct !== null && !isNaN(pct) ? ` <span class="breakdown-item-pct">(${pct.toFixed(1)}%)</span>` : ''}
                </span>
            `;
            assetTypeDiv.appendChild(item);
        });


        document.getElementById('stats-loading').style.display = 'none';
        document.getElementById('stats-content').style.display = 'grid';
    } catch (error) {
        console.error('Error loading statistics:', error);
        document.getElementById('stats-loading').textContent = 'Error loading statistics';
    }
}

// Update pie charts
function updatePieCharts(stats) {
    const chartColors = [
        '#4285F4', // Google Blue
        '#34A853', // Google Green
        '#FBBC04', // Google Yellow
        '#EA4335', // Google Red
        '#9AA0A6', // Google Gray
        '#FF6D01', // Orange
        '#9334E6', // Purple
        '#00BCD4', // Cyan
    ];

    // Chart: By Asset Type (value) - use value field, not count
    const assetTypeData = {};
    Object.entries(stats.by_asset_type).forEach(([key, data]) => {
        // Force use value field, not count
        let assetValue = 0;
        if (data && typeof data === 'object') {
            // Explicitly check for value field first
            if ('value' in data && data.value !== null && data.value !== undefined) {
                assetValue = data.value;
            } else if ('count' in data && data.count !== null && data.count !== undefined) {
                // Fallback to count only if value is not available
                assetValue = data.count;
            }
        }
        assetTypeData[key] = assetValue;
    });
    updateChart('chart-asset-type', assetTypeData, chartColors, (label, value, total) => {
        const percentage = ((value / total) * 100).toFixed(1);
        return `${label}: ${formatCurrency(value, 'RUB')} (${percentage}%)`;
    }, chartAssetType, (chart) => { chartAssetType = chart; });
}

// Helper function to create/update a chart
function updateChart(canvasId, data, colors, tooltipFormatter, existingChart, setChartCallback) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;

    const chartData = [];
    const chartLabels = [];

    Object.entries(data).forEach(([key, value], index) => {
        const numValue = (value.count !== undefined) ? value.count : ((value.value !== undefined) ? value.value : value);
        if (numValue > 0) {
            chartLabels.push(key);
            chartData.push(numValue);
        }
    });

    if (chartData.length === 0) return;

    // Destroy existing chart if it exists
    if (existingChart) {
        existingChart.destroy();
    }

    // Create new chart
    const chart = new Chart(ctx, {
        type: 'pie',
        data: {
            labels: chartLabels,
            datasets: [{
                data: chartData,
                backgroundColor: colors.slice(0, chartData.length),
                borderColor: '#ffffff',
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        padding: 8,
                        font: {
                            family: 'Google Sans, sans-serif',
                            size: 11
                        },
                        color: 'var(--text-primary)'
                    }
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const label = context.label || '';
                            const value = context.parsed || 0;
                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                            return tooltipFormatter(label, value, total);
                        }
                    },
                    font: {
                        family: 'Google Sans, sans-serif'
                    }
                }
            }
        }
    });

    setChartCallback(chart);
}

// Load news analysis status for a ticker
async function loadNewsStatus(ticker) {
    try {
        const response = await fetch(`${API_BASE}/news-analysis/${encodeURIComponent(ticker)}`);
        if (response.ok) {
            const result = await response.json();
            // Map analysis_status to status for consistency
            if (result.analysis_status) {
                result.status = result.analysis_status;
            }
            return result;
        } else {
            return { status: 'pending', ticker: ticker, sentiment: null };
        }
    } catch (error) {
        return { status: 'pending', ticker: ticker, sentiment: null };
    }
}

// Get HTML for news status badge - show sentiment instead of status
function getNewsStatusHTML(status) {
    // If analysis is completed and has sentiment, show sentiment
    if (status.status === 'completed' && status.sentiment) {
        const sentimentMap = {
            'positive': { text: 'Positive', class: 'sentiment-positive', icon: '📈' },
            'negative': { text: 'Negative', class: 'sentiment-negative', icon: '📉' },
            'neutral': { text: 'Neutral', class: 'sentiment-neutral', icon: '➡️' }
        };
        const sentimentInfo = sentimentMap[status.sentiment.toLowerCase()] || sentimentMap['neutral'];
        return `<span class="news-status-badge ${sentimentInfo.class}" data-ticker="${status.ticker}" style="cursor: pointer;">${sentimentInfo.icon} ${sentimentInfo.text}</span>`;
    }
    
    // Otherwise show status
    const statusMap = {
        'pending': { text: 'Pending', class: 'status-pending', icon: '⏳' },
        'completed': { text: 'Ready', class: 'status-completed', icon: '✅' },
        'failed': { text: 'Failed', class: 'status-failed', icon: '❌' }
    };
    
    const statusInfo = statusMap[status.status] || statusMap['pending'];
    return `<span class="news-status-badge ${statusInfo.class}" data-ticker="${status.ticker}">${statusInfo.icon} ${statusInfo.text}</span>`;
}

// Show news analysis modal with saved data
function showNewsAnalysisModal(ticker, name, analysisData) {
    // Create or get modal
    let modal = document.getElementById('news-analysis-modal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'news-analysis-modal';
        modal.className = 'modal';
        modal.innerHTML = `
            <div class="modal-content">
                <div class="modal-header">
                    <h2>📰 News Analysis: <span id="modal-ticker">${ticker}</span></h2>
                    <button class="modal-close">&times;</button>
                </div>
                <div class="modal-body">
                    <div id="news-analysis-loading" class="loading" style="display: none;">Loading...</div>
                    <div id="news-analysis-content" style="display: none;"></div>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
        
        // Close modal handlers
        const closeBtn = modal.querySelector('.modal-close');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => {
                modal.style.display = 'none';
            });
        }
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.style.display = 'none';
            }
        });
    }
    
    // Update modal
    const tickerSpan = document.getElementById('modal-ticker');
    if (tickerSpan) {
        tickerSpan.textContent = `${ticker} (${name || ticker})`;
    }
    const loadingDiv = document.getElementById('news-analysis-loading');
    const contentDiv = document.getElementById('news-analysis-content');
    
    if (!loadingDiv || !contentDiv) {
        console.error('Modal elements not found');
        return;
    }
    
    modal.style.display = 'flex';
    loadingDiv.style.display = 'block';
    contentDiv.style.display = 'none';
    contentDiv.innerHTML = '';
    
    // Load full analysis data
    fetch(`${API_BASE}/news-analysis/${encodeURIComponent(ticker)}`)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            return response.json();
        })
        .then(result => {
            // API returns status: "success" for the response
            // Check if we have the required data
            if (result.status === 'success' || (result.news_articles && result.analysis)) {
                let html = `
                    <div class="news-analysis-header">
                        <div class="holding-info">
                            <h3>${escapeHtml(name)} (${escapeHtml(ticker)})</h3>
                            <p>Analysis Date: ${result.created_at ? new Date(result.created_at).toLocaleString() : 'Unknown'}</p>
                        </div>
                        <div class="news-count-badge">
                            📰 ${result.news_count || 0} articles analyzed
                        </div>
                    </div>
                    
                    <div class="news-articles-section">
                        <h4>Recent News Articles</h4>
                        <div class="news-articles-list">
                `;
                
                // Check if news_articles is an array
                const articles = Array.isArray(result.news_articles) ? result.news_articles : [];
                if (articles.length === 0) {
                    html += '<p style="color: var(--text-secondary); padding: 16px;">No news articles available.</p>';
                } else {
                    articles.forEach((article, index) => {
                        if (!article) return; // Skip null/undefined articles
                        
                        // Escape HTML to prevent XSS
                        const title = escapeHtml(article.title || 'No title');
                        const summary = article.summary ? escapeHtml(article.summary) : '';
                        const source = escapeHtml(article.source || 'Unknown');
                        const published = escapeHtml(article.published || 'Unknown date');
                        const link = article.link || '#';
                        
                        html += `
                            <div class="news-article-item">
                                <div class="news-article-header">
                                    <span class="news-article-number">#${index + 1}</span>
                                    <span class="news-article-source">${source}</span>
                                    <span class="news-article-date">${published}</span>
                                </div>
                                <h5 class="news-article-title">${title}</h5>
                                ${summary ? `<p class="news-article-summary">${summary}</p>` : ''}
                                ${link !== '#' ? `<a href="${escapeHtml(link)}" target="_blank" rel="noopener noreferrer" class="news-article-link">Read more →</a>` : ''}
                            </div>
                        `;
                    });
                }
                
                html += `
                        </div>
                    </div>
                    
                    <div class="news-analysis-section">
                        <h4>AI Analysis & Recommendations</h4>
                        <div class="news-analysis-text">
                `;
                
                // Parse markdown and render as HTML
                if (typeof marked !== 'undefined') {
                    html += marked.parse(result.analysis || 'No analysis available');
                } else {
                    html += (result.analysis || 'No analysis available').replace(/\n/g, '<br>');
                }
                
                html += `
                        </div>
                    </div>
                `;
                
                contentDiv.innerHTML = html;
                contentDiv.style.display = 'block';
            } else {
                contentDiv.innerHTML = `<div style="color: var(--danger-color); padding: 20px;">Error: ${result.message || 'Unknown error'}</div>`;
                contentDiv.style.display = 'block';
            }
        })
        .catch(error => {
            contentDiv.innerHTML = `<div style="color: var(--danger-color); padding: 20px;">Error: ${error.message}</div>`;
            contentDiv.style.display = 'block';
        })
        .finally(() => {
            loadingDiv.style.display = 'none';
        });
}

// Load holdings
async function loadHoldings() {
    try {
        // Load all holdings for client-side sorting and filtering
        // Add cache-busting parameter to ensure fresh data
        const params = new URLSearchParams({
            skip: 0,
            limit: 10000,  // Get all holdings for client-side operations
            _t: Date.now()  // Cache-busting parameter
        });

        if (filters.ticker) params.append('ticker', filters.ticker);
        if (filters.asset_type) params.append('asset_type', filters.asset_type);
        if (filters.currency) params.append('currency', filters.currency);

        document.getElementById('holdings-loading').style.display = 'block';
        document.getElementById('holdings-content').style.display = 'none';

        const response = await fetch(`${API_BASE}/holdings?${params}`);
        const allHoldingsData = await response.json();
        
        // Store all holdings
        allHoldings = allHoldingsData;
        
        // Filter zero balances if enabled (check only quantity)
        const hideZeroCheckbox = document.getElementById('filter-hide-zero');
        const shouldHideZero = hideZeroCheckbox ? hideZeroCheckbox.checked : (filters.hide_zero || false);
        
        let filteredHoldings = [...allHoldingsData];
        if (shouldHideZero) {
            const beforeCount = filteredHoldings.length;
            filteredHoldings = filteredHoldings.filter(h => {
                const qty = parseFloat(h.qty);
                if (isNaN(qty)) {
                    console.warn(`Invalid qty for ${h.ticker}:`, h.qty);
                    return false;
                }
                return qty > 0.0001;
            });
            console.log(`Filtered: ${filteredHoldings.length} of ${beforeCount} holdings (hiding zero qty)`);
        }
        
        // Apply sorting
        if (sortColumn) {
            filteredHoldings = sortHoldings(filteredHoldings, sortColumn, sortDirection);
        }
        
        // Apply pagination
        const totalFilteredCount = filteredHoldings.length;
        const startIndex = currentPage * pageSize;
        const endIndex = startIndex + pageSize;
        const paginatedHoldings = filteredHoldings.slice(startIndex, endIndex);
        
        const tbody = document.getElementById('holdings-table-body');
        tbody.innerHTML = '';

        if (paginatedHoldings.length === 0) {
            tbody.innerHTML = '<tr><td colspan="13" style="text-align: center; padding: 2rem; color: var(--text-secondary);">No holdings found</td></tr>';
        } else {
            // Use for...of loop to properly handle async operations
            for (const holding of paginatedHoldings) {
                const row = document.createElement('tr');
                
                // Use sentiment from holding if available - no need to make additional API calls
                // The /holdings endpoint already includes sentiment, so we don't need to fetch it separately
                let status = { status: 'pending', ticker: holding.ticker, sentiment: holding.sentiment || null };
                if (holding.sentiment) {
                    // If we have sentiment, assume status is completed
                    status.status = 'completed';
                }
                // If no sentiment, just show "Pending" - don't make API call here
                // API call will be made only when user clicks on the sentiment badge
                
                row.innerHTML = `
                    <td><strong>${holding.ticker}</strong></td>
                    <td>${holding.name || '-'}</td>
                    <td><span class="badge ${getAssetTypeBadge(holding.asset_type)}">${holding.asset_type}</span></td>
                    <td>${holding.currency}</td>
                    <td>${formatNumber(holding.qty, 4)}</td>
                    <td>${formatCurrency(holding.avg_price, holding.currency)}</td>
                    <td>${formatCurrency(holding.invested_value, holding.currency)}</td>
                    <td>${formatCurrency(holding.current_value, holding.currency)}</td>
                    <td class="${getPnLClass(holding.pnl_value)}">${formatCurrency(holding.pnl_value, holding.currency)}</td>
                    <td class="${getPnLClass(holding.pnl_pct)}">${formatPercent(holding.pnl_pct)}</td>
                    <td>${formatPercent(holding.share_pct)}</td>
                    <td class="news-status-cell"><span class="news-status-badge status-pending">Loading...</span></td>
                    <td><button class="btn-analyze-news" data-ticker="${holding.ticker}" data-name="${holding.name || holding.ticker}">📰 Analyze News</button></td>
                `;
                tbody.appendChild(row);
                
                // Update status cell with sentiment
                const statusCell = row.querySelector('.news-status-cell');
                if (statusCell) {
                    statusCell.innerHTML = getNewsStatusHTML(status);
                    // Add click handler if completed
                    const statusBadge = statusCell.querySelector('.news-status-badge');
                    if (statusBadge && status.status === 'completed') {
                        statusBadge.style.cursor = 'pointer';
                        statusBadge.addEventListener('click', () => {
                            showNewsAnalysisModal(holding.ticker, holding.name || holding.ticker, status);
                        });
                    }
                }
            }
            
            // Add event listeners for analyze news buttons
            document.querySelectorAll('.btn-analyze-news').forEach(btn => {
                btn.addEventListener('click', async (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    // Use currentTarget to get the button element, not the clicked child
                    const button = e.currentTarget || e.target.closest('.btn-analyze-news');
                    const ticker = button.getAttribute('data-ticker');
                    const name = button.getAttribute('data-name');
                    if (ticker) {
                        await analyzeStockNews(ticker, name);
                    } else {
                        console.error('Ticker not found for button:', button);
                    }
                });
            });
        }
        
        // Update pagination
        document.getElementById('pagination-info').textContent = `Page ${currentPage + 1} (${paginatedHoldings.length} of ${totalFilteredCount} items)`;
        document.getElementById('btn-prev').disabled = currentPage === 0;
        // Disable next button if we're on the last page
        document.getElementById('btn-next').disabled = (currentPage + 1) * pageSize >= totalFilteredCount;

        document.getElementById('holdings-loading').style.display = 'none';
        document.getElementById('holdings-content').style.display = 'block';
    } catch (error) {
        console.error('Error loading holdings:', error);
        document.getElementById('holdings-loading').textContent = 'Error loading holdings';
    }
}

// Sort holdings
function sortHoldings(holdings, column, direction) {
    return [...holdings].sort((a, b) => {
        let aVal, bVal;
        
        switch(column) {
            case 'ticker':
                aVal = a.ticker || '';
                bVal = b.ticker || '';
                return direction === 'asc' ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
            case 'name':
                aVal = a.name || '';
                bVal = b.name || '';
                return direction === 'asc' ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
            case 'type':
                aVal = a.asset_type || '';
                bVal = b.asset_type || '';
                return direction === 'asc' ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
            case 'currency':
                aVal = a.currency || '';
                bVal = b.currency || '';
                return direction === 'asc' ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
            case 'quantity':
                aVal = parseFloat(a.qty) || 0;
                bVal = parseFloat(b.qty) || 0;
                return direction === 'asc' ? aVal - bVal : bVal - aVal;
            case 'avg_price':
                aVal = parseFloat(a.avg_price) || 0;
                bVal = parseFloat(b.avg_price) || 0;
                return direction === 'asc' ? aVal - bVal : bVal - aVal;
            case 'invested':
                aVal = parseFloat(a.invested_value) || 0;
                bVal = parseFloat(b.invested_value) || 0;
                return direction === 'asc' ? aVal - bVal : bVal - aVal;
            case 'current':
                aVal = parseFloat(a.current_value) || 0;
                bVal = parseFloat(b.current_value) || 0;
                return direction === 'asc' ? aVal - bVal : bVal - aVal;
            case 'pnl':
                aVal = parseFloat(a.pnl_value) || 0;
                bVal = parseFloat(b.pnl_value) || 0;
                return direction === 'asc' ? aVal - bVal : bVal - aVal;
            case 'pnl_pct':
                aVal = parseFloat(a.pnl_pct) || 0;
                bVal = parseFloat(b.pnl_pct) || 0;
                return direction === 'asc' ? aVal - bVal : bVal - aVal;
            case 'share_pct':
                aVal = parseFloat(a.share_pct) || 0;
                bVal = parseFloat(b.share_pct) || 0;
                return direction === 'asc' ? aVal - bVal : bVal - aVal;
            case 'sentiment':
                // Sort sentiment: positive > neutral > negative > null
                const sentimentOrder = { 'positive': 3, 'neutral': 2, 'negative': 1, null: 0, undefined: 0 };
                aVal = sentimentOrder[a.sentiment] || 0;
                bVal = sentimentOrder[b.sentiment] || 0;
                return direction === 'asc' ? aVal - bVal : bVal - aVal;
            default:
                return 0;
        }
    });
}

// Handle column header click for sorting
function setupTableSorting() {
    const headers = document.querySelectorAll('.holdings-table th');
    const columnMap = ['ticker', 'name', 'type', 'currency', 'quantity', 'avg_price', 'invested', 'current', 'pnl', 'pnl_pct', 'share_pct', 'sentiment'];
    
    headers.forEach((header, index) => {
        const column = columnMap[index];
        
        if (column) {
            header.style.cursor = 'pointer';
            header.classList.add('sortable');
            
            header.addEventListener('click', () => {
                // Toggle sort direction if clicking the same column
                if (sortColumn === column) {
                    sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
                } else {
                    sortColumn = column;
                    sortDirection = 'asc';
                }
                
                // Update visual indicators
                headers.forEach(h => {
                    h.classList.remove('sort-asc', 'sort-desc');
                });
                header.classList.add(sortDirection === 'asc' ? 'sort-asc' : 'sort-desc');
                
                // Reset to first page and reload
                currentPage = 0;
                loadHoldings();
            });
        }
    });
}

// Event listeners
document.getElementById('filter-ticker').addEventListener('input', (e) => {
    filters.ticker = e.target.value;
    currentPage = 0;
    loadHoldings();
});

document.getElementById('filter-asset-type').addEventListener('change', (e) => {
    filters.asset_type = e.target.value;
    currentPage = 0;
    loadHoldings();
});

document.getElementById('filter-currency').addEventListener('change', (e) => {
    filters.currency = e.target.value;
    currentPage = 0;
    loadHoldings();
});

const hideZeroCheckbox = document.getElementById('filter-hide-zero');
if (hideZeroCheckbox) {
    hideZeroCheckbox.addEventListener('change', (e) => {
        filters.hide_zero = e.target.checked;
        currentPage = 0;
        console.log('Hide zero filter changed to:', filters.hide_zero);
        loadHoldings();
    });
} else {
    console.error('filter-hide-zero checkbox not found when setting up event listener!');
}

document.getElementById('btn-refresh').addEventListener('click', () => {
    loadStatistics();
    loadHoldings();
});

document.getElementById('btn-prev').addEventListener('click', () => {
    if (currentPage > 0) {
        currentPage--;
        loadHoldings();
    }
});

document.getElementById('btn-next').addEventListener('click', () => {
    currentPage++;
    loadHoldings();
});

// Excel file upload
const fileInput = document.getElementById('file-input');
const fileName = document.getElementById('file-name');
const btnSyncExcel = document.getElementById('btn-sync-excel');

fileInput.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (file) {
        fileName.textContent = file.name;
        btnSyncExcel.disabled = false;
    } else {
        fileName.textContent = 'No file chosen';
        btnSyncExcel.disabled = true;
    }
});

btnSyncExcel.addEventListener('click', async () => {
    const file = fileInput.files[0];
    if (!file) {
        alert('Please select a file first');
        return;
    }
    
    const statusDiv = document.getElementById('sync-status');
    const btn = btnSyncExcel;
    
    btn.disabled = true;
    btn.textContent = 'Uploading...';
    statusDiv.style.display = 'block';
    statusDiv.className = 'sync-status loading';
    statusDiv.textContent = 'Uploading and syncing Excel file...';
    
    try {
        const formData = new FormData();
        formData.append('file', file);
        
        const response = await fetch(`${API_BASE}/sync`, {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        
        if (result.status === 'success') {
            statusDiv.className = 'sync-status success';
            statusDiv.textContent = `Successfully synced ${result.count} holdings from Excel!`;
            
            // Reset file input
            fileInput.value = '';
            fileName.textContent = 'No file chosen';
            
            // Reload data after sync
            setTimeout(() => {
                loadStatistics();
                loadHoldings();
            }, 1000);
        } else {
            statusDiv.className = 'sync-status error';
            statusDiv.textContent = `Error: ${result.message || 'Unknown error'}`;
        }
    } catch (error) {
        statusDiv.className = 'sync-status error';
        statusDiv.textContent = `Error: ${error.message}`;
    } finally {
        btn.disabled = false;
        btn.textContent = '📤 Upload & Sync Excel';
    }
});

// Sync from public URL
document.getElementById('btn-sync-public').addEventListener('click', async () => {
    const url = document.getElementById('sync-url').value.trim();
    const statusDiv = document.getElementById('sync-status');
    const btn = document.getElementById('btn-sync-public');
    
    if (!url) {
        statusDiv.textContent = 'Please enter a URL';
        statusDiv.style.display = 'block';
        statusDiv.className = 'sync-status error';
        return;
    }
    
    btn.disabled = true;
    btn.textContent = 'Syncing...';
    statusDiv.style.display = 'block';
    statusDiv.className = 'sync-status loading';
    statusDiv.textContent = 'Syncing portfolio from public URL...';
    
    try {
        const response = await fetch(`${API_BASE}/sync/public?url=${encodeURIComponent(url)}`);
        const result = await response.json();
        
        if (result.status === 'success') {
            statusDiv.className = 'sync-status success';
            statusDiv.textContent = `Successfully synced ${result.count} holdings!`;
            
            // Reload data after sync
            setTimeout(() => {
                loadStatistics();
                loadHoldings();
            }, 1000);
        } else {
            statusDiv.className = 'sync-status error';
            statusDiv.textContent = `Error: ${result.message || 'Unknown error'}`;
        }
    } catch (error) {
        statusDiv.className = 'sync-status error';
        statusDiv.textContent = `Error: ${error.message}`;
    } finally {
        btn.disabled = false;
        btn.textContent = '📥 Sync from Public URL';
    }
});

// Get AI recommendations
document.getElementById('btn-get-recommendations').addEventListener('click', async () => {
    const btn = document.getElementById('btn-get-recommendations');
    const loadingDiv = document.getElementById('recommendations-loading');
    const contentDiv = document.getElementById('recommendations-content');
    
    btn.disabled = true;
    btn.textContent = '⏳ Analyzing...';
    loadingDiv.style.display = 'block';
    contentDiv.style.display = 'none';
    
    try {
        const response = await fetch(`${API_BASE}/recommendations`, {
            method: 'POST'
        });
        
        const result = await response.json();
        
        if (result.status === 'success') {
            // Parse markdown and render as HTML
            if (typeof marked !== 'undefined') {
                // Configure marked options for better formatting
                marked.setOptions({
                    breaks: true,
                    gfm: true,
                    headerIds: false,
                    mangle: false
                });
                contentDiv.innerHTML = marked.parse(result.recommendations);
            } else {
                // Fallback to plain text if marked is not available
                contentDiv.innerHTML = result.recommendations.replace(/\n/g, '<br>');
            }
            contentDiv.style.display = 'block';
        } else {
            contentDiv.innerHTML = `<div style="color: var(--danger-color);">Error: ${result.message || 'Unknown error'}</div>`;
            contentDiv.style.display = 'block';
        }
    } catch (error) {
        contentDiv.innerHTML = `<div style="color: var(--danger-color);">Error: ${error.message}</div>`;
        contentDiv.style.display = 'block';
    } finally {
        btn.disabled = false;
        btn.textContent = '🤖 Get AI Recommendations';
        loadingDiv.style.display = 'none';
    }
});

// Analyze stock news
async function analyzeStockNews(ticker, name) {
    if (!ticker) {
        console.error('Ticker is required');
        alert('Error: Ticker is required');
        return;
    }
    
    // Create or get modal
    let modal = document.getElementById('news-analysis-modal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'news-analysis-modal';
        modal.className = 'modal';
        modal.innerHTML = `
            <div class="modal-content">
                <div class="modal-header">
                    <h2>📰 News Analysis: <span id="modal-ticker">${ticker}</span></h2>
                    <button class="modal-close">&times;</button>
                </div>
                <div class="modal-body">
                    <div id="news-analysis-loading" class="loading" style="display: none;">Fetching news and analyzing...</div>
                    <div id="news-analysis-content" style="display: none;"></div>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
        
        // Close modal handlers
        const closeBtn = modal.querySelector('.modal-close');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => {
                modal.style.display = 'none';
            });
        }
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.style.display = 'none';
            }
        });
    }
    
    // Update modal
    const tickerSpan = document.getElementById('modal-ticker');
    if (tickerSpan) {
        tickerSpan.textContent = `${ticker} (${name || ticker})`;
    }
    const loadingDiv = document.getElementById('news-analysis-loading');
    const contentDiv = document.getElementById('news-analysis-content');
    
    if (!loadingDiv || !contentDiv) {
        console.error('Modal elements not found');
        return;
    }
    
    modal.style.display = 'flex';
    loadingDiv.style.display = 'block';
    contentDiv.style.display = 'none';
    contentDiv.innerHTML = '';
    
    try {
        const response = await fetch(`${API_BASE}/analyze-news/${encodeURIComponent(ticker)}`, {
            method: 'POST'
        });
        
        if (!response.ok) {
            const errorText = await response.text();
            let errorMessage = `HTTP ${response.status}`;
            try {
                const errorJson = JSON.parse(errorText);
                errorMessage = errorJson.detail || errorJson.message || errorMessage;
            } catch (e) {
                errorMessage = errorText || errorMessage;
            }
            throw new Error(errorMessage);
        }
        
        const result = await response.json();
        
        if (result.status === 'success') {
            let html = `
                <div class="news-analysis-header">
                    <div class="holding-info">
                        <h3>${result.holding.name} (${result.holding.ticker})</h3>
                        <p>Current Value: ${formatCurrency(result.holding.current_value, 'RUB')} | 
                           P&L: ${formatPercent(result.holding.pnl_pct)} | 
                           Portfolio Share: ${formatPercent(result.holding.share_pct)}</p>
                    </div>
                    <div class="news-count-badge">
                        📰 ${result.news_count} articles analyzed
                    </div>
                </div>
                
                <div class="news-articles-section">
                    <h4>Recent News Articles</h4>
                    <div class="news-articles-list">
            `;
            
            result.news_articles.forEach((article, index) => {
                html += `
                    <div class="news-article-item">
                        <div class="news-article-header">
                            <span class="news-article-number">#${index + 1}</span>
                            <span class="news-article-source">${article.source}</span>
                            <span class="news-article-date">${article.published || 'Unknown date'}</span>
                        </div>
                        <h5 class="news-article-title">${article.title}</h5>
                        ${article.summary ? `<p class="news-article-summary">${article.summary}</p>` : ''}
                        ${article.link ? `<a href="${article.link}" target="_blank" class="news-article-link">Read more →</a>` : ''}
                    </div>
                `;
            });
            
            html += `
                    </div>
                </div>
                
                <div class="news-analysis-section">
                    <h4>AI Analysis & Recommendations</h4>
                    <div class="news-analysis-text">
            `;
            
            // Parse markdown and render as HTML
            if (typeof marked !== 'undefined') {
                html += marked.parse(result.analysis);
            } else {
                html += result.analysis.replace(/\n/g, '<br>');
            }
            
            html += `
                    </div>
                </div>
            `;
            
            contentDiv.innerHTML = html;
            contentDiv.style.display = 'block';
        } else {
            contentDiv.innerHTML = `<div style="color: var(--danger-color); padding: 20px;">Error: ${result.message || 'Unknown error'}</div>`;
            contentDiv.style.display = 'block';
        }
    } catch (error) {
        contentDiv.innerHTML = `<div style="color: var(--danger-color); padding: 20px;">Error: ${error.message}</div>`;
        contentDiv.style.display = 'block';
    } finally {
        loadingDiv.style.display = 'none';
    }
}

// Batch analysis functions
let batchStatusInterval = null;
let backgroundStatusCheckInterval = null; // For checking status when no active job

async function startBatchAnalysis() {
    const btn = document.getElementById('btn-start-batch');
    const statusDiv = document.getElementById('batch-status');
    
    if (!btn) {
        console.error('Batch analysis button not found');
        return;
    }
    
    btn.disabled = true;
    btn.textContent = 'Starting...';
    
    try {
        const response = await fetch(`${API_BASE}/batch-analyze-news`, {
            method: 'POST'
        });
        
        const result = await response.json();
        
        if (result.status === 'success') {
            // Hide button and show progress container
            const progressContainer = document.getElementById('batch-progress-container');
            if (btn) btn.style.display = 'none';
            if (progressContainer) progressContainer.style.display = 'block';
            
            // Start polling for status
            if (batchStatusInterval) {
                clearInterval(batchStatusInterval);
            }
            batchStatusInterval = setInterval(updateBatchStatus, 2000); // Poll every 2 seconds
            updateBatchStatus();
        } else {
            alert(`Error: ${result.message || 'Failed to start batch analysis'}`);
            btn.disabled = false;
            btn.textContent = '🚀 Start Batch Analysis';
        }
    } catch (error) {
        console.error('Error starting batch analysis:', error);
        alert(`Error: ${error.message}`);
        btn.disabled = false;
        btn.textContent = '🚀 Start Batch Analysis';
    }
}

async function updateBatchStatus() {
    try {
        const response = await fetch(`${API_BASE}/batch-analyze-news/status`);
        const result = await response.json();
        
        if (result.status === 'success' && result.job) {
            const job = result.job;
            const progressContainer = document.getElementById('batch-progress-container');
            const statusText = document.getElementById('batch-status-text');
            const progressText = document.getElementById('batch-progress-text');
            const progressFill = document.getElementById('batch-progress-fill');
            const totalEl = document.getElementById('batch-total');
            const processedEl = document.getElementById('batch-processed');
            const successEl = document.getElementById('batch-success');
            const failedEl = document.getElementById('batch-failed');
            const btn = document.getElementById('btn-start-batch');
            
            if (!progressContainer || !statusText || !progressText || !progressFill) {
                return;
            }
            
            // Show/hide progress container and button based on job status
            if (job.status === 'running' || job.status === 'pending') {
                // Show progress bar, hide button
                if (btn) btn.style.display = 'none';
                if (progressContainer) progressContainer.style.display = 'block';
                
                // Update status text
                const statusMessages = {
                    'pending': 'Starting...',
                    'running': 'Processing...'
                };
                statusText.textContent = statusMessages[job.status] || job.status;
                
                // Update progress
                progressText.textContent = `${job.progress_pct.toFixed(1)}%`;
                progressFill.style.width = `${job.progress_pct}%`;
                
                // Update stats
                if (totalEl) totalEl.textContent = job.total_holdings;
                if (processedEl) processedEl.textContent = job.processed_holdings;
                if (successEl) successEl.textContent = job.successful_holdings;
                if (failedEl) failedEl.textContent = job.failed_holdings;
                
                // Also reload holdings periodically during processing to show progress
                if (job.status === 'running') {
                    // Reload holdings every 5 seconds during processing to show updated statuses
                    if (!window.holdingsUpdateInterval) {
                        window.holdingsUpdateInterval = setInterval(() => {
                            allHoldings = null; // Clear cache
                            loadHoldings();
                        }, 5000);
                    }
                } else {
                    // Stop holdings updates if job is not running
                    if (window.holdingsUpdateInterval) {
                        clearInterval(window.holdingsUpdateInterval);
                        window.holdingsUpdateInterval = null;
                    }
                }
            } else {
                // Hide progress bar, show button
                if (progressContainer) progressContainer.style.display = 'none';
                if (btn) {
                    btn.style.display = 'block';
                    btn.disabled = false;
                    btn.textContent = '🚀 Start Batch Analysis';
                }
                
                if (batchStatusInterval) {
                    clearInterval(batchStatusInterval);
                    batchStatusInterval = null;
                }
                
                // Reload holdings to update status badges - force reload by clearing cache
                if (window.holdingsUpdateInterval) {
                    clearInterval(window.holdingsUpdateInterval);
                    window.holdingsUpdateInterval = null;
                }
                
                // Stop background status check
                if (backgroundStatusCheckInterval) {
                    clearInterval(backgroundStatusCheckInterval);
                    backgroundStatusCheckInterval = null;
                }
                
                // Reload holdings immediately and then again after a short delay to ensure data is fresh
                allHoldings = null; // Clear cached holdings
                loadHoldings();
                setTimeout(() => {
                    allHoldings = null; // Clear cached holdings again
                    loadHoldings();
                }, 2000);
                
                // Stop further polling - job is complete
                return; // Exit early to prevent further updates
            }
        } else if (result.status === 'no_job') {
            // No batch job running - stop all intervals
            const btn = document.getElementById('btn-start-batch');
            const progressContainer = document.getElementById('batch-progress-container');
            if (btn) {
                btn.style.display = 'block';
                btn.disabled = false;
                btn.textContent = '🚀 Start Batch Analysis';
            }
            if (progressContainer) progressContainer.style.display = 'none';
            if (batchStatusInterval) {
                clearInterval(batchStatusInterval);
                batchStatusInterval = null;
            }
            if (window.holdingsUpdateInterval) {
                clearInterval(window.holdingsUpdateInterval);
                window.holdingsUpdateInterval = null;
            }
        }
    } catch (error) {
        console.error('Error updating batch status:', error);
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    // Ensure checkbox is checked by default
    const hideZeroCheckbox = document.getElementById('filter-hide-zero');
    if (hideZeroCheckbox) {
        hideZeroCheckbox.checked = true;
        filters.hide_zero = true;
        console.log('Initialized: hide_zero filter is', filters.hide_zero);
    } else {
        console.error('filter-hide-zero checkbox not found!');
    }
    
    // Setup batch analysis button
    const btnStartBatch = document.getElementById('btn-start-batch');
    if (btnStartBatch) {
        btnStartBatch.addEventListener('click', startBatchAnalysis);
        console.log('Batch analysis button event listener added');
    } else {
        console.error('btn-start-batch button not found!');
    }
    
    // Check for existing batch job on page load
    updateBatchStatus();
    // Don't set up constant polling - only poll when batch job is active
    // The batchStatusInterval will be started when batch job starts and stopped when it completes
    
    loadStatistics();
    loadHoldings().then(() => {
        // Setup table sorting after table is loaded
        setupTableSorting();
    });
});

