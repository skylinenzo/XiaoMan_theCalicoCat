"""Windows 11 transparent, draggable desktop cat. Run with Windows Python."""
import math
from dataclasses import replace
import json
from pathlib import Path
import sys
import time

from PySide6.QtCore import QRectF, QSettings, Qt, QTimer
from PySide6.QtGui import QActionGroup, QCursor, QIcon, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QWidget

from pet_logic import REST_STATES, PatrolBehavior, blink_at, floor_offset, sequence_blend, sequence_frame
from deform_renderer import STRIDE, DeformCat
from anchored_renderer import AnchoredWalk, mix
from desktop_route import DesktopRoute, Surface
from pose_transition import PoseTransition
from action_routes import transition_route
from pet_effects import HeldSway, contact_shadow
from window_perch import WindowObserver, choose_perch, follow_perch, advance_perch, match_monitors
from activity_rhythm import ActivityRhythm
from mouse_hunt import MouseHunt
from run_animation import RunCycle
from eyes import EyeControl
from sprite_scale import calibrate_animation
from window_motion import GravityDescent
from window_transfer import TransferMotion, choose_transfer, canvas_on_screens, window_occlusion_rects

ASSETS = Path(__file__).resolve().parent / 'output/imagegen/idle-v3'
WALK_SPEED_MULTIPLIER = 2.0


def blend_images(first, second, amount):
    """Interpolate premultiplied color AND alpha, without double-compositing edges."""
    return mix(first, second, amount)


class DesktopCat(QWidget):
    def __init__(self, settings=None):
        super().__init__()
        from windows_taskbar import TaskbarObserver
        self.observer = TaskbarObserver()
        try:
            self.window_observer = WindowObserver()
        except OSError:
            self.window_observer = None
        self.perch = None
        self.perch_errors = 0
        self.perch_snapshot = None
        self.perch_floor = None
        self.perch_state = 'window_perch'
        self.perch_direction = 1
        self.perch_action_time = 0.
        self.perch_action_duration = 5.
        self.jump = None
        self.transfer = None
        self.hunt = MouseHunt()
        self.hunt_enabled = False
        self.running_requested = False
        self.run_cycle = RunCycle()
        self.gaze = EyeControl()
        self.cursor_position = QCursor.pos
        self.roam_cooldown = 15.
        self.overlay_elapsed = 0.
        self.held_sway = HeldSway()
        self.held_dx = 0.
        self.shadow_cache = {}
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool
                            | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowTitle('三花桌宠')
        transition_folder = ASSETS.parent / 'turn-sit-v1'
        transition_meta = json.loads((transition_folder / 'animation.json').read_text())
        self.idle_scale = transition_meta['idle_scale']
        self.transition_seconds = transition_meta['segment_duration_ms'] / 1000
        self.transition = None
        self.turn_frames = {side: [QImage(str(transition_folder / name)).convertToFormat(
            QImage.Format.Format_ARGB32_Premultiplied) for name in transition_meta[side]]
            for side in ('left', 'right')}
        if any(frame.isNull() for frames in self.turn_frames.values() for frame in frames):
            raise RuntimeError(f'找不到转身素材：{transition_folder}')
        self.frames = [self.rest_image(ASSETS / f'frame-{i:02}.png') for i in range(1, 7)]
        if any(frame.isNull() for frame in self.frames):
            raise RuntimeError(f'找不到动画素材：{ASSETS}')
        self.animations = {}
        for state, directory in [('groom', 'groom-v1'),
                                 ('rest_prone', 'rest-idles-v1/prone'),
                                 ('rest_supine', 'rest-idles-v1/supine'),
                                 ('rest_side', 'rest-idles-v1/side'),
                                 ('held', 'interactions-v1/held'),
                                 ('window_perch', 'interactions-v1/perch'),
                                 ('window_straddle', 'window-actions-v1/straddle'),
                                 ('jump_down', 'window-actions-v1/jump'),
                                 ('window_climb', 'window-climb-v1'),
                                 ('window_climb_back', 'window-climb-back-v1'),
                                 ('window_climb_side', 'window-climb-side-v1'),
                                 *[(name, 'hunt-actions-v1/'+name) for name in
                                   ('run_left','run_right','pounce_left','pounce_right','play_kick','play_lick')]]:
            folder = ASSETS.parent / directory
            metadata = json.loads((folder / 'animation.json').read_text())
            frames = ([QImage(str(folder / name)).convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
                       for name in metadata['frames']] if metadata.get('ready_for_app') else
                      [self.rest_image(folder / name) for name in metadata['frames']])
            if any(frame.isNull() for frame in frames):
                raise RuntimeError(f'找不到动画素材：{folder}')
            self.animations[state] = calibrate_animation(state, frames, metadata)
        self.walk_animations = {}
        for style, version in [('frames_original', 'v1'), ('frames_aligned', 'v2')]:
            self.walk_animations[style] = {}
            for side in ('left', 'right'):
                folder = ASSETS.parent / f'walk-{side}-{version}'
                metadata = json.loads((folder / 'animation.json').read_text())
                frames = [QImage(str(folder / name)).convertToFormat(
                    QImage.Format.Format_ARGB32_Premultiplied) for name in metadata['frames']]
                if any(frame.isNull() for frame in frames):
                    raise RuntimeError(f'找不到动画素材：{folder}')
                self.walk_animations[style][side] = (frames, metadata)
        self.deform = DeformCat()
        self.anchored = AnchoredWalk()
        self.diagonal = AnchoredWalk({'left': 'walk-diagonal-left-v1',
                                     'right': 'walk-diagonal-right-v1'})
        self.settings = settings if settings is not None else QSettings('DesktopCat', 'CalicoPet')
        # One-time migration to the user's new preferred eight-frame gait.
        if self.settings.value('gait_revision', '') != 'diagonal-cycle-v2':
            self.settings.setValue('walk_style', 'frames_diagonal')
            self.settings.setValue('gait_revision', 'diagonal-cycle-v2')
        saved_style = self.settings.value('walk_style', 'frames_diagonal')
        self.walk_style = saved_style if saved_style in ('frames_diagonal', 'frames_anchored', 'deform', *self.walk_animations) else 'frames_diagonal'
        saved_climb = self.settings.value('climb_style', 'back')
        self.climb_style = saved_climb if saved_climb in ('back', 'side', 'front_hidden') else 'back'
        self.gait_phase = 0.
        self.gait_time = 0.
        self.route = None
        self.route_position = 0.
        self.route_screen = None
        self.rhythm = ActivityRhythm()
        self.rhythm_pending = False
        self.manual_activity_time = 0.
        self.behavior = PatrolBehavior(cycle_seconds={
            **{state: sum(metadata['duration_ms']) / 1000
               for state, (_, metadata) in self.animations.items()},
            'walk_left': 1., 'walk_right': 1.}, rest_states=REST_STATES, rhythm=self.rhythm)
        self.resize(220, 220)
        self.drag_offset = None
        self.mode = 'auto'
        self.started = time.monotonic()
        self.last_tick = self.started
        self.rest_y = None
        self.target_y = None
        self.menu_open = False
        self.floor_pixels = 0
        self.menu = QMenu()
        self.auto_action = self.menu.addAction('自主生活（休息、活动、偶尔撒欢）')
        self.auto_action.setCheckable(True)
        self.auto_action.setChecked(True)
        self.auto_action.toggled.connect(self.set_autonomy)
        self.hunt_action = self.menu.addAction('捕猎鼠标（底部测试）')
        self.hunt_action.setCheckable(True)
        self.hunt_action.toggled.connect(self.set_hunt_enabled)
        self.gaze_action = self.menu.addAction('目光跟随（眼眶内）')
        self.gaze_action.setCheckable(True)
        self.gaze_action.setChecked(True)
        self.gaze_action.toggled.connect(lambda enabled: setattr(self.gaze, 'enabled', enabled))
        moods = self.menu.addMenu('活动程度')
        self.mood_status = moods.addAction('当前：休息')
        self.mood_status.setEnabled(False)
        for title, state in [('休息一会儿', 'rest'), ('起来活动', 'active'), ('撒欢一阵', 'burst')]:
            moods.addAction(title, lambda checked=False, value=state: self.set_activity(value))
        styles = self.menu.addMenu('走路效果')
        self.style_group = QActionGroup(self)
        self.style_group.setExclusive(True)
        self.style_actions = {}
        for title, style in [('对角交替走路（新 8 帧）', 'frames_diagonal'),
                             ('旧 8 帧翘尾巴（脚掌锚定）', 'frames_anchored'),
                             ('Deform（整图柔性变形）', 'deform'),
                             ('最初动画版（8 帧）', 'frames_original'),
                             ('整理后的动画版（4 帧）', 'frames_aligned')]:
            action = styles.addAction(title)
            action.setCheckable(True)
            action.setChecked(style == self.walk_style)
            self.style_group.addAction(action)
            action.triggered.connect(lambda checked=False, value=style: self.set_walk_style(value))
            self.style_actions[style] = action
        climbs = self.menu.addMenu('爬窗方式')
        self.climb_group = QActionGroup(self)
        self.climb_group.setExclusive(True)
        self.climb_actions = {}
        for title, style in [('背面爬（窗口前方）', 'back'), ('侧面爬（窗口前方）', 'side'),
                             ('正面爬（窗口后方遮挡）', 'front_hidden')]:
            action = climbs.addAction(title)
            action.setCheckable(True)
            action.setChecked(style == self.climb_style)
            self.climb_group.addAction(action)
            action.triggered.connect(lambda checked=False, value=style: self.set_climb_style(value))
            self.climb_actions[style] = action
        actions = self.menu.addMenu('现在做个动作')
        for title, state in [('坐下休息', 'idle'), ('舔爪', 'groom'),
                             ('趴着休息', 'rest_prone'), ('仰躺放松', 'rest_supine'),
                             ('侧卧打盹', 'rest_side'), ('抱住蹬蹬', 'play_kick'), ('按住舔舔', 'play_lick'),
                             ('向左走', 'walk_left'), ('向右走', 'walk_right')]:
            actions.addAction(title, lambda value=state: self.manual_perform(value))
        actions.addAction('向左奔跑', lambda: self.perform_run('left'))
        actions.addAction('向右奔跑', lambda: self.perform_run('right'))
        actions.addAction('趴到附近窗口上沿', lambda: self.try_attach_window(160))
        actions.addAction('骑在窗框上放松', lambda: self.perform('window_straddle'))
        actions.addAction('趴在窗沿休息', lambda: self.perform('window_perch'))
        actions.addAction('跳上／爬上附近窗口', lambda: self.start_transfer(upward_only=True))
        actions.addAction('跳到另一扇窗口', self.start_transfer)
        actions.addAction('从窗口跳下', self.jump_down)
        actions.addAction('回到任务栏／屏幕底沿', lambda: self.set_mode('auto'))
        self.menu.addSeparator()
        for title, mode in [('自动坐在任务栏／屏幕底沿', 'auto'),
                            ('固定坐在屏幕底沿', 'screen'), ('自由悬浮', 'free')]:
            action = self.menu.addAction(title)
            action.triggered.connect(lambda checked=False, value=mode: self.set_mode(value))
        sizes = self.menu.addMenu('大小')
        for size in (160, 220, 300):
            sizes.addAction(f'{size} 像素', lambda value=size: self.change_size(value))
        self.menu.addSeparator()
        self.menu.addAction('退出', QApplication.instance().quit)
        self.tray = QSystemTrayIcon(QIcon(QPixmap.fromImage(self.frames[0])), self)
        self.tray.setToolTip('三花桌宠：拖动抱起，靠近窗口上沿松手，右键设置')
        self.tray.setContextMenu(self.menu)
        self.tray.show()
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.x() + screen.width() * 3 // 4,
                  screen.y() + screen.height() - self.height())
        self.show()
        self.rest_x = float(self.x())
        self.refresh_floor()
        if self.target_y is not None:
            self.rest_y = self.target_y
            self.move(self.x(), round(self.rest_y))
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.tick)
        self.timer.start(16)
        self.floor_timer = QTimer(self)
        self.floor_timer.timeout.connect(self.refresh_floor)
        self.floor_timer.start(100)
        self.top_timer = QTimer(self)
        self.top_timer.timeout.connect(self.raise_pet)
        self.top_timer.start(1500)

    def set_mode(self, mode):
        self.hunt.cancel()
        self.mode = mode
        if self.transfer is not None:
            if mode == 'free':
                self.transfer = self.perch = self.perch_snapshot = self.transition = None
                self.behavior.start('idle')
                return
            self.cancel_transfer(fall=True)
        if self.jump is not None:
            # Finish a supported landing before changing position mode.
            self.mode = 'auto' if mode == 'free' else mode
            return
        if self.perch is not None:
            if mode != 'free':
                self.jump_down()
                return
            previous, initial = self.visible_state(), self.visible_image()
            self.perch = self.perch_snapshot = None
            self.behavior.start('idle')
            self.begin_transition(previous, 'idle', initial)
            return
        self.perform('idle')
        self.refresh_floor()

    def rest_image(self, path):
        source = QImage(str(path))
        if source.isNull():
            raise RuntimeError(f'找不到动画素材：{path}')
        image = QImage(512, 512, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        scale = self.idle_scale
        painter.drawImage(QRectF(256 * (1 - scale), 490 * (1 - scale),
                                 512 * scale, 512 * scale), source)
        painter.end()
        return image

    def active_walker(self):
        return self.diagonal if self.walk_style == 'frames_diagonal' else self.anchored

    def set_walk_style(self, style):
        if style not in self.style_actions:
            raise ValueError(f'Unknown walking style: {style}')
        self.walk_style = style
        state = self.perch_state if self.perch is not None else self.behavior.state
        side = 'left' if state == 'walk_left' else 'right'
        self.gait_time = self.gait_phase * self.active_walker().cycles[side].duration
        if self.transition and state.startswith('walk'):
            self.transition.frames[-1] = self.walking_image(side, 512)
        self.style_actions[style].setChecked(True)
        self.settings.setValue('walk_style', style)
        self.settings.sync()
        # Preserve phase, destination and rest/groom progress when switching.
        self.update()

    def walking_stride(self):
        if self.walk_style in ('frames_anchored', 'frames_diagonal'):
            side = 'left' if self.behavior.state == 'walk_left' else 'right'
            return self.active_walker().cycles[side].stride
        if self.walk_style == 'deform':
            return STRIDE
        side = 'left' if self.behavior.state == 'walk_left' else 'right'
        return self.walk_animations[self.walk_style][side][1].get('stride_pixels', 110)

    def gaze_image(self, image, key):
        return self.gaze.paint(image,key,(self.x(),self.y()),self.width())

    def update_gaze(self, dt):
        cursor = self.cursor_position()
        state = self.visible_state()
        if self.transfer is not None:
            target = self.transfer['target']
            x,y = target.x+self.width()/2,target.floor
        elif state.startswith('walk') and self.hunt.state == 'off':
            direction = -1 if state.endswith('left') else 1
            x,y = self.x()+self.width()/2+direction*self.width()*1.5,self.y()+self.height()*.55
        elif self.hunt.state != 'off' or abs(cursor.x()-self.x())<600:
            x,y = cursor.x(),cursor.y()
        else:
            x,y = self.x()+self.width()/2,self.y()+self.height()*.55
        self.gaze.follow(x,y,dt)

    def is_running(self):
        return (self.perch is None and self.hunt.state == 'off'
                and self.behavior.state.startswith('walk')
                and (self.running_requested or (self.behavior.enabled and self.rhythm.state == 'burst')))

    def perform_run(self, side):
        self.manual_perform('walk_'+side)
        if self.perch is None and self.jump is None and self.transfer is None:
            self.running_requested = True
            self.gait_time = self.gait_phase = 0.
            if self.transition:
                self.transition.frames[-1] = self.animations['run_'+side][0][0]

    def walking_image(self, side, size=None):
        if self.is_running():
            index = self.run_cycle.frame(self.gait_time)
            return self.gaze_image(self.animations['run_'+side][0][index],f'run_{side}/{index}')
        size = size or round(self.width() * self.devicePixelRatioF())
        if self.walk_style in ('frames_anchored', 'frames_diagonal'):
            return self.gaze_image(self.active_walker().render(side, self.gait_time, size),f'walk/{self.walk_style}/{side}')
        if self.walk_style == 'deform':
            return self.gaze_image(self.deform.render(side, self.gait_phase,size),f'walk/{self.walk_style}/{side}')
        frames, metadata = self.walk_animations[self.walk_style][side]
        seconds = self.gait_phase * sum(metadata['duration_ms']) / 1000
        first, second, amount = sequence_blend(
            seconds, metadata['playback_order_zero_based'], metadata['duration_ms'],
            metadata.get('transition_ms', 0))
        return self.gaze_image(blend_images(frames[first], frames[second], amount),f'walk/{self.walk_style}/{side}')

    def set_autonomy(self, enabled):
        self.behavior.enabled = enabled
        if self.perch is not None and not enabled and self.perch_state.startswith('walk'):
            self.set_perch_action('window_straddle')
        elif self.perch is None and self.drag_offset is None and self.jump is None:
            self.perform('idle')

    def visible_state(self):
        if self.drag_offset is not None:
            return 'held'
        if self.hunt.state != 'off':
            return 'hunt_' + self.hunt.state
        if self.transfer is not None and not self.transfer['ready']:
            return 'transfer_' + self.transfer['sample'].phase
        if self.jump is not None:
            return 'jump_' + self.jump['stage']
        if self.transition:
            return self.transition.current_state or self.behavior.state
        if self.perch is not None:
            return self.perch_state
        return self.behavior.state

    def visible_image(self):
        if self.hunt.state != 'off':
            side = 'right' if self.hunt.direction > 0 else 'left'
            if self.hunt.state == 'stalk':return self.walking_image(side, 512)
            if self.hunt.state in ('play_kick','play_lick'):
                return self.pose_image(self.hunt.state, self.hunt.elapsed)
            index = (0 if self.hunt.state == 'watch' else 1 if self.hunt.state == 'crouch'
                     else min(5,2+int(self.hunt.elapsed/.38*4)) if self.hunt.state == 'pounce'
                     else 6 if self.hunt.elapsed < .22 else 7)
            return self.gaze_image(self.animations['pounce_'+side][0][index],f'pounce_{side}/{index}')
        if self.transfer is not None and not self.transfer['ready']:
            return self.gaze_image(self.animations[self.transfer['animation']][0][self.transfer['sample'].frame],
                                   f"{self.transfer['animation']}/{self.transfer['sample'].frame}")
        if self.jump is not None and self.drag_offset is None:
            return self.pose_image(self.visible_state())
        if self.drag_offset is not None or (self.perch is not None and not self.transition):
            return self.pose_image(self.visible_state(), self.overlay_elapsed)
        return self.transition.image() if self.transition else self.pose_image()

    def pose_image(self, state=None, elapsed=None):
        state = state or self.behavior.state
        elapsed = self.behavior.elapsed if elapsed is None else elapsed
        if state.startswith('jump_'):
            index = {'jump_prepare': 0, 'jump_air': 1, 'jump_land': 2, 'jump_recover': 3}[state]
            return self.gaze_image(self.animations['jump_down'][0][index],f'jump_down/{index}')
        if state.startswith('walk'):
            return self.walking_image('left' if state == 'walk_left' else 'right', 512)
        if state == 'idle':
            first, second, amount = blink_at(elapsed)
            return blend_images(self.gaze_image(self.frames[first],f'idle/{first}'),self.gaze_image(self.frames[second],f'idle/{second}'),amount)
        frames, metadata = self.animations[state]
        index = sequence_frame(elapsed, metadata['playback_order_zero_based'],
                               metadata['duration_ms'])
        return self.gaze_image(frames[index],f'{state}/{index}')

    def begin_transition(self, previous, state, initial=None):
        first = initial if initial is not None else self.pose_image(previous)
        # Cancel even a same-state request: the old route may have a different
        # destination from the named pose currently on screen.
        self.transition = None
        poses, labels = [first], [previous]
        for following in transition_route(previous, state):
            if previous.startswith('walk') and following == 'idle':
                poses.extend(self.turn_frames[previous[5:]])
                labels.extend(['idle'] * len(self.turn_frames[previous[5:]]))
            elif following.startswith('walk'):
                side = following[5:]
                poses.extend(reversed(self.turn_frames[side]))
                labels.extend(['idle'] * len(self.turn_frames[side]))
                self.gait_phase = self.gait_time = 0.
            poses.append(self.pose_image(following, 0.))
            labels.append(following)
            previous = following
        if len(poses) > 1:
            self.transition = PoseTransition(poses, self.transition_seconds, labels)

    def perform(self, state):
        self.running_requested = False
        self.hunt.cancel()
        if self.transfer is not None:
            self.transfer['after'] = state
            return
        if self.jump is not None:
            if state not in ('window_perch', 'window_straddle'):
                self.jump['after'] = state
            return
        if state in ('window_perch', 'window_straddle') and self.perch is None:
            if self.try_attach_window(160):
                self.set_perch_action(state)
            return
        if self.perch is not None:
            if state in ('window_perch', 'window_straddle', 'idle', 'groom', 'walk_left', 'walk_right'):
                self.set_perch_action(state)
            else:
                self.jump_down(after=state)
            return
        previous, initial = self.visible_state(), self.visible_image()
        was_perched = self.perch is not None
        self.perch = None
        # Explicit walking requests in free mode return to a supported surface.
        if state.startswith('walk') and self.mode == 'free':
            self.mode = 'auto'
        self.behavior.start(state)
        if state.startswith('walk'):
            self.gait_phase = 0.
            self.gait_time = 0.
        self.begin_transition(previous, state, initial)
        if was_perched and self.route:
            self.route_position = self.route.project(self.x(), self.y())
        self.refresh_floor()
        self.update()

    def change_size(self, size):
        self.hunt.cancel()
        if self.transfer is not None:
            self.cancel_transfer(fall=True)
        self.resize(size, size)
        self.refresh_floor()

    def screen_surfaces(self):
        screens = QApplication.screens()
        snapshots = self.observer.snapshots() if hasattr(self.observer, 'snapshots') else {}
        if not snapshots:
            screen = self.screen() or QApplication.primaryScreen()
            snapshots[screen.name()] = self.observer.snapshot(int(self.winId()))
        monitor_names = match_monitors({name: data[0] for name, data in snapshots.items()},
                                       self.logical_screens())
        surfaces = []
        for screen in screens:
            g = screen.geometry()
            offset = max(0, g.bottom() - screen.availableGeometry().bottom())
            if screen.name() in monitor_names:
                monitor, work, bars, auto = snapshots[monitor_names[screen.name()]]
                offset = floor_offset(monitor, work, bars, auto) * g.height() / (monitor[3] - monitor[1])
            floor = g.y() + g.height() - max(3, offset if self.mode == 'auto' else 0)
            surfaces.append(Surface(screen.name(), g.x(), g.y(), g.width(), g.height(), floor))
        return surfaces

    def raise_pet(self):
        if not self.menu_open and not self.menu.isVisible():
            self.observer.keep_topmost(int(self.winId()))

    def logical_screens(self):
        screens = {}
        for screen in QApplication.screens():
            g = screen.geometry()
            screens[screen.name()] = (g.x(), g.y(), g.x() + g.width(), g.y() + g.height())
        return screens

    def perch_baseline(self, state=None):
        state = state or (self.visible_state() if self.perch else 'window_perch')
        native = self.animations[state][1]['contact_baseline_y'] if state in ('window_perch', 'window_straddle') else 490
        return native * self.height() / 512

    def window_snapshot(self):
        if self.window_observer is None:
            return None
        return self.window_observer.snapshot(exclude_hwnds=(int(self.winId()),))

    def apply_perch(self, placement):
        self.perch = placement.attachment
        self.rest_x, self.rest_y = placement.x, placement.y
        self.target_y, self.route_screen = placement.y, placement.screen
        self.perch_floor = placement.floor
        # Staying in contact takes priority over a delayed vertical ease when
        # the supporting window itself is moved or resized.
        self.move(round(self.rest_x), round(self.rest_y))

    def try_attach_window(self, snap_distance=32, previous=None, initial=None):
        if self.jump is not None or self.transfer is not None:
            return False
        try:
            snapshot = self.window_snapshot()
        except OSError:
            return False
        if snapshot is None:
            return False
        placement = choose_perch(
            snapshot, self.logical_screens(),
            (self.x() + self.width() / 2, self.y() + self.height() * 490 / 512),
            (self.width(), self.height()), baseline=self.perch_baseline('window_perch'),
            snap_distance=snap_distance)
        if placement is None:
            return False
        previous = previous or self.visible_state()
        initial = initial if initial is not None else self.visible_image()
        self.behavior.start('idle')
        self.overlay_elapsed = 0.
        self.perch_errors = 0
        self.perch_snapshot = snapshot
        self.perch_state = 'window_perch'
        self.perch_action_time = 0.
        self.perch_action_duration = self.behavior.rng.uniform(3.5, 6.)
        self.begin_transition(previous, 'window_perch', initial)
        self.apply_perch(placement)
        displayed = follow_perch(self.perch, snapshot, self.logical_screens(),
                                 (self.width(), self.height()), self.perch_baseline())
        if displayed is not None:
            self.apply_perch(displayed)
        self.update()
        return True

    def release_perch(self):
        if self.jump is not None:
            self.jump['stage'], self.jump['elapsed'] = 'air', 0.
            self.jump['motion'].velocity = 0.
            self.detach_for_jump()
        else:
            self.jump_down(airborne=True)

    def set_perch_action(self, state):
        if self.perch is None or self.jump is not None:
            return
        if self.perch_snapshot is not None and follow_perch(
                self.perch, self.perch_snapshot, self.logical_screens(),
                (self.width(), self.height()), self.perch_baseline(state)) is None:
            if state.startswith('walk'):
                self.perch_action_time = 0.
                return  # Keep resting when there isn't enough headroom to stand.
            # Near the screen bottom a hanging tail may not fit, but a low
            # prone rest still does. Never reverse travel while still facing
            # the old direction because a requested resting pose was rejected.
            state = 'window_perch'
            if follow_perch(self.perch, self.perch_snapshot, self.logical_screens(),
                            (self.width(), self.height()), self.perch_baseline(state)) is None:
                self.perch_action_time = 0.
                return
        previous, initial = self.visible_state(), self.visible_image()
        self.perch_state = state
        self.perch_action_time = self.overlay_elapsed = 0.
        self.perch_action_duration = self.behavior.rng.uniform(2.5, 5.) if state.startswith('walk') else self.behavior.rng.uniform(4., 8.)
        if self.behavior.enabled and self.rhythm.quiet and not state.startswith('walk'):
            self.perch_action_duration = self.rhythm.rest_duration()
        if state.startswith('walk'):
            self.perch_direction = -1 if state == 'walk_left' else 1
            self.gait_phase = self.gait_time = 0.
        self.begin_transition(previous, state, initial)
        self.update()

    def tick_perch(self, dt):
        if self.transition:
            if self.transition.advance(dt):
                self.transition = None
        else:
            self.overlay_elapsed += dt
            self.perch_action_time += dt
            state = self.perch_state
            if state.startswith('walk') and self.perch_snapshot is not None:
                side = state[5:]
                # Walk on the window with the same anchored gait, at a calmer pace.
                cycle = self.active_walker().cycles[side]
                gait_dt = dt * 1.3 * (self.rhythm.speed if self.behavior.enabled else 1.)
                anchored = self.walk_style in ('frames_anchored', 'frames_diagonal')
                distance = (cycle.travel(self.gait_time, gait_dt) if anchored else 120 * gait_dt) * self.width() / 512
                placement, travelled = advance_perch(
                    self.perch, self.perch_snapshot, self.logical_screens(),
                    (self.width(), self.height()), self.perch_direction * distance,
                    self.perch_baseline())
                if placement is None:
                    self.release_perch()
                    return
                self.apply_perch(placement)
                actual = abs(travelled) * 512 / self.width()
                if anchored and actual > 0:
                    self.gait_time = cycle.time_after_distance(self.gait_time, gait_dt, actual)
                    self.gait_phase = (self.gait_time / cycle.duration) % 1.
                elif not anchored:
                    stride = STRIDE if self.walk_style == 'deform' else self.walk_animations[self.walk_style][side][1].get('stride_pixels', 110)
                    self.gait_phase = (self.gait_phase + actual / stride) % 1.
                if abs(travelled) + 1e-5 < distance or self.perch_action_time >= self.perch_action_duration:
                    self.perch_direction *= -1
                    self.set_perch_action('window_straddle')
            elif self.behavior.enabled and self.perch_action_time >= self.perch_action_duration:
                if self.rhythm.quiet:
                    self.set_perch_action(self.rhythm.rest_pose(window=True))
                elif self.roam_cooldown <= 0:
                    self.roam_cooldown = self.rhythm.exploration_delay()
                    choice = self.behavior.rng.random()
                    if choice < .45 and self.start_transfer():
                        return
                    if choice > .85:
                        self.jump_down()
                        return
                # Alternate a lazy pose with short strolls; preserve both coats.
                if self.rhythm.quiet:
                    pass
                elif state == 'window_perch':
                    self.set_perch_action('window_straddle')
                else:
                    self.set_perch_action('walk_right' if self.perch_direction > 0 else 'walk_left')
        # A change in pose changes the canvas's contact baseline. Align every
        # displayed pose to the actual ledge, rather than sliding its paws in Y.
        if self.perch is not None and self.perch_snapshot is not None:
            placement = follow_perch(self.perch, self.perch_snapshot, self.logical_screens(),
                                     (self.width(), self.height()), self.perch_baseline())
            if placement is None:
                self.release_perch()
            else:
                self.apply_perch(placement)

    def manual_perform(self, state):
        self.manual_activity_time = 20.
        self.perform(state)

    def set_hunt_enabled(self, enabled):
        self.hunt_enabled = enabled
        self.hunt.cancel()
        if enabled:
            self.mode = 'auto'
            if self.transfer is not None or self.perch is not None:
                self.jump_down()
            elif self.jump is None:
                self.perform('idle')
        elif self.jump is None and self.transfer is None:
            self.perform('idle')
        self.refresh_floor()

    def tick_hunt(self, dt):
        if (not self.hunt_enabled or self.mode == 'free' or self.perch is not None
                or self.transfer is not None or self.jump is not None or self.route is None):
            return False
        lane = next((s for s in self.route.lanes if s.name == self.route_screen), None)
        if lane is None:
            self.hunt.cancel()
            return False
        if self.hunt.state == 'off' and (self.transition or abs(self.y()-self.target_y)>3):
            return False
        cursor = self.cursor_position()
        previous = self.hunt.state
        previous_image = self.visible_image() if previous != 'off' else None
        before = self.rest_x
        x = self.hunt.step(dt, before, (cursor.x(),cursor.y()), lane, self.width())
        if self.hunt.state == 'off':
            if previous != 'off':
                self.behavior.start('idle')
                self.begin_transition('rest_prone','idle',previous_image)
                self.rest_y = self.target_y
                self.move(round(self.rest_x),round(self.rest_y))
            return False
        self.transition = None
        if previous == 'off':self.gait_time = self.gait_phase = 0.
        if self.hunt.state == 'stalk':
            side = 'right' if self.hunt.direction > 0 else 'left'
            cycle = self.active_walker().cycles[side]
            distance = abs(x-before)*512/self.width()
            self.gait_time = cycle.time_after_distance(self.gait_time, dt*3, distance)
            self.gait_phase = self.gait_time/cycle.duration % 1.
        self.rest_x = x
        self.route_position = self.route.project(x,self.target_y)
        self.rest_y = self.target_y-self.hunt.height
        self.move(round(x),round(self.rest_y))
        self.update()
        return True

    def set_activity(self, state):
        self.rhythm.enter(state)
        self.rhythm_pending = True
        self.manual_activity_time = 0.
        self.auto_action.setChecked(True)
        if not self.behavior.enabled:
            self.set_autonomy(True)
        self.update_activity(0.)

    def update_activity(self, dt):
        if not self.behavior.enabled:
            return
        self.manual_activity_time = max(0., self.manual_activity_time - dt)
        if self.rhythm.advance(dt):
            self.rhythm_pending = True
        self.mood_status.setText('当前：' + self.rhythm.LABELS[self.rhythm.state])
        if (not self.rhythm_pending or self.manual_activity_time > 0 or self.transfer is not None
                or self.jump is not None or self.transition is not None):
            return
        self.rhythm_pending = False
        self.roam_cooldown = 2. if not self.rhythm.quiet else self.rhythm.duration
        if self.rhythm.quiet:
            self.perform(self.rhythm.rest_pose(window=self.perch is not None))
        elif self.perch is not None:
            self.set_perch_action('walk_right' if self.perch_direction > 0 else 'walk_left')
        else:
            self.perform('idle')
            self.behavior.duration = .5

    def set_climb_style(self, style):
        if style not in self.climb_actions:
            raise ValueError(f'Unknown climbing style: {style}')
        self.climb_style = style
        self.climb_actions[style].setChecked(True)
        self.settings.setValue('climb_style', style)
        self.settings.sync()
        # An ongoing jump keeps its artwork and contact anchors until landing.

    def start_transfer(self, checked=False, *, upward_only=False):
        self.hunt.cancel()
        if self.drag_offset is not None or self.jump is not None or self.transfer is not None:
            return False
        try:
            snapshot = self.window_snapshot()
        except OSError:
            return False
        if snapshot is None:
            return False
        origin = (self.rest_x + self.width() / 2,
                  self.perch_floor if self.perch else self.y() + self.height() * 490 / 512)
        animation = {'back': 'window_climb_back', 'side': 'window_climb_side',
                     'front_hidden': 'window_climb'}[self.climb_style]
        anchors = self.animations[animation][1]['contact_baselines_y']
        motion = choose_transfer(snapshot, self.logical_screens(), origin, self.width(), anchors,
                                 self.perch.hwnd if self.perch else None, upward_only)
        if motion is None:
            return False
        previous, initial = self.visible_state(), self.visible_image()
        self.behavior.start('idle')
        self.begin_transition(previous, 'idle', initial)
        self.transfer = dict(motion=motion, target=motion.destination, display_target=motion.destination, ready=True,
                             sample=motion.sample(), errors=0, after='window_perch',
                             style=self.climb_style, animation=animation, snapshot=snapshot)
        self.roam_cooldown = 18.
        return True

    def cancel_transfer(self, *, fall=False):
        transfer = self.transfer
        if transfer is None:
            return
        airborne = not transfer['ready'] and transfer['motion'].elapsed >= .18
        self.transfer = None
        self.transition = None
        self.roam_cooldown = 18.
        if fall or airborne:
            self.perch = self.perch_snapshot = None
            self.jump_down(airborne=True)
        else:
            self.behavior.start('idle')
            self.refresh_floor()
        self.update()

    def refresh_transfer(self):
        transfer = self.transfer
        try:
            snapshot = self.window_snapshot()
        except OSError:
            transfer['errors'] += 1
            if transfer['errors'] < 3:
                return
            snapshot = None
        else:
            transfer['errors'] = 0
        target = (follow_perch(transfer['target'].attachment, snapshot, self.logical_screens(),
                              (self.width(), self.height()), self.height() * 490 / 512)
                  if snapshot is not None else None)
        old = transfer['target']
        if target is None or math.hypot(target.x-old.x, target.floor-old.floor) > self.width() * .7:
            self.cancel_transfer()
            return
        motion = transfer['motion']
        if transfer['ready'] or motion.elapsed < .18:
            if self.perch is not None:
                source = follow_perch(self.perch, snapshot, self.logical_screens(),
                                      (self.width(), self.height()), self.perch_baseline())
                if source is None:
                    self.cancel_transfer(fall=True)
                    return
                self.perch_snapshot = snapshot
                self.apply_perch(source)
                motion.origin = (source.x + self.width()/2, source.floor)
        transfer['target'] = target
        transfer['snapshot'] = snapshot
        # Recheck the remaining path when a window or display changes.
        for i in range(21):
            t = motion.elapsed + (motion.duration-motion.elapsed) * i / 20
            sample = motion.sample(t, target)
            if not canvas_on_screens(sample.x, sample.y, self.width(), self.height() * 490 / 512, self.logical_screens()):
                self.cancel_transfer()
                return

    def tick_transfer(self, dt):
        transfer = self.transfer
        if transfer['ready']:
            if self.transition and not self.transition.advance(dt):
                self.update()
                return
            self.transition = None
            transfer['ready'] = False
            motion = transfer['motion']
            motion.origin = (self.rest_x + self.width()/2,
                             self.perch_floor if self.perch else self.y() + self.height()*490/512)
            self.refresh_transfer()
            if self.transfer is None:
                return
        motion = transfer['motion']
        motion.elapsed += dt
        if motion.elapsed >= .18:
            self.perch = self.perch_snapshot = None
        target, displayed = transfer['target'], transfer['display_target']
        amount = 1 - math.exp(-18 * dt)
        displayed = replace(target, x=displayed.x + (target.x-displayed.x)*amount,
                            floor=displayed.floor + (target.floor-displayed.floor)*amount)
        transfer['display_target'] = displayed
        sample = motion.sample(destination=displayed)
        if not canvas_on_screens(sample.x, sample.y, self.width(), self.height() * 490 / 512, self.logical_screens()):
            self.cancel_transfer(fall=True)
            return
        transfer['sample'] = sample
        self.rest_x, self.rest_y = sample.x, sample.y
        self.move(round(sample.x), round(sample.y))
        if (motion.elapsed >= motion.duration
                and math.hypot(displayed.x-target.x, displayed.floor-target.floor) < 1.):
            self.refresh_transfer()
            if self.transfer is None:
                return
            target = transfer['target']
            self.transfer = None
            self.perch_snapshot = transfer['snapshot']
            self.perch_state = 'idle'
            self.apply_perch(target)
            self.overlay_elapsed = self.perch_action_time = 0.
            self.perch_action_duration = self.behavior.rng.uniform(4., 8.)
            self.transition = PoseTransition([self.animations[transfer['animation']][0][7], self.frames[0]],
                                             .20, ['idle', 'idle'])
            self.perform(transfer['after'])
        self.update()

    def jump_down(self, checked=False, *, airborne=False, after='idle'):
        if self.transfer is not None:
            self.cancel_transfer(fall=True)
            return
        self.roam_cooldown = 18.
        if self.jump is not None or self.drag_offset is not None:
            return
        if self.perch is None and not airborne:
            return
        foot = (self.perch_floor if self.perch is not None else
                self.y() + self.height() * 490 / 512)
        self.transition = None
        if self.mode == 'free':
            self.mode = 'auto'
        self.behavior.start('idle')
        self.jump = {'stage': 'air' if airborne else 'prepare', 'elapsed': 0.,
                     'motion': GravityDescent(foot, velocity=0. if airborne else -55.), 'after': after}
        if airborne:
            self.detach_for_jump()
        else:
            self.refresh_floor()
        self.rest_y = foot - self.height() * 490 / 512
        self.move(round(self.rest_x), round(self.rest_y))
        self.update()

    def detach_for_jump(self):
        self.perch = self.perch_snapshot = None
        self.perch_errors = 0
        if self.route:
            self.route_position = self.route.project(self.x(), self.y())
        self.refresh_floor()

    def tick_jump(self, dt):
        jump = self.jump
        jump['elapsed'] += dt
        if jump['stage'] == 'prepare':
            # The support may move while she crouches, before the actual launch.
            jump['motion'].foot_y = self.perch_floor
            if jump['elapsed'] >= .28:
                jump['stage'], jump['elapsed'] = 'air', 0.
                self.detach_for_jump()
        elif jump['stage'] == 'air':
            floor = self.target_y + self.height() * 490 / 512
            if jump['motion'].advance(dt, floor):
                jump['stage'], jump['elapsed'] = 'land', 0.
        elif jump['stage'] == 'land' and jump['elapsed'] >= .16:
            jump['stage'], jump['elapsed'] = 'recover', 0.
        elif jump['stage'] == 'recover' and jump['elapsed'] >= .26:
            initial = self.pose_image('jump_recover')
            after = jump['after']
            self.jump = None
            self.behavior.start(after)
            self.begin_transition('rest_prone', after, initial)
        if jump['stage'] in ('land', 'recover'):
            jump['motion'].foot_y = self.target_y + self.height() * 490 / 512
        self.rest_y = jump['motion'].foot_y - self.height() * 490 / 512
        self.move(round(self.rest_x), round(self.rest_y))
        self.update()

    def refresh_floor(self):
        if self.drag_offset is not None:
            return
        if self.transfer is not None:
            self.refresh_transfer()
            return
        if self.perch is not None:
            try:
                snapshot = self.window_snapshot()
            except OSError:
                # A brief native race is harmless; persistent failure must not
                # strand the cat on a support we can no longer observe.
                self.perch_errors += 1
                if self.perch_errors < 3:
                    return
                snapshot = None
            else:
                self.perch_errors = 0
                self.perch_snapshot = snapshot
            placement = (follow_perch(self.perch, snapshot, self.logical_screens(),
                                      (self.width(), self.height()), self.perch_baseline())
                         if snapshot is not None else None)
            if placement is not None:
                self.apply_perch(placement)
                return
            self.release_perch()
        if self.mode == 'free':
            return
        try:
            route = DesktopRoute(self.screen_surfaces(), self.width())
        except OSError:
            # Shell restart: retain the last known surface until the next poll.
            return
        if self.route is None or route.signature != self.route.signature:
            self.route_position = route.project(self.x(), self.y())
            if self.route is not None:
                self.behavior.stop_x = None  # A hot-plug/resize invalidates the old waypoint.
        self.route = route
        self.rest_x, self.target_y, self.route_screen = route.locate(self.route_position)

    def tick(self):
        now = time.monotonic()
        dt = max(0., min(now - self.last_tick, .1))
        self.last_tick = now
        if self.drag_offset is not None:
            self.update_gaze(dt)
            self.overlay_elapsed += dt
            self.held_sway.update(dt, self.held_dx)
            self.held_dx = 0.
            self.update()
            return
        if self.menu_open or self.menu.isVisible():
            return
        self.update_gaze(dt)
        if self.tick_hunt(dt):
            return
        self.update_activity(dt)
        self.roam_cooldown = max(0., self.roam_cooldown - dt)
        if self.transfer is not None:
            self.tick_transfer(dt)
            return
        if self.jump is not None:
            self.tick_jump(dt)
            return
        if self.perch is not None:
            self.tick_perch(dt)
            self.update()
            return
        grounded = (self.target_y is not None and abs(self.y() - self.target_y) < 3)
        if (grounded and not self.hunt_enabled and self.mode != 'free' and self.behavior.enabled and not self.rhythm.quiet
                and self.manual_activity_time <= 0
                and not self.transition and not self.behavior.state.startswith('walk')
                and self.behavior.elapsed >= 2 and self.roam_cooldown <= 0):
            self.roam_cooldown = self.rhythm.exploration_delay()
            if self.start_transfer(upward_only=True):
                return
        # All walking styles share patrol and freeze when movement pauses.
        previous_state, previous_position = self.behavior.state, self.route_position
        previous_elapsed = self.behavior.elapsed
        activity_speed = self.rhythm.speed if self.behavior.enabled else 1.
        running = self.is_running()
        running_image = self.walking_image('left' if previous_state == 'walk_left' else 'right',512) if running else None
        gait_dt = dt * (1.15 if self.rhythm.state == 'burst' else 1.) if running else dt * WALK_SPEED_MULTIPLIER * activity_speed
        speed = 120 * WALK_SPEED_MULTIPLIER * activity_speed * self.width() / 512
        side = 'left' if previous_state == 'walk_left' else 'right'
        cycle = self.run_cycle if running else self.active_walker().cycles[side]
        anchored = running or self.walk_style in ('frames_anchored', 'frames_diagonal') and previous_state.startswith('walk')
        if anchored and dt > 0:
            speed = cycle.travel(self.gait_time, gait_dt) * self.width() / 512 / dt
        if self.transition:
            if self.transition.advance(dt):
                self.transition = None
        else:
            self.route_position = self.behavior.advance(
                dt, self.route_position, 0, self.route.length if self.route else 0,
                speed=speed, can_walk=self.mode != 'free', surface_moving=not grounded,
                stop_filter=self.route.safe_stop if self.route else None)
        travelled = abs(self.route_position - previous_position)
        if anchored and travelled > 0:
            self.gait_time = cycle.time_after_distance(self.gait_time, gait_dt, travelled * 512 / self.width())
            self.gait_phase = (self.gait_time / cycle.duration) % 1.
        elif previous_state.startswith('walk'):
            self.gait_phase = (self.gait_phase + travelled
                               / (self.walking_stride() * self.width() / 512)) % 1.
        if self.behavior.state != previous_state:
            self.running_requested = False
            self.begin_transition(previous_state, self.behavior.state,
                                  running_image if running_image is not None else self.pose_image(previous_state, elapsed=previous_elapsed))
        if self.route and self.mode != 'free':
            self.rest_x, new_y, screen_name = self.route.locate(self.route_position)
            # Different-height or stacked screens reconnect at the destination floor.
            # No interpolation through empty desktop gaps. Taskbar motion on the SAME
            # screen continues to use the smooth vertical follower below.
            if screen_name != self.route_screen:
                self.rest_y = new_y
            self.route_screen = screen_name
            self.target_y = new_y
        y = self.y()
        if self.drag_offset is None and self.mode != 'free' and self.target_y is not None:
            if self.rest_y is None:
                self.rest_y = float(self.y())
            self.rest_y += (self.target_y - self.rest_y) * (1 - math.exp(-18 * dt))
            y = round(self.rest_y)
        self.move(round(self.rest_x), y)
        self.update()

    def render_frame(self, size=None):
        """Composite cat and contact shadow once, preserving the sprite's alpha."""
        size = size or round(self.width() * self.devicePixelRatioF())
        state = self.visible_state()
        image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        bounds = QRectF(0, 0, size, size)
        free = self.mode == 'free' and self.perch is None
        shadow_state = 'free' if free or state.startswith('transfer_') or state == 'hunt_pounce' else state
        floor_ratio = self.perch_baseline() / self.height() if self.perch else 490 / 512
        key = (size, shadow_state, floor_ratio)
        if key not in self.shadow_cache:
            # Resizing or moving across DPI scales shouldn't grow an unbounded cache.
            if len(self.shadow_cache) >= 40:
                self.shadow_cache.clear()
            self.shadow_cache[key] = contact_shadow(size, shadow_state, floor_ratio=floor_ratio)
        opacity = 1.
        if self.perch is None and self.target_y is not None:
            opacity = max(0., 1. - abs(self.y() - self.target_y) / 30)
        painter.setOpacity(opacity)
        painter.drawImage(bounds, self.shadow_cache[key])
        painter.setOpacity(1.)
        if state == 'held' and self.drag_offset is not None:
            pivot = self.animations['held'][1]['pivot_px']
            painter.translate(pivot[0] * size / 512, pivot[1] * size / 512)
            painter.rotate(self.held_sway.angle)
            painter.translate(-pivot[0] * size / 512, -pivot[1] * size / 512)
        elif not self.transition and state.startswith('walk'):
            # Keep the stance anchor's fractional desktop position after the
            # native HWND position has been rounded to an integer.
            bounds.translate((self.rest_x - round(self.rest_x)) * size / self.width(), 0)
        pose = (self.walking_image(state[5:], size)
                if state.startswith('walk') and not self.transition else self.visible_image())
        if state == 'transfer_climb':
            strength = self.transfer['sample'].blur
            for offset, alpha in ((12, .045), (6, .09)):
                painter.setOpacity(strength * alpha)
                painter.drawImage(bounds.translated(0, offset * size / 512), pose)
            painter.setOpacity(1.)
        # SourceOver is essential: transparent cat pixels must retain the shadow.
        painter.drawImage(bounds, pose)
        if (self.transfer is not None and not self.transfer['ready']
                and self.transfer['style'] == 'front_hidden'):
            # Clear only real target-window coverage, including the blur trail.
            # Keep the native pet window topmost: no activation/z-order churn.
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.setOpacity(1.)
            scale = size / self.width()
            for rect in window_occlusion_rects(self.transfer['snapshot'], self.logical_screens(),
                                               self.transfer['target'].attachment):
                painter.fillRect(QRectF((rect.left-self.x())*scale, (rect.top-self.y())*scale,
                                        rect.width*scale, rect.height*scale), Qt.GlobalColor.transparent)
        painter.end()
        return image

    def paintEvent(self, event):
        image = self.render_frame()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.drawImage(self.rect(), image)
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.hunt.cancel()
            self.perch = self.perch_snapshot = self.jump = self.transfer = None
            self.roam_cooldown = 18.
            self.transition = None
            self.behavior.start('idle')
            self.drag_offset = event.globalPosition().toPoint() - self.pos()
            self.overlay_elapsed = self.held_dx = 0.
            self.held_sway.reset()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.update()

    def mouseMoveEvent(self, event):
        if self.drag_offset is not None:
            destination = event.globalPosition().toPoint() - self.drag_offset
            self.held_dx += destination.x() - self.x()
            self.move(destination)
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.drag_offset is not None:
            # Preserve the actual swung drawing at release, so a moving cat
            # doesn't snap upright before the landing transition starts.
            initial = self.render_frame(512)
            self.drag_offset = None
            self.unsetCursor()
            self.held_sway.reset()
            self.held_dx = 0.
            self.rest_y = float(self.y())
            self.rest_x = float(self.x())
            if self.try_attach_window(previous='held', initial=initial):
                return
            self.behavior.start('idle')
            self.begin_transition('held', 'idle', initial)
            if self.route:
                self.route_position = self.route.project(self.x(), self.y())
            self.refresh_floor()
            if self.mode != 'free' and self.target_y is not None and self.target_y - self.y() > 24:
                self.jump_down(airborne=True)
            self.update()

    def contextMenuEvent(self, event):
        self.menu_open = True
        try:
            self.menu.exec(event.globalPos())
        finally:
            self.menu_open = False


def main():
    if sys.platform != 'win32':
        raise SystemExit('请使用 Windows Python 启动，本程序需要 Windows 11 桌面环境。')
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    pet = DesktopCat()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
