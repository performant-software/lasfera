// The following script handles the admin and back-end work for the text annotations.
document.addEventListener("DOMContentLoaded", function() {
    // First add the styles to document head in admin view
    addStyles();
    
    // Initialize the annotation system only after Trix is ready
    if (typeof Trix !== 'undefined') {
        initializeAnnotationSystem();
    } else {
        console.error('Trix editor not found. Make sure trix.js is loaded.');
    }
});

function addStyles() {
    const modalStyle = document.createElement("style");
    modalStyle.textContent = `
        .annotation-modal {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.5);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 10000;
        }
        
        .annotation-modal-content {
            background: white;
            padding: 20px;
            border-radius: 8px;
            width: 450px;
            max-width: 90%;
            max-height: 90vh;
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
        }
        
        .annotation-modal h3 {
            margin: 0 0 15px 0;
            font-size: 18px;
        }
        
        .annotation-modal textarea,
        .annotation-modal input[type="text"],
        .annotation-modal select {
            width: 100%;
            margin: 10px 0;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-family: inherit;
            box-sizing: border-box;
        }

        .annotation-modal textarea {
            min-height: 80px;
            resize: vertical;
            padding: 8px;
        }

        .annotation-modal-buttons {
            display: flex;
            justify-content: flex-end;
            gap: 10px;
            margin-top: 15px;
            padding-top: 10px;
            border-top: 1px solid #eee;
        }
        
        .annotation-modal button {
            padding: 8px 16px;
            border-radius: 4px;
            cursor: pointer;
            border: none;
            font-size: 14px;
        }
        
        .annotation-modal .btn-save {
            background: #007bff;
            color: white;
        }
        
        .annotation-modal .btn-cancel {
            background: #6c757d;
            color: white;
        }
        
        .selected-text-preview {
            background: #f8f9fa;
            padding: 10px;
            border-radius: 4px;
            margin-bottom: 10px;
            border: 1px solid #dee2e6;
            font-style: italic;
        }

        .variant-fields {
            padding: 10px;
            border: 1px solid #eee;
            border-radius: 4px;
            margin-bottom: 10px;
        }

        .variant-flex {
            display: flex;
            gap: 10px;
        }

        .variant-flex div {
            flex: 1;
        }

        .hidden {
            display: none !important;
        }
    `;
    document.head.appendChild(modalStyle);

    // Add annotation button icon styles
    const iconStyle = document.createElement('style');
    iconStyle.id = 'annotation-styles';
    iconStyle.textContent = `
        .trix-button--icon-note::before {
            background-image: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>');
        }
    `;
    document.head.appendChild(iconStyle);
}

function initializeAnnotationSystem() {
    // Wait for Trix editor to be initialized
    document.addEventListener('formset:added', () => {
        // target the toolbar for the stanza_text field's rich text editor
        const toolbar = document.querySelector('.field-stanza_text trix-toolbar .trix-button-row');
        if (toolbar && !toolbar.querySelector('[data-trix-action="addAnnotation"]')) {
            addAnnotationButton(toolbar);
        } else if (!toolbar) {
            console.error('Trix toolbar not found');
            return;
        }
    });
}

function addAnnotationButton(toolbar) {
    const annotationGroup = document.createElement('span');
    annotationGroup.className = 'trix-button-group';
    annotationGroup.setAttribute('data-trix-button-group', 'annotation-tools');

    const annotateButton = document.createElement('button');
    annotateButton.type = 'button';
    annotateButton.className = 'trix-button trix-button--icon trix-button--icon-note';
    annotateButton.setAttribute('data-trix-action', 'addAnnotation');
    annotateButton.title = 'Add Annotation';

    annotationGroup.appendChild(annotateButton);
    toolbar.appendChild(annotationGroup);

    // Add click handler
    annotateButton.addEventListener('click', handleAnnotationClick);
}

function getStanzaId() {
    const urlMatch = window.location.pathname.match(/\/(stanza|stanzatranslated)\/(\d+)/);
    if (urlMatch) return urlMatch[2];

    const form = document.querySelector("#stanza_form, #stanzatranslated_form");
    if (form) {
        const objectId = form.getAttribute("data-object-id") || 
                        form.querySelector('input[name="object_id"]')?.value;
        if (objectId) return objectId;
    }

    const urlParams = new URLSearchParams(window.location.search);
    const objectId = urlParams.get("object_id");
    if (objectId) return objectId;

    const breadcrumbs = document.querySelector(".breadcrumbs");
    if (breadcrumbs) {
        const match = breadcrumbs.textContent.match(/Stanza\s+(\d+)/);
        if (match) return match[1];
    }

    const hiddenId = document.querySelector('input[name="stanza_id"], input[name="id"]')?.value;
    if (hiddenId) return hiddenId;

    console.error("Could not find stanza ID. URL:", window.location.href);
    return null;
}

function getAvailableAnnotationTypes() {
    // pull annotation types currently being added to populate list of options
    const types = [
        {
            selector: '.inline-group[id*="editorialnote"]',
            value: 'note',
            label: 'Editorial Note',
        },
        {
            selector: '.inline-group[id*="textualvariant"]',
            value: 'variant',
            label: 'Textual Variant',
        },
        {
            selector: '.inline-group[id*="crossreference"]',
            value: 'reference',
            label: 'Cross Reference',
        },
    ];

    return types
        .filter(({ selector }) => {
            const inline = document.querySelector(selector);
            if (!inline) return false;

            // limit to only those being newly added
            return Array.from(inline.querySelectorAll('.form-row:not(.empty-form)')).some(row => {
                const idInput = row.querySelector('input[type="hidden"][name$="-id"]');
                const isNew = idInput && !idInput.value;
                return isNew;
            });
        })
        .map(({ value, label }) => ({ value, label }));
}

function getManuscriptOptions() {
    // get manuscript labels and values from the TextualVariant formset:
    // look for any select input ending in '-manuscript' within the admin form
    const sourceSelect = document.querySelector('select[name$="-manuscript"]');

    if (!sourceSelect) {
        return '<option value="">-- Manual Entry Required --</option>';
    }

    // return the innerHTML (the <options>) directly
    return sourceSelect.innerHTML;
}

function handleAnnotationClick(event) {
    event.preventDefault();

    const editor = document.querySelector("trix-editor").editor;
    const selectedRange = editor.getSelectedRange();

    if (selectedRange[0] === selectedRange[1]) {
        alert("Please select some text to annotate");
        return;
    }

    const availableTypes = getAvailableAnnotationTypes();

    if (availableTypes.length === 0) {
        alert("No annotations currently being added. Click 'Add another' at the bottom of the list of the annotation type you want to add.");
        return;
    }
    const optionsHtml = availableTypes.map(t => 
        `<option value="${t.value}">${t.label}</option>`
    ).join('');
    const isVariantSelected = availableTypes.length === 1 && availableTypes[0].value === 'variant';
    const variantDisplayClass = isVariantSelected ? '' : 'hidden';
    const manuscriptOptions = getManuscriptOptions();

    const selectedText = editor.getDocument().getStringAtRange(selectedRange);
    const stanzaId = getStanzaId();

    if (!stanzaId) {
        alert("Could not determine which stanza to annotate");
        return;
    }

    // Create and append modal
    const modal = document.createElement("div");
    modal.className = "annotation-modal";
    modal.innerHTML = `
        <div class="annotation-modal-content">
            <h3>Add Annotation</h3>
            <div class="selected-text-preview">
                Selected text: <strong>${selectedText}</strong>
            </div>
            <label for="annotation-type">Annotation Type</label>
            <select id="annotation-type" ${availableTypes.length === 1 ? 'disabled' : ''}>
                ${optionsHtml}
            </select>
            <label for="annotation-text" id="main-text-label">Annotation Content</label>
            <textarea id="annotation-text" 
                placeholder="Enter your annotation..."
                autofocus></textarea>
            <div id="variant-fields-container" class="variant-fields ${variantDisplayClass}">
                <label for="variant-manuscript">Manuscript (Siglum)</label>
                <select id="variant-manuscript">
                    ${manuscriptOptions}
                </select>
                
                <label for="variant-significance">Significance</label>
                <select id="variant-significance">
                    <option value="0">0</option>
                    <option value="1">1</option>
                    <option value="2">2</option>
                    <option value="3">3</option>
                </select>

                <div class="variant-flex">
                    <div>
                        <label for="variant-id">Variant ID</label>
                        <input type="text" id="variant-id" placeholder="e.g. T00035">
                    </div>
                    <div>
                        <label for="variant-editor">Editor Initials</label>
                        <input type="text" id="variant-editor" placeholder="e.g. LI">
                    </div>
                </div>
            </div>
            <div class="annotation-modal-buttons">
                <button type="button" class="btn-cancel">Cancel</button>
                <button type="button" class="btn-save">Save</button>
            </div>
        </div>
    `;

    document.body.appendChild(modal);
    const typeSelect = modal.querySelector("#annotation-type");
    const variantContainer = modal.querySelector("#variant-fields-container");
    const mainTextLabel = modal.querySelector("#main-text-label");
    const textarea = modal.querySelector("#annotation-text");

    // Toggle fields logic
    function updateFieldVisibility() {
        const type = typeSelect.value;
        if (type === 'variant') {
            variantContainer.classList.remove('hidden');
            mainTextLabel.textContent = "Variant text";
            textarea.placeholder = "Enter the variant text here...";
        } else {
            variantContainer.classList.add('hidden');
            mainTextLabel.textContent = "Annotation content";
            textarea.placeholder = "Enter your annotation...";
        }
    }
    typeSelect.addEventListener('change', updateFieldVisibility);
    updateFieldVisibility();

    // Focus the textarea
    setTimeout(() => {
        if (textarea) {
            textarea.focus();
        }
    }, 100);

    // Handle modal buttons
    modal.querySelector(".btn-cancel").addEventListener("click", () => {
        modal.remove();
    });

    modal.querySelector(".btn-save").addEventListener("click", () => {
        const annotationText = modal.querySelector("#annotation-text").value;
        const annotationType = modal.querySelector("#annotation-type").value;

        if (!annotationText.trim()) {
            alert("Please enter an annotation");
            return;
        }

        // Get CSRF token
        const csrfToken = document.querySelector("[name=csrfmiddlewaretoken]")?.value;
        if (!csrfToken) {
            console.error("No CSRF token found");
            alert("Security token missing");
            return;
        }

        // Prepare the data
        const formData = new FormData();
        formData.append("model_type", 
            window.location.pathname.includes("stanzatranslated") ? "stanzatranslated" : "stanza"
        );
        formData.append("stanza_id", stanzaId);
        formData.append("selected_text", selectedText);
        formData.append("annotation", annotationText);
        formData.append("annotation_type", annotationType);
        formData.append("from_pos", selectedRange[0]);
        formData.append("to_pos", selectedRange[1]);
        formData.append("csrfmiddlewaretoken", csrfToken);
        if (annotationType === 'variant') {
            formData.append("manuscript_id", modal.querySelector("#variant-manuscript").value);
            formData.append("significance", modal.querySelector("#variant-significance").value);
            formData.append("variant_id", modal.querySelector("#variant-id").value);
            formData.append("editor_initials", modal.querySelector("#variant-editor").value);
        }

        // Add loading state to save button
        const saveButton = modal.querySelector(".btn-save");
        const originalButtonText = saveButton.textContent;
        saveButton.textContent = "Saving...";
        saveButton.disabled = true;

        fetch("/text-annotations/create/", {
            method: "POST",
            body: formData,
            headers: {
                "X-Requested-With": "XMLHttpRequest",
            },
            credentials: "same-origin", // Important for CSRF
        })
        .then(response => {
            return response.json().then(data => ({ status: response.status, data }));
        })
        .then(({ status, data }) => {
            if (status === 200 && data.success) {
                // Create the annotated span with proper attributes and styling
                editor.setSelectedRange(selectedRange);

                // Close the modal
                modal.remove();

                // Show success message
                const successMessage = document.createElement("div");
                successMessage.className = "annotation-success-message";
                successMessage.textContent = "Annotation saved successfully";
                successMessage.style.cssText = `
                    position: fixed;
                    top: 20px;
                    right: 20px;
                    background: #28a745;
                    color: white;
                    padding: 10px 20px;
                    border-radius: 4px;
                    z-index: 10000;
                `;
                document.body.appendChild(successMessage);
                setTimeout(() => successMessage.remove(), 3000);
            } else {
                throw new Error(data.error || "Failed to save annotation");
            }
        })
        .catch(error => {
            console.error("Error saving annotation:", error);
            saveButton.textContent = originalButtonText;
            saveButton.disabled = false;
            alert("Failed to save annotation. Please try again.");
        });
    });
}
