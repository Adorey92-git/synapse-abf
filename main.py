"""
Synapse ABF Viewer
Cross-platform ABF file viewer and analyzer
"""
import sys
import os

# Enable high DPI scaling for better appearance on modern displays
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from viewer import ABFViewerMainWindow


def main():
    """Main entry point"""
    # Enable high DPI support
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    
    app = QApplication(sys.argv)
    app.setApplicationName("Synapse ABF Viewer")
    app.setOrganizationName("Synapse")
    
    # Create and show main window
    window = ABFViewerMainWindow()
    window.show()
    
    # Handle file opening from command line
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        if os.path.exists(file_path):
            window.abf_handler.load_file(file_path)
            window.current_file_path = file_path
            window._update_ui()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

