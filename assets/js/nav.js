// Mobile hamburger — collapses the nav behind a toggle button on narrow screens.
(function () {
  const header = document.querySelector('header.site');
  const inner = header && header.querySelector('.inner');
  if (!inner) return;
  // Inject the hamburger button only if not already present (idempotent).
  if (!document.getElementById('nav-toggle')) {
    const btn = document.createElement('button');
    btn.id = 'nav-toggle';
    btn.setAttribute('aria-label', 'Toggle navigation');
    btn.setAttribute('aria-expanded', 'false');
    btn.textContent = '☰';
    // Place the button at the end of the inner flex row so it sits far-right
    // next to the (hidden-on-mobile) nav.
    inner.appendChild(btn);
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const open = header.classList.toggle('nav-open');
      btn.setAttribute('aria-expanded', open ? 'true' : 'false');
      btn.textContent = open ? '✕' : '☰';
    });
    // Close when a link inside is tapped (so navigating from menu feels right).
    header.querySelectorAll('nav a').forEach((a) => a.addEventListener('click', () => {
      header.classList.remove('nav-open');
      btn.setAttribute('aria-expanded', 'false');
      btn.textContent = '☰';
    }));
    // Close on outside click
    document.addEventListener('click', (e) => {
      if (!header.contains(e.target)) {
        header.classList.remove('nav-open');
        btn.setAttribute('aria-expanded', 'false');
        btn.textContent = '☰';
      }
    });
  }
})();

// Nav dropdown — pure CSS hover works on desktop. On touch devices we need
// click-to-toggle so users can open the "Learn ▾" dropdown without hover.
(function () {
  document.querySelectorAll('.nav-group').forEach((group) => {
    const trigger = group.querySelector('.nav-group-trigger');
    if (!trigger) return;
    trigger.addEventListener('click', (e) => {
      e.stopPropagation();
      const open = group.classList.toggle('open');
      trigger.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
  });
  // Click outside closes any open dropdown.
  document.addEventListener('click', () => {
    document.querySelectorAll('.nav-group.open').forEach((g) => {
      g.classList.remove('open');
      const t = g.querySelector('.nav-group-trigger');
      if (t) t.setAttribute('aria-expanded', 'false');
    });
  });
  // Escape closes it.
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      document.querySelectorAll('.nav-group.open').forEach((g) => g.classList.remove('open'));
    }
  });
})();
