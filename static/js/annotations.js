// The following script provides the front-end view for the annotated text.
document.addEventListener("DOMContentLoaded", function () {
  // Add styles for annotations and popup
      const style = document.createElement("style");
      style.textContent = `
        .annotated-text {
            background-color: #A8DCD9;
            cursor: help;
            position: relative;
            color: #1A1A1A;
        }

        .annotation-popup {
            position: absolute;
            background: white;
            border: 1px solid #ddd;
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

        .annotation-popup.active {
            visibility: visible;
            opacity: 1;
        }

        .annotation-popup::before {
            content: '';
            position: absolute;
            bottom: -8px;
            left: 50%;
            transform: translateX(-50%);
            border-width: 8px 8px 0;
            border-style: solid;
            border-color: white transparent transparent;
            z-index: 1;
        }

        .annotation-popup::after {
            content: '';
            position: absolute;
            bottom: -9px;
            left: 50%;
            transform: translateX(-50%);
            border-width: 9px 9px 0;
            border-style: solid;
            border-color: #ddd transparent transparent;
            z-index: 0;
        }

        .annotation-type {
            font-size: 0.8em;
            color: #666;
            text-transform: uppercase;
            margin-bottom: 6px;
        }

        .annotation-content {
            color: #333;
            line-height: 1.4;
        }

        .annotation-loading {
            color: #666;
            font-style: italic;
        }
        /* Link styles in annotation popup */
        .annotation-content a {
            color: #2563eb;
            text-decoration: none;
            border-bottom: 1px solid #2563eb;
            padding-bottom: 1px;
            transition: all 0.2s ease;
        }

        .annotation-content a:hover {
            color: #1d4ed8;
            border-bottom-color: #1d4ed8;
            background-color: rgba(37, 99, 235, 0.1);
        }

        .annotation-content a:focus {
            outline: 2px solid #2563eb;
            outline-offset: 2px;
            border-radius: 2px;
        }

        .annotation-content a:active {
            color: #1e40af;
            border-bottom-color: #1e40af;
        }

        /* External link indicator */
        .annotation-content a[href^="http"]::after {
            content: "↗";
            display: inline-block;
            margin-left: 2px;
            font-size: 0.8em;
            transform: translateY(-1px);
        }

        .annotation-loading {
            color: #666;
            font-style: italic;
        }
    `;
      document.head.appendChild(style);

  // Keep track of active popup
      let activePopup = null;

  // Function to position popup
      function positionPopup(popup, element) {
        const rect = element.getBoundingClientRect();
        const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
        const scrollLeft =
          window.pageXOffset || document.documentElement.scrollLeft;

    // Position above the element
        popup.style.left = `${rect.left + rect.width / 2 - popup.offsetWidth / 2}px`;
        popup.style.top = `${rect.top + scrollTop - popup.offsetHeight - 10}px`;

    // Check if popup would go off screen
        const popupRect = popup.getBoundingClientRect();

    // Check right edge
        if (popupRect.right > window.innerWidth) {
          popup.style.left = `${window.innerWidth - popup.offsetWidth - 10}px`;
        }

    // Check left edge
        if (popupRect.left < 0) {
          popup.style.left = "10px";
        }

    // If would go above viewport, show below instead
        if (popupRect.top < 0) {
          popup.style.top = `${rect.bottom + scrollTop + 10}px`;
          popup.classList.add("below");
        } else {
          popup.classList.remove("below");
        }
      }

      window.showAnnotation = function (event, element) {
        event.preventDefault();
        event.stopPropagation();

    // Remove any existing popup
        if (activePopup) {
          activePopup.remove();
          activePopup = null;
        }

        const annotationId = element.getAttribute("data-annotation-id");
        const annotationType = element.getAttribute("data-annotation-type");

        const typeMap = {
            "note": "Editorial Note",
            "reference": "Cross Reference",
            "variant": "Textual Variant",
        }

        // Create popup for non-variant annotations (variants handled elsewhere)
        if (annotationType !== "variant") {
            const popup = document.createElement("div");
            popup.className = "annotation-popup";
            popup.dataset.annotationId = annotationId;
            popup.dataset.annotationType = annotationType;
            popup.innerHTML = '<div class="annotation-loading">Loading...</div>';
            document.body.appendChild(popup);

            // Position popup
            positionPopup(popup, element);

            // Show popup
            setTimeout(() => popup.classList.add("active"), 10);

            // Store as active popup
            activePopup = popup;

            fetch(`/text-annotations/annotation/${annotationType}/${annotationId}/`)
            .then((response) => {
                if (!response.ok) throw new Error("Network response was not ok");
                return response.json();
            })
            .then((data) => {
                popup.innerHTML = `
                        <div class="annotation-type">${typeMap[data.annotation_type] || data.annotation_type}</div>
                        <div class="annotation-content">${data.annotation}</div>
                    `;
                // Reposition after content loaded
                positionPopup(popup, element);
            })
            .catch((error) => {
                console.error("Error loading annotation:", error);
                popup.innerHTML = `
                        <div class="annotation-content text-red-500">
                            Failed to load annotation
                        </div>
                    `;
            });
        }
      };

  // Close popup when clicking outside
      document.addEventListener("click", function (event) {
        if (
          activePopup &&
          !event.target.closest(".annotated-text") &&
          !event.target.closest(".annotation-popup")
        ) {
          activePopup.remove();
          activePopup = null;
        }
      });

  // Close popup on escape key
      document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && activePopup) {
          activePopup.remove();
          activePopup = null;
        }
      });

  // Update popup position on scroll
      window.addEventListener("scroll", function () {
        if (activePopup) {
          const annotatedElement = document.querySelector(
            `.annotated-text[data-annotation-id="${activePopup.dataset.annotationId}"][data-annotation-type="${activePopup.dataset.annotationType}"]`
          );
          if (annotatedElement) {
            positionPopup(activePopup, annotatedElement);
          }
        }
      });

  // Update popup position on window resize
      window.addEventListener("resize", function () {
        if (activePopup) {
          const annotatedElement = document.querySelector(
            `.annotated-text[data-annotation-id="${activePopup.dataset.annotationId}"][data-annotation-type="${activePopup.dataset.annotationType}"]`
          );
          if (annotatedElement) {
            positionPopup(activePopup, annotatedElement);
          }
        }
      });
    });

    // Function to update the manuscript content
    // Function to apply annotations to text
function annotateText(text, annotations) {
    if (!annotations || annotations.length === 0) return text;
    
    // Sort annotations by starting position
    const sortedAnnotations = [...annotations].sort((a, b) => a.from_pos - b.from_pos);
    
    let result = text;
    let offset = 0;
    
    sortedAnnotations.forEach(ann => {
        const startPos = parseInt(ann.from_pos) + offset;
        const endPos = parseInt(ann.to_pos) + offset;
        
        const before = result.slice(0, startPos);
        const annotatedPart = result.slice(startPos, endPos);
        const after = result.slice(endPos);
        
        const annotatedHtml = `<span class="annotated-text" 
            data-annotation-id="${ann.id}" 
            data-annotation-type="${ann.annotation_type}"
            onclick="showAnnotation(event, this)">${annotatedPart}</span>`;
            
        result = before + annotatedHtml + after;
        offset += annotatedHtml.length - annotatedPart.length;
    });
    
    return result;
}

// Function to handle line code display
function updateLineCodeDisplay(mode) {
    const lineCodes = document.querySelectorAll('.line-code');
    lineCodes.forEach(code => {
        switch(mode) {
            case 'shortened':
                // Show only last part of line code (e.g., "01" from "01.01.01")
                const shortCode = code.textContent.trim().split('.').pop();
                code.style.display = '';
                code.querySelector('span').textContent = shortCode;
                break;
            case 'hidden':
                code.style.display = 'none';
                break;
            default: // 'full'
                code.style.display = '';
                // Restore original line code if needed
                const originalCode = code.querySelector('a').id;
                code.querySelector('span').textContent = originalCode;
        }
    });
}

