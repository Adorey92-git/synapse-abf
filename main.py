"""
Synapse ABF Viewer
Cross-platform ABF file viewer and analyzer
"""
import sys
import os

# Enable high DPI scaling for better appearance on modern displays
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPalette

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
    
    # Force light mode regardless of system theme
    app.setStyle('Fusion')  # Use Fusion style for consistent cross-platform appearance
    
    # Set light palette
    palette = QPalette()
    # Window colors (background)
    palette.setColor(QPalette.ColorRole.Window, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.black)
    # Base colors (for input fields, tables, etc.)
    palette.setColor(QPalette.ColorRole.Base, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.AlternateBase, Qt.GlobalColor.lightGray)
    palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.black)
    # Button colors
    palette.setColor(QPalette.ColorRole.Button, Qt.GlobalColor.lightGray)
    palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.black)
    # Highlight colors
    palette.setColor(QPalette.ColorRole.Highlight, Qt.GlobalColor.blue)
    palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.white)
    # Tooltip colors
    palette.setColor(QPalette.ColorRole.ToolTipBase, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.black)
    # Disabled colors
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, Qt.GlobalColor.gray)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, Qt.GlobalColor.gray)
    
    app.setPalette(palette)
    
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

