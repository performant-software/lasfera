// canvas_linking.js - Admin page for linking a manuscript's folios to its IIIF canvases
(function () {
  const readJson = (id) => JSON.parse(document.getElementById(id).textContent);
  const folios = readJson('canvas-folios');
  const submitted = readJson('canvas-submitted');
  const manifestUrl = readJson('canvas-manifest-url');
  const canCreate = readJson('canvas-can-create');

  const form = document.getElementById('canvas-form');
  const statusEl = document.getElementById('canvas-status');
  const noticesEl = document.getElementById('canvas-notices');
  const tbody = document.querySelector('#canvas-table tbody');
  const summaryEl = document.getElementById('canvas-summary');
  const filterEl = document.getElementById('canvas-filter');
  const saveButton = document.getElementById('canvas-save');
  const fillButton = document.getElementById('canvas-fill');
  const viewer = document.getElementById('canvas-viewer');
  const viewerTitle = document.getElementById('canvas-viewer-title');
  const viewerFrame = viewer.querySelector('.canvas-viewer-image');
  const viewerImage = viewerFrame.querySelector('img');
  const viewerFull = document.getElementById('canvas-viewer-full');

  // Same normalization as manuscript.utils.normalize_folio_label, so that
  // e.g. "Carta: 12 recto", "f. 12r" and "12r" are treated as the same folio
  const FOLIO_LABEL_PREFIX = /^(?:carta|folio|fol|ff|f|c)\s*[.:]?\s*(?=\d)/;
  function normalizeFolioLabel(label) {
    if (!label) return '';
    let value = label.trim().toLowerCase();
    value = value.replace(/\brecto\b/g, 'r').replace(/\bverso\b/g, 'v');
    value = value.replace(FOLIO_LABEL_PREFIX, '');
    return value.replace(/[\s.]/g, '');
  }
  const folioKey = (number) => normalizeFolioLabel(number) || number.trim().toLowerCase();

  // The folio number in a manifest label in its usual form, e.g. "53r" from
  // "Carta: 53r" or "53 recto", or null if the label doesn't contain one
  function folioNumberFromLabel(label) {
    const match = normalizeFolioLabel(label).match(/^(\d+)([rv])$/);
    if (match) return `${Number(match[1])}${match[2]}`;
    // roman-numbered flyleaves, e.g. "Ir", when that's the whole label
    if (/^[ivxlc]+[rv]$/i.test(label.trim())) return label.trim();
    return null;
  }

  // The folio numbers in a manifest label: one as above, or both from a label
  // for an image of two folios, e.g. "13v" and "14r" from "13v-14r", unless a
  // single folio record has that whole number
  function folioNumbersFromLabel(label) {
    const number = folioNumberFromLabel(label);
    if (number) return [number];
    const key = normalizeFolioLabel(label);
    const pair = key.match(/^(\d+[rv])-(\d+[rv])$/);
    if (!pair || foliosByKey.has(key)) return [];
    return [folioNumberFromLabel(pair[1]), folioNumberFromLabel(pair[2])];
  }

  // Flatten a IIIF v2 or v3 label into a plain string
  function labelToString(label) {
    if (!label) return '';
    if (typeof label === 'string') return label;
    if (Array.isArray(label)) return label.map(labelToString).join(' ');
    if (label['@value']) return String(label['@value']);
    return Object.values(label).map(labelToString).join(' ');
  }

  function serviceId(service) {
    if (Array.isArray(service)) service = service[0];
    return service ? service['@id'] || service.id : null;
  }

  function thumbnailId(thumbnail) {
    if (Array.isArray(thumbnail)) thumbnail = thumbnail[0];
    if (!thumbnail) return null;
    return typeof thumbnail === 'string' ? thumbnail : thumbnail['@id'] || thumbnail.id;
  }

  // Canvases of a IIIF v2 or v3 manifest, matching manuscript.utils.get_canvases
  function getCanvases(manifest) {
    const raw = manifest.sequences ? manifest.sequences[0].canvases || [] : manifest.items || [];
    return raw.map((canvas, index) => {
      let resource = null;
      if (canvas.images && canvas.images.length) {
        resource = canvas.images[0].resource || null;
      } else if (canvas.items && canvas.items.length) {
        try {
          resource = canvas.items[0].items[0].body;
          if (Array.isArray(resource)) resource = resource[0];
        } catch (e) {
          resource = null;
        }
      }
      const imageService = resource ? serviceId(resource.service) : null;
      const resourceId = resource ? resource['@id'] || resource.id : null;
      return {
        index,
        id: canvas['@id'] || canvas.id,
        label: labelToString(canvas.label).trim(),
        image_id: imageService || resourceId || null,
        thumbnail: imageService
          ? `${imageService}/full/!200,200/0/default.jpg`
          : thumbnailId(canvas.thumbnail) || resourceId,
        large: imageService ? `${imageService}/full/!1200,1200/0/default.jpg` : resourceId,
        // some manifests' resource IDs aren't images, so prefer the image service
        full: imageService ? `${imageService}/full/max/0/default.jpg` : resourceId,
      };
    });
  }

  const foliosByCanvas = new Map();
  const foliosByKey = new Map();
  for (const folio of folios) {
    if (folio.canvas_id) {
      if (!foliosByCanvas.has(folio.canvas_id)) foliosByCanvas.set(folio.canvas_id, []);
      foliosByCanvas.get(folio.canvas_id).push(folio);
    }
    if (!folio.number) continue;
    const key = folioKey(folio.number);
    if (!foliosByKey.has(key)) foliosByKey.set(key, []);
    foliosByKey.get(key).push(folio);
  }

  // an image's folios in order, e.g. 99v before 100r
  for (const linked of foliosByCanvas.values()) {
    linked.sort((a, b) => a.number.localeCompare(b.number, undefined, { numeric: true }));
  }
  const linkedFolios = (canvasId) => foliosByCanvas.get(canvasId) || [];

  let rows = [];
  let canvasPositions = new Map();
  let dirty = false;
  let fillNote = '';

  // the text can only turn to folios with both ends of a line range
  const hasLineRange = (folio) => !!(folio.line_start && folio.line_end);

  function folioDetails(folio) {
    const details = [];
    if (folio.line_start) details.push(`lines ${folio.line_start} → ${folio.line_end || 'end'}`);
    if (folio.toponyms) details.push(`${folio.toponyms} toponym${folio.toponyms === 1 ? '' : 's'}`);
    return details.join(' · ');
  }

  function canvasName(canvasId) {
    return canvasPositions.has(canvasId)
      ? `image ${canvasPositions.get(canvasId) + 1}`
      : 'an image no longer in the manifest';
  }

  function addNote(row, text, kind = '') {
    const note = document.createElement('span');
    note.className = `canvas-note ${kind ? 'is-' + kind : ''}`;
    note.textContent = text;
    row.notesEl.appendChild(note);
  }

  // The folios entered for a row, leaving out blanks and repeats
  function rowEntries(row) {
    const entries = new Map();
    for (const input of row.inputs) {
      const value = input.value.trim();
      if (value && !entries.has(folioKey(value))) entries.set(folioKey(value), value);
    }
    return [...entries].map(([key, value]) => ({ key, value }));
  }

  function setRowFolios(row, numbers) {
    numbers.forEach((number, i) => {
      if (i >= row.inputs.length) addFolioInput(row);
      row.inputs[i].value = number;
    });
  }

  // Work out what saving would do for each row, and flag conflicts
  function update() {
    const entriesByKey = new Map();
    for (const row of rows) {
      for (const { key } of rowEntries(row)) {
        if (!entriesByKey.has(key)) entriesByKey.set(key, []);
        entriesByKey.get(key).push(row);
      }
    }

    let linked = 0;
    let changed = 0;
    let problems = 0;
    for (const row of rows) {
      const entries = rowEntries(row);
      const current = linkedFolios(row.canvas.id);
      row.notesEl.replaceChildren();
      if (row.suggestion) row.suggestion.hidden = entries.length > 0;
      row.addButton.hidden = row.inputs.some((input) => !input.value.trim());
      row.isChanged = false;
      row.hasProblem = false;

      const entered = new Set();
      let isLinked = false;
      for (const { key, value } of entries) {
        const matches = foliosByKey.get(key) || [];
        const sameEntry = entriesByKey.get(key).filter((other) => other !== row);
        if (sameEntry.length) {
          row.hasProblem = true;
          const images = sameEntry.map((other) => other.canvas.index + 1).join(', ');
          addNote(row, `${value}: also entered for image ${images}. Each folio can be linked to one image.`, 'problem');
        }
        if (matches.length > 1) {
          row.hasProblem = true;
          const numbers = matches.map((folio) => `"${folio.number}"`).join(', ');
          addNote(row, `${value}: matches several folio records (${numbers}). Merge or renumber those folio records first.`, 'problem');
        } else if (matches.length === 1) {
          const folio = matches[0];
          entered.add(folio.id);
          if (folio.canvas_id === row.canvas.id) {
            isLinked = true;
            addNote(row, `Linked to folio ${folio.number}.`, 'info');
          } else {
            row.isChanged = true;
            if (folio.canvas_id) {
              addNote(row, `Will move folio ${folio.number} here from ${canvasName(folio.canvas_id)}.`);
            } else {
              addNote(row, `Will link folio ${folio.number}.`);
            }
          }
          const details = folioDetails(folio);
          if (details) addNote(row, details, 'info');
          if (!hasLineRange(folio)) {
            addNote(row, `Folio ${folio.number} has no line range.`, 'warning');
          }
        } else if (!canCreate) {
          row.hasProblem = true;
          addNote(row, `There is no folio record "${value}", and you don't have permission to add folio records.`, 'problem');
        } else {
          row.isChanged = true;
          addNote(row, `Will create a new folio record "${value}".`);
          addNote(row, "It will need a line range before the text can turn to this image.", 'warning');
        }
      }
      for (const folio of current) {
        if (!entered.has(folio.id)) {
          row.isChanged = true;
          addNote(row, `Will unlink folio ${folio.number}.`);
        }
      }
      if (isLinked) linked += 1;

      if (row.labelCount > 1) {
        addNote(row, `The manifest label "${row.canvas.label}" appears on ${row.labelCount} images.`, 'info');
      }
      row.tr.classList.toggle('is-changed', row.isChanged && !row.hasProblem);
      row.tr.classList.toggle('has-problem', row.hasProblem);
      if (row.isChanged) changed += 1;
      if (row.hasProblem) problems += 1;
    }

    summaryEl.textContent =
      `${rows.length} images · ${linked} linked · ${changed} unsaved change${changed === 1 ? '' : 's'}` +
      (problems ? ` · ${problems} with problems` : '') +
      fillNote;
    saveButton.disabled = problems > 0;
    saveButton.title = problems ? 'Fix the problems shown in red before saving' : '';
    applyFilter();
  }

  function applyFilter() {
    const filter = filterEl.value;
    for (const row of rows) {
      const isLinked = linkedFolios(row.canvas.id).length > 0;
      row.tr.hidden =
        (filter === 'linked' && !isLinked) ||
        (filter === 'unlinked' && isLinked) ||
        (filter === 'changed' && !row.isChanged) ||
        (filter === 'problem' && !row.hasProblem);
    }
  }

  function buildRow(canvas, labelCounts) {
    const tr = document.createElement('tr');
    tr.id = `image-${canvas.index + 1}`;
    const current = linkedFolios(canvas.id);

    const position = document.createElement('td');
    position.className = 'canvas-position';
    position.textContent = canvas.index + 1;

    const thumb = document.createElement('td');
    thumb.className = 'canvas-thumb';
    if (canvas.thumbnail) {
      const link = document.createElement('a');
      link.href = canvas.large || canvas.thumbnail;
      link.className = 'canvas-thumb-frame is-loading';
      link.title = 'View larger';
      const img = document.createElement('img');
      img.loading = 'lazy';
      img.alt = `Image ${canvas.index + 1}`;
      img.addEventListener('load', () => link.classList.remove('is-loading'));
      img.addEventListener('error', () => {
        link.classList.remove('is-loading');
        link.classList.add('is-broken');
        link.replaceChildren('No image');
      });
      img.src = canvas.thumbnail;
      link.appendChild(img);
      link.addEventListener('click', (event) => {
        // open in a new tab as usual with a modifier key or middle click
        if (event.metaKey || event.ctrlKey || event.shiftKey || link.classList.contains('is-broken')) return;
        event.preventDefault();
        openViewer(canvas);
      });
      thumb.appendChild(link);
    }

    const label = document.createElement('td');
    label.textContent = canvas.label;

    const folioCell = document.createElement('td');
    folioCell.className = 'canvas-folio';
    const entriesEl = document.createElement('div');
    const addButton = document.createElement('button');
    addButton.type = 'button';
    addButton.className = 'canvas-add-folio';
    addButton.textContent = 'Add another folio';
    folioCell.append(entriesEl, addButton);

    const notesEl = document.createElement('td');

    tr.append(position, thumb, label, folioCell, notesEl);
    const row = {
      canvas,
      tr,
      inputs: [],
      entriesEl,
      addButton,
      suggestion: null,
      notesEl,
      labelCount: labelCounts.get(normalizeFolioLabel(canvas.label)) || 0,
      isChanged: false,
      hasProblem: false,
    };
    addButton.addEventListener('click', () => {
      addFolioInput(row).focus();
      update();
    });

    const initial = current.map((folio) => folio.number);
    const values = submitted && canvas.id in submitted ? submitted[canvas.id] : initial;
    if (submitted && values.join() !== initial.join()) dirty = true;
    (values.length ? values : ['']).forEach((value) => {
      const input = addFolioInput(row);
      input.value = value;
      const folio = current.find((f) => f.number === value);
      if (folio) {
        const link = document.createElement('a');
        link.href = folio.admin_url;
        link.textContent = 'Edit folio record';
        link.style.marginLeft = '0.5em';
        input.parentElement.appendChild(link);
      }
    });

    // offer the folio numbers in the manifest label, when it has any
    const suggestedNumbers = folioNumbersFromLabel(canvas.label);
    if (suggestedNumbers.length) {
      const suggestion = document.createElement('button');
      suggestion.type = 'button';
      suggestion.className = 'canvas-suggestion';
      suggestion.textContent = `Use ${suggestedNumbers.join(', ')}`;
      suggestion.title = `Use the folio numbers from the manifest label "${canvas.label}"`;
      suggestion.addEventListener('click', () => {
        setRowFolios(row, suggestedNumbers);
        dirty = true;
        update();
        row.inputs[0].focus();
      });
      row.inputs[0].parentElement.appendChild(suggestion);
      row.suggestion = suggestion;
    }
    return row;
  }

  function addFolioInput(row) {
    const entry = document.createElement('div');
    entry.className = 'canvas-folio-entry';
    const input = document.createElement('input');
    input.type = 'text';
    input.setAttribute('list', 'canvas-folio-numbers');
    input.setAttribute('aria-label', `Folio number for image ${row.canvas.index + 1}`);
    input.addEventListener('input', () => {
      dirty = true;
      update();
    });
    entry.appendChild(input);
    row.entriesEl.appendChild(entry);
    row.inputs.push(input);
    return input;
  }

  function showNotices(canvases) {
    const canvasIds = new Set(canvases.map((canvas) => canvas.id));
    const notices = [
      [
        'Folio records not linked to an image: ',
        folios.filter((folio) => !folio.canvas_id),
      ],
      [
        "Linked Folio records without a line range: ",
        folios
          .filter((folio) => canvasIds.has(folio.canvas_id) && !hasLineRange(folio))
          .sort((a, b) => canvasPositions.get(a.canvas_id) - canvasPositions.get(b.canvas_id)),
      ],
      [
        'Folio records linked to images no longer in the manifest: ',
        folios.filter((folio) => folio.canvas_id && !canvasIds.has(folio.canvas_id)),
      ],
    ];
    for (const [text, list] of notices) {
      if (!list.length) continue;
      const p = document.createElement('p');
      p.className = 'canvas-notice';
      p.append(text);
      list.forEach((folio, i) => {
        if (i) p.append(', ');
        const link = document.createElement('a');
        link.href = folio.admin_url;
        link.textContent = folio.number || `(no number, #${folio.id})`;
        p.appendChild(link);
      });
      noticesEl.appendChild(p);
    }
  }

  async function load() {
    let canvases;
    try {
      const response = await fetch(manifestUrl);
      if (!response.ok) throw new Error(`the server responded ${response.status}`);
      canvases = getCanvases(await response.json());
    } catch (error) {
      statusEl.textContent = `Could not load the IIIF manifest (${error.message}).`;
      statusEl.classList.add('canvas-status-error');
      return;
    }
    if (!canvases.length) {
      statusEl.textContent = 'The IIIF manifest has no images.';
      statusEl.classList.add('canvas-status-error');
      return;
    }

    canvasPositions = new Map(canvases.map((canvas) => [canvas.id, canvas.index]));
    const labelCounts = new Map();
    for (const canvas of canvases) {
      const key = normalizeFolioLabel(canvas.label);
      labelCounts.set(key, (labelCounts.get(key) || 0) + 1);
    }
    rows = canvases.map((canvas) => buildRow(canvas, labelCounts));
    tbody.append(...rows.map((row) => row.tr));
    showNotices(canvases);
    statusEl.hidden = true;
    form.hidden = false;
    update();
    showLinkedRow();
  }

  // Rows are built after the page loads, so jump to a row named in the URL
  // here: #folio-<id> for the image linked to that folio record (as linked
  // from the manuscript's folio list), or #image-<position>
  function showLinkedRow() {
    let row = null;
    let folio = null;
    const folioMatch = location.hash.match(/^#folio-(\d+)$/);
    if (folioMatch) {
      folio = folios.find((f) => String(f.id) === folioMatch[1]);
      row = folio && rows.find((r) => r.canvas.id === folio.canvas_id);
    } else if (/^#image-\d+$/.test(location.hash)) {
      row = rows.find((r) => `#${r.tr.id}` === location.hash);
    }
    if (!row) return;
    row.tr.classList.add('is-target');
    row.tr.scrollIntoView({ block: 'center' });
    const input = folio && row.inputs.find((i) => i.value.trim() === folio.number);
    (input || row.inputs[0]).focus({ preventScroll: true });
  }

  filterEl.addEventListener('change', applyFilter);

  // Larger view of an image, in a dialog over the page
  function openViewer(canvas) {
    const numbers = linkedFolios(canvas.id).map((folio) => folio.number).join(', ');
    viewerTitle.textContent =
      `Image ${canvas.index + 1}` +
      (canvas.label ? ` · manifest label "${canvas.label}"` : '') +
      (numbers ? ` · linked to folio ${numbers}` : '');
    viewerFrame.classList.add('is-loading');
    viewerImage.removeAttribute('src');
    viewerImage.alt = `Image ${canvas.index + 1}`;
    viewerImage.src = canvas.large || canvas.thumbnail;
    viewerFull.href = canvas.full || canvas.large || canvas.thumbnail;
    viewer.showModal();
  }
  viewerImage.addEventListener('load', () => viewerFrame.classList.remove('is-loading'));
  viewerImage.addEventListener('error', () => viewerFrame.classList.remove('is-loading'));
  document.getElementById('canvas-viewer-close').addEventListener('click', () => viewer.close());
  // close when clicking the backdrop around the dialog
  viewer.addEventListener('click', (event) => {
    if (event.target === viewer) viewer.close();
  });

  // Fill in an empty image whose label appears once in the manifest, with each
  // recto/verso number in it that matches exactly one folio that isn't linked
  // to an image or entered elsewhere
  fillButton.addEventListener('click', () => {
    const entered = new Set(rows.flatMap(rowEntries).map(({ key }) => key));
    let filled = 0;
    for (const row of rows) {
      if (rowEntries(row).length || row.labelCount !== 1) continue;
      const numbers = [];
      for (const key of folioNumbersFromLabel(row.canvas.label).map(folioKey)) {
        const matches = foliosByKey.get(key) || [];
        if (entered.has(key) || matches.length !== 1 || matches[0].canvas_id) continue;
        numbers.push(matches[0].number);
        entered.add(key);
      }
      if (!numbers.length) continue;
      setRowFolios(row, numbers);
      filled += 1;
    }
    if (filled) {
      dirty = true;
      filterEl.value = 'changed';
    }
    fillNote = ` · filled in ${filled} image${filled === 1 ? '' : 's'}`;
    update();
  });

  form.addEventListener('submit', (event) => {
    if (saveButton.disabled) {
      event.preventDefault();
      return;
    }
    document.getElementById('canvas-rows').value = JSON.stringify(
      rows.map((row) => ({
        id: row.canvas.id,
        index: row.canvas.index,
        label: row.canvas.label,
        image_id: row.canvas.image_id,
        folios: rowEntries(row).map(({ value }) => value),
      })),
    );
    dirty = false;
  });

  window.addEventListener('beforeunload', (event) => {
    if (dirty && rows.some((row) => row.isChanged)) {
      event.preventDefault();
      event.returnValue = '';
    }
  });

  load();
})();
