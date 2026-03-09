"""
游戏图标匹配脚本
功能：截取屏幕区域，识别并匹配游戏中的图标
"""

import cv2
import numpy as np
from PIL import ImageGrab
import os
from pathlib import Path
import time

class GameIconMatcher:
    def __init__(self, templates_dir='tiles_standardized'):
        """初始化图标匹配器"""
        self.templates_dir = templates_dir
        self.templates = {}
        self.load_templates()
        self.region = None
        
    def load_templates(self):
        """加载所有模板图标"""
        print("正在加载模板图标...")
        template_path = Path(self.templates_dir)
        
        for category_dir in template_path.iterdir():
            if category_dir.is_dir():
                category_id = category_dir.name
                self.templates[category_id] = []
                
                for img_file in category_dir.glob('*.png'):
                    template = cv2.imread(str(img_file))
                    if template is not None:
                        self.templates[category_id].append({
                            'image': template,
                            'name': img_file.stem,
                            'path': str(img_file)
                        })
        
        total_templates = sum(len(v) for v in self.templates.values())
        print(f"已加载 {len(self.templates)} 个类别，共 {total_templates} 个模板图标")
    
    def list_windows(self):
        """列出所有窗口"""
        windows = []
        
        def callback(hwnd, windows):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title:
                    windows.append((hwnd, title))
            return True
        
        win32gui.EnumWindows(callback, windows)
        return windows
    
    def select_window(self):
        """选择游戏窗口"""
        windows = self.list_windows()
        
        print("\n可用窗口列表:")
        for i, (hwnd, title) in enumerate(windows, 1):
            print(f"{i}. {title}")
        
        root = tk.Tk()
        root.withdraw()
        
        choice = simpledialog.askinteger(
            "选择窗口",
            f"请输入窗口编号 (1-{len(windows)}):\n\n" + 
            "\n".join([f"{i}. {title}" for i, (_, title) in enumerate(windows[:10], 1)]),
            minvalue=1,
            maxvalue=len(windows)
        )
        
        root.destroy()
        
        if choice:
            hwnd, title = windows[choice - 1]
            print(f"\n已选择窗口: {title}")
            return hwnd
        return None
    
    def capture_window(self, hwnd):
        """截取指定窗口"""
        try:
            # 获取窗口位置和大小
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            width = right - left
            height = bottom - top
            
            # 创建设备上下文
            hwndDC = win32gui.GetWindowDC(hwnd)
            mfcDC = win32ui.CreateDCFromHandle(hwndDC)
            saveDC = mfcDC.CreateCompatibleDC()
            
            # 创建位图对象
            saveBitMap = win32ui.CreateBitmap()
            saveBitMap.CreateCompatibleBitmap(mfcDC, width, height)
            saveDC.SelectObject(saveBitMap)
            
            # 截图
            saveDC.BitBlt((0, 0), (width, height), mfcDC, (0, 0), win32con.SRCCOPY)
            
            # 转换为numpy数组
            bmpinfo = saveBitMap.GetInfo()
            bmpstr = saveBitMap.GetBitmapBits(True)
            img = np.frombuffer(bmpstr, dtype=np.uint8)
            img.shape = (height, width, 4)
            
            # 清理资源
            win32gui.DeleteObject(saveBitMap.GetHandle())
            saveDC.DeleteDC()
            mfcDC.DeleteDC()
            win32gui.ReleaseDC(hwnd, hwndDC)
            
            # 转换为BGR格式
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            
            return img, (left, top, right, bottom)
            
        except Exception as e:
            print(f"截取窗口失败: {e}")
            return None, None
    
    def select_region_from_image(self, image):
        """从图像中选择区域"""
        print("\n请在图像中框选游戏区域...")
        print("操作说明:")
        print("- 按住鼠标左键拖拽选择区域")
        print("- 按 'r' 键重新选择")
        print("- 按 'c' 键确认选择")
        print("- 按 'ESC' 键取消")
        
        clone = image.copy()
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
                clone = image.copy()
                cv2.rectangle(clone, coords['start'], coords['end'], (0, 255, 0), 2)
                cv2.imshow('选择区域', clone)
            
            elif event == cv2.EVENT_LBUTTONUP:
                coords['end'] = (x, y)
                selecting = False
                clone = image.copy()
                cv2.rectangle(clone, coords['start'], coords['end'], (0, 255, 0), 2)
                cv2.imshow('选择区域', clone)
        
        cv2.namedWindow('选择区域')
        cv2.setMouseCallback('选择区域', mouse_callback)
        cv2.imshow('选择区域', image)
        
        while True:
            key = cv2.waitKey(1) & 0xFF
            
            if key == ord('c') and coords['start'] and coords['end']:
                cv2.destroyAllWindows()
                x1 = min(coords['start'][0], coords['end'][0])
                y1 = min(coords['start'][1], coords['end'][1])
                x2 = max(coords['start'][0], coords['end'][0])
                y2 = max(coords['start'][1], coords['end'][1])
                return (x1, y1, x2, y2)
            
            elif key == ord('r'):
                coords = {'start': None, 'end': None}
                clone = image.copy()
                cv2.imshow('选择区域', clone)
            
            elif key == 27:  # ESC
                cv2.destroyAllWindows()
                return None
        
        return None
    
    def capture_fullscreen(self):
        """截取全屏"""
        print("\n正在截取全屏...")
        screenshot = ImageGrab.grab()
        return cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
    
    def select_region_by_clicks(self, image):
        """通过点击两个点选择区域"""
        print("\n请点击选择游戏区域:")
        print("1. 点击左上角")
        print("2. 点击右下角")
        print("按 'ESC' 键取消")
        
        # 缩放图像以适应屏幕
        screen_height, screen_width = image.shape[:2]
        max_display_height = 900
        max_display_width = 1600
        
        scale = 1.0
        if screen_height > max_display_height or screen_width > max_display_width:
            scale_h = max_display_height / screen_height
            scale_w = max_display_width / screen_width
            scale = min(scale_h, scale_w)
            display_image = cv2.resize(image, None, fx=scale, fy=scale)
        else:
            display_image = image.copy()
        
        clone = display_image.copy()
        points = []
        
        def mouse_callback(event, x, y, flags, param):
            nonlocal clone, points
            
            if event == cv2.EVENT_LBUTTONDOWN:
                if len(points) < 2:
                    points.append((x, y))
                    
                    # 绘制点
                    cv2.circle(clone, (x, y), 5, (0, 0, 255), -1)
                    
                    if len(points) == 1:
                        cv2.putText(clone, "1. 左上角", (x + 10, y - 10),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                        print(f"已选择左上角: ({int(x/scale)}, {int(y/scale)})")
                    elif len(points) == 2:
                        cv2.putText(clone, "2. 右下角", (x + 10, y - 10),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                        print(f"已选择右下角: ({int(x/scale)}, {int(y/scale)})")
                        
                        # 绘制矩形
                        cv2.rectangle(clone, points[0], points[1], (0, 255, 0), 2)
                    
                    cv2.imshow('选择区域 - 点击两个点', clone)
        
        cv2.namedWindow('选择区域 - 点击两个点')
        cv2.setMouseCallback('选择区域 - 点击两个点', mouse_callback)
        cv2.imshow('选择区域 - 点击两个点', clone)
        
        while True:
            key = cv2.waitKey(1) & 0xFF
            
            if len(points) == 2:
                # 等待1秒后自动确认
                time.sleep(1)
                cv2.destroyAllWindows()
                
                # 转换回原始坐标
                x1 = int(min(points[0][0], points[1][0]) / scale)
                y1 = int(min(points[0][1], points[1][1]) / scale)
                x2 = int(max(points[0][0], points[1][0]) / scale)
                y2 = int(max(points[0][1], points[1][1]) / scale)
                
                return (x1, y1, x2, y2)
            
            elif key == 27:  # ESC
                cv2.destroyAllWindows()
                return None
        
        return None
    
    def match_icons(self, screenshot, threshold=0.8, use_multiscale=True):
        """在截图中匹配所有图标"""
        results = []
        gray_screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
        
        # 多尺度匹配的缩放比例
        scales = [0.8, 0.9, 1.0, 1.1, 1.2] if use_multiscale else [1.0]
        
        print(f"使用 {len(scales)} 个尺度进行匹配...")
        
        for category_id, templates in self.templates.items():
            for template_info in templates:
                template = template_info['image']
                gray_template = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
                
                best_matches = []
                
                # 多尺度匹配
                for scale in scales:
                    if scale != 1.0:
                        width = int(gray_template.shape[1] * scale)
                        height = int(gray_template.shape[0] * scale)
                        scaled_template = cv2.resize(gray_template, (width, height))
                    else:
                        scaled_template = gray_template
                    
                    # 检查模板是否小于截图
                    if scaled_template.shape[0] > gray_screenshot.shape[0] or \
                       scaled_template.shape[1] > gray_screenshot.shape[1]:
                        continue
                    
                    # 模板匹配
                    result = cv2.matchTemplate(gray_screenshot, scaled_template, cv2.TM_CCOEFF_NORMED)
                    locations = np.where(result >= threshold)
                    
                    for pt in zip(*locations[::-1]):
                        best_matches.append({
                            'category': category_id,
                            'name': template_info['name'],
                            'position': pt,
                            'confidence': result[pt[1], pt[0]],
                            'size': (scaled_template.shape[1], scaled_template.shape[0]),
                            'scale': scale
                        })
                
                results.extend(best_matches)
        
        # 去除重复检测（非极大值抑制）
        results = self.non_max_suppression(results, overlap_thresh=0.5)
        
        # 按位置排序
        results = sorted(results, key=lambda x: (x['position'][1], x['position'][0]))
        
        return results
    
    def non_max_suppression(self, detections, overlap_thresh=0.5):
        """非极大值抑制，去除重叠的检测结果"""
        if len(detections) == 0:
            return []
        
        # 按置信度排序
        detections = sorted(detections, key=lambda x: x['confidence'], reverse=True)
        
        keep = []
        for i, det in enumerate(detections):
            x1, y1 = det['position']
            w1, h1 = det['size']
            
            should_keep = True
            for kept_det in keep:
                x2, y2 = kept_det['position']
                w2, h2 = kept_det['size']
                
                # 计算重叠区域
                x_overlap = max(0, min(x1 + w1, x2 + w2) - max(x1, x2))
                y_overlap = max(0, min(y1 + h1, y2 + h2) - max(y1, y2))
                overlap_area = x_overlap * y_overlap
                
                area1 = w1 * h1
                area2 = w2 * h2
                
                # 如果重叠面积超过阈值，保留置信度更高的
                if overlap_area / min(area1, area2) > overlap_thresh:
                    should_keep = False
                    break
            
            if should_keep:
                keep.append(det)
        
        return keep
    
    def draw_results(self, screenshot, results):
        """在截图上绘制匹配结果"""
        output = screenshot.copy()
        
        for result in results:
            x, y = result['position']
            w, h = result['size']
            
            # 绘制矩形框
            cv2.rectangle(output, (x, y), (x + w, y + h), (0, 255, 0), 3)
            
            # 准备标签文本（只显示类别代号）
            label = result['category']
            
            # 计算文字大小
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.5
            thickness = 2
            
            (label_w, label_h), _ = cv2.getTextSize(label, font, font_scale, thickness)
            
            # 计算文字位置（在矩形框中心）
            text_x = x + (w - label_w) // 2
            text_y = y + (h + label_h) // 2
            
            # 绘制文字背景（黑色半透明）
            padding = 5
            overlay = output.copy()
            cv2.rectangle(overlay, 
                         (text_x - padding, text_y - label_h - padding),
                         (text_x + label_w + padding, text_y + padding),
                         (0, 0, 0), -1)
            cv2.addWeighted(overlay, 0.7, output, 0.3, 0, output)
            
            # 绘制类别代号（黄色）
            cv2.putText(output, label, 
                       (text_x, text_y),
                       font, font_scale, (0, 255, 255), thickness)
        
        return output
    
    def run(self, threshold=0.8, show_result=True, use_multiscale=True):
        """运行匹配流程"""
        # 截取全屏
        print("\n3秒后将截取全屏，请准备...")
        time.sleep(3)
        
        full_image = self.capture_fullscreen()
        print(f"已截取全屏，尺寸: {full_image.shape[1]}x{full_image.shape[0]}")
        
        # 通过点击选择区域
        region = self.select_region_by_clicks(full_image)
        if not region:
            print("未选择区域，程序退出")
            return
        
        x1, y1, x2, y2 = region
        screenshot = full_image[y1:y2, x1:x2]
        print(f"已选择区域: ({x1}, {y1}) 到 ({x2}, {y2})")
        print(f"区域尺寸: {x2-x1}x{y2-y1}")
        
        # 保存原始截图用于对比
        cv2.imwrite('original_region.png', screenshot)
        print("原始区域已保存到 original_region.png")
        
        # 匹配图标
        print(f"\n正在匹配图标 (阈值: {threshold}, 多尺度: {use_multiscale})...")
        results = self.match_icons(screenshot, threshold, use_multiscale)
        
        print(f"\n找到 {len(results)} 个匹配项:")
        for i, result in enumerate(results, 1):
            scale_info = f", 缩放: {result['scale']:.1f}x" if 'scale' in result else ""
            print(f"{i}. 类别: {result['category']}, "
                  f"位置: {result['position']}, "
                  f"置信度: {result['confidence']:.3f}{scale_info}")
        
        # 显示结果
        if show_result:
            output = self.draw_results(screenshot, results)
            cv2.imshow('匹配结果 (按任意键关闭)', output)
            cv2.waitKey(0)
            cv2.destroyAllWindows()
            
            # 保存结果
            cv2.imwrite('match_result.png', output)
            print("\n结果已保存到 match_result.png")
        
        return results


def main():
    """主函数"""
    print("=" * 50)
    print("游戏图标匹配工具")
    print("=" * 50)
    
    # 创建匹配器
    matcher = GameIconMatcher()
    
    # 运行匹配
    # threshold: 匹配阈值 (0.7-0.9)，越高越严格
    # use_multiscale: 是否使用多尺度匹配，可以处理不同大小的图标
    matcher.run(threshold=0.75, use_multiscale=True)


if __name__ == '__main__':
    main()
