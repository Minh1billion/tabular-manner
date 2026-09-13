(function () {
  var toggle = document.querySelector('.nav-toggle');
  var scrim = document.querySelector('.nav-scrim');
  var body = document.body;

  function closeNav() {
    body.classList.remove('nav-open');
    if (toggle) toggle.setAttribute('aria-expanded', 'false');
  }

  if (toggle) {
    toggle.addEventListener('click', function () {
      var isOpen = body.classList.toggle('nav-open');
      toggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
    });
  }
  if (scrim) {
    scrim.addEventListener('click', closeNav);
  }
  var navClose = document.querySelector('.nav-close');
  if (navClose) {
    navClose.addEventListener('click', closeNav);
  }
  document.querySelectorAll('.sidebar .nav-link, .sidebar .brand').forEach(function (link) {
    link.addEventListener('click', closeNav);
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') closeNav();
  });
})();

function copyBlock(btn) {
  var pre = btn.parentElement.querySelector('pre');
  var text = pre.innerText;
  navigator.clipboard.writeText(text).then(function () {
    var original = btn.textContent;
    btn.textContent = 'copied';
    setTimeout(function () { btn.textContent = original; }, 1200);
  });
}

(function () {
  var links = Array.prototype.slice.call(document.querySelectorAll('.nav-link'));
  var currentPage = links.filter(function (link) {
    var url = new URL(link.href, window.location.href);
    return url.pathname === window.location.pathname;
  });

  var sections = currentPage
    .map(function (link) {
      var url = new URL(link.href, window.location.href);
      return document.querySelector(url.hash);
    })
    .filter(Boolean);

  currentPage.forEach(function (link) { link.classList.add('same-page'); });

  if (!('IntersectionObserver' in window) || sections.length === 0) {
    if (currentPage.length > 0) currentPage[0].classList.add('active');
    return;
  }

  var observer = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (!entry.isIntersecting) return;
      var id = '#' + entry.target.id;
      currentPage.forEach(function (link) {
        var url = new URL(link.href, window.location.href);
        link.classList.toggle('active', url.hash === id);
      });
    });
  }, { rootMargin: '-15% 0px -70% 0px', threshold: 0 });

  sections.forEach(function (section) { observer.observe(section); });
})();
