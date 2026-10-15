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
