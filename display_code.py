#!/alexander/Documents/Coding_Projects/tfl-monitor/.venv/bin/env python

import pandas as pd
import asyncio
import yaml
from datetime import datetime
from project_data_gathering import constant_data_pull
from queries_to_bikepoint_api_async import (
    get_specific_boris_bike_info,
)
from queries_to_line_api_async import (
    _get_tube_status_update,
    _next_train_or_bus,
)
from queries_overground import get_live_overground_trains
import httpx
from textual.app import App, ComposeResult
from textual.widgets import DataTable, Button, Static, Label
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

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
    # Default refresh interval (seconds) - can be overridden from config.yml
    refresh_interval_seconds: int = 10

    # Reactive attribute to trigger data refresh
    current_time = reactive(str)
    # Reactive countdown (seconds) until next refresh
    refresh_countdown = reactive(int)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.data_dict = {}
        self.client = client
        self.tube_and_bus_stops = {}
        self.bikepoints = {}
        self.overground_stations = {}
        self.overground_api_url: str = ""
        self.overground_routes: list = []
        self.overground_auth: tuple | None = None
        self.overground_stations = {}

    def _get_colored_status(self, col_name: str, status: str, row: pd.Series) -> str:
        """
        Return status with color markup based on content.
        """
        match row["Status"].lower():
            case "good service" | "no issues":
                return f"[green]{status}[/green]"
            case (
                "minor delays"
                | "part closure"
                | "change of frequency"
                | "diverted"
                | "issues reported"
                | "reduced service"
            ):
                return f"[yellow]{status}[/yellow]"
            case (
                "closed"
                | "suspended"
                | "planned closure"
                | "not running"
                | "service closed"
                | "bus service"
                | "severe delays"
                | "part suspended"
            ):
                return f"[red]{status}[/red]"
            case _:
                return f"[grey]{status}[/grey]"

    def _df_to_datatable(self, df) -> DataTable | Static:
        """Convert a pandas DataFrame to a Textual DataTable widget.

        If `df` is not a DataFrame, returns a Static widget with stringified content.
        """
        try:

            async def _update_table_by_id(
                self, table_id: str, df: pd.DataFrame
            ) -> None:
                """Update a specific table by ID."""
                try:
                    table = self.query_one(table_id, DataTable)
                    await self._refresh_datatable(table, df)
                except Exception as e:
                    logger.exception("Error updating table %s: %s", table_id, e)
                # Debug logging            if not hasattr(df, "columns"):
                raise TypeError

            table = DataTable(zebra_stripes=True)
            # add columns
            for col in df.columns:
                table.add_column(str(col))
            # add row
            for _, row in df.iterrows():
                row_data = []
                for col_name, value in zip(df.columns, row.tolist()):
                    if "Status" in df.columns and col_name == "Line":
                        row_data.append(
                            self._get_colored_status(str(col_name), str(value), row)
                        )
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
                    self._fetch_and_update_bike_data(),
                    self._fetch_and_update_overground_data(),
                )
                # Update time after all data fetches
                self.current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            except Exception as e:
                self.notify(f"Error refreshing data: {e}", severity="error")

            finally:
                # Wait configured interval before next refresh - update countdown every second
                interval = int(getattr(self, "refresh_interval_seconds", 10))
                # ensure countdown starts at full interval
                for remaining in range(interval, 0, -1):
                    try:
                        self.refresh_countdown = remaining
                    except Exception:
                        pass
                    await asyncio.sleep(1)

    async def _fetch_and_update_tube_status(self) -> None:
        """Fetch tube line status independently."""
        try:
            self.data_dict["tube_line_status"] = await _get_tube_status_update(
                self.client
            )
            if not self.data_dict["tube_line_status"].empty:
                await self._update_table_by_id(
                    "#status_table",
                    self.data_dict.get("tube_line_status", pd.DataFrame()),
                )
                # print(self.data_dict["tube_line_status"])
        except Exception:
            pass  # Individual fetch failed, will retry on next cycle

    async def _fetch_and_update_bus_data(self) -> None:
        """Fetch next tube/bus data independently."""
        try:
            self.data_dict["next_tube_and_bus_df"] = await _next_train_or_bus(
                self.client, self.tube_and_bus_stops
            )
            if not self.data_dict["next_tube_and_bus_df"].empty:
                await self._update_table_by_id(
                    "#next_tube_and_bus_df",
                    self.data_dict.get("next_tube_and_bus_df", pd.DataFrame()),
                )
        except Exception:
            pass  # Individual fetch failed, will retry on next cycle

    async def _fetch_and_update_bike_data(self) -> None:
        """Fetch bike point data independently."""
        try:
            self.data_dict["boris_bike_df"] = await get_specific_boris_bike_info(
                self.client, self.bikepoints
            )
            if not self.data_dict["boris_bike_df"].empty:
                await self._update_table_by_id(
                    "#boris_bike_df",
                    self.data_dict.get("boris_bike_df", pd.DataFrame()),
                )
        except Exception:
            pass  # Individual fetch failed, will retry on next cycle

    async def _fetch_and_update_overground_data(self) -> None:
        """Fetch overground live departures independently."""
        try:
            self.data_dict["overground_df"] = await get_live_overground_trains(
                self.client,
                self.overground_routes,
                self.overground_api_url,
                self.overground_auth,
            )
            if not self.data_dict["overground_df"].empty:
                await self._update_table_by_id(
                    "#overground_df",
                    self.data_dict.get("overground_df", pd.DataFrame()),
                )
        except Exception:
            pass

    async def _update_table_by_id(self, table_id: str, df: pd.DataFrame) -> None:
        """Update a specific table by ID."""
        try:
            table = self.query_one(table_id, DataTable)
            await self._refresh_datatable(table, df)
        except Exception as e:
            logger.exception("Error updating table %s: %s", table_id, e)

    async def _refresh_datatable(
        self, table: DataTable, df: pd.DataFrame
    ) -> DataTable | None:
        """Clear and repopulate a DataTable with new data."""
        try:
            # Clear existing rows only
            table.clear(columns=False)

            # Only add columns on first load (if table is empty)
            if len(table.columns) == 0:
                for col in df.columns:
                    table.add_column(str(col))

            # Add rows with coloring

            for _, row in df.iterrows():
                row_data = []
                for col_name, value in zip(df.columns, row.tolist()):
                    if "Status" in df.columns and col_name == "Line":
                        row_data.append(
                            self._get_colored_status(str(col_name), str(value), row)
                        )
                    else:
                        row_data.append(str(value))
                table.add_row(*row_data)
            return table
        except Exception:
            # Skip if data invalid and return None to indicate no update
            return None

    def compose(self) -> ComposeResult:
        """Compose the layout with header, main content, and exit button."""
        # Create tables with IDs
        top_left_table = self._df_to_datatable(
            self.data_dict.get("next_tube_and_bus_df", pd.DataFrame())
        )
        top_left_table.id = "next_tube_and_bus_df"

        status_table = self._df_to_datatable(
            self.data_dict.get("tube_line_status", pd.DataFrame())
        )
        status_table.id = "status_table"

        bottom_table = self._df_to_datatable(
            self.data_dict.get("boris_bike_df", pd.DataFrame())
        )
        bottom_table.id = "boris_bike_df"
        overground_table = self._df_to_datatable(
            self.data_dict.get("overground_df", pd.DataFrame())
        )
        overground_table.id = "overground_df"

        # Header with time and exit button
        yield Vertical(
            Horizontal(
                Label("TfL Monitor      ", id="header_title"),
                Static(str(self.current_time), id="header_time"),
                Button("Exit", id="exit_btn", variant="error"),
                id="header",
            ),
            # Main content: left table + right container
            Horizontal(
                Vertical(
                    top_left_table, bottom_table, overground_table, id="left_container"
                ),
                # Put the status table in a Vertical so we can display a countdown above it
                Vertical(
                    Static(str(self.refresh_countdown), id="refresh_countdown"),
                    status_table,
                    id="right_container",
                ),
                id="main_container",
            ),
            id="main_layout",
        )

    def on_mount(self) -> None:
        """Initialize the app and start data refresh task."""
        # Set initial time
        self.current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Initialize countdown from configured interval
        try:
            self.refresh_countdown = int(getattr(self, "refresh_interval_seconds", 10))
        except Exception:
            self.refresh_countdown = 10

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

    def watch_refresh_countdown(self, new_value: int) -> None:
        """Update the countdown widget when refresh_countdown changes."""
        try:
            countdown_widget = self.query_one("#refresh_countdown", Static)
            countdown_widget.update(f"Next refresh in {new_value}s")
        except Exception:
            pass


if __name__ == "__main__":
    # Load configuration from YAML for better readability (config.yml)
    config_path = Path(__file__).parent / "config.yml"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    else:
        cfg = {}

    # Expect mappings directly in YAML
    tube_and_bus_stops = cfg.get("tube_and_bus_stops", {})
    bikepoints = cfg.get("bikepoints", {})
    overground_stations = cfg.get("overground_stations", {})
    overground_api_url = cfg.get("overground_api_url", "")
    overground_routes = cfg.get("overground_routes", [])
    overground_api_username = cfg.get("overground_api_username", "")
    overground_api_password = cfg.get("overground_api_password", "")
    overground_auth = (
        (overground_api_username, overground_api_password)
        if overground_api_username and overground_api_password
        else None
    )
    # Optional values
    tfl_api_key = cfg.get("tfl_api_key")
    tfl_api_name = cfg.get("tfl_api_name")

    # Gather initial data and run the textual app
    initial_data = asyncio.run(constant_data_pull(tube_and_bus_stops, bikepoints))

    app = TfLDisplayApp()
    app.data_dict = initial_data
    app.client = client
    app.tube_and_bus_stops = tube_and_bus_stops
    app.bikepoints = bikepoints
    app.overground_stations = overground_stations
    app.overground_api_url = overground_api_url
    app.overground_routes = overground_routes
    app.overground_auth = overground_auth
    # Initial overground fetch (best-effort)
    initial_overground = asyncio.run(
        get_live_overground_trains(
            client, overground_routes, overground_api_url, overground_auth
        )
    )
    app.data_dict["overground_df"] = initial_overground
    # Set refresh interval from config (seconds)
    app.refresh_interval_seconds = cfg.get("refresh_interval_seconds", 10)

    # run the TUI
    app.run()
