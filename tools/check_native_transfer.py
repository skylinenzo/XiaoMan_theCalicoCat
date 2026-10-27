"""Brief nonactivating native Windows smoke; closes its own test window."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from types import SimpleNamespace
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtCore import Qt
from desktop_cat import DesktopCat
app = QApplication([])
cat = DesktopCat(SimpleNamespace(value=lambda k,d=None:d, setValue=lambda *a:None, sync=lambda:None))
for timer in (cat.timer,cat.floor_timer,cat.top_timer): timer.stop()
cat.hide(); cat.tray.hide(); cat.behavior.enabled=False
support=QWidget()
support.setWindowFlags(Qt.Window|Qt.WindowStaysOnTopHint)
support.setAttribute(Qt.WA_ShowWithoutActivating)
g=app.screens()[-1].geometry()
support.setGeometry(g.x()+350,g.bottom()-650,850,450)
try:
    support.show();app.processEvents();cat.window_observer.pid=-1
    cat.move(g.x()+500,g.bottom()-cat.height()+1)
    cat.route=None;cat.refresh_floor();cat.rest_y=cat.target_y
    cat.move(round(cat.rest_x),round(cat.rest_y))
    assert cat.start_transfer(upward_only=True), 'No reachable native window'
    assert cat.transfer['target'].attachment.hwnd==int(support.winId())
    states=set()
    for i in range(200):
        if i%2==0: cat.refresh_floor()
        with patch('desktop_cat.time.monotonic',return_value=cat.last_tick+.05): cat.tick()
        states.add(cat.visible_state())
        if cat.transfer is None and cat.transition is None: break
    assert cat.perch and cat.perch.hwnd==int(support.winId())
    assert 'transfer_climb' in states
    assert abs(cat.rest_y+cat.perch_baseline()-cat.perch_floor)<1
    cat.jump_down()
    for i in range(150):
        with patch('desktop_cat.time.monotonic',return_value=cat.last_tick+.05): cat.tick()
        if cat.jump is None and cat.transition is None: break
    assert cat.jump is None and cat.perch is None
    print('PASS native Windows: climb, mantle, contact, jump down and landing;',app.screens()[-1].name())
finally:
    support.close();cat.close();cat.tray.hide();app.processEvents()
