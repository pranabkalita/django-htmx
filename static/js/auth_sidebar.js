(function () {
    var globalBound = false;
    var resizeBound = false;

    function wireSidebar() {
        var shell = document.getElementById('auth-shell');
        var btn = document.getElementById('sidebar-toggle');
        var collapseBtn = document.getElementById('sidebar-collapse-toggle');
        var sidebar = document.getElementById('auth-sidebar');
        var backdrop = document.getElementById('sidebar-backdrop');
        var iconOpen = document.getElementById('toggleSidebarMobileHamburger');
        var iconClose = document.getElementById('toggleSidebarMobileClose');
        var collapseIconLeft = document.getElementById('collapseIconLeft');
        var collapseIconRight = document.getElementById('collapseIconRight');
        var storageKey = 'authSidebarCollapsed';
        if (!sidebar) return;

        function isDesktop() {
            return window.innerWidth >= 1024;
        }

        function setExpanded(expanded) {
            btn.setAttribute('aria-expanded', expanded ? 'true' : 'false');
            if (iconOpen) iconOpen.classList.toggle('hidden', expanded);
            if (iconClose) iconClose.classList.toggle('hidden', !expanded);
        }

        function setDesktopCollapsed(collapsed) {
            if (!shell) return;
            shell.classList.toggle('sidebar-collapsed', !!collapsed);
            if (collapseBtn) {
                collapseBtn.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
            }
            if (collapseIconLeft) collapseIconLeft.classList.toggle('hidden', !!collapsed);
            if (collapseIconRight) collapseIconRight.classList.toggle('hidden', !collapsed);
        }

        function saveCollapsedPreference(collapsed) {
            try {
                window.localStorage.setItem(storageKey, collapsed ? '1' : '0');
            } catch (_) {
                // Ignore storage errors in private mode.
            }
        }

        function loadCollapsedPreference() {
            try {
                return window.localStorage.getItem(storageKey) === '1';
            } catch (_) {
                return false;
            }
        }

        function openSidebar() {
            sidebar.classList.remove('hidden');
            if (!isDesktop()) {
                sidebar.classList.add('flex');
            }
            if (backdrop) backdrop.classList.remove('hidden');
            setExpanded(true);
        }

        function closeSidebar() {
            if (isDesktop()) {
                if (backdrop) backdrop.classList.add('hidden');
                setExpanded(false);
                return;
            }

            sidebar.classList.add('hidden');
            sidebar.classList.remove('flex');
            if (backdrop) backdrop.classList.add('hidden');
            setExpanded(false);
        }

        function syncSidebarForViewport() {
            if (isDesktop()) {
                sidebar.classList.remove('hidden');
                sidebar.classList.remove('flex');
                if (backdrop) backdrop.classList.add('hidden');
                setExpanded(false);
                setDesktopCollapsed(loadCollapsedPreference());
            } else {
                sidebar.classList.add('hidden');
                sidebar.classList.remove('flex');
                if (backdrop) backdrop.classList.add('hidden');
                setExpanded(false);
                setDesktopCollapsed(false);
            }
        }

        if (btn && btn.dataset.bound !== 'true') {
            btn.dataset.bound = 'true';
            btn.addEventListener('click', function () {
                var hidden = sidebar.classList.contains('hidden');
                if (hidden || isDesktop()) {
                    openSidebar();
                } else {
                    closeSidebar();
                }
            });
        }

        if (collapseBtn && collapseBtn.dataset.bound !== 'true') {
            collapseBtn.dataset.bound = 'true';
            collapseBtn.addEventListener('click', function () {
                if (!isDesktop()) return;
                var collapsed = shell && shell.classList.contains('sidebar-collapsed');
                setDesktopCollapsed(!collapsed);
                saveCollapsedPreference(!collapsed);
            });
        }

        if (backdrop && backdrop.dataset.bound !== 'true') {
            backdrop.dataset.bound = 'true';
            backdrop.addEventListener('click', closeSidebar);
        }

        if (!resizeBound) {
            resizeBound = true;
            window.addEventListener('resize', function () {
                wireSidebar();
            });
        }
        syncSidebarForViewport();
    }

    function bindGlobalSidebarLifecycle() {
        if (globalBound) return;
        globalBound = true;

        // Re-bind controls whenever HTMX swaps in fresh layout markup.
        document.body.addEventListener('htmx:afterSwap', function () {
            wireSidebar();
        });

        document.body.addEventListener('htmx:afterSettle', function () {
            wireSidebar();
        });

        // Keep mobile drawer behavior consistent across navigations.
        document.body.addEventListener('htmx:beforeRequest', function () {
            var sidebar = document.getElementById('auth-sidebar');
            if (!sidebar) return;
            if (window.innerWidth < 1024) {
                sidebar.classList.add('hidden');
                sidebar.classList.remove('flex');
                var backdrop = document.getElementById('sidebar-backdrop');
                if (backdrop) backdrop.classList.add('hidden');
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () {
            bindGlobalSidebarLifecycle();
            wireSidebar();
        });
    } else {
        bindGlobalSidebarLifecycle();
        wireSidebar();
    }
})();
