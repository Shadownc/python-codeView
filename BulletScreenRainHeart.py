import tkinter as tk
import random
import time
import math


def generate_heart_positions(num_points, screen_width, screen_height):
    """生成爱心形状的坐标点"""
    positions = []
    center_x = screen_width // 2
    center_y = screen_height // 2

    # 爱心参数方程
    for i in range(num_points):
        t = (i / num_points) * 2 * math.pi

        # 爱心曲线方程
        x = 16 * math.sin(t) ** 3
        y = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))

        # 缩放和平移到屏幕中心
        scale = min(screen_width, screen_height) // 40
        pos_x = int(center_x + x * scale - 125)  # 125是窗口宽度的一半
        pos_y = int(center_y + y * scale - 40)  # 40是窗口高度的一半

        # 确保在屏幕范围内
        pos_x = max(0, min(pos_x, screen_width - 250))
        pos_y = max(0, min(pos_y, screen_height - 80))

        positions.append((pos_x, pos_y))

    return positions


def create_heart_popup(text, color, x, y):
    """创建爱心位置的弹窗"""
    window = tk.Toplevel()

    # 窗口尺寸
    width, height = 250, 80

    window.geometry(f"{width}x{height}+{x}+{y}")
    window.title("✨")
    window.configure(bg=color)
    window.attributes('-topmost', True)
    window.overrideredirect(True)

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

    # 存储label以便后续修改
    window.label = label

    return window


def animate_to_center(window, start_x, start_y, target_x, target_y, duration=800):
    """让窗口快速移动到目标位置"""
    steps = 30  # 减少步数,加快速度
    delay = duration // steps

    def move_step(step):
        if step <= steps:
            progress = step / steps
            # 缓动效果
            eased_progress = progress * progress * (3 - 2 * progress)

            current_x = int(start_x + (target_x - start_x) * eased_progress)
            current_y = int(start_y + (target_y - start_y) * eased_progress)

            try:
                window.geometry(f"+{current_x}+{current_y}")
                window.after(delay, lambda: move_step(step + 1))
            except:
                pass

    move_step(0)


def popup_rain_heart(texts, colors, count=99, delay=0.03):
    """
    爱心形状的弹窗雨,快速汇聚,最后一个显示"我好想你"
    :param texts: 文本列表
    :param colors: 颜色列表
    :param count: 弹窗数量
    :param delay: 间隔时间
    """
    global root
    root = tk.Tk()
    root.withdraw()

    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()

    # 生成爱心形状的位置
    positions = generate_heart_positions(count, screen_width, screen_height)

    # 计算目标中心位置
    target_x = (screen_width - 250) // 2
    target_y = (screen_height - 80) // 2

    windows = []

    print("🎨 开始绘制爱心...")

    # 第一阶段:按爱心形状显示弹窗
    for i in range(count):
        text = random.choice(texts)
        color = random.choice(colors)
        x, y = positions[i]

        window = create_heart_popup(text, color, x, y)
        windows.append((window, x, y))
        root.update()
        time.sleep(delay)

    print("❤️ 爱心绘制完成!保持显示...")

    # 保持完整爱心显示(缩短到2秒)
    time.sleep(0.5)

    print("✨ 开始快速汇聚...")

    # 第二阶段:所有窗口同时向中心汇聚(加快速度)
    for window, x, y in windows:
        try:
            animate_to_center(window, x, y, target_x, target_y, duration=800)  # 从1500缩短到800毫秒
        except:
            pass

    root.update()

    # 等待汇聚完成(缩短等待时间)
    time.sleep(0.7)

    print("💖 修改最上层窗口为'我好想你'...")

    # 定义关闭所有窗口的函数
    def close_all_windows():
        """关闭所有窗口并退出"""
        print("👋 关闭所有窗口...")
        for window, _, _ in windows:
            try:
                window.destroy()
            except:
                pass
        try:
            root.quit()
            root.destroy()
        except:
            pass

    # 修改最后一个窗口(最上层)的内容为"我好想你"
    if windows:
        last_window = windows[-1][0]
        try:
            bg_color = '#2C3E50'  # 深蓝灰
            text_color = '#FFB6C1'  # 淡粉色文字
            blink_color = '#FF69B4'  # 亮粉色闪烁
            button_bg = '#34495E'
            button_hover = '#2C3E50'
            # 修改背景色
            last_window.configure(bg=bg_color)
            # 修改文本
            last_window.label.config(
                text="我好想你",
                font=("Arial", 20, "bold"),
                bg=bg_color,
                fg=text_color
            )
            last_window.title("💖")

            # 添加闪烁效果
            def blink(count=0):
                if count < 8:
                    current_color = last_window.label.cget("fg")
                    new_color = blink_color if current_color == text_color else text_color
                    try:
                        last_window.label.config(fg=new_color)
                        last_window.after(400, lambda: blink(count + 1))
                    except:
                        pass

            blink()

            # 添加透明背景的关闭按钮
            try:
                close_btn = tk.Button(
                    last_window,
                    text="( ´◔ ‸◔`)",
                    command=close_all_windows,  # 修改为关闭所有窗口
                    font=("Arial", 9),
                    bg=button_bg,  # 使用与窗口相同的背景色
                    fg='white',
                    relief=tk.FLAT,  # 扁平样式
                    bd=0,  # 无边框
                    padx=8,
                    pady=2,
                    activebackground=button_hover,  # 鼠标悬停时的颜色
                    activeforeground='white',
                    cursor='hand2'  # 手型鼠标指针
                )
                close_btn.pack(side=tk.BOTTOM, pady=3)
            except:
                pass

        except Exception as e:
            print(f"修改窗口时出错: {e}")

    root.mainloop()


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

    # 自定义颜色列表
    my_colors = [
        '#FF1493',  # 深粉色
        '#FF69B4',  # 亮粉色
        '#FFB6C1',  # 浅粉色
        '#FFC0CB',  # 粉红色
        '#FF6B6B',  # 红色
        '#FF4500',  # 橙红色
        '#C71585',  # 深紫红
        '#FFB3BA',  # 淡粉
        '#FF8FAB',  # 樱花粉
        '#FF85A2',  # 蜜桃粉
        '#4ECDC4',  # 青色
        '#45B7D1',  # 蓝色
    ]

    popup_rain_heart(my_texts, my_colors, count=99, delay=0.03)
