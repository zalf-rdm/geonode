
(function () {
    // ---- Safe boot for the global config array ----
    var formsetsInTabs = Array.isArray(window.formsetsInTabs) ? window.formsetsInTabs : [];

    // ---- Init on load: reorder labels and hide DELETEs ----
    for (var i = 0; i < formsetsInTabs.length; i++) {
        var name = formsetsInTabs[i];
        if (!name) continue;
        var $form = $('#' + name);
        if ($form.length) {
            reOrderUI($form);
            hideDeleteCheckbox($form);
            // Ensure one tab is active
            if (!$form.find('.allTabs li.active').length) {
                var $first = $form.find('.allTabs li').not('.li-add').not('.templateTab').first();
                if ($first.length) {
                    $first.addClass('active').find('a').attr('aria-expanded', true);
                    var target = $first.find('a').attr('href');
                    $form.find('.allContent .tab-pane').removeClass('active');
                    if (target) $form.find(target).addClass('active');
                }
            }
        }
    }

    // ---- Utilities ----
    function getFormsetInfo($form) {
        var prefix = $form.attr('id');
        return {
            prefix: prefix,
            totalForms: parseInt($('#id_' + prefix + '-TOTAL_FORMS').val(), 10),
            initialForms: parseInt($('#id_' + prefix + '-INITIAL_FORMS').val(), 10),
            maxForms: parseInt($('#id_' + prefix + '-MAX_NUM_FORMS').val(), 10),
            minForms: parseInt($('#id_' + prefix + '-MIN_NUM_FORMS').val(), 10),
            $allTabs: $form.find('.allTabs'),
            $allContents: $form.find('.allContent'),
            $templateTab: $form.find('.templateTab'),
            $templateContent: $form.find('.templateContent')
        };
    }

    function removeActive($form) {
        $form.find('.allTabs li').removeClass('active').find('a').attr('aria-expanded', false);
        $form.find('.allContent .tab-pane').removeClass('active');
    }

    function hideDeleteCheckbox($form) {
        $form.find(".allContent input[name$='-DELETE']").each(function () {
            var $inp = $(this);
            $inp.closest('.form-group').hide();
            $('label[for="' + $inp.attr('id') + '"]').hide();
            $inp.closest('[hidden], .hidden').attr('hidden', true).hide();
        });
    }

    function getAttr($form, name) {
        return $form.attr('data-' + name);
    }

    // Custom tab labels are now handled by inline scripts in templates when needed.

    // ----- Add new tab -----
    window.addNewTab = function addNewTab(buttonEl) {
        var $form = $(buttonEl).closest("div[id^='form']");
        var info = getFormsetInfo($form);
        var prefix = info.prefix;

        // respect MAX if present
        if (!isNaN(info.maxForms) && info.totalForms >= info.maxForms) {
            console.warn('Max forms reached for', prefix);
            return;
        }

        removeActive($form);

        var newIndex = info.totalForms; // next index for Django
        var label = newIndex + 1;

        // Clone tab (UI)
        var $newTab = info.$templateTab.clone(true)
            .removeClass('hidden templateTab nav-empty')
            .attr('id', '');
        $newTab.find('a')
            .attr('href', '#' + prefix + '-' + newIndex)
            .attr('aria-controls', prefix + '-' + newIndex)
            .find('.newTabTex')
            .text(label)
            .addClass('tabTex')
            .removeClass('newTabTex');
        $newTab.insertBefore($form.find('.li-add')).addClass('active');

        // Clone content (data)
        var $newContent = info.$templateContent.clone(true)
            .removeClass('hidden templateContent nav-empty')
            .attr('id', prefix + '-' + newIndex)
            .addClass('in active');

        // Replace __prefix__ in for/name/id
        $newContent.find('select, input, textarea, label, div').each(function () {
            var $el = $(this);
            ['for', 'name', 'id'].forEach(function (attr) {
                if ($el.attr(attr)) $el.attr(attr, $el.attr(attr).replace('__prefix__', newIndex));
            });
        });

        $newContent.insertBefore(info.$templateContent);

        // Update TOTAL_FORMS (only on add)
        $('#id_' + prefix + '-TOTAL_FORMS').val(newIndex + 1);

        reOrderUI($form);
        hideDeleteCheckbox($form);
    };

    // ----- Delete flow (with confirmation) -----
    var deleteCandidate = null;

    // Try to open Bootstrap3 modal if available; if not, lazy-load bootstrap.js then open; else fallback
    function ensureBs3ModalThen(cb) {
        // If jQuery plugin exists, we are good
        if ($ && $.fn && typeof $.fn.modal === 'function') {
            cb(true);
            return;
        }
        // Try to lazy-load bootstrap.js (path based on staticUrl if available)
        var staticUrl = (window.staticUrl || '/static/').replace(/\/?$/, '/');
        var src = staticUrl + 'lib/js/bootstrap.js';
        var tagId = 'fit-bootstrap3-js';

        if (document.getElementById(tagId)) {
            // already loading/loaded
            document.getElementById(tagId).addEventListener('load', function () { cb(!!($.fn && $.fn.modal)); });
            document.getElementById(tagId).addEventListener('error', function () { cb(false); });
            return;
        }

        var s = document.createElement('script');
        s.id = tagId;
        s.src = src;
        s.onload = function () { cb(!!($.fn && $.fn.modal)); };
        s.onerror = function () { cb(false); };
        document.head.appendChild(s);
    }

    // Lightweight inline modal (no deps) — created on demand
    function ensureInlineConfirm() {
        if (document.getElementById('fit-confirm-overlay')) return;
        var css = '\
#fit-confirm-overlay{position:fixed;inset:0;background:rgba(0,0,0,.35);display:none;align-items:center;justify-content:center;z-index:20000}\
#fit-confirm-box{background:#fff;border-radius:6px;width:420px;max-width:90%;box-shadow:0 10px 30px rgba(0,0,0,.2);overflow:hidden}\
#fit-confirm-head{padding:12px 16px;border-bottom:1px solid #eee;font-weight:600}\
#fit-confirm-body{padding:16px}\
#fit-confirm-foot{padding:12px 16px;border-top:1px solid #eee;text-align:right}\
#fit-confirm-foot button{margin-left:8px}';
        var style = document.createElement('style');
        style.id = 'fit-confirm-style';
        style.textContent = css;
        document.head.appendChild(style);

        var html = '\
<div id="fit-confirm-overlay" role="dialog" aria-modal="true" aria-labelledby="fit-confirm-title">\
  <div id="fit-confirm-box">\
    <div id="fit-confirm-head"><span id="fit-confirm-title">Confirm deletion</span></div>\
    <div id="fit-confirm-body">Are you sure you want to delete this information?</div>\
    <div id="fit-confirm-foot">\
      <button type="button" class="btn btn-default" id="fit-confirm-no">No</button>\
      <button type="button" class="btn btn-danger" id="fit-confirm-yes">Yes, delete</button>\
    </div>\
  </div>\
</div>';
        document.body.insertAdjacentHTML('beforeend', html);

        $(document).on('click', '#fit-confirm-no', function () {
            $('#fit-confirm-overlay').hide();
            deleteCandidate = null;
        });
        $(document).on('click', '#fit-confirm-yes', function () {
            $('#fit-confirm-overlay').hide();
            if (deleteCandidate) reallyRemoveTab(deleteCandidate);
            deleteCandidate = null;
        });
        $(document).on('click', '#fit-confirm-overlay', function (e) {
            if (e.target && e.target.id === 'fit-confirm-overlay') $('#fit-confirm-overlay').hide();
        });
        $(document).on('keydown', function (e) {
            if ($('#fit-confirm-overlay').is(':visible') && e.key === 'Escape') $('#fit-confirm-overlay').hide();
        });
    }

    function openInlineConfirm() {
        ensureInlineConfirm();
        $('#fit-confirm-overlay').css('display', 'flex');
    }

    // Called by buttons in template
    window.confirmRemoveTab = function confirmRemoveTab(buttonEl) {
        deleteCandidate = buttonEl;

        // Prefer Bootstrap3 modal if present / loadable
        ensureBs3ModalThen(function (hasBsModal) {
            if (hasBsModal && document.getElementById('confirmDeleteModal')) {
                $('#confirmDeleteModal').modal('show');
            } else {
                openInlineConfirm(); // fallback no-deps
            }
        });
    };

    // Confirm button (works for BS3 modal)
    $(document).on('click', '#confirmDeleteBtn', function () {
        if (deleteCandidate) {
            reallyRemoveTab(deleteCandidate);
            deleteCandidate = null;
        }
        if ($ && $.fn && typeof $.fn.modal === 'function') {
            $('#confirmDeleteModal').modal('hide');
        }
    });

    // ----- Actual delete -----
    function reallyRemoveTab(buttonEl) {
        var $form = $(buttonEl).closest("div[id^='form']");
        var info = getFormsetInfo($form);
        var prefix = info.prefix;

        // enforce min forms
        var $visibleTabs = $form.find('.allTabs li').not('.li-add').not('.templateTab');
        var min = isNaN(info.minForms) ? 0 : info.minForms;
        if ($visibleTabs.length <= min) {
            console.warn('Minimum forms reached for', prefix);
            return;
        }

        var $tab = $(buttonEl).closest('li');
        var wasActive = $tab.hasClass('active');
        var href = $tab.find('a').attr('href');
        var paneId = (href && href[0] === '#') ? href.slice(1) : null;

        // remove tab from UI
        $tab.remove();

        // mark DELETE on content and move it after the template (kept in DOM for Django)
        if (paneId) {
            var $content = $form.find('#' + paneId);
            var $tpl = info.$templateContent;
            $content.find("input[name$='-DELETE']").prop("checked", true);
            $content.attr('data-deleted', '1').hide().insertAfter($tpl);
        }

        // activate another tab if needed
        var $remaining = $form.find('.allTabs li').not('.li-add').not('.templateTab');
        if (wasActive && $remaining.length) {
            var $first = $remaining.first();
            $remaining.removeClass('active').find('a').attr('aria-expanded', false);
            $form.find('.allContent .tab-pane').removeClass('active');
            $first.addClass('active').find('a').attr('aria-expanded', true);
            var tgt = $first.find('a').attr('href');
            if (tgt) $form.find(tgt).addClass('active');
        } else if (!wasActive) {
            var $current = $form.find('.allTabs li.active').first();
            if ($current.length) {
                var ct = $current.find('a').attr('href');
                $form.find('.allContent .tab-pane').removeClass('active');
                if (ct) $form.find(ct).addClass('active');
            }
        }

        // DO NOT change TOTAL_FORMS on delete
        reOrderUI($form);
        hideDeleteCheckbox($form);
    }

    // ----- Reorder only the UI (labels/anchors), do not rename fields after render -----
    function reOrderUI($form) {
        var prefix = $form.attr("id");
        var hasCustomLabels = !!getAttr($form, 'tab-label-field');

        // Re-attach anchor targets and labels based on current visible tab order
        var $tabs = $form.find('.allTabs li a');
        $tabs.each(function (i) {
            $(this)
                .attr('href', '#' + prefix + '-' + i)
                .attr('aria-controls', prefix + '-' + i)
                .find('.tabTex').each(function () {
                    if (!hasCustomLabels) {
                        $(this).text(i + 1);
                    }
                });
        });

        // Re-id panes by order (UI only). We do NOT rename field names/ids after render to keep Django safe.
        var $panes = $form.find('.allContent .tab-pane');
        var paneIdx = 0;
        $panes.each(function () {
            var $pane = $(this);
            if ($pane.attr('id') === 'templateContent') return;
            $pane.attr('id', prefix + '-' + paneIdx);
            paneIdx += 1;
        });
    }

    // Dynamic tab label adjustments, if needed, should be handled by specialized scripts in templates.

})();
