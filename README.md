# Synapse ABF Viewer

A lightweight, cross-platform ABF (Axon Binary Format) file viewer and analyzer for electrophysiology data analysis. Built with Python, PySide6 (Qt), and pyABF, this application provides comprehensive tools for viewing and analyzing electrophysiology data on Windows, macOS, and Linux.

## 🚀 Quick Download (Recommended)

**The fastest way to get started is to download a pre-built application:**

- **macOS**: Download `synapse-abf-mac.zip` - Extract and run the app (no installation required!)
- **Windows**: Download `synapse-abf-windows.exe` - Double-click to run (coming soon)

These pre-built applications include all dependencies and require no Python installation. Just download and run!

## Features

### Core Functionality
- **Multi-platform Support**: Runs natively on Windows, macOS, and Linux
- **ABF File Support**: Full support for Axon Binary Format files via pyABF
- **Dual-channel Display**: View Channel 0 and Channel 1 simultaneously in vertically stacked plots
- **Sweep Navigation**: Easy navigation through sweeps/episodes with Previous/Next buttons
- **File Navigation**: Navigate through ABF files in the current directory
- **Professional Navigation**: Zoom (+/-) and pan buttons on axes, mouse wheel zoom, drag pan

### Cursor System
- **Two Independent Cursors**: Cursor 1 (red) and Cursor 2 (blue)
- **Cursor Locking**: Move both cursors together while maintaining distance
- **Measurements Table**: Copyable format storing multiple measurements for both channels
- **Statistics Table**: Copyable format with comprehensive statistics for both channels (calculated between cursors)

### Analysis Tools
- **Peak Detection**: Detect peaks and troughs with configurable parameters
  - Minimum height, distance, and prominence thresholds
  - Peaks table with copyable data (Index, Time, Value, Type)
- **Block Detection**: Automatic detection of experimental blocks/episodes
  - Multiple detection methods (variance, mean, peak, combined)
  - Adaptive thresholding
- **Insert Detection**: Detect inserts/responses based on baseline comparison
  - Configurable baseline and response windows
- **Baseline Correction**: Set baseline using Cursor 1 Y value or manual input

### Filtering
- **Gaussian Lowpass Filter**:
  - Configurable cutoff frequency
  - Filter entire trace or only region between cursors
  - Apply to Channel 0, Channel 1, or both channels
  - Permanent and cumulative (filters persist within a sweep)
  - Gaussian filter implementation (-3dB point at cutoff frequency)

### Display & Customization
- **Trace Colors**: Customize colors for Channel 0 and Channel 1 independently
  - Preset colors or custom RGB color picker
- **Grid Visibility**: Toggle grid lines on/off for clean image export
- **White Background**: Clean, publication-ready appearance
- **Command Waveform**: Toggle display of stimulus/command waveforms

### File Operations
- **Save ABF Files**: Save current trace (filtered or unfiltered)
  - Option to save only region between cursors
  - Saves all channels (creates separate files for multi-channel data)

### Performance
- Optimized for large data files:
  - Clip to view rendering
  - Automatic downsampling when zoomed out
  - Efficient memory usage

## Installation

### Option 1: Download Pre-built Application (Easiest)

1. Download the appropriate file for your platform:
   - macOS: `synapse-abf-mac.zip`
   - Windows: `synapse-abf-windows.exe` (coming soon)
2. Extract (macOS) or run (Windows) the application
3. No Python installation required!

### Option 2: Run from Source

#### Prerequisites
- Python 3.7 or higher
- pip (Python package manager)

#### Install Dependencies

```bash
pip install -r requirements.txt
```

Or install individually:
```bash
pip install pyABF PySide6 pyqtgraph scipy numpy
```

#### Running the Application

```bash
python main.py
```

Or with an ABF file:
```bash
python main.py path/to/file.abf
```

## Usage

### User Interface

#### Menu Bar
- **File Menu**
  - Open: Load an ABF file (Ctrl+O)
  - Save As...: Save current trace as ABF file (Ctrl+S)
  - Exit: Close application (Ctrl+Q)

- **Analysis Menu**
  - Enable Cursor 1/2: Toggle measurement cursors (Ctrl+1, Ctrl+2)
  - Add Measurement: Add measurement to table (Ctrl+M)
  - Add Statistics: Add statistics to table (Ctrl+T)
  - Measurements Table: Show measurements table
  - Statistics Table: Show statistics table
  - Peaks Table: Show detected peaks table
  - Detect Peaks: Detect peaks/troughs in current sweep
  - Detect Blocks: Identify experimental blocks
  - Detect Inserts: Find insert/responses
  - Baseline Correction: Set baseline offset

- **View Menu**
  - Show Command Waveform: Toggle stimulus display
  - Trace Colors...: Customize trace colors
  - Show Grid: Toggle grid lines

#### Toolbar
- File navigation: Previous/Next ABF file buttons
- Sweep navigation: Previous/Next sweep buttons

#### Control Panel (Left)
- **File Info**: Displays file metadata
- **Sweep Controls**: Navigate through sweeps
- **Analysis Controls**: Quick access buttons for all analysis tools

#### Main Plot Area
- Dual-channel plots (stacked vertically)
- Interactive waveform display
- Zoom: Scroll wheel or +/- buttons
- Pan: Drag or arrow buttons
- Cursors: Red (Cursor 1) and Blue (Cursor 2)

### Keyboard Shortcuts
- `Ctrl+O`: Open file
- `Ctrl+S`: Save ABF file
- `Ctrl+Q`: Quit
- `Ctrl+1`: Toggle Cursor 1
- `Ctrl+2`: Toggle Cursor 2
- `Ctrl+M`: Add measurement
- `Ctrl+T`: Add statistics

### Common Workflows

#### Taking Measurements
1. Open ABF file
2. Enable Cursor 1 and Cursor 2
3. Position cursors at desired locations
4. Click "Add Measurement" or press Ctrl+M
5. Measurement added to table (copyable format)

#### Analyzing Between Cursors
1. Enable both cursors
2. Position cursors to define analysis region
3. Use any analysis tool (Statistics, Peak Detection, etc.)
4. Results calculated only for data between cursors

#### Filtering Data
1. Navigate to desired sweep
2. Optionally enable cursors to filter specific region
3. Click "Apply Filter" or use View menu
4. Select cutoff frequency and channel(s)
5. Filter is permanent and cumulative

## Architecture

### Module Structure
- `main.py`: Application entry point
- `viewer.py`: Main GUI window and UI components
- `abf_handler.py`: ABF file loading and management
- `analysis_tools.py`: Analysis algorithms and utilities

### Key Classes
- `ABFViewerMainWindow`: Main application window
- `ABFHandler`: ABF file operations
- `TracePlotWidget`: Custom plotting widget with cursor support
- `DualChannelPlotWidget`: Container for dual-channel display
- `AnalysisTools`: Static analysis functions
- `BlockDetector`: Block and insert detection

## Development

### Requirements
- Python 3.7+
- PySide6 6.5.0+
- pyABF 2.3.8+
- pyqtgraph 0.13.0+
- scipy 1.10.0+
- numpy 1.24.0+

### Code Structure
The application follows a modular design:
- UI components in `viewer.py`
- Data handling in `abf_handler.py`
- Analysis algorithms in `analysis_tools.py`
- Entry point in `main.py`

### Building Standalone Applications

#### Using PyInstaller

**macOS App Bundle:**
```bash
pip install pyinstaller
pyinstaller --name="SynapseABFViewer" --windowed --onedir --icon=icon.icns main.py
```

**Windows Executable:**
```bash
pip install pyinstaller
pyinstaller --name="SynapseABFViewer" --windowed --onefile --icon=icon.ico main.py
```

**Linux AppImage:**
```bash
pip install pyinstaller
pyinstaller --name="SynapseABFViewer" --windowed --onedir main.py
# Then use appimagetool to create AppImage
```

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## License

This project is open source. Please check license information for dependencies:
- pyABF: MIT License
- PySide6: LGPL/Commercial
- pyqtgraph: MIT License
- scipy: BSD License
- numpy: BSD License

## Acknowledgments

- Built with [pyABF](https://swharden.com/pyabf/)
- UI framework: PySide6 (Qt for Python)
- Plotting: pyqtgraph
- Designed for electrophysiology data analysis workflows

## Support

For issues, feature requests, or questions, please open an issue on the project repository.

