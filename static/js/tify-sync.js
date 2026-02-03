// tify-sync.js - Handles integration between Tify viewer and manuscript text
const TifySync = {
  viewer: null,
  manifestUrl: null,
  observer: null,
  currentFolio: null,
  manifestData: null,
  viewerReady: false,

  async initialize(containerId, manifestUrl) {
    console.log('Initializing TifySync with:', { containerId, manifestUrl });
    this.manifestUrl = manifestUrl;
    
    if (!manifestUrl) {
      console.log('No manifest URL provided, skipping initialization');
      return;
    }

    if (!this.manifestData) {
      // Fetch the manifest JSON
      try {
        const response = await fetch(this.manifestUrl);
        this.manifestData = await response.json();
      } catch (error) {
        console.error('Error fetching manifest:', error);
      }
    }
    
    // Initialize Tify viewer
    this.viewer = new Tify({
      container: `#${containerId}`,
      manifestUrl: manifestUrl,
      language: 'en',
      view: '', // Default to scan view
      optionsResetOnPageChange: ['pan'],
      urlQueryKey: null, // Disable URL parameter changes to avoid conflicts
    });

    this.viewer.ready.then(() => {
      console.log('Tify ready to change pages');
      this.viewerReady = true;
    });
    
    console.log('Tify viewer initialized');
    
    // Set up event listeners
    this.setupEventListeners();

    // resolve
    return true;
  },
  
  setupEventListeners() {
    // Listen for custom events from Tify
    // Note: Tify might emit certain events when page changes
    // If Tify doesn't provide built-in events, we'll poll for changes periodically
    const container = document.getElementById('tify-container');
    
    // Example: Check for page changes every second
    setInterval(() => {
      // Try to get current page from Tify API/DOM
      const currentPage = this.getCurrentPage();
      if (currentPage && currentPage !== this.currentPage) {
        this.currentPage = currentPage;
        console.log('Page changed to:', currentPage);
      }
    }, 1000);
  },
  
  navigateToFolio(folioNumber, retryCount = 0) {
    if (!this.viewerReady && retryCount < 5) {
      console.log(`Viewer not ready for ${folioNumber}, retrying... (${retryCount + 1})`);
      setTimeout(() => this.navigateToFolio(folioNumber, retryCount + 1), 1000);
      return;
    }

    if (!this.viewer || !this.manifestUrl || !folioNumber) {
      console.log('Cannot navigate: missing required data', {
        hasViewer: !!this.viewer,
        manifestUrl: this.manifestUrl,
        folioNumber
      });
      return;
    }

    try {
      console.log('Attempting to navigate to folio:', folioNumber);
      
      // Determine page number based on folio - this might require fetching
      // the manifest data and searching for the folio in labels
      this.fetchManifestAndNavigate(folioNumber);
    } catch (error) {
      console.error('Error navigating to folio:', error);
    }
  },
  
  async fetchManifestAndNavigate(folioNumber) {
    try {
      if (!this.manifestData) {
        const response = await fetch(this.manifestUrl);
        this.manifestData = await response.json();
      }
      const manifest = this.manifestData;

      // Extract the canvases
      const canvases = manifest.sequences[0].canvases;
      console.log('Found manifest with', canvases.length, 'canvases');
      
      // Try different patterns for matching folio numbers
      const folioPatterns = [
        new RegExp(`f.?${folioNumber}[rv]?`, 'i'),  // f12v, f.12v, f12r
        new RegExp(`${folioNumber}[rv]?`, 'i'),      // 12v, 12r
        new RegExp(`folio.?${folioNumber}`, 'i')     // folio 12, folio.12
      ];

      // Try to find matching canvas
      const pageIndex = canvases.findIndex(canvas => 
        folioPatterns.some(pattern => {
          const matchesLabel = pattern.test(canvas.label);
          const matchesMetadata = canvas.metadata && 
            canvas.metadata.some(m => pattern.test(m.value));
          
          if (matchesLabel || matchesMetadata) {
            console.log('Found match:', {
              pattern: pattern.toString(),
              label: canvas.label,
              metadata: canvas.metadata
            });
          }
          
          return matchesLabel || matchesMetadata;
        })
      );

      if (pageIndex !== -1) {
        console.log('Found matching canvas at index:', pageIndex);
        
        // Tify uses 1-based page numbers
        const tifyPageNumber = pageIndex + 1;
        
        // Navigate to the page using Tify's API
        // If Tify provides a direct method to go to a page:
        if (this.viewer && this.viewer.setPage) {
          this.viewer.setPage(tifyPageNumber);
        } else {
          // Otherwise, we might need to update options or use a workaround
          // For example, recreating the instance with different initial page:
          this.viewer = new Tify({
            container: '#tify-container',
            manifestUrl: this.manifestUrl,
            language: 'en',
            pages: [tifyPageNumber],
            view: '',
          });
        }
      } else {
        console.log('No matching canvas found for folio:', folioNumber);
      }
    } catch (error) {
      console.error('Error fetching manifest or navigating:', error);
    }
  },
  
  getCurrentPage() {
    // This method would need to be adapted based on how Tify exposes the current page
    // It might be available via the Tify API or we might need to examine the DOM
    
    // Example approaches:
    // 1. If Tify exposes an API method:
    if (this.viewer && this.viewer.getCurrentPage) {
      return this.viewer.getCurrentPage();
    }
    
    // 2. Try to find page indicator in the DOM
    const pageIndicator = document.querySelector('.tify-page-select');
    if (pageIndicator) {
      return pageIndicator.value;
    }
    
    return null;
  },

  setupIntersectionObserver(handleFolioChange) {
    console.log('Setting up Intersection Observer');
    
    this.observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        const folioElement = entry.target;
        const folioNumber = folioElement.dataset.folioNumber;
        
        if (entry.isIntersecting) {
          console.log('Folio entered viewport:', folioNumber, 'Intersection ratio:', entry.intersectionRatio);
          folioElement.style.backgroundColor = '#f0f9ff';
          handleFolioChange(folioNumber);
        } else {
          folioElement.style.backgroundColor = '';
        }
      });
    }, {
      root: null,
      rootMargin: '-20% 0px -60% 0px',
      threshold: [0, 0.25, 0.5, 0.75, 1]
    });

    // Observe all folio dividers
    const dividers = document.querySelectorAll('.folio-divider');
    console.log('Found folio dividers:', dividers.length);
    
    dividers.forEach(divider => {
      this.observer.observe(divider);
      console.log('Observing divider with folio:', divider.dataset.folioNumber);
    });
  }
};

// Initialize Alpine data
document.addEventListener('alpine:init', () => {
  Alpine.data('tifyViewer', () => ({
    hasKnownFolios: false,
    manifestUrl: null,
    currentFolio: null,
    viewerInitialized: false,

    async init() {
      console.log('Initializing Alpine tifyViewer component');
      this.hasKnownFolios = this.$el.dataset.hasKnownFolios === 'true';
      this.manifestUrl = this.$el.dataset.manifestUrl;
      
      console.log('TifyViewer initialized with:', {
        hasKnownFolios: this.hasKnownFolios,
        manifestUrl: this.manifestUrl
      });
      
      if (this.manifestUrl) {
        await TifySync.initialize('tify-container', this.manifestUrl);
        this.viewerInitialized = true;
        console.log('Tify viewer initialized');
        
        // Set up the observer after Alpine and Tify are initialized
        TifySync.setupIntersectionObserver((folioNumber) => {
          this.handleFolioChange(folioNumber);
        });

        TifySync.viewer.ready.then(() => {
          console.log('Tify is ready. Finding current folio...');
          const dividers = Array.from(
            document.querySelectorAll('.folio-divider'),
          );
          let activeFolio = null;
          // get the last divider that is ABOVE the top 15% of screen
          const readingLine = window.innerHeight * 0.15;
          for (let i = 0; i < dividers.length; i++) {
            const rect = dividers[i].getBoundingClientRect();
            if (rect.top <= readingLine) {
              activeFolio = dividers[i].dataset.folioNumber;
            } else {
              break;
            }
          }
          if (activeFolio) {
            console.log('Initial jump to folio:', activeFolio);
            this.handleFolioChange(activeFolio, true);
          } else {
            console.log(
              'No folio divider found above the current scroll position.',
            );
          }
        });
      }
    },

    handleFolioChange(folioNumber, force = false) {
      if (!force && this.currentFolio === folioNumber) {
        return;
      }
      console.log('Handling folio change:', folioNumber);
      this.currentFolio = folioNumber;
      if (this.viewerInitialized) {
        TifySync.navigateToFolio(folioNumber);
      } else {
        console.log('Viewer not yet initialized');
      }
    }
  }));
});

// Function to handle click on line codes
function navigateToFolio(event, element) {
  event.preventDefault();
  
  // Extract folio number from the data attribute or from parent folio-divider
  const folioNumber = element.dataset.folio || 
                      element.closest('.folio-divider')?.dataset.folioNumber;
  
  if (folioNumber) {
    console.log('Navigating to folio:', folioNumber);
    TifySync.navigateToFolio(folioNumber);
  }
}
