import tkinter as tk
import random
import time


def create_animated_popup(text, color, duration=5):
    """创建带动画效果的单个弹窗"""
    window = tk.Tk()

    # 屏幕尺寸
    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()

    # 窗口尺寸
    width, height = 250, 80
    x = random.randint(0, screen_width - width)
    y = random.randint(0, screen_height - height)

    window.geometry(f"{width}x{height}+{x}+{y}")
    window.title("✨")
    window.configure(bg=color)
    window.attributes('-topmost', True)  # 置顶

    # 文本标签
    label = tk.Label(
        window,
        text=text,
        font=("Arial", 12, "bold"),
        bg=color,
        fg="white",
        wraplength=200
    )
    label.pack(expand=True, pady=10)

    # 自动关闭
    window.after(duration * 1000, window.destroy)

    return window


def popup_rain_advanced(texts, colors, count=40, delay=0.08):
    """
    高级弹窗雨
    :param texts: 文本列表
    :param colors: 颜色列表
    :param count: 弹窗数量
    :param delay: 间隔时间
    """
    windows = []

    for _ in range(count):
        text = random.choice(texts)
        color = random.choice(colors)
        window = create_animated_popup(text, color, duration=random.randint(3, 8))
        windows.append(window)
        window.update()
        time.sleep(delay)

    # 保持运行
    if windows:
        windows[0].mainloop()


# 使用示例
if __name__ == "__main__":
    # 自定义文本列表
    my_texts = [
        "别回头 别停留 往前走",
        "我会站在你身后",
        "纵有万难 也与你携手",
        "等花开 或是风霜依旧",
        "同甘苦 亦共白首",
        "春秋几度 此心永不朽"
    ]

    # 自定义颜色列表（十六进制或颜色名）
    my_colors = [
        '#FF6B6B',  # 红色
        '#4ECDC4',  # 青色
        '#45B7D1',  # 蓝色
        '#FFA07A',  # 橙色
        '#98D8C8',  # 绿色
        '#9B59B6',  # 紫色
    ]

    popup_rain_advanced(my_texts, my_colors, count=99, delay=0.05)