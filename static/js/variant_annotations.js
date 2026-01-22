// variant_annotations.js - Enhanced handling for textual variants

document.addEventListener("DOMContentLoaded", function() {
    // Initialize variant-specific functionality
    initVariantAnnotations();
    
    // Add CSS for textual variants if not already present
    addVariantStyles();
});

function addVariantStyles() {
    // Check if styles are already added
    if (document.getElementById('variant-annotation-styles')) return;
    
    const style = document.createElement('style');
    style.id = 'variant-annotation-styles';
    style.textContent = `
        /* Textual variant specific styles */
        .textual-variant {
            background-color: #FFE0B2;
            cursor: help;
            position: relative;
            border-radius: 4px;
            transition: background-color 0.3s ease;
        }
        
        .textual-variant:hover {
            background-color: #FFCC80;
        }
        
        /* Popup specific styles for variants */
        .variant-popup {
            position: absolute;
            background: white;
            border: 1px solid #FF9800;
            border-radius: 4px;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
            padding: 12px;
            z-index: 1000;
            max-width: 300px;
            font-size: 0.9em;
            visibility: hidden;
            opacity: 0;
            transition: opacity 0.2s ease-in-out;
        }
        
        .variant-popup.active {
            visibility: visible;
            opacity: 1;
        }
        
        .variant-popup-title {
            font-weight: 600;
            color: #E65100;
            margin-bottom: 8px;
            border-bottom: 1px solid #FFE0B2;
            padding-bottom: 4px;
        }
        
        .variant-popup-content {
            color: #333;
            line-height: 1.4;
        }
        
        .variant-popup-manuscript {
            font-style: italic;
            color: #666;
            margin-top: 8px;
            font-size: 0.85em;
        }
        
        /* Sidebar entry styling */
        .variant-entry {
            padding: 10px;
            margin-bottom: 10px;
            border-left: 3px solid #FF9800;
            background-color: #FFF8E1;
            cursor: pointer;
            transition: all 0.2s ease;
        }
        
        .variant-entry:hover {
            background-color: #FFE0B2;
            transform: translateX(3px);
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
    `;
    
    document.head.appendChild(style);
}

function initVariantAnnotations() {
    // Get all textual variant spans
    const variants = document.querySelectorAll('.textual-variant');
    let activePopup = null;
    
    variants.forEach(variant => {
        // Set up event listeners
        variant.addEventListener('click', function(event) {
            event.preventDefault();
            event.stopPropagation();
            showVariantPopup(event, this);
        });
        
        // Highlight corresponding sidebar entry on hover
        variant.addEventListener('mouseenter', function() {
            const annotationId = this.dataset.annotationId;
            const annotationType = this.dataset.annotationType;
            const sidebarEntry = document.querySelector(`.variant-entry[data-annotation-id="${annotationId}"][data-annotation-type="${annotationType}"]`);            if (sidebarEntry) {
                sidebarEntry.style.backgroundColor = '#FFCC80';
                sidebarEntry.style.transform = 'translateX(3px)';
            }
        });
        
        variant.addEventListener('mouseleave', function() {
            const annotationId = this.dataset.annotationId;
            const annotationType = this.dataset.annotationType;
            const sidebarEntry = document.querySelector(`.variant-entry[data-annotation-id="${annotationId}"][data-annotation-type="${annotationType}"]`);
            if (sidebarEntry) {
                sidebarEntry.style.backgroundColor = '#FFF8E1';
                sidebarEntry.style.transform = 'translateX(0)';
            }
        });
    });
    
    // Function to show variant popup
    function showVariantPopup(event, element) {
        // Remove any existing popup
        if (activePopup) {
            activePopup.remove();
            activePopup = null;
        }
        
        const annotationId = element.getAttribute('data-annotation-id');
        const annotationType = element.getAttribute('data-annotation-type') || 'variant';
        // Create popup
        const popup = document.createElement('div');
        popup.className = 'variant-popup';
        popup.innerHTML = '<div class="variant-popup-content">Loading variant information...</div>';
        document.body.appendChild(popup);
        
        // Position popup
        positionPopup(popup, element);
        
        // Show popup
        setTimeout(() => popup.classList.add('active'), 10);
        
        // Store as active popup
        activePopup = popup;
        
        // Fetch annotation data
        fetch(`/text-annotations/annotation/${annotationType}/${annotationId}/`)
            .then(response => {
                if (!response.ok) throw new Error('Network response was not ok');
                return response.json();
            })
            .then(data => {
                const variantTextEl = data.annotation ? `<p class="mb-1"><strong>${data.line_code}</strong> ${element.textContent}] ${data.annotation} <strong>${data.manuscript}</strong></p>` : '';
                const additionalNotesEl = data.notes ? `<div class="variant-popup-manuscript">${data.notes}</div>` : '';
                // Use specific template for variant display
                popup.innerHTML = `
                    <div class="variant-popup-title">Textual Variant</div>
                    <div class="variant-popup-content">${variantTextEl}</div>
                    ${additionalNotesEl}
                `;
                
                // Reposition after content loaded
                positionPopup(popup, element);
                
                // Highlight the corresponding sidebar entry
                const sidebarEntry = document.querySelector(`.variant-entry[data-annotation-id="${annotationId}"]`);
                if (sidebarEntry) {
                    sidebarEntry.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    sidebarEntry.style.backgroundColor = '#FFCC80';
                    setTimeout(() => {
                        sidebarEntry.style.backgroundColor = '#FFF8E1';
                    }, 1500);
                }
            })
            .catch(error => {
                console.error('Error loading annotation:', error);
                popup.innerHTML = `
                    <div class="variant-popup-title">Error</div>
                    <div class="variant-popup-content text-red-500">
                        Failed to load variant information
                    </div>
                `;
            });
    }
    
    // Function to position popup
    function positionPopup(popup, element) {
        const rect = element.getBoundingClientRect();
        const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
        const scrollLeft = window.pageXOffset || document.documentElement.scrollLeft;
        
        // Position above the element
        popup.style.left = `${rect.left + rect.width / 2 - popup.offsetWidth / 2}px`;
        popup.style.top = `${rect.top + scrollTop - popup.offsetHeight - 10}px`;
        
        // Check if popup would go off screen and adjust if needed
        const popupRect = popup.getBoundingClientRect();
        
        // Check right edge
        if (popupRect.right > window.innerWidth) {
            popup.style.left = `${window.innerWidth - popup.offsetWidth - 10}px`;
        }
        
        // Check left edge
        if (popupRect.left < 0) {
            popup.style.left = '10px';
        }
        
        // If would go above viewport, show below instead
        if (popupRect.top < 0) {
            popup.style.top = `${rect.bottom + scrollTop + 10}px`;
            popup.classList.add('below');
        } else {
            popup.classList.remove('below');
        }
    }
    
    // Close popup when clicking outside
    document.addEventListener('click', function(event) {
        if (
            activePopup && 
            !event.target.closest('.textual-variant') && 
            !event.target.closest('.variant-popup')
        ) {
            activePopup.remove();
            activePopup = null;
        }
    });
    
    // Close popup on escape key
    document.addEventListener('keydown', function(event) {
        if (event.key === 'Escape' && activePopup) {
            activePopup.remove();
            activePopup = null;
        }
    });
    
    // Sidebar entries interaction
    const sidebarEntries = document.querySelectorAll('.variant-entry');
    sidebarEntries.forEach(entry => {
        entry.addEventListener('click', function() {
            const annotationId = this.dataset.annotationId;
            const textElement = document.querySelector(`.textual-variant[data-annotation-id="${annotationId}"]`);
            
            if (textElement) {
                // Scroll to the element
                textElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
                
                // Highlight effect
                textElement.style.backgroundColor = '#FFA726';
                setTimeout(() => {
                    textElement.style.backgroundColor = '#FFE0B2';
                }, 1500);
                
                // Trigger the popup
                const clickEvent = new MouseEvent('click', {
                    bubbles: true,
                    cancelable: true,
                    view: window
                });
                textElement.dispatchEvent(clickEvent);
            }
        });
    });
}
