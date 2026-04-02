(function () {
    function wireSidebar () {
        var btn = document.getElementById('sidebar-toggle');
        var sidebar = document.getElementById('auth-sidebar');
        if (!btn || !sidebar || btn.dataset.bound === 'true') return;

        btn.dataset.bound = 'true';
        btn.addEventListener('click', function () {
            var hidden = sidebar.classList.contains('-translate-x-[120%]');
            if (hidden) {
                sidebar.classList.remove('-translate-x-[120%]');
            } else {
                sidebar.classList.add('-translate-x-[120%]');
            }
        });

        document.body.addEventListener('htmx:afterSwap', function () {
            if (window.innerWidth < 768) sidebar.classList.add('-translate-x-[120%]');
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', wireSidebar);
    } else {
        wireSidebar();
    }
})();
