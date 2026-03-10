"""
创建空位置模板的工具
从当前游戏截图中提取空位置的背景
"""

import cv2
import numpy as np
from PIL import ImageGrab
import os

def create_empty_template():
    """创建空位置模板"""
    print("空位置模板创建工具")
    print("=" * 50)
    
    # 读取最新的调试截图
    if os.path.exists('debug_screenshot.png'):
        screenshot = cv2.imread('debug_screenshot.png')
        print("使用 debug_screenshot.png")
    else:
        print("未找到 debug_screenshot.png，请先运行游戏识别")
        return
    
    print("\n请在图像中点击一个空位置的中心")
    print("操作说明:")
    print("- 点击鼠标左键选择空位置")
    print("- 按 'ESC' 键取消")
    
    clone = screenshot.copy()
    selected_point = None
    
    def mouse_callback(event, x, y, flags, param):
        nonlocal selected_point
        
        if event == cv2.EVENT_LBUTTONDOWN:
            selected_point = (x, y)
            # 绘制选择点
            cv2.circle(clone, (x, y), 5, (0, 0, 255), -1)
            cv2.putText(clone, "Selected", (x + 10, y - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
            cv2.imshow('选择空位置', clone)
    
    cv2.namedWindow('选择空位置')
    cv2.setMouseCallback('选择空位置', mouse_callback)
    cv2.imshow('选择空位置', clone)
    
    while True:
        key = cv2.waitKey(1) & 0xFF
        
        if selected_point:
            break
        elif key == 27:  # ESC
            cv2.destroyAllWindows()
            print("已取消")
            return
    
    cv2.destroyAllWindows()
    
    # 提取空位置模板
    x, y = selected_point
    template_size = 49  # 根据识别到的格子大小
    
    # 确保不超出边界
    half_size = template_size // 2
    x1 = max(0, x - half_size)
    y1 = max(0, y - half_size)
    x2 = min(screenshot.shape[1], x + half_size)
    y2 = min(screenshot.shape[0], y + half_size)
    
    empty_template = screenshot[y1:y2, x1:x2]
    
    # 创建空位置模板目录
    empty_dir = 'tiles_standardized/empty'
    os.makedirs(empty_dir, exist_ok=True)
    
    # 保存模板
    template_path = os.path.join(empty_dir, 'empty_bg.png')
    cv2.imwrite(template_path, empty_template)
    
    print(f"\n空位置模板已保存到: {template_path}")
    print(f"模板尺寸: {empty_template.shape[1]} x {empty_template.shape[0]}")
    
    # 显示模板
    cv2.imshow('空位置模板', empty_template)
    cv2.waitKey(0)
    cv2.destroyAllWindows()
    
    print("\n完成！现在可以重新运行游戏脚本")


if __name__ == '__main__':
    create_empty_template()