let chart, currentBranch = 'main', currentTaskId = '', currentHighlightedCommit = null;

// Utility functions
function showLoading(show = true) {
    document.getElementById('loading').style.display = show ? 'block' : 'none';
}

function showNotification(message, type = 'info') {
    const notification = document.getElementById('notification');
    notification.textContent = message;
    notification.className = `alert alert-${type}`;
    notification.style.display = 'block';
    setTimeout(() => notification.style.display = 'none', 5000);
}

async function fetchWithErrorHandling(url, options = {}) {
    showLoading(true);
    try {
        const response = await fetch(url, options);
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
        }
        return await response.json();
    } catch (error) {
        console.error('Fetch error:', error);
        showNotification(`Error: ${error.message}`, 'danger');
        throw error;
    } finally {
        showLoading(false);
    }
}

// Task and Branch Management
async function loadTasks() {
    try {
        const limit = 10; // Set the limit for tasks per page
        const offset = 0; // Start with the first page
        const data = await fetchWithErrorHandling(`/api/tasks?limit=${limit}&offset=${offset}`);

        const select = document.getElementById('taskSelect');

        // Populate the dropdown with task goals and task IDs
        // Format: "Goal Description (Task ID)"
        select.innerHTML = data.tasks.map(task => `<option value="${task.id}">${task.goal} (${task.id})</option>`).join('');
        select.style.display = 'block';

        // Automatically select task based on URL parameter or default to the first task
        if (data.tasks.length > 0) {
            const urlParams = new URLSearchParams(location.search);
            const selectedTaskId = urlParams.get('task_id');
            const selectedTaskExists = data.tasks.some(task => task.id === selectedTaskId);

            if (selectedTaskId && selectedTaskExists) {
                // Select the task if specified in the query string and exists
                select.value = selectedTaskId;
                await loadTaskData(selectedTaskId);
            } else {
                // Select the first task by default
                select.value = data.tasks[0].id;
                await loadTaskData(data.tasks[0].id);
            }
        } else {
            showNotification('No tasks available.', 'warning');
            clearDetails();
        }

        // Prevent duplicate listeners by removing existing ones before adding a new listener
        select.removeEventListener('change', handleTaskChange);
        select.addEventListener('change', handleTaskChange);
    } catch (error) {
        console.error('Error loading tasks:', error);
        showNotification('Failed to load tasks.', 'danger');
    }
}

async function handleTaskChange(event) {
    const selectedTaskId = event.target.value;
    await loadTaskData(selectedTaskId);
}

async function loadTaskData(taskId) {
    currentTaskId = taskId;
    await loadBranches();
    clearDetails();
}

async function setTask() {
    const selectedTaskId = document.getElementById('taskSelect').value;
    const data = await fetchWithErrorHandling(`/set_task/${selectedTaskId}?task_id=${encodeURIComponent(selectedTaskId)}`);
    if (data.success) {
        showNotification(data.message, 'success');
        currentTaskId = selectedTaskId;
        await loadBranches();
        clearDetails();
    } else {
        showNotification(data.message, 'danger');
    }
}

async function loadBranches() {
    const data = await fetchWithErrorHandling(`/api/tasks/${encodeURIComponent(currentTaskId)}/branches`);
    updateBranchSelector(data);
    return updateChart(data.map(branch => branch.name));
}

async function setBranch() {
    const branchName = document.getElementById('branchDropdown').value;
    const data = await fetchWithErrorHandling(`/api/tasks/${encodeURIComponent(currentTaskId)}/set_branch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ branch_name: branchName })
    });
    if (data.success) {
        currentBranch = branchName;
        showNotification(data.message, 'success');
        highlightCurrentBranch();
        const branchData = await fetchWithErrorHandling(`/api/tasks/${encodeURIComponent(currentTaskId)}/branches/${encodeURIComponent(branchName)}/details`);
        updateStepList(branchData);
        if (branchData.length > 0) {
            showCommitDetailsAndHighlight(branchData[0].commit_hash);
        } else {
            clearDetails();
        }
    } else {
        showNotification(data.error, 'danger');
    }
}

// Chart Management
async function updateChart(branches) {
    const branchesData = await Promise.all(branches.map(async branch => {
        try {
            const data = await fetchWithErrorHandling(`/api/tasks/${encodeURIComponent(currentTaskId)}/branches/${encodeURIComponent(branch)}/details`);
            return data.length > 0 ? data : null;
        } catch (error) {
            console.warn(`Failed to fetch data for branch ${branch}:`, error);
            return null;
        }
    }));

    const validBranches = branches.filter((_, index) => branchesData[index] !== null);
    const validBranchesData = branchesData.filter(data => data !== null);

    const colors = ['#007bff', '#28a745', '#dc3545', '#ffc107', '#17a2b8', '#6610f2', '#fd7e14', '#20c997'];
    const pointStyles = ['circle', 'triangle', 'rect', 'rectRounded', 'rectRot', 'star', 'cross'];

    const datasets = validBranchesData.map((data, index) => {
        const sortedData = data.sort((a, b) => new Date(a.time) - new Date(b.time));
        return {
            label: `${validBranches[index]} - Program Counter`,
            data: sortedData.map(state => ({
                x: new Date(state.time),
                y: state.vm_state?.program_counter,
                commit_hash: state.commit_hash,
                branch: validBranches[index]
            })),
            borderColor: colors[index % colors.length],
            backgroundColor: `${colors[index % colors.length]}33`,
            fill: false,
            stepped: 'before',
            tension: 0,
            borderWidth: 2,
            pointRadius: 6,  
            pointHoverRadius: 10,  
            pointStyle: pointStyles[index % pointStyles.length],
        };
    });

    const allDates = datasets.flatMap(dataset => dataset.data.map(d => d.x));
    const minDate = new Date(Math.min(...allDates));
    const maxDate = new Date(Math.max(...allDates));

    minDate.setHours(minDate.getHours() - 1);
    maxDate.setHours(maxDate.getHours() + 1);

    const allProgramCounters = datasets.flatMap(dataset => dataset.data.map(d => d.y)).filter(y => y !== undefined && y !== null);
    const minPC = Math.min(...allProgramCounters);
    const maxPC = Math.max(...allProgramCounters);

    // Adjust y-axis range
    const yMin = Math.max(0, Math.floor(minPC) - 1);
    const yMax = Math.ceil(maxPC) + 1;

    const chartOptions = {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
            x: {
                type: 'time',
                time: { 
                    unit: 'hour',
                    displayFormats: { hour: 'MMM D, HH:mm' },
                    tooltipFormat: 'MMM D, YYYY, HH:mm:ss'
                },
                title: { display: true, text: 'Time' },
                grid: { color: 'rgba(0, 0, 0, 0.1)' },
                ticks: { 
                    color: '#666',
                    maxRotation: 0,
                    autoSkip: true,
                    maxTicksLimit: 12
                },
                min: minDate,
                max: maxDate
            },
            y: {
                beginAtZero: true,
                title: { display: true, text: 'Program Counter' },
                grid: { color: 'rgba(0, 0, 0, 0.1)' },
                ticks: { 
                    color: '#666',
                    stepSize: 1,
                    precision: 0
                },
                min: yMin,
                max: yMax,
                afterBuildTicks: (scale) => {
                    scale.ticks = scale.ticks.filter(tick => Number.isInteger(tick.value));
                }
            }
        },
        plugins: {
            legend: { position: 'top' },
            tooltip: { 
                mode: 'index', 
                intersect: false,
                callbacks: {
                    title: function(tooltipItems) {
                        return moment(tooltipItems[0].parsed.x).format('MMM D, YYYY, HH:mm:ss');
                    },
                    label: function(context) {
                        let label = context.dataset.label || '';
                        if (label) {
                            label += ': ';
                        }
                        if (context.parsed.y !== null) {
                            label += context.parsed.y.toFixed(0);
                        }
                        return `${label} (${context.raw.branch})`;
                    },
                    afterBody: function(tooltipItems) {
                        return `Commit: ${tooltipItems[0].raw.commit_hash}`;
                    }
                }
            }
        },
        onClick: async (event, elements) => {
            if (elements.length > 0) {
                const { index, datasetIndex } = elements[0];
                const branch = chart.data.datasets[datasetIndex].label.split(' - ')[0];
                const commitHash = chart.data.datasets[datasetIndex].data[index].commit_hash;
                currentBranch = branch;
                document.getElementById('branchDropdown').value = branch;
                try {
                    const branchData = await fetchWithErrorHandling(`/api/tasks/${encodeURIComponent(currentTaskId)}/branches/${encodeURIComponent(branch)}/details`);
                    if (branchData.length === 0) {
                        showNotification(`No VM states found for branch: ${branch}`, 'warning');
                        updateStepList([]);
                    } else {
                        updateStepList(branchData);
                        showCommitDetailsAndHighlight(commitHash);
                    }
                    showNotification(`Switched to branch: ${branch}`, 'info');
                } catch (error) {
                    console.error('Error fetching branch data:', error);
                    showNotification(`Error fetching data for branch: ${branch}`, 'danger');
                    updateStepList([]);
                }
            }
        },
    };

    if (chart) {
        chart.data.datasets = datasets;
        chart.options = chartOptions;
        chart.update();
    } else {
        const ctx = document.getElementById('executionChart').getContext('2d');
        chart = new Chart(ctx, {
            type: 'line',
            data: { datasets },
            options: chartOptions
        });
    }

    highlightCurrentBranch();
}

function highlightCurrentBranch() {
    if (chart) {
        chart.data.datasets.forEach(dataset => {
            if (dataset.label.startsWith(currentBranch)) {
                dataset.borderWidth = 6;  
                dataset.pointRadius = 4; 
                dataset.pointHoverRadius = 16; 
                dataset.zIndex = 10;  
            } else {
                dataset.borderWidth = 2;
                dataset.pointRadius = 4;
                dataset.pointHoverRadius = 10;
                dataset.zIndex = 1;
            }
        });
        chart.update();
    }
}

// Step List Management
function updateStepList(data) {
    const filteredData = data.filter(state => {
        const commitType = state.commit_type || 'General';
        return commitType === 'StepExecution';
    });

    const stepList = document.getElementById('stepList');
    if (!Array.isArray(filteredData) || filteredData.length === 0) {
        stepList.innerHTML = '<p>No steps available for this selection.</p>';
        return;
    }
    stepList.innerHTML = filteredData.map((state, index) => {
        return `
            <div class="step-item" id="step-${state.commit_hash}">
                <div>
                    <strong style="font-size: 0.9em;">${state.title}</strong>
                </div>
                <div>
                    <small class="text-muted" style="font-size: 0.85em;">
                        ${state.details?.input_parameters ?
                            `<pre>${JSON.stringify(state.details.input_parameters, null, 2)}</pre>`
                            : 'No input parameters available'}
                    </small>
                </div>
                <hr style="margin: 5px 0; border-top: 1px solid #ccc;">
                <div>
                    <small class="text-muted" style="font-size: 0.85em;">
                        ${state.details?.output_variables ?
                            `<pre>${JSON.stringify(state.details.output_variables, null, 2)}</pre>`
                            : 'No output variables available'}
                    </small>
                </div>
                <div class="mt-2">
                    <small class="text-muted" style="display: block; word-break: break-word;">
                        ${state.time ? moment(state.time).format('YYYY-MM-DD HH:mm:ss') : 'No timestamp available'}
                    </small>
                </div>
                <div class="mt-2">
                    <button onclick="executeFromStep('${state.commit_hash}', '${state.seq_no}')" class="btn btn-sm btn-outline-success" data-bs-toggle="tooltip" title="Execute from here">
                        <i class="bi bi-play-fill"></i> Execute
                    </button>
                    <button onclick="optimizeStep('${state.commit_hash}', '${state.seq_no}')" class="btn btn-sm btn-outline-primary" data-bs-toggle="tooltip" title="Update this step">
                        <i class="bi bi-pencil-fill"></i> Optimize Step
                    </button>
                </div>
                <div class="mt-2">
                    <small>SeqNo:[${state.seq_no || 'N/A'}], PC:[${state.vm_state?.program_counter || 'N/A'}]</small>
                    ${state.vm_state?.goal_completed ? '<span class="badge bg-success ms-2">Completed</span>' : ''}
                </div>
            </div>
        `;
    }).join('');

    stepList.querySelectorAll('.step-item').forEach(item => {
        item.addEventListener('click', event => {
            if (!event.target.closest('.btn')) {
                showCommitDetailsAndHighlight(item.id.split('-')[1]);
            }
        });
    });

    initTooltips();
}

// Commit Details and Highlighting
async function showCommitDetailsAndHighlight(commitHash) {
    currentHighlightedCommit = commitHash;
    highlightChartPoint(commitHash);
    highlightStep(commitHash);
    
    try {
        const [vmState, codeDiff] = await Promise.all([
            fetchWithErrorHandling(`/api/tasks/${encodeURIComponent(currentTaskId)}/commits/${encodeURIComponent(commitHash)}/detail`),
            fetchWithErrorHandling(`/api/tasks/${encodeURIComponent(currentTaskId)}/commits/${encodeURIComponent(commitHash)}/diff`)
        ]);

        updateCommitDetails(vmState);
        updateVMState(vmState.vm_state);
        updateCodeDiff(codeDiff.diff);
        updateVMVariables(vmState.vm_state);

        hljs.highlightAll();
    } catch (error) {
        console.error('Error fetching details:', error);
        showNotification('Error fetching commit details: ' + error.message, 'danger');
        clearDetails();
    }
}

function updateCommitDetails(commitDetails) {
    document.getElementById('commitDetails').innerHTML = `
        <h2>Commit Details</h2>
        <p><strong>Branch:</strong> ${currentBranch}</p>
        <p><strong>Hash:</strong> ${commitDetails.commit_hash}</p>
        <p><strong>Date:</strong> ${moment(commitDetails.time).format('YYYY-MM-DD HH:mm:ss')}</p>
        <p><strong>Message:</strong> ${commitDetails.message}</p>
        <p><strong>Commit Type:</strong> ${commitDetails.commit_type}</p>
    `;
}

function updateVMState(vmState) {
    document.getElementById('vmState').innerHTML = `
        <h2>VM State</h2>
        <pre><code class="json">${JSON.stringify(vmState, null, 2)}</code></pre>
    `;
}

function updateCodeDiff(codeDiff) {
    document.getElementById('codeDiff').innerHTML = `
        <h2>Code Diff</h2>
        <pre><code class="diff">${codeDiff}</code></pre>
    `;
}

function updateVMStateDetails(vmStateDetails, commitHash) {
    document.getElementById('vmVariables').innerHTML = `
        <h2>VM Variables</h2>
        <pre><code class="json">${JSON.stringify(vmStateDetails.variables || {}, null, 2)}</code></pre>
    `;
}

function highlightStep(commitHash) {
    document.querySelectorAll('.step-item').forEach(item => item.classList.remove('highlighted-step'));
    const stepItem = document.getElementById(`step-${commitHash}`);
    if (stepItem) {
        stepItem.classList.add('highlighted-step');
        stepItem.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
}

function highlightChartPoint(commitHash, updateCurrentHighlight = true) {
    if (chart) {
        let foundPoint = false;
        chart.data.datasets.forEach((dataset, datasetIndex) => {
            const pointIndex = dataset.data.findIndex(point => point.commit_hash === commitHash);
            if (pointIndex !== -1) {
                foundPoint = true;
                chart.setActiveElements([{ datasetIndex, index: pointIndex }]);
                chart.update();
                
                currentBranch = dataset.label.split(' - ')[0];
            }
        });

        if (foundPoint && updateCurrentHighlight) {
            currentHighlightedCommit = commitHash;
        } else if (!foundPoint && updateCurrentHighlight) {
            console.warn(`No point found for commit hash: ${commitHash}`);
            currentHighlightedCommit = null;
        }
    }
}

async function executeFromStep(commitHash, seqNo) {
    // Create a modal dialog for user input
    const modal = document.createElement('div');
    modal.style.position = 'fixed';
    modal.style.left = '50%';
    modal.style.top = '50%';
    modal.style.transform = 'translate(-50%, -50%)';
    modal.style.backgroundColor = 'white';
    modal.style.padding = '20px';
    modal.style.boxShadow = '0 0 10px rgba(0, 0, 0, 0.5)';
    modal.style.zIndex = '1000';

    const commitInfo = document.createElement('p');
    commitInfo.textContent = `Commit Hash: ${commitHash}, Sequence No: ${seqNo}`;
    modal.appendChild(commitInfo);

    const suggestionLabel = document.createElement('label');
    suggestionLabel.textContent = 'Enter your suggestion:';
    modal.appendChild(suggestionLabel);

    const suggestionInput = document.createElement('textarea');
    suggestionInput.style.width = '100%';
    suggestionInput.style.height = '100px';
    modal.appendChild(suggestionInput);

    const submitButton = document.createElement('button');
    submitButton.textContent = 'Submit';
    submitButton.onclick = async function() {
        const suggestion = suggestionInput.value;
        if (!suggestion) {
            alert("Please enter a suggestion.");
            return;
        }

        // Disable the input and buttons
        suggestionInput.disabled = true;
        submitButton.disabled = true;
        cancelButton.disabled = true;

        // Create and show a loading spinner
        const spinner = document.createElement('div');
        spinner.className = 'spinner';
        spinner.style.border = '4px solid #f3f3f3';
        spinner.style.borderTop = '4px solid #3498db';
        spinner.style.borderRadius = '50%';
        spinner.style.width = '30px';
        spinner.style.height = '30px';
        spinner.style.animation = 'spin 1s linear infinite';
        spinner.style.margin = '10px auto';
        modal.appendChild(spinner);

        try {
            const executeData = await fetchWithErrorHandling(`/api/tasks/${encodeURIComponent(currentTaskId)}/dynamic_update`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    commit_hash: commitHash,
                    suggestion: suggestion
                })
            });

            if (executeData.success) {
                await updateUIAfterExecution(executeData.branch_name);
                showNotification('Execution completed successfully', 'success');
            } else {
                showNotification('Execution failed: ' + (executeData.error || 'Unknown error'), 'danger');
            }
        } catch (error) {
            console.error('Error in executeFromStep:', error);
            showNotification('An error occurred: ' + error.message, 'danger');
        } finally {
            showLoading(false);
            // Remove the spinner
            modal.removeChild(spinner);
            document.body.removeChild(modal);
        }
    };
    modal.appendChild(submitButton);

    const cancelButton = document.createElement('button');
    cancelButton.textContent = 'Cancel';
    cancelButton.onclick = function() {
        document.body.removeChild(modal);
    };
    modal.appendChild(cancelButton);

    document.body.appendChild(modal);
}

async function updateUIAfterExecution(newBranch) {
    currentBranch = newBranch;
    await loadBranches();
    highlightCurrentBranch();
    
    try {
        const branchData = await fetchWithErrorHandling(`/api/tasks/${encodeURIComponent(currentTaskId)}/branches/${encodeURIComponent(newBranch)}/details`);
        
        if (branchData.length === 0) {
            showNotification(`No VM states found for branch: ${newBranch}`, 'warning');
            updateStepList([]);
        } else {
            updateStepList(branchData);
            
            // Automatically highlight the latest commit
            const latestCommit = branchData[branchData.length - 1].commit_hash;
            showCommitDetailsAndHighlight(latestCommit);
        }
    } catch (error) {
        console.error('Error fetching branch data:', error);
        showNotification(`Error fetching data for branch: ${newBranch}`, 'danger');
        updateStepList([]);
    }
}

function clearDetails() {
    ['commitDetails', 'vmState', 'codeDiff', 'vmVariables'].forEach(id => {
        document.getElementById(id).innerHTML = `<h2>No ${id.replace('Details', '').replace('vm', 'VM')} Available</h2>`;
    });
}

function initTooltips() {
    [...document.querySelectorAll('[data-bs-toggle="tooltip"]')].map(el => new bootstrap.Tooltip(el));
}

function updateBranchSelector(branches) {
    const select = document.getElementById('branchDropdown');
    select.innerHTML = branches.map(branch => `
        <option value="${branch.name}" ${branch.is_active ? 'selected' : ''}>
            ${branch.name} (${new Date(branch.last_commit_date).toLocaleString()})
        </option>
    `).join('');
    document.getElementById('branchSelect').style.display = 'block';
    currentBranch = branches.find(branch => branch.is_active)?.name || branches[0]?.name;
}

async function deleteBranch() {
    const branchName = document.getElementById('branchDropdown').value;
    if (!confirm(`Are you sure you want to delete branch "${branchName}"?`)) {
        return;
    }
    
    try {
        const data = await fetchWithErrorHandling(`/api/tasks/${encodeURIComponent(currentTaskId)}/branches/${encodeURIComponent(branchName)}`, {
            method: 'DELETE'
        });
        
        if (data.success) {
            showNotification(data.message, 'success');
            await updateBranchesAndChart();
        } else {
            showNotification(`Error: ${data.error}`, 'danger');
        }
    } catch (error) {
        showNotification(`Error deleting branch: ${error.message}`, 'danger');
    }
}

async function updateBranchesAndChart() {
    const branches = await fetchWithErrorHandling(`/api/tasks/${encodeURIComponent(currentTaskId)}/branches`);
    updateBranchSelector(branches);
    await updateChart(branches.map(branch => branch.name));
}

document.getElementById('stepSearch').addEventListener('input', e => {
    const searchTerm = e.target.value.toLowerCase();
    document.querySelectorAll('.step-item').forEach(item => {
        item.style.display = item.textContent.toLowerCase().includes(searchTerm) ? '' : 'none';
    });
});

async function optimizeStep(commitHash, seqNo) {
    // Create a modal dialog for user input
    const modal = document.createElement('div');
    modal.style.position = 'fixed';
    modal.style.left = '50%';
    modal.style.top = '50%';
    modal.style.transform = 'translate(-50%, -50%)';
    modal.style.backgroundColor = 'white';
    modal.style.padding = '20px';
    modal.style.boxShadow = '0 0 10px rgba(0, 0, 0, 0.5)';
    modal.style.zIndex = '1000';

    const commitInfo = document.createElement('p');
    commitInfo.textContent = `Commit Hash: ${commitHash}, Sequence No: ${seqNo}`;
    modal.appendChild(commitInfo);

    const suggestionLabel = document.createElement('label');
    suggestionLabel.textContent = 'Enter your suggestion:';
    modal.appendChild(suggestionLabel);

    const suggestionInput = document.createElement('textarea');
    suggestionInput.style.width = '100%';
    suggestionInput.style.height = '100px';
    modal.appendChild(suggestionInput);

    const submitButton = document.createElement('button');
    submitButton.textContent = 'Submit';
    submitButton.onclick = async function() {
        const suggestion = suggestionInput.value;
        if (!suggestion) {
            alert("Please enter a suggestion.");
            return;
        }

        // Disable the input and buttons
        suggestionInput.disabled = true;
        submitButton.disabled = true;
        cancelButton.disabled = true;

        // Create and show a loading spinner
        const spinner = document.createElement('div');
        spinner.className = 'spinner';
        spinner.style.border = '4px solid #f3f3f3';
        spinner.style.borderTop = '4px solid #3498db';
        spinner.style.borderRadius = '50%';
        spinner.style.width = '30px';
        spinner.style.height = '30px';
        spinner.style.animation = 'spin 1s linear infinite';
        spinner.style.margin = '10px auto';
        modal.appendChild(spinner);

        try {
            const executeData = await fetchWithErrorHandling(`/api/tasks/${encodeURIComponent(currentTaskId)}/optimize_step`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    commit_hash: commitHash,
                    suggestion: suggestion,
                    seq_no: seqNo
                })
            });

            if (executeData.success) {
                await updateUIAfterExecution(executeData.current_branch);
                showNotification('Execution completed successfully', 'success');
            } else {
                showNotification('Execution failed: ' + (executeData.error || 'Unknown error'), 'danger');
            }
        } catch (error) {
            showNotification('An error occurred: ' + error.message, 'danger');
        } finally {
            document.body.removeChild(modal);
        }
    };
    modal.appendChild(submitButton);

    const cancelButton = document.createElement('button');
    cancelButton.textContent = 'Cancel';
    cancelButton.onclick = function() {
        document.body.removeChild(modal);
    };
    modal.appendChild(cancelButton);

    document.body.appendChild(modal);
}

// Existing loadTasks call and other initializations
loadTasks();
window.addEventListener('resize', () => { if (chart) chart.resize(); });

function updateVMVariables(vmState) {
    const vmVariablesElement = document.getElementById('vmVariables');
    if (vmState && vmState.variables) {
        vmVariablesElement.innerHTML = `
            <h2>VM Variables</h2>
            <pre><code class="json">${JSON.stringify(vmState.variables, null, 2)}</code></pre>
        `;

        const finalAnswer = vmState.variables.final_answer;
        console.log('Final Answer:', finalAnswer);

        const goal = vmState ? vmState.goal : undefined;
        console.log('Goal:', goal);

        const finalAnswerElement = document.getElementById('finalAnswerContent');
        const goalElement = document.getElementById('goalContent');

        if (finalAnswerElement) {
            if (finalAnswer) {
                const converter = new showdown.Converter();
                finalAnswerElement.innerHTML = converter.makeHtml(finalAnswer);
            } else {
                finalAnswerElement.innerHTML = 'No final answer available.';
            }
        } else {
            console.error('Final Answer element not found!');
        }

        if (goalElement) {
            if (goal) {
                const converter = new showdown.Converter();
                goalElement.innerHTML = converter.makeHtml(goal);
            } else {
                goalElement.innerHTML = 'No goal available.';
            }
        } else {
            console.error('Goal element not found!');
        }
    } else {
        vmVariablesElement.innerHTML = '<p>No VM variables available.</p>';
    }
}
