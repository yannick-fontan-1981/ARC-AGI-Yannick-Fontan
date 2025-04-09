
// Internal state.
var CURRENT_INPUT_GRID = new Grid(3, 3);
var CURRENT_OUTPUT_GRID = new Grid(3, 3);
var TEST_PAIRS = new Array();
var CURRENT_TEST_PAIR_INDEX = 0;
var COPY_PASTE_DATA = new Array();

// Cosmetic.
var EDITION_GRID_HEIGHT = 500;
var EDITION_GRID_WIDTH = 500;
var MAX_CELL_SIZE = 100;

var CURRENT_PAIR_ID = 0;
var CURRENT_IS_TEST_PAIR = false;

var TRAINING_PAIRS = [];
var TRAINING_PAIR_IDS = [];

function resetTask() {
    // Clear the left column containers
    $('#training_pairs_container').empty();
    $('#test_pair_container').empty();

    // Reset data structures
    TRAINING_PAIRS = [];
    TEST_PAIRS = [];
    TRAINING_PAIR_IDS = [];
    CURRENT_PAIR_ID = null;
    CURRENT_IS_TEST_PAIR = false;

    // Reset current grids
    CURRENT_INPUT_GRID = new Grid(3, 3);
    CURRENT_OUTPUT_GRID = new Grid(3, 3);

    // Clear the edition grids
    $('#output_grid .edition_grid').empty();
    $('#evaluation_input .edition_grid').empty();
}

function refreshEditionGrid(jqGrid, dataGrid) {
    fillJqGridWithData(jqGrid, dataGrid);
    setUpEditionGridListeners(jqGrid);
    fitCellsToContainer(jqGrid, dataGrid.height, dataGrid.width, EDITION_GRID_HEIGHT, EDITION_GRID_HEIGHT);
    initializeSelectable();
}

function resizeInputGrid() {
    var size = $('#input_grid_size').val();
    size = parseSizeTupleForCreation(size);
    if (!size) {
        return;
    }
    var height = size[0];
    var width = size[1];

    // Synchronize the current grid with the edition grid
    syncFromEditionGridToDataGrid();

    // Create a new grid with the new size
    var dataGrid = JSON.parse(JSON.stringify(CURRENT_INPUT_GRID.grid));
    var newGrid = createResizedGrid(dataGrid, height, width);

    CURRENT_INPUT_GRID = new Grid(height, width, newGrid);

    // Update the input grid display
    fillTestInput(CURRENT_INPUT_GRID);
}

function syncFromEditionGridToDataGrid() {
    copyJqGridToDataGrid($('#output_grid .edition_grid'), CURRENT_OUTPUT_GRID);
    copyJqGridToDataGrid($('#evaluation_input .edition_grid'), CURRENT_INPUT_GRID);
}

function syncFromDataGridToEditionGrid() {
     refreshEditionGrid($('#output_grid .edition_grid'), CURRENT_OUTPUT_GRID);
    refreshEditionGrid($('#evaluation_input .edition_grid'), CURRENT_INPUT_GRID);
}

function getSelectedSymbol() {
    selected = $('#symbol_picker .selected-symbol-preview')[0];
    return $(selected).attr('symbol');
}

function setUpEditionGridListeners(jqGrid) {
    jqGrid.find('.cell').click(function(event) {
        cell = $(event.target);
        symbol = getSelectedSymbol();

        mode = $('input[name=tool_switching]:checked').val();
        if (mode == 'floodfill') {
            // If floodfill: fill all connected cells.
            syncFromEditionGridToDataGrid();
            grid = CURRENT_OUTPUT_GRID.grid;
            floodfillFromLocation(grid, cell.attr('x'), cell.attr('y'), symbol);
            syncFromDataGridToEditionGrid();
        }
        else if (mode == 'edit') {
            // Else: fill just this cell.
            setCellSymbol(cell, symbol);
        }
    });
}

function createResizedGrid(oldGrid, newHeight, newWidth) {
    var newGrid = new Array(newHeight);
    for (var i = 0; i < newHeight; i++) {
        newGrid[i] = new Array(newWidth);
        for (var j = 0; j < newWidth; j++) {
            if (oldGrid[i] && oldGrid[i][j] !== undefined) {
                newGrid[i][j] = oldGrid[i][j];
            } else {
                newGrid[i][j] = 0; // Default symbol
            }
        }
    }
    return newGrid;
}

function resizeOutputGrid() {
    var size = $('#output_grid_size').val();
    size = parseSizeTupleForCreation(size);
    if (!size) {
        return;
    }
    var height = size[0];
    var width = size[1];

    // Synchronize the current grid with the edition grid
    syncFromEditionGridToDataGrid();

    // Create a new grid with the new size
    var dataGrid = JSON.parse(JSON.stringify(CURRENT_OUTPUT_GRID.grid));
    var newGrid = createResizedGrid(dataGrid, height, width);

    CURRENT_OUTPUT_GRID = new Grid(height, width, newGrid);

    // Update the output grid display
    var jqGrid = $('#output_grid .edition_grid');
    refreshEditionGrid(jqGrid, CURRENT_OUTPUT_GRID);
}

function resetOutputGrid() {
    syncFromEditionGridToDataGrid();
    CURRENT_OUTPUT_GRID = new Grid(3, 3);
    syncFromDataGridToEditionGrid();
    resizeOutputGrid();
}

function copyFromInput() {
    syncFromEditionGridToDataGrid();
    CURRENT_OUTPUT_GRID = convertSerializedGridToGridObject(CURRENT_INPUT_GRID.grid);
    syncFromDataGridToEditionGrid();
    $('#output_grid_size').val(CURRENT_OUTPUT_GRID.height + 'x' + CURRENT_OUTPUT_GRID.width);
}

function swapPairWithEditor(pairId, isTestPair) {
    // Save current edited grids back to their respective pair
    syncFromEditionGridToDataGrid();

    // Save the current grids
    const savedInputGrid = new Grid(
        CURRENT_INPUT_GRID.height,
        CURRENT_INPUT_GRID.width,
        JSON.parse(JSON.stringify(CURRENT_INPUT_GRID.grid))
    );
    const savedOutputGrid = new Grid(
        CURRENT_OUTPUT_GRID.height,
        CURRENT_OUTPUT_GRID.width,
        JSON.parse(JSON.stringify(CURRENT_OUTPUT_GRID.grid))
    );

    // Add the previously edited pair back to the left column
    if (CURRENT_PAIR_ID !== null) {
        if (CURRENT_IS_TEST_PAIR) {
            TEST_PAIRS[0].input = savedInputGrid;
            TEST_PAIRS[0].output = savedOutputGrid;
            fillPairPreview('test', savedInputGrid, savedOutputGrid, true);
        } else {
            TRAINING_PAIRS[CURRENT_PAIR_ID].input = savedInputGrid;
            TRAINING_PAIRS[CURRENT_PAIR_ID].output = savedOutputGrid;
            fillPairPreview(CURRENT_PAIR_ID, savedInputGrid, savedOutputGrid);
        }
    }

    // Remove the clicked pair from the left column
    $('#pair_preview_' + pairId).remove();

    // Load the selected pair into the editor
    if (isTestPair) {
        CURRENT_INPUT_GRID = TEST_PAIRS[0].input;
        CURRENT_OUTPUT_GRID = TEST_PAIRS[0].output;
        CURRENT_IS_TEST_PAIR = true;
        CURRENT_PAIR_ID = 'test';
    } else {
        CURRENT_INPUT_GRID = TRAINING_PAIRS[pairId].input;
        CURRENT_OUTPUT_GRID = TRAINING_PAIRS[pairId].output;
        CURRENT_IS_TEST_PAIR = false;
        CURRENT_PAIR_ID = pairId;
    }

    syncFromDataGridToEditionGrid();
    fillTestInput(CURRENT_INPUT_GRID);
}

function fillPairPreview(pairId, inputGrid, outputGrid, isTestPair = false) {
    // Remove existing preview to prevent duplicates
    $('#pair_preview_' + pairId).remove();

    // Create HTML for pair
    var pairSlot = $('<div id="pair_preview_' + pairId + '" class="pair_preview" index="' + pairId + '"></div>');
    if (isTestPair) {
        pairSlot.css('border', '2px solid red');
    }

    pairSlot.on('click', function () {
        swapPairWithEditor(pairId, isTestPair);
    });

    // Create and fill input and output previews
    var jqInputGrid = $('<div class="input_preview"></div>').appendTo(pairSlot);
    var jqOutputGrid = $('<div class="output_preview"></div>').appendTo(pairSlot);

    fillJqGridWithData(jqInputGrid, inputGrid);
    fitCellsToContainer(jqInputGrid, inputGrid.height, inputGrid.width, 100, 100);
    fillJqGridWithData(jqOutputGrid, outputGrid);
    fitCellsToContainer(jqOutputGrid, outputGrid.height, outputGrid.width, 100, 100);

    // Append to the correct container
    if (isTestPair) {
    $('#test_pair_container').append(pairSlot);
    } else {
        var index = TRAINING_PAIR_IDS.indexOf(pairId);
        var trainingPairsContainer = $('#training_pairs_container');
        if (index === 0) {
            // If first, insert at the top
            trainingPairsContainer.prepend(pairSlot);
        } else {
            // Insert after the previous pair
            var previousPairId = TRAINING_PAIR_IDS[index - 1];
            $('#pair_preview_' + previousPairId).after(pairSlot);
        }
    }
}

function loadJSONTask(train, test) {
    // Reset the task
    resetTask();

    // Clear the left column containers
    $('#training_pairs_container').empty();
    $('#test_pair_container').empty();
    TRAINING_PAIRS = [];
    TEST_PAIRS = [];
    TRAINING_PAIR_IDS = [];
    CURRENT_PAIR_ID = null;
    CURRENT_IS_TEST_PAIR = false;

    // Load training pairs
    for (var i = 0; i < train.length; i++) {
        var pair = train[i];
        var inputGrid = convertSerializedGridToGridObject(pair['input']);
        var outputGrid = convertSerializedGridToGridObject(pair['output']);
        TRAINING_PAIRS.push({ input: inputGrid, output: outputGrid });
        TRAINING_PAIR_IDS.push(i);
        fillPairPreview(i, inputGrid, outputGrid);
    }

    // Load test pairs
    for (var i = 0; i < test.length; i++) {
        var pair = test[i];
        var inputGrid = convertSerializedGridToGridObject(pair['input']);
        var outputGrid = pair['output'] ? convertSerializedGridToGridObject(pair['output']) : new Grid(3, 3);
        TEST_PAIRS.push({ input: inputGrid, output: outputGrid });
        // Assuming there's only one test pair
        if (i === 0) {
            fillPairPreview('test', inputGrid, outputGrid, true);
        }
    }

    // Start editing the first test pair
    $('#pair_preview_test').remove();
    CURRENT_INPUT_GRID = TEST_PAIRS[0].input;
    CURRENT_OUTPUT_GRID = TEST_PAIRS[0].output;
    CURRENT_PAIR_ID = 'test';
    CURRENT_IS_TEST_PAIR = true;

    syncFromDataGridToEditionGrid();
    fillTestInput(CURRENT_INPUT_GRID);
}

function display_task_name(task_name, task_index, number_of_tasks) {
    big_space = '&nbsp;'.repeat(4); 
    document.getElementById('task_name').innerHTML = (
        'Task name:' + big_space + task_name + big_space + (
            task_index===null ? '' :
            ( String(task_index) + ' out of ' + String(number_of_tasks) )
        )
    );
}

function loadTaskFromFile(e) {
    var file = e.target.files[0];
    if (!file) {
        errorMsg('No file selected');
        return;
    }
    var reader = new FileReader();
    reader.onload = function(e) {
        var contents = e.target.result;

        try {
            var taskData = JSON.parse(contents);
            var train = taskData['train'];
            var test = taskData['test'];
        } catch (e) {
            errorMsg('Bad file format');
            return;
        }

        loadJSONTask(train, test);

        // Set the save file name input to the selected file's name
        $('#save_file_name').val(file.name);

        // Clear the file input
        $('#load_task_file_input').val("");
    };
    reader.readAsText(file);
}

function randomTask() {
    var subset = "training";
    $.getJSON("https://api.github.com/repos/fchollet/ARC/contents/data/" + subset, function(tasks) {
        var task_index = Math.floor(Math.random() * tasks.length)
        var task = tasks[task_index];
        $.getJSON(task["download_url"], function(json) {
            try {
                train = json['train'];
                test = json['test'];
            } catch (e) {
                errorMsg('Bad file format');
                return;
            }
            loadJSONTask(train, test);
            //$('#load_task_file_input')[0].value = "";
            infoMsg("Loaded task training/" + task["name"]);
            display_task_name(task['name'], task_index, tasks.length);
        })
        .error(function(){
          errorMsg('Error loading task');
        });
    })
    .error(function(){
      errorMsg('Error loading task list');
    });
}

function nextTestInput() {
    if (TEST_PAIRS.length <= CURRENT_TEST_PAIR_INDEX + 1) {
        errorMsg('No next test input. Pick another file?')
        return
    }
    CURRENT_TEST_PAIR_INDEX += 1;
    values = TEST_PAIRS[CURRENT_TEST_PAIR_INDEX]['input'];
    CURRENT_INPUT_GRID = convertSerializedGridToGridObject(values)
    fillTestInput(CURRENT_INPUT_GRID);
    $('#current_test_input_id_display').html(CURRENT_TEST_PAIR_INDEX + 1);
    $('#total_test_input_count_display').html(test.length);
}

function submitSolution() {
    syncFromEditionGridToDataGrid();
    reference_output = TEST_PAIRS[CURRENT_TEST_PAIR_INDEX]['output'];
    submitted_output = CURRENT_OUTPUT_GRID.grid;
    if (reference_output.length != submitted_output.length) {
        errorMsg('Wrong solution.');
        return
    }
    for (var i = 0; i < reference_output.length; i++){
        ref_row = reference_output[i];
        for (var j = 0; j < ref_row.length; j++){
            if (ref_row[j] != submitted_output[i][j]) {
                errorMsg('Wrong solution.');
                return
            }
        }

    }
    infoMsg('Correct solution!');
}

function fillTestInput(inputGrid) {
    var jqInputGrid = $('#evaluation_input .edition_grid');
    if (!jqInputGrid.length) {
        jqInputGrid = $('<div class="edition_grid selectable_grid"></div>');
        $('#evaluation_input').append(jqInputGrid);
    }
    fillJqGridWithData(jqInputGrid, inputGrid);
    fitCellsToContainer(jqInputGrid, inputGrid.height, inputGrid.width, 400, 400);
    setUpEditionGridListeners(jqInputGrid);
}

function copyToOutput() {
    syncFromEditionGridToDataGrid();
    CURRENT_OUTPUT_GRID = convertSerializedGridToGridObject(CURRENT_INPUT_GRID.grid);
    syncFromDataGridToEditionGrid();
    $('#output_grid_size').val(CURRENT_OUTPUT_GRID.height + 'x' + CURRENT_OUTPUT_GRID.width);
}

function initializeSelectable() {
    try {
        $('.selectable_grid').selectable('destroy');
    }
    catch (e) {
    }
    toolMode = $('input[name=tool_switching]:checked').val();
    if (toolMode == 'select') {
        infoMsg('Select some cells and click on a color to fill in, or press C to copy');
        $('.selectable_grid').selectable(
            {
                autoRefresh: false,
                filter: '> .row > .cell',
                start: function(event, ui) {
                    $('.ui-selected').each(function(i, e) {
                        $(e).removeClass('ui-selected');
                    });
                }
            }
        );
    }
}

function saveTask() {
    // Synchronize the current grids with the edition grids
    syncFromEditionGridToDataGrid();

    // Save current edited grids back to their respective pair
    if (CURRENT_IS_TEST_PAIR) {
        TEST_PAIRS[0].input = new Grid(
            CURRENT_INPUT_GRID.height,
            CURRENT_INPUT_GRID.width,
            JSON.parse(JSON.stringify(CURRENT_INPUT_GRID.grid))
        );
        TEST_PAIRS[0].output = new Grid(
            CURRENT_OUTPUT_GRID.height,
            CURRENT_OUTPUT_GRID.width,
            JSON.parse(JSON.stringify(CURRENT_OUTPUT_GRID.grid))
        );
    } else if (CURRENT_PAIR_ID !== null) {
        TRAINING_PAIRS[CURRENT_PAIR_ID].input = new Grid(
            CURRENT_INPUT_GRID.height,
            CURRENT_INPUT_GRID.width,
            JSON.parse(JSON.stringify(CURRENT_INPUT_GRID.grid))
        );
        TRAINING_PAIRS[CURRENT_PAIR_ID].output = new Grid(
            CURRENT_OUTPUT_GRID.height,
            CURRENT_OUTPUT_GRID.width,
            JSON.parse(JSON.stringify(CURRENT_OUTPUT_GRID.grid))
        );
    } else {
        // This should not happen, but handle it just in case
        console.error('No current pair selected for saving.');
    }

    // Prepare data in the required format
    const taskData = {
        train: TRAINING_PAIRS.map(pair => ({
            input: pair.input.grid,
            output: pair.output.grid,
        })),
        test: TEST_PAIRS.map(pair => ({
            input: pair.input.grid,
            output: pair.output.grid,
        })),
    };

    const dataStr = JSON.stringify(taskData, null, 2); // Pretty-print the JSON
    const fileName = $('#save_file_name').val() || 'task.json';

    // Create a blob and save the file
    const blob = new Blob([dataStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);

    const a = document.createElement('a');
    a.href = url;
    a.download = fileName;
    a.click();
    URL.revokeObjectURL(url);
}

function initializeEmptyTask() {
    // Create three empty training pairs
    for (let i = 0; i < 3; i++) {
        const emptyInputGrid = new Grid(3, 3);
        const emptyOutputGrid = new Grid(3, 3);
        TRAINING_PAIRS.push({ input: emptyInputGrid, output: emptyOutputGrid });
        TRAINING_PAIR_IDS.push(i); // Store the pair ID
        fillPairPreview(i, emptyInputGrid, emptyOutputGrid); // Add to left column
    }

    // Create one empty test pair
    const emptyTestInputGrid = new Grid(3, 3);
    const emptyTestOutputGrid = new Grid(3, 3);
    TEST_PAIRS.push({ input: emptyTestInputGrid, output: emptyTestOutputGrid });
    fillPairPreview('test', emptyTestInputGrid, emptyTestOutputGrid, true);

    // We begin editing the test pair, so remove it from the left column
    $('#pair_preview_test').remove();

    // Set the current grids to the test pair
    CURRENT_INPUT_GRID = TEST_PAIRS[0].input;
    CURRENT_OUTPUT_GRID = TEST_PAIRS[0].output;
    CURRENT_PAIR_ID = 'test';
    CURRENT_IS_TEST_PAIR = true;

    syncFromDataGridToEditionGrid();
    fillTestInput(CURRENT_INPUT_GRID);
}

// Initial event binding.

$(document).ready(function () {
    // Initialize empty training and test data
    initializeEmptyTask();

    $('#symbol_picker').find('.symbol_preview').click(function(event) {
        symbol_preview = $(event.target);
        $('#symbol_picker').find('.symbol_preview').each(function(i, preview) {
            $(preview).removeClass('selected-symbol-preview');
        })
        symbol_preview.addClass('selected-symbol-preview');

        toolMode = $('input[name=tool_switching]:checked').val();
        if (toolMode == 'select') {
            $('.edition_grid').find('.ui-selected').each(function(i, cell) {
                symbol = getSelectedSymbol();
                setCellSymbol($(cell), symbol);
            });
        }
    });

    $('.edition_grid').each(function(i, jqGrid) {
        setUpEditionGridListeners($(jqGrid));
    });

    $('.load_task').on('change', function(event) {
        loadTaskFromFile(event);
    });

    $('.load_task').on('click', function(event) {
      event.target.value = "";
    });

    $('input[type=radio][name=tool_switching]').change(function() {
        initializeSelectable();
    });
    
    $('input[type=text][name=size]').on('keydown', function(event) {
        if (event.keyCode == 13) {
            resizeOutputGrid();
        }
    });

    $('#load_task_file_input').on('change', function(event) {
        loadTaskFromFile(event);
    });

    // Clear the file input when the button is clicked
    $('#load_task_file_input').on('click', function(event) {
        event.target.value = "";
    });

    $('body').keydown(function(event) {
        // Copy and paste functionality.
        if (event.which == 67) {
            // Press C

            selected = $('.ui-selected');
            if (selected.length == 0) {
                return;
            }

            COPY_PASTE_DATA = [];
            for (var i = 0; i < selected.length; i ++) {
                x = parseInt($(selected[i]).attr('x'));
                y = parseInt($(selected[i]).attr('y'));
                symbol = parseInt($(selected[i]).attr('symbol'));
                COPY_PASTE_DATA.push([x, y, symbol]);
            }
            infoMsg('Cells copied! Select a target cell and press V to paste at location.');

        }
        if (event.which == 86) {
            // Press P
            if (COPY_PASTE_DATA.length == 0) {
                errorMsg('No data to paste.');
                return;
            }
            selected = $('.edition_grid').find('.ui-selected');
            if (selected.length == 0) {
                errorMsg('Select a target cell on the output grid.');
                return;
            }

            jqGrid = $(selected.parent().parent()[0]);

            if (selected.length == 1) {
                targetx = parseInt(selected.attr('x'));
                targety = parseInt(selected.attr('y'));

                xs = new Array();
                ys = new Array();
                symbols = new Array();

                for (var i = 0; i < COPY_PASTE_DATA.length; i ++) {
                    xs.push(COPY_PASTE_DATA[i][0]);
                    ys.push(COPY_PASTE_DATA[i][1]);
                    symbols.push(COPY_PASTE_DATA[i][2]);
                }

                minx = Math.min(...xs);
                miny = Math.min(...ys);
                for (var i = 0; i < xs.length; i ++) {
                    x = xs[i];
                    y = ys[i];
                    symbol = symbols[i];
                    newx = x - minx + targetx;
                    newy = y - miny + targety;
                    res = jqGrid.find('[x="' + newx + '"][y="' + newy + '"] ');
                    if (res.length == 1) {
                        cell = $(res[0]);
                        setCellSymbol(cell, symbol);
                    }
                }
            } else {
                errorMsg('Can only paste at a specific location; only select *one* cell as paste destination.');
            }
        }
    });
});




function parseSizeTupleForCreation(sizeStr) {
    var size = sizeStr.split('x');
    if (size.length != 2) {
        alert('Grid size should have the format "3x3", "5x7", etc.');
        return null;
    }
    var height = parseInt(size[0]);
    var width = parseInt(size[1]);
    if (isNaN(height) || isNaN(width) || height < 1 || width < 1) {
        alert('Grid size should be positive integers.');
        return null;
    }
    if (height > 30 || width > 30) {
        alert('Grid size should be at most 30 per side. Pick a smaller size.');
        return null;
    }
    return [height, width];
}






