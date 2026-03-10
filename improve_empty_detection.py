"""
改进空位置检测的工具
1. 创建多个空位置模板
2. 分析20号图标的特征
3. 提供更精确的过滤建议
"""

import cv2
import numpy as np
import os
from pathlib import Path

def analyze_misidentified_20():
    """分析被误识别为20的空位置"""
    print("分析误识别的20号图标")
    print("=" * 50)
    
    # 读取调试截图
    if not os.path.exists('debug_screenshot.png'):
        print("未找到 debug_screenshot.png，请先运行游戏识别")
        return
    
    screenshot = cv2.imread('debug_screenshot.png')
    
    # 加载20号模板进行对比
    template_20_path = None
    for category_dir in Path('tiles_standardized').iterdir():
        if category_dir.is_dir() and category_dir.name == '20':
            for img_file in category_dir.glob('*.png'):
                template_20_path = str(img_file)
                break
            break
    
    if not template_20_path:
        print("未找到20号图标模板")
        return
    
    template_20 = cv2.imread(template_20_path)
    print(f"20号模板路径: {template_20_path}")
    
    # 显示20号模板
    cv2.imshow('20号模板', template_20)
    
    print("\n请在截图中点击被误识别为20的空位置")
    print("操作说明:")
    print("- 点击鼠标左键选择误识别位置")
    print("- 按 'r' 键重置选择")
    print("- 按 'c' 键完成选择并分析")
    print("- 按 'ESC' 键退出")
    
    clone = screenshot.copy()
    selected_points = []
    
    def mouse_callback(event, x, y, flags, param):
        nonlocal clone, selected_points
        
        if event == cv2.EVENT_LBUTTONDOWN:
            selected_points.append((x, y))
            # 绘制选择点
            cv2.circle(clone, (x, y), 5, (0, 0, 255), -1)
            cv2.putText(clone, f"{len(selected_points)}", (x + 10, y - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
            cv2.imshow('选择误识别位置', clone)
    
    cv2.namedWindow('选择误识别位置')
    cv2.setMouseCallback('选择误识别位置', mouse_callback)
    cv2.imshow('选择误识别位置', clone)
    
    while True:
        key = cv2.waitKey(1) & 0xFF
        
        if key == ord('c') and selected_points:
            break
        elif key == ord('r'):
            selected_points = []
            clone = screenshot.copy()
            cv2.imshow('选择误识别位置', clone)
        elif key == 27:  # ESC
            cv2.destroyAllWindows()
            return
    
    cv2.destroyAllWindows()
    
    # 分析选择的位置
    print(f"\n分析 {len(selected_points)} 个误识别位置...")
    
    template_size = 49
    half_size = template_size // 2
    
    # 创建改进的空位置模板目录
    empty_dir = 'tiles_standardized/empty'
    os.makedirs(empty_dir, exist_ok=True)
    
    for i, (x, y) in enumerate(selected_points):
        # 提取区域
        x1 = max(0, x - half_size)
        y1 = max(0, y - half_size)
        x2 = min(screenshot.shape[1], x + half_size)
        y2 = min(screenshot.shape[0], y + half_size)
        
        empty_region = screenshot[y1:y2, x1:x2]
        
        # 保存额外的空位置模板
        template_path = os.path.join(empty_dir, f'empty_variant_{i+1}.png')
        cv2.imwrite(template_path, empty_region)
        print(f"保存空位置变体 {i+1}: {template_path}")
        
        # 与20号模板对比
        if empty_region.shape[:2] == template_20.shape[:2]:
            # 计算相似度
            gray_empty = cv2.cvtColor(empty_region, cv2.COLOR_BGR2GRAY)
            gray_20 = cv2.cvtColor(template_20, cv2.COLOR_BGR2GRAY)
            
            result = cv2.matchTemplate(gray_empty, gray_20, cv2.TM_CCOEFF_NORMED)
            similarity = result[0, 0] if result.size > 0 else 0
            
            print(f"  与20号模板相似度: {similarity:.3f}")
            
            # 显示对比
            comparison = np.hstack([empty_region, template_20])
            cv2.imshow(f'对比 {i+1}: 空位置 vs 20号', comparison)
    
    print("\n建议:")
    print("1. 已保存多个空位置变体模板")
    print("2. 如果相似度 > 0.7，说明20号模板与空位置太相似")
    print("3. 可以考虑提高图标识别阈值或改进20号模板")
    
    cv2.waitKey(0)
    cv2.destroyAllWindows()

def create_multiple_empty_templates():
    """创建多个空位置模板"""
    print("创建多个空位置模板")
    print("=" * 50)
    
    if not os.path.exists('debug_screenshot.png'):
        print("未找到 debug_screenshot.png，请先运行游戏识别")
        return
    
    screenshot = cv2.imread('debug_screenshot.png')
    
    print("\n请点击多个不同的空位置")
    print("操作说明:")
    print("- 点击鼠标左键选择空位置")
    print("- 按 'c' 键完成并保存所有模板")
    print("- 按 'ESC' 键退出")
    
    clone = screenshot.copy()
    selected_points = []
    
    def mouse_callback(event, x, y, flags, param):
        nonlocal clone, selected_points
        
        if event == cv2.EVENT_LBUTTONDOWN:
            selected_points.append((x, y))
            cv2.circle(clone, (x, y), 5, (0, 255, 0), -1)
            cv2.putText(clone, f"Empty {len(selected_points)}", (x + 10, y - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            cv2.imshow('选择多个空位置', clone)
    
    cv2.namedWindow('选择多个空位置')
    cv2.setMouseCallback('选择多个空位置', mouse_callback)
    cv2.imshow('选择多个空位置', clone)
    
    while True:
        key = cv2.waitKey(1) & 0xFF
        
        if key == ord('c') and selected_points:
            break
        elif key == 27:  # ESC
            cv2.destroyAllWindows()
            return
    
    cv2.destroyAllWindows()
    
    # 保存所有模板
    empty_dir = 'tiles_standardized/empty'
    os.makedirs(empty_dir, exist_ok=True)
    
    template_size = 49
    half_size = template_size // 2
    
    for i, (x, y) in enumerate(selected_points):
        x1 = max(0, x - half_size)
        y1 = max(0, y - half_size)
        x2 = min(screenshot.shape[1], x + half_size)
        y2 = min(screenshot.shape[0], y + half_size)
        
        empty_template = screenshot[y1:y2, x1:x2]
        
        if i == 0:
            template_path = os.path.join(empty_dir, 'empty_bg.png')
        else:
            template_path = os.path.join(empty_dir, f'empty_bg_{i+1}.png')
        
        cv2.imwrite(template_path, empty_template)
        print(f"保存空位置模板 {i+1}: {template_path}")
    
    print(f"\n完成！保存了 {len(selected_points)} 个空位置模板")

def main():
    """主菜单"""
    while True:
        print("\n" + "=" * 50)
        print("空位置检测改进工具")
        print("=" * 50)
        print("1. 创建多个空位置模板")
        print("2. 分析误识别的20号图标")
        print("3. 退出")
        
        choice = input("\n请选择 (1-3): ").strip()
        
        if choice == '1':
            create_multiple_empty_templates()
        elif choice == '2':
            analyze_misidentified_20()
        elif choice == '3':
            break
        else:
            print("无效选择")

if __name__ == '__main__':
    main()