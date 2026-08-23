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
