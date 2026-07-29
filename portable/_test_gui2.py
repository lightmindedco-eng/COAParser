import sys, time
sys.path.insert(0, "src")
from gui.main_window import MainWindow, _CATEGORY_ROLE
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)
w = MainWindow()

start = time.time()
while time.time() - start < 90:
    app.processEvents()
    last = w.file_list.item(w.file_list.count() - 1)
    if last and "[" in last.text():
        break
    time.sleep(0.2)

elapsed = time.time() - start
print(f"Preload done in {elapsed:.1f}s")

for i in range(3):
    item = w.file_list.item(i)
    print(f"  {item.text()}")

cats = w.category_combo
print(f"Category combo has {cats.count()} items:")
for i in range(min(cats.count(), 8)):
    print(f"  {cats.itemText(i)}")

# Filter by first category
if cats.count() > 1:
    cats.setCurrentIndex(1)
    app.processEvents()
    v = sum(1 for i in range(w.file_list.count()) if not w.file_list.item(i).isHidden())
    print(f"Filtered to {v} visible")
    cats.setCurrentIndex(0)
    app.processEvents()

# Test sort
w.sort_combo.setCurrentIndex(2)
app.processEvents()
time.sleep(0.5)
app.processEvents()
for i in range(3):
    print(f"  Date-sorted: {w.file_list.item(i).text()}")

w.sort_combo.setCurrentIndex(0)
