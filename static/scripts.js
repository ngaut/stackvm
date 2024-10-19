let chart, currentBranch = 'main', currentRepo = '', currentHighlightedCommit = null;

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

// Repository and Branch Management
async function loadDirectories() {
    const data = await fetchWithErrorHandling('/get_directories');
    const select = document.getElementById('directorySelect');
    select.innerHTML = data.map(dir => `<option value="${dir}">${dir}</option>`).join('');
    select.style.display = 'block';
    document.getElementById('setRepoButton').style.display = 'block';

    // Automatically select the first directory and set the repository
    if (data.length > 0) {
        select.value = data[0];
        await setRepo();
    }
}

async function setRepo() {
    const selectedRepo = document.getElementById('directorySelect').value;
    const data = await fetchWithErrorHandling(`/set_repo/${selectedRepo}?repo=${encodeURIComponent(selectedRepo)}`);
    if (data.success) {
        showNotification(data.message, 'success');
        currentRepo = selectedRepo;
        await loadBranches();
        clearDetails();
        // Show Save Plan Button after setting repository
        document.getElementById('savePlanButton').style.display = 'inline-block';
    } else {
        showNotification(data.message, 'danger');
    }
}

async function loadBranches() {
    const data = await fetchWithErrorHandling(`/get_branches?repo=${encodeURIComponent(currentRepo)}`);
    updateBranchSelector(data);
    return updateChart(data.map(branch => branch.name));
}

async function setBranch() {
    const branchName = document.getElementById('branchDropdown').value;
    const data = await fetchWithErrorHandling(`/set_branch/${branchName}?repo=${encodeURIComponent(currentRepo)}`);
    if (data.success) {
        currentBranch = branchName;
        showNotification(data.message, 'success');
        highlightCurrentBranch();
        const branchData = await fetchWithErrorHandling(`/vm_data?branch=${branchName}&repo=${encodeURIComponent(currentRepo)}`);
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
            const data = await fetchWithErrorHandling(`/vm_data?branch=${branch}&repo=${encodeURIComponent(currentRepo)}`);
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
                    const branchData = await fetchWithErrorHandling(`/vm_data?branch=${encodeURIComponent(branch)}&repo=${encodeURIComponent(currentRepo)}`);
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
        const [commitDetails, vmState, codeDiff, vmStateDetails] = await Promise.all([
            fetchWithErrorHandling(`/commit_details/${commitHash}?repo=${encodeURIComponent(currentRepo)}`),
            fetchWithErrorHandling(`/vm_state/${commitHash}?repo=${encodeURIComponent(currentRepo)}`),
            fetchWithErrorHandling(`/code_diff/${commitHash}?repo=${encodeURIComponent(currentRepo)}`),
            fetchWithErrorHandling(`/vm_state_details/${commitHash}?repo=${encodeURIComponent(currentRepo)}`)
        ]);

        updateCommitDetails(commitDetails);
        updateVMState(vmState);
        updateCodeDiff(codeDiff);
        updateVMStateDetails(vmStateDetails, commitHash);

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
        <p><strong>Hash:</strong> ${commitDetails.hash}</p>
        <p><strong>Date:</strong> ${moment(commitDetails.date).format('YYYY-MM-DD HH:mm:ss')}</p>
        <p><strong>Message:</strong> ${commitDetails.message}</p>
        <p><strong>Commit Type:</strong> ${commitDetails.commit_type}</p>
        <p><strong>Input Parameters:</strong></p>
        <pre><code class="json">${JSON.stringify(commitDetails.input_parameters, null, 2)}</code></pre>
        <p><strong>Output Variables:</strong></p>
        <pre><code class="json">${JSON.stringify(commitDetails.output_variables, null, 2)}</code></pre>
        <p><strong>Files changed:</strong></p>
        <ul>${commitDetails.files_changed.map(file => `<li>${file}</li>`).join('')}</ul>
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
        <pre><code class="diff">${codeDiff.diff}</code></pre>
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
            showLoading(true);
            const executeData = await fetchWithErrorHandling('/execute_vm', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    repo: currentRepo,
                    commit_hash: commitHash,
                    seq_no: seqNo,
                    suggestion: suggestion // Include suggestion parameter
                }),
            });

            if (executeData.success) {
                await updateUIAfterExecution(executeData.current_branch, executeData.last_commit_hash);
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

async function updateUIAfterExecution(newBranch, lastCommitHash) {
    currentBranch = newBranch;
    await loadBranches();
    highlightCurrentBranch();
    
    try {
        const branchData = await fetchWithErrorHandling(`/vm_data?branch=${newBranch}&repo=${encodeURIComponent(currentRepo)}`);
        
        if (branchData.length === 0) {
            showNotification(`No VM states found for branch: ${newBranch}`, 'warning');
            updateStepList([]);
        } else {
            updateStepList(branchData);
            
            if (lastCommitHash) {
                showCommitDetailsAndHighlight(lastCommitHash);
            }
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
    if (!confirm(`Are you sure you want to delete the branch "${branchName}"?`)) {
        return;
    }
    
    showLoading(true);
    try {
        const data = await fetchWithErrorHandling(`/delete_branch/${branchName}?repo=${encodeURIComponent(currentRepo)}`, {
            method: 'POST'
        });
        
        if (data.success) {
            showNotification(data.message, 'success');
            await updateBranchesAndChart();
        } else {
            showNotification(`Error: ${data.error}`, 'danger');
        }
    } catch (error) {
        showNotification(`Error deleting branch: ${error.message}`, 'danger');
    } finally {
        showLoading(false);
    }
}

async function updateBranchesAndChart() {
    const branches = await fetchWithErrorHandling(`/get_branches?repo=${encodeURIComponent(currentRepo)}`);
    updateBranchSelector(branches);
    await updateChart(branches.map(branch => branch.name));
}

document.getElementById('stepSearch').addEventListener('input', e => {
    const searchTerm = e.target.value.toLowerCase();
    document.querySelectorAll('.step-item').forEach(item => {
        item.style.display = item.textContent.toLowerCase().includes(searchTerm) ? '' : 'none';
    });
});

function optimizeStep(commitHash, seqNo) {
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

        const executeData = await fetchWithErrorHandling('/optimize_step', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                commit_hash: commitHash,
                suggestion: suggestion,
                seq_no: seqNo,
                repo: currentRepo // Assuming this function is defined elsewhere
            })
        });

        // Remove the spinner
        modal.removeChild(spinner);

        // Re-enable the input and buttons
        suggestionInput.disabled = false;
        submitButton.disabled = false;
        cancelButton.disabled = false;

        if (executeData.success) {
            await updateUIAfterExecution(executeData.current_branch, executeData.last_commit_hash);
            showNotification('Execution completed successfully', 'success');
        } else {
            showNotification('Execution failed: ' + (executeData.error || 'Unknown error'), 'danger');
        }

        document.body.removeChild(modal);
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

// New Save Plan Functionality
async function savePlan() {
    // Create a modal dialog for user input
    const modal = createModal('Save Plan', 'Enter the target directory to save the plan:', async () => {
        const targetDirectory = document.getElementById('targetDirectoryInput').value.trim();
        if (!targetDirectory) {
            alert("Please enter a target directory.");
            return;
        }

        // Disable buttons and input
        document.getElementById('modalSubmitButton').disabled = true;
        document.getElementById('modalCancelButton').disabled = true;
        showLoading(true);

        try {
            const response = await fetch('/save_plan', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    repo_name: currentRepo,
                    target_directory: targetDirectory
                }),
            });

            const result = await response.json();
            if (response.ok && result.success) {
                showNotification(result.message, 'success');
            } else {
                showNotification(result.message || 'Failed to save the plan.', 'danger');
            }
        } catch (error) {
            console.error('Error saving plan:', error);
            showNotification('An error occurred while saving the plan.', 'danger');
        } finally {
            showLoading(false);
            document.body.removeChild(modal);
        }
    });

    document.body.appendChild(modal);
}

// Utility function to create a modal
function createModal(title, message, onSubmit) {
    // Create overlay
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';

    // Create modal container
    const modal = document.createElement('div');
    modal.className = 'modal-container';

    // Modal Header
    const header = document.createElement('div');
    header.className = 'modal-header';
    const headerTitle = document.createElement('h5');
    headerTitle.textContent = title;
    header.appendChild(headerTitle);
    modal.appendChild(header);

    // Modal Body
    const body = document.createElement('div');
    body.className = 'modal-body';
    const messagePara = document.createElement('p');
    messagePara.textContent = message;
    body.appendChild(messagePara);

    const input = document.createElement('input');
    input.type = 'text';
    input.id = 'targetDirectoryInput';
    input.className = 'form-control';
    input.placeholder = 'e.g., /path/to/save/plan';
    body.appendChild(input);
    modal.appendChild(body);

    // Modal Footer
    const footer = document.createElement('div');
    footer.className = 'modal-footer';
    const submitButton = document.createElement('button');
    submitButton.textContent = 'Save';
    submitButton.className = 'btn btn-primary';
    submitButton.id = 'modalSubmitButton';
    submitButton.onclick = onSubmit;
    footer.appendChild(submitButton);

    const cancelButton = document.createElement('button');
    cancelButton.textContent = 'Cancel';
    cancelButton.className = 'btn btn-secondary';
    cancelButton.id = 'modalCancelButton';
    cancelButton.onclick = () => document.body.removeChild(overlay);
    footer.appendChild(cancelButton);

    modal.appendChild(footer);
    overlay.appendChild(modal);

    // Style the modal (Alternatively, you can move these styles to your CSS file)
    overlay.style.position = 'fixed';
    overlay.style.top = '0';
    overlay.style.left = '0';
    overlay.style.width = '100%';
    overlay.style.height = '100%';
    overlay.style.backgroundColor = 'rgba(0,0,0,0.5)';
    overlay.style.display = 'flex';
    overlay.style.alignItems = 'center';
    overlay.style.justifyContent = 'center';
    overlay.style.zIndex = '10000';

    modal.style.backgroundColor = '#fff';
    modal.style.padding = '20px';
    modal.style.borderRadius = '8px';
    modal.style.width = '400px';
    modal.style.boxShadow = '0 5px 15px rgba(0,0,0,.5)';

    return overlay;
}

// Ensure the Save Plan button is hidden initially (in case the repository is already set)
document.addEventListener('DOMContentLoaded', () => {
    if (!currentRepo) {
        document.getElementById('savePlanButton').style.display = 'none';
    }
});

// Existing loadDirectories call and other initializations
loadDirectories();
window.addEventListener('resize', () => { if (chart) chart.resize(); });