'use strict';

// Django's standard FilteredSelectMultiple searches the entire option label.
// Our label also contains bot, price and stock metadata, which made a search
// such as "GPT" match every product belonging to a GPT-named supplier. For
// this one selector, search only the product title before the stable marker.
(function installProductOnlyFilter() {
    function install() {
        if (!window.SelectBox || window.SelectBox.productOnlyFilterInstalled) {
            return false;
        }

        const originalFilter = window.SelectBox.filter;
        window.SelectBox.filter = function(id, text) {
            if (!id.startsWith('id_selected_bot_products_')) {
                return originalFilter.call(this, id, text);
            }

            const tokens = text.toLocaleLowerCase().trim().split(/\s+/).filter(Boolean);
            const cache = window.SelectBox.cache[id] || [];
            for (const node of cache) {
                const productName = node.text.split(' [Bot:')[0].toLocaleLowerCase();
                node.displayed = tokens.every((token) => productName.includes(token)) ? 1 : 0;
            }
            window.SelectBox.redisplay(id);
        };
        window.SelectBox.productOnlyFilterInstalled = true;
        return true;
    }

    if (!install()) {
        window.addEventListener('load', install, {once: true});
    }
})();
