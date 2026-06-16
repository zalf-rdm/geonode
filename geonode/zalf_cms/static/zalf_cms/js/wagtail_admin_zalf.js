(function() {
    function applyDocumentBranding() {
        if (document.title && document.title.indexOf("Wagtail") !== -1) {
            document.title = document.title.replace(/Wagtail/g, "ZALF CMS");
        }
    }

    document.addEventListener("DOMContentLoaded", function() {
        applyDocumentBranding();
    });
})();
