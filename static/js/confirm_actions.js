(function () {
    if (window.__confirmActionsBound) return;
    window.__confirmActionsBound = true;

    document.addEventListener('click', function (event) {
        var button = event.target.closest('button[data-confirm-message], input[type="submit"][data-confirm-message]');
        if (!button) return;

        var message = button.getAttribute('data-confirm-message');
        if (!message) return;

        if (!window.confirm(message)) {
            event.preventDefault();
            event.stopPropagation();
        }
    }, true);
})();
