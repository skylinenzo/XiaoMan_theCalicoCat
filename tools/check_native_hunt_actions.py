"""Native Qt smoke, hidden pet and simulated cursor; no real input injection."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from types import SimpleNamespace
from unittest.mock import patch
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication
from desktop_cat import DesktopCat
app=QApplication([])
cat=DesktopCat(SimpleNamespace(value=lambda k,d=None:d,setValue=lambda *a:None,sync=lambda:None))
for t in (cat.timer,cat.floor_timer,cat.top_timer):t.stop()
cat.hide();cat.tray.hide();cat.behavior.enabled=False
try:
    g=app.primaryScreen().geometry()
    cat.move(g.x()+g.width()//2,g.bottom()-cat.height())
    cat.route=None;cat.refresh_floor();cat.rest_y=cat.target_y
    cat.move(round(cat.rest_x),round(cat.rest_y))
    floor=round(cat.target_y+cat.height()*490/512)
    cursor=QPoint(round(cat.rest_x+cat.width()/2+60),floor-10)
    cat.cursor_position=lambda:cursor
    cat.set_hunt_enabled(True);cat.transition=None;cat.hunt.cooldown=0
    seen=set()
    for _ in range(120):
        with patch('desktop_cat.time.monotonic',return_value=cat.last_tick+.05):cat.tick()
        seen.add(cat.hunt.state)
        assert not cat.render_frame().isNull()
    assert 'play_kick' in seen and 'pounce' in seen,seen
    cat.set_hunt_enabled(False);cat.perform_run('left')
    for _ in range(30):
        with patch('desktop_cat.time.monotonic',return_value=cat.last_tick+.05):cat.tick()
    assert cat.is_running()
    assert cat.gaze.target is not None
    print('PASS native Windows: directional pounce, caught play, gallop and eye layers; simulated cursor only')
finally:
    cat.close();cat.tray.hide();app.processEvents()
