import config
from pathlib import Path
import io
import base64
from datetime import datetime

def create_report(fig_pnl, fig_return, fig_alloc, summary_sheet, df_alloc, output_dir=config.OUTPUT_DIR):
    """Create an interactive HTML report with DataTables"""
    
    current_date = datetime.now().strftime('%Y-%m-%d')
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Convert Plotly figures
    plotly_config = {'responsive': True, 'displayModeBar': True}   
    
    pnl_html = fig_pnl.to_html(
        full_html=False, 
        include_plotlyjs='cdn',
        default_width='100%',  # Ensures 100% width on load
        default_height='500px', # Set a consistent height
        config=plotly_config    # Enables Javascript resizing
    )
    
    alloc_html = fig_alloc.to_html(
        full_html=False, 
        include_plotlyjs=False,
        default_width='100%',
        default_height='500px',
        config=plotly_config
    )
    
    # Convert matplotlib figure to base64
    buf = io.BytesIO()
    fig_return.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    return_plot_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    
    # Convert summary sheet
    if hasattr(summary_sheet, 'data'):
        summary_content = summary_sheet.data
    else:
        summary_content = str(summary_sheet)
    
    # Create interactive table HTML with DataTables
    # First, create the table HTML with an ID
    table_html = df_alloc.to_html(
        index=False, 
        classes='display compact stripe hover order-column row-border', 
        border=0,
        table_id='alloc_table'
    )
    
    # HTML template with DataTables
    html_template = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Portfolio Analysis Report</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        
        <!-- DataTables CSS -->
        <link rel="stylesheet" type="text/css" href="https://cdn.datatables.net/1.13.4/css/jquery.dataTables.min.css">
        <link rel="stylesheet" type="text/css" href="https://cdn.datatables.net/buttons/2.3.6/css/buttons.dataTables.min.css">
        <link rel="stylesheet" type="text/css" href="https://cdn.datatables.net/responsive/2.4.1/css/responsive.dataTables.min.css">
        
        <style>
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                margin: 30px;
                background-color: #f8f9fa;
            }}
            .container {{
                max-width: 1600px;
                margin: 0 auto;
                background-color: white;
                padding: 30px;
                border-radius: 10px;
                box-shadow: 0 0 20px rgba(0,0,0,0.1);
            }}
            .section {{
                margin-bottom: 40px;
                padding: 25px;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                background-color: white;
            }}
            h1 {{
                color: #2c3e50;
                border-bottom: 3px solid #3498db;
                padding-bottom: 15px;
                margin-bottom: 30px;
            }}
            h2 {{
                color: #34495e;
                border-bottom: 2px solid #ecf0f1;
                padding-bottom: 10px;
                margin-bottom: 20px;
            }}
            .plot-container {{
                margin: 25px 0;
                padding: 15px;
                background-color: #f8f9fa;
                border-radius: 5px;
                width: 100%;
                box-sizing: border-box;
            }}
            .summary {{
                background-color: #f1f8ff;
                padding: 20px;
                border-radius: 8px;
                border-left: 5px solid #3498db;
            }}
            .dataTables_wrapper {{
                margin-top: 20px;
            }}
            .export-buttons {{
                margin: 10px 0;
            }}
            .tabs {{
                margin-bottom: 20px;
            }}
            .tab-button {{
                padding: 10px 20px;
                background-color: #ecf0f1;
                border: none;
                border-radius: 5px 5px 0 0;
                margin-right: 5px;
                cursor: pointer;
            }}
            .tab-button.active {{
                background-color: #3498db;
                color: white;
            }}
            .tab-content {{
                display: none;
                padding: 20px;
                border: 1px solid #ddd;
                border-radius: 0 5px 5px 5px;
            }}
            .tab-content.active {{
                display: block;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📊 Portfolio Analysis Report</h1>
            <p><strong>Generated:</strong> {current_time}</p>
            
            <!-- Tab Navigation -->
            <div class="tabs">
                <button class="tab-button active" onclick="openTab('tab1')">📝 Summary</button>
                <button class="tab-button" onclick="openTab('tab2')">📈 Charts</button>
                <button class="tab-button" onclick="openTab('tab3')">📋 Data</button>
                
            </div>

            <!-- Tab 1: Summary -->
            <div id="tab1" class="tab-content active">
                <div class="section summary">
                    <h2>📝 Summary Sheet</h2>
                    <div id="summary-content">
                        {summary_content}
                    </div>
                </div>
            </div>

            <!-- Tab 2: Charts -->
            <div id="tab2" class="tab-content">
                <div class="section">
                    <h2>📈 Total P&L Over Time</h2>
                    <div class="plot-container">
                        {pnl_html}
                    </div>
                    <p><i>Hover over the chart to see detailed values. Use the toolbar to zoom, pan, or download.</i></p>
                </div>
                
                <div class="section">
                    <h2>📊 Returns Analysis</h2>
                    <div class="plot-container">
                        <img src="data:image/png;base64,{return_plot_base64}" 
                             alt="Returns Plot" style="width:100%; max-width:1600px; border-radius:5px;">
                    </div>
                    <p><i>Static image of returns analysis. For interactive version, run the notebook.</i></p>
                </div>
                
                <div class="section">
                    <h2>🥧 Portfolio Allocation</h2>
                    <div class="plot-container">
                        {alloc_html}
                    </div>
                    <p><i>Click on legend items to show/hide categories. Hover for exact percentages.</i></p>
                </div>
            </div>
            
            <!-- Tab 3: Interactive Data -->
            <div id="tab3" class="tab-content">
                <div class="section">
                    <h2>📊 Interactive Allocation Data</h2>
                    <p>Use the search box to filter, click on column headers to sort, or use the buttons to export data.</p>
                    <div class="export-buttons"></div>
                    {table_html}
                    
                    <div style="margin-top: 20px; padding: 15px; background-color: #f8f9fa; border-radius: 5px;">
                        <h4>💡 Tips for using this table:</h4>
                        <ul>
                            <li><strong>Search:</strong> Type in the search box to filter all columns</li>
                            <li><strong>Sort:</strong> Click any column header to sort (click again for reverse order)</li>
                            <li><strong>Show entries:</strong> Use the dropdown to change number of rows shown</li>
                            <li><strong>Export:</strong> Use buttons above to export as CSV, Excel, or PDF</li>
                            <li><strong>Column visibility:</strong> Use column visibility button to hide/show columns</li>
                        </ul>
                    </div>
                </div>
                
                <!--
                <div class="section">
                    <h3>📊 Quick Statistics</h3>
                    <div id="stats-container" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px;">
                    </div>
                </div>
                
                -->
            </div>
            
            
        </div>
        
        <!-- jQuery (required for DataTables) -->
        <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
        
        <!-- DataTables JavaScript -->
        <script type="text/javascript" charset="utf8" src="https://cdn.datatables.net/1.13.4/js/jquery.dataTables.min.js"></script>
        <script type="text/javascript" charset="utf8" src="https://cdn.datatables.net/buttons/2.3.6/js/dataTables.buttons.min.js"></script>
        <script type="text/javascript" charset="utf8" src="https://cdn.datatables.net/buttons/2.3.6/js/buttons.html5.min.js"></script>
        <script type="text/javascript" charset="utf8" src="https://cdn.datatables.net/buttons/2.3.6/js/buttons.print.min.js"></script>
        <script type="text/javascript" charset="utf8" src="https://cdn.datatables.net/buttons/2.3.6/js/buttons.colVis.min.js"></script>
        <script type="text/javascript" charset="utf8" src="https://cdn.datatables.net/responsive/2.4.1/js/dataTables.responsive.min.js"></script>
        
        <!-- PDF export support -->
        <script type="text/javascript" src="https://cdnjs.cloudflare.com/ajax/libs/pdfmake/0.1.36/pdfmake.min.js"></script>
        <script type="text/javascript" src="https://cdnjs.cloudflare.com/ajax/libs/pdfmake/0.1.36/vfs_fonts.js"></script>
        
        <script>
            // Tab switching function
            function openTab(tabName) {{
                // Hide all tab contents
                document.querySelectorAll('.tab-content').forEach(tab => {{
                    tab.classList.remove('active');
                }});
                
                // Remove active class from all buttons
                document.querySelectorAll('.tab-button').forEach(button => {{
                    button.classList.remove('active');
                }});
                
                // Show the selected tab
                document.getElementById(tabName).classList.add('active');
                
                // Add active class to clicked button
                event.currentTarget.classList.add('active');

                // When we switch to the charts tab, we must manually trigger a resize event
                // This forces Plotly to look at the container width (now visible) and scale to fit 100%
                if (tabName === 'tab2') {{
                    setTimeout(function() {{
                        window.dispatchEvent(new Event('resize'));
                    }}, 50); // Small delay ensures DOM is rendered before resize
                }}
                
                // Redraw DataTables when tab becomes active (fixes rendering issues)
                if (tabName === 'tab2' && $.fn.DataTable.isDataTable('#alloc_table')) {{
                    $('#alloc_table').DataTable().columns.adjust().responsive.recalc();
                }}
            }}
            
            // Initialize DataTables when page loads
            $(document).ready(function() {{
                // Initialize DataTable with extensive features
                var table = $('#alloc_table').DataTable({{
                    dom: 'Bfrtip',
                    buttons: [
                        'copy', 'csv', 'excel', 'pdf', 'print', 'colvis'
                    ],
                    pageLength: 25,
                    lengthMenu: [[10, 25, 50, 100, -1], [10, 25, 50, 100, "All"]],
                    responsive: true,
                    order: [], // No initial sorting
                    columnDefs: [
                        {{
                            targets: '_all',
                            className: 'dt-left'
                        }}
                    ],
                    initComplete: function() {{
                        // Add custom CSS to buttons container
                        $('.dt-buttons').addClass('export-buttons');
                        
                        // Calculate and display statistics
                        calculateStatistics();
                    }}
                }});
                
                // Calculate statistics from table data
                function calculateStatistics() {{
                    // Get numeric columns (assuming they're numeric if they contain numbers)
                    var numericColumns = [];
                    var api = table.api();
                    
                    // Loop through columns to find numeric ones
                    api.columns().every(function() {{
                        var column = this;
                        var columnData = column.data().toArray();
                        var isNumeric = columnData.some(function(cell) {{
                            return !isNaN(parseFloat(cell)) && isFinite(cell);
                        }});
                        
                        if (isNumeric && columnData.length > 0) {{
                            numericColumns.push({{
                                index: column.index(),
                                header: $(column.header()).text(),
                                data: columnData.map(Number).filter(n => !isNaN(n))
                            }});
                        }}
                    }});
                    
                    // Display statistics
                    var statsHtml = '';
                    numericColumns.forEach(function(col) {{
                        if (col.data.length > 0) {{
                            var sum = col.data.reduce((a, b) => a + b, 0);
                            var avg = sum / col.data.length;
                            var max = Math.max(...col.data);
                            var min = Math.min(...col.data);
                            
                            statsHtml += `
                            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 15px; border-radius: 8px; width=100%">
                                <h4 style="margin-top: 0; color: white;">${{col.header}}</h4>
                                <p style="margin: 5px 0;"><strong>Avg:</strong> ${{avg.toFixed(2)}}</p>
                                <p style="margin: 5px 0;"><strong>Min:</strong> ${{min.toFixed(2)}}</p>
                                <p style="margin: 5px 0;"><strong>Max:</strong> ${{max.toFixed(2)}}</p>
                                <p style="margin: 5px 0;"><strong>Count:</strong> ${{col.data.length}}</p>
                            </div>
                            `;
                        }}
                    }});
                    
                    if (statsHtml) {{
                        $('#stats-container').html(statsHtml);
                    }}
                }}
                
                // Add search debouncing for better performance
                var searchTimeout;
                $('#alloc_table_filter input').on('keyup', function() {{
                    clearTimeout(searchTimeout);
                    var searchBox = this;
                    searchTimeout = setTimeout(function() {{
                        table.search(searchBox.value).draw();
                    }}, 300);
                }});
                
                // Add tooltips to table headers
                $('#alloc_table thead th').attr('title', 'Click to sort');
            }});
        </script>
    </body>
    </html>
    '''
    
    # Save the report
    output_path = Path(output_dir) / f"portfolio_report_{current_date}.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_template)
    
    return output_path

# Use the function

