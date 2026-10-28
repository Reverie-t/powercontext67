// 科研周报助手前端逻辑

const API_BASE = '';

const state = {
    projects: [],
    recordProjectId: null,
    reportProjectId: null,
    memoryProjectId: null,
    currentReportId: null,
    selectListenersBound: false,
};

document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    initProjectForm();
    initRecordForm();
    initReportForm();
    initReportViewer();
    initMemoryPanel();
    loadProjects();
});

// --- Global alerts ---

function showError(msg) {
    const el = document.getElementById('global-error');
    el.textContent = msg;
    el.classList.remove('hidden');
    setTimeout(() => el.classList.add('hidden'), 8000);
}

function showInfo(msg) {
    const el = document.getElementById('global-info');
    el.textContent = msg;
    el.classList.remove('hidden');
    setTimeout(() => el.classList.add('hidden'), 4000);
}

function clearAlerts() {
    document.getElementById('global-error').classList.add('hidden');
    document.getElementById('global-info').classList.add('hidden');
}

// --- Tab switching ---

function initTabs() {
    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
            document.getElementById(`${tab.dataset.tab}-panel`).classList.add('active');
        });
    });
}

// --- API helper ---

async function apiFetch(url, options = {}) {
    const response = await fetch(`${API_BASE}${url}`, {
        headers: { 'Content-Type': 'application/json' },
        ...options,
    });
    if (!response.ok) {
        let detail = `请求失败 (${response.status})`;
        try {
            const body = await response.json();
            detail = body.detail || detail;
        } catch (_) {}
        throw new Error(detail);
    }
    return response.json();
}

// --- Project management ---

function initProjectForm() {
    const newBtn = document.getElementById('new-project-btn');
    const form = document.getElementById('new-project-form');
    const cancelBtn = document.getElementById('cancel-project-btn');
    const formEl = document.getElementById('project-form');

    newBtn.addEventListener('click', () => {
        form.classList.remove('hidden');
        newBtn.classList.add('hidden');
    });

    cancelBtn.addEventListener('click', () => {
        form.classList.add('hidden');
        newBtn.classList.remove('hidden');
        formEl.reset();
    });

    formEl.addEventListener('submit', async (e) => {
        e.preventDefault();
        clearAlerts();
        const data = {
            name: document.getElementById('project-name').value.trim(),
            direction: document.getElementById('project-direction').value.trim(),
            preferences: document.getElementById('project-preferences').value.trim(),
        };
        try {
            await apiFetch('/api/projects', {
                method: 'POST',
                body: JSON.stringify(data),
            });
            form.classList.add('hidden');
            newBtn.classList.remove('hidden');
            formEl.reset();
            await loadProjects();
            showInfo('项目创建成功');
        } catch (err) {
            showError('创建项目失败：' + err.message);
        }
    });
}

async function loadProjects() {
    try {
        const data = await apiFetch('/api/projects');
        state.projects = data.projects;

        renderProjectCards();
        updateProjectSelects();
    } catch (err) {
        console.error('加载项目失败：', err);
        showError('加载项目失败：' + err.message);
    }
}

function renderProjectCards() {
    const list = document.getElementById('projects-list');
    if (state.projects.length === 0) {
        list.innerHTML = '<div class="empty-state"><p>暂无研究项目</p><p>点击"新建项目"开始</p></div>';
        return;
    }
    list.innerHTML = state.projects.map(p => `
        <div class="card" data-project-id="${escapeAttr(p.id)}">
            <h3>${escapeHtml(p.name)}</h3>
            <div class="meta">创建于 ${formatDate(p.created_at)}</div>
            <div class="description"><strong>方向：</strong>${escapeHtml(p.direction)}</div>
            <div class="description"><strong>偏好：</strong>${escapeHtml(p.preferences)}</div>
            <div class="card-actions">
                <button class="btn btn-sm" type="button" onclick="selectProjectForRecords('${escapeAttr(p.id)}')">记录</button>
                <button class="btn btn-sm" type="button" onclick="selectProjectForReports('${escapeAttr(p.id)}')">周报</button>
                <button class="btn btn-sm" type="button" onclick="selectProjectForMemory('${escapeAttr(p.id)}')">记忆</button>
            </div>
        </div>
    `).join('');
}

function updateProjectSelects() {
    const options = '<option value="">-- 请选择项目 --</option>' +
        state.projects.map(p => `<option value="${escapeAttr(p.id)}">${escapeHtml(p.name)}</option>`).join('');

    const recordSelect = document.getElementById('record-project-select');
    const reportSelect = document.getElementById('report-project-select');
    const memorySelect = document.getElementById('memory-project-select');

    const prevRecord = state.recordProjectId;
    const prevReport = state.reportProjectId;
    const prevMemory = state.memoryProjectId;

    recordSelect.innerHTML = options;
    reportSelect.innerHTML = options;
    memorySelect.innerHTML = options;

    if (prevRecord) recordSelect.value = prevRecord;
    if (prevReport) reportSelect.value = prevReport;
    if (prevMemory) memorySelect.value = prevMemory;

    if (!state.selectListenersBound) {
        state.selectListenersBound = true;

        recordSelect.addEventListener('change', () => {
            state.recordProjectId = recordSelect.value || null;
            document.getElementById('new-record-btn').disabled = !state.recordProjectId;
            if (state.recordProjectId) loadRecords();
            else document.getElementById('records-list').innerHTML = '';
        });

        reportSelect.addEventListener('change', () => {
            state.reportProjectId = reportSelect.value || null;
            document.getElementById('generate-report-btn').disabled = !state.reportProjectId;
            if (state.reportProjectId) loadReports();
            else document.getElementById('reports-list').innerHTML = '';
        });

        memorySelect.addEventListener('change', () => {
            state.memoryProjectId = memorySelect.value || null;
            document.getElementById('refresh-memory-btn').disabled = !state.memoryProjectId;
            if (state.memoryProjectId) loadMemory();
            else document.getElementById('memory-list').innerHTML = '';
        });
    }
}

function switchToTab(tabName) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    document.getElementById(`${tabName}-panel`).classList.add('active');
}

function selectProjectForRecords(projectId) {
    state.recordProjectId = projectId;
    document.getElementById('record-project-select').value = projectId;
    document.getElementById('new-record-btn').disabled = false;
    switchToTab('records');
    loadRecords();
}

function selectProjectForReports(projectId) {
    state.reportProjectId = projectId;
    document.getElementById('report-project-select').value = projectId;
    document.getElementById('generate-report-btn').disabled = false;
    switchToTab('reports');
    loadReports();
}

function selectProjectForMemory(projectId) {
    state.memoryProjectId = projectId;
    document.getElementById('memory-project-select').value = projectId;
    document.getElementById('refresh-memory-btn').disabled = false;
    switchToTab('memory');
    loadMemory();
}

// --- Record management ---

function initRecordForm() {
    const newBtn = document.getElementById('new-record-btn');
    const form = document.getElementById('new-record-form');
    const cancelBtn = document.getElementById('cancel-record-btn');
    const formEl = document.getElementById('record-form');

    newBtn.addEventListener('click', () => {
        form.classList.remove('hidden');
        newBtn.classList.add('hidden');
        document.getElementById('record-date').value = localToday();
    });

    cancelBtn.addEventListener('click', () => {
        form.classList.add('hidden');
        newBtn.classList.remove('hidden');
        formEl.reset();
    });

    formEl.addEventListener('submit', async (e) => {
        e.preventDefault();
        clearAlerts();
        const data = {
            project_id: state.recordProjectId,
            date: document.getElementById('record-date').value,
            record_type: document.getElementById('record-type').value,
            content: document.getElementById('record-content').value.trim(),
        };
        try {
            await apiFetch('/api/records', {
                method: 'POST',
                body: JSON.stringify(data),
            });
            form.classList.add('hidden');
            newBtn.classList.remove('hidden');
            formEl.reset();
            await loadRecords();
            showInfo('记录添加成功');
        } catch (err) {
            showError('添加记录失败：' + err.message);
        }
    });
}

async function loadRecords() {
    if (!state.recordProjectId) return;
    try {
        const data = await apiFetch(`/api/projects/${state.recordProjectId}/records`);
        renderRecords(data.records);
    } catch (err) {
        console.error('加载记录失败：', err);
        showError('加载记录失败：' + err.message);
    }
}

function renderRecords(records) {
    const list = document.getElementById('records-list');
    if (records.length === 0) {
        list.innerHTML = '<div class="empty-state"><p>暂无研究记录</p><p>点击"添加记录"开始</p></div>';
        return;
    }
    const typeLabels = {
        experiment: '实验',
        literature: '文献',
        issue: '问题',
        plan: '计划',
    };
    list.innerHTML = records.map(r => {
        const citation = r.memory_artifact_id
            ? `${r.id} / ${r.memory_artifact_id}`
            : r.id;
        return `
        <div class="record-item">
            <div class="record-date">${escapeHtml(r.date)}</div>
            <div class="record-content">
                <span class="record-type ${escapeAttr(r.record_type)}">${typeLabels[r.record_type] || r.record_type}</span>
                <div>${escapeHtml(r.content)}</div>
                <div class="record-citation">${escapeHtml(citation)}</div>
            </div>
        </div>
    `;
    }).join('');
}

// --- Report management ---

function initReportForm() {
    const newBtn = document.getElementById('generate-report-btn');
    const form = document.getElementById('generate-report-form');
    const cancelBtn = document.getElementById('cancel-report-btn');
    const formEl = document.getElementById('report-form');

    newBtn.addEventListener('click', () => {
        form.classList.remove('hidden');
        newBtn.classList.add('hidden');
    });

    cancelBtn.addEventListener('click', () => {
        form.classList.add('hidden');
        newBtn.classList.remove('hidden');
        formEl.reset();
    });

    formEl.addEventListener('submit', async (e) => {
        e.preventDefault();
        clearAlerts();
        const data = {
            project_id: state.reportProjectId,
            week_start: document.getElementById('week-start').value,
            week_end: document.getElementById('week-end').value,
        };
        try {
            const result = await apiFetch('/api/reports/generate', {
                method: 'POST',
                body: JSON.stringify(data),
            });
            form.classList.add('hidden');
            newBtn.classList.remove('hidden');
            formEl.reset();
            await loadReports();
            await viewReport(result.report.id);
            showInfo('周报生成成功');
        } catch (err) {
            showError('生成周报失败：' + err.message);
        }
    });
}

async function loadReports() {
    if (!state.reportProjectId) return;
    try {
        const data = await apiFetch(`/api/projects/${state.reportProjectId}/reports`);
        renderReports(data.reports);
    } catch (err) {
        console.error('加载周报失败：', err);
        showError('加载周报失败：' + err.message);
    }
}

function renderReports(reports) {
    const list = document.getElementById('reports-list');
    if (reports.length === 0) {
        list.innerHTML = '<div class="empty-state"><p>暂无周报</p><p>点击"生成周报"开始</p></div>';
        return;
    }
    list.innerHTML = reports.map(r => `
        <div class="report-item">
            <div class="report-header">
                <div class="report-title">${escapeHtml(r.week_start)} 至 ${escapeHtml(r.week_end)}</div>
            </div>
            <div class="report-meta">生成于 ${formatDate(r.generated_at)}</div>
            <div class="report-actions">
                <button class="btn btn-sm" type="button" onclick="viewReport('${escapeAttr(r.id)}')">查看</button>
            </div>
        </div>
    `).join('');
}

function initReportViewer() {
    document.getElementById('close-viewer-btn').addEventListener('click', () => {
        document.getElementById('report-viewer').classList.add('hidden');
        state.currentReportId = null;
    });

    document.getElementById('edit-report-btn').addEventListener('click', () => {
        const preview = document.getElementById('report-preview');
        const editor = document.getElementById('report-editor');
        const editBtn = document.getElementById('edit-report-btn');
        const saveBtn = document.getElementById('save-report-btn');

        if (editor.classList.contains('hidden')) {
            editor.value = preview.dataset.rawMarkdown || '';
            editor.classList.remove('hidden');
            preview.classList.add('hidden');
            editBtn.textContent = '取消编辑';
            saveBtn.disabled = false;
        } else {
            editor.classList.add('hidden');
            preview.classList.remove('hidden');
            editBtn.textContent = '编辑';
            saveBtn.disabled = true;
        }
    });

    document.getElementById('save-report-btn').addEventListener('click', async () => {
        if (!state.currentReportId) return;
        const editor = document.getElementById('report-editor');
        clearAlerts();
        try {
            await saveReport(state.currentReportId, editor.value);
        } catch (err) {
            showError('保存失败：' + err.message);
        }
    });

    document.getElementById('export-report-btn').addEventListener('click', () => {
        const preview = document.getElementById('report-preview');
        const markdown = preview.dataset.rawMarkdown || '';
        const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `周报-${state.currentReportId}.md`;
        a.click();
        URL.revokeObjectURL(url);
    });
}

async function viewReport(reportId) {
    try {
        const data = await apiFetch(`/api/reports/${reportId}`);
        const report = data.report;

        state.currentReportId = reportId;
        const viewer = document.getElementById('report-viewer');
        const preview = document.getElementById('report-preview');
        const editor = document.getElementById('report-editor');

        document.getElementById('report-title').textContent =
            `${report.week_start} 至 ${report.week_end} 周报`;

        preview.dataset.rawMarkdown = report.markdown;
        preview.innerHTML = renderMarkdown(report.markdown);
        preview.classList.remove('hidden');
        editor.classList.add('hidden');
        document.getElementById('edit-report-btn').textContent = '编辑';
        document.getElementById('save-report-btn').disabled = true;

        viewer.classList.remove('hidden');
        viewer.scrollIntoView({ behavior: 'smooth' });
    } catch (err) {
        console.error('加载周报失败：', err);
        showError('加载周报失败：' + err.message);
    }
}

async function saveReport(reportId, markdown) {
    await apiFetch(`/api/reports/${reportId}`, {
        method: 'PUT',
        body: JSON.stringify({ markdown }),
    });

    const preview = document.getElementById('report-preview');
    const editor = document.getElementById('report-editor');

    preview.dataset.rawMarkdown = markdown;
    preview.innerHTML = renderMarkdown(markdown);
    preview.classList.remove('hidden');
    editor.classList.add('hidden');
    document.getElementById('edit-report-btn').textContent = '编辑';
    document.getElementById('save-report-btn').disabled = true;

    showInfo('保存成功');
    if (state.reportProjectId) await loadReports();
}

// --- Memory evidence ---

function initMemoryPanel() {
    document.getElementById('refresh-memory-btn').addEventListener('click', loadMemory);
}

async function loadMemory() {
    if (!state.memoryProjectId) return;
    clearAlerts();
    try {
        const data = await apiFetch(`/api/projects/${state.memoryProjectId}/memory`);
        renderMemoryList(data.memories);
    } catch (err) {
        console.error('加载记忆失败：', err);
        showError('加载记忆失败：' + err.message);
    }
}

const kindLabels = {
    preference: '偏好',
    observation: '实验',
    reference: '文献',
    constraint: '问题',
    decision: '待办',
    'completed-task': '已完成',
};

function renderMemoryList(memories) {
    const list = document.getElementById('memory-list');
    if (!memories || memories.length === 0) {
        list.innerHTML = '<div class="empty-state"><p>暂无记忆数据</p></div>';
        return;
    }
    list.innerHTML = memories.map(m => {
        const kindClass = escapeAttr(m.kind);
        const label = kindLabels[m.kind] || m.kind;
        const isDecision = m.kind === 'decision' && m.state === 'active';
        const isPreference = m.kind === 'preference' && m.state === 'active';

        let actions = '';
        if (isDecision) {
            actions = `<button class="btn btn-sm btn-success" type="button"
                onclick="completeTask('${escapeAttr(m.artifact_id)}', ${m.revision})">标记完成</button>`;
        }
        if (isPreference) {
            actions = `<button class="btn btn-sm btn-warning" type="button"
                onclick="showEditPreference('${escapeAttr(m.artifact_id)}', ${m.revision}, this)">编辑偏好</button>`;
        }

        return `
        <div class="memory-item" id="memory-${escapeAttr(m.artifact_id)}">
            <div class="memory-header">
                <div class="memory-header-left">
                    <span class="memory-kind ${kindClass}">${escapeHtml(label)}</span>
                    <span class="memory-state ${escapeAttr(m.state)}">${escapeHtml(m.state)}</span>
                </div>
            </div>
            <div class="memory-text">${escapeHtml(m.text)}</div>
            <div class="memory-meta">
                artifact: ${escapeHtml(m.artifact_id)} &middot;
                rev ${m.revision} &middot;
                state_version ${m.state_version}
            </div>
            ${actions ? `<div class="memory-actions">${actions}</div>` : ''}
        </div>
    `;
    }).join('');
}

async function completeTask(artifactId, revision) {
    clearAlerts();
    try {
        await apiFetch('/api/tasks/complete', {
            method: 'POST',
            body: JSON.stringify({
                project_id: state.memoryProjectId,
                artifact_id: artifactId,
                revision: revision,
                reason: '用户标记任务完成',
            }),
        });
        showInfo('任务已标记为完成');
        await loadMemory();
    } catch (err) {
        showError('标记完成失败：' + err.message);
    }
}

function showEditPreference(artifactId, revision, btnEl) {
    const memoryItem = document.getElementById(`memory-${artifactId}`);
    const existing = memoryItem.querySelector('.memory-edit-form');
    if (existing) {
        existing.remove();
        btnEl.textContent = '编辑偏好';
        return;
    }

    const memory = state.projects.length > 0 && memoryItem
        ? null : null;
    const currentText = memoryItem.querySelector('.memory-text').textContent;

    const formDiv = document.createElement('div');
    formDiv.className = 'memory-edit-form';
    formDiv.innerHTML = `
        <textarea aria-label="编辑偏好内容">${escapeHtml(currentText)}</textarea>
        <div class="form-actions">
            <button class="btn btn-sm btn-primary" type="button"
                onclick="savePreference('${escapeAttr(artifactId)}', ${revision})">保存</button>
            <button class="btn btn-sm" type="button"
                onclick="this.closest('.memory-edit-form').remove(); document.querySelector('#memory-${escapeAttr(artifactId)} .btn-warning').textContent='编辑偏好'">取消</button>
        </div>
    `;
    memoryItem.appendChild(formDiv);
    formDiv.querySelector('textarea').focus();
    btnEl.textContent = '收起';
}

async function savePreference(artifactId, revision) {
    clearAlerts();
    const memoryItem = document.getElementById(`memory-${artifactId}`);
    const textarea = memoryItem.querySelector('.memory-edit-form textarea');
    const newText = textarea.value.trim();
    if (!newText) {
        showError('偏好内容不能为空');
        return;
    }
    try {
        await apiFetch('/api/preferences', {
            method: 'PUT',
            body: JSON.stringify({
                project_id: state.memoryProjectId,
                artifact_id: artifactId,
                revision: revision,
                new_text: newText,
                reason: '用户通过界面更新偏好',
            }),
        });
        showInfo('偏好已更新');
        await loadMemory();
        await loadProjects();
    } catch (err) {
        showError('更新偏好失败：' + err.message);
    }
}

// --- Utility functions ---

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function escapeAttr(text) {
    return String(text).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function formatDate(dateStr) {
    const d = new Date(dateStr);
    return d.toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
    });
}

function localToday() {
    const d = new Date();
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

function renderMarkdown(md) {
    let html = escapeHtml(md);

    html = html.replace(/^### (.*$)/gim, '<h3>$1</h3>');
    html = html.replace(/^## (.*$)/gim, '<h2>$1</h2>');
    html = html.replace(/^# (.*$)/gim, '<h1>$1</h1>');

    html = html.replace(/\*\*(.*)\*\*/gim, '<strong>$1</strong>');
    html = html.replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/gim, '<em>$1</em>');

    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

    html = html.replace(/^- (.*$)/gim, '<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>\n?)+/gim, '<ul>$&</ul>');

    html = html.replace(/\n\n/g, '</p><p>');
    html = '<p>' + html + '</p>';

    html = html.replace(/<p><h/g, '<h');
    html = html.replace(/<\/h([1-6])><\/p>/g, '</h$1>');
    html = html.replace(/<p><ul>/g, '<ul>');
    html = html.replace(/<\/ul><\/p>/g, '</ul>');

    return html;
}
