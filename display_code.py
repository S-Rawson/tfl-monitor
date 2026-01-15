#!/alexander/Documents/Coding_Projects/tfl-monitor/.venv/bin/env python

import pandas as pd
import asyncio
import json
import os
from datetime import datetime
from project_data_gathering import constant_data_pull
from queries_to_bikepoint_api_async import get_all_boris_bike_info, get_specific_boris_bike_info
from queries_to_line_api_async import _get_list_modes, _get_tube_lines, _all_valid_routes_all_lines, _all_valid_routes_single_line, _get_tube_status_update, _get_stops_on_a_line, _next_train_or_bus
import httpx
from textual.app import App, ComposeResult
from textual.widgets import DataTable, Button, Static, Label
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.theme import Theme
from dotenv import load_dotenv
from pathlib import Path

client = httpx.AsyncClient(
    headers={"Accept": "application/json"},
    base_url="https://api.tfl.gov.uk/",
)

# Textual app to display the three items from data_dict
class TfLDisplayApp(App):
    """Display three widgets with header and auto-refresh:
    - header: current time and exit button
    - left: DataTable for `next_tube_and_bus_df`
    - top-right: DataTable from `tube_line_status`
    - bottom-right: DataTable for `boris_bike_df`
    
    Data refreshes every 5 seconds.
    """

    CSS_PATH = "horizontal_layout.tcss"
    BINDINGS = [("q", "quit", "Quit")]
    THEME = "dracula"
    
    # Reactive attribute to trigger data refresh
    current_time = reactive(str)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.data_dict = {}
        self.client = client
        self.dict_of_useful_tube_and_bus_stops = {}
        self.dict_of_useful_bikepoints = {}

    def _get_colored_status(self, col_name:str, status: str, row: pd.Series) -> str:
        """Return status with color markup based on content."""
        if "good service" in row['Status'].lower():
            return f"[green]{status}[/green]"
        elif "minor delays" in row['Status'].lower():
            return f"[yellow]{status}[/yellow]"
        else:
            return f"[red]{status}[/red]"

    def _df_to_datatable(self, df) -> DataTable:
        """Convert a pandas DataFrame to a Textual DataTable widget.

        If `df` is not a DataFrame, returns a Static widget with stringified content.
        """
        try:
    

            async def _update_table_by_id(self, table_id: str, df: pd.DataFrame) -> None:
                """Update a specific table by ID."""
                try:
                    table = self.query_one(table_id, DataTable)
                    await self._refresh_datatable(table, df)
                except Exception as e:
                    print(f"Error updating table {table_id}: {e}")  # Debug logging            if not hasattr(df, "columns"):
                raise TypeError
            table = DataTable(zebra_stripes=True)
            # add columns
            for col in df.columns:
                 if col != "Status":
                     table.add_column(str(col))
            # add row
            for _, row in df.iterrows():
                row_data = []
                for col_name, value in zip(df.columns, row.tolist()):
                    if "Status" in df.columns and col_name == "Line":
                        row_data.append(self._get_colored_status(str(col_name), str(value), row))
                    elif col_name == "Status":
                        pass
                    else:
                        row_data.append(str(value))
                table.add_row(*row_data)
            return table
        except Exception as e:
            return Static(f"Error: {str(e)}\n\n{str(df)[:500]}")

    async def _refresh_data(self) -> None:
        """Refresh data every 5 seconds and update display. 
        All three data sources refresh independently and concurrently."""
        while True:
            try:
                # Fetch all three data sources concurrently
                await asyncio.gather(
                    self._fetch_and_update_tube_status(),
                    self._fetch_and_update_bus_data(),
                    self._fetch_and_update_bike_data()
                )
                # Update time after all data fetches
                self.current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
            except Exception as e:
                self.notify(f"Error refreshing data: {e}", severity="error")
            
            finally:
                # Wait 5 seconds before next refresh - always runs
                await asyncio.sleep(10)

    async def _fetch_and_update_tube_status(self) -> None:
        """Fetch tube line status independently."""
        try:
            self.data_dict["tube_line_status"] = await _get_tube_status_update(self.client)
            if not self.data_dict['tube_line_status'].empty:
                await self._update_table_by_id("#status_table", self.data_dict.get("tube_line_status", pd.DataFrame()))
                #print(self.data_dict["tube_line_status"])
        except Exception as e:
            pass  # Individual fetch failed, will retry on next cycle

    async def _fetch_and_update_bus_data(self) -> None:
        """Fetch next tube/bus data independently."""
        try:
            self.data_dict['next_tube_and_bus_df'] = await _next_train_or_bus(self.client, self.dict_of_useful_tube_and_bus_stops)
            print(self.data_dict['next_tube_and_bus_df'])
            if not self.data_dict['next_tube_and_bus_df'].empty:
                await self._update_table_by_id("#next_tube_and_bus_df", self.data_dict.get("next_tube_and_bus_df", pd.DataFrame()))
        except Exception as e:
            pass  # Individual fetch failed, will retry on next cycle

    async def _fetch_and_update_bike_data(self) -> None:
        """Fetch bike point data independently."""
        try:
            self.data_dict['boris_bike_df'] = await get_specific_boris_bike_info(self.client, self.dict_of_useful_bikepoints)
            if not self.data_dict['boris_bike_df'].empty:
                await self._update_table_by_id("#boris_bike_df", self.data_dict.get("boris_bike_df", pd.DataFrame()))
        except Exception as e:
            pass  # Individual fetch failed, will retry on next cycle

    async def _update_table_by_id(self, table_id: str, df: pd.DataFrame) -> None:
        """Update a specific table by ID."""
        try:
            table = self.query_one(table_id, DataTable)
            await self._refresh_datatable(table, df)
        except Exception as e:
            print(f"Error updating table {table_id}: {e}") 

    async def _refresh_datatable(self, table: DataTable, df: pd.DataFrame) -> DataTable:
        """Clear and repopulate a DataTable with new data."""
        try:
            # Clear existing rows only
            table.clear(columns=False)
            
            # Only add columns on first load (if table is empty)
            if len(table.columns) == 0:
                for col in df.columns:
                    if col != "Status":
                        table.add_column(str(col))
        
            # Add rows with coloring
            
            for _, row in df.iterrows():
                row_data = []
                for col_name, value in zip(df.columns, row.tolist()):
                    if "Status" in df.columns and col_name == "Line":
                        row_data.append(self._get_colored_status(str(col_name), str(value), row))
                    elif col_name == "Status":
                        pass  # Skip Status column
                    else:
                        row_data.append(str(value))
                table.add_row(*row_data)
            return table
        except Exception:
            pass  # Skip if data invalid

    def compose(self) -> ComposeResult:
        """Compose the layout with header, main content, and exit button."""
        # Create tables with IDs
        top_left_table = self._df_to_datatable(self.data_dict.get("next_tube_and_bus_df", pd.DataFrame()))
        top_left_table.id = "next_tube_and_bus_df"
        
        status_table = self._df_to_datatable(self.data_dict.get("tube_line_status", pd.DataFrame()))
        status_table.id = "status_table"
        
        bottom_table = self._df_to_datatable(self.data_dict.get("boris_bike_df", pd.DataFrame()))
        bottom_table.id = "boris_bike_df"
        
        # Header with time and exit button
        yield Vertical(
            Horizontal(
                Label("TfL Monitor      ", id="header_title"),
                Static(self.current_time, id="header_time"),
                Button("Exit", id="exit_btn", variant="error"),
                id="header"
            ),
            # Main content: left table + right container
            Horizontal(
                Vertical(
                    top_left_table,
                    bottom_table,
                    id="left_container"
                ),
                status_table,
                id="main_container"
            ),
            id="main_layout"
        )

    def on_mount(self) -> None:
        """Initialize the app and start data refresh task."""
        # Set initial time
        self.current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Start background data refresh task
        self.app.call_later(self._start_refresh)

    def _start_refresh(self) -> None:
        """Start the async data refresh task."""
        asyncio.create_task(self._refresh_data())

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "exit_btn":
            self.exit()

    def watch_current_time(self, new_time: str) -> None:
        """Update time display when current_time changes."""
        try:
            header_time = self.query_one("#header_time", Static)
            header_time.update(new_time)
        except Exception:
            pass  # Widget may not be mounted yet


if __name__ == "__main__":
    env_path = Path(__file__).parent / "config.env"
    load_dotenv(env_path)
    
    dict_of_useful_tube_and_bus_stops = json.loads(os.getenv("dict_of_useful_tube_and_bus_stops"))
    dict_of_useful_bikepoints = json.loads((os.getenv("dict_of_useful_bikepoints")))
    
    # Gather initial data and run the textual app
    initial_data = asyncio.run(constant_data_pull(dict_of_useful_tube_and_bus_stops, dict_of_useful_bikepoints))

    app = TfLDisplayApp()
    app.data_dict = initial_data
    app.client = client
    app.dict_of_useful_tube_and_bus_stops = dict_of_useful_tube_and_bus_stops
    app.dict_of_useful_bikepoints = dict_of_useful_bikepoints

    # run the TUI
    app.run()
