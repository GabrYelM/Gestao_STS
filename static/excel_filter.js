/**
 * Excel-Style Column Filtering Plugin for DataTables
 * Gestão STS Penha
 * Comportamento 100% fiel ao Microsoft Excel
 */

window.initExcelFilters = function(dtApi, colIndices) {
    if (!dtApi) return;

    var table = dtApi.table ? dtApi.table() : dtApi;
    var $tableNode = $(table.node());
    var columns = dtApi.columns(colIndices !== undefined ? colIndices : '');

    // Armazena filtros ativos por coluna: { colIndex: Array[valores_selecionados] }
    var activeFilters = {};

    columns.every(function() {
        var column = this;
        var colIdx = column.index();
        var $header = $(column.header());

        // Evita duplicar se já inicializado
        if ($header.find('.btn-excel-filter').length > 0) return;

        // Cria container flex no header
        var headerText = $header.contents().filter(function() {
            return this.nodeType === 3;
        }).text().trim() || $header.text().trim();

        // Limpa texto puro e envolve em estrutura flex com botão de funil e alça de redimensionamento
        $header.html(`
            <div class="d-flex align-items-center justify-content-between gap-1 w-100 header-excel-container">
                <span class="header-text text-nowrap" title="${headerText}">${headerText}</span>
                <button type="button" class="btn btn-sm p-0 btn-excel-filter" title="Filtrar por esta coluna" data-col="${colIdx}">
                    <i class="bi bi-funnel filter-icon"></i>
                </button>
            </div>
            <div class="dt-column-resizer" title="Arraste para redimensionar a coluna | Duplo clique para auto-ajustar"></div>
        `);

        var $btn = $header.find('.btn-excel-filter');
        var $resizer = $header.find('.dt-column-resizer');

        // Impede que o clique no filtro abra o dropdown ou acione ordenação
        $btn.on('click', function(e) {
            e.stopPropagation();
            fecharTodosDropdowns();
            abrirDropdownFiltro(column, $btn);
        });

        // Eventos de Redimensionamento da Coluna (Estilo Excel)
        $resizer.on('click', function(e) {
            e.stopPropagation();
            e.preventDefault();
        });

        $resizer.on('mousedown', function(e) {
            e.stopPropagation();
            e.preventDefault();

            var $th = $header;
            var startX = e.pageX;
            var startWidth = $th.outerWidth();
            var minWidth = 50;
            var $table = $th.closest('table');

            // Permite que a tabela se expanda horizontalmente de forma suave
            $table.css({
                'min-width': '100%',
                'width': 'max-content'
            });

            $('body').addClass('is-resizing-column');
            $resizer.addClass('is-resizing');

            function onMouseMove(moveEvent) {
                moveEvent.preventDefault();
                var diffX = moveEvent.pageX - startX;
                var newWidth = Math.max(minWidth, startWidth + diffX);
                $th.css({
                    'width': newWidth + 'px',
                    'min-width': newWidth + 'px',
                    'max-width': newWidth + 'px'
                });
            }

            function onMouseUp(upEvent) {
                upEvent.preventDefault();
                $('body').removeClass('is-resizing-column');
                $resizer.removeClass('is-resizing');
                $(document).off('mousemove', onMouseMove);
                $(document).off('mouseup', onMouseUp);
            }

            $(document).on('mousemove', onMouseMove);
            $(document).on('mouseup', onMouseUp);
        });

        // Duplo clique na divisória: Restaura o tamanho automático da coluna
        $resizer.on('dblclick', function(e) {
            e.stopPropagation();
            e.preventDefault();
            $header.css({
                'width': '',
                'min-width': '',
                'max-width': ''
            });
            if (dtApi && dtApi.columns && dtApi.columns.adjust) {
                dtApi.columns.adjust().draw(false);
            }
        });
    });

    function fecharTodosDropdowns() {
        $('.excel-filter-dropdown').remove();
    }

    // Fecha ao clicar fora
    $(document).on('click', function(e) {
        if (!$(e.target).closest('.excel-filter-dropdown, .btn-excel-filter').length) {
            fecharTodosDropdowns();
        }
    });

    function abrirDropdownFiltro(column, $btn) {
        var colIdx = column.index();
        var colTitle = $(column.header()).find('.header-text').text().trim();

        // Obtém todos os valores únicos brutos da coluna inteira
        var uniqueData = [];
        var valCounts = {};
        
        column.data().each(function(d) {
            var rawText = $('<div>').html(d).text().trim();
            if (rawText === '') rawText = '(Vazio)';
            if (!valCounts[rawText]) {
                valCounts[rawText] = 0;
                uniqueData.push(rawText);
            }
            valCounts[rawText]++;
        });

        // Ordena valores numericamente ou alfabeticamente
        uniqueData.sort(function(a, b) {
            var numA = parseFloat(a.replace(/[^0-9.-]+/g, ''));
            var numB = parseFloat(b.replace(/[^0-9.-]+/g, ''));
            if (!isNaN(numA) && !isNaN(numB)) return numA - numB;
            return a.localeCompare(b, 'pt-BR');
        });

        // Itens que estão atualmente selecionados/filtrados
        var hasActiveFilter = Boolean(activeFilters[colIdx]);
        var selectedSet = hasActiveFilter ? new Set(activeFilters[colIdx]) : new Set(uniqueData);
        var isAllSelected = selectedSet.size === uniqueData.length;

        // Constrói o HTML do Dropdown estilo Excel
        var $dropdown = $(`
            <div class="excel-filter-dropdown card shadow-lg" data-col="${colIdx}">
                <div class="card-header bg-light d-flex justify-content-between align-items-center py-2 px-3">
                    <strong class="small text-truncate me-2"><i class="bi bi-funnel text-primary me-1"></i> ${colTitle}</strong>
                    <button type="button" class="btn-close btn-sm btn-fechar"></button>
                </div>
                <div class="card-body p-2">
                    <!-- Campo de Busca -->
                    <div class="input-group input-group-sm mb-2">
                        <span class="input-group-text bg-white"><i class="bi bi-search text-muted"></i></span>
                        <input type="text" class="form-control excel-search-input" placeholder="Pesquisar..." autofocus>
                    </div>

                    <!-- Opção de Adicionar Seleção Atual (Estilo Excel) -->
                    <div class="form-check form-check-sm mb-1 d-none div-add-to-filter">
                        <input class="form-check-input chk-add-to-filter" type="checkbox" id="chk_add_${colIdx}">
                        <label class="form-check-label text-muted small" for="chk_add_${colIdx}">
                            Adicionar seleção atual ao filtro
                        </label>
                    </div>

                    <!-- Selecionar Tudo -->
                    <div class="form-check form-check-sm mb-1 pb-1 border-bottom">
                        <input class="form-check-input chk-select-all" type="checkbox" id="chk_all_${colIdx}" ${isAllSelected ? 'checked' : ''}>
                        <label class="form-check-label fw-bold small lbl-select-all" for="chk_all_${colIdx}">
                            (Selecionar Tudo)
                        </label>
                    </div>

                    <!-- Lista de Checkboxes -->
                    <div class="excel-filter-items-list" style="max-height: 220px; overflow-y: auto;">
                        ${uniqueData.map(function(val, idx) {
                            var isChecked = selectedSet.has(val);
                            var safeVal = $('<div>').text(val).html();
                            return `
                                <div class="form-check form-check-sm excel-item-row py-1" data-val="${safeVal}">
                                    <input class="form-check-input chk-item" type="checkbox" value="${safeVal}" id="chk_${colIdx}_${idx}" ${isChecked ? 'checked' : ''}>
                                    <label class="form-check-label small d-flex justify-content-between text-truncate" for="chk_${colIdx}_${idx}" title="${safeVal}">
                                        <span class="text-truncate">${safeVal}</span>
                                        <span class="badge bg-light text-secondary ms-1 count-badge">${valCounts[val]}</span>
                                    </label>
                                </div>
                            `;
                        }).join('')}
                    </div>
                </div>
                <div class="card-footer bg-light py-2 px-3 d-flex justify-content-between gap-1">
                    <button type="button" class="btn btn-sm btn-outline-secondary btn-limpar-filtro">
                        <i class="bi bi-arrow-counterclockwise me-1"></i>Limpar
                    </button>
                    <div class="d-flex gap-1">
                        <button type="button" class="btn btn-sm btn-light btn-fechar">Cancelar</button>
                        <button type="button" class="btn btn-sm btn-primary btn-aplicar fw-bold px-3">
                            <i class="bi bi-check2 me-1"></i>Aplicar
                        </button>
                    </div>
                </div>
            </div>
        `);

        $('body').append($dropdown);

        // Posicionamento absoluto do Dropdown sob o botão
        var offset = $btn.offset();
        var dropWidth = 300;
        var leftPos = offset.left;
        
        // Ajusta se passar do limite direito da tela
        if (leftPos + dropWidth > $(window).width()) {
            leftPos = $(window).width() - dropWidth - 15;
        }

        $dropdown.css({
            top: (offset.top + $btn.outerHeight() + 5) + 'px',
            left: leftPos + 'px',
            width: dropWidth + 'px',
            position: 'absolute',
            zIndex: 9999
        });

        // Elementos internos
        var $searchInput = $dropdown.find('.excel-search-input');
        var $selectAll = $dropdown.find('.chk-select-all');
        var $lblSelectAll = $dropdown.find('.lbl-select-all');
        var $itemsList = $dropdown.find('.excel-filter-items-list');
        var $divAdd = $dropdown.find('.div-add-to-filter');
        var $chkAdd = $dropdown.find('.chk-add-to-filter');

        // Busca em tempo real idêntica ao Excel
        $searchInput.on('input', function() {
            var term = $(this).val().toLowerCase().trim();
            
            if (term === '') {
                // Campo de busca vazio: mostra todas as opções
                $itemsList.find('.excel-item-row').removeClass('d-none');
                $lblSelectAll.text('(Selecionar Tudo)');
                $divAdd.addClass('d-none');
            } else {
                // Campo de busca preenchido: mostra apenas as opções correspondentes
                $itemsList.find('.excel-item-row').each(function() {
                    var text = $(this).find('label').text().toLowerCase();
                    if (text.indexOf(term) > -1) {
                        $(this).removeClass('d-none');
                    } else {
                        $(this).addClass('d-none');
                    }
                });
                $lblSelectAll.text('(Selecionar resultados da pesquisa)');
                
                // Se já havia filtro ativo, dá a opção de adicionar à seleção
                if (hasActiveFilter) {
                    $divAdd.removeClass('d-none');
                }
            }
            
            atualizarEstadoSelectAll();
        });

        // Clique em Selecionar / Deselecionar Tudo
        $selectAll.on('change', function() {
            var isChecked = $(this).is(':checked');
            // Marca/desmarca apenas as opções VISÍVEIS
            $itemsList.find('.excel-item-row:not(.d-none) .chk-item').prop('checked', isChecked);
        });

        $itemsList.on('change', '.chk-item', function() {
            atualizarEstadoSelectAll();
        });

        function atualizarEstadoSelectAll() {
            var $visible = $itemsList.find('.excel-item-row:not(.d-none) .chk-item');
            var $checked = $visible.filter(':checked');
            $selectAll.prop('checked', $visible.length > 0 && $visible.length === $checked.length);
        }

        // Botão Limpar Filtro
        $dropdown.find('.btn-limpar-filtro').on('click', function() {
            delete activeFilters[colIdx];
            column.search('').draw();
            atualizarIconeColuna(column, false);
            fecharTodosDropdowns();
        });

        // Botão Fechar / Cancelar
        $dropdown.find('.btn-fechar').on('click', function() {
            fecharTodosDropdowns();
        });

        // Botão Aplicar (Lógica 100% Excel)
        $dropdown.find('.btn-aplicar').on('click', function() {
            var searchTerm = $searchInput.val().trim();
            var checkedValues = [];

            if (searchTerm !== '') {
                // Se o usuário FILTROU POR DIGITAÇÃO na caixa de pesquisa:
                // Considera apenas as opções visíveis que estão marcadas!
                $itemsList.find('.excel-item-row:not(.d-none) .chk-item:checked').each(function() {
                    var val = $(this).val();
                    if (val === '(Vazio)') val = '^$';
                    checkedValues.push(val);
                });

                // Se marcou "Adicionar seleção atual ao filtro", inclui os valores anteriores
                if ($chkAdd.is(':checked') && activeFilters[colIdx]) {
                    activeFilters[colIdx].forEach(function(v) {
                        if (checkedValues.indexOf(v) === -1) {
                            checkedValues.push(v);
                        }
                    });
                }
            } else {
                // Se a caixa de pesquisa estava vazia, considera todos os checkboxes marcados
                $itemsList.find('.chk-item:checked').each(function() {
                    var val = $(this).val();
                    if (val === '(Vazio)') val = '^$';
                    checkedValues.push(val);
                });
            }

            if (checkedValues.length === 0) {
                // Nenhuma opção marcada: não exibe nada
                activeFilters[colIdx] = [];
                column.search('^$NO_MATCH$', true, false).draw();
                atualizarIconeColuna(column, true);
            } else if (checkedValues.length === uniqueData.length && searchTerm === '') {
                // Todas as opções marcadas sem pesquisa: remove filtro
                delete activeFilters[colIdx];
                column.search('').draw();
                atualizarIconeColuna(column, false);
            } else {
                // Subconjunto marcado: aplica regex de união exata
                activeFilters[colIdx] = checkedValues;
                
                var regexParts = checkedValues.map(function(v) {
                    if (v === '^$') return '^$';
                    return '^' + $.fn.dataTable.util.escapeRegex(v) + '$';
                });
                
                var searchPattern = regexParts.join('|');
                column.search(searchPattern, true, false).draw();
                atualizarIconeColuna(column, true);
            }

            fecharTodosDropdowns();
        });

        function atualizarIconeColuna(col, isActive) {
            var $btnEl = $(col.header()).find('.btn-excel-filter');
            if (isActive) {
                $btnEl.addClass('btn-excel-filter-active');
                $btnEl.find('.filter-icon').removeClass('bi-funnel').addClass('bi-funnel-fill');
            } else {
                $btnEl.removeClass('btn-excel-filter-active');
                $btnEl.find('.filter-icon').removeClass('bi-funnel-fill').addClass('bi-funnel');
            }
        }
    }
};
