import sys
import os
import shutil
import subprocess
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QListWidget, QListWidgetItem, QMenu,
    QMessageBox, QInputDialog, QLabel
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QCursor

class SearchWorker(QThread):
    """Background thread to run the search process without freezing the GUI."""
    item_found = Signal(str)  # Emits each path as soon as it's found
    error_occurred = Signal(str)
    search_finished = Signal()

    def __init__(self, location, search_term):
        super().__init__()
        self.location = location
        self.search_term = search_term

    def run(self):
        try:
            # pkexec triggers a GUI password prompt instead of terminal sudo
            process = subprocess.Popen(
                [
                    "pkexec", "find", self.location, 
                    "-xdev", 
                    "-iname", f"*{self.search_term}*", 
                    "-print"
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, 
                text=True
            )
            
            # Read the output line-by-line in real time
            for line in process.stdout:
                path = line.strip()
                if path:
                    self.item_found.emit(path)
            
            process.wait()
            self.search_finished.emit()
        except Exception as e:
            self.error_occurred.emit(str(e))


class SearchApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("File Search")
        self.resize(800, 600)

        # Central Widget & Layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Top Bar Layout (Location, Search Bar, Search Button)
        top_layout = QHBoxLayout()
        
        self.location_input = QLineEdit()
        self.location_input.setPlaceholderText("Search Location (e.g., /home or /)")
        self.location_input.setText("/")
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Enter search term...")
        
        self.search_btn = QPushButton("Search")
        self.search_btn.clicked.connect(self.perform_search)
        self.search_input.returnPressed.connect(self.perform_search)

        top_layout.addWidget(QLabel("Location:"))
        top_layout.addWidget(self.location_input, 1)
        top_layout.addWidget(self.search_input, 3)
        top_layout.addWidget(self.search_btn)

        # Search Results List
        self.results_list = QListWidget()
        self.results_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.results_list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.results_list.itemDoubleClicked.connect(self.on_double_click)
        self.results_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.results_list.customContextMenuRequested.connect(self.show_context_menu)

        main_layout.addLayout(top_layout)
        main_layout.addWidget(self.results_list)

        self.worker = None

    def perform_search(self):
        location = self.location_input.text().strip() or "/"
        search_term = self.search_input.text().strip()

        if not search_term:
            return

        # Clear previous results and disable inputs while searching
        self.results_list.clear()
        self.search_btn.setEnabled(False)
        self.search_input.setEnabled(False)
        self.location_input.setEnabled(False)

        # Start background thread
        self.worker = SearchWorker(location, search_term)
        self.worker.item_found.connect(self.add_single_result)
        self.worker.error_occurred.connect(self.handle_search_error)
        self.worker.search_finished.connect(self.restore_ui)
        self.worker.start()

    def add_single_result(self, path):
        name = os.path.basename(path)
        if not name:  # Edge case for root dir
            name = path
        
        item = QListWidgetItem(name)
        # Store the full path in the item's hidden data
        item.setData(Qt.UserRole, path)
        self.results_list.addItem(item)

    def handle_search_error(self, error_msg):
        self.results_list.clear()
        QMessageBox.critical(self, "Error", f"Failed to execute search.sh: {error_msg}")

    def restore_ui(self):
        # Re-enable inputs once the background thread finishes
        self.search_btn.setEnabled(True)
        self.search_input.setEnabled(True)
        self.location_input.setEnabled(True)

    def on_double_click(self, item):
        path = item.data(Qt.UserRole)
        if path:
            self.open_with_fallback(path)

    def show_context_menu(self, position):
        item = self.results_list.itemAt(position)
        if not item or not item.data(Qt.UserRole):
            return

        path = item.data(Qt.UserRole)
        is_dir = os.path.isdir(path)
        type_str = "folder" if is_dir else "file"

        menu = QMenu()
        rename_action = menu.addAction(f"Rename {type_str}")
        delete_action = menu.addAction(f"Delete {type_str}")
        copy_action = menu.addAction("Copy full path")
        open_loc_action = menu.addAction(f"Open {type_str} location")
        open_action = menu.addAction(f"Open {type_str}")

        action = menu.exec(self.results_list.viewport().mapToGlobal(position))

        if action == rename_action:
            self.rename_item(item, path)
        elif action == delete_action:
            self.delete_item(item, path, type_str)
        elif action == copy_action:
            QApplication.clipboard().setText(path)
        elif action == open_loc_action:
            parent_dir = os.path.dirname(path)
            self.open_with_fallback(parent_dir)
        elif action == open_action:
            self.open_with_fallback(path)

    def rename_item(self, item, current_path):
        current_name = os.path.basename(current_path)
        new_name, ok = QInputDialog.getText(self, "Rename", "Enter new name:", text=current_name)
        
        if ok and new_name and new_name != current_name:
            parent_dir = os.path.dirname(current_path)
            new_path = os.path.join(parent_dir, new_name)
            try:
                os.rename(current_path, new_path)
                item.setText(new_name)
                item.setData(Qt.UserRole, new_path)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not rename:\n{e}")

    def delete_item(self, item, path, type_str):
        confirm = QMessageBox.question(
            self, "Confirm Delete", 
            f"Are you sure you want to delete this {type_str}?\n\n{path}",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if confirm == QMessageBox.Yes:
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
                
                # Remove item from the list UI
                row = self.results_list.row(item)
                self.results_list.takeItem(row)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not delete:\n{e}")

    def open_with_fallback(self, target_path):
        commands = [
            ["xdg-open", target_path],
            ["gio", "open", target_path],
            ["kde-open", target_path],
            ["exo-open", target_path],
            ["pcmanfm", target_path],
            ["dde-open", target_path]
        ]

        for cmd in commands:
            try:
                subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return 
            except (FileNotFoundError, subprocess.CalledProcessError):
                pass
                
        QMessageBox.warning(self, "Warning", "Could not find a suitable application to open this path.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SearchApp()
    window.show()
    sys.exit(app.exec())