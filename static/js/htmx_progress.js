(function () {
  var progress = document.getElementById('top-progress');
  if (!progress) return;
  var content = document.getElementById('content');
  function start() {
    progress.style.width = '25%';
    progress.style.opacity = '1';
    requestAnimationFrame(function () { progress.style.width = '80%'; });
  }
  function done() {
    progress.style.width = '100%';
    setTimeout(function () { progress.style.width = '0'; progress.style.opacity = '0'; }, 150);
  }

  function showError(message) {
    if (!content) return;
    var existing = document.getElementById('htmx-error-banner');
    if (existing) existing.remove();
    var banner = document.createElement('div');
    banner.id = 'htmx-error-banner';
    banner.className = 'mb-4 rounded bg-red-100 p-3 text-sm text-red-700';
    banner.textContent = message;
    content.prepend(banner);
  }
  document.body.addEventListener('htmx:beforeRequest', start);
  document.body.addEventListener('htmx:afterSettle', done);
  document.body.addEventListener('htmx:responseError', function () {
    done();
    showError('Request failed. Please retry.');
  });
  document.body.addEventListener('htmx:sendError', function () {
    done();
    showError('Network error. Check your connection.');
  });
})();
