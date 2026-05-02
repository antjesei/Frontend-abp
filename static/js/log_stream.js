function startLogStream(toolId) {
    const logEl = document.getElementById('log-output');
    if (!logEl) return;
    const es = new EventSource(`/tool/${toolId}/logs/stream`);
    es.onmessage = (e) => {
        logEl.textContent += e.data + '\n';
        logEl.scrollTop = logEl.scrollHeight;
    };
    es.addEventListener('end', () => es.close());
    es.onerror = () => es.close();
}

function startInstallStream(toolId) {
    const logEl = document.getElementById('install-output');
    if (!logEl) return;
    logEl.textContent = '';
    const btn = document.getElementById('install-btn');
    if (btn) btn.disabled = true;

    const es = new EventSource(`/tool/${toolId}/venv/install/stream`);
    es.onmessage = (e) => {
        logEl.textContent += e.data + '\n';
        logEl.scrollTop = logEl.scrollHeight;
    };
    es.addEventListener('end', () => {
        es.close();
        if (btn) btn.disabled = false;
    });
    es.onerror = () => {
        es.close();
        if (btn) btn.disabled = false;
    };
}

// Tab switching
function showTab(tabName) {
    document.querySelectorAll('.tab-content').forEach(el => {
        el.classList.remove('active');
    });
    document.querySelectorAll('.tab-link').forEach(el => {
        el.classList.remove('active');
    });
    const content = document.getElementById('tab-' + tabName);
    if (content) content.classList.add('active');
    const link = document.querySelector('[data-tab="' + tabName + '"]');
    if (link) link.classList.add('active');

    // Start log stream when logs tab is shown
    if (tabName === 'logs') {
        const toolIdEl = document.getElementById('tool-id');
        if (toolIdEl) startLogStream(toolIdEl.value);
    }
}

// Initialize first tab on page load
document.addEventListener('DOMContentLoaded', () => {
    const firstTab = document.querySelector('.tab-link');
    if (firstTab) {
        const tabName = firstTab.getAttribute('data-tab');
        if (tabName) showTab(tabName);
    }
});
