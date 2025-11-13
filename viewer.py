"""
Main Viewer Window
Cross-platform ABF viewer and analyzer with professional electrophysiology interface
"""
import sys
import os
from pathlib import Path
from typing import Optional, List, Tuple, Dict
import numpy as np

from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QMenuBar, QToolBar, QStatusBar,
                               QFileDialog, QLabel, QSpinBox, QComboBox, QPushButton,
                               QSplitter, QTableWidget, QTableWidgetItem, QGroupBox,
                               QScrollArea, QMessageBox, QDialog, QDialogButtonBox,
                               QFormLayout, QDoubleSpinBox, QCheckBox, QTextEdit,
                               QSizePolicy, QColorDialog, QFrame)
from PySide6.QtCore import Qt, QTimer, Signal, Slot, QRectF, QPointF
from PySide6.QtGui import QAction, QIcon, QFont, QPainter, QPolygonF, QColor

import pyqtgraph as pg
from pyqtgraph import PlotWidget, PlotItem, ViewBox, LinearRegionItem

from abf_handler import ABFHandler, SweepData
from analysis_tools import AnalysisTools, Peak, Measurement, BlockDetector

# Try to import ABF writing capability
try:
    from pyabf.abfWriter import writeABF1
    ABF_WRITE_AVAILABLE = True
except ImportError:
    ABF_WRITE_AVAILABLE = False


class ZoomButton(QWidget):
    """Small + or - button for axis zooming"""
    clicked = Signal()
    
    def __init__(self, zoom_type: str = '+', parent=None):
        super().__init__(parent)
        self.zoom_type = zoom_type  # '+' or '-'
        self.setFixedSize(18, 18)
        self.setCursor(Qt.PointingHandCursor)
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(pg.mkPen('k', width=1.5))
        
        w, h = self.width(), self.height()
        center_x, center_y = w / 2, h / 2
        
        # Draw border rectangle
        painter.drawRect(1, 1, w - 2, h - 2)
        
        # Draw + or -
        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)
        
        if self.zoom_type == '+':
            # Draw horizontal line
            painter.drawLine(center_x - 4, center_y, center_x + 4, center_y)
            # Draw vertical line
            painter.drawLine(center_x, center_y - 4, center_x, center_y + 4)
        else:  # '-'
            # Draw horizontal line
            painter.drawLine(center_x - 4, center_y, center_x + 4, center_y)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()


class ZoomArrowButton(QWidget):
    """Small arrow button for axis panning"""
    clicked = Signal()
    
    def __init__(self, direction: str = 'up', parent=None):
        super().__init__(parent)
        self.direction = direction  # 'up', 'down', 'left', 'right'
        self.setFixedSize(12, 12)
        self.setCursor(Qt.PointingHandCursor)
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(pg.mkPen('k', width=1))
        painter.setBrush(pg.mkBrush('k'))
        
        w, h = self.width(), self.height()
        center_x, center_y = w / 2, h / 2
        
        if self.direction == 'up':
            points = QPolygonF([
                QPointF(center_x, 2),
                QPointF(2, h - 2),
                QPointF(w - 2, h - 2)
            ])
        elif self.direction == 'down':
            points = QPolygonF([
                QPointF(center_x, h - 2),
                QPointF(2, 2),
                QPointF(w - 2, 2)
            ])
        elif self.direction == 'left':
            points = QPolygonF([
                QPointF(2, center_y),
                QPointF(w - 2, 2),
                QPointF(w - 2, h - 2)
            ])
        else:  # right
            points = QPolygonF([
                QPointF(w - 2, center_y),
                QPointF(2, 2),
                QPointF(2, h - 2)
            ])
        
        painter.drawPolygon(points)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()


class TracePlotWidget(PlotWidget):
    """Custom plot widget with axis arrows for zooming"""
    cursor_moved = Signal(float, float)  # x, y
    cursor1_set = Signal(float, float)
    cursor2_set = Signal(float, float)
    
    def __init__(self, channel_label: str = "", parent=None):
        super().__init__(parent)
        
        # Set white background style
        self.setBackground('w')
        self.getAxis('left').setPen(pg.mkPen('k', width=1))
        self.getAxis('bottom').setPen(pg.mkPen('k', width=1))
        self.getAxis('right').setPen(pg.mkPen('k', width=1))
        
        self.setLabel('left', channel_label)
        self.setLabel('bottom', 'Time', units='s')
        self.showGrid(x=True, y=True, alpha=0.2)
        
        # Store trace color (default black)
        self.trace_color = 'k'
        self.grid_visible = True
        
        # Professional navigation: enable mouse controls
        self.setMouseEnabled(x=True, y=True)
        self.setMenuEnabled(False)  # Disable right-click menu
        
        # Configure viewbox for better interaction
        vb = self.getViewBox()
        vb.setMouseMode(pg.ViewBox.PanMode)  # Left click drag pans
        
        
        # Store channel label
        self.channel_label = channel_label
        
        # Cursors
        self.cursor1_line: Optional[pg.InfiniteLine] = None
        self.cursor2_line: Optional[pg.InfiniteLine] = None
        self.cursor1_enabled = False
        self.cursor2_enabled = False
        self.cursors_locked = False  # When locked, cursors move together maintaining distance
        
        # Data plot
        self.data_plot: Optional[pg.PlotDataItem] = None
        self.command_plot: Optional[pg.PlotDataItem] = None
        
        # Store current data
        self.current_time: Optional[np.ndarray] = None
        self.current_data: Optional[np.ndarray] = None
        self.current_command: Optional[np.ndarray] = None
    
    def plot_sweep(self, sweep_data: SweepData, show_command: bool = False, baseline_offset: float = 0.0):
        """Plot sweep data (data is already filtered if filters were applied)
        
        Args:
            sweep_data: Sweep data to plot (may contain pre-filtered data)
            show_command: Whether to show command waveform
            baseline_offset: Baseline correction offset
        """
        self.current_time = sweep_data.time
        
        # Data is already filtered (stored in filtered_data_ch0/ch1), just apply baseline correction
        self.current_data = sweep_data.data - baseline_offset
        self.current_command = sweep_data.command
        
        # Clear previous plots
        self.clear()
        
        # Clear block markers when replotting
        self.clear_block_markers()
        # Clear peak markers when replotting
        self.clear_peak_markers()
        
        # Plot data with customizable color
        self.data_plot = self.plot(sweep_data.time, self.current_data, 
                                   pen=pg.mkPen(self.trace_color, width=1.5))
        
        # Enable performance optimizations after plot creation
        # This avoids any coordinate system issues
        if isinstance(self.data_plot, pg.PlotDataItem):
            self.data_plot.setClipToView(True)  # Only render visible data points
            try:
                # Try new API first
                self.data_plot.setDownsampling(ds=True, auto=True, method='peak')
            except (TypeError, AttributeError):
                # Fall back to basic API if method parameter not supported
                try:
                    self.data_plot.setDownsampling(ds=True, auto=True)
                except (TypeError, AttributeError):
                    # Fall back to even simpler API
                    self.data_plot.setDownsampling(True)
                    if hasattr(self.data_plot, 'setAutoDownsample'):
                        self.data_plot.setAutoDownsample(True)
        
        # Plot command if available and requested (dotted)
        if show_command and sweep_data.command is not None and len(sweep_data.command) > 0:
            if np.any(sweep_data.command != 0):
                self.command_plot = self.plot(sweep_data.time, sweep_data.command,
                                             pen=pg.mkPen('k', width=1, style=Qt.PenStyle.DotLine))
                # Enable performance optimizations for command plot too
                if isinstance(self.command_plot, pg.PlotDataItem):
                    self.command_plot.setClipToView(True)
                    try:
                        # Try new API first
                        self.command_plot.setDownsampling(ds=True, auto=True, method='peak')
                    except (TypeError, AttributeError):
                        # Fall back to basic API if method parameter not supported
                        try:
                            self.command_plot.setDownsampling(ds=True, auto=True)
                        except (TypeError, AttributeError):
                            # Fall back to even simpler API
                            self.command_plot.setDownsampling(True)
                            if hasattr(self.command_plot, 'setAutoDownsample'):
                                self.command_plot.setAutoDownsample(True)
        
        # Re-add cursors if they were enabled
        if self.cursor1_enabled:
            self.enable_cursor1()
        if self.cursor2_enabled:
            self.enable_cursor2()
    
    def enable_cursor1(self):
        """Enable cursor 1"""
        self.cursor1_enabled = True
        if self.cursor1_line is None:
            # Get center of current view for initial position
            vb = self.getViewBox()
            if vb:
                x_range = vb.viewRange()[0]
                initial_x = (x_range[0] + x_range[1]) / 2
            else:
                initial_x = 0.0
            
            # Create cursor line
            self.cursor1_line = pg.InfiniteLine(angle=90, movable=True,
                                               pen=pg.mkPen('r', width=2),
                                               hoverPen=pg.mkPen((255, 180, 180), width=2))  # Lighter red for hover
            self.cursor1_line.setValue(initial_x)  # Set position after creation
            self.cursor1_line.sigPositionChanged.connect(self._on_cursor1_moved)
            self.addItem(self.cursor1_line)
        else:
            # If cursor already exists, reposition to center if at 0.0
            if abs(self.cursor1_line.value()) < 1e-10:  # Check if essentially 0
                vb = self.getViewBox()
                if vb:
                    x_range = vb.viewRange()[0]
                    initial_x = (x_range[0] + x_range[1]) / 2
                    self.cursor1_line.setValue(initial_x)
            self.addItem(self.cursor1_line)
    
    def enable_cursor2(self):
        """Enable cursor 2"""
        self.cursor2_enabled = True
        if self.cursor2_line is None:
            # Get center of current view for initial position
            vb = self.getViewBox()
            if vb:
                x_range = vb.viewRange()[0]
                initial_x = (x_range[0] + x_range[1]) / 2
            else:
                initial_x = 0.0
            
            # Create cursor line
            self.cursor2_line = pg.InfiniteLine(angle=90, movable=True,
                                               pen=pg.mkPen('b', width=2),
                                               hoverPen=pg.mkPen((180, 180, 255), width=2))  # Lighter blue for hover
            self.cursor2_line.setValue(initial_x)  # Set position after creation
            self.cursor2_line.sigPositionChanged.connect(self._on_cursor2_moved)
            self.addItem(self.cursor2_line)
        else:
            # If cursor already exists, reposition to center if at 0.0
            if abs(self.cursor2_line.value()) < 1e-10:  # Check if essentially 0
                vb = self.getViewBox()
                if vb:
                    x_range = vb.viewRange()[0]
                    initial_x = (x_range[0] + x_range[1]) / 2
                    self.cursor2_line.setValue(initial_x)
            self.addItem(self.cursor2_line)
    
    def set_cursor1_position(self, x: float):
        """Set cursor 1 position (for synchronization)"""
        if self.cursor1_line:
            self.cursor1_line.setValue(x)
    
    def set_cursor2_position(self, x: float):
        """Set cursor 2 position (for synchronization)"""
        if self.cursor2_line:
            self.cursor2_line.setValue(x)
    
    def disable_cursor1(self):
        """Disable cursor 1"""
        self.cursor1_enabled = False
        if self.cursor1_line:
            self.removeItem(self.cursor1_line)
    
    def disable_cursor2(self):
        """Disable cursor 2"""
        self.cursor2_enabled = False
        if self.cursor2_line:
            self.removeItem(self.cursor2_line)
    
    def _on_cursor1_moved(self):
        """Handle cursor 1 movement"""
        if self.cursor1_line and self.current_time is not None:
            x = self.cursor1_line.value()
            y = self._get_y_at_x(x) if self.current_data is not None else 0.0
            
            # If cursors are locked, move cursor 2 maintaining distance
            if self.cursors_locked and self.cursor2_line:
                if not hasattr(self, '_cursor_distance'):
                    # First time - calculate and store distance
                    x2 = self.cursor2_line.value()
                    self._cursor_distance = x2 - x
                else:
                    # Move cursor 2 maintaining distance
                    new_x2 = x + self._cursor_distance
                    # Temporarily disconnect to avoid recursive updates
                    if self.cursor2_line:
                        self.cursor2_line.blockSignals(True)
                        self.set_cursor2_position(new_x2)
                        self.cursor2_line.blockSignals(False)
            
            self.cursor1_set.emit(x, y)
            self.cursor_moved.emit(x, y)
    
    def _on_cursor2_moved(self):
        """Handle cursor 2 movement"""
        if self.cursor2_line and self.current_time is not None:
            x = self.cursor2_line.value()
            y = self._get_y_at_x(x) if self.current_data is not None else 0.0
            
            # If cursors are locked, move cursor 1 maintaining distance
            if self.cursors_locked and self.cursor1_line:
                if not hasattr(self, '_cursor_distance'):
                    # First time - calculate and store distance
                    x1 = self.cursor1_line.value()
                    self._cursor_distance = x - x1
                else:
                    # Move cursor 1 maintaining distance
                    new_x1 = x - self._cursor_distance
                    # Temporarily disconnect to avoid recursive updates
                    if self.cursor1_line:
                        self.cursor1_line.blockSignals(True)
                        self.set_cursor1_position(new_x1)
                        self.cursor1_line.blockSignals(False)
            
            self.cursor2_set.emit(x, y)
            self.cursor_moved.emit(x, y)
    
    def set_cursors_locked(self, locked: bool):
        """Set whether cursors are locked together"""
        self.cursors_locked = locked
        # Reset distance when unlocking
    
    def set_trace_color(self, color):
        """Set the color for the trace (can be string like 'k', 'r', or RGB tuple)"""
        self.trace_color = color
        # Update existing plot if it exists
        if self.data_plot is not None:
            self.data_plot.setPen(pg.mkPen(color, width=1.5))
    
    def set_grid_visible(self, visible: bool):
        """Show or hide grid lines"""
        self.grid_visible = visible
        self.showGrid(x=visible, y=visible, alpha=0.2 if visible else 0)
    
    def _on_view_changed(self):
        """Handle view range changes"""
        # No label updates needed anymore
        pass
    
    def _get_y_at_x(self, x: float) -> float:
        """Get y value at x position by interpolation"""
        if self.current_time is None or self.current_data is None:
            return 0.0
        
        # Find closest index
        idx = np.argmin(np.abs(self.current_time - x))
        if idx < len(self.current_data):
            return float(self.current_data[idx])
        return 0.0
    
    def get_cursor_positions(self) -> Tuple[float, float, float, float]:
        """Get cursor positions (x1, y1, x2, y2)"""
        x1 = self.cursor1_line.value() if self.cursor1_line else 0.0
        y1 = self._get_y_at_x(x1)
        x2 = self.cursor2_line.value() if self.cursor2_line else 0.0
        y2 = self._get_y_at_x(x2)
        return x1, y1, x2, y2
    
    def mark_peaks(self, peaks: List[Peak]):
        """Mark peaks on the plot"""
        # Clear existing peak markers first
        self.clear_peak_markers()
        
        for peak in peaks:
            if self.current_time is not None:
                time = self.current_time[peak.index]
                color = 'g' if peak.is_max else 'r'
                scatter = pg.ScatterPlotItem([time], [peak.value], 
                                            symbol='o', size=10, 
                                            pen=pg.mkPen(color, width=2),
                                            brush=pg.mkBrush(color))
                self.addItem(scatter)
                
                # Store references for clearing
                if not hasattr(self, '_peak_markers'):
                    self._peak_markers = []
                self._peak_markers.append(scatter)
    
    def clear_peak_markers(self):
        """Clear all peak markers from the plot"""
        if hasattr(self, '_peak_markers'):
            for marker in self._peak_markers:
                try:
                    self.removeItem(marker)
                except:
                    pass
            self._peak_markers = []
    
    def mark_blocks(self, blocks: List[Dict]):
        """Mark blocks on the plot with colored regions"""
        # Clear existing block markers
        self.clear_block_markers()
        
        for block in blocks:
            start_time = block.get('start_time')
            end_time = block.get('end_time')
            avg_amplitude = block.get('average_amplitude', 0)
            
            if start_time is None or end_time is None:
                continue
            
            # Create a region highlight for the block
            # Use a semi-transparent rectangle
            region = LinearRegionItem([start_time, end_time], 
                                     movable=False,
                                     brush=pg.mkBrush((255, 200, 0, 100)),  # Orange/yellow with transparency
                                     pen=pg.mkPen((255, 150, 0, 200), width=2))
            self.addItem(region)
            
            # Also mark the average amplitude point
            mid_time = (start_time + end_time) / 2
            scatter = pg.ScatterPlotItem([mid_time], [avg_amplitude],
                                        symbol='s', size=8,
                                        pen=pg.mkPen('orange', width=2),
                                        brush=pg.mkBrush('orange'))
            self.addItem(scatter)
            
            # Store references for clearing
            if not hasattr(self, '_block_markers'):
                self._block_markers = []
            self._block_markers.append(region)
            self._block_markers.append(scatter)
    
    def clear_block_markers(self):
        """Clear all block markers from the plot"""
        if hasattr(self, '_block_markers'):
            for marker in self._block_markers:
                try:
                    self.removeItem(marker)
                except:
                    pass
            self._block_markers = []
    
    def zoom_x(self, factor: float):
        """Zoom x-axis by factor"""
        vb = self.getViewBox()
        x_range = vb.viewRange()[0]
        center = (x_range[0] + x_range[1]) / 2
        width = x_range[1] - x_range[0]
        new_width = width / factor
        vb.setXRange(center - new_width/2, center + new_width/2, padding=0)
    
    def zoom_y(self, factor: float):
        """Zoom y-axis by factor"""
        vb = self.getViewBox()
        y_range = vb.viewRange()[1]
        center = (y_range[0] + y_range[1]) / 2
        height = y_range[1] - y_range[0]
        new_height = height / factor
        vb.setYRange(center - new_height/2, center + new_height/2, padding=0)
    
    def pan_x(self, direction: str):
        """Pan x-axis"""
        vb = self.getViewBox()
        x_range = vb.viewRange()[0]
        width = x_range[1] - x_range[0]
        shift = width * 0.1
        if direction == 'left':
            vb.setXRange(x_range[0] - shift, x_range[1] - shift, padding=0)
        else:
            vb.setXRange(x_range[0] + shift, x_range[1] + shift, padding=0)
    
    def pan_y(self, direction: str):
        """Pan y-axis"""
        vb = self.getViewBox()
        y_range = vb.viewRange()[1]
        height = y_range[1] - y_range[0]
        shift = height * 0.1
        if direction == 'up':
            vb.setYRange(y_range[0] + shift, y_range[1] + shift, padding=0)
        else:
            vb.setYRange(y_range[0] - shift, y_range[1] - shift, padding=0)


class DualChannelPlotWidget(QWidget):
    """Container widget with two plots stacked vertically and axis arrows"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Create two plot widgets
        self.plot0 = TracePlotWidget("Channel 0")
        self.plot1 = TracePlotWidget("Channel 1")
        
        # Create containers for plots with axis arrows
        self.plot0_container = self._create_plot_container(self.plot0, 0)
        self.plot1_container = self._create_plot_container(self.plot1, 1)
        
        layout.addWidget(self.plot0_container, 1)
        layout.addWidget(self.plot1_container, 1)
        
        # Link x-axes for synchronized zooming
        self.plot1.getViewBox().setXLink(self.plot0.getViewBox())
        
        # Connect cursors for synchronization
        self.plot0.cursor1_line = None  # Will be created when enabled
        self.plot0.cursor2_line = None
        self.plot1.cursor1_line = None
        self.plot1.cursor2_line = None
        
        # Store references for easy access
        self.plots = [self.plot0, self.plot1]
        
        # Connect cursor movement to sync between plots
        self.plot0.cursor_moved.connect(self._sync_cursors)
        self.plot1.cursor_moved.connect(self._sync_cursors)
    
    def _sync_cursors(self, x: float, y: float):
        """Synchronize cursor positions between plots"""
        # Get which cursor moved
        if self.plot0.cursor1_enabled and self.plot0.cursor1_line:
            if abs(self.plot0.cursor1_line.value() - x) < 0.0001:
                # Cursor 1 moved on plot0, sync to plot1
                self.plot1.set_cursor1_position(x)
        if self.plot0.cursor2_enabled and self.plot0.cursor2_line:
            if abs(self.plot0.cursor2_line.value() - x) < 0.0001:
                # Cursor 2 moved on plot0, sync to plot1
                self.plot1.set_cursor2_position(x)
        if self.plot1.cursor1_enabled and self.plot1.cursor1_line:
            if abs(self.plot1.cursor1_line.value() - x) < 0.0001:
                # Cursor 1 moved on plot1, sync to plot0
                self.plot0.set_cursor1_position(x)
        if self.plot1.cursor2_enabled and self.plot1.cursor2_line:
            if abs(self.plot1.cursor2_line.value() - x) < 0.0001:
                # Cursor 2 moved on plot1, sync to plot0
                self.plot0.set_cursor2_position(x)
    
    def _create_plot_container(self, plot: TracePlotWidget, index: int) -> QWidget:
        """Create a container widget with plot and axis arrows"""
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(20, 5, 5, 5)
        container_layout.setSpacing(0)
        
        # Top row: y-axis up arrow, plot area, y-axis down arrow
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(0)
        
        # Left side: y-axis controls (zoom buttons together, pan centered)
        y_axis_container = QVBoxLayout()
        y_axis_container.setContentsMargins(0, 0, 5, 0)
        y_axis_container.setSpacing(0)
        
        # Top: zoom buttons together (side by side)
        zoom_buttons_container = QHBoxLayout()
        zoom_buttons_container.setContentsMargins(0, 0, 0, 0)
        zoom_buttons_container.setSpacing(3)
        
        zoom_in_y = ZoomButton('+')
        zoom_in_y.clicked.connect(lambda: plot.zoom_y(1.2))  # Zoom in (show less)
        zoom_buttons_container.addWidget(zoom_in_y, 0, Qt.AlignCenter)
        
        zoom_out_y = ZoomButton('-')
        zoom_out_y.clicked.connect(lambda: plot.zoom_y(1/1.2))  # Zoom out (show more)
        zoom_buttons_container.addWidget(zoom_out_y, 0, Qt.AlignCenter)
        
        y_axis_container.addLayout(zoom_buttons_container, 0)
        y_axis_container.addStretch()
        
        # Middle: pan arrows centered vertically (close together)
        pan_container = QVBoxLayout()
        pan_container.setContentsMargins(0, 0, 0, 0)
        pan_container.setSpacing(3)
        
        # Pan up arrow
        pan_up = ZoomArrowButton('up')
        pan_up.clicked.connect(lambda: plot.pan_y('up'))
        pan_container.addWidget(pan_up, 0, Qt.AlignCenter)
        
        # Pan down arrow
        pan_down = ZoomArrowButton('down')
        pan_down.clicked.connect(lambda: plot.pan_y('down'))
        pan_container.addWidget(pan_down, 0, Qt.AlignCenter)
        
        y_axis_container.addLayout(pan_container, 0)
        y_axis_container.addStretch()
        
        top_row.addLayout(y_axis_container, 0)
        
        # Plot area
        plot_container = QVBoxLayout()
        plot_container.setContentsMargins(0, 0, 0, 0)
        plot_container.setSpacing(0)
        plot_container.addWidget(plot, 1)
        
        # Bottom row: x-axis arrows (only for bottom plot)
        bottom_arrows = QHBoxLayout()
        bottom_arrows.setContentsMargins(20, 0, 0, 0)
        bottom_arrows.setSpacing(0)
        bottom_arrows.addStretch()
        
        if index == 1:  # Only show on bottom plot
            # Pan left arrow
            left_arrow = ZoomArrowButton('left')
            left_arrow.clicked.connect(lambda: self._pan_x_all('left'))
            bottom_arrows.addWidget(left_arrow)
            
            bottom_arrows.addSpacing(10)
            
            # Pan right arrow
            right_arrow = ZoomArrowButton('right')
            right_arrow.clicked.connect(lambda: self._pan_x_all('right'))
            bottom_arrows.addWidget(right_arrow)
        
        bottom_arrows.addStretch()
        
        plot_container.addLayout(bottom_arrows)
        top_row.addLayout(plot_container, 1)
        
        container_layout.addLayout(top_row, 1)
        
        # Add zoom buttons on right side of x-axis (only for bottom plot)
        if index == 1:
            x_axis_row = QHBoxLayout()
            x_axis_row.setContentsMargins(20, 0, 0, 0)
            x_axis_row.setSpacing(0)
            x_axis_row.addStretch()
            
            zoom_in_x = ZoomButton('+')
            zoom_in_x.clicked.connect(lambda: self._zoom_x_all(1.2))  # Zoom in (show less)
            x_axis_row.addWidget(zoom_in_x)
            
            x_axis_row.addSpacing(5)
            
            zoom_out_x = ZoomButton('-')
            zoom_out_x.clicked.connect(lambda: self._zoom_x_all(1/1.2))  # Zoom out (show more)
            x_axis_row.addWidget(zoom_out_x)
            
            x_axis_row.addSpacing(20)
            container_layout.addLayout(x_axis_row, 0)
        
        return container
    
    def _zoom_x_all(self, factor: float):
        """Zoom x-axis on all plots"""
        self.plot0.zoom_x(factor)
        # plot1 x-axis is linked, so it will update automatically
    
    def _pan_x_all(self, direction: str):
        """Pan x-axis on all plots"""
        self.plot0.pan_x(direction)
        # plot1 x-axis is linked, so it will update automatically
    
    def plot_sweeps(self, channel0_sweep: Optional[SweepData],
                   channel1_sweep: Optional[SweepData],
                   channel0_units: str = "",
                   channel1_units: str = "",
                   show_command: bool = False,
                   baseline_offset_ch0: float = 0.0,
                   baseline_offset_ch1: float = 0.0):
        """Plot sweeps on both channels"""
        # Plot channel 0
        if channel0_sweep:
            label0 = f'Channel 0 ({channel0_units})' if channel0_units else 'Channel 0'
            # Set label before plotting (will be preserved through clear)
            self.plot0.setLabel('left', label0)
            self.plot0.plot_sweep(channel0_sweep, show_command, baseline_offset_ch0)
            # Re-set label after plot_sweep clears everything
            self.plot0.setLabel('left', label0)
        
        # Plot channel 1
        if channel1_sweep is not None:
            label1 = f'Channel 1 ({channel1_units})' if channel1_units else 'Channel 1'
            # Set label before plotting (will be preserved through clear)
            self.plot1.setLabel('left', label1)
            self.plot1.plot_sweep(channel1_sweep, show_command, baseline_offset_ch1)
            # Re-set label after plot_sweep clears everything
            self.plot1.setLabel('left', label1)


class CursorDialog(QDialog):
    """Dialog for cursor measurements"""
    def __init__(self, measurement: Measurement, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cursor Measurement")
        self.setModal(False)
        
        layout = QFormLayout()
        
        self.delta_x_label = QLabel(f"{measurement.delta_x:.6f} s")
        self.delta_y_label = QLabel(f"{measurement.delta_y:.6f}")
        self.slope_label = QLabel(f"{measurement.slope:.6f}")
        self.x1_label = QLabel(f"{measurement.x1:.6f} s")
        self.y1_label = QLabel(f"{measurement.y1:.6f}")
        self.x2_label = QLabel(f"{measurement.x2:.6f} s")
        self.y2_label = QLabel(f"{measurement.y2:.6f}")
        
        layout.addRow("Time Difference (ΔX):", self.delta_x_label)
        layout.addRow("Amplitude Difference (ΔY):", self.delta_y_label)
        layout.addRow("Slope:", self.slope_label)
        layout.addRow("X1:", self.x1_label)
        layout.addRow("Y1:", self.y1_label)
        layout.addRow("X2:", self.x2_label)
        layout.addRow("Y2:", self.y2_label)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.accept)
        layout.addRow(buttons)
        
        self.setLayout(layout)


class StatisticsDialog(QDialog):
    """Dialog for displaying statistics"""
    def __init__(self, stats: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Statistics")
        self.setModal(False)
        
        layout = QFormLayout()
        
        for key, value in stats.items():
            if isinstance(value, float):
                label = QLabel(f"{value:.6f}")
            else:
                label = QLabel(str(value))
            layout.addRow(key.replace('_', ' ').title() + ":", label)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.accept)
        layout.addRow(buttons)
        
        self.setLayout(layout)


class BlockDetectionDialog(QDialog):
    """Dialog for block detection parameters"""
    def __init__(self, parent=None, cursor1_y: float = None):
        super().__init__(parent)
        self.setWindowTitle("Block Detection")
        self.setModal(True)
        
        layout = QFormLayout()
        
        # Option to use cursor 1 Y value
        self.use_cursor1_check = QCheckBox()
        self.use_cursor1_check.setChecked(cursor1_y is not None)
        self.use_cursor1_check.setEnabled(cursor1_y is not None)
        layout.addRow("Use Cursor 1 Y value as baseline:", self.use_cursor1_check)
        
        self.baseline_threshold_spin = QDoubleSpinBox()
        self.baseline_threshold_spin.setRange(-1e6, 1e6)
        if cursor1_y is not None:
            self.baseline_threshold_spin.setValue(cursor1_y)
        else:
            self.baseline_threshold_spin.setValue(0.0)
            self.baseline_threshold_spin.setSpecialValueText("Auto")
        layout.addRow("Baseline Threshold:", self.baseline_threshold_spin)
        
        self.block_threshold_factor_spin = QDoubleSpinBox()
        self.block_threshold_factor_spin.setRange(0.1, 10.0)
        self.block_threshold_factor_spin.setValue(2.0)
        self.block_threshold_factor_spin.setDecimals(1)
        layout.addRow("Block Threshold Factor:", self.block_threshold_factor_spin)
        
        self.min_duration_spin = QDoubleSpinBox()
        self.min_duration_spin.setRange(0.0001, 1.0)
        self.min_duration_spin.setValue(0.001)
        self.min_duration_spin.setDecimals(4)
        self.min_duration_spin.setSuffix(" s")
        layout.addRow("Min Block Duration:", self.min_duration_spin)
        
        info_label = QLabel(
            "Detects blocking events where current moves toward 0 pA from baseline.\n"
            "Higher threshold factor = more conservative detection."
        )
        info_label.setStyleSheet("color: gray; font-style: italic;")
        info_label.setWordWrap(True)
        layout.addRow("", info_label)
        
        # Update baseline spin when checkbox changes
        if cursor1_y is not None:
            self.use_cursor1_check.toggled.connect(
                lambda checked: self.baseline_threshold_spin.setValue(cursor1_y) if checked else None
            )
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
        
        self.setLayout(layout)
    
    def get_baseline_threshold(self):
        """Get baseline threshold (None if auto)"""
        if self.use_cursor1_check.isChecked():
            return self.baseline_threshold_spin.value()
        val = self.baseline_threshold_spin.value()
        return None if val == 0.0 else val
    
    def get_block_threshold_factor(self):
        """Get block threshold factor"""
        return self.block_threshold_factor_spin.value()
    
    def get_min_duration(self):
        """Get minimum block duration"""
        return self.min_duration_spin.value()


class BlocksTableDialog(QDialog):
    """Dialog for displaying detected blocks in a table"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Blocks Table")
        self.setModal(False)
        self.setMinimumSize(800, 400)
        
        layout = QVBoxLayout()
        
        # Table widget
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Block", "Sweep", "Start Time (s)", "End Time (s)", "Duration (s)",
            "Average Amplitude", "Baseline Amplitude", "Block Depth"
        ])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        copy_btn = QPushButton("Copy Selected")
        copy_btn.clicked.connect(self.copy_selected)
        button_layout.addWidget(copy_btn)
        
        copy_all_btn = QPushButton("Copy All")
        copy_all_btn.clicked.connect(self.copy_all)
        button_layout.addWidget(copy_all_btn)
        
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self.clear_all)
        button_layout.addWidget(clear_btn)
        
        button_layout.addStretch()
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
        
        # Clipboard
        self.app = QApplication.instance()
    
    def add_blocks(self, blocks: List[Dict]):
        """Add blocks to the table"""
        if not blocks:
            return
        
        for i, block in enumerate(blocks):
            row = self.table.rowCount()
            self.table.insertRow(row)
            
            block_num = row + 1
            sweep_num = block.get('sweep_number', '')
            
            self.table.setItem(row, 0, QTableWidgetItem(str(block_num)))
            self.table.setItem(row, 1, QTableWidgetItem(str(sweep_num)))
            self.table.setItem(row, 2, QTableWidgetItem(f"{block.get('start_time', 0):.6f}"))
            self.table.setItem(row, 3, QTableWidgetItem(f"{block.get('end_time', 0):.6f}"))
            self.table.setItem(row, 4, QTableWidgetItem(f"{block.get('duration', 0):.6f}"))
            self.table.setItem(row, 5, QTableWidgetItem(f"{block.get('average_amplitude', 0):.6f}"))
            self.table.setItem(row, 6, QTableWidgetItem(f"{block.get('baseline_amplitude', 0):.6f}"))
            self.table.setItem(row, 7, QTableWidgetItem(f"{block.get('block_depth', 0):.6f}"))
        
        # Resize columns to content
        self.table.resizeColumnsToContents()
    
    def copy_selected(self):
        """Copy selected rows to clipboard"""
        selection = self.table.selectedIndexes()
        if not selection:
            return
        
        # Get unique rows
        rows = sorted(set(index.row() for index in selection))
        
        lines = []
        # Header
        headers = []
        for col in range(self.table.columnCount()):
            headers.append(self.table.horizontalHeaderItem(col).text())
        lines.append("\t".join(headers))
        
        # Data rows
        for row in rows:
            row_data = []
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                row_data.append(item.text() if item else "")
            lines.append("\t".join(row_data))
        
        self.app.clipboard().setText("\n".join(lines))
    
    def copy_all(self):
        """Copy all rows to clipboard"""
        if self.table.rowCount() == 0:
            return
        
        # Select all
        self.table.selectAll()
        self.copy_selected()
    
    def clear_all(self):
        """Clear all blocks"""
        self.table.setRowCount(0)


class PeakDetectionDialog(QDialog):
    """Dialog for peak detection parameters"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Peak Detection")
        self.setModal(True)
        
        layout = QFormLayout()
        
        self.height_spin = QDoubleSpinBox()
        self.height_spin.setRange(-1e6, 1e6)
        self.height_spin.setValue(0.0)
        self.height_spin.setSpecialValueText("None")
        layout.addRow("Min Height:", self.height_spin)
        
        self.distance_spin = QSpinBox()
        self.distance_spin.setRange(0, 10000)
        self.distance_spin.setValue(10)
        layout.addRow("Min Distance (samples):", self.distance_spin)
        
        self.prominence_spin = QDoubleSpinBox()
        self.prominence_spin.setRange(0, 1e6)
        self.prominence_spin.setValue(0.0)
        self.prominence_spin.setSpecialValueText("None")
        layout.addRow("Prominence:", self.prominence_spin)
        
        self.find_max_check = QCheckBox()
        self.find_max_check.setChecked(True)
        layout.addRow("Find Peaks (uncheck for troughs):", self.find_max_check)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
        
        self.setLayout(layout)


class MeasurementsTableDialog(QDialog):
    """Dialog for displaying measurements in a table"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Measurements Table")
        self.setModal(False)
        self.setMinimumSize(600, 400)
        
        layout = QVBoxLayout()
        
        # Table widget
        self.table = QTableWidget()
        self.table.setColumnCount(10)
        self.table.setHorizontalHeaderLabels([
            "Measurement", "X1 (s)", "Y1 Ch0", "Y1 Ch1", "X2 (s)", "Y2 Ch0", "Y2 Ch1", "ΔX (s)", "ΔY Ch0", "ΔY Ch1"
        ])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        copy_btn = QPushButton("Copy Selected")
        copy_btn.clicked.connect(self.copy_selected)
        button_layout.addWidget(copy_btn)
        
        copy_all_btn = QPushButton("Copy All")
        copy_all_btn.clicked.connect(self.copy_all)
        button_layout.addWidget(copy_all_btn)
        
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self.clear_all)
        button_layout.addWidget(clear_btn)
        
        button_layout.addStretch()
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
        
        # Clipboard
        self.app = QApplication.instance()
    
    def add_measurement(self, measurement_ch0: Measurement, measurement_ch1: Optional[Measurement] = None, measurement_num: int = None):
        """Add a measurement to the table (both channels)"""
        row = self.table.rowCount()
        self.table.insertRow(row)
        
        if measurement_num is None:
            measurement_num = row + 1
        
        # Use channel 0 measurement for X positions (they're the same)
        self.table.setItem(row, 0, QTableWidgetItem(str(measurement_num)))
        self.table.setItem(row, 1, QTableWidgetItem(f"{measurement_ch0.x1:.6f}"))
        self.table.setItem(row, 2, QTableWidgetItem(f"{measurement_ch0.y1:.6f}"))  # Ch0 Y1
        self.table.setItem(row, 3, QTableWidgetItem(f"{measurement_ch1.y1:.6f}" if measurement_ch1 else ""))  # Ch1 Y1
        self.table.setItem(row, 4, QTableWidgetItem(f"{measurement_ch0.x2:.6f}"))
        self.table.setItem(row, 5, QTableWidgetItem(f"{measurement_ch0.y2:.6f}"))  # Ch0 Y2
        self.table.setItem(row, 6, QTableWidgetItem(f"{measurement_ch1.y2:.6f}" if measurement_ch1 else ""))  # Ch1 Y2
        self.table.setItem(row, 7, QTableWidgetItem(f"{measurement_ch0.delta_x:.6f}"))
        self.table.setItem(row, 8, QTableWidgetItem(f"{measurement_ch0.delta_y:.6f}"))  # Ch0 ΔY
        self.table.setItem(row, 9, QTableWidgetItem(f"{measurement_ch1.delta_y:.6f}" if measurement_ch1 else ""))  # Ch1 ΔY
        
        # Resize columns to content
        self.table.resizeColumnsToContents()
    
    def copy_selected(self):
        """Copy selected rows to clipboard"""
        selection = self.table.selectedIndexes()
        if not selection:
            return
        
        # Get unique rows
        rows = sorted(set(index.row() for index in selection))
        
        lines = []
        # Header
        headers = []
        for col in range(self.table.columnCount()):
            headers.append(self.table.horizontalHeaderItem(col).text())
        lines.append("\t".join(headers))
        
        # Data rows
        for row in rows:
            row_data = []
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                row_data.append(item.text() if item else "")
            lines.append("\t".join(row_data))
        
        self.app.clipboard().setText("\n".join(lines))
    
    def copy_all(self):
        """Copy all rows to clipboard"""
        if self.table.rowCount() == 0:
            return
        
        # Select all
        self.table.selectAll()
        self.copy_selected()
    
    def clear_all(self):
        """Clear all measurements"""
        self.table.setRowCount(0)


class StatisticsTableDialog(QDialog):
    """Dialog for displaying statistics in a table"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Statistics Table")
        self.setModal(False)
        self.setMinimumSize(600, 400)
        
        layout = QVBoxLayout()
        
        # Table widget
        self.table = QTableWidget()
        self.table.setColumnCount(19)  # Sweep + 9 stats per channel (2 channels)
        self.table.setHorizontalHeaderLabels([
            "Sweep", 
            "Mean Ch0", "Std Ch0", "Min Ch0", "Max Ch0", "Median Ch0", "Q25 Ch0", "Q75 Ch0", "Range Ch0", "Variance Ch0",
            "Mean Ch1", "Std Ch1", "Min Ch1", "Max Ch1", "Median Ch1", "Q25 Ch1", "Q75 Ch1", "Range Ch1", "Variance Ch1"
        ])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        copy_btn = QPushButton("Copy Selected")
        copy_btn.clicked.connect(self.copy_selected)
        button_layout.addWidget(copy_btn)
        
        copy_all_btn = QPushButton("Copy All")
        copy_all_btn.clicked.connect(self.copy_all)
        button_layout.addWidget(copy_all_btn)
        
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self.clear_all)
        button_layout.addWidget(clear_btn)
        
        button_layout.addStretch()
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
        
        # Clipboard
        self.app = QApplication.instance()
    
    def add_statistics(self, stats_ch0: dict, stats_ch1: Optional[dict] = None, sweep_num: int = None):
        """Add statistics to the table (both channels)"""
        row = self.table.rowCount()
        self.table.insertRow(row)
        
        if sweep_num is None:
            sweep_num = row + 1
        
        # Set sweep number
        self.table.setItem(row, 0, QTableWidgetItem(str(sweep_num)))
        
        # Helper function to add stats values
        def add_stats(stats: dict, start_col: int):
            self.table.setItem(row, start_col + 0, QTableWidgetItem(f"{stats.get('mean', 0):.6f}"))
            self.table.setItem(row, start_col + 1, QTableWidgetItem(f"{stats.get('std', 0):.6f}"))
            self.table.setItem(row, start_col + 2, QTableWidgetItem(f"{stats.get('min', 0):.6f}"))
            self.table.setItem(row, start_col + 3, QTableWidgetItem(f"{stats.get('max', 0):.6f}"))
            self.table.setItem(row, start_col + 4, QTableWidgetItem(f"{stats.get('median', 0):.6f}"))
            self.table.setItem(row, start_col + 5, QTableWidgetItem(f"{stats.get('q25', 0):.6f}"))
            self.table.setItem(row, start_col + 6, QTableWidgetItem(f"{stats.get('q75', 0):.6f}"))
            self.table.setItem(row, start_col + 7, QTableWidgetItem(f"{stats.get('range', 0):.6f}"))
            self.table.setItem(row, start_col + 8, QTableWidgetItem(f"{stats.get('variance', 0):.6f}"))
        
        # Add Channel 0 statistics (columns 1-9)
        add_stats(stats_ch0, 1)
        
        # Add Channel 1 statistics (columns 10-18) if available
        if stats_ch1:
            add_stats(stats_ch1, 10)
        else:
            # Fill with empty strings if Ch1 not available
            for col in range(10, 19):
                self.table.setItem(row, col, QTableWidgetItem(""))
        
        # Resize columns to content
        self.table.resizeColumnsToContents()
    
    def copy_selected(self):
        """Copy selected rows to clipboard"""
        selection = self.table.selectedIndexes()
        if not selection:
            return
        
        # Get unique rows
        rows = sorted(set(index.row() for index in selection))
        
        lines = []
        # Header
        headers = []
        for col in range(self.table.columnCount()):
            headers.append(self.table.horizontalHeaderItem(col).text())
        lines.append("\t".join(headers))
        
        # Data rows
        for row in rows:
            row_data = []
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                row_data.append(item.text() if item else "")
            lines.append("\t".join(row_data))
        
        self.app.clipboard().setText("\n".join(lines))
    
    def copy_all(self):
        """Copy all rows to clipboard"""
        if self.table.rowCount() == 0:
            return
        
        # Select all
        self.table.selectAll()
        self.copy_selected()
    
    def clear_all(self):
        """Clear all statistics"""
        self.table.setRowCount(0)


class PeaksTableDialog(QDialog):
    """Dialog for displaying detected peaks in a table"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Peaks Table")
        self.setModal(False)
        self.setMinimumSize(600, 400)
        
        layout = QVBoxLayout()
        
        # Table widget
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "Peak", "Index", "Time (s)", "Value", "Type"
        ])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        copy_btn = QPushButton("Copy Selected")
        copy_btn.clicked.connect(self.copy_selected)
        button_layout.addWidget(copy_btn)
        
        copy_all_btn = QPushButton("Copy All")
        copy_all_btn.clicked.connect(self.copy_all)
        button_layout.addWidget(copy_all_btn)
        
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self.clear_all)
        button_layout.addWidget(clear_btn)
        
        button_layout.addStretch()
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
        
        # Clipboard
        self.app = QApplication.instance()
    
    def add_peaks(self, peaks: List[Peak], sweep_num: int = None):
        """Add peaks to the table"""
        if not peaks:
            return
        
        for i, peak in enumerate(peaks):
            row = self.table.rowCount()
            self.table.insertRow(row)
            
            peak_num = row + 1
            
            self.table.setItem(row, 0, QTableWidgetItem(str(peak_num)))
            self.table.setItem(row, 1, QTableWidgetItem(str(peak.index)))
            self.table.setItem(row, 2, QTableWidgetItem(f"{peak.time:.6f}"))
            self.table.setItem(row, 3, QTableWidgetItem(f"{peak.value:.6f}"))
            self.table.setItem(row, 4, QTableWidgetItem("Peak" if peak.is_max else "Trough"))
        
        # Resize columns to content
        self.table.resizeColumnsToContents()
    
    def copy_selected(self):
        """Copy selected rows to clipboard"""
        selection = self.table.selectedIndexes()
        if not selection:
            return
        
        # Get unique rows
        rows = sorted(set(index.row() for index in selection))
        
        lines = []
        # Header
        headers = []
        for col in range(self.table.columnCount()):
            headers.append(self.table.horizontalHeaderItem(col).text())
        lines.append("\t".join(headers))
        
        # Data rows
        for row in rows:
            row_data = []
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                row_data.append(item.text() if item else "")
            lines.append("\t".join(row_data))
        
        self.app.clipboard().setText("\n".join(lines))
    
    def copy_all(self):
        """Copy all rows to clipboard"""
        if self.table.rowCount() == 0:
            return
        
        # Select all
        self.table.selectAll()
        self.copy_selected()
    
    def clear_all(self):
        """Clear all peaks"""
        self.table.setRowCount(0)


class SaveDialog(QDialog):
    """Dialog for save options"""
    def __init__(self, parent=None, cursors_enabled: bool = False):
        super().__init__(parent)
        self.setWindowTitle("Save ABF File")
        self.setModal(True)
        
        layout = QFormLayout()
        
        # Option to save between cursors only
        self.save_between_cursors_check = QCheckBox()
        self.save_between_cursors_check.setChecked(False)
        self.save_between_cursors_check.setEnabled(cursors_enabled)
        layout.addRow("Save region between cursors only:", self.save_between_cursors_check)
        
        if not cursors_enabled:
            info_label = QLabel("Enable both cursors to save a region")
            info_label.setStyleSheet("color: gray; font-style: italic;")
            layout.addRow("", info_label)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
        
        self.setLayout(layout)
    
    def save_between_cursors(self) -> bool:
        """Check if should save only between cursors"""
        return self.save_between_cursors_check.isChecked()


class TraceColorDialog(QDialog):
    """Dialog for trace color settings"""
    def __init__(self, parent=None, channel0_color: str = 'k', channel1_color: str = 'k'):
        super().__init__(parent)
        self.setWindowTitle("Trace Color Settings")
        self.setModal(True)
        
        layout = QVBoxLayout()
        
        # Info label
        info_label = QLabel("Select colors for trace plotting:")
        layout.addWidget(info_label)
        
        # Channel 0 color
        ch0_layout = QHBoxLayout()
        ch0_layout.addWidget(QLabel("Channel 0:"))
        self.ch0_color_btn = QPushButton()
        self.ch0_color_btn.setFixedSize(50, 30)
        self.ch0_color = self._string_to_qcolor(channel0_color)
        self._update_color_button(self.ch0_color_btn, self.ch0_color)
        self.ch0_color_btn.clicked.connect(lambda: self._pick_color('ch0'))
        ch0_layout.addWidget(self.ch0_color_btn)
        ch0_layout.addStretch()
        layout.addLayout(ch0_layout)
        
        # Channel 1 color
        ch1_layout = QHBoxLayout()
        ch1_layout.addWidget(QLabel("Channel 1:"))
        self.ch1_color_btn = QPushButton()
        self.ch1_color_btn.setFixedSize(50, 30)
        self.ch1_color = self._string_to_qcolor(channel1_color)
        self._update_color_button(self.ch1_color_btn, self.ch1_color)
        self.ch1_color_btn.clicked.connect(lambda: self._pick_color('ch1'))
        ch1_layout.addWidget(self.ch1_color_btn)
        ch1_layout.addStretch()
        layout.addLayout(ch1_layout)
        
        # Preset colors
        preset_layout = QVBoxLayout()
        preset_layout.addWidget(QLabel("Preset Colors:"))
        preset_buttons = QHBoxLayout()
        preset_colors = [('Black', 'k'), ('Red', 'r'), ('Blue', 'b'), ('Green', 'g'), 
                        ('Cyan', 'c'), ('Magenta', 'm'), ('Yellow', 'y'), ('Gray', 'gray')]
        for name, color_code in preset_colors:
            btn = QPushButton(name)
            btn.setMaximumWidth(70)
            btn.clicked.connect(lambda checked, cc=color_code: self._set_both_colors(cc))
            preset_buttons.addWidget(btn)
        preset_layout.addLayout(preset_buttons)
        layout.addLayout(preset_layout)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
        self.setLayout(layout)
    
    def _string_to_qcolor(self, color_str: str) -> QColor:
        """Convert color string to QColor"""
        color_map = {
            'k': QColor(0, 0, 0),
            'r': QColor(255, 0, 0),
            'b': QColor(0, 0, 255),
            'g': QColor(0, 128, 0),
            'c': QColor(0, 255, 255),
            'm': QColor(255, 0, 255),
            'y': QColor(255, 255, 0),
            'gray': QColor(128, 128, 128),
        }
        return color_map.get(color_str, QColor(0, 0, 0))
    
    def _qcolor_to_string(self, color: QColor):
        """Convert QColor to color string or tuple for pyqtgraph"""
        r, g, b = color.red(), color.green(), color.blue()
        # Check for common colors
        if r == 0 and g == 0 and b == 0:
            return 'k'
        elif r == 255 and g == 0 and b == 0:
            return 'r'
        elif r == 0 and g == 0 and b == 255:
            return 'b'
        elif r == 0 and g == 128 and b == 0:
            return 'g'
        elif r == 0 and g == 255 and b == 255:
            return 'c'
        elif r == 255 and g == 0 and b == 255:
            return 'm'
        elif r == 255 and g == 255 and b == 0:
            return 'y'
        elif r == 128 and g == 128 and b == 128:
            return 'gray'
        else:
            # Return as RGB tuple for pyqtgraph (values 0-255)
            return (r, g, b)
    
    def _update_color_button(self, btn: QPushButton, color: QColor):
        """Update button to show current color"""
        btn.setStyleSheet(f"background-color: rgb({color.red()}, {color.green()}, {color.blue()})")
    
    def _pick_color(self, channel: str):
        """Open color picker dialog"""
        current_color = self.ch0_color if channel == 'ch0' else self.ch1_color
        color = QColorDialog.getColor(current_color, self, f"Select Color for {channel.upper()}")
        if color.isValid():
            if channel == 'ch0':
                self.ch0_color = color
                self._update_color_button(self.ch0_color_btn, color)
            else:
                self.ch1_color = color
                self._update_color_button(self.ch1_color_btn, color)
    
    def _set_both_colors(self, color_code: str):
        """Set both channels to the same preset color"""
        color = self._string_to_qcolor(color_code)
        self.ch0_color = color
        self.ch1_color = color
        self._update_color_button(self.ch0_color_btn, color)
        self._update_color_button(self.ch1_color_btn, color)
    
    def get_channel0_color(self):
        """Get Channel 0 color"""
        return self._qcolor_to_string(self.ch0_color)
    
    def get_channel1_color(self):
        """Get Channel 1 color"""
        return self._qcolor_to_string(self.ch1_color)


class FilterDialog(QDialog):
    """Dialog for filter parameters"""
    def __init__(self, parent=None, sample_rate: float = 10000.0):
        super().__init__(parent)
        self.setWindowTitle("Gaussian Lowpass Filter")
        self.setModal(True)
        
        layout = QFormLayout()
        
        self.cutoff_spin = QDoubleSpinBox()
        self.cutoff_spin.setRange(0.1, sample_rate / 2)
        self.cutoff_spin.setValue(1000.0)
        self.cutoff_spin.setSuffix(" Hz")
        self.cutoff_spin.setDecimals(1)
        layout.addRow("Cutoff Frequency:", self.cutoff_spin)
        
        # Channel selection
        self.channel_combo = QComboBox()
        self.channel_combo.addItems(["Channel 0", "Channel 1", "Both Channels"])
        layout.addRow("Apply to:", self.channel_combo)
        
        # Filter between cursors only option
        self.filter_between_cursors_check = QCheckBox()
        self.filter_between_cursors_check.setChecked(False)
        layout.addRow("Filter between cursors only:", self.filter_between_cursors_check)
        
        # Info label
        info_label = QLabel("Filters the currently displayed sweep data.")
        info_label.setStyleSheet("color: gray; font-style: italic;")
        layout.addRow("", info_label)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
        
        self.setLayout(layout)
    
    def get_cutoff(self) -> float:
        """Get cutoff frequency"""
        return self.cutoff_spin.value()
    
    def get_channel(self) -> int:
        """Get selected channel: 0 for Ch0, 1 for Ch1, -1 for both"""
        idx = self.channel_combo.currentIndex()
        return idx if idx < 2 else -1
    
    def filter_between_cursors_only(self) -> bool:
        """Check if filter should only be applied between cursors"""
        return self.filter_between_cursors_check.isChecked()


class BaselineCorrectionDialog(QDialog):
    """Dialog for baseline correction"""
    def __init__(self, parent=None, cursor1_y_ch0=None, cursor1_y_ch1=None):
        super().__init__(parent)
        self.setWindowTitle("Baseline Correction")
        self.setModal(True)
        
        layout = QVBoxLayout()
        
        info_label = QLabel(
            "Set the baseline (0 pA) using Cursor 1's Y value, or enter a manual offset value.\n"
            "The baseline offset will be applied to shift the data so the selected level becomes zero."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        form_layout = QFormLayout()
        
        self.offset_spin = QDoubleSpinBox()
        self.offset_spin.setRange(-1e6, 1e6)
        self.offset_spin.setDecimals(6)
        
        # Set initial value from cursor 1 if available
        if cursor1_y_ch0 is not None:
            self.offset_spin.setValue(cursor1_y_ch0)
        else:
            self.offset_spin.setValue(0.0)
        
        form_layout.addRow("Baseline Offset:", self.offset_spin)
        
        self.channel_combo = QComboBox()
        self.channel_combo.addItems(["Channel 0", "Channel 1", "Both Channels"])
        form_layout.addRow("Apply to:", self.channel_combo)
        
        # Use cursor 1 button
        use_cursor_btn = QPushButton("Use Cursor 1 Value")
        use_cursor_btn.clicked.connect(lambda: self._use_cursor1_value(cursor1_y_ch0, cursor1_y_ch1))
        form_layout.addRow("", use_cursor_btn)
        
        # Status label
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: blue; font-style: italic;")
        if cursor1_y_ch0 is not None:
            ch0_text = f"Cursor 1 Ch0: {cursor1_y_ch0:.6f}"
            if cursor1_y_ch1 is not None:
                ch1_text = f" | Ch1: {cursor1_y_ch1:.6f}"
                self.status_label.setText(ch0_text + ch1_text)
            else:
                self.status_label.setText(ch0_text)
        form_layout.addRow("", self.status_label)
        
        layout.addLayout(form_layout)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
        self.setLayout(layout)
    
    def _use_cursor1_value(self, cursor1_y_ch0, cursor1_y_ch1):
        """Set offset from cursor 1 value"""
        channel = self.channel_combo.currentIndex()
        if channel == 0 and cursor1_y_ch0 is not None:
            self.offset_spin.setValue(cursor1_y_ch0)
            self.status_label.setText(f"Using Cursor 1 Ch0 value: {cursor1_y_ch0:.6f}")
        elif channel == 1 and cursor1_y_ch1 is not None:
            self.offset_spin.setValue(cursor1_y_ch1)
            self.status_label.setText(f"Using Cursor 1 Ch1 value: {cursor1_y_ch1:.6f}")
        elif channel == 2:  # Both channels
            if cursor1_y_ch0 is not None:
                self.offset_spin.setValue(cursor1_y_ch0)
                self.status_label.setText(f"Using Cursor 1 Ch0 value: {cursor1_y_ch0:.6f}")
            else:
                self.status_label.setText("Cursor 1 not available")
        else:
            self.status_label.setText("Cursor 1 not available for selected channel")
    
    def get_offset(self) -> float:
        """Get the baseline offset value"""
        return self.offset_spin.value()
    
    def get_channel(self) -> int:
        """Get selected channel (0, 1, or -1 for both)"""
        index = self.channel_combo.currentIndex()
        if index == 0:
            return 0
        elif index == 1:
            return 1
        else:
            return -1  # Both


class ABFViewerMainWindow(QMainWindow):
    """Main application window"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Synapse ABF Viewer")
        self.setGeometry(100, 100, 1400, 900)
        
        # Initialize handler
        self.abf_handler = ABFHandler()
        
        # UI state
        self.current_file_path: Optional[str] = None
        self.peaks: List[Peak] = []
        self.measurements_table: Optional[MeasurementsTableDialog] = None
        self.statistics_table: Optional[StatisticsTableDialog] = None
        self.peaks_table: Optional[PeaksTableDialog] = None
        self.blocks_table: Optional[BlocksTableDialog] = None
        self.detected_blocks: List[Dict] = []  # Store detected blocks for marker updates
        self.baseline_offset_ch0: float = 0.0
        self.baseline_offset_ch1: float = 0.0
        
        # Filter state - store actual filtered data arrays (None means use original data)
        self.filtered_data_ch0: Optional[np.ndarray] = None
        self.filtered_data_ch1: Optional[np.ndarray] = None
        self.filtered_time_ch0: Optional[np.ndarray] = None  # Store time array for filtered data
        self.filtered_time_ch1: Optional[np.ndarray] = None
        
        # Trace color settings (default black)
        self.trace_color_ch0: str = 'k'
        self.trace_color_ch1: str = 'k'
        
        # Create UI
        self._create_menu_bar()
        self._create_toolbar()
        self._create_main_widget()
        self._create_status_bar()
        
        # Update UI
        self._update_ui()
    
    def _create_menu_bar(self):
        """Create menu bar"""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("&File")
        
        open_action = QAction("&Open...", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.open_file)
        file_menu.addAction(open_action)
        
        file_menu.addSeparator()
        
        save_action = QAction("&Save As...", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self.save_as_abf)
        file_menu.addAction(save_action)
        
        export_action = QAction("&Export Data...", self)
        export_action.triggered.connect(self.export_data)
        file_menu.addAction(export_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Analysis menu
        analysis_menu = menubar.addMenu("&Analysis")
        
        cursor1_action = QAction("Cursor &1", self)
        cursor1_action.setShortcut("Ctrl+1")
        cursor1_action.setCheckable(True)
        cursor1_action.toggled.connect(self.toggle_cursor1)
        analysis_menu.addAction(cursor1_action)
        
        cursor2_action = QAction("Cursor &2", self)
        cursor2_action.setShortcut("Ctrl+2")
        cursor2_action.setCheckable(True)
        cursor2_action.toggled.connect(self.toggle_cursor2)
        analysis_menu.addAction(cursor2_action)
        
        measurement_action = QAction("&Add Measurement", self)
        measurement_action.setShortcut("Ctrl+M")
        measurement_action.triggered.connect(self.add_measurement)
        analysis_menu.addAction(measurement_action)
        
        measurements_table_action = QAction("&Measurements Table...", self)
        measurements_table_action.triggered.connect(self.show_measurements_table)
        analysis_menu.addAction(measurements_table_action)
        
        lock_cursors_action = QAction("&Lock Cursors", self)
        lock_cursors_action.setShortcut("Ctrl+L")
        lock_cursors_action.setCheckable(True)
        lock_cursors_action.toggled.connect(self.toggle_lock_cursors)
        analysis_menu.addAction(lock_cursors_action)
        
        analysis_menu.addSeparator()
        
        baseline_correction_action = QAction("&Baseline Correction...", self)
        baseline_correction_action.triggered.connect(self.baseline_correction)
        analysis_menu.addAction(baseline_correction_action)
        
        filter_action = QAction("Apply &Filter...", self)
        filter_action.triggered.connect(self.apply_filter)
        analysis_menu.addAction(filter_action)
        
        analysis_menu.addSeparator()
        
        peak_detection_action = QAction("&Peak Detection...", self)
        peak_detection_action.triggered.connect(self.detect_peaks)
        analysis_menu.addAction(peak_detection_action)
        
        add_statistics_action = QAction("&Add Statistics", self)
        add_statistics_action.setShortcut("Ctrl+T")  # Changed from Ctrl+S to avoid conflict with Save
        add_statistics_action.triggered.connect(self.add_statistics)
        analysis_menu.addAction(add_statistics_action)
        
        statistics_table_action = QAction("&Statistics Table...", self)
        statistics_table_action.triggered.connect(self.show_statistics_table)
        analysis_menu.addAction(statistics_table_action)
        
        peaks_table_action = QAction("&Peaks Table...", self)
        peaks_table_action.triggered.connect(self.show_peaks_table)
        analysis_menu.addAction(peaks_table_action)
        
        block_detection_action = QAction("&Detect Blocks...", self)
        block_detection_action.triggered.connect(self.detect_blocks)
        analysis_menu.addAction(block_detection_action)
        
        analysis_menu.addSeparator()
        
        clear_analysis_action = QAction("Clear &Analysis", self)
        clear_analysis_action.triggered.connect(self.clear_analysis)
        analysis_menu.addAction(clear_analysis_action)
        
        insert_detection_action = QAction("&Detect Inserts...", self)
        insert_detection_action.triggered.connect(self.detect_inserts)
        analysis_menu.addAction(insert_detection_action)
        
        # View menu
        view_menu = menubar.addMenu("&View")
        
        show_command_action = QAction("Show &Command Waveform", self)
        show_command_action.setCheckable(True)
        show_command_action.toggled.connect(self.toggle_command_waveform)
        view_menu.addAction(show_command_action)
        
        view_menu.addSeparator()
        
        trace_color_action = QAction("Trace &Colors...", self)
        trace_color_action.triggered.connect(self.change_trace_colors)
        view_menu.addAction(trace_color_action)
        
        show_grid_action = QAction("Show &Grid", self)
        show_grid_action.setCheckable(True)
        show_grid_action.setChecked(True)
        show_grid_action.toggled.connect(self.toggle_grid)
        view_menu.addAction(show_grid_action)
        
        self.show_grid_action = show_grid_action
        
        # Store actions for later access
        self.cursor1_action = cursor1_action
        self.cursor2_action = cursor2_action
        self.show_command_action = show_command_action
        self.lock_cursors_action = lock_cursors_action
    
    def _create_toolbar(self):
        """Create toolbar"""
        toolbar = QToolBar("Main Toolbar")
        self.addToolBar(toolbar)
        
        open_action = QAction("Open", self)
        open_action.triggered.connect(self.open_file)
        toolbar.addAction(open_action)
        
        toolbar.addSeparator()
        
        prev_file_action = QAction("◄ Prev File", self)
        prev_file_action.triggered.connect(self.previous_file)
        toolbar.addAction(prev_file_action)
        
        next_file_action = QAction("Next File ►", self)
        next_file_action.triggered.connect(self.next_file)
        toolbar.addAction(next_file_action)
        
        toolbar.addSeparator()
        
        prev_sweep_action = QAction("◄ Prev Sweep", self)
        prev_sweep_action.triggered.connect(self.previous_sweep)
        toolbar.addAction(prev_sweep_action)
        
        next_sweep_action = QAction("Next Sweep ►", self)
        next_sweep_action.triggered.connect(self.next_sweep)
        toolbar.addAction(next_sweep_action)
    
    def _create_main_widget(self):
        """Create main widget layout"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout(central_widget)
        
        # Left panel - controls
        left_panel = self._create_control_panel()
        
        # Center - plot area with dual channels
        plot_container = QWidget()
        plot_layout = QVBoxLayout(plot_container)
        
        # Create dual-channel plot widget
        self.plot_widget = DualChannelPlotWidget()
        
        # Connect cursor signals from both plots
        self.plot_widget.plot0.cursor1_set.connect(self._on_cursor1_set)
        self.plot_widget.plot0.cursor2_set.connect(self._on_cursor2_set)
        self.plot_widget.plot1.cursor1_set.connect(self._on_cursor1_set)
        self.plot_widget.plot1.cursor2_set.connect(self._on_cursor2_set)
        
        plot_layout.addWidget(self.plot_widget, 1)
        
        # Create info panel below plot
        info_panel = self._create_info_panel()
        plot_layout.addWidget(info_panel, 0)
        
        # Splitter for resizable panels
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(plot_container)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 1100])
        
        main_layout.addWidget(splitter)
    
    def _create_control_panel(self) -> QWidget:
        """Create left control panel"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        # File info group
        file_group = QGroupBox("File Info")
        file_layout = QVBoxLayout()
        self.file_info_label = QLabel("No file loaded")
        self.file_info_label.setWordWrap(True)
        file_layout.addWidget(self.file_info_label)
        file_group.setLayout(file_layout)
        layout.addWidget(file_group)
        
        # Sweep controls
        sweep_group = QGroupBox("Sweep Controls")
        sweep_layout = QVBoxLayout()
        
        sweep_layout.addWidget(QLabel("Sweep:"))
        self.sweep_spin = QSpinBox()
        self.sweep_spin.setMinimum(0)
        self.sweep_spin.setMaximum(0)
        self.sweep_spin.valueChanged.connect(self.on_sweep_changed)
        sweep_layout.addWidget(self.sweep_spin)
        
        # Note: Both channels shown simultaneously
        info_label = QLabel("Both channels displayed")
        info_label.setStyleSheet("color: gray; font-style: italic;")
        sweep_layout.addWidget(info_label)
        
        sweep_group.setLayout(sweep_layout)
        layout.addWidget(sweep_group)
        
        # Analysis controls
        analysis_group = QGroupBox("Analysis")
        analysis_layout = QVBoxLayout()
        
        # Reorganized button order
        self.cursor1_btn = QPushButton("Enable Cursor 1 (red)")
        self.cursor1_btn.setCheckable(True)
        self.cursor1_btn.toggled.connect(self.toggle_cursor1)
        analysis_layout.addWidget(self.cursor1_btn)
        
        self.cursor2_btn = QPushButton("Enable Cursor 2 (blue)")
        self.cursor2_btn.setCheckable(True)
        self.cursor2_btn.toggled.connect(self.toggle_cursor2)
        analysis_layout.addWidget(self.cursor2_btn)
        
        lock_btn = QPushButton("Lock Cursors")
        lock_btn.setCheckable(True)
        lock_btn.toggled.connect(self.toggle_lock_cursors)
        analysis_layout.addWidget(lock_btn)
        
        measure_btn = QPushButton("Add Measurement")
        measure_btn.clicked.connect(self.add_measurement)
        analysis_layout.addWidget(measure_btn)
        
        stats_btn = QPushButton("Add Statistics")
        stats_btn.clicked.connect(self.add_statistics)
        analysis_layout.addWidget(stats_btn)
        
        show_measurements_btn = QPushButton("Show Measurements Table")
        show_measurements_btn.clicked.connect(self.show_measurements_table)
        analysis_layout.addWidget(show_measurements_btn)
        
        show_stats_btn = QPushButton("Show Statistics Table")
        show_stats_btn.clicked.connect(self.show_statistics_table)
        analysis_layout.addWidget(show_stats_btn)
        
        blocks_btn = QPushButton("Detect Blocks")
        blocks_btn.clicked.connect(self.detect_blocks)
        analysis_layout.addWidget(blocks_btn)
        
        show_blocks_btn = QPushButton("Show Blocks Table")
        show_blocks_btn.clicked.connect(self.show_blocks_table)
        analysis_layout.addWidget(show_blocks_btn)
        
        # Add separator line
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        analysis_layout.addWidget(separator)
        
        clear_analysis_btn = QPushButton("Clear Analysis")
        clear_analysis_btn.clicked.connect(self.clear_analysis)
        analysis_layout.addWidget(clear_analysis_btn)
        
        baseline_btn = QPushButton("Baseline Correction")
        baseline_btn.clicked.connect(self.baseline_correction)
        analysis_layout.addWidget(baseline_btn)
        
        filter_btn = QPushButton("Apply Filter")
        filter_btn.clicked.connect(self.apply_filter)
        analysis_layout.addWidget(filter_btn)
        
        analysis_group.setLayout(analysis_layout)
        layout.addWidget(analysis_group)
        
        layout.addStretch()
        
        return panel
    
    def _create_info_panel(self) -> QWidget:
        """Create info panel below plot"""
        panel = QWidget()
        layout = QHBoxLayout(panel)
        
        self.status_label = QLabel("Ready")
        layout.addWidget(self.status_label)
        
        self.cursor_label = QLabel("")
        layout.addWidget(self.cursor_label)
        
        layout.addStretch()
        
        return panel
    
    def _create_status_bar(self):
        """Create status bar"""
        self.statusBar().showMessage("Ready")
    
    def _update_ui(self):
        """Update UI based on current state"""
        if not self.abf_handler.is_loaded:
            self.file_info_label.setText("No file loaded")
            self.sweep_spin.setEnabled(False)
            self.statusBar().showMessage("No file loaded")
            return
        
        # Update file info
        info = self.abf_handler.get_file_info()
        info_text = f"<b>File:</b> {Path(info['filename']).name}<br>"
        info_text += f"<b>Protocol:</b> {info['protocol']}<br>"
        info_text += f"<b>Sweeps:</b> {info['sweeps']}<br>"
        info_text += f"<b>Channels:</b> {info['channels']}<br>"
        info_text += f"<b>Sample Rate:</b> {info['sample_rate']:.0f} Hz"
        self.file_info_label.setText(info_text)
        
        # Update sweep controls
        self.sweep_spin.setMaximum(self.abf_handler.sweep_count - 1)
        self.sweep_spin.setValue(self.abf_handler.current_sweep)
        self.sweep_spin.setEnabled(True)
        
        # Update plot
        self._update_plot()
        
        # Reset plot views to auto-range (show all data) after plot is drawn
        QTimer.singleShot(50, self._reset_plot_views)
        
        # Update status
        self.statusBar().showMessage(f"Loaded: {Path(info['filename']).name}")
    
    def _update_plot(self):
        """Update plot with current sweep - both channels displayed"""
        if not self.abf_handler.is_loaded:
            return
        
        # Get sweeps for both channels
        channel0_sweep = None
        channel1_sweep = None
        channel0_units = ""
        channel1_units = ""
        
        if self.abf_handler.channel_count > 0:
            channel0_sweep_orig = self.abf_handler.get_sweep(
                self.abf_handler.current_sweep, 0
            )
            if channel0_sweep_orig:
                # Use filtered data if available, otherwise use original
                if self.filtered_data_ch0 is not None and self.filtered_time_ch0 is not None:
                    # Create modified SweepData with filtered data
                    channel0_sweep = SweepData(
                        sweep_number=channel0_sweep_orig.sweep_number,
                        channel=channel0_sweep_orig.channel,
                        time=self.filtered_time_ch0,
                        data=self.filtered_data_ch0,
                        command=channel0_sweep_orig.command,
                        sample_rate=channel0_sweep_orig.sample_rate
                    )
                else:
                    channel0_sweep = channel0_sweep_orig
                
                info = self.abf_handler.get_protocol_info()
                if len(info.adc_units) > 0:
                    channel0_units = info.adc_units[0]
        
        if self.abf_handler.channel_count > 1:
            channel1_sweep_orig = self.abf_handler.get_sweep(
                self.abf_handler.current_sweep, 1
            )
            if channel1_sweep_orig:
                # Use filtered data if available, otherwise use original
                if self.filtered_data_ch1 is not None and self.filtered_time_ch1 is not None:
                    # Create modified SweepData with filtered data
                    channel1_sweep = SweepData(
                        sweep_number=channel1_sweep_orig.sweep_number,
                        channel=channel1_sweep_orig.channel,
                        time=self.filtered_time_ch1,
                        data=self.filtered_data_ch1,
                        command=channel1_sweep_orig.command,
                        sample_rate=channel1_sweep_orig.sample_rate
                    )
                else:
                    channel1_sweep = channel1_sweep_orig
                
                info = self.abf_handler.get_protocol_info()
                if len(info.adc_units) > 1:
                    channel1_units = info.adc_units[1]
        
        show_command = self.show_command_action.isChecked()
        # Plot without filter parameters since we're using pre-filtered data
        self.plot_widget.plot_sweeps(channel0_sweep, channel1_sweep,
                                    channel0_units, channel1_units,
                                    show_command,
                                    self.baseline_offset_ch0,
                                    self.baseline_offset_ch1)
        
        # Apply trace colors
        self.plot_widget.plot0.set_trace_color(self.trace_color_ch0)
        self.plot_widget.plot1.set_trace_color(self.trace_color_ch1)
        
        # Apply grid visibility
        if hasattr(self, 'show_grid_action') and self.show_grid_action:
            self.plot_widget.plot0.set_grid_visible(self.show_grid_action.isChecked())
            self.plot_widget.plot1.set_grid_visible(self.show_grid_action.isChecked())
        
        # Update status label
        self.status_label.setText(
            f"Sweep {self.abf_handler.current_sweep + 1}/{self.abf_handler.sweep_count} | "
            f"Channels: {self.abf_handler.channel_count}"
        )
    
    def open_file(self):
        """Open ABF file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open ABF File", "", "ABF Files (*.abf);;All Files (*)"
        )
        
        if file_path:
            if self.abf_handler.load_file(file_path):
                # Reset state first (before setting sweep)
                self._reset_viewer_state()
                # Reset sweep to first sweep (0) after file is loaded
                if self.abf_handler.is_loaded:
                    self.abf_handler.set_current_sweep(0)
                self.current_file_path = file_path
                # Update UI (which will update plot with sweep 0)
                self._update_ui()
            else:
                QMessageBox.critical(self, "Error", "Failed to load ABF file.")
    
    def _get_abf_files_in_directory(self) -> List[str]:
        """Get list of all ABF files in the current file's directory, sorted alphabetically"""
        if not self.current_file_path:
            return []
        
        file_dir = Path(self.current_file_path).parent
        abf_files = sorted(file_dir.glob("*.abf"), key=lambda p: p.name.lower())
        return [str(f) for f in abf_files]
    
    def previous_file(self):
        """Open previous ABF file in the folder"""
        if not self.current_file_path:
            QMessageBox.warning(self, "Warning", "No file is currently open.")
            return
        
        abf_files = self._get_abf_files_in_directory()
        if len(abf_files) == 0:
            QMessageBox.warning(self, "Warning", "No ABF files found in directory.")
            return
        
        try:
            current_index = abf_files.index(self.current_file_path)
            if current_index > 0:
                prev_file = abf_files[current_index - 1]
                self._load_file_direct(prev_file)
            else:
                QMessageBox.information(self, "Info", "Already at the first file in the folder.")
        except ValueError:
            # Current file not in list (shouldn't happen, but handle gracefully)
            QMessageBox.warning(self, "Warning", "Current file not found in directory list.")
    
    def next_file(self):
        """Open next ABF file in the folder"""
        if not self.current_file_path:
            QMessageBox.warning(self, "Warning", "No file is currently open.")
            return
        
        abf_files = self._get_abf_files_in_directory()
        if len(abf_files) == 0:
            QMessageBox.warning(self, "Warning", "No ABF files found in directory.")
            return
        
        try:
            current_index = abf_files.index(self.current_file_path)
            if current_index < len(abf_files) - 1:
                next_file = abf_files[current_index + 1]
                self._load_file_direct(next_file)
            else:
                QMessageBox.information(self, "Info", "Already at the last file in the folder.")
        except ValueError:
            # Current file not in list (shouldn't happen, but handle gracefully)
            QMessageBox.warning(self, "Warning", "Current file not found in directory list.")
    
    def _load_file_direct(self, file_path: str):
        """Load a file directly without showing file dialog (used by previous/next file)"""
        if self.abf_handler.load_file(file_path):
            # Reset state first (before setting sweep)
            self._reset_viewer_state()
            # Reset sweep to first sweep (0) after file is loaded
            if self.abf_handler.is_loaded:
                self.abf_handler.set_current_sweep(0)
            self.current_file_path = file_path
            # Update UI (which will update plot with sweep 0)
            self._update_ui()
        else:
            QMessageBox.critical(self, "Error", f"Failed to load ABF file:\n{file_path}")
    
    def _reset_viewer_state(self):
        """Reset all viewer state when loading a new file - complete reset to initial state"""
        # Reset baseline offsets
        self.baseline_offset_ch0 = 0.0
        self.baseline_offset_ch1 = 0.0
        
        # Reset filter state
        self.filtered_data_ch0 = None
        self.filtered_data_ch1 = None
        self.filtered_time_ch0 = None
        self.filtered_time_ch1 = None
        
        # Clear peaks
        self.peaks = []
        
        # Reset trace colors to default (black)
        self.trace_color_ch0 = 'k'
        self.trace_color_ch1 = 'k'
        
        # Reset grid visibility
        if self.show_grid_action:
            self.show_grid_action.setChecked(True)
        
        # Disable cursors and unlock
        if self.plot_widget.plot0.cursor1_enabled:
            self.plot_widget.plot0.disable_cursor1()
            self.plot_widget.plot1.disable_cursor1()
        if self.plot_widget.plot0.cursor2_enabled:
            self.plot_widget.plot0.disable_cursor2()
            self.plot_widget.plot1.disable_cursor2()
        
        # Unlock cursors
        self.plot_widget.plot0.set_cursors_locked(False)
        self.plot_widget.plot1.set_cursors_locked(False)
        
        # Update cursor button states
        self.cursor1_btn.setChecked(False)
        self.cursor2_btn.setChecked(False)
        if hasattr(self, 'cursor1_action'):
            self.cursor1_action.setChecked(False)
        if hasattr(self, 'cursor2_action'):
            self.cursor2_action.setChecked(False)
        if hasattr(self, 'lock_cursors_action'):
            self.lock_cursors_action.setChecked(False)
        
        # Clear measurements table
        if self.measurements_table is not None:
            self.measurements_table.clear_all()
        
        # Clear statistics table
        if self.statistics_table is not None:
            self.statistics_table.clear_all()
        
        # Clear peaks table
        if self.peaks_table is not None:
            self.peaks_table.clear_all()
        
        # Clear blocks table
        if self.blocks_table is not None:
            self.blocks_table.clear_all()
        
        # Clear detected blocks
        self.detected_blocks = []
        
        # Clear block markers from plots
        self.plot_widget.plot0.clear_block_markers()
        
        # Clear cursor label and status
        self.cursor_label.setText("")
        self.status_label.setText("Ready")
    
    def _reset_plot_views(self):
        """Reset plot views to auto-range showing all data"""
        # Auto-range both plots to show all data
        if self.plot_widget.plot0.data_plot is not None:
            self.plot_widget.plot0.getViewBox().autoRange()
        if self.plot_widget.plot1.data_plot is not None:
            self.plot_widget.plot1.getViewBox().autoRange()
    
    def on_sweep_changed(self, value: int):
        """Handle sweep change"""
        if self.abf_handler.is_loaded:
            self.abf_handler.set_current_sweep(value)
            # Reset filtered data when changing sweeps (filters are per-sweep)
            self.filtered_data_ch0 = None
            self.filtered_data_ch1 = None
            self.filtered_time_ch0 = None
            self.filtered_time_ch1 = None
            self._update_plot()
            
            # Update block markers for new sweep
            if self.detected_blocks:
                current_sweep_blocks = [b for b in self.detected_blocks if b.get('sweep_number') == value]
                if current_sweep_blocks:
                    self.plot_widget.plot0.mark_blocks(current_sweep_blocks)
                else:
                    self.plot_widget.plot0.clear_block_markers()
    
    def previous_sweep(self):
        """Go to previous sweep"""
        if self.abf_handler.is_loaded and self.abf_handler.current_sweep > 0:
            self.sweep_spin.setValue(self.abf_handler.current_sweep - 1)
    
    def next_sweep(self):
        """Go to next sweep"""
        if self.abf_handler.is_loaded:
            if self.abf_handler.current_sweep < self.abf_handler.sweep_count - 1:
                self.sweep_spin.setValue(self.abf_handler.current_sweep + 1)
    
    def toggle_cursor1(self, enabled: bool):
        """Toggle cursor 1 on both plots"""
        self.cursor1_action.setChecked(enabled)
        self.cursor1_btn.setChecked(enabled)
        if enabled:
            self.plot_widget.plot0.enable_cursor1()
            self.plot_widget.plot1.enable_cursor1()
        else:
            self.plot_widget.plot0.disable_cursor1()
            self.plot_widget.plot1.disable_cursor1()
    
    def toggle_cursor2(self, enabled: bool):
        """Toggle cursor 2 on both plots"""
        self.cursor2_action.setChecked(enabled)
        self.cursor2_btn.setChecked(enabled)
        if enabled:
            self.plot_widget.plot0.enable_cursor2()
            self.plot_widget.plot1.enable_cursor2()
        else:
            self.plot_widget.plot0.disable_cursor2()
            self.plot_widget.plot1.disable_cursor2()
    
    def toggle_command_waveform(self, show: bool):
        """Toggle command waveform display"""
        self._update_plot()
    
    def change_trace_colors(self):
        """Open dialog to change trace colors"""
        dialog = TraceColorDialog(self, self.trace_color_ch0, self.trace_color_ch1)
        if dialog.exec() == QDialog.Accepted:
            self.trace_color_ch0 = dialog.get_channel0_color()
            self.trace_color_ch1 = dialog.get_channel1_color()
            # Update plots if data is loaded
            if self.abf_handler.is_loaded:
                self.plot_widget.plot0.set_trace_color(self.trace_color_ch0)
                self.plot_widget.plot1.set_trace_color(self.trace_color_ch1)
    
    def toggle_grid(self, visible: bool):
        """Toggle grid visibility on both plots"""
        self.plot_widget.plot0.set_grid_visible(visible)
        self.plot_widget.plot1.set_grid_visible(visible)
    
    def _on_cursor1_set(self, x: float, y: float):
        """Handle cursor 1 position"""
        self.cursor_label.setText(f"C1: ({x:.4f} s, {y:.4f})")
    
    def _on_cursor2_set(self, x: float, y: float):
        """Handle cursor 2 position"""
        # Get positions from plot 0 (they should be synchronized)
        x1, y1, x2, y2 = self.plot_widget.plot0.get_cursor_positions()
        if self.plot_widget.plot0.cursor1_enabled and self.plot_widget.plot0.cursor2_enabled:
            self.cursor_label.setText(
                f"C1: ({x1:.4f} s, {y1:.4f}) | C2: ({x2:.4f} s, {y2:.4f})"
            )
        else:
            self.cursor_label.setText(f"C2: ({x:.4f} s, {y:.4f})")
    
    def add_measurement(self):
        """Add measurement to table (Ctrl+M) - both channels"""
        if not self.plot_widget.plot0.cursor1_enabled or not self.plot_widget.plot0.cursor2_enabled:
            QMessageBox.warning(self, "Warning", "Please enable both cursors first.")
            return
        
        # Get cursor positions from both plots (X positions are synchronized)
        x1_ch0, y1_ch0, x2_ch0, y2_ch0 = self.plot_widget.plot0.get_cursor_positions()
        x1_ch1, y1_ch1, x2_ch1, y2_ch1 = self.plot_widget.plot1.get_cursor_positions()
        
        # Calculate measurements for both channels
        measurement_ch0 = AnalysisTools.calculate_measurement(x1_ch0, y1_ch0, x2_ch0, y2_ch0)
        measurement_ch1 = AnalysisTools.calculate_measurement(x1_ch1, y1_ch1, x2_ch1, y2_ch1) if self.abf_handler.channel_count > 1 else None
        
        # Get or create measurements table
        if self.measurements_table is None:
            self.measurements_table = MeasurementsTableDialog(self)
        
        # Ensure window is visible and brought to front
        self.measurements_table.show()
        self.measurements_table.raise_()
        self.measurements_table.activateWindow()
        if self.measurements_table.isMinimized():
            self.measurements_table.showNormal()
        
        # Add measurement to table (both channels)
        self.measurements_table.add_measurement(measurement_ch0, measurement_ch1)
    
    def show_measurements_table(self):
        """Show measurements table dialog"""
        if self.measurements_table is None:
            self.measurements_table = MeasurementsTableDialog(self)
        
        # Ensure window is visible and brought to front
        self.measurements_table.show()
        self.measurements_table.raise_()
        self.measurements_table.activateWindow()
        
        # If window was minimized, restore it
        if self.measurements_table.isMinimized():
            self.measurements_table.showNormal()
    
    def toggle_lock_cursors(self, locked: bool):
        """Toggle cursor locking"""
        self.plot_widget.plot0.set_cursors_locked(locked)
        self.plot_widget.plot1.set_cursors_locked(locked)
        self.lock_cursors_action.setChecked(locked)
    
    def baseline_correction(self):
        """Apply baseline correction"""
        # Get cursor 1 Y values from both plots (original data, not corrected)
        cursor1_y_ch0 = None
        cursor1_y_ch1 = None
        
        if self.plot_widget.plot0.cursor1_enabled and self.plot_widget.plot0.cursor1_line:
            # Get cursor 1 X position
            x1 = self.plot_widget.plot0.cursor1_line.value()
            # Get original data value at cursor 1 position (before baseline correction)
            sweep_ch0 = self.abf_handler.get_sweep(self.abf_handler.current_sweep, 0)
            if sweep_ch0:
                time_diff = np.abs(sweep_ch0.time - x1)
                if len(time_diff) > 0:
                    idx = np.argmin(time_diff)
                    if idx < len(sweep_ch0.data):
                        cursor1_y_ch0 = float(sweep_ch0.data[idx])
        
        if self.abf_handler.channel_count > 1:
            if self.plot_widget.plot1.cursor1_enabled and self.plot_widget.plot1.cursor1_line:
                # Get cursor 1 X position (synchronized with plot0)
                x1 = self.plot_widget.plot0.cursor1_line.value() if self.plot_widget.plot0.cursor1_line else None
                if x1 is not None:
                    sweep_ch1 = self.abf_handler.get_sweep(self.abf_handler.current_sweep, 1)
                    if sweep_ch1:
                        time_diff = np.abs(sweep_ch1.time - x1)
                        if len(time_diff) > 0:
                            idx = np.argmin(time_diff)
                            if idx < len(sweep_ch1.data):
                                cursor1_y_ch1 = float(sweep_ch1.data[idx])
        
        # Create dialog with cursor 1 values
        dialog = BaselineCorrectionDialog(self, cursor1_y_ch0, cursor1_y_ch1)
        
        if dialog.exec() == QDialog.Accepted:
            offset = dialog.get_offset()
            channel = dialog.get_channel()
            
            if channel == 0 or channel == -1:
                self.baseline_offset_ch0 = offset
            if channel == 1 or channel == -1:
                self.baseline_offset_ch1 = offset
            
            # Update plot with baseline correction
            self._update_plot()
    
    def apply_filter(self):
        """Apply Gaussian lowpass filter to data - filters are permanent and cumulative"""
        if not self.abf_handler.is_loaded:
            QMessageBox.warning(self, "Warning", "Please load a file first.")
            return
        
        # Get sample rate from current sweep
        sweep = self.abf_handler.get_sweep(self.abf_handler.current_sweep, 0)
        if not sweep:
            QMessageBox.warning(self, "Warning", "No data available to filter.")
            return
        
        sample_rate = sweep.sample_rate
        
        # Show filter dialog
        dialog = FilterDialog(self, sample_rate=sample_rate)
        
        if dialog.exec() == QDialog.Accepted:
            cutoff = dialog.get_cutoff()
            channel = dialog.get_channel()
            filter_between_cursors = dialog.filter_between_cursors_only()
            
            # Get cursor positions if filtering between cursors
            cursor_range = None
            if filter_between_cursors:
                # Check if cursors are enabled
                if not (self.plot_widget.plot0.cursor1_enabled and self.plot_widget.plot0.cursor2_enabled):
                    QMessageBox.warning(self, "Warning", "Please enable both cursors to filter between them.")
                    return
                
                # Get cursor positions
                x1, y1, x2, y2 = self.plot_widget.plot0.get_cursor_positions()
                cursor_range = (x1, x2)
            
            # Apply filter to channel 0
            if channel == 0 or channel == -1:
                sweep_ch0 = self.abf_handler.get_sweep(self.abf_handler.current_sweep, 0)
                if sweep_ch0:
                    # Get current data (filtered if exists, otherwise original)
                    if self.filtered_data_ch0 is not None:
                        current_data = self.filtered_data_ch0.copy()
                        current_time = self.filtered_time_ch0.copy()
                    else:
                        current_data = sweep_ch0.data.copy()
                        current_time = sweep_ch0.time.copy()
                    
                    # Apply filter
                    if filter_between_cursors and cursor_range:
                        # Filter only between cursors
                        x1, x2 = cursor_range
                        if x1 > x2:
                            x1, x2 = x2, x1
                        
                        mask = (current_time >= x1) & (current_time <= x2)
                        mask_indices = np.where(mask)[0]
                        
                        if len(mask_indices) > 0:
                            start_idx = int(mask_indices[0])
                            end_idx = int(mask_indices[-1] + 1)
                            
                            # Calculate padding
                            normalized_cutoff = cutoff / sample_rate
                            if normalized_cutoff < 0.5:
                                sigma_time = 0.1325 / normalized_cutoff
                                sigma_samples = sigma_time * sample_rate
                                padding_needed = int(6 * sigma_samples) + 10
                            else:
                                padding_needed = 100
                            
                            padding = min(padding_needed, start_idx, len(current_data) - end_idx)
                            if padding > 0:
                                padded_start = max(0, start_idx - padding)
                                padded_end = min(len(current_data), end_idx + padding)
                            else:
                                padded_start = start_idx
                                padded_end = end_idx
                            
                            padded_segment = current_data[padded_start:padded_end].copy()
                            filtered_padded = AnalysisTools.gaussian_lowpass_filter(
                                padded_segment, cutoff_freq=cutoff, sample_rate=sample_rate
                            )
                            
                            segment_start_in_padded = start_idx - padded_start
                            segment_end_in_padded = end_idx - padded_start
                            filtered_segment = filtered_padded[segment_start_in_padded:segment_end_in_padded]
                            
                            if len(filtered_segment) == (end_idx - start_idx):
                                current_data[start_idx:end_idx] = filtered_segment
                    else:
                        # Filter entire sweep
                        current_data = AnalysisTools.gaussian_lowpass_filter(
                            current_data, cutoff_freq=cutoff, sample_rate=sample_rate
                        )
                    
                    # Store filtered data
                    self.filtered_data_ch0 = current_data
                    self.filtered_time_ch0 = current_time
            
            # Apply filter to channel 1
            if channel == 1 or channel == -1:
                if self.abf_handler.channel_count > 1:
                    sweep_ch1 = self.abf_handler.get_sweep(self.abf_handler.current_sweep, 1)
                    if sweep_ch1:
                        # Get current data (filtered if exists, otherwise original)
                        if self.filtered_data_ch1 is not None:
                            current_data = self.filtered_data_ch1.copy()
                            current_time = self.filtered_time_ch1.copy()
                        else:
                            current_data = sweep_ch1.data.copy()
                            current_time = sweep_ch1.time.copy()
                        
                        # Apply filter (same logic as channel 0)
                        if filter_between_cursors and cursor_range:
                            x1, x2 = cursor_range
                            if x1 > x2:
                                x1, x2 = x2, x1
                            
                            mask = (current_time >= x1) & (current_time <= x2)
                            mask_indices = np.where(mask)[0]
                            
                            if len(mask_indices) > 0:
                                start_idx = int(mask_indices[0])
                                end_idx = int(mask_indices[-1] + 1)
                                
                                normalized_cutoff = cutoff / sample_rate
                                if normalized_cutoff < 0.5:
                                    sigma_time = 0.1325 / normalized_cutoff
                                    sigma_samples = sigma_time * sample_rate
                                    padding_needed = int(6 * sigma_samples) + 10
                                else:
                                    padding_needed = 100
                                
                                padding = min(padding_needed, start_idx, len(current_data) - end_idx)
                                if padding > 0:
                                    padded_start = max(0, start_idx - padding)
                                    padded_end = min(len(current_data), end_idx + padding)
                                else:
                                    padded_start = start_idx
                                    padded_end = end_idx
                                
                                padded_segment = current_data[padded_start:padded_end].copy()
                                filtered_padded = AnalysisTools.gaussian_lowpass_filter(
                                    padded_segment, cutoff_freq=cutoff, sample_rate=sample_rate
                                )
                                
                                segment_start_in_padded = start_idx - padded_start
                                segment_end_in_padded = end_idx - padded_start
                                filtered_segment = filtered_padded[segment_start_in_padded:segment_end_in_padded]
                                
                                if len(filtered_segment) == (end_idx - start_idx):
                                    current_data[start_idx:end_idx] = filtered_segment
                        else:
                            current_data = AnalysisTools.gaussian_lowpass_filter(
                                current_data, cutoff_freq=cutoff, sample_rate=sample_rate
                            )
                        
                        # Store filtered data
                        self.filtered_data_ch1 = current_data
                        self.filtered_time_ch1 = current_time
                elif channel == 1:
                    QMessageBox.warning(self, "Warning", "Channel 1 not available.")
                    return
            
            # Update plot with filter applied
            self._update_plot()
            
            # Show status message
            channel_text = "both channels" if channel == -1 else f"channel {channel}"
            cursor_text = " between cursors" if filter_between_cursors else ""
            self.status_label.setText(f"Filter applied: {cutoff:.1f} Hz cutoff to {channel_text}{cursor_text}")
    
    def detect_peaks(self):
        """Detect peaks in current sweep (channel 0) - between cursors if enabled"""
        if not self.abf_handler.is_loaded:
            QMessageBox.warning(self, "Warning", "Please load a file first.")
            return
        
        # Check if cursors are enabled - if so, only analyze between them
        use_cursors = (self.plot_widget.plot0.cursor1_enabled and 
                      self.plot_widget.plot0.cursor2_enabled)
        
        if use_cursors:
            x1, y1, x2, y2 = self.plot_widget.plot0.get_cursor_positions()
            if x1 > x2:
                x1, x2 = x2, x1
        else:
            QMessageBox.warning(self, "Warning", "Please enable both cursors to analyze data between them.")
            return
        
        # Show parameter dialog
        dialog = PeakDetectionDialog(self)
        if dialog.exec() == QDialog.Accepted:
            height = dialog.height_spin.value() if dialog.height_spin.value() != -1e6 else None
            distance = dialog.distance_spin.value()
            prominence = dialog.prominence_spin.value() if dialog.prominence_spin.value() > 0 else None
            find_max = dialog.find_max_check.isChecked()
            
            # Detect peaks in channel 0 (current channel)
            sweep = self.abf_handler.get_sweep(
                self.abf_handler.current_sweep,
                0  # Always use channel 0 for peak detection
            )
            
            if sweep:
                # Extract data between cursors
                if use_cursors:
                    mask = (sweep.time >= x1) & (sweep.time <= x2)
                    segment_data = sweep.data[mask]
                    segment_time = sweep.time[mask]
                    
                    if len(segment_data) == 0:
                        QMessageBox.warning(self, "Warning", "No data found between cursors.")
                        return
                    
                    # Find the starting index offset for proper peak indexing
                    start_idx = np.where(mask)[0][0] if np.any(mask) else 0
                else:
                    segment_data = sweep.data
                    segment_time = sweep.time
                    start_idx = 0
                
                # Detect peaks in the segment
                peaks = AnalysisTools.find_peaks(
                    segment_data, segment_time,
                    height=height, distance=distance,
                    prominence=prominence, find_max=find_max
                )
                
                # Adjust peak indices to match original data array
                # Note: The peaks are already marked with correct time values,
                # but we need to adjust the indices if we used a segment
                if use_cursors and len(peaks) > 0:
                    # Find indices in original data array based on time values
                    adjusted_peaks = []
                    for peak in peaks:
                        # Find closest index in original sweep data
                        time_diff = np.abs(sweep.time - peak.time)
                        original_idx = int(np.argmin(time_diff))
                        adjusted_peaks.append(Peak(
                            index=original_idx,
                            time=peak.time,
                            value=peak.value,
                            is_max=peak.is_max
                        ))
                    self.peaks = adjusted_peaks
                else:
                    self.peaks = peaks
                
                # Mark peaks on plot
                self.plot_widget.plot0.mark_peaks(self.peaks)
                
                # Add peaks to table
                if self.peaks_table is None:
                    self.peaks_table = PeaksTableDialog(self)
                
                # Ensure window is visible and brought to front
                self.peaks_table.show()
                self.peaks_table.raise_()
                self.peaks_table.activateWindow()
                if self.peaks_table.isMinimized():
                    self.peaks_table.showNormal()
                
                # Add peaks to table with current sweep number
                self.peaks_table.add_peaks(self.peaks, self.abf_handler.current_sweep + 1)
                
                # Show results
                QMessageBox.information(
                    self, "Peak Detection",
                    f"Found {len(self.peaks)} {'peaks' if find_max else 'troughs'} in Channel 0" +
                    (" between cursors." if use_cursors else ".")
                )
    
    def add_statistics(self):
        """Add statistics to table (Ctrl+T) - both channels, between cursors"""
        if not self.abf_handler.is_loaded:
            QMessageBox.warning(self, "Warning", "Please load a file first.")
            return
        
        # Check if both cursors are enabled
        if not self.plot_widget.plot0.cursor1_enabled or not self.plot_widget.plot0.cursor2_enabled:
            QMessageBox.warning(self, "Warning", "Please enable both cursors first.")
            return
        
        # Get cursor positions (X positions are synchronized between plots)
        x1, y1, x2, y2 = self.plot_widget.plot0.get_cursor_positions()
        
        # Ensure x1 < x2
        if x1 > x2:
            x1, x2 = x2, x1
        
        # Get data segments between cursors from both plots (which have baseline correction applied)
        data_ch0 = self.plot_widget.plot0.current_data
        time_ch0 = self.plot_widget.plot0.current_time
        data_ch1 = self.plot_widget.plot1.current_data if self.abf_handler.channel_count > 1 else None
        time_ch1 = self.plot_widget.plot1.current_time if self.abf_handler.channel_count > 1 else None
        
        # Extract data between cursors for channel 0
        mask_ch0 = (time_ch0 >= x1) & (time_ch0 <= x2)
        segment_ch0 = data_ch0[mask_ch0] if data_ch0 is not None and time_ch0 is not None else None
        
        # Extract data between cursors for channel 1
        segment_ch1 = None
        if data_ch1 is not None and time_ch1 is not None:
            mask_ch1 = (time_ch1 >= x1) & (time_ch1 <= x2)
            segment_ch1 = data_ch1[mask_ch1]
        
        if segment_ch0 is None or len(segment_ch0) == 0:
            QMessageBox.warning(self, "Warning", "No data found between cursors.")
            return
        
        # Calculate statistics for the segment
        stats_ch0 = AnalysisTools.calculate_statistics(segment_ch0)
        stats_ch1 = AnalysisTools.calculate_statistics(segment_ch1) if segment_ch1 is not None and len(segment_ch1) > 0 else None
        
        # Get or create statistics table
        if self.statistics_table is None:
            self.statistics_table = StatisticsTableDialog(self)
        
        # Ensure window is visible and brought to front
        self.statistics_table.show()
        self.statistics_table.raise_()
        self.statistics_table.activateWindow()
        if self.statistics_table.isMinimized():
            self.statistics_table.showNormal()
        
        # Add statistics to table (both channels)
        self.statistics_table.add_statistics(stats_ch0, stats_ch1, self.abf_handler.current_sweep + 1)
    
    def show_statistics_table(self):
        """Show statistics table dialog"""
        if self.statistics_table is None:
            self.statistics_table = StatisticsTableDialog(self)
        
        # Ensure window is visible and brought to front
        self.statistics_table.show()
        self.statistics_table.raise_()
        self.statistics_table.activateWindow()
        
        # If window was minimized, restore it
        if self.statistics_table.isMinimized():
            self.statistics_table.showNormal()
    
    def show_peaks_table(self):
        """Show peaks table dialog"""
        if self.peaks_table is None:
            self.peaks_table = PeaksTableDialog(self)
        
        # Ensure window is visible and brought to front
        self.peaks_table.show()
        self.peaks_table.raise_()
        self.peaks_table.activateWindow()
        
        # If window was minimized, restore it
        if self.peaks_table.isMinimized():
            self.peaks_table.showNormal()
    
    def show_blocks_table(self):
        """Show blocks table dialog"""
        if self.blocks_table is None:
            self.blocks_table = BlocksTableDialog(self)
        
        # Ensure window is visible and brought to front
        self.blocks_table.show()
        self.blocks_table.raise_()
        self.blocks_table.activateWindow()
        
        # If window was minimized, restore it
        if self.blocks_table.isMinimized():
            self.blocks_table.showNormal()
    
    def detect_blocks(self):
        """Detect block events in channel 0 - between cursors if enabled"""
        if not self.abf_handler.is_loaded:
            QMessageBox.warning(self, "Warning", "Please load a file first.")
            return
        
        # Check if cursors are enabled - if so, only analyze between them
        use_cursors = (self.plot_widget.plot0.cursor1_enabled and 
                      self.plot_widget.plot0.cursor2_enabled)
        
        if not use_cursors:
            QMessageBox.warning(self, "Warning", "Please enable both cursors to analyze data between them.")
            return
        
        # Get cursor positions
        x1, y1, x2, y2 = self.plot_widget.plot0.get_cursor_positions()
        if x1 > x2:
            x1, x2 = x2, x1
        
        # Get cursor 1 Y value for baseline option
        cursor1_y_ch0 = y1 if self.plot_widget.plot0.cursor1_enabled else None
        
        # Show parameter dialog
        dialog = BlockDetectionDialog(self, cursor1_y=cursor1_y_ch0)
        if dialog.exec() != QDialog.Accepted:
            return
        
        baseline_threshold = dialog.get_baseline_threshold()
        block_threshold_factor = dialog.get_block_threshold_factor()
        min_duration = dialog.get_min_duration()
        
        # Get all sweeps for channel 0
        sweeps = self.abf_handler.get_all_sweeps(0)  # Use channel 0
        
        # Extract data segments between cursors for each sweep
        segment_sweeps = []
        for sweep in sweeps:
            mask = (sweep.time >= x1) & (sweep.time <= x2)
            if np.any(mask):
                segment_data = sweep.data[mask]
                segment_time = sweep.time[mask]
                segment_command = sweep.command[mask] if sweep.command is not None else None
                
                # Create a new SweepData object with just the segment
                segment_sweep = SweepData(
                    sweep_number=sweep.sweep_number,
                    channel=sweep.channel,
                    time=segment_time,
                    data=segment_data,
                    command=segment_command,
                    sample_rate=sweep.sample_rate
                )
                segment_sweeps.append(segment_sweep)
        
        if len(segment_sweeps) == 0:
            QMessageBox.warning(self, "Warning", "No data found between cursors in any sweep.")
            return
        
        # Detect blocks across all sweeps
        all_blocks = BlockDetector.detect_blocks_multiple_sweeps(
            segment_sweeps,
            baseline_threshold=baseline_threshold,
            block_threshold_factor=block_threshold_factor,
            min_block_duration=min_duration
        )
        
        # Store detected blocks for marker updates when changing sweeps
        self.detected_blocks = all_blocks
        
        if len(all_blocks) == 0:
            QMessageBox.information(self, "Block Detection", "No blocks detected with current parameters.")
            return
        
        # Get or create blocks table
        if not hasattr(self, 'blocks_table') or self.blocks_table is None:
            self.blocks_table = BlocksTableDialog(self)
        
        # Ensure window is visible and brought to front
        self.blocks_table.show()
        self.blocks_table.raise_()
        self.blocks_table.activateWindow()
        if self.blocks_table.isMinimized():
            self.blocks_table.showNormal()
        
        # Add blocks to table
        self.blocks_table.add_blocks(all_blocks)
        
        # Mark blocks on plot (only show blocks from current sweep)
        current_sweep_num = self.abf_handler.current_sweep
        current_sweep_blocks = [b for b in all_blocks if b.get('sweep_number') == current_sweep_num]
        if current_sweep_blocks:
            self.plot_widget.plot0.mark_blocks(current_sweep_blocks)
        
        # Show summary message
        total_blocks = len(all_blocks)
        unique_sweeps = len(set(block.get('sweep_number', 0) for block in all_blocks))
        avg_amplitude = np.mean([block.get('average_amplitude', 0) for block in all_blocks])
        
        QMessageBox.information(
            self, "Block Detection",
            f"Detected {total_blocks} block event(s) across {unique_sweeps} sweep(s).\n"
            f"Average block amplitude: {avg_amplitude:.6f}\n\n"
            f"Results displayed in Blocks Table.\n"
            f"Block regions highlighted on current sweep plot."
        )
    
    def clear_analysis(self):
        """Clear all analysis markers (peaks and blocks) from the plot"""
        self.peaks = []
        self.detected_blocks = []
        self.plot_widget.plot0.clear_peak_markers()
        self.plot_widget.plot1.clear_peak_markers()
        self.plot_widget.plot0.clear_block_markers()
        self.plot_widget.plot1.clear_block_markers()
        QMessageBox.information(self, "Clear Analysis", "All analysis markers cleared from plot.")
    
    def clear_peaks(self):
        """Clear peak markers from the plot"""
        self.peaks = []
        self.plot_widget.plot0.clear_peak_markers()
        self.plot_widget.plot1.clear_peak_markers()
        QMessageBox.information(self, "Clear Peaks", "Peak markers cleared from plot.")
    
    def clear_blocks(self):
        """Clear block markers from the plot"""
        self.detected_blocks = []
        self.plot_widget.plot0.clear_block_markers()
        self.plot_widget.plot1.clear_block_markers()
        QMessageBox.information(self, "Clear Blocks", "Block markers cleared from plot.")
    
    def detect_inserts(self):
        """Detect inserts/responses in channel 0 - between cursors if enabled"""
        if not self.abf_handler.is_loaded:
            QMessageBox.warning(self, "Warning", "Please load a file first.")
            return
        
        # Check if cursors are enabled - if so, only analyze between them
        use_cursors = (self.plot_widget.plot0.cursor1_enabled and 
                      self.plot_widget.plot0.cursor2_enabled)
        
        if not use_cursors:
            QMessageBox.warning(self, "Warning", "Please enable both cursors to analyze data between them.")
            return
        
        # Get cursor positions
        x1, y1, x2, y2 = self.plot_widget.plot0.get_cursor_positions()
        if x1 > x2:
            x1, x2 = x2, x1
        
        # Get all sweeps for channel 0
        sweeps = self.abf_handler.get_all_sweeps(0)  # Use channel 0
        
        # Extract data segments between cursors for each sweep
        segment_sweeps = []
        for sweep in sweeps:
            mask = (sweep.time >= x1) & (sweep.time <= x2)
            if np.any(mask):
                segment_data = sweep.data[mask]
                segment_time = sweep.time[mask]
                segment_command = sweep.command[mask] if sweep.command is not None else None
                
                # Create a new SweepData object with just the segment
                segment_sweep = SweepData(
                    sweep_number=sweep.sweep_number,
                    channel=sweep.channel,
                    time=segment_time,
                    data=segment_data,
                    command=segment_command,
                    sample_rate=sweep.sample_rate
                )
                segment_sweeps.append(segment_sweep)
        
        if len(segment_sweeps) == 0:
            QMessageBox.warning(self, "Warning", "No data found between cursors in any sweep.")
            return
        
        # For insert detection, the method uses fractional time windows (0.0-0.1 for baseline, etc.)
        # Since we're working with segments, we'll pass the segments and let the method work
        # with them as if they were full sweeps (the time will be relative to the segment)
        inserts = BlockDetector.detect_inserts(segment_sweeps)
        
        msg = f"Detected {len(inserts)} insert(s)/response(s) in Channel 0 (between cursors):\n\n"
        for i, insert in enumerate(inserts[:20]):  # Limit to first 20
            msg += f"Sweep {insert['sweep'] + 1}: "
            msg += f"Deviation = {insert['deviation']:.4f}, "
            msg += f"Response = {insert['response_mean']:.4f}\n"
        
        if len(inserts) > 20:
            msg += f"\n... and {len(inserts) - 20} more"
        
        QMessageBox.information(self, "Insert Detection", msg)
    
    def export_data(self):
        """Export current sweep data (both channels if available)"""
        if not self.abf_handler.is_loaded:
            QMessageBox.warning(self, "Warning", "Please load a file first.")
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Data", "", "CSV Files (*.csv);;All Files (*)"
        )
        
        if file_path:
            try:
                # Get both channels
                channel0_sweep = self.abf_handler.get_sweep(self.abf_handler.current_sweep, 0)
                channel1_sweep = None
                if self.abf_handler.channel_count > 1:
                    channel1_sweep = self.abf_handler.get_sweep(self.abf_handler.current_sweep, 1)
                
                if channel0_sweep:
                    if channel1_sweep:
                        # Export both channels
                        data = np.column_stack([
                            channel0_sweep.time, 
                            channel0_sweep.data, 
                            channel1_sweep.data
                        ])
                        if channel0_sweep.command is not None and len(channel0_sweep.command) > 0:
                            data = np.column_stack([data, channel0_sweep.command])
                            np.savetxt(file_path, data, delimiter=',', 
                                     header='Time,Channel0,Channel1,Command', comments='')
                        else:
                            np.savetxt(file_path, data, delimiter=',', 
                                     header='Time,Channel0,Channel1', comments='')
                    else:
                        # Export only channel 0
                        data = np.column_stack([channel0_sweep.time, channel0_sweep.data])
                        if channel0_sweep.command is not None and len(channel0_sweep.command) > 0:
                            data = np.column_stack([data, channel0_sweep.command])
                            np.savetxt(file_path, data, delimiter=',', 
                                     header='Time,Channel0,Command', comments='')
                        else:
                            np.savetxt(file_path, data, delimiter=',', 
                                     header='Time,Channel0', comments='')
                    QMessageBox.information(self, "Export", "Data exported successfully.")
                else:
                    QMessageBox.warning(self, "Warning", "No data to export.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to export data: {e}")
    
    def save_as_abf(self):
        """Save current trace as ABF file (with filters applied if any)"""
        if not self.abf_handler.is_loaded:
            QMessageBox.warning(self, "Warning", "Please load a file first.")
            return
        
        if not ABF_WRITE_AVAILABLE:
            QMessageBox.critical(self, "Error", 
                               "ABF writing not available. Please ensure pyABF >= 2.3.8 is installed.")
            return
        
        # Check if cursors are enabled for save between cursors option
        cursors_enabled = (self.plot_widget.plot0.cursor1_enabled and 
                          self.plot_widget.plot0.cursor2_enabled)
        
        # Show save dialog
        dialog = SaveDialog(self, cursors_enabled=cursors_enabled)
        if dialog.exec() != QDialog.Accepted:
            return
        
        save_between_cursors = dialog.save_between_cursors()
        
        if save_between_cursors and not cursors_enabled:
            QMessageBox.warning(self, "Warning", "Please enable both cursors to save a region.")
            return
        
        # Get file path
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save ABF File", "", "ABF Files (*.abf);;All Files (*)"
        )
        
        if not file_path:
            return
        
        # Ensure .abf extension
        if not file_path.lower().endswith('.abf'):
            file_path += '.abf'
        
        try:
            # Get current data (filtered if filters were applied)
            # Channel 0
            channel0_sweep_orig = self.abf_handler.get_sweep(self.abf_handler.current_sweep, 0)
            if not channel0_sweep_orig:
                QMessageBox.warning(self, "Warning", "No data available to save.")
                return
            
            # Use filtered data if available, otherwise use original
            if self.filtered_data_ch0 is not None and self.filtered_time_ch0 is not None:
                ch0_data = self.filtered_data_ch0.copy()
                ch0_time = self.filtered_time_ch0.copy()
            else:
                ch0_data = channel0_sweep_orig.data.copy()
                ch0_time = channel0_sweep_orig.time.copy()
            
            # Get cursor range if saving between cursors
            cursor_x1 = None
            cursor_x2 = None
            if save_between_cursors:
                x1, y1, x2, y2 = self.plot_widget.plot0.get_cursor_positions()
                cursor_x1, cursor_x2 = (x1, x2) if x1 <= x2 else (x2, x1)
                
                # Extract region between cursors
                mask = (ch0_time >= cursor_x1) & (ch0_time <= cursor_x2)
                if not np.any(mask):
                    QMessageBox.warning(self, "Warning", "No data found between cursors.")
                    return
                
                ch0_data = ch0_data[mask]
                ch0_time = ch0_time[mask]
            
            # Channel 1 if available
            channel1_data = None
            if self.abf_handler.channel_count > 1:
                channel1_sweep_orig = self.abf_handler.get_sweep(self.abf_handler.current_sweep, 1)
                if channel1_sweep_orig:
                    # Use filtered data if available
                    if self.filtered_data_ch1 is not None and self.filtered_time_ch1 is not None:
                        ch1_data = self.filtered_data_ch1.copy()
                        ch1_time = self.filtered_time_ch1.copy()
                    else:
                        ch1_data = channel1_sweep_orig.data.copy()
                        ch1_time = channel1_sweep_orig.time.copy()
                    
                    # Extract region if saving between cursors
                    if save_between_cursors and cursor_x1 is not None and cursor_x2 is not None:
                        mask = (ch1_time >= cursor_x1) & (ch1_time <= cursor_x2)
                        if np.any(mask):
                            channel1_data = ch1_data[mask]
                    else:
                        # Ensure same length as ch0
                        if len(ch1_data) == len(ch0_data):
                            channel1_data = ch1_data
                        elif len(ch1_data) > len(ch0_data):
                            channel1_data = ch1_data[:len(ch0_data)]
                        else:
                            # Pad with last value
                            channel1_data = np.pad(ch1_data, (0, len(ch0_data) - len(ch1_data)), 
                                                  mode='edge')
            
            # Prepare data for writing
            # writeABF1 expects data in shape (sweeps, points) - 2D array where each row is a sweep
            # For multiple channels, we'll interleave them or save separately
            sample_rate = channel0_sweep_orig.sample_rate
            
            # Get units from original file
            info = self.abf_handler.get_protocol_info()
            ch0_units = info.adc_units[0] if len(info.adc_units) > 0 else 'pA'
            
            if channel1_data is not None:
                # Two channels - ABF1 format may not support multiple channels in one file
                # We'll interleave the channels as alternating samples (not ideal but works)
                # Or we could save channel 0 and prompt for channel 1 separately
                # For now, let's save channel 0 in the main file and channel 1 separately
                
                # Ensure both channels have the same length
                min_len = min(len(ch0_data), len(channel1_data))
                ch0_data = ch0_data[:min_len]
                channel1_data = channel1_data[:min_len]
                
                # Save channel 0
                # Reshape to (1 sweep, N points)
                data_array_ch0 = ch0_data.reshape(1, -1)
                writeABF1(data_array_ch0, file_path, sample_rate, units=ch0_units)
                
                # Save channel 1 to a separate file
                base_path = file_path.rsplit('.', 1)[0]
                ch1_file_path = f"{base_path}_ch1.abf"
                ch1_units = info.adc_units[1] if len(info.adc_units) > 1 else 'mV'
                data_array_ch1 = channel1_data.reshape(1, -1)
                writeABF1(data_array_ch1, ch1_file_path, sample_rate, units=ch1_units)
                
                QMessageBox.information(self, "Save", 
                                      f"Data saved successfully:\n"
                                      f"Channel 0: {file_path}\n"
                                      f"Channel 1: {ch1_file_path}")
                return
            else:
                # Single channel
                # Reshape to (1 sweep, N points)
                data_array = ch0_data.reshape(1, -1)
                
                # Write ABF file with correct parameter order: (data, filename, sampleRate, units)
                writeABF1(data_array, file_path, sample_rate, units=ch0_units)
            
            QMessageBox.information(self, "Save", 
                                  f"Data saved successfully to:\n{file_path}")
        
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"Save error: {error_details}")  # Print to console for debugging
            QMessageBox.critical(self, "Error", 
                               f"Failed to save ABF file:\n{str(e)}\n\n"
                               f"Check console for details.")
