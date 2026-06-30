# 3D Heart Particles

一个用 Python、OpenCV、NumPy 和 Pillow 生成发光 3D 粒子爱心动画的小项目。脚本可以打开实时预览窗口，也可以导出 MP4 视频；爱心中央的文字支持英文、中文、日文假名和韩文字符。

## 功能

- 生成由粒子组成的 3D 爱心轮廓
- 在爱心中央渲染自定义文字
- 粒子从画面下方聚拢成形，并带有呼吸、闪烁和光晕效果
- 支持实时预览和 MP4 导出
- 针对中文等 CJK 字符做了字体选择和采样优化

## 环境要求

- Python 3.9 或更高版本
- Windows 环境推荐使用，脚本默认查找 `C:/Windows/Fonts` 下的字体
- 依赖包：
  - `opencv-python`
  - `numpy`
  - `Pillow`

安装依赖：

```powershell
pip install opencv-python numpy Pillow
```

## 快速开始

打开实时预览：

```powershell
python heart_3d_particles.py
```

预览窗口操作：

- 按 `Esc` 或 `q` 退出
- 鼠标左键拖动窗口
- 默认是无边框窗口，加入 `--windowed` 可以显示正常标题栏

## 导出视频

导出默认设置的视频：

```powershell
python heart_3d_particles.py --output heart_output.mp4
```

导出自定义文字的视频：

```powershell
python heart_3d_particles.py --text "LOVE" --output love.mp4
```

导出中文文字：

```powershell
python heart_3d_particles.py --text "蓝蓝" --output lanlan.mp4
```

## 常用参数

| 参数 | 说明 | 默认值 |
| --- | --- | --- |
| `--text` | 爱心中央的文字 | `ZY` |
| `--output` | 输出 MP4 路径；不传则打开实时预览 | 空 |
| `--width` | 画面宽度 | 预览 `900`，导出 `1112` |
| `--height` | 画面高度 | 预览 `580`，导出 `720` |
| `--fps` | 帧率 | 预览 `24`，导出 `30` |
| `--duration` | 导出视频时长，单位秒 | `13.6` |
| `--particles` | 粒子数量 | 预览 `1800`，导出 `2400` |
| `--bg-alpha` | 背景亮度强度，范围 `0.0` 到 `1.0` | `1.0` |
| `--window-alpha` | 预览窗口透明度，范围 `0.15` 到 `1.0` | `1.0` |
| `--windowed` | 使用普通窗口边框显示预览 | 关闭 |

示例：导出 6 秒、1080p、更多粒子的版本：

```powershell
python heart_3d_particles.py --width 1920 --height 1080 --duration 6 --particles 5000 --text "LOVE" --output heart_1080p.mp4
```

## 项目文件

- `heart_3d_particles.py`：主程序，包含粒子生成、运动、投影、渲染、预览和导出逻辑
- `heart_preview*.mp4`、`heart_*_test.mp4`：已有的测试或预览视频
- `heart_*.png`、`frames_*.png`：已有的预览帧或导出截图

## 代码结构

主脚本的大致流程如下：

1. `make_particles()` 生成爱心轮廓粒子、文字粒子和随机起始位置
2. `particle_motion()` 根据时间计算粒子从散开到聚拢的动画位置
3. `project()` 把 3D 坐标投影到 2D 画布
4. `draw_particles()` 或 `draw_particles_fast()` 绘制粒子和光晕
5. `play_live()` 打开实时预览，`render_video()` 导出 MP4

## 注意事项

- 导出视频比实时预览更精细，因此渲染时间会更长。
- 如果中文字体显示不理想，可以在 `load_text_font()` 里调整字体候选列表。
- OpenCV 的 `mp4v` 编码在大多数环境可用；如果无法写入视频，可以尝试更换输出路径或安装完整的 OpenCV/视频编码支持。
