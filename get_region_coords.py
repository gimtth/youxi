"""
获取游戏区域坐标的辅助工具
使用方法：运行后将鼠标移动到游戏区域的角落，按空格键记录坐标
"""

import pyautogui
import keyboard
import time

def get_coordinates():
    """获取游戏区域坐标"""
    print("=" * 60)
    print("游戏区域坐标获取工具")
    print("=" * 60)
    print("\n使用说明:")
    print("1. 将鼠标移动到游戏区域的左上角")
    print("2. 按空格键记录第一个点")
    print("3. 将鼠标移动到游戏区域的右下角")
    print("4. 按空格键记录第二个点")
    print("5. 按 ESC 键退出")
    print("\n准备就绪，等待输入...")
    
    points = []
    
    def on_space():
        """空格键按下时记录坐标"""
        x, y = pyautogui.position()
        points.append((x, y))
        
        if len(points) == 1:
            print(f"\n✓ 左上角坐标: ({x}, {y})")
            print("请移动鼠标到右下角，然后按空格键...")
        elif len(points) == 2:
            print(f"✓ 右下角坐标: ({x}, {y})")
            
            x1, y1 = points[0]
            x2, y2 = points[1]
            
            # 确保坐标顺序正确
            x1, x2 = min(x1, x2), max(x1, x2)
            y1, y2 = min(y1, y2), max(y1, y2)
            
            print("\n" + "=" * 60)
            print("游戏区域坐标:")
            print("=" * 60)
            print(f"左上角: ({x1}, {y1})")
            print(f"右下角: ({x2}, {y2})")
            print(f"区域尺寸: {x2-x1} x {y2-y1}")
            print("\n复制以下内容用于 game_auto_player.py:")
            print("-" * 60)
            print(f"x1 = {x1}")
            print(f"y1 = {y1}")
            print(f"x2 = {x2}")
            print(f"y2 = {y2}")
            print("-" * 60)
            
            # 验证截图
            print("\n正在验证截图...")
            from PIL import ImageGrab
            import cv2
            import numpy as np
            
            screenshot = ImageGrab.grab(bbox=(x1, y1, x2, y2))
            screenshot = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
            
            cv2.imwrite('verify_region.png', screenshot)
            print(f"验证截图已保存到 verify_region.png")
            print(f"截图尺寸: {screenshot.shape[1]} x {screenshot.shape[0]}")
            
            if screenshot.shape[1] == (x2-x1) and screenshot.shape[0] == (y2-y1):
                print("✓ 坐标验证成功！")
            else:
                print("✗ 警告：截图尺寸与预期不符，可能存在DPI缩放问题")
            
            print("\n按 ESC 退出...")
    
    # 注册空格键事件
    keyboard.on_press_key('space', lambda _: on_space())
    
    # 等待用户操作
    keyboard.wait('esc')
    
    print("\n程序退出")


if __name__ == '__main__':
    get_coordinates()
