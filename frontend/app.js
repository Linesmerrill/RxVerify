// RxVerify Frontend Application
console.log('RxVerify app.js loaded successfully!');
let app;

class RxVerifyApp {
    constructor() {
        // Use environment-specific API URL
        this.apiBaseUrl = window.location.hostname === 'localhost' 
            ? 'http://localhost:8000' 
            : 'https://rx-verify-api-e68bdd74c056.herokuapp.com';
        this.currentQuery = null;
        this.searchTimeout = null;
        this.currentTab = 'ask';
        this.init();
    }

    init() {
        this.setupEventListeners();
        this.setupCharacterCounter();
        this.checkSystemStatus();
    }

    // WebSocket functionality removed to fix feedback buttons

    setupEventListeners() {
        // Form submission
        document.getElementById('queryForm').addEventListener('submit', (e) => {
            e.preventDefault();
            this.submitQuery();
        });

        // Advanced search toggle
        document.getElementById('advancedSearch').addEventListener('change', (e) => {
            const advancedOptions = document.getElementById('advancedOptions');
            advancedOptions.classList.toggle('hidden', !e.target.checked);
        });

        // Status button
        document.getElementById('statusBtn').addEventListener('click', () => {
            this.showSystemStatus();
        });

        // Character counter
        document.getElementById('questionInput').addEventListener('input', (e) => {
            this.updateCharacterCount(e.target.value.length);
        });

        // Enter key in textarea
        document.getElementById('questionInput').addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && e.ctrlKey) {
                e.preventDefault();
                this.submitQuery();
            }
        });

        // Search input with debounced search
        document.getElementById('searchInput').addEventListener('input', (e) => {
            this.handleSearchInput(e.target.value);
        });
    }

    setupCharacterCounter() {
        const input = document.getElementById('questionInput');
        const counter = document.getElementById('charCount');
        
        input.addEventListener('input', () => {
            const length = input.value.length;
            counter.textContent = length;
            
            if (length > 450) {
                counter.classList.add('text-red-500');
            } else if (length > 400) {
                counter.classList.add('text-yellow-500');
            } else {
                counter.classList.remove('text-red-500', 'text-yellow-500');
            }
        });
    }

    updateCharacterCount(count) {
        const counter = document.getElementById('charCount');
        counter.textContent = count;
        
        if (count > 450) {
            counter.classList.add('text-red-500');
        } else if (count > 400) {
            counter.classList.add('text-yellow-500');
        } else {
            counter.classList.remove('text-red-500', 'text-yellow-500');
        }
    }

    async submitQuery() {
        const question = document.getElementById('questionInput').value.trim();
        const topK = parseInt(document.getElementById('topK').value);
        
        if (!question) {
            this.showToast('Please enter a question', 'error');
            return;
        }

        if (question.length > 500) {
            this.showToast('Question is too long. Please keep it under 500 characters.', 'error');
            return;
        }

        this.currentQuery = {
            question,
            top_k: topK
        };

        this.showLoadingState();
        this.hideResults();
        this.hideError();

        try {
            const response = await this.callAPI('/query', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(this.currentQuery)
            });

            if (response.ok) {
                const data = await response.json();
                this.displayResults(data);
            } else {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Query failed');
            }
        } catch (error) {
            console.error('Query error:', error);
            this.showError(error.message);
        } finally {
            this.hideLoadingState();
        }
    }

    async callAPI(endpoint, options = {}) {
        const url = `${this.apiBaseUrl}${endpoint}`;
        
        try {
            const response = await fetch(url, {
                ...options,
                headers: {
                    'Content-Type': 'application/json',
                    ...options.headers,
                },
            });
            
            return response;
        } catch (error) {
            throw new Error(`Network error: ${error.message}`);
        }
    }

    displayResults(data) {
        const resultsSection = document.getElementById('results');
        const answerDiv = document.getElementById('answer');
        const sourcesDiv = document.getElementById('sources');
        const crossValidationDiv = document.getElementById('crossValidation');
        
        // Clear previous results
        answerDiv.innerHTML = '';
        sourcesDiv.innerHTML = '';
        crossValidationDiv.innerHTML = '';
        
        // Display the answer
        if (data.answer) {
            answerDiv.innerHTML = `
                <div class="bg-white rounded-lg p-6 shadow-sm border border-gray-200">
                    <h3 class="text-lg font-semibold text-gray-900 mb-4 flex items-center">
                        <svg class="w-5 h-5 text-blue-600 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"></path>
                        </svg>
                        AI-Generated Answer
                    </h3>
                    <div class="prose prose-sm max-w-none">
                        ${this.formatAnswer(data.answer)}
                    </div>
                </div>
            `;
        }
        
        // Display search debug information
        if (data.search_debug) {
            const debugDiv = document.createElement('div');
            debugDiv.className = 'bg-yellow-50 border border-yellow-200 rounded-lg p-4 mb-6';
            debugDiv.innerHTML = `
                <h4 class="text-sm font-semibold text-yellow-800 mb-2 flex items-center">
                    <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L3.732 16.5c-.77.833.192 2.5 1.732 2.5z"></path>
                    </svg>
                    Search Debug Information
                </h4>
                <div class="text-sm text-yellow-700 space-y-2">
                    <div><strong>Query:</strong> "${data.search_debug.query}"</div>
                    <div><strong>Search Strategy:</strong> ${data.search_debug.strategy || 'Real-time Medical Database APIs'}</div>
                    <div><strong>Total Documents Retrieved:</strong> ${data.search_debug.total_retrieved || 'Unknown'}</div>
                    <div><strong>Search Time:</strong> ${data.search_debug.search_time_ms || 'Unknown'}ms</div>
                    ${data.search_debug.sources_queried ? `<div><strong>Sources Queried:</strong> ${data.search_debug.sources_queried.join(', ')}</div>` : ''}
                    ${data.search_debug.retrieval_method ? `<div><strong>Retrieval Method:</strong> ${data.search_debug.retrieval_method}</div>` : ''}
                </div>
            `;
            resultsSection.insertBefore(debugDiv, answerDiv);
        }
        
        // Display sources with enhanced information
        if (data.sources && data.sources.length > 0) {
            sourcesDiv.innerHTML = `
                <div class="bg-white rounded-lg p-6 shadow-sm border border-gray-200">
                    <h3 class="text-lg font-semibold text-gray-900 mb-4 flex items-center">
                        <svg class="w-5 h-5 text-green-600 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.246 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"></path>
                        </svg>
                        Sources & Context (${data.sources.length} documents)
                    </h3>
                    <div class="space-y-4">
                        ${data.sources.map((source, index) => `
                            <div class="border border-gray-200 rounded-lg p-4 bg-gray-50">
                                <div class="flex items-start justify-between mb-2">
                                    <div class="flex items-center space-x-2">
                                        <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${this.getSourceColor(source.source)}">
                                            ${this.getSourceIcon(source.source)} ${source.source.toUpperCase()}
                                        </span>
                                        <span class="text-sm font-medium text-gray-900">${source.title || 'No Title'}</span>
                                    </div>
                                    <span class="text-xs text-gray-500">#${index + 1}</span>
                                </div>
                                
                                <div class="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                                    <div>
                                        <strong class="text-gray-700">RxCUI:</strong> 
                                        <span class="font-mono text-blue-600">${source.rxcui || 'Unknown'}</span>
                                    </div>
                                    <div>
                                        <strong class="text-gray-700">Source ID:</strong> 
                                        <span class="font-mono text-gray-600">${source.id || 'Unknown'}</span>
                                    </div>
                                    <div>
                                        <strong class="text-gray-700">URL:</strong> 
                                        ${source.url ? `<a href="${source.url}" target="_blank" class="text-blue-600 hover:underline">View Source</a>` : 'Not available'}
                                    </div>
                                    <div>
                                        <strong class="text-gray-700">Relevance Score:</strong> 
                                        <span class="font-mono ${source.score ? 'text-green-600' : 'text-gray-500'}">${source.score ? source.score.toFixed(4) : 'N/A'}</span>
                                    </div>
                                </div>
                                
                                <div class="mt-3">
                                    <strong class="text-gray-700 text-sm">Content Preview:</strong>
                                    <div class="mt-1 text-sm text-gray-600 bg-white p-2 rounded border">
                                        ${source.text ? (source.text.length > 200 ? source.text.substring(0, 200) + '...' : source.text) : 'No content available'}
                                    </div>
                                </div>
                            </div>
                        `).join('')}
                    </div>
                </div>
            `;
        }
        
        // Display cross-validation with enhanced details
        if (data.cross_validation && data.cross_validation.length > 0) {
            crossValidationDiv.innerHTML = `
                <div class="bg-white rounded-lg p-6 shadow-sm border border-gray-200">
                    <h3 class="text-lg font-semibold text-gray-900 mb-4 flex items-center">
                        <svg class="w-5 h-5 text-orange-600 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                        </svg>
                        Cross-Source Validation (${data.cross_validation.length} findings)
                    </h3>
                    <div class="space-y-4">
                        ${data.cross_validation.map((validation, index) => `
                            <div class="border border-orange-200 rounded-lg p-4 bg-orange-50">
                                <div class="flex items-center justify-between mb-2">
                                    <span class="text-sm font-medium text-orange-800">Finding #${index + 1}</span>
                                    <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-orange-100 text-orange-800">
                                        ${validation.field.toUpperCase()}
                                    </span>
                                </div>
                                
                                <div class="text-sm text-orange-700">
                                    <div class="mb-2">
                                        <strong>Drug RxCUI:</strong> 
                                        <span class="font-mono text-orange-800">${validation.rxcui}</span>
                                    </div>
                                    <div class="mb-2">
                                        <strong>Field:</strong> 
                                        <span class="capitalize">${validation.field}</span>
                                    </div>
                                    <div>
                                        <strong>Conflicting Values:</strong>
                                        <div class="mt-1 space-y-1">
                                            ${validation.values.map(value => `
                                                <div class="bg-white px-2 py-1 rounded border border-orange-200 text-orange-800 font-mono text-xs">
                                                    ${value}
                                                </div>
                                            `).join('')}
                                        </div>
                                    </div>
                                </div>
                            </div>
                        `).join('')}
                    </div>
                </div>
            `;
        } else if (data.cross_validation && data.cross_validation.length === 0) {
            crossValidationDiv.innerHTML = `
                <div class="bg-white rounded-lg p-6 shadow-sm border border-gray-200">
                    <h3 class="text-lg font-semibold text-gray-900 mb-4 flex items-center">
                        <svg class="w-5 h-5 text-green-600 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                        </svg>
                        Cross-Source Validation
                    </h3>
                    <div class="text-center py-8">
                        <svg class="w-12 h-12 text-green-400 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                        </svg>
                        <p class="text-green-700 font-medium">No discrepancies found!</p>
                        <p class="text-green-600 text-sm mt-1">All sources agree on the information provided.</p>
                    </div>
                </div>
            `;
        }
        
        // Show results section
        this.showResults();
    }

    formatAnswer(answer) {
        // Convert plain text to formatted HTML with enhanced formatting
        const lines = answer.split('\n');
        let formattedHtml = '';
        let inList = false;
        let listItems = [];
        
        for (let i = 0; i < lines.length; i++) {
            const line = lines[i].trim();
            
            if (line === '') {
                // End any current list
                if (inList && listItems.length > 0) {
                    formattedHtml += this.formatList(listItems);
                    listItems = [];
                    inList = false;
                }
                formattedHtml += '<br>';
                continue;
            }
            
            // Check for numbered list items (e.g., "1. ", "2. ", etc.)
            if (/^\d+\.\s/.test(line)) {
                if (!inList) {
                    inList = true;
                }
                const listItem = line.replace(/^\d+\.\s/, '');
                listItems.push(listItem);
                continue;
            }
            
            // Check for bullet points or other list indicators
            if (line.startsWith('•') || line.startsWith('-') || line.startsWith('*')) {
                if (!inList) {
                    inList = true;
                }
                const listItem = line.replace(/^[•\-*]\s/, '');
                listItems.push(listItem);
                continue;
            }
            
            // End list if we encounter a non-list item
            if (inList && listItems.length > 0) {
                formattedHtml += this.formatList(listItems);
                listItems = [];
                inList = false;
            }
            
            // Handle different line types
            if (line.startsWith('###')) {
                formattedHtml += `<h3 class="text-xl font-bold text-gray-900 mt-6 mb-3 border-b border-gray-200 pb-2">${line.replace('###', '').trim()}</h3>`;
            } else if (line.startsWith('##')) {
                formattedHtml += `<h4 class="text-lg font-semibold text-gray-800 mt-5 mb-2">${line.replace('##', '').trim()}</h4>`;
            } else if (line.startsWith('**') && line.endsWith('**')) {
                formattedHtml += `<div class="bg-blue-50 border-l-4 border-blue-400 p-4 my-3 rounded-r-lg"><strong class="text-blue-900 font-semibold">${line.replace(/\*\*/g, '').trim()}</strong></div>`;
            } else if (line.toLowerCase().includes('warning') || line.toLowerCase().includes('caution')) {
                formattedHtml += `<div class="bg-yellow-50 border-l-4 border-yellow-400 p-4 my-3 rounded-r-lg"><div class="flex items-center"><svg class="w-5 h-5 text-yellow-600 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L3.732 16.5c-.77.833.192 2.5 1.732 2.5z"></path></svg><span class="text-yellow-800 font-medium">${line}</span></div></div>`;
            } else if (line.toLowerCase().includes('important') || line.toLowerCase().includes('note')) {
                formattedHtml += `<div class="bg-blue-50 border-l-4 border-blue-400 p-4 my-3 rounded-r-lg"><div class="flex items-center"><svg class="w-5 h-5 text-blue-600 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg><span class="text-blue-800 font-medium">${line}</span></div></div>`;
            } else if (line.toLowerCase().includes('consult') || line.toLowerCase().includes('professional')) {
                formattedHtml += `<div class="bg-green-50 border-l-4 border-green-400 p-4 my-3 rounded-r-lg"><div class="flex items-center"><svg class="w-5 h-5 text-green-600 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg><span class="text-green-800 font-medium">${line}</span></div></div>`;
            } else {
                // Regular paragraph with enhanced styling and inline markdown processing
                formattedHtml += `<p class="text-gray-700 mb-4 leading-relaxed text-base">${this.processInlineMarkdown(line)}</p>`;
            }
        }
        
        // Handle any remaining list items
        if (inList && listItems.length > 0) {
            formattedHtml += this.formatList(listItems);
        }
        
        return formattedHtml;
    }

    formatList(items) {
        if (items.length === 0) return '';
        
        const listItems = items.map((item, index) => {
            // Check if item contains citations
            const hasCitations = item.includes('[') && item.includes(']');
            
            if (hasCitations) {
                // Split content and citations
                const parts = item.split(/(\[.*?\])/);
                let formattedItem = '';
                
                parts.forEach(part => {
                    if (part.startsWith('[') && part.endsWith(']')) {
                        // Format citations
                        formattedItem += `<span class="inline-block bg-gray-100 text-gray-600 px-2 py-1 rounded text-xs font-mono mr-1">${part}</span>`;
                    } else if (part.trim()) {
                        // Process inline markdown within the content
                        formattedItem += this.processInlineMarkdown(part.trim());
                    }
                });
                
                return `<li class="mb-3 text-gray-700 leading-relaxed"><span class="font-semibold text-blue-600 mr-2">${index + 1}.</span>${formattedItem}</li>`;
            } else {
                // Process inline markdown within the item
                return `<li class="mb-3 text-gray-700 leading-relaxed"><span class="font-semibold text-blue-600 mr-2">${index + 1}.</span>${this.processInlineMarkdown(item)}</li>`;
            }
        }).join('');
        
        return `<ol class="space-y-2 bg-gray-50 p-4 rounded-lg border-l-4 border-blue-400 my-4">${listItems}</ol>`;
    }

    processInlineMarkdown(text) {
        // Process inline markdown formatting within text
        return text
            // Convert **bold text** to <strong>bold text</strong>
            .replace(/\*\*(.*?)\*\*/g, '<strong class="font-semibold text-gray-900">$1</strong>')
            // Convert *italic text* to <em>italic text</em>
            .replace(/\*(.*?)\*/g, '<em class="italic text-gray-800">$1</em>')
            // Convert `code text` to <code>code text</code>
            .replace(/`(.*?)`/g, '<code class="bg-gray-100 px-1 py-0.5 rounded text-sm font-mono text-gray-700">$1</code>');
    }

    getSourceIcon(source) {
        const icons = {
            'rxnorm': '🏥',
            'dailymed': '💊',
            'openfda': '🔍',
            'drugbank': '🧬'
        };
        return icons[source] || '📄';
    }

    getSourceColor(source) {
        const colors = {
            'rxnorm': 'bg-blue-100 text-blue-800',
            'dailymed': 'bg-green-100 text-green-800',
            'openfda': 'bg-purple-100 text-purple-800',
            'drugbank': 'bg-pink-100 text-pink-800'
        };
        return colors[source] || 'bg-gray-100 text-gray-800';
    }

    async checkSystemStatus() {
        try {
            const response = await this.callAPI('/health');
            const statusIndicator = document.querySelector('.w-2.h-2.bg-green-400, .w-2.h-2.bg-red-400');
            const statusText = document.querySelector('.flex.items-center.space-x-2 span');
            
            if (response.ok) {
                // Backend is healthy
                if (statusIndicator) {
                    statusIndicator.classList.remove('bg-red-400');
                    statusIndicator.classList.add('bg-green-400');
                }
                if (statusText) {
                    statusText.textContent = 'System Online';
                }
            } else {
                // Backend returned error
                if (statusIndicator) {
                    statusIndicator.classList.remove('bg-green-400');
                    statusIndicator.classList.add('bg-red-400');
                }
                if (statusText) {
                    statusText.textContent = 'System Offline';
                }
            }
        } catch (error) {
            // Backend is unreachable
            const statusIndicator = document.querySelector('.w-2.h-2.bg-green-400, .w-2.h-2.bg-red-400');
            const statusText = document.querySelector('.flex.items-center.space-x-2 span');
            
            if (statusIndicator) {
                statusIndicator.classList.remove('bg-green-400');
                statusIndicator.classList.add('bg-red-400');
            }
            if (statusText) {
                statusText.textContent = 'System Offline';
            }
        }
    }

    async showSystemStatus() {
        try {
            const response = await this.callAPI('/status');
            if (response.ok) {
                const statusData = await response.json();
                
                // Create a comprehensive status message
                const uptime = Math.floor(statusData.uptime_seconds / 60);
                const chromaStatus = statusData.chromadb?.status || 'unknown';
                const docCount = statusData.chromadb?.document_count || 0;
                const successRate = statusData.success_rate_percent || 0;
                
                const statusMessage = `System Healthy | Uptime: ${uptime}m | ChromaDB: ${chromaStatus} (${docCount} docs) | Success Rate: ${successRate}%`;
                
                this.showToast(statusMessage, 'success');
            } else {
                this.showToast('Unable to get system status', 'error');
            }
        } catch (error) {
            this.showToast('System status check failed - Backend may be offline', 'error');
        }
    }

    showLoadingState() {
        document.getElementById('loadingState').classList.remove('hidden');
        document.getElementById('submitBtn').disabled = true;
        document.getElementById('submitBtn').innerHTML = `
            <svg class="animate-spin w-5 h-5" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            <span>Processing...</span>
        `;
        
        // Show the multi-step progress indicator
        this.showProgressIndicator();
    }

    showProgressIndicator() {
        const progressContainer = document.getElementById('progressContainer');
        if (progressContainer) {
            progressContainer.classList.remove('hidden');
            this.startProgressSteps();
        }
    }

    startProgressSteps() {
        const steps = [
            { id: 'search', title: 'Querying medical databases', icon: '🔍', description: 'Searching RxNorm, DailyMed, OpenFDA & DrugBank APIs...' },
            { id: 'crosscheck', title: 'Cross-validating sources', icon: '✅', description: 'Checking data consistency across sources...' },
            { id: 'llm', title: 'Generating AI response', icon: '🤖', description: 'Creating intelligent answer with citations...' },
            { id: 'finalize', title: 'Finalizing results', icon: '✨', description: 'Preparing your response...' }
        ];

        let currentStep = 0;
        const startTime = Date.now();

        const updateStep = () => {
            if (currentStep >= steps.length) return;

            const step = steps[currentStep];
            const stepElement = document.getElementById(`step_${step.id}`);
            if (stepElement) {
                // Update current step
                stepElement.classList.add('bg-blue-50', 'border-blue-200');
                stepElement.classList.remove('bg-gray-50', 'border-gray-200');
                
                // Add active indicator
                const iconElement = stepElement.querySelector('.step-icon');
                if (iconElement) {
                    iconElement.innerHTML = `
                        <div class="w-6 h-6 bg-blue-600 rounded-full flex items-center justify-center">
                            <svg class="w-4 h-4 text-white animate-spin" fill="none" viewBox="0 0 24 24">
                                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                            </svg>
                        </div>
                    `;
                }

                // Update description
                const descElement = stepElement.querySelector('.step-description');
                if (descElement) {
                    descElement.textContent = step.description;
                }

                // Add timing for search and LLM steps
                if (step.id === 'search' || step.id === 'llm') {
                    const timingElement = stepElement.querySelector('.step-timing');
                    if (timingElement) {
                        const updateTiming = () => {
                            const elapsed = Date.now() - startTime;
                            const seconds = Math.floor(elapsed / 1000);
                            const minutes = Math.floor(seconds / 60);
                            const remainingSeconds = seconds % 60;
                            const timeStr = minutes > 0 ? `${minutes}m ${remainingSeconds}s` : `${seconds}s`;
                            timingElement.textContent = timeStr;
                        };
                        
                        // Update timing every second
                        const timingInterval = setInterval(updateTiming, 1000);
                        updateTiming(); // Initial update
                        
                        // Store interval for cleanup
                        stepElement.dataset.timingInterval = timingInterval;
                    }
                }
            }

            // Move to next step after a delay
            setTimeout(() => {
                if (currentStep < steps.length) {
                    // Mark current step as completed
                    const stepElement = document.getElementById(`step_${step.id}`);
                    if (stepElement) {
                        stepElement.classList.remove('bg-blue-50', 'border-blue-200');
                        stepElement.classList.add('bg-green-50', 'border-green-200');
                        
                        // Show completion icon
                        const iconElement = stepElement.querySelector('.step-icon');
                        if (iconElement) {
                            iconElement.innerHTML = `
                                <div class="w-6 h-6 bg-green-600 rounded-full flex items-center justify-center">
                                    <svg class="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
                                    </svg>
                                </div>
                            `;
                        }

                        // Clear timing interval if exists
                        if (stepElement.dataset.timingInterval) {
                            clearInterval(parseInt(stepElement.dataset.timingInterval));
                        }
                    }
                    
                    currentStep++;
                    updateStep();
                }
            }, this.getStepDelay(step.id));
        };

        // Start the first step
        updateStep();
    }

    getStepDelay(stepId) {
        // Different delays for different steps to simulate realistic processing times
        const delays = {
            'search': 2000,      // 2 seconds for search
            'crosscheck': 1500,  // 1.5 seconds for cross-check
            'llm': 3000,         // 3 seconds for LLM (longest step)
            'finalize': 1000     // 1 second for finalization
        };
        return delays[stepId] || 2000;
    }

    hideLoadingState() {
        document.getElementById('loadingState').classList.add('hidden');
        document.getElementById('submitBtn').disabled = false;
        document.getElementById('submitBtn').innerHTML = `
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path>
            </svg>
            <span>Get Answer</span>
        `;
        
        // Hide the progress indicator
        const progressContainer = document.getElementById('progressContainer');
        if (progressContainer) {
            progressContainer.classList.add('hidden');
        }
    }

    showResults() {
        document.getElementById('results').classList.remove('hidden');
    }

    hideResults() {
        document.getElementById('results').classList.add('hidden');
    }

    showError(message) {
        const errorState = document.getElementById('errorState');
        const errorMessage = document.getElementById('errorMessage');
        
        errorMessage.textContent = message;
        errorState.classList.remove('hidden');
        errorState.classList.add('fade-in');
        
        this.showToast(message, 'error');
    }

    hideError() {
        document.getElementById('errorState').classList.add('hidden');
    }

    showToast(message, type = 'info') {
        const toastContainer = document.getElementById('toastContainer');
        const toast = document.createElement('div');
        
        const colors = {
            success: 'bg-green-500',
            error: 'bg-red-500',
            warning: 'bg-yellow-500',
            info: 'bg-blue-500'
        };
        
        const icons = {
            success: `<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
            </svg>`,
            error: `<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
            </svg>`,
            warning: `<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L3.34 16.5c-.77.833.192 2.5 1.732 2.5z"></path>
            </svg>`,
            info: `<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
            </svg>`
        };
        
        toast.className = `${colors[type]} text-white px-4 py-3 rounded-lg shadow-lg flex items-center space-x-2 fade-in`;
        toast.innerHTML = `${icons[type]} <span>${message}</span>`;
        
        toastContainer.appendChild(toast);
        
        // Auto-remove after 5 seconds
        setTimeout(() => {
            toast.classList.add('opacity-0', 'transform', 'translate-x-full');
            setTimeout(() => {
                if (toast.parentNode) {
                    toast.parentNode.removeChild(toast);
                }
            }, 300);
        }, 5000);
    }

    // Tab switching functionality
    switchTab(tabName) {
        this.currentTab = tabName;
        
        // Update tab buttons
        const askTab = document.getElementById('askTab');
        const searchTab = document.getElementById('searchTab');
        const askContent = document.getElementById('askTabContent');
        const searchContent = document.getElementById('searchTabContent');
        
        if (tabName === 'ask') {
            askTab.className = 'tab-button flex-1 py-3 px-6 text-center font-medium rounded-lg transition-all duration-200 bg-white text-primary-600 shadow-sm';
            searchTab.className = 'tab-button flex-1 py-3 px-6 text-center font-medium rounded-lg transition-all duration-200 text-gray-600 hover:text-gray-900';
            askContent.classList.remove('hidden');
            searchContent.classList.add('hidden');
        } else {
            searchTab.className = 'tab-button flex-1 py-3 px-6 text-center font-medium rounded-lg transition-all duration-200 bg-white text-green-600 shadow-sm';
            askTab.className = 'tab-button flex-1 py-3 px-6 text-center font-medium rounded-lg transition-all duration-200 text-gray-600 hover:text-gray-900';
            searchContent.classList.remove('hidden');
            askContent.classList.add('hidden');
        }
    }

    // Search functionality
    handleSearchInput(query) {
        // Set current search query for feedback
        window.currentSearchQuery = query;
        console.log('handleSearchInput called with query:', query);
        
        // Clear previous timeout
        if (this.searchTimeout) {
            clearTimeout(this.searchTimeout);
        }
        
        // Hide previous results
        this.hideSearchResults();
        
        // If query is empty or too short, hide loading and stop
        if (query.length < 2) {
            this.showSearchLoading(false);
            return;
        }
        
        // Show loading
        this.showSearchLoading(true);
        
        // Debounce search
        this.searchTimeout = setTimeout(() => {
            this.performSearch(query);
        }, 300);
    }

    async performSearch(query) {
        try {
            // Store current search query for feedback
            this.currentSearchQuery = query;
            
            // Use the new drug search endpoint for autocomplete
            const response = await fetch(`${this.apiBaseUrl}/drugs/search?query=${encodeURIComponent(query)}&limit=10`);
            
            if (!response.ok) {
                throw new Error(`Search failed: ${response.statusText}`);
            }
            
            const data = await response.json();
            this.displaySearchResults(data.results);
            
        } catch (error) {
            console.error('Search error:', error);
            this.showToast('Search failed. Please try again.', 'error');
            this.hideSearchResults();
        } finally {
            this.showSearchLoading(false);
        }
    }

    displaySearchResults(results) {
        const resultsContainer = document.getElementById('searchResults');
        const noResults = document.getElementById('noResults');
        
        if (results.length === 0) {
            resultsContainer.classList.add('hidden');
            noResults.classList.remove('hidden');
            return;
        }
        
        noResults.classList.add('hidden');
        resultsContainer.classList.remove('hidden');
        
        const resultsDiv = resultsContainer.querySelector('.space-y-3');
        resultsDiv.innerHTML = '';
        
        results.forEach(result => {
            const resultElement = this.createSearchResultElement(result);
            resultsDiv.appendChild(resultElement);
        });
    }

    createSearchResultElement(result) {
        console.log('Creating search result element for:', result.name);
        const div = document.createElement('div');
        div.className = 'search-result bg-white border border-gray-200 rounded-xl p-4 hover:border-green-300 hover:shadow-md transition-all duration-200';
        
        // Create drug name and class
        const nameDiv = document.createElement('div');
        nameDiv.className = 'flex items-start justify-between mb-2';
        
        const nameInfo = document.createElement('div');
        nameInfo.className = 'flex-1';
        
        const drugName = document.createElement('h4');
        drugName.className = 'drug-name font-semibold text-gray-900 text-lg';
        drugName.textContent = result.name;
        
        const genericName = document.createElement('p');
        genericName.className = 'text-sm text-gray-600 mt-1';
        if (result.generic_name && result.generic_name !== result.name) {
            genericName.textContent = `Generic: ${result.generic_name}`;
        }
        
        nameInfo.appendChild(drugName);
        if (result.generic_name && result.generic_name !== result.name) {
            nameInfo.appendChild(genericName);
        }
        
        const drugClass = document.createElement('div');
        drugClass.className = 'text-xs text-gray-500 bg-gray-100 px-2 py-1 rounded-full';
        drugClass.textContent = result.drug_class || 'Medication';
        
        nameDiv.appendChild(nameInfo);
        nameDiv.appendChild(drugClass);
        
        // Create brand names
        let brandNamesDiv = '';
        if (result.brand_names && result.brand_names.length > 0) {
            brandNamesDiv = `
                <div class="mb-2">
                    <span class="text-xs font-medium text-gray-500">Brand names:</span>
                    <span class="text-sm text-gray-700 ml-1">${result.brand_names.join(', ')}</span>
                </div>
            `;
        }
        
        // Create common uses
        let usesDiv = '';
        if (result.common_uses && result.common_uses.length > 0) {
            usesDiv = `
                <div class="mb-2">
                    <span class="text-xs font-medium text-gray-500">Common uses:</span>
                    <div class="flex flex-wrap gap-1 mt-1">
                        ${result.common_uses.map(use => 
                            `<span class="text-xs bg-green-100 text-green-800 px-2 py-1 rounded-full">${use}</span>`
                        ).join('')}
                    </div>
                </div>
            `;
        }
        
        // Create feedback section
        const feedbackDiv = document.createElement('div');
        feedbackDiv.className = 'flex items-center justify-between mt-3 pt-2 border-t border-gray-100';
        
        const feedbackButtons = document.createElement('div');
        feedbackButtons.className = 'flex items-center space-x-2';
        
        const thumbsUpBtn = document.createElement('button');
        thumbsUpBtn.className = 'flex items-center space-x-1 px-2 py-1 text-xs text-green-600 hover:bg-green-50 rounded transition-colors border border-transparent';
        thumbsUpBtn.innerHTML = `
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 10h4.764a2 2 0 011.789 2.894l-3.5 7A2 2 0 0115.263 21h-4.017c-.163 0-.326-.02-.485-.06L7 20m7-10V5a2 2 0 00-2-2h-.095c-.5 0-.905.405-.905.905 0 .714-.211 1.412-.608 2.006L7 11v9m7-10h-2M7 20H5a2 2 0 01-2-2v-6a2 2 0 012-2h2.5"></path>
            </svg>
            <span>Helpful</span>
            <span class="helpful-count ml-1 text-xs font-medium">${result.helpful_count > 0 ? `(${result.helpful_count})` : ''}</span>
        `;
        
        const thumbsDownBtn = document.createElement('button');
        thumbsDownBtn.className = 'flex items-center space-x-1 px-2 py-1 text-xs text-red-600 hover:bg-red-50 rounded transition-colors border border-transparent';
        thumbsDownBtn.innerHTML = `
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 14H5.236a2 2 0 01-1.789-2.894l3.5-7A2 2 0 018.737 3h4.018c.163 0 .326.02.485.06L17 4m-7 10v2a2 2 0 002 2h.096c.5 0 .905-.405.905-.905 0-.714.211-1.412.608-2.006L17 13V4m-7 10h2m5-10h2a2 2 0 012 2v6a2 2 0 01-2 2h-2.5"></path>
            </svg>
            <span>Not helpful</span>
            <span class="not-helpful-count ml-1 text-xs font-medium">${result.not_helpful_count > 0 ? `(${result.not_helpful_count})` : ''}</span>
        `;
        
        // Add feedback event listeners
        console.log('Adding event listeners to buttons for:', result.name);
        
        // Add proper feedback functionality
        thumbsUpBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            console.log('Helpful button clicked!', result.name);
            const currentQuery = window.currentSearchQuery || this.currentSearchQuery || 'fallback';
            this.handleVote(result.name, currentQuery, true, thumbsUpBtn, thumbsDownBtn);
        });
        
        thumbsDownBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            console.log('Not helpful button clicked!', result.name);
            const currentQuery = window.currentSearchQuery || this.currentSearchQuery || 'fallback';
            this.handleVote(result.name, currentQuery, false, thumbsUpBtn, thumbsDownBtn);
        });
        
        // Restore user's previous vote state
        this.restoreVoteState(result.name, window.currentSearchQuery || this.currentSearchQuery || 'fallback', thumbsUpBtn, thumbsDownBtn);
        
        feedbackButtons.appendChild(thumbsUpBtn);
        feedbackButtons.appendChild(thumbsDownBtn);
        
        feedbackDiv.appendChild(feedbackButtons);
        
        // Use appendChild instead of innerHTML to preserve event listeners
        div.appendChild(nameDiv);
        if (brandNamesDiv) {
            const brandDiv = document.createElement('div');
            brandDiv.innerHTML = brandNamesDiv;
            div.appendChild(brandDiv);
        }
        if (usesDiv) {
            const usesDivElement = document.createElement('div');
            usesDivElement.innerHTML = usesDiv;
            div.appendChild(usesDivElement);
        }
        div.appendChild(feedbackDiv);
        
        // No click handler - these are just search results for feedback
        
        return div;
    }

    searchForDrug(drugName) {
        // Switch to ask tab and populate the question
        this.switchTab('ask');
        const questionInput = document.getElementById('questionInput');
        questionInput.value = `Tell me about ${drugName}`;
        this.updateCharacterCount(questionInput.value.length);
        
        // Focus on the input
        questionInput.focus();
        
        this.showToast(`Searching for information about ${drugName}...`, 'info');
    }

    showSearchLoading(show) {
        const loading = document.getElementById('searchLoading');
        if (show) {
            loading.classList.remove('hidden');
        } else {
            loading.classList.add('hidden');
        }
    }

    hideSearchResults() {
        document.getElementById('searchResults').classList.add('hidden');
        document.getElementById('noResults').classList.add('hidden');
    }

    async submitFeedback(drugName, query, isPositive, isRemoval = false) {
        try {
            const response = await fetch(`${this.apiBaseUrl}/feedback`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    drug_name: drugName,
                    query: query,
                    is_positive: isPositive,
                    is_removal: isRemoval, // New field to indicate if this is removing a vote
                    user_id: this.getUserId(),
                    session_id: this.getSessionId(),
                    timestamp: new Date().toISOString()
                })
            });
            
            if (!response.ok) {
                throw new Error(`Feedback submission failed: ${response.statusText}`);
            }
            
            const data = await response.json();
            console.log('Feedback submitted successfully:', data);
            
        } catch (error) {
            console.error('Feedback submission error:', error);
            // Don't show error toast for feedback failures to avoid annoying users
        }
    }

    restoreVoteState(drugName, query, helpfulBtn, notHelpfulBtn) {
        const voteKey = `vote_${drugName}_${query}`;
        const currentVote = localStorage.getItem(voteKey);
        
        if (currentVote === 'helpful') {
            // User previously voted helpful - highlight the helpful button
            helpfulBtn.className = helpfulBtn.className.replace('border-transparent', 'border-green-500 bg-green-50');
            // Don't disable the button - allow toggle functionality
        } else if (currentVote === 'not_helpful') {
            // User previously voted not helpful - highlight the not helpful button
            notHelpfulBtn.className = notHelpfulBtn.className.replace('border-transparent', 'border-red-500 bg-red-50');
            // Don't disable the button - allow toggle functionality
        }
    }

    handleVote(drugName, query, isPositive, helpfulBtn, notHelpfulBtn) {
        console.log('handleVote called:', { drugName, query, isPositive });
        const voteKey = `vote_${drugName}_${query}`;
        const currentVote = localStorage.getItem(voteKey);
        
        // Check if user is clicking the same button they already pressed (toggle off)
        if ((currentVote === 'helpful' && isPositive) || (currentVote === 'not_helpful' && !isPositive)) {
            // Remove the vote (toggle off)
            localStorage.removeItem(voteKey);
            
            // Reset both buttons to default state
            helpfulBtn.className = helpfulBtn.className.replace('border-green-500 bg-green-50', 'border-transparent');
            notHelpfulBtn.className = notHelpfulBtn.className.replace('border-red-500 bg-red-50', 'border-transparent');
            helpfulBtn.disabled = false;
            notHelpfulBtn.disabled = false;
            
            // Submit negative feedback to backend (to decrement count)
            this.submitFeedback(drugName, query, isPositive, true); // true = isRemoval
            
            // Show success message
            this.showToast(`Feedback removed: ${isPositive ? 'Helpful' : 'Not helpful'}`, 'info');
            return;
        }
        
        // Store the new vote in localStorage
        localStorage.setItem(voteKey, isPositive ? 'helpful' : 'not_helpful');
        
        // Reset both buttons to default state first
        helpfulBtn.className = helpfulBtn.className.replace('border-green-500 bg-green-50', 'border-transparent');
        notHelpfulBtn.className = notHelpfulBtn.className.replace('border-red-500 bg-red-50', 'border-transparent');
        helpfulBtn.disabled = false;
        notHelpfulBtn.disabled = false;
        
        // Apply new vote state
        if (isPositive) {
            helpfulBtn.className = helpfulBtn.className.replace('border-transparent', 'border-green-500 bg-green-50');
            // Don't disable the button - allow toggle functionality
        } else {
            notHelpfulBtn.className = notHelpfulBtn.className.replace('border-transparent', 'border-red-500 bg-red-50');
            // Don't disable the button - allow toggle functionality
        }
        
        // Submit feedback to backend
        this.submitFeedback(drugName, query, isPositive);
        
        // Show success message
        this.showToast(`Feedback recorded: ${isPositive ? 'Helpful' : 'Not helpful'}`, 'success');
    }

    getUserId() {
        // Generate or retrieve user ID (could be stored in localStorage)
        let userId = localStorage.getItem('rxverify_user_id');
        if (!userId) {
            userId = 'user_' + Math.random().toString(36).substr(2, 9);
            localStorage.setItem('rxverify_user_id', userId);
        }
        return userId;
    }

    getSessionId() {
        // Generate or retrieve session ID
        let sessionId = sessionStorage.getItem('rxverify_session_id');
        if (!sessionId) {
            sessionId = 'session_' + Math.random().toString(36).substr(2, 9);
            sessionStorage.setItem('rxverify_session_id', sessionId);
        }
        return sessionId;
    }

    resetForm() {
        document.getElementById('questionInput').value = '';
        document.getElementById('advancedSearch').checked = false;
        document.getElementById('advancedOptions').classList.add('hidden');
        this.hideResults();
        this.hideError();
        this.updateCharacterCount(0);
        this.showToast('Form reset successfully', 'info');
    }
}

// Initialize the application

document.addEventListener('DOMContentLoaded', () => {
    app = new RxVerifyApp();
    // Make app globally available for index.html
    window.rxVerifyApp = app;
});

// Add some nice keyboard shortcuts
document.addEventListener('keydown', (e) => {
    // Ctrl/Cmd + Enter to submit
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        if (app) {
            app.submitQuery();
        }
    }
    
    // Escape to reset
    if (e.key === 'Escape') {
        if (app) {
            app.resetForm();
        }
    }
});
