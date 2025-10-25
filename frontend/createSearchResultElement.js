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
        
        // Create voting section
        const votingDiv = document.createElement('div');
        votingDiv.className = 'flex items-center justify-between mt-3 pt-2 border-t border-gray-100';
        
        const votingButtons = document.createElement('div');
        votingButtons.className = 'flex items-center space-x-2';
        
        // Rating display
        const ratingDiv = document.createElement('div');
        ratingDiv.className = 'flex items-center space-x-2';
        
        const ratingScore = document.createElement('span');
        ratingScore.className = `px-2 py-1 rounded-full text-xs font-medium ${
            result.rating_score > 0 ? 'bg-green-100 text-green-800' :
            result.rating_score < 0 ? 'bg-red-100 text-red-800' :
            'bg-gray-100 text-gray-800'
        }`;
        ratingScore.textContent = `${result.rating_score.toFixed(1)} (${result.total_votes})`;
        ratingDiv.appendChild(ratingScore);
        
        // Upvote button
        const upvoteBtn = document.createElement('button');
        upvoteBtn.className = 'flex items-center space-x-1 px-3 py-1 bg-green-50 text-green-700 rounded-full hover:bg-green-100 transition-colors duration-200 text-sm';
        upvoteBtn.innerHTML = `
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 15l7-7 7 7"></path>
            </svg>
            <span>${result.upvotes}</span>
        `;
        upvoteBtn.onclick = () => this.voteOnDrug(result.drug_id, 'upvote');
        
        // Downvote button
        const downvoteBtn = document.createElement('button');
        downvoteBtn.className = 'flex items-center space-x-1 px-3 py-1 bg-red-50 text-red-700 rounded-full hover:bg-red-100 transition-colors duration-200 text-sm';
        downvoteBtn.innerHTML = `
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
            </svg>
            <span>${result.downvotes}</span>
        `;
        downvoteBtn.onclick = () => this.voteOnDrug(result.drug_id, 'downvote');
        
        votingButtons.appendChild(upvoteBtn);
        votingButtons.appendChild(downvoteBtn);
        
        // Source info
        const sourceDiv = document.createElement('div');
        sourceDiv.className = 'text-xs text-gray-500';
        sourceDiv.textContent = `Source: ${result.source}`;
        
        votingDiv.appendChild(votingButtons);
        votingDiv.appendChild(sourceDiv);
        
        // Use appendChild instead of innerHTML to preserve event listeners
        div.appendChild(nameDiv);
        if (brandNamesDiv) {
            const brandDiv = document.createElement('div');
            brandDiv.innerHTML = brandNamesDiv;
            div.appendChild(brandDiv);
        }
        div.appendChild(usesDiv);
        div.appendChild(votingDiv);
        
        // No click handler - these are just search results for feedback
        
        return div;
    }
