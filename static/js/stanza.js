// Handle toggling line codes
(function() {
  const lineCodeDisplay = document.getElementById("lineCodeDisplay");
  if (lineCodeDisplay) {
    lineCodeDisplay.addEventListener("change", function () {
      const mode = this.value; // "hidden", "shortened", or "full"
      updateLineCodeDisplay(mode, this);
    });
  }
  const handleHash = () => {
    const hash = window.location.hash;
    if (hash) {
      const id = decodeURIComponent(hash.substring(1));
      const target = document.getElementById(id);
      if (target) {
        this.updateLineCodeDisplay("full", lineCodeDisplay);
      }
    }
  };
  window.addEventListener("hashchange", handleHash);
  handleHash();
})();

// Return to top button
window.addEventListener("scroll", function () {
  const returnToTop = document.getElementById("return-to-top");
  if (!returnToTop) return;
  
  const top = document.getElementById("top");
  if (!top) return;
  
  const distanceFromTop = top.getBoundingClientRect().top;

  // Show the button after the #top anchor is 100px above the viewport
  if (distanceFromTop < -100) {
    returnToTop.classList.remove("opacity-0", "invisible");
    returnToTop.classList.add("opacity-100");
  } else {
    returnToTop.classList.remove("opacity-100");
    returnToTop.classList.add("opacity-0", "invisible");
  }
});

function updateLineCodeDisplay(mode, selectElement) {
  const lineCodeLinks = document.querySelectorAll("a.line-code");
  lineCodeLinks.forEach((a) => {
    const span = a.querySelector(".line-text");
    const fullCode = a.id;

    if (mode === "shortened") {
      // Show only last part of line code (e.g., "1" from "01.01.01")
      const parts = fullCode.split(".");
      span.textContent = parseInt(parts[parts.length - 1]);
    } else {
      span.textContent = fullCode;
    }

    if (mode === "hidden") {
      // Hide line codes
      a.classList.add("sr-only");
    } else {
      a.classList.remove("sr-only");
    }
  });
  if (selectElement && mode) {
    selectElement.value = mode;
  }
}
