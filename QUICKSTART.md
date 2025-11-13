# Quick Start Guide

## 🚀 Quickest Way to Get Started

**Download the pre-built application for your platform:**

- **macOS**: Download `synapse-abf-mac.zip` - Extract and run! (No Python installation needed)
- **Windows**: Download `synapse-abf-windows.exe` - Double-click to run! (Coming soon)

This is the fastest way to use Synapse ABF Viewer. The application includes all dependencies and works immediately without any setup.

---

## Alternative: Running from Source

If you prefer to run from source or want to modify the code:

### Installation

1. **Activate your virtual environment** (if using one):
   ```bash
   source synapse-abf/bin/activate  # On macOS/Linux
   # or
   synapse-abf\Scripts\activate  # On Windows
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

### Running the Application

#### Basic Usage
```bash
python main.py
```

#### Open a file directly
```bash
python main.py path/to/your/file.abf
```

#### Using the installed command (after setup.py install)
```bash
pip install -e .
synapse-abf path/to/your/file.abf
```

---

## First Steps

### 1. Open a File
   - Click `File > Open` or press `Ctrl+O` (Cmd+O on Mac)
   - Navigate to your ABF file
   - Or use the file navigation buttons (◄ Prev File / Next File ►) to browse files in a directory

### 2. Navigate Sweeps
   - Use the spin box in the left panel
   - Use toolbar buttons (◄ Prev Sweep / Next Sweep ►)
   - Both Channel 0 and Channel 1 are displayed simultaneously

### 3. Zoom and Pan
   - **Zoom**: Use scroll wheel or +/- buttons on axes
   - **Pan**: Drag with mouse or use arrow buttons on axes
   - Professional navigation with buttons at edges (zoom) and center (pan)

### 4. Take Measurements
   - Click "Enable Cursor 1 (red)" button
   - Click "Enable Cursor 2 (blue)" button
   - Drag cursors to desired positions
   - Click "Add Measurement" or press `Ctrl+M`
   - Measurement appears in the Measurements Table (copyable format)

### 5. View Statistics
   - Enable both cursors
   - Position cursors to define analysis region
   - Click "Add Statistics" or press `Ctrl+T`
   - Statistics appear in the Statistics Table (calculated between cursors)

### 6. Detect Peaks
   - Enable both cursors to analyze a specific region
   - Click "Detect Peaks"
   - Adjust parameters in the dialog (height, distance, prominence)
   - Peaks are marked on the plot and added to the Peaks Table

---

## Common Workflows

### Analyzing a Response Between Cursors
1. Open your ABF file
2. Navigate to the sweep with the response
3. Enable both cursors
4. Position Cursor 1 at baseline
5. Position Cursor 2 at peak response
6. Click "Add Measurement" for delta values
7. Click "Add Statistics" for comprehensive statistics
8. Copy data from tables to Excel/other programs

### Filtering Data
1. Navigate to desired sweep
2. Click "Apply Filter" or use View menu
3. Select cutoff frequency (e.g., 1000 Hz)
4. Choose channel(s) to filter
5. Optionally check "Filter between cursors only"
6. Click OK - filter is permanent and cumulative

### Baseline Correction
1. Enable Cursor 1
2. Position cursor at desired baseline level
3. Click "Baseline Correction"
4. Use Cursor 1 value or enter manual offset
5. Click OK - baseline is corrected for both channels independently

### Customizing Display
1. **Change trace colors**: View > Trace Colors...
   - Select colors for Channel 0 and Channel 1
   - Use preset colors or custom color picker
2. **Toggle grid**: View > Show Grid
   - Uncheck to hide grid for clean image export
   - Check to show grid again

### Saving Filtered Data
1. Apply filters as desired
2. Optionally enable cursors to save only a region
3. Click File > Save As... or press Ctrl+S
4. Choose save location
5. Option to save only region between cursors
6. All channels are saved

### File Navigation
1. Open an ABF file
2. Use toolbar buttons "◄ Prev File" and "Next File ►"
3. Navigate through all ABF files in the current directory
4. Viewer resets to initial state for each new file

---

## Tips & Tricks

- **Zoom**: Scroll wheel on plot or use +/- buttons
- **Pan**: Drag with mouse or use arrow buttons
- **Lock Cursors**: Click "Lock Cursors" to move both together maintaining distance
- **Command Waveform**: Toggle via `View > Show Command Waveform`
- **Copy Table Data**: Select rows in any table and click "Copy Selected", or "Copy All"
- **Clean Images**: Hide grid (View > Show Grid) and customize colors for publication-ready plots
- **Multiple Measurements**: Keep adding measurements - they accumulate in the table
- **Filtering**: Filters are cumulative - you can apply multiple filters sequentially
- **Reset**: Loading a new file resets all analysis state (cursors, filters, measurements)

---

## Keyboard Shortcuts

- `Ctrl+O` (Cmd+O): Open file
- `Ctrl+S` (Cmd+S): Save ABF file
- `Ctrl+Q` (Cmd+Q): Quit
- `Ctrl+1`: Toggle Cursor 1
- `Ctrl+2`: Toggle Cursor 2
- `Ctrl+M`: Add measurement
- `Ctrl+T`: Add statistics

---

## Troubleshooting

### Application won't start (Pre-built version)
- **macOS**: Right-click the app and select "Open" if you get a security warning
- Ensure you're running on a compatible system version
- Try downloading again if the file appears corrupted

### "No module named 'pyabf'" (Source version)
Run: `pip install pyABF`

### "No module named 'PySide6'" (Source version)
Run: `pip install PySide6`

### Application won't start (Source version)
- Ensure all dependencies are installed: `pip install -r requirements.txt`
- Check Python version: `python --version` (needs 3.7+)

### File won't load
- Verify file is a valid ABF file
- Check file permissions
- Try opening with pyABF directly to verify file integrity: `python -c "import pyabf; abf = pyabf.ABF('file.abf')"`

### Filter not working
- Ensure you have scipy installed: `pip install scipy`
- Check that cutoff frequency is below Nyquist frequency (sample_rate / 2)

### Colors not updating
- Try changing colors and then navigating to a different sweep and back
- Ensure you clicked OK in the color dialog

---

## Getting Help

- Check the full [README.md](README.md) for detailed feature documentation
- Review [FeatureList.txt](FeatureList.txt) for a complete list of features
- Open an issue on the project repository for bugs or feature requests

---

## What's Next?

- Try detecting blocks and inserts for automated analysis
- Explore the Gaussian lowpass filter for smoothing data
- Use the Peaks Table to analyze multiple detected peaks
- Customize colors and hide grid for publication-ready figures
- Save filtered data as new ABF files for further analysis
