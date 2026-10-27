# 三花桌宠 · Desktop Cat

Windows 11 上的 Python / PySide6 卡通三花猫桌宠。左右花纹独立，带透明置顶窗口、动画和自主活动。

## 启动

1. 安装 Windows 版 Python 3.10 或更新版本（建议 3.12），包含 Python Launcher。
2. 下载或克隆整个仓库，保留 `assets` 和 `output/imagegen` 目录。
3. 双击 `start_cat.bat`，首次运行自动创建虚拟环境并安装依赖。

如需代理，将 `proxy.example.bat` 复制为 `proxy.local.bat`，填写自己的地址。该本地配置不会上传 Git。也可使用已有的 `HTTP_PROXY` / `HTTPS_PROXY` 环境变量。

## 功能

- 多显示器底沿巡逻，支持自动隐藏任务栏。
- 坐着、舔毛、趴着、侧卧、仰躺，以及休息、活动、短暂撒欢的行为节奏。
- 左右独立行走和奔跑素材；保留多种可切换的行走效果。
- 拖动抱起、窗沿休息和移动、跳下、跨窗跳跃及攀爬。
- 屏幕底部鼠标捕猎、左右扑跃、抓到后的蹬踢和舔舐，眼睛跟随目标。
- 右键猫咪或托盘图标可调整行为、大小、位置和退出。

详细操作与已知限制见 [使用说明](使用说明.txt)。原生窗口交互需在 Windows 上运行；部分窗口没有足够空间供猫咪停靠。

## 开发

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe desktop_cat.py
```

运行测试：

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv\Scripts\python.exe -m unittest discover -v
```

`tools` 包含素材整理、预览和原生交互检查脚本；部分素材工具另需 Pillow。原始猫咪照片、虚拟环境、本机配置和预览输出不随仓库分发；程序使用的动画素材保留在 `output/imagegen`，眼睛标注位于 `assets`。
