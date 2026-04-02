(function () {
    var processedQueues = new WeakSet();

    function splitTags(raw) {
        if (!raw) return [];
        return raw.split(/\s+/).filter(Boolean);
    }

    function findLevel(tags) {
        if (tags.indexOf('toast-level-success') >= 0 || tags.indexOf('success') >= 0) return 'success';
        if (tags.indexOf('toast-level-error') >= 0 || tags.indexOf('error') >= 0) return 'error';
        if (tags.indexOf('toast-level-warning') >= 0 || tags.indexOf('warning') >= 0) return 'warning';
        return 'info';
    }

    function findPosition(tags) {
        for (var i = 0; i < tags.length; i += 1) {
            if (tags[i].indexOf('toast-pos-') === 0) {
                return tags[i].replace('toast-pos-', '');
            }
        }
        return 'top-right';
    }

    function findDuration(tags) {
        for (var i = 0; i < tags.length; i += 1) {
            if (tags[i].indexOf('toast-dur-') === 0) {
                var parsed = parseInt(tags[i].replace('toast-dur-', ''), 10);
                if (!Number.isNaN(parsed) && parsed > 0) return parsed;
            }
        }
        return 3500;
    }

    function containerClasses(position) {
        var base = 'pointer-events-none fixed z-[210] flex max-w-[95vw] flex-col gap-3 sm:max-w-sm';
        var map = {
            'top-right': 'top-4 right-4 items-end',
            'top-center': 'top-4 left-1/2 -translate-x-1/2 items-center',
            'top-left': 'top-4 left-4 items-start',
            'bottom-right': 'bottom-4 right-4 items-end',
            'bottom-center': 'bottom-4 left-1/2 -translate-x-1/2 items-center',
            'bottom-left': 'bottom-4 left-4 items-start'
        };
        return base + ' ' + (map[position] || map['top-right']);
    }

    function toastClasses(level) {
        var base = 'pointer-events-auto relative flex w-full items-start gap-3 overflow-hidden rounded-xl border px-4 py-3 text-sm shadow-2xl ring-1 ring-black/10 transition-all duration-250';
        var map = {
            success: 'border-emerald-300/80 bg-emerald-700 text-emerald-50',
            error: 'border-rose-300/80 bg-rose-700 text-rose-50',
            warning: 'border-amber-300/80 bg-amber-700 text-amber-50',
            info: 'border-sky-300/80 bg-sky-700 text-sky-50'
        };
        return base + ' ' + (map[level] || map.info);
    }

    function liveMode(level) {
        return level === 'error' || level === 'warning' ? 'assertive' : 'polite';
    }

    function ensureRoot() {
        var root = document.getElementById('toast-root');
        if (root && root.parentNode !== document.body) {
            root.remove();
            root = null;
        }
        if (!root) {
            root = document.createElement('div');
            root.id = 'toast-root';
            root.className = 'pointer-events-none fixed inset-0 z-[200]';
            document.body.appendChild(root);
        }
        return root;
    }

    function ensureContainer(position) {
        var root = ensureRoot();
        if (!root) return null;

        var id = 'toast-container-' + position;
        var existing = document.getElementById(id);
        if (existing) return existing;

        var container = document.createElement('div');
        container.id = id;
        container.className = containerClasses(position);
        // Inline fallback so container is visible even if CSS cache is stale.
        container.style.position = 'fixed';
        container.style.zIndex = '210';
        container.style.display = 'flex';
        container.style.flexDirection = 'column';
        container.style.gap = '0.75rem';
        container.style.maxWidth = '24rem';
        if (position === 'top-right') {
            container.style.top = '1rem';
            container.style.right = '1rem';
        } else if (position === 'top-left') {
            container.style.top = '1rem';
            container.style.left = '1rem';
        } else if (position === 'top-center') {
            container.style.top = '1rem';
            container.style.left = '50%';
            container.style.transform = 'translateX(-50%)';
        } else if (position === 'bottom-right') {
            container.style.bottom = '1rem';
            container.style.right = '1rem';
        } else if (position === 'bottom-left') {
            container.style.bottom = '1rem';
            container.style.left = '1rem';
        } else if (position === 'bottom-center') {
            container.style.bottom = '1rem';
            container.style.left = '50%';
            container.style.transform = 'translateX(-50%)';
        }
        root.appendChild(container);
        return container;
    }

    function dismissToast(el) {
        if (!el || el.dataset.dismissing === 'true') return;
        el.dataset.dismissing = 'true';
        if (el._dismissTimer) {
            clearTimeout(el._dismissTimer);
            el._dismissTimer = null;
        }
        el.classList.remove('opacity-100', 'translate-y-0', 'scale-100');
        el.classList.add('opacity-0', 'translate-y-2', 'scale-95');
        setTimeout(function () {
            if (el && el.parentNode) el.parentNode.removeChild(el);
        }, 220);
    }

    function renderToast(payload) {
        var container = ensureContainer(payload.position);
        if (!container) return;

        var toast = document.createElement('div');
        toast.className = toastClasses(payload.level) + ' opacity-0 translate-y-2 scale-95';
        // Inline fallback ensures readability if utility CSS is not yet loaded.
        toast.style.background = payload.level === 'success' ? '#047857' : payload.level === 'error' ? '#be123c' : payload.level === 'warning' ? '#b45309' : '#0369a1';
        toast.style.color = '#f8fafc';
        toast.style.border = '1px solid rgba(255,255,255,0.25)';
        toast.style.borderRadius = '0.75rem';
        toast.style.padding = '0.75rem 1rem';
        toast.style.boxShadow = '0 10px 30px rgba(2, 6, 23, 0.24)';
        toast.setAttribute('role', 'status');
        toast.setAttribute('aria-live', liveMode(payload.level));
        toast.setAttribute('aria-atomic', 'true');

        var text = document.createElement('p');
        text.className = 'flex-1 pr-2 leading-5';
        text.textContent = payload.message;

        var close = document.createElement('button');
        close.type = 'button';
        close.className = 'rounded-md p-1 text-current/80 hover:bg-white/15 hover:text-white';
        close.setAttribute('aria-label', 'Dismiss notification');
        close.innerHTML = '&times;';
        close.addEventListener('click', function () {
            dismissToast(toast);
        });

        var progressTrack = document.createElement('div');
        progressTrack.className = 'pointer-events-none absolute inset-x-0 bottom-0 h-1 bg-black/20';

        var progressBar = document.createElement('div');
        progressBar.className = 'h-full w-full bg-white/80';
        progressBar.style.transitionProperty = 'width';
        progressBar.style.transitionTimingFunction = 'linear';
        progressBar.style.transitionDuration = payload.duration + 'ms';
        progressTrack.appendChild(progressBar);

        toast.appendChild(text);
        toast.appendChild(close);
        toast.appendChild(progressTrack);
        container.appendChild(toast);

        requestAnimationFrame(function () {
            toast.classList.remove('opacity-0', 'translate-y-2', 'scale-95');
            toast.classList.add('opacity-100', 'translate-y-0', 'scale-100');
            requestAnimationFrame(function () {
                progressBar.style.width = '0%';
            });
        });

        toast._dismissTimer = setTimeout(function () {
            dismissToast(toast);
        }, payload.duration);
    }

    function processQueue(queue) {
        if (!queue || processedQueues.has(queue)) return;
        processedQueues.add(queue);

        var items = queue.querySelectorAll('.js-toast-item');
        items.forEach(function (item) {
            var tags = splitTags(item.getAttribute('data-toast-tags'));
            renderToast({
                message: item.getAttribute('data-toast-message') || '',
                level: findLevel(tags),
                position: findPosition(tags),
                duration: findDuration(tags)
            });
        });

        queue.remove();
    }

    function initToasts(root) {
        var scope = root || document;
        var queues = [];
        if (scope.matches && scope.matches('.js-toast-queue')) {
            queues.push(scope);
        }
        var found = scope.querySelectorAll ? scope.querySelectorAll('.js-toast-queue') : [];
        found.forEach(function (queue) {
            queues.push(queue);
        });
        queues.forEach(processQueue);
    }

    document.addEventListener('DOMContentLoaded', function () {
        initToasts(document);
    });

    function handleHtmxLifecycle(event) {
        var swappedRoot = event && event.detail && event.detail.elt ? event.detail.elt : (event.target || document);
        initToasts(swappedRoot);
        // Fallback for async DOM mutations that occur right after HTMX swap/settle.
        setTimeout(function () {
            initToasts(document);
        }, 0);
    }

    document.body.addEventListener('htmx:afterSwap', function (event) {
        handleHtmxLifecycle(event);
    });

    document.body.addEventListener('htmx:afterSettle', function (event) {
        handleHtmxLifecycle(event);
    });

    if (window.MutationObserver) {
        var observer = new MutationObserver(function (mutations) {
            for (var i = 0; i < mutations.length; i += 1) {
                var addedNodes = mutations[i].addedNodes;
                for (var j = 0; j < addedNodes.length; j += 1) {
                    var node = addedNodes[j];
                    if (!node || node.nodeType !== 1) continue;
                    initToasts(node);
                }
            }
        });
        observer.observe(document.body, { childList: true, subtree: true });
    }
})();
