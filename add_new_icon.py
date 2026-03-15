"""
添加新图标到图标库的工具
从 debug_screenshot.png 中框选新图标并保存到 tiles_standardized 目录
"""

import cv2
import numpy as np
import os
from pathlib import Path


def add_new_icon():
    """添加新图标到图标库"""
    print("新图标添加工具")
    print("=" * 50)
    
    # 读取最新的调试截图
    script_dir = Path(__file__).parent
    screenshot_path = script_dir / 'debug_screenshot.png'
    if screenshot_path.exists():
        screenshot = cv2.imread(str(screenshot_path))
        print(f"使用 {screenshot_path}")
        print(f"图像尺寸: {screenshot.shape[1]} x {screenshot.shape[0]}")
    else:
        print("未找到 debug_screenshot.png，请先运行游戏识别")
        return
    
    # 获取图标库目录
    tiles_dir = script_dir / 'tiles_standardized'
    
    # 查找下一个可用的类别编号
    existing_categories = [d.name for d in tiles_dir.iterdir() 
                          if d.is_dir() and d.name.isdigit()]
    if existing_categories:
        next_category = str(max(int(c) for c in existing_categories) + 1).zfill(2)
    else:
        next_category = '01'
    
    print(f"\n下一个可用类别编号: {next_category}")
    print("\n请在图像中框选新图标...")
    print("操作说明:")
    print("- 按住鼠标左键拖拽选择区域")
    print("- 按 'r' 键重新选择")
    print("- 按 'c' 键确认选择")
    print("- 按 'ESC' 键取消")
    
    # 缩放图像以适应屏幕
    screen_height, screen_width = screenshot.shape[:2]
    max_display_height = 900
    max_display_width = 1600
    
    scale = 1.0
    if screen_height > max_display_height or screen_width > max_display_width:
        scale_h = max_display_height / screen_height
        scale_w = max_display_width / screen_width
        scale = min(scale_h, scale_w)
        display_image = cv2.resize(screenshot, None, fx=scale, fy=scale)
    else:
        display_image = screenshot.copy()
    
    clone = display_image.copy()
    coords = {'start': None, 'end': None}
    selecting = False
    
    def mouse_callback(event, x, y, flags, param):
        nonlocal selecting, clone
        
        if event == cv2.EVENT_LBUTTONDOWN:
            coords['start'] = (x, y)
            coords['end'] = (x, y)
            selecting = True
        
        elif event == cv2.EVENT_MOUSEMOVE and selecting:
            coords['end'] = (x, y)
            clone = display_image.copy()
            cv2.rectangle(clone, coords['start'], coords['end'], (0, 255, 0), 2)
            cv2.imshow('框选新图标', clone)
        
        elif event == cv2.EVENT_LBUTTONUP:
            coords['end'] = (x, y)
            selecting = False
            clone = display_image.copy()
            cv2.rectangle(clone, coords['start'], coords['end'], (0, 255, 0), 2)
            cv2.imshow('框选新图标', clone)
    
    cv2.namedWindow('框选新图标')
    cv2.setMouseCallback('框选新图标', mouse_callback)
    cv2.imshow('框选新图标', clone)
    
    while True:
        key = cv2.waitKey(1) & 0xFF
        
        if key == ord('c') and coords['start'] and coords['end']:
            break
        
        elif key == ord('r'):
            coords = {'start': None, 'end': None}
            clone = display_image.copy()
            cv2.imshow('框选新图标', clone)
        
        elif key == 27:  # ESC
            cv2.destroyAllWindows()
            print("已取消")
            return
    
    cv2.destroyAllWindows()
    
    # 转换回原始坐标
    x1 = int(min(coords['start'][0], coords['end'][0]) / scale)
    y1 = int(min(coords['start'][1], coords['end'][1]) / scale)
    x2 = int(max(coords['start'][0], coords['end'][0]) / scale)
    y2 = int(max(coords['start'][1], coords['end'][1]) / scale)
    
    # 确保坐标有效
    x1 = max(0, x1)
    y1 = max(0, y1)
    x2 = min(screenshot.shape[1], x2)
    y2 = min(screenshot.shape[0], y2)
    
    # 提取图标
    icon = screenshot[y1:y2, x1:x2]
    
    if icon.size == 0:
        print("选择的区域无效")
        return
    
    print(f"\n选择的区域: ({x1}, {y1}) 到 ({x2}, {y2})")
    print(f"图标尺寸: {icon.shape[1]} x {icon.shape[0]}")
    
    # 创建类别目录
    category_dir = tiles_dir / next_category
    category_dir.mkdir(exist_ok=True)
    
    # 保存图标
    icon_path = category_dir / f'{next_category}.png'
    cv2.imwrite(str(icon_path), icon)
    
    print(f"\n图标已保存到: {icon_path}")
    
    # 显示图标
    cv2.imshow('提取的图标', icon)
    print("\n按任意键关闭预览...")
    cv2.waitKey(0)
    cv2.destroyAllWindows()
    
    print("\n完成！现在可以重新运行游戏脚本")
    print(f"新图标类别: {next_category}")


if __name__ == '__main__':
    add_new_icon()
