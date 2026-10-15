// Victoria votes 2026 — map interactions.
// No build step. Uses Leaflet + OSM tiles + Nominatim for geocoding.

(async function () {
  const map = L.map('map', { preferCanvas: true, zoomControl: true });
  // Default: Melbourne metro — most users are here. Scroll out to see regional Victoria.
  map.setView([-37.84, 145.00], 11);
  // In case the map container was sized after Leaflet init, invalidate once things settle.
  setTimeout(() => map.invalidateSize(), 100);
  window.addEventListener('resize', () => map.invalidateSize());

  // --- Draggable sidebar divider ---
  (function wireDivider() {
    const divider = document.getElementById('divider');
    const layout = document.querySelector('.map-layout');
    if (!divider || !layout) return;
    const MIN = 280;
    const MAX = Math.min(900, Math.round(window.innerWidth * 0.7));
    const saved = parseInt(localStorage.getItem('sidebar-w') || '', 10);
    if (saved && saved >= MIN) layout.style.setProperty('--sidebar-w', saved + 'px');

    let dragging = false;
    const onDown = (e) => {
      dragging = true;
      divider.classList.add('dragging');
      document.body.classList.add('dragging');
      e.preventDefault();
    };
    const onMove = (e) => {
      if (!dragging) return;
      const x = e.touches ? e.touches[0].clientX : e.clientX;
      const w = Math.min(Math.max(window.innerWidth - x, MIN), MAX);
      layout.style.setProperty('--sidebar-w', w + 'px');
      map.invalidateSize(false);
    };
    const onUp = () => {
      if (!dragging) return;
      dragging = false;
      divider.classList.remove('dragging');
      document.body.classList.remove('dragging');
      const w = parseInt(getComputedStyle(layout).gridTemplateColumns.split(' ').pop(), 10);
      if (!isNaN(w)) localStorage.setItem('sidebar-w', String(w));
      map.invalidateSize();
    };
    divider.addEventListener('mousedown', onDown);
    divider.addEventListener('touchstart', onDown, { passive: false });
    window.addEventListener('mousemove', onMove);
    window.addEventListener('touchmove', onMove, { passive: false });
    window.addEventListener('mouseup', onUp);
    window.addEventListener('touchend', onUp);
    // Double-click to reset to default width.
    divider.addEventListener('dblclick', () => {
      layout.style.removeProperty('--sidebar-w');
      localStorage.removeItem('sidebar-w');
      map.invalidateSize();
    });
  })();

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 18,
    attribution:
      '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors · Boundaries © State of Victoria (Vicmap Admin)',
  }).addTo(map);

  const partyColour = (p) => {
    const key = (p || '').toLowerCase();
    if (key.includes('labor') && !key.includes('independent')) return '#e52a2a';
    if (key.includes('independent labor')) return '#9b1b1b';
    if (key.includes('liberal') && !key.includes('independent')) return '#1565c0';
    if (key.includes('independent liberal')) return '#4a86cc';
    if (key.includes('national')) return '#374151';
    if (key.includes('greens')) return '#0f8f3a';
    if (key.includes('one nation')) return '#f36c21';
    if (key.includes('socialist')) return '#7a0010';
    if (key.includes('family first')) return '#5b2c86';
    if (key.includes('cannabis')) return '#72c342';
    if (key.includes('libertarian')) return '#fec327';
    if (key.includes('animal')) return '#008080';
    if (key.includes('shooters')) return '#8b5a2b';
    if (key.includes('democratic labour')) return '#aa3333';
    if (key.includes('vacant')) return '#bbb';
    if (key.includes('independent')) return '#a3a3a3';
    return '#777';
  };

  const partySlug = (p) =>
    (p || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');

  // Fetch all data in parallel; bios may not exist yet (scraper runs separately).
  const safeFetch = (url) => fetch(url).then(r => r.ok ? r.json() : {}).catch(() => ({}));
  const [districtsGeo, regionsGeo, members, candidates, margins, parties, bios, margins2018, projectionsFile] = await Promise.all([
    fetch('/assets/data/districts.geojson').then((r) => r.json()),
    fetch('/assets/data/regions.geojson').then((r) => r.json()),
    fetch('/assets/data/members.json').then((r) => r.json()),
    fetch('/assets/data/candidates.json').then((r) => r.json()),
    fetch('/assets/data/margins.json').then((r) => r.json()),
    safeFetch('/assets/data/parties.json').then(d => d.parties || {}),
    safeFetch('/assets/data/bios.json'),
    safeFetch('/assets/data/margins_2018.json'),
    safeFetch('/assets/data/projections.json'),
  ]);
  const projections = projectionsFile.projections || {};
  const aggregateSwing = projectionsFile.aggregate_swing;

  // Safety colour ramp — purple sequential, intentionally non-partisan so it
  // doesn't visually overlap with Labor red / Liberal blue.
  const safetyColour = (s) => ({
    'marginal': '#e879f9',
    'fairly safe': '#c084fc',
    'safe': '#8b5cf6',
    'very safe': '#581c87',
  })[s] || '#999';

  // 2026 projection colour: party colour of projected winner, intensity by margin.
  // For non-two-party seats (Greens-held, Independent-held) we fall back to the
  // sitting winner's party colour at moderate opacity — statewide Lab-vs-Coa swing
  // doesn't flip these so the sensible default is "status quo".
  const projectionColour = (proj, memParty) => {
    if (proj && proj.status === 'non-two-party') {
      // Use sitting MP's party colour at moderate opacity.
      const col = partyColour(memParty || '');
      // If sitting MP party is unknown/Independent, grey is appropriate.
      return { fill: col, opacity: 0.5 };
    }
    if (!proj || proj.projected_labor_tpp == null) {
      return { fill: '#bbb', opacity: 0.35 };
    }
    const base = proj.projected_winner === 'Labor' ? '#e52a2a' : '#1565c0';
    const margin = Math.abs(proj.projected_labor_tpp - 50);
    // margin 0 → opacity 0.35 (ambiguous), margin >=10 → opacity 0.75 (confident)
    const opacity = Math.min(0.75, 0.35 + margin * 0.04);
    return { fill: base, opacity };
  };

  let colourMode = 'party'; // 'party' | 'safety' | 'projection'

  // For regions, pre-compute the dominant party from the sitting MLCs.
  const regionDominant = {};
  for (const [key, mlcs] of Object.entries(members.regions || {})) {
    const counts = {};
    for (const m of mlcs) counts[m.party] = (counts[m.party] || 0) + 1;
    const top = Object.entries(counts).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))[0];
    regionDominant[key] = top ? top[0] : '';
  }

  // Style helpers
  const styleFor = (feature) => {
    const key = feature.properties.district;
    if (colourMode === 'safety') {
      const m = margins[key];
      return { fillColor: m ? safetyColour(m.safety) : '#999', fillOpacity: 0.55, color: '#333', weight: 1 };
    }
    if (colourMode === 'projection') {
      const sittingParty = members.districts[key] ? members.districts[key].party : '';
      const p = projectionColour(projections[key], sittingParty);
      return { fillColor: p.fill, fillOpacity: p.opacity, color: '#333', weight: 1 };
    }
    const party = members.districts[key] ? members.districts[key].party : '';
    return { fillColor: partyColour(party), fillOpacity: 0.45, color: '#333', weight: 1 };
  };
  const hoverStyle = { weight: 3, color: '#000', fillOpacity: 0.65 };
  const regionStyleFor = (feature) => {
    const key = feature.properties.region;
    const party = regionDominant[key] || '';
    return { fillColor: partyColour(party), fillOpacity: 0.45, color: '#1b2d4a', weight: 1.5 };
  };

  // --- District layer ---
  const districtLayer = L.geoJSON(districtsGeo, {
    style: styleFor,
    onEachFeature: (f, layer) => {
      const key = f.properties.district;
      const label = f.properties.district_label;
      layer.bindTooltip(label, { sticky: true });
      layer.on({
        mouseover: (e) => e.target.setStyle(hoverStyle),
        mouseout: (e) => districtLayer.resetStyle(e.target),
        click: () => showDistrict(key, label),
      });
    },
  });

  // --- Region layer ---
  const regionLayer = L.geoJSON(regionsGeo, {
    style: regionStyleFor,
    onEachFeature: (f, layer) => {
      const key = f.properties.region;
      const label = f.properties.region_label;
      layer.bindTooltip(label + ' (most MLCs: ' + (regionDominant[key] || 'mixed') + ')', { sticky: true });
      layer.on({
        mouseover: (e) => e.target.setStyle({ fillOpacity: 0.65, weight: 3 }),
        mouseout: (e) => regionLayer.resetStyle(e.target),
        click: () => showRegion(key, label),
      });
    },
  });

  districtLayer.addTo(map);
  // Intentionally don't fitBounds — keep the Melbourne-metro default view so
  // most users immediately see their area without having to zoom in.

  // --- Panel updates ---
  const title = document.getElementById('panel-title');
  const body = document.getElementById('panel-body');

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
  }

  function partyPill(party) {
    const slug = partySlug(party) || 'other';
    return '<span class="pill party party-' + slug + '">' + esc(party || 'Unknown') + '</span>';
  }

  function bioBlock(name) {
    const b = bios[name];
    if (!b) return '';
    // Case 1 — Wikipedia-style structured bio (sitting MPs etc.)
    if (b.wikipedia_url) {
      const bits = [];
      if (b.elected_since) bits.push('First elected ' + esc(b.elected_since));
      if (b.prior_occupation) bits.push('Prior: ' + esc(b.prior_occupation));
      if (b.born) bits.push('Born ' + esc(b.born));
      let html = '<p class="bio">';
      if (bits.length) html += bits.join(' · ');
      if (b.prior_roles && b.prior_roles.length) {
        html += '<br><small>' + b.prior_roles.slice(0, 3).map(esc).join('; ') + '</small>';
      }
      if (b.education) html += '<br><small>Education: ' + esc(b.education) + '</small>';
      html += ' <a href="' + esc(b.wikipedia_url) + '" target="_blank" rel="noopener">wikipedia</a>';
      html += '</p>';
      return html;
    }
    // Case 2 — ABC/party-sourced bio summary (non-sitting candidates)
    if (b.summary) {
      const srcLabel = b.source || 'source';
      const srcLink = b.source_url
        ? ' <a href="' + esc(b.source_url) + '" target="_blank" rel="noopener">' + esc(srcLabel) + '</a>'
        : '';
      return '<p class="bio">' + esc(b.summary) + srcLink + '</p>';
    }
    return '';
  }

  function partiesAboutBlock(partyNames) {
    const unique = [...new Set(partyNames.filter(Boolean))];
    const shown = unique.map(p => {
      // Match party key: try exact, then first-word
      const key = Object.keys(parties).find(k =>
        k.toLowerCase() === p.toLowerCase() ||
        p.toLowerCase().startsWith(k.toLowerCase()) ||
        k.toLowerCase().startsWith(p.toLowerCase())
      );
      if (!key) return null;
      const info = parties[key];
      return '<details class="party-about"><summary>' + partyPill(key) +
             ' <small>' + esc(info.position || '') + '</small></summary>' +
             '<p>' + esc(info.stated_priorities) +
             (info.website ? ' <a href="' + esc(info.website) + '" target="_blank" rel="noopener">website</a>' : '') +
             '</p></details>';
    }).filter(Boolean);
    if (!shown.length) return '';
    return '<h3>About the parties on this ballot</h3>' + shown.join('');
  }

  const sidebarEl = document.querySelector('.sidebar');
  const scrollSidebarTop = () => { if (sidebarEl) sidebarEl.scrollTop = 0; };

  function showDistrict(key, label) {
    const mem = members.districts[key];
    const cand = candidates.districts[key] || candidates.districts[(key || '').replace(/\s+/g, ' ')];
    const mg = margins[key];
    const proj = projections[key]; // hoisted so it's available in both Trajectory and Candidates blocks
    title.textContent = label;
    scrollSidebarTop();
    let html = '<p><em>Legislative Assembly district</em></p>';
    html += '<h3>Current MP <a class="src" href="https://en.wikipedia.org/wiki/Members_of_the_Victorian_Legislative_Assembly,_2022%E2%80%932026" target="_blank" rel="noopener" title="Source">source</a></h3>';
    if (mem) {
      html += '<p><strong>' + esc(mem.mp) + '</strong> ' + partyPill(mem.party) + '</p>';
      html += bioBlock(mem.mp);
    } else {
      html += '<p>Not available.</p>';
    }
    if (mg) {
      const swing = (typeof mg.swing === 'number')
        ? (mg.swing >= 0 ? '+' + mg.swing.toFixed(1) : mg.swing.toFixed(1)) + '% swing'
        : '';
      const combinedBadge = (safety, margin) =>
        (safety && typeof margin === 'number')
          ? '<span class="pill" style="background:' + safetyColour(safety) + ';color:#fff">' + esc(safety) + ' ' + margin.toFixed(1) + '%</span>'
          : '';
      html += '<h3>Trajectory <a class="src" href="https://en.wikipedia.org/wiki/Results_of_the_2022_Victorian_state_election_(Legislative_Assembly)" target="_blank" rel="noopener">source</a></h3>';
      const m2018 = margins2018[key];
      const row = (label, bodyHtml) =>
        '<p class="trajectory-row"><span class="year-label">' + label + '</span>' +
        '<span class="year-content">' + bodyHtml + '</span></p>';
      const yearRow = (label, m) => {
        if (!m || !m.winner) return '';
        const badge = combinedBadge(m.safety, m.margin);
        return row(label,
          esc(m.winner) + ' <strong>' + m.tpp_winner_pct.toFixed(1) + '%</strong> vs ' + esc(m.tpp_opponent) +
          ' <small style="color:var(--muted)">(' + m.basis + ')</small>' + (badge ? ' ' + badge : ''));
      };
      if (m2018 === null) {
        html += row('2018', '<em>district did not exist (2021 redistribution)</em>');
      } else {
        html += yearRow('2018', m2018);
      }
      html += yearRow('2022', mg);
      // Only show the 2018→2022 swing line when the district actually existed in 2018.
      // When the district is new, Wikipedia's "swing" field is a notional swing vs a
      // redistributed baseline — potentially misleading, so we suppress it.
      if (swing && m2018 && m2018.winner) {
        html += '<p class="bio">Swing to ' + esc(mg.winner) + ' from 2018 to 2022: <strong>' + swing + '</strong></p>';
      }

      // 2026 projection (uniform swing from polling average) — proj is hoisted above
      if (proj && proj.projected_labor_tpp != null) {
        const statusColour = {
          'likely flip': '#d7301f',
          'in play': '#fc8d59',
          'close hold': '#fee08b',
          'safe hold': '#4575b4',
          'non-two-party': '#999',
        }[proj.status] || '#999';
        const badge = '<span class="pill" style="background:' + statusColour + ';color:#fff">' + esc(proj.status) + '</span>';
        html += row('2026<br><em>projected</em>',
          '<strong>' + esc(proj.projected_winner) + '</strong> ' +
          (proj.projected_winner === 'Labor' ? proj.projected_labor_tpp.toFixed(1) : (100 - proj.projected_labor_tpp).toFixed(1)) + '% TPP ' +
          badge);
        html += '<p class="bio">Based on uniform swing of ' + aggregateSwing.toFixed(1) + '% applied to 2022 TPP — see <a href="/pages/projections.html">how it works &amp; caveats</a>.</p>';
      } else if (proj && proj.status === 'non-two-party') {
        html += row('2026<br><em>projected</em>', '<em>' + esc(proj.note) + '</em>');
        html += '<p class="bio">See <a href="/pages/projections.html">projections page</a> for why uniform swing doesn\'t apply here.</p>';
      }
    }
    html += '<h3>Candidates for 2026 <a class="src" href="https://en.wikipedia.org/wiki/Candidates_of_the_2026_Victorian_state_election" target="_blank" rel="noopener">source</a></h3>';
    if (cand && cand.candidates && cand.candidates.length) {
      // Match the projection winner to candidates by party.
      const projWinner = proj && proj.projected_winner;
      const isCoalitionParty = (p) => /liberal|national|coalition/i.test(p || '');
      const matchesProjection = (party) => {
        if (!projWinner) return false;
        if (projWinner === 'Coalition') return isCoalitionParty(party);
        if (projWinner === 'Labor') return /labor/i.test(party || '') && !/independent/i.test(party || '');
        if (projWinner === 'Greens') return /greens/i.test(party || '');
        if (projWinner === 'Independent') return /independent/i.test(party || '');
        return false;
      };
      html += '<ul class="candidate-list detailed">';
      for (const c of cand.candidates) {
        const sitting = mem && c.name === mem.mp;
        const projected = matchesProjection(c.party);
        const badges = [];
        if (sitting) badges.push('<span class="role-badge sitting">sitting MP</span>');
        if (projected) badges.push('<span class="role-badge projected" title="Projected by uniform swing from current polling — not a prediction">projected winner</span>');
        html += '<li>'
             + '<div class="cand-head"><strong>' + esc(c.name) + '</strong> '
             + partyPill(c.party)
             + (badges.length ? ' <span class="cand-badges">' + badges.join(' ') + '</span>' : '')
             + '</div>'
             + bioBlock(c.name)
             + '</li>';
      }
      html += '</ul>';
      html += '<p style="font-size:0.85rem;color:var(--muted)">Candidate data from Wikipedia, pre-nomination (last updated 15 Oct 2026) and may be partial or imperfectly party-coded. The official list is published by the <a href="https://www.vec.vic.gov.au" target="_blank" rel="noopener">VEC</a> after nominations close on 9 November 2026. Bios are drawn from Wikipedia — many non-sitting candidates have no public bio yet. "Projected winner" is based on applying statewide polling swing to the 2022 result (see <a href="/pages/projections.html">caveats</a>) — the projection names the party, not the specific candidate.</p>';
    } else {
      html += '<p>No candidate list available yet. Nominations close 9 November 2026.</p>';
    }
    // About-the-parties block based on 2026 candidate parties + current MP's party
    const partyList = [];
    if (mem) partyList.push(mem.party);
    if (cand && cand.candidates) partyList.push(...cand.candidates.map(c => c.party));
    html += partiesAboutBlock(partyList);
    html += '<p style="margin-top:1em"><a href="https://en.wikipedia.org/wiki/Electoral_district_of_' + encodeURIComponent(label.replace(/ /g, '_')) + '" target="_blank" rel="noopener">Wikipedia: ' + esc(label) + '</a></p>';
    body.innerHTML = html;
  }

  function showRegion(key, label) {
    const mlcs = members.regions[key] || [];
    const cand = candidates.regions && candidates.regions[key];
    title.textContent = label;
    scrollSidebarTop();
    let html = '<p><em>Legislative Council region — elects 5 members by proportional representation</em></p>';
    html += '<h3>Current MLCs <a class="src" href="https://en.wikipedia.org/wiki/Members_of_the_Victorian_Legislative_Council,_2022%E2%80%932026" target="_blank" rel="noopener">source</a></h3>';
    if (mlcs.length) {
      html += '<ul class="candidate-list detailed">';
      for (const m of mlcs) {
        html += '<li><div><strong>' + esc(m.mlc) + '</strong> ' + partyPill(m.party) + '</div>' + bioBlock(m.mlc) + '</li>';
      }
      html += '</ul>';
    } else {
      html += '<p>Not available.</p>';
    }
    html += '<h3>Candidates for 2026</h3>';
    if (cand && cand.candidates && cand.candidates.length) {
      html += '<ul class="candidate-list detailed">';
      for (const c of cand.candidates) {
        html += '<li><div><strong>' + esc(c.name) + '</strong> ' + partyPill(c.party) + '</div>' + bioBlock(c.name) + '</li>';
      }
      html += '</ul>';
    } else {
      html += '<p>Upper house candidate groups are still being announced. See the <a href="https://en.wikipedia.org/wiki/Candidates_of_the_2026_Victorian_state_election#Legislative_Council" target="_blank" rel="noopener">Wikipedia running tally</a> and the authoritative <a href="https://www.vec.vic.gov.au" target="_blank" rel="noopener">VEC candidate list</a> (published after 9 November 2026).</p>';
    }
    // About-the-parties block
    const partyList = mlcs.map(m => m.party);
    if (cand && cand.candidates) partyList.push(...cand.candidates.map(c => c.party));
    html += partiesAboutBlock(partyList);
    body.innerHTML = html;
  }

  // --- Toggles ---
  const btnD = document.getElementById('btn-districts');
  const btnR = document.getElementById('btn-regions');
  function activate(mode) {
    if (mode === 'districts') {
      if (!map.hasLayer(districtLayer)) districtLayer.addTo(map);
      if (map.hasLayer(regionLayer)) map.removeLayer(regionLayer);
      btnD.classList.add('active'); btnD.setAttribute('aria-pressed', 'true');
      btnR.classList.remove('active'); btnR.setAttribute('aria-pressed', 'false');
      // Safety colouring only makes sense for single-member districts.
      btnColourSafety.disabled = false;
      btnColourSafety.title = 'Colour each district by how safe the 2022 result was';
      btnColourProjection.disabled = false;
      btnColourProjection.title = 'Colour each district by its projected 2026 winner';
    } else {
      if (!map.hasLayer(regionLayer)) regionLayer.addTo(map);
      if (map.hasLayer(districtLayer)) map.removeLayer(districtLayer);
      btnR.classList.add('active'); btnR.setAttribute('aria-pressed', 'true');
      btnD.classList.remove('active'); btnD.setAttribute('aria-pressed', 'false');
      // Force party mode in region view — safety and projection don't apply to PR.
      if (colourMode !== 'party') setColour('party');
      btnColourSafety.disabled = true;
      btnColourSafety.title = 'Safety ratings only apply to single-member districts';
      btnColourProjection.disabled = true;
      btnColourProjection.title = 'Projections only apply to single-member districts';
    }
    colourExplainer.innerHTML = explainerHtml(colourMode, mode);
    document.getElementById('legend').innerHTML = legendHtml(colourMode, mode);
  }
  btnD.addEventListener('click', () => activate('districts'));
  btnR.addEventListener('click', () => activate('regions'));

  // Colour mode toggle
  const btnColourParty = document.getElementById('btn-colour-party');
  const btnColourSafety = document.getElementById('btn-colour-safety');
  const btnColourProjection = document.getElementById('btn-colour-projection');
  const colourExplainer = document.getElementById('colour-explainer');
  function setColour(mode) {
    colourMode = mode;
    districtLayer.setStyle(styleFor);
    btnColourParty.classList.toggle('active', mode === 'party');
    btnColourSafety.classList.toggle('active', mode === 'safety');
    btnColourProjection.classList.toggle('active', mode === 'projection');
    btnColourParty.setAttribute('aria-pressed', mode === 'party');
    btnColourSafety.setAttribute('aria-pressed', mode === 'safety');
    btnColourProjection.setAttribute('aria-pressed', mode === 'projection');
    const layer = map.hasLayer(regionLayer) ? 'regions' : 'districts';
    colourExplainer.innerHTML = explainerHtml(mode, layer);
    document.getElementById('legend').innerHTML = legendHtml(mode, layer);
  }
  btnColourParty.addEventListener('click', () => setColour('party'));
  btnColourSafety.addEventListener('click', () => setColour('safety'));
  btnColourProjection.addEventListener('click', () => setColour('projection'));

  function explainerHtml(mode, layer) {
    if (layer === 'regions') return 'Regions coloured by the party holding the most sitting MLCs.';
    if (mode === 'party') return 'Districts coloured by the party of the sitting MP.';
    if (mode === 'safety') return "Each district's 2022 margin — bigger margin, darker colour. Marginal seats are most likely to change hands.";
    if (mode === 'projection') return 'Projected 2026 winner (party colour), with intensity by projected margin. Greens- and Independent-held seats keep their sitting party\'s colour (assumed hold — statewide swing doesn\'t apply).';
    return '';
  }

  function legendHtml(mode, layer) {
    const item = (col, label) =>
      '<span class="legend-item"><span class="sw" style="background:' + col + '"></span>' + label + '</span>';
    if (mode === 'safety' && layer === 'districts') {
      return item('#e879f9', 'marginal (&lt;6%)') +
             item('#c084fc', 'fairly safe (6–10%)') +
             item('#8b5cf6', 'safe (10–20%)') +
             item('#581c87', 'very safe (20%+)');
    }
    if (mode === 'projection' && layer === 'districts') {
      return item('#e52a2a', 'Labor hold/gain') +
             item('#1565c0', 'Coalition hold/gain') +
             item('#0f8f3a', 'Greens hold (assumed)') +
             item('#a3a3a3', 'Independent hold (assumed)') +
             '<br><small>Intensity by projected margin — faint = tight race, saturated = safe. Non-two-party seats shown at the sitting party\'s colour since statewide swing doesn\'t apply.</small>';
    }
    const prefix = layer === 'regions' ? '<em>Coloured by majority sitting MLC party</em><br>' : '';
    return prefix +
           item('#e52a2a', 'Labor') +
           item('#1565c0', 'Liberal') +
           item('#374151', 'National') +
           item('#0f8f3a', 'Greens') +
           item('#a3a3a3', 'Independent');
  }
  setColour('party');

  // --- Address search ---
  const form = document.getElementById('search-form');
  const input = document.getElementById('search-input');
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const q = input.value.trim();
    if (!q) return;
    body.innerHTML = '<p>Looking up <strong>' + esc(q) + '</strong>…</p>';
    try {
      const isPostcode = /^\d{4}$/.test(q);
      let url;
      if (isPostcode) {
        url = 'https://nominatim.openstreetmap.org/search?format=json&limit=1&countrycodes=au&postalcode=' + encodeURIComponent(q);
      } else {
        const augmented = /victoria|vic\b|australia/i.test(q) ? q : q + ', Victoria, Australia';
        url = 'https://nominatim.openstreetmap.org/search?format=json&limit=1&countrycodes=au&q=' + encodeURIComponent(augmented);
      }
      const res = await fetch(url, { headers: { 'Accept': 'application/json' } });
      const results = await res.json();
      if (!results.length) {
        body.innerHTML = '<p>No result found for <strong>' + esc(q) + '</strong>. Try adding a suburb (e.g. "Camberwell") or a street plus suburb.</p>';
        return;
      }
      const { lat, lon, display_name } = results[0];
      const point = L.latLng(+lat, +lon);
      map.setView(point, 11);
      L.circleMarker(point, { radius: 8, color: '#000', fillColor: '#ffcc00', fillOpacity: 1, weight: 2 })
        .addTo(map).bindTooltip(display_name).openTooltip();
      // Find which district & region contain the point
      const inDistrict = findContaining(districtsGeo, +lat, +lon);
      const inRegion = findContaining(regionsGeo, +lat, +lon);
      let html = '<p>Found: <em>' + esc(display_name) + '</em></p>';
      if (inDistrict) {
        html += '<p>Lower house district: <strong><a href="#" data-nav="district" data-key="' + esc(inDistrict.properties.district) + '" data-label="' + esc(inDistrict.properties.district_label) + '">' + esc(inDistrict.properties.district_label) + '</a></strong></p>';
      }
      if (inRegion) {
        html += '<p>Upper house region: <strong><a href="#" data-nav="region" data-key="' + esc(inRegion.properties.region) + '" data-label="' + esc(inRegion.properties.region_label) + '">' + esc(inRegion.properties.region_label) + '</a></strong></p>';
      }
      body.innerHTML = html;
      body.querySelectorAll('a[data-nav]').forEach(a => {
        a.addEventListener('click', (ev) => {
          ev.preventDefault();
          if (a.dataset.nav === 'district') { activate('districts'); showDistrict(a.dataset.key, a.dataset.label); }
          else { activate('regions'); showRegion(a.dataset.key, a.dataset.label); }
        });
      });
    } catch (err) {
      body.innerHTML = '<p>Lookup failed: ' + esc(err.message) + '</p>';
    }
  });

  // Point-in-polygon test (ray casting). Works on GeoJSON MultiPolygon / Polygon.
  function findContaining(fc, lat, lon) {
    for (const f of fc.features) {
      if (pointInFeature(f, lon, lat)) return f;
    }
    return null;
  }
  function pointInFeature(feature, x, y) {
    const g = feature.geometry;
    if (g.type === 'Polygon') return pointInPolygon(g.coordinates, x, y);
    if (g.type === 'MultiPolygon') return g.coordinates.some(poly => pointInPolygon(poly, x, y));
    return false;
  }
  function pointInPolygon(polygon, x, y) {
    // outer ring first; holes subtract
    if (!polygon.length) return false;
    const [outer, ...holes] = polygon;
    if (!pointInRing(outer, x, y)) return false;
    for (const h of holes) if (pointInRing(h, x, y)) return false;
    return true;
  }
  function pointInRing(ring, x, y) {
    let inside = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const [xi, yi] = ring[i], [xj, yj] = ring[j];
      const intersect = (yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi + 1e-18) + xi;
      if (intersect) inside = !inside;
    }
    return inside;
  }
})();
