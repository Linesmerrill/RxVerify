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
        this.voteStates = this.loadVoteStates(); // Load cached vote states as plain object
        this.voteCooldowns = new Map(); // Track cooldowns to prevent spam
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
            this.updateClearButtonVisibility(e.target.value);
        });

        // Clear search button
        document.getElementById('clearSearchBtn').addEventListener('click', () => {
            this.clearSearch();
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

    hideSearchResults() {
        const resultsContainer = document.getElementById('searchResults');
        const noResults = document.getElementById('noResults');
        
        resultsContainer.classList.add('hidden');
        noResults.classList.add('hidden');
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
            // Show loading spinner
            this.showSearchLoading(true);
            
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
        
        results.forEach((result, index) => {
            try {
                const resultElement = this.createSearchResultElement(result);
                resultsDiv.appendChild(resultElement);
                
                // Load common uses asynchronously if not already present
                if (!result.common_uses || result.common_uses.length === 0) {
                    this.loadCommonUsesAsync(result.name, resultElement);
                }
            } catch (error) {
                console.error(`Error creating result element ${index}:`, error, result);
            }
        });
    }

    createSearchResultElement(result) {
        const div = document.createElement('div');
        div.className = 'search-result bg-white border border-gray-200 rounded-xl p-4 hover:border-green-300 hover:shadow-md transition-all duration-200';
        div.setAttribute('data-drug-id', result.drug_id);
        
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
        
        // Create common uses section
        const usesDiv = document.createElement('div');
        usesDiv.className = 'common-uses-section mb-2';
        if (result.common_uses && result.common_uses.length > 0) {
            usesDiv.innerHTML = `
                <span class="text-xs font-medium text-gray-500">Common uses:</span>
                <div class="flex flex-wrap gap-1 mt-1">
                    ${result.common_uses.map(use => 
                        `<span class="text-xs bg-green-100 text-green-800 px-2 py-1 rounded-full">${use}</span>`
                    ).join('')}
                </div>
            `;
        }
        
        // Create feedback section
        const feedbackDiv = document.createElement('div');
        feedbackDiv.className = 'flex items-center justify-between mt-3 pt-2 border-t border-gray-100';
        
        const feedbackButtons = document.createElement('div');
        feedbackButtons.className = 'flex items-center space-x-2';
        
        const thumbsUpBtn = document.createElement('button');
        thumbsUpBtn.className = 'thumbs-up-btn flex items-center space-x-1 px-2 py-1 text-xs text-green-600 hover:bg-green-50 rounded transition-colors border border-transparent';
        thumbsUpBtn.innerHTML = `
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 10h4.764a2 2 0 011.789 2.894l-3.5 7A2 2 0 0115.263 21h-4.017c-.163 0-.326-.02-.485-.06L7 20m7-10V5a2 2 0 00-2-2h-.095c-.5 0-.905.405-.905.905 0 .714-.211 1.412-.608 2.006L7 11v9m7-10h-2M7 20H5a2 2 0 01-2-2v-6a2 2 0 012-2h2.5"></path>
            </svg>
            <span>Helpful</span>
            <span class="helpful-count ml-1 text-xs font-medium">${result.upvotes > 0 ? `(${result.upvotes})` : ''}</span>
        `;
        
        const thumbsDownBtn = document.createElement('button');
        thumbsDownBtn.className = 'thumbs-down-btn flex items-center space-x-1 px-2 py-1 text-xs text-red-600 hover:bg-red-50 rounded transition-colors border border-transparent';
        thumbsDownBtn.innerHTML = `
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 14H5.236a2 2 0 01-1.789-2.894l3.5-7A2 2 0 018.737 3h4.018c.163 0 .326.02.485.06L17 4m-7 10v2a2 2 0 002 2h.096c.5 0 .905-.405.905-.905 0-.714.211-1.412.608-2.006L17 13V4m-7 10h2m5-10h2a2 2 0 012 2v6a2 2 0 01-2 2h-2.5"></path>
            </svg>
            <span>Not helpful</span>
            <span class="not-helpful-count ml-1 text-xs font-medium">${result.downvotes > 0 ? `(${result.downvotes})` : ''}</span>
        `;
        
        // Add voting event listeners
        thumbsUpBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            this.voteOnDrug(result.drug_id, 'upvote');
        });
        
        thumbsDownBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            this.voteOnDrug(result.drug_id, 'downvote');
        });
        
        feedbackButtons.appendChild(thumbsUpBtn);
        feedbackButtons.appendChild(thumbsDownBtn);
        
        feedbackDiv.appendChild(feedbackButtons);
        
        // Apply initial vote state from cache, but verify with backend
        const currentVote = this.voteStates[result.drug_id];
        
        // Always allow voting initially - we'll verify with backend on click
        // This implements "when in doubt, allow voting" policy
        if (currentVote === 'upvote') {
            thumbsUpBtn.className += ' bg-green-100 border-green-300';
        } else if (currentVote === 'downvote') {
            thumbsDownBtn.className += ' bg-red-100 border-red-300';
        }
        
        // Use appendChild instead of innerHTML to preserve event listeners
        div.appendChild(nameDiv);
        if (brandNamesDiv) {
            const brandDiv = document.createElement('div');
            brandDiv.innerHTML = brandNamesDiv;
            div.appendChild(brandDiv);
        }
        div.appendChild(usesDiv);
        div.appendChild(feedbackDiv);
        
        // No click handler - these are just search results for feedback
        
        return div;
    }

    async voteOnDrug(drugId, voteType) {
        try {
            // First, verify with backend if user has actually voted
            const backendStatus = await this.verifyVoteStatus(drugId);
            
            // Check cooldown to prevent spam clicking
            const cooldownKey = `${drugId}_${voteType}`;
            const now = Date.now();
            const cooldownTime = 2000; // 2 seconds cooldown
            
            if (this.voteCooldowns.has(cooldownKey)) {
                const lastVote = this.voteCooldowns.get(cooldownKey);
                if (now - lastVote < cooldownTime) {
                    console.log('Vote cooldown active, please wait...');
                    return;
                }
            }
            
            // Check if user already voted on this drug (backend verification)
            const currentVote = backendStatus.has_voted ? backendStatus.vote_type : null;
            let isUnvote = false;
            let needsUnvoteFirst = false;
            
            console.log(`Vote attempt: ${voteType} on ${drugId}, current vote state: ${currentVote}`);
            
            if (currentVote === voteType) {
                // User is trying to unvote (clicking same vote type again)
                isUnvote = true;
                console.log(`Unvoting ${voteType} on drug:`, drugId);
            } else if (currentVote && currentVote !== voteType) {
                // User is switching vote types (e.g., helpful -> not helpful)
                needsUnvoteFirst = true;
                console.log(`Switching vote from ${currentVote} to ${voteType} on drug:`, drugId);
            } else {
                console.log(`Voting ${voteType} on drug:`, drugId);
            }
            
            // IMMEDIATE UI UPDATE (Optimistic Update)
            this.updateVoteButtonsImmediately(drugId, voteType, isUnvote);
            
            // Update vote state in cache immediately and sync with backend
            if (isUnvote) {
                delete this.voteStates[drugId];
                console.log(`Removed vote state for ${drugId}`);
            } else {
                this.voteStates[drugId] = voteType;
                console.log(`Set vote state for ${drugId} to ${voteType}`);
            }
            this.saveVoteStates();
            
            // Sync localStorage with backend state
            console.log('Vote state synced with backend:', { drugId, voteType, isUnvote });
            
            // Set cooldown
            this.voteCooldowns.set(cooldownKey, now);
            
            // Handle vote switching (unvote first, then vote)
            if (needsUnvoteFirst) {
                try {
                    // First, unvote the existing vote
                    const unvoteResponse = await fetch(`${this.apiBaseUrl}/drugs/vote?drug_id=${encodeURIComponent(drugId)}&vote_type=${currentVote}&is_unvote=true`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        }
                    });
                    
                    if (!unvoteResponse.ok) {
                        const errorData = await unvoteResponse.json();
                        throw new Error(errorData.detail || 'Failed to unvote');
                    }
                    
                    console.log('Successfully unvoted previous vote');
                    
                    // Then, vote with the new type
                    const voteResponse = await fetch(`${this.apiBaseUrl}/drugs/vote?drug_id=${encodeURIComponent(drugId)}&vote_type=${voteType}&is_unvote=false`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        }
                    });
                    
                    if (!voteResponse.ok) {
                        const errorData = await voteResponse.json();
                        throw new Error(errorData.detail || 'Failed to vote');
                    }
                    
                    const result = await voteResponse.json();
                    console.log('Vote switch result:', result);
                    
                    // Show success message
                    this.showToast(`Vote switched to ${voteType} successfully!`, 'success');
                    
                    // Refresh the search results to show updated ratings
                    const currentQuery = document.getElementById('searchInput').value;
                    if (currentQuery.trim()) {
                        await this.performSearch(currentQuery);
                    }
                    
                } catch (error) {
                    console.error('Failed to switch vote:', error);
                    this.showToast(`Failed to switch vote: ${error.message}`, 'error');
                    
                    // Revert UI changes on error
                    this.revertVoteButtons(drugId, currentVote);
                    return;
                }
            } else {
                // Regular vote or unvote
                const response = await fetch(`${this.apiBaseUrl}/drugs/vote?drug_id=${encodeURIComponent(drugId)}&vote_type=${voteType}&is_unvote=${isUnvote}`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    }
                });
                
                if (!response.ok) {
                    const errorData = await response.json();
                    throw new Error(errorData.detail || 'Failed to vote');
                }
                
                const result = await response.json();
                console.log('Vote result:', result);
                
                // Show success message
                const message = isUnvote ? `Vote removed successfully!` : `Vote recorded successfully!`;
                this.showToast(message, 'success');
                
                // Refresh the search results to show updated ratings
                const currentQuery = document.getElementById('searchInput').value;
                if (currentQuery.trim()) {
                    await this.performSearch(currentQuery);
                }
            }
            
        } catch (error) {
            console.error('Voting error:', error);
            
            // REVERT UI CHANGES on error
            this.revertVoteButtons(drugId);
            
            // Revert vote state in cache
            const currentVote = this.voteStates[drugId];
            if (currentVote === voteType) {
                delete this.voteStates[drugId];
            } else {
                this.voteStates[drugId] = currentVote;
            }
            this.saveVoteStates();
            
            this.showToast(`Failed to vote: ${error.message}`, 'error');
        }
    }

    // Vote state management methods
    async verifyVoteStatus(drugId) {
        // Verify with backend if user has actually voted on this drug
        try {
            const response = await fetch(`${this.apiBaseUrl}/drugs/vote-status?drug_id=${encodeURIComponent(drugId)}`, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                }
            });
            
            if (response.ok) {
                const data = await response.json();
                return {
                    has_voted: data.has_voted,
                    vote_type: data.vote_type
                };
            } else {
                console.warn('Failed to verify vote status, allowing vote');
                return { has_voted: false, vote_type: null };
            }
        } catch (error) {
            console.warn('Error verifying vote status, allowing vote:', error);
            return { has_voted: false, vote_type: null };
        }
    }
    
    loadVoteStates() {
        try {
            const stored = localStorage.getItem('rxverify_vote_states');
            if (stored) {
                const states = JSON.parse(stored);
                console.log('Loaded vote states from localStorage:', states);
                return states;
            }
        } catch (error) {
            console.error('Error loading vote states:', error);
        }
        console.log('No vote states found, returning empty object');
        return {};
    }

    saveVoteStates() {
        try {
            localStorage.setItem('rxverify_vote_states', JSON.stringify(this.voteStates));
            console.log('Saved vote states to localStorage:', this.voteStates);
        } catch (error) {
            console.error('Error saving vote states:', error);
        }
    }

    updateVoteButtons(drugId, voteType, isUnvote) {
        // Find the result element for this drug
        const resultElements = document.querySelectorAll('.search-result');
        for (const element of resultElements) {
            const drugIdElement = element.querySelector('[data-drug-id]');
            if (drugIdElement && drugIdElement.getAttribute('data-drug-id') === drugId) {
                const thumbsUpBtn = element.querySelector('.thumbs-up-btn');
                const thumbsDownBtn = element.querySelector('.thumbs-down-btn');
                
                if (thumbsUpBtn && thumbsDownBtn) {
                    // Reset both buttons to default state
                    thumbsUpBtn.className = 'thumbs-up-btn flex items-center space-x-1 px-2 py-1 text-xs text-green-600 hover:bg-green-50 rounded transition-colors border border-transparent';
                    thumbsDownBtn.className = 'thumbs-down-btn flex items-center space-x-1 px-2 py-1 text-xs text-red-600 hover:bg-red-50 rounded transition-colors border border-transparent';
                    
                    // Apply active state based on current vote
                    const currentVote = this.voteStates.get(drugId);
                    if (currentVote === 'upvote') {
                        thumbsUpBtn.className += ' bg-green-100 border-green-300';
                    } else if (currentVote === 'downvote') {
                        thumbsDownBtn.className += ' bg-red-100 border-red-300';
                    }
                }
                break;
            }
        }
    }

    updateVoteButtonsImmediately(drugId, voteType, isUnvote) {
        // Find the result element for this drug
        const resultElements = document.querySelectorAll('.search-result');
        for (const element of resultElements) {
            const drugIdElement = element.querySelector('[data-drug-id]');
            if (drugIdElement && drugIdElement.getAttribute('data-drug-id') === drugId) {
                const thumbsUpBtn = element.querySelector('.thumbs-up-btn');
                const thumbsDownBtn = element.querySelector('.thumbs-down-btn');
                
                if (thumbsUpBtn && thumbsDownBtn) {
                    // Reset both buttons to default state
                    thumbsUpBtn.className = 'thumbs-up-btn flex items-center space-x-1 px-2 py-1 text-xs text-green-600 hover:bg-green-50 rounded transition-colors border border-transparent';
                    thumbsDownBtn.className = 'thumbs-down-btn flex items-center space-x-1 px-2 py-1 text-xs text-red-600 hover:bg-red-50 rounded transition-colors border border-transparent';
                    
                    // Apply active state based on new vote state
                    if (!isUnvote && voteType === 'upvote') {
                        thumbsUpBtn.className += ' bg-green-100 border-green-300';
                    } else if (!isUnvote && voteType === 'downvote') {
                        thumbsDownBtn.className += ' bg-red-100 border-red-300';
                    }
                    
                    // Add a subtle animation effect
                    const activeButton = isUnvote ? null : (voteType === 'upvote' ? thumbsUpBtn : thumbsDownBtn);
                    if (activeButton) {
                        activeButton.style.transform = 'scale(0.95)';
                        setTimeout(() => {
                            activeButton.style.transform = 'scale(1)';
                        }, 150);
                    }
                }
                break;
            }
        }
    }

    revertVoteButtons(drugId) {
        // Find the result element for this drug and revert to cached state
        const resultElements = document.querySelectorAll('.search-result');
        for (const element of resultElements) {
            const drugIdElement = element.querySelector('[data-drug-id]');
            if (drugIdElement && drugIdElement.getAttribute('data-drug-id') === drugId) {
                const thumbsUpBtn = element.querySelector('.thumbs-up-btn');
                const thumbsDownBtn = element.querySelector('.thumbs-down-btn');
                
                if (thumbsUpBtn && thumbsDownBtn) {
                    // Reset both buttons to default state
                    thumbsUpBtn.className = 'thumbs-up-btn flex items-center space-x-1 px-2 py-1 text-xs text-green-600 hover:bg-green-50 rounded transition-colors border border-transparent';
                    thumbsDownBtn.className = 'thumbs-down-btn flex items-center space-x-1 px-2 py-1 text-xs text-red-600 hover:bg-red-50 rounded transition-colors border border-transparent';
                    
                    // Apply cached vote state
                    const currentVote = this.voteStates.get(drugId);
                    if (currentVote === 'upvote') {
                        thumbsUpBtn.className += ' bg-green-100 border-green-300';
                    } else if (currentVote === 'downvote') {
                        thumbsDownBtn.className += ' bg-red-100 border-red-300';
                    }
                }
                break;
            }
        }
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
        const clearBtn = document.getElementById('clearSearchBtn');
        
        if (show) {
            loading.classList.remove('hidden');
            clearBtn.classList.add('hidden'); // Hide clear button when loading
        } else {
            loading.classList.add('hidden');
            // Show clear button again if there's text in the input
            const searchInput = document.getElementById('searchInput');
            if (searchInput.value && searchInput.value.trim().length > 0) {
                clearBtn.classList.remove('hidden');
            }
        }
    }

    updateClearButtonVisibility(value) {
        const clearBtn = document.getElementById('clearSearchBtn');
        const loadingSpinner = document.getElementById('searchLoading');
        
        if (value && value.trim().length > 0) {
            // Show clear button when there's text
            clearBtn.classList.remove('hidden');
            // Hide loading spinner if it's showing
            loadingSpinner.classList.add('hidden');
        } else {
            // Hide clear button when input is empty
            clearBtn.classList.add('hidden');
        }
    }

    clearSearch() {
        const searchInput = document.getElementById('searchInput');
        const clearBtn = document.getElementById('clearSearchBtn');
        
        // Clear the input
        searchInput.value = '';
        
        // Hide clear button
        clearBtn.classList.add('hidden');
        
        // Clear any existing search results
        this.hideSearchResults();
        
        // Clear any pending search timeout
        if (this.searchTimeout) {
            clearTimeout(this.searchTimeout);
        }
        
        // Focus back on the input
        searchInput.focus();
        
        // Show a brief toast
        this.showToast('Search cleared', 'info');
    }

    async loadCommonUsesAsync(drugName, resultElement) {
        try {
            // Fetch common uses from backend
            const response = await fetch(`${this.apiBaseUrl}/drugs/common-uses?name=${encodeURIComponent(drugName)}`);
            
            if (response.ok) {
                const data = await response.json();
                if (data.common_uses && data.common_uses.length > 0) {
                    this.updateCommonUsesSection(resultElement, data.common_uses);
                }
            }
        } catch (error) {
            console.error('Error loading common uses:', error);
            // Remove skeleton on error
            const usesSection = resultElement.querySelector('.common-uses-section');
            if (usesSection) {
                usesSection.innerHTML = '';
            }
        }
    }

    updateCommonUsesSection(resultElement, commonUses) {
        const usesSection = resultElement.querySelector('.common-uses-section');
        if (usesSection) {
            usesSection.innerHTML = `
                <div class="mb-2">
                    <span class="text-xs font-medium text-gray-500">Common uses:</span>
                    <div class="flex flex-wrap gap-1 mt-1">
                        ${commonUses.map(use => 
                            `<span class="text-xs bg-green-100 text-green-800 px-2 py-1 rounded-full">${use}</span>`
                        ).join('')}
                    </div>
                </div>
            `;
        }
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
    
    revertVoteButtons(drugId, previousVoteType) {
        // Find the result element for this drug
        const resultElements = document.querySelectorAll('.search-result');
        for (const element of resultElements) {
            const drugIdElement = element.querySelector('[data-drug-id]');
            if (drugIdElement && drugIdElement.getAttribute('data-drug-id') === drugId) {
                const thumbsUpBtn = element.querySelector('.thumbs-up-btn');
                const thumbsDownBtn = element.querySelector('.thumbs-down-btn');
                
                if (thumbsUpBtn && thumbsDownBtn) {
                    // Reset both buttons to default state
                    thumbsUpBtn.className = 'thumbs-up-btn flex items-center space-x-1 px-2 py-1 text-xs text-green-600 hover:bg-green-50 rounded transition-colors border border-transparent';
                    thumbsDownBtn.className = 'thumbs-down-btn flex items-center space-x-1 px-2 py-1 text-xs text-red-600 hover:bg-red-50 rounded transition-colors border border-transparent';
                    
                    // Restore the previous vote state
                    if (previousVoteType === 'upvote') {
                        thumbsUpBtn.className += ' bg-green-100 border-green-300';
                    } else if (previousVoteType === 'downvote') {
                        thumbsDownBtn.className += ' bg-red-100 border-red-300';
                    }
                }
                break;
            }
        }
        
        // Restore the vote state in cache
        this.voteStates[drugId] = previousVoteType;
        this.saveVoteStates();
    }
}

// Missing Drug Functions
let currentMissingDrugRequest = null;

async function handleReportMissing() {
    const searchInput = document.getElementById('searchInput');
    const drugName = searchInput.value.trim();
    
    if (!drugName || drugName.length < 2) {
        alert('Please enter a drug name first');
        return;
    }
    
    // Reset selected result
    selectedApiResult = null;
    
    // Show missing drug flow
    const missingDrugFlow = document.getElementById('missingDrugFlow');
    const missingDrugSearching = document.getElementById('missingDrugSearching');
    const missingDrugResults = document.getElementById('missingDrugResults');
    const missingDrugNotFound = document.getElementById('missingDrugNotFound');
    const missingDrugSuccess = document.getElementById('missingDrugSuccess');
    
    missingDrugFlow.classList.remove('hidden');
    missingDrugSearching.classList.remove('hidden');
    missingDrugResults.classList.add('hidden');
    missingDrugNotFound.classList.add('hidden');
    missingDrugSuccess.classList.add('hidden');
    
    // Disable submit button
    const submitBtn = document.getElementById('addMissingDrugBtn');
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.classList.add('opacity-50', 'cursor-not-allowed');
    }
    
    try {
        const apiBaseUrl = window.rxVerifyApp ? window.rxVerifyApp.apiBaseUrl : 'http://localhost:8000';
        const response = await fetch(`${apiBaseUrl}/drugs/report-missing?drug_name=${encodeURIComponent(drugName)}&search_query=${encodeURIComponent(drugName)}`, {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (data.success) {
            currentMissingDrugRequest = data;
            
            // Hide searching
            missingDrugSearching.classList.add('hidden');
            
            if (data.api_search && data.api_search.found && data.api_search.results && data.api_search.results.length > 0) {
                // Show API results
                displayApiResults(data.api_search.results);
                missingDrugResults.classList.remove('hidden');
            } else {
                // Show not found
                missingDrugNotFound.classList.remove('hidden');
            }
        } else {
            throw new Error(data.message || 'Failed to report missing drug');
        }
    } catch (error) {
        console.error('Error reporting missing drug:', error);
        missingDrugSearching.classList.add('hidden');
        alert('Failed to search for drug. Please try again.');
    }
}

function formatDrugName(name) {
    if (!name || name.trim() === '') return name;
    
    // Words that should remain uppercase (units, abbreviations)
    const uppercaseWords = ['MG', 'ML', 'MCG', 'G', 'KG', 'MG/ML', 'MCG/ML', 'IU', 'MEQ', 'MMOL', 'L', 'ML/HR', 'MG/HR'];
    
    // Words that should remain lowercase (prepositions, articles)
    const lowercaseWords = ['of', 'the', 'and', 'or', 'in', 'on', 'at', 'to', 'for', 'with', 'by'];
    
    return name.split(' ').map((word, index) => {
        // Remove punctuation temporarily for processing
        const cleanWord = word.replace(/[.,;:!?()[\]{}'"]/g, '');
        const punctuation = word.replace(/[^.,;:!?()[\]{}'"]/g, '');
        
        // Check if it's a number or contains numbers (keep as is)
        if (/^\d+/.test(cleanWord) || /^\d+\.\d+/.test(cleanWord)) {
            return word;
        }
        
        // Check if it's an uppercase word (units, abbreviations)
        if (uppercaseWords.includes(cleanWord.toUpperCase())) {
            return cleanWord.toUpperCase() + punctuation;
        }
        
        // First word should always be capitalized
        if (index === 0) {
            return cleanWord.charAt(0).toUpperCase() + cleanWord.slice(1).toLowerCase() + punctuation;
        }
        
        // Check if it's a lowercase word (prepositions, articles)
        if (lowercaseWords.includes(cleanWord.toLowerCase())) {
            return cleanWord.toLowerCase() + punctuation;
        }
        
        // Default: capitalize first letter, lowercase rest
        return cleanWord.charAt(0).toUpperCase() + cleanWord.slice(1).toLowerCase() + punctuation;
    }).join(' ');
}

function displayApiResults(results) {
    const container = document.getElementById('missingDrugApiResults');
    container.innerHTML = '';
    
    // Add explanatory text with better contrast
    const explanation = document.createElement('div');
    explanation.className = 'mb-4 p-3 bg-blue-50 border border-blue-300 rounded-lg';
    explanation.innerHTML = `
        <p class="text-sm text-blue-900">
            <strong class="text-blue-900">Select the drug that matches what you're looking for:</strong> We found several possible matches in external databases. 
            Please select the one that best matches the drug you searched for, then click "Suggest to add to Database" below.
        </p>
    `;
    container.appendChild(explanation);
    
    results.forEach((result, index) => {
        const div = document.createElement('div');
        div.className = 'bg-white border-2 border-gray-300 rounded-lg p-4 cursor-pointer hover:border-green-500 hover:shadow-md transition-all duration-200';
        div.setAttribute('data-result-index', index);
        div.setAttribute('data-is-drug-result', 'true');
        
        const source = result.source || 'Unknown';
        const rawName = result.name || result.drug_name || 'Unknown';
        const name = formatDrugName(rawName);
        const rxcui = result.rxcui || result.rxnorm_id || '';
        
        div.innerHTML = `
            <div class="flex items-start justify-between">
                <div class="flex-1">
                    <div class="flex items-center gap-2">
                        <input type="radio" name="selectedDrug" value="${index}" class="w-4 h-4 text-green-600 focus:ring-green-500 focus:ring-2" aria-label="Select ${name}" />
                        <h5 class="font-semibold text-gray-900">${name}</h5>
                    </div>
                    <p class="text-sm text-gray-700 mt-1 ml-6">Source: ${source}</p>
                    ${rxcui ? `<p class="text-xs text-gray-600 mt-1 ml-6">RxCUI: ${rxcui}</p>` : ''}
                </div>
            </div>
        `;
        
        // Add click handler
        div.onclick = (e) => {
            // Don't trigger if clicking on radio button directly
            if (e.target.type !== 'radio') {
                selectApiResult(index, result, div);
            }
        };
        
        // Also handle radio button click
        const radio = div.querySelector('input[type="radio"]');
        if (radio) {
            radio.onclick = (e) => {
                e.stopPropagation();
                selectApiResult(index, result, div);
            };
        }
        
        container.appendChild(div);
    });
}

let selectedApiResult = null;

function selectApiResult(index, result, element) {
    // Remove previous selection (skip explanation div)
    document.querySelectorAll('#missingDrugApiResults > div[data-is-drug-result="true"]').forEach(div => {
        if (div !== element) {
            div.classList.remove('border-green-600', 'bg-green-100', 'ring-2', 'ring-green-500');
            div.classList.add('border-gray-300');
            // Reset text colors to default
            const nameEl = div.querySelector('h5');
            const sourceEl = div.querySelector('p.text-sm');
            const rxcuiEl = div.querySelector('p.text-xs');
            if (nameEl) nameEl.className = 'font-semibold text-gray-900';
            if (sourceEl) sourceEl.className = 'text-sm text-gray-700 mt-1 ml-6';
            if (rxcuiEl) rxcuiEl.className = 'text-xs text-gray-600 mt-1 ml-6';
            const radio = div.querySelector('input[type="radio"]');
            if (radio) {
                radio.checked = false;
            }
        }
    });
    
    // Update current selection with better contrast colors
    element.classList.remove('border-gray-300');
    element.classList.add('border-green-600', 'bg-green-50', 'ring-2', 'ring-green-500');
    
    // Update text colors for better contrast on selected background
    const nameEl = element.querySelector('h5');
    const sourceEl = element.querySelector('p.text-sm');
    const rxcuiEl = element.querySelector('p.text-xs');
    if (nameEl) nameEl.className = 'font-semibold text-gray-900';
    if (sourceEl) sourceEl.className = 'text-sm text-gray-800 mt-1 ml-6';
    if (rxcuiEl) rxcuiEl.className = 'text-xs text-gray-700 mt-1 ml-6';
    
    // Update radio button
    const radio = element.querySelector('input[type="radio"]');
    if (radio) {
        radio.checked = true;
    }
    
    selectedApiResult = result;
    
    // Enable submit button
    const submitBtn = document.getElementById('addMissingDrugBtn');
    if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.classList.remove('opacity-50', 'cursor-not-allowed');
    }
}

async function handleAddMissingDrug() {
    if (!currentMissingDrugRequest || !currentMissingDrugRequest.request_id) {
        alert('No request to submit');
        return;
    }
    
    if (!selectedApiResult) {
        alert('Please select a drug from the list above');
        return;
    }
    
    try {
        const apiBaseUrl = window.rxVerifyApp ? window.rxVerifyApp.apiBaseUrl : 'http://localhost:8000';
        const response = await fetch(`${apiBaseUrl}/drugs/missing/${currentMissingDrugRequest.request_id}/suggest`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(selectedApiResult)
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Show success message
            const missingDrugResults = document.getElementById('missingDrugResults');
            const missingDrugSuccess = document.getElementById('missingDrugSuccess');
            
            missingDrugResults.classList.add('hidden');
            missingDrugSuccess.classList.remove('hidden');
            
            // Show toast
            if (window.rxVerifyApp) {
                window.rxVerifyApp.showToast('Suggestion submitted! This drug will be reviewed by an admin.', 'success');
            }
        } else {
            throw new Error(data.message || 'Failed to submit suggestion');
        }
    } catch (error) {
        console.error('Error submitting suggestion:', error);
        alert('Failed to submit suggestion. Please try again.');
    }
}

async function handleRequestAddMissingDrug() {
    if (!currentMissingDrugRequest || !currentMissingDrugRequest.request_id) {
        alert('No request to submit');
        return;
    }
    
    // Show success message
    const missingDrugNotFound = document.getElementById('missingDrugNotFound');
    const missingDrugSuccess = document.getElementById('missingDrugSuccess');
    
    missingDrugNotFound.classList.add('hidden');
    missingDrugSuccess.classList.remove('hidden');
    
    // Show toast
    if (window.rxVerifyApp) {
        window.rxVerifyApp.showToast('Request submitted! This drug will be reviewed by an admin.', 'success');
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
