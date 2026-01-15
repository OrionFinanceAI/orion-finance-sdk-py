(function() {
    // Immediately force light theme
    document.documentElement.setAttribute('data-theme', 'light');
    document.documentElement.classList.remove('theme-dark');
    document.documentElement.classList.add('theme-light');

    // Observer to prevent changes by other scripts
    var observer = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
            if (mutation.type == "attributes" && (mutation.attributeName == "data-theme" || mutation.attributeName == "class")) {
                var currentTheme = document.documentElement.getAttribute('data-theme');
                if (currentTheme !== 'light') {
                    document.documentElement.setAttribute('data-theme', 'light');
                }
                if (document.documentElement.classList.contains('theme-dark')) {
                    document.documentElement.classList.remove('theme-dark');
                    document.documentElement.classList.add('theme-light');
                }
            }
        });
    });
    
    observer.observe(document.documentElement, {
        attributes: true,
        attributeFilter: ['data-theme', 'class']
    });
})();
