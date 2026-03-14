"""
游戏自动玩家
功能：自动识别、分析并执行游戏操作
整合：zhuan-solver的GBFS搜索算法
"""

import cv2
import numpy as np
from PIL import ImageGrab
import pyautogui
import keyboard
import time
import json
import os
from collections import defaultdict
import win32api
import win32con
from game_icon_matcher import GameIconMatcher
from state.search import GBFS
from app.zhuan.board_state import BoardState
from app.zhuan.zhuan_node import ZhuanNode


class GameGrid:
    """游戏网格数据结构"""
    
    def __init__(self):
        self.grid = {}  # {(row, col): cell_info}
        self.rows = 0
        self.cols = 0
        self.cell_width = 0
        self.cell_height = 0
        self.region_offset = (0, 0)  # 游戏区域相对屏幕的偏移
        
    def build_from_results(self, results, region_offset):
        """从识别结果构建网格"""
        if not results:
            print("没有识别到任何图标")
            return False
        
        self.region_offset = region_offset
        
        # 提取所有位置信息
        positions = []
        for r in results:
            x, y = r['position']
            w, h = r['size']
            center_x = x + w // 2
            center_y = y + h // 2
            positions.append({
                'center_x': center_x,
                'center_y': center_y,
                'width': w,
                'height': h,
                'category': r['category']
            })
        
        # 按Y坐标聚类确定行
        y_coords = sorted([p['center_y'] for p in positions])
        rows = self._cluster_coordinates(y_coords, threshold=15)
        
        # 按X坐标聚类确定列
        x_coords = sorted([p['center_x'] for p in positions])
        cols = self._cluster_coordinates(x_coords, threshold=15)
        
        self.rows = len(rows)
        self.cols = len(cols)
        
        print(f"\n网格结构: {self.rows} 行 x {self.cols} 列")
        print(f"Y坐标聚类: {len(rows)} 个行中心")
        print(f"X坐标聚类: {len(cols)} 个列中心")
        
        # 计算平均格子大小
        widths = [p['width'] for p in positions]
        heights = [p['height'] for p in positions]
        self.cell_width = int(np.mean(widths))
        self.cell_height = int(np.mean(heights))
        
        print(f"格子大小: {self.cell_width} x {self.cell_height}")
        
        # 建立位置到行列的映射
        y_to_row = {y: i for i, y in enumerate(rows)}
        x_to_col = {x: i for i, x in enumerate(cols)}
        
        # 初始化网格（全部为空）
        for row in range(self.rows):
            for col in range(self.cols):
                self.grid[(row, col)] = {
                    'type': None,
                    'center_x': cols[col],
                    'center_y': rows[row],
                    'abs_center_x': cols[col] + region_offset[0],
                    'abs_center_y': rows[row] + region_offset[1],
                    'is_empty': True
                }
        
        # 填充识别到的图标
        for pos in positions:
            # 找到最近的行和列
            row = min(y_to_row.keys(), key=lambda y: abs(y - pos['center_y']))
            col = min(x_to_col.keys(), key=lambda x: abs(x - pos['center_x']))
            
            row_idx = y_to_row[row]
            col_idx = x_to_col[col]
            
            self.grid[(row_idx, col_idx)] = {
                'type': pos['category'],
                'center_x': pos['center_x'],
                'center_y': pos['center_y'],
                'abs_center_x': pos['center_x'] + region_offset[0],
                'abs_center_y': pos['center_y'] + region_offset[1],
                'is_empty': False
            }
        
        # 统计
        filled = sum(1 for cell in self.grid.values() if not cell['is_empty'])
        empty = self.rows * self.cols - filled
        print(f"已填充格子: {filled}/{self.rows * self.cols}")
        print(f"空格子: {empty}")
        
        # 警告：如果空格子太多可能是识别问题
        if empty > self.rows * self.cols * 0.3:
            print(f"警告：空格子比例较高 ({empty}/{self.rows * self.cols})，可能存在识别遗漏")
            print("建议检查 move/debug_screenshot.png 和 move/debug_matched.png")
        
        return True
    
    def _cluster_coordinates(self, coords, threshold=10):
        """聚类坐标，合并相近的值"""
        if not coords:
            return []
        
        clusters = []
        current_cluster = [coords[0]]
        
        for coord in coords[1:]:
            if coord - current_cluster[-1] <= threshold:
                current_cluster.append(coord)
            else:
                clusters.append(int(np.mean(current_cluster)))
                current_cluster = [coord]
        
        clusters.append(int(np.mean(current_cluster)))
        return clusters
    
    def get_cell(self, row, col):
        """获取指定格子"""
        return self.grid.get((row, col))
    
    def set_empty(self, row, col):
        """设置格子为空"""
        if (row, col) in self.grid:
            self.grid[(row, col)]['type'] = None
            self.grid[(row, col)]['is_empty'] = True
    
    def print_grid(self):
        """打印网格状态"""
        print("\n当前网格状态:")
        
        for row in range(self.rows):
            for col in range(self.cols):
                cell = self.grid[(row, col)]
                if cell['is_empty']:
                    print(f"({row:02d},{col:02d},00)", end=" ")
                else:
                    # 将类型转换为两位数字
                    item_id = cell['type'].zfill(2) if cell['type'] else "00"
                    print(f"({row:02d},{col:02d},{item_id})", end=" ")
            print()  # 换行
        
        # 额外显示25的位置
        print(f"\n25的所有位置:")
        for row in range(self.rows):
            for col in range(self.cols):
                cell = self.grid[(row, col)]
                if not cell['is_empty'] and cell['type'] == '25':
                    print(f"  25 at ({row:02d},{col:02d})")


class GameAutoPlayer:
    """游戏自动玩家"""
    
    def __init__(self):
        self.matcher = GameIconMatcher()
        self.grid = GameGrid()
        self.game_region = None  # (x1, y1, x2, y2)
        self.move_count = 0
        self.config_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'game_region_config.json')
        self.last_moves = []  # 记录最近的移动，避免重复
        self.max_history = 5  # 最多记录5次移动历史
        self.solution_path = None  # GBFS求解路径
    
    def _drag_to(self, start_x, start_y, end_x, end_y, duration=0.3):
        """使用 win32api 执行可靠的拖动操作
        
        自动检测水平/垂直移动，确保走直线
        """
        start_x, start_y = int(start_x), int(start_y)
        end_x, end_y = int(end_x), int(end_y)
        
        # 移动到起点
        win32api.SetCursorPos((start_x, start_y))
        time.sleep(0.1)
        
        # 按下鼠标左键
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.05)
        
        # 判断移动方向，确保走直线
        dx = end_x - start_x
        dy = end_y - start_y
        
        if abs(dx) > abs(dy):
            # 水平移动为主，锁定 Y 坐标
            steps = max(10, int(duration * 60))
            for i in range(1, steps + 1):
                x = start_x + dx * i // steps
                win32api.SetCursorPos((x, start_y))  # Y 保持不变
                time.sleep(duration / steps)
            win32api.SetCursorPos((end_x, start_y))
        else:
            # 垂直移动为主，锁定 X 坐标
            steps = max(10, int(duration * 60))
            for i in range(1, steps + 1):
                y = start_y + dy * i // steps
                win32api.SetCursorPos((start_x, y))  # X 保持不变
                time.sleep(duration / steps)
            win32api.SetCursorPos((start_x, end_y))
        
        # 确保到达终点
        win32api.SetCursorPos((end_x, end_y))
        time.sleep(0.05)
        
        # 释放鼠标左键
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        time.sleep(0.1)
    
    def _drag_rel(self, start_x, start_y, dx, dy, duration=0.3):
        """使用 win32api 执行相对距离拖动"""
        end_x = start_x + dx
        end_y = start_y + dy
        self._drag_to(start_x, start_y, end_x, end_y, duration)
    
    def solve_with_gbfs(self):
        """使用GBFS算法求解游戏"""
        print("\n" + "=" * 50)
        print("使用 GBFS 算法求解...")
        print("=" * 50)
        
        # 从grid构建棋盘矩阵
        if not self.grid.grid:
            print("错误：棋盘数据为空")
            return None
        
        # 构建矩阵，0表示空格
        matrix = []
        for row in range(self.grid.rows):
            row_data = []
            for col in range(self.grid.cols):
                cell = self.grid.get_cell(row, col)
                if cell['is_empty']:
                    row_data.append(0)
                else:
                    # 使用类型的数字（去掉前导零）
                    type_id = int(cell['type'])
                    row_data.append(type_id)
            matrix.append(row_data)
        
        print(f"棋盘大小: {self.grid.rows} x {self.grid.cols}")
        
        # 创建初始状态
        initial_state = BoardState(matrix)
        start_node = ZhuanNode(initial_state)
        
        # 执行GBFS搜索
        searcher = GBFS(start_node)
        path = searcher.search()
        
        if path:
            print(f"\n✓ 找到解决方案! 共 {len(path)-1} 步")
            searcher.show_algorithm_stats()
            self.solution_path = path
            return path
        else:
            print("\n✗ 未找到解决方案")
            searcher.show_algorithm_stats()
            return None
    
    def preview_solution(self):
        """预览解决方案：在窗口中可视化每步移动"""
        if not self.solution_path:
            print("没有解决方案可预览")
            return
        
        print("\n" + "=" * 60)
        print("可视化预览模式")
        print("=" * 60)
        print("按键说明:")
        print("  空格/回车 - 下一步")
        print("  b - 上一步")
        print("  q/ESC - 退出预览")
        print("=" * 60)
        
        # 记录每步后的棋盘状态 - 直接使用节点的实际状态
        board_states = []
        for node in self.solution_path:
            # 从节点的BoardState获取棋盘矩阵
            if hasattr(node, 'state') and hasattr(node.state, 'tiles'):
                board_states.append([list(row) for row in node.state.tiles])
            else:
                # 如果节点没有状态，使用当前网格
                board_states.append(self._get_board_matrix())
        
        # 可视化循环
        current_step = 0
        total_steps = len(self.solution_path) - 1
        
        while True:
            # 创建当前步骤的可视化图像
            img = self._visualize_step(board_states[current_step], current_step)
            
            # 显示步骤信息
            if current_step == 0:
                title = f"初始状态 - 按空格开始"
            elif current_step < len(self.solution_path):
                node = self.solution_path[current_step]
                if node.from_action:
                    start, end, dir_key = node.from_action
                    title = f"步骤 {current_step}/{total_steps}"
                else:
                    title = f"步骤 {current_step}/{total_steps}"
            else:
                title = f"完成! 共 {total_steps} 步"
            
            cv2.imshow('解决方案预览', img)
            cv2.setWindowTitle('解决方案预览', title)
            
            # 等待按键
            key = cv2.waitKey(0) & 0xFF
            
            if key == ord('q') or key == 27:  # q 或 ESC
                break
            elif key == ord(' ') or key == 13:  # 空格或回车
                if current_step < len(board_states) - 1:
                    current_step += 1
            elif key == ord('b'):  # 返回上一步
                if current_step > 0:
                    current_step -= 1
        
        cv2.destroyAllWindows()
    
    def _get_board_matrix(self):
        """获取当前棋盘矩阵"""
        matrix = []
        for row in range(self.grid.rows):
            row_data = []
            for col in range(self.grid.cols):
                cell = self.grid.get_cell(row, col)
                if cell['is_empty']:
                    row_data.append(0)
                else:
                    row_data.append(int(cell['type']))
            matrix.append(row_data)
        return matrix
    
    def _visualize_step(self, matrix, step):
        """可视化单步棋盘状态"""
        rows = len(matrix)
        cols = len(matrix[0])
        
        # 每个格子大小
        cell_size = 50
        padding = 60  # 左上角留出空间显示行列号
        
        # 图像尺寸
        width = cols * cell_size + padding
        height = rows * cell_size + padding
        
        # 创建白色背景
        img = np.ones((height, width, 3), dtype=np.uint8) * 255
        
        # 颜色映射（根据方块类型）
        colors = self._get_block_colors()
        
        # 绘制网格和方块
        for row in range(rows):
            for col in range(cols):
                x = col * cell_size + padding
                y = row * cell_size + padding
                
                block_type = matrix[row][col]
                
                if block_type > 0:
                    # 绘制方块
                    color = colors.get(block_type % len(colors), (100, 100, 100))
                    cv2.rectangle(img, (x+2, y+2), (x+cell_size-2, y+cell_size-2), color, -1)
                    cv2.rectangle(img, (x+2, y+2), (x+cell_size-2, y+cell_size-2), (50, 50, 50), 1)
                    
                    # 显示类型编号
                    cv2.putText(img, str(block_type), (x+15, y+35), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                else:
                    # 空格子
                    cv2.rectangle(img, (x+2, y+2), (x+cell_size-2, y+cell_size-2), (240, 240, 240), -1)
                    cv2.rectangle(img, (x+2, y+2), (x+cell_size-2, y+cell_size-2), (200, 200, 200), 1)
        
        # 绘制行号
        for row in range(rows):
            y = row * cell_size + padding + cell_size // 2 + 5
            cv2.putText(img, str(row), (20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
        
        # 绘制列号
        for col in range(cols):
            x = col * cell_size + padding + cell_size // 2 - 5
            cv2.putText(img, str(col), (x, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
        
        # 绘制步骤信息
        if step > 0 and step < len(self.solution_path):
            node = self.solution_path[step]
            if node.from_action:
                start, end, dir_key = node.from_action
                start_row, start_col = start
                end_row, end_col = end
                
                # 高亮起始位置（红色边框）
                x = start_col * cell_size + padding
                y = start_row * cell_size + padding
                cv2.rectangle(img, (x, y), (x+cell_size, y+cell_size), (0, 0, 255), 3)
                
                # 如果是移动操作，高亮终点
                if start != end:
                    x2 = end_col * cell_size + padding
                    y2 = end_row * cell_size + padding
                    cv2.rectangle(img, (x2, y2), (x2+cell_size, y2+cell_size), (255, 0, 0), 3)
                    
                    # 绘制箭头
                    cx1, cy1 = x + cell_size//2, y + cell_size//2
                    cx2, cy2 = x2 + cell_size//2, y2 + cell_size//2
                    cv2.arrowedLine(img, (cx1, cy1), (cx2, cy2), (0, 165, 255), 2)
        
        return img
    
    def _get_block_colors(self):
        """获取方块颜色映射"""
        return {
            0: (240, 240, 240),  # 空 - 浅灰
            1: (255, 99, 71),    # 番茄红
            2: (30, 144, 255),   # 道奇蓝
            3: (50, 205, 50),    # 酸橙绿
            4: (255, 215, 0),    # 金色
            5: (238, 130, 238),  # 紫罗兰
            6: (255, 165, 0),    # 橙色
            7: (0, 206, 209),    # 深青色
            8: (255, 20, 147),   # 深粉色
            9: (154, 205, 50),   # 黄绿色
            10: (70, 130, 180),  # 钢蓝色
            11: (220, 20, 60),   # 猩红色
            12: (0, 255, 127),   # 春绿色
            13: (255, 105, 180), # 热粉色
            14: (138, 43, 226),  # 蓝紫色
            15: (0, 139, 139),   # 深青色
            16: (255, 69, 0),    # 橙红色
            17: (46, 139, 87),   # 海绿色
            18: (199, 21, 133),  # 中紫罗兰红
            19: (25, 25, 112),   # 午夜蓝
            20: (128, 0, 0),     # 栗色
        }
    
    def _print_board_matrix(self):
        """打印棋盘矩阵"""
        # 打印列号
        print("     ", end="")
        for col in range(self.grid.cols):
            print(f"{col:3d}", end=" ")
        print()
        
        # 打印每行
        for row in range(self.grid.rows):
            print(f"{row:3d} ", end="")
            for col in range(self.grid.cols):
                cell = self.grid.get_cell(row, col)
                if cell['is_empty']:
                    print("   0", end=" ")
                else:
                    print(f"{int(cell['type']):4d}", end=" ")
            print()
    
    def execute_solution(self, move_delay=1.0, manual_mode=False):
        """执行GBFS求解的路径
        
        Args:
            move_delay: 移动间隔时间（自动模式）
            manual_mode: 是否手动模式（按空格执行每一步）
        """
        if not self.solution_path:
            print("没有解决方案可执行")
            return False
        
        print("\n" + "=" * 60)
        print("开始执行解决方案")
        print("=" * 60)
        print(f"总共需要 {len(self.solution_path)-1} 步")
        
        if manual_mode:
            print("\n📋 手动执行模式")
            print("按 空格键 或 回车键 执行下一步")
            print("按 q 键 退出")
        else:
            print(f"移动间隔: {move_delay}秒")
            print("\n⚠️ 注意：鼠标将被自动控制")
            print("⚠️ 暂停：将鼠标移到屏幕左上角（移回游戏区域继续）")
            print("⚠️ 退出：暂停时按 q 键")
        
        
        input("\n按回车键开始执行...")
        
        total_moves = len(self.solution_path) - 1
        step_idx = 0
        
        while step_idx < len(self.solution_path):
            node = self.solution_path[step_idx]
            
            if node.from_action:
                start, end, dir_key = node.from_action
                
                # 手动模式：等待用户按键
                if manual_mode:
                    while True:
                        print(f"\n[步骤 {step_idx}/{total_moves}] 移动: {start} -> {end}, 方向: {dir_key}")
                        print("按 空格/回车 执行 | q 退出")
                        
                        event = keyboard.read_event()
                        if event.event_type == keyboard.KEY_DOWN:
                            if event.name == 'space' or event.name == 'enter':
                                break  # 执行当前步骤
                            elif event.name == 'q':
                                print("⚠️ 用户取消执行")
                                return False
                else:
                    # 自动模式：检查暂停/继续
                    x, y = pyautogui.position()
                    if x < 10 and y < 10:
                        print("\n⏸️ 暂停执行 - 鼠标移入游戏区域后自动继续")
                        
                        # 等待鼠标回到游戏区域
                        while True:
                            mx, my = pyautogui.position()
                            # 检查是否在游戏区域内
                            if (self.game_region[0] <= mx <= self.game_region[2] and 
                                self.game_region[1] <= my <= self.game_region[3]):
                                print("▶️ 继续执行...")
                                break
                            # 检查是否按q退出
                            if keyboard.is_pressed('q'):
                                print("⚠️ 用户取消执行")
                                return False
                            time.sleep(0.1)
                
                # 执行移动
                print(f"执行: {start} -> {end}")
                self._execute_gbfs_move(start, end, dir_key)
                self.move_count += 1
                
                if not manual_mode:
                    time.sleep(move_delay)
            
            step_idx += 1
        
        print("\n" + "=" * 60)
        print("✓ 执行完成!")
        print("=" * 60)
        return True
    
    def _execute_gbfs_move(self, start, end, search_dir):
        """执行GBFS求解中的单步移动"""
        start_row, start_col = start
        end_row, end_col = end
        
        # 获取屏幕坐标
        start_cell = self.grid.get_cell(start_row, start_col)
        if not start_cell or start_cell['is_empty']:
            print(f"警告：起始位置无效")
            return
        
        start_x = start_cell['abs_center_x']
        start_y = start_cell['abs_center_y']
        
        if start == end:
            # 原地点击消除
            print(f"  原地点击: ({start_x}, {start_y})")
            pyautogui.click(start_x, start_y)
        else:
            # 获取目标位置的实际砖块中心
            end_cell = self.grid.get_cell(end_row, end_col)
            
            if end_cell and not end_cell['is_empty']:
                # 目标位置有砖块，使用实际识别的中心
                end_x = end_cell['abs_center_x']
                end_y = end_cell['abs_center_y']
            else:
                # 目标位置为空，使用理论网格位置
                end_x = self.grid.region_offset[0] + (end_col + 0.5) * self.grid.cell_width
                end_y = self.grid.region_offset[1] + (end_row + 0.5) * self.grid.cell_height
            
            # 计算移动方向，稍微偏移以确保到达
            dx = end_x - start_x
            dy = end_y - start_y
            distance = abs(end_row - start_row) + abs(end_col - start_col)
            
            # 根据移动方向添加小偏移（约0.2格）
            if abs(dx) > abs(dy):
                # 水平移动为主
                offset = 0.2 * self.grid.cell_width * (1 if dx > 0 else -1)
                end_x += offset
            else:
                # 垂直移动为主
                offset = 0.2 * self.grid.cell_height * (1 if dy > 0 else -1)
                end_y += offset
            
            print(f"  拖动: ({start_x}, {start_y}) -> ({int(end_x)}, {int(end_y)})")
            
            # 执行拖动，距离越远时间越长
            duration = 0.2 + distance * 0.15
            self._drag_to(start_x, start_y, end_x, end_y, duration)
            time.sleep(0.3)
    
    def get_region_by_mouse(self):
        """通过鼠标获取游戏区域坐标"""
        print("\n" + "=" * 60)
        print("游戏区域坐标获取")
        print("=" * 60)
        print("\n使用说明:")
        print("1. 将鼠标移动到游戏区域的左上角")
        print("2. 按空格键记录第一个点")
        print("3. 将鼠标移动到游戏区域的右下角")
        print("4. 按空格键记录第二个点")
        print("5. 按 ESC 键取消")
        print("\n准备就绪，等待输入...")
        
        points = []
        cancelled = [False]
        
        def on_space(e):
            """空格键按下时记录坐标"""
            if cancelled[0]:
                return
                
            x, y = pyautogui.position()
            points.append((x, y))
            
            if len(points) == 1:
                print(f"\n✓ 左上角坐标: ({x}, {y})")
                print("请移动鼠标到右下角，然后按空格键...")
            elif len(points) == 2:
                print(f"✓ 右下角坐标: ({x}, {y})")
        
        def on_esc(e):
            """ESC键取消"""
            cancelled[0] = True
            print("\n已取消")
        
        # 注册按键事件
        keyboard.on_press_key('space', on_space)
        keyboard.on_press_key('esc', on_esc)
        
        # 等待用户输入两个点或取消
        while len(points) < 2 and not cancelled[0]:
            time.sleep(0.1)
        
        # 取消注册
        keyboard.unhook_all()
        
        if cancelled[0] or len(points) < 2:
            return None
        
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
        
        # 验证截图
        print("\n正在验证截图...")
        screenshot = ImageGrab.grab(bbox=(x1, y1, x2, y2))
        screenshot = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        
        cv2.imwrite(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'verify_region.png'), screenshot)
        print(f"验证截图已保存到 move/verify_region.png")
        print(f"截图尺寸: {screenshot.shape[1]} x {screenshot.shape[0]}")
        
        if screenshot.shape[1] == (x2-x1) and screenshot.shape[0] == (y2-y1):
            print("✓ 坐标验证成功！")
        else:
            print("✗ 警告：截图尺寸与预期不符，可能存在DPI缩放问题")
        
        return (x1, y1, x2, y2)
    
    def save_config(self, region):
        """保存配置到文件"""
        config = {
            'game_region': {
                'x1': region[0],
                'y1': region[1],
                'x2': region[2],
                'y2': region[3]
            }
        }
        
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
        
        print(f"\n配置已保存到 {self.config_file}")
    
    def load_config(self):
        """从文件加载配置"""
        if not os.path.exists(self.config_file):
            return None
        
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            region_config = config.get('game_region')
            if region_config:
                region = (
                    region_config['x1'],
                    region_config['y1'],
                    region_config['x2'],
                    region_config['y2']
                )
                print(f"\n从配置文件加载游戏区域: {region}")
                return region
        except Exception as e:
            print(f"加载配置失败: {e}")
        
        return None
        
    def initialize(self):
        """初始化游戏"""
        print("\n" + "=" * 50)
        print("游戏自动玩家初始化")
        print("=" * 50)
        
        # 尝试加载保存的配置
        saved_region = self.load_config()
        
        if saved_region:
            print(f"区域尺寸: {saved_region[2]-saved_region[0]} x {saved_region[3]-saved_region[1]}")
            choice = input("\n使用保存的配置？(y/n，直接回车=y): ").strip().lower()
            
            if choice == '' or choice == 'y':
                self.game_region = saved_region
                print("使用保存的游戏区域")
            else:
                self.game_region = self._select_region()
                if not self.game_region:
                    return False
        else:
            print("\n未找到保存的配置")
            self.game_region = self._select_region()
            if not self.game_region:
                return False
        
        # 首次识别（保存调试信息）
        return self.update_game_state(save_debug=True)
    
    def _select_region(self):
        """选择游戏区域"""
        print("\n选择获取坐标的方式:")
        print("1. 使用鼠标点击获取（推荐）")
        print("2. 手动输入坐标")
        
        choice = input("请选择 (1/2，直接回车=1): ").strip()
        
        if choice == '' or choice == '1':
            # 使用鼠标获取
            region = self.get_region_by_mouse()
            if region:
                # 保存配置
                save_choice = input("\n是否保存此配置供下次使用？(y/n，直接回车=y): ").strip().lower()
                if save_choice == '' or save_choice == 'y':
                    self.save_config(region)
                return region
            else:
                print("获取坐标失败")
                return None
        else:
            # 手动输入
            try:
                print("\n请输入游戏区域坐标:")
                x1 = int(input("左上角 X 坐标: "))
                y1 = int(input("左上角 Y 坐标: "))
                x2 = int(input("右下角 X 坐标: "))
                y2 = int(input("右下角 Y 坐标: "))
                
                region = (x1, y1, x2, y2)
                print(f"\n游戏区域: ({x1}, {y1}) 到 ({x2}, {y2})")
                print(f"区域尺寸: {x2-x1} x {y2-y1}")
                
                # 保存配置
                save_choice = input("\n是否保存此配置供下次使用？(y/n，直接回车=y): ").strip().lower()
                if save_choice == '' or save_choice == 'y':
                    self.save_config(region)
                
                return region
            except ValueError:
                print("输入错误")
                return None
    
    def update_game_state(self, save_debug=False):
        """更新游戏状态（重新识别）"""
        print("\n正在识别游戏状态...")
        
        # 截取游戏区域
        x1, y1, x2, y2 = self.game_region
        
        # 使用PIL截图（坐标已经是正确的）
        screenshot = ImageGrab.grab(bbox=(x1, y1, x2, y2))
        screenshot = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        
        print(f"截图尺寸: {screenshot.shape[1]} x {screenshot.shape[0]}")
        print(f"预期尺寸: {x2-x1} x {y2-y1}")
        
        # 检查尺寸是否匹配
        if screenshot.shape[1] != (x2-x1) or screenshot.shape[0] != (y2-y1):
            print(f"警告：截图尺寸与预期不符！可能是DPI缩放问题")
            print(f"实际: {screenshot.shape[1]}x{screenshot.shape[0]}, 预期: {x2-x1}x{y2-y1}")
        
        # 保存调试图片
        if save_debug:
            cv2.imwrite(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'debug_screenshot.png'), screenshot)
            print("调试截图已保存到 move/debug_screenshot.png")
        
        # 识别图标 - 降低阈值以识别更多图标
        results = self.matcher.match_icons(screenshot, threshold=0.70, use_multiscale=True)
        print(f"识别到 {len(results)} 个图标")
        
        # 如果识别数量明显不足，尝试更低的阈值
        if len(results) < 100:
            print(f"警告：识别数量偏少 ({len(results)}), 尝试降低阈值重新识别...")
            results = self.matcher.match_icons(screenshot, threshold=0.65, use_multiscale=True)
            print(f"重新识别到 {len(results)} 个图标")
        
        # 过滤掉空位置的误识别
        results = self.filter_empty_positions(screenshot, results)
        print(f"过滤后剩余 {len(results)} 个有效图标")
        
        # 保存标注结果用于调试
        if save_debug:
            debug_output = self.matcher.draw_results(screenshot, results)
            cv2.imwrite(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'debug_matched.png'), debug_output)
            print("标注结果已保存到 move/debug_matched.png")
        
        # 构建网格
        region_offset = (x1, y1)
        success = self.grid.build_from_results(results, region_offset)
        
        if success:
            self.grid.print_grid()
        
        return success
    
    def filter_empty_positions(self, screenshot, results):
        """过滤掉空位置的误识别"""
        import os
        from pathlib import Path
        
        # 加载所有空位置模板
        empty_dir = Path('tiles_standardized/empty')
        if not empty_dir.exists():
            print("未找到空位置模板目录，跳过空位置过滤")
            return results
        
        empty_templates = []
        for template_file in empty_dir.glob('*.png'):
            template = cv2.imread(str(template_file))
            if template is not None:
                empty_templates.append({
                    'image': template,
                    'name': template_file.name
                })
        
        if not empty_templates:
            print("未找到空位置模板，跳过空位置过滤")
            return results
        
        print(f"加载了 {len(empty_templates)} 个空位置模板")
        
        gray_screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
        
        # 使用所有模板检测空位置
        all_empty_positions = []
        
        for template_info in empty_templates:
            template = template_info['image']
            gray_empty = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
            
            # 多尺度匹配
            scales = [0.9, 1.0, 1.1]
            
            for scale in scales:
                if scale != 1.0:
                    width = int(gray_empty.shape[1] * scale)
                    height = int(gray_empty.shape[0] * scale)
                    scaled_empty = cv2.resize(gray_empty, (width, height))
                else:
                    scaled_empty = gray_empty
                
                # 检查模板是否小于截图
                if scaled_empty.shape[0] > gray_screenshot.shape[0] or \
                   scaled_empty.shape[1] > gray_screenshot.shape[1]:
                    continue
                
                # 匹配空位置
                empty_threshold = 0.7  # 进一步降低阈值
                empty_result = cv2.matchTemplate(gray_screenshot, scaled_empty, cv2.TM_CCOEFF_NORMED)
                empty_locations = np.where(empty_result >= empty_threshold)
                
                for pt in zip(*empty_locations[::-1]):
                    all_empty_positions.append({
                        'x': pt[0],
                        'y': pt[1],
                        'w': scaled_empty.shape[1],
                        'h': scaled_empty.shape[0],
                        'confidence': empty_result[pt[1], pt[0]],
                        'template': template_info['name'],
                        'scale': scale
                    })
        
        # 去重空位置
        empty_positions = self._nms_empty_positions(all_empty_positions)
        
        print(f"检测到 {len(empty_positions)} 个空位置")
        
        # 过滤结果
        filtered_results = []
        removed_count = 0
        
        for result in results:
            x, y = result['position']
            w, h = result['size']
            
            # 检查是否与任何空位置重叠
            is_empty = False
            max_overlap = 0
            best_match_template = ""
            
            for empty_pos in empty_positions:
                # 计算重叠区域
                x_overlap = max(0, min(x + w, empty_pos['x'] + empty_pos['w']) - max(x, empty_pos['x']))
                y_overlap = max(0, min(y + h, empty_pos['y'] + empty_pos['h']) - max(y, empty_pos['y']))
                overlap_area = x_overlap * y_overlap
                
                # 计算重叠比例
                result_area = w * h
                overlap_ratio = overlap_area / result_area if result_area > 0 else 0
                
                if overlap_ratio > max_overlap:
                    max_overlap = overlap_ratio
                    best_match_template = empty_pos['template']
                
                # 更严格的过滤：重叠 > 40% 才认为是空位置（提高阈值）
                if overlap_ratio > 0.40:
                    is_empty = True
                    break
            
            if is_empty:
                removed_count += 1
                print(f"  移除空位置误识别: {result['category']} at ({x}, {y}), "
                      f"重叠率: {max_overlap:.2f}, 模板: {best_match_template}")
            else:
                # 额外的启发式过滤
                should_remove = False
                
                # 1. 如果是20且置信度很低（提高阈值，减少误删）
                if result['category'] == '20' and result.get('confidence', 1.0) < 0.65:
                    should_remove = True
                    print(f"  移除低置信度20: at ({x}, {y}), 置信度: {result.get('confidence', 'N/A')}")
                
                # 2. 如果是20且位置在截图边缘（减小边缘范围）
                elif result['category'] == '20':
                    # 更严格的边缘检测：只移除真正在边缘的
                    margin = 5  # 减小边缘范围
                    if (x < margin or y < margin or 
                        x + w > screenshot.shape[1] - margin or 
                        y + h > screenshot.shape[0] - margin):
                        should_remove = True
                        print(f"  移除边缘20: at ({x}, {y})")
                
                if should_remove:
                    removed_count += 1
                else:
                    filtered_results.append(result)
        
        print(f"移除了 {removed_count} 个空位置误识别")
        return filtered_results
    
    def _nms_empty_positions(self, positions, overlap_thresh=0.3):
        """对空位置进行非极大值抑制"""
        if len(positions) == 0:
            return []
        
        # 按置信度排序
        positions = sorted(positions, key=lambda x: x['confidence'], reverse=True)
        
        keep = []
        for pos in positions:
            should_keep = True
            
            for kept_pos in keep:
                # 计算重叠
                x_overlap = max(0, min(pos['x'] + pos['w'], kept_pos['x'] + kept_pos['w']) - 
                              max(pos['x'], kept_pos['x']))
                y_overlap = max(0, min(pos['y'] + pos['h'], kept_pos['y'] + kept_pos['h']) - 
                              max(pos['y'], kept_pos['y']))
                overlap_area = x_overlap * y_overlap
                
                area1 = pos['w'] * pos['h']
                area2 = kept_pos['w'] * kept_pos['h']
                
                if overlap_area / min(area1, area2) > overlap_thresh:
                    should_keep = False
                    break
            
            if should_keep:
                keep.append(pos)
        
        return keep
    
    def find_adjacent_pairs(self):
        """查找所有可直接消除的相同图标对（相邻或中间只有空格）"""
        pairs = []
        
        for row in range(self.grid.rows):
            for col in range(self.grid.cols):
                cell = self.grid.get_cell(row, col)
                if cell['is_empty']:
                    continue
                
                cell_type = cell['type']
                
                # 检查右边（包括中间有空格的情况）
                for offset in range(1, self.grid.cols - col):
                    check_col = col + offset
                    check_cell = self.grid.get_cell(row, check_col)
                    
                    if check_cell['is_empty']:
                        # 空格，继续检查
                        continue
                    elif check_cell['type'] == cell_type:
                        # 找到相同类型，检查中间是否都是空格
                        all_empty_between = True
                        for mid_col in range(col + 1, check_col):
                            if not self.grid.get_cell(row, mid_col)['is_empty']:
                                all_empty_between = False
                                break
                        
                        if all_empty_between:
                            pairs.append({
                                'type': cell_type,
                                'pos1': (row, col),
                                'pos2': (row, check_col),
                                'direction': 'horizontal',
                                'distance': check_col - col
                            })
                        break  # 找到第一个非空格子，停止
                    else:
                        # 不同类型，停止
                        break
                
                # 检查下边（包括中间有空格的情况）
                for offset in range(1, self.grid.rows - row):
                    check_row = row + offset
                    check_cell = self.grid.get_cell(check_row, col)
                    
                    if check_cell['is_empty']:
                        # 空格，继续检查
                        continue
                    elif check_cell['type'] == cell_type:
                        # 找到相同类型，检查中间是否都是空格
                        all_empty_between = True
                        for mid_row in range(row + 1, check_row):
                            if not self.grid.get_cell(mid_row, col)['is_empty']:
                                all_empty_between = False
                                break
                        
                        if all_empty_between:
                            pairs.append({
                                'type': cell_type,
                                'pos1': (row, col),
                                'pos2': (check_row, col),
                                'direction': 'vertical',
                                'distance': check_row - row
                            })
                        break  # 找到第一个非空格子，停止
                    else:
                        # 不同类型，停止
                        break
        
        return pairs
    
    def click_cell(self, row, col):
        """点击指定格子"""
        cell = self.grid.get_cell(row, col)
        if not cell:
            return False
        
        x = cell['abs_center_x']
        y = cell['abs_center_y']
        
        print(f"点击格子 ({row}, {col}) at ({x}, {y})")
        pyautogui.click(x, y)
        time.sleep(0.3)
        
        return True
    
    def eliminate_pair(self, pair):
        """消除一对图标"""
        pos1 = pair['pos1']
        pos2 = pair['pos2']
        
        print(f"\n消除配对: {pair['type']} at {pos1} 和 {pos2}")
        
        # 点击其中一个
        self.click_cell(pos1[0], pos1[1])
        
        # 标记为空
        self.grid.set_empty(pos1[0], pos1[1])
        self.grid.set_empty(pos2[0], pos2[1])
        
        self.move_count += 1
        
        # 等待动画
        time.sleep(0.5)
    
    def find_smart_moves(self):
        """智能移动查找，考虑简单的连锁移动"""
        
        # 1. 首先找直接可行的移动
        direct_moves = self.find_one_move_pairs()
        if direct_moves:
            return direct_moves
        
        # 2. 找需要一步清理的移动
        clearing_moves = self.find_one_step_clearing_moves()
        if clearing_moves:
            return clearing_moves
        
        return []
    
    def find_one_step_clearing_moves(self):
        """寻找只需要一步清理就能实现的目标移动"""
        opportunities = []
        
        # 统计每种类型的位置
        type_positions = defaultdict(list)
        for row in range(self.grid.rows):
            for col in range(self.grid.cols):
                cell = self.grid.get_cell(row, col)
                if not cell['is_empty']:
                    type_positions[cell['type']].append((row, col))
        
        # 对于每种有2个或以上的类型，检查是否能通过清理移动配对
        for icon_type, positions in type_positions.items():
            if len(positions) < 2:
                continue
            
            # 检查所有配对组合
            for i in range(len(positions)):
                for j in range(i + 1, len(positions)):
                    pos1 = positions[i]
                    pos2 = positions[j]
                    
                    # 检查相邻行的情况（如你提到的15的例子）
                    if abs(pos1[0] - pos2[0]) == 1 and pos1[1] == pos2[1]:
                        # 同一列相邻行，检查是否能通过清理实现移动
                        clearing_move = self.find_clearing_for_adjacent_rows(pos1, pos2, icon_type)
                        if clearing_move:
                            opportunities.append(clearing_move)
                    
                    # 检查相邻列的情况
                    elif abs(pos1[1] - pos2[1]) == 1 and pos1[0] == pos2[0]:
                        # 同一行相邻列，检查是否能通过清理实现移动
                        clearing_move = self.find_clearing_for_adjacent_cols(pos1, pos2, icon_type)
                        if clearing_move:
                            opportunities.append(clearing_move)
        
        return opportunities
    
    def find_clearing_for_adjacent_rows(self, pos1, pos2, icon_type):
        """为相邻行的配对寻找清理移动"""
        row1, col = pos1
        row2, _ = pos2
        
        # 确保row1 < row2
        if row1 > row2:
            row1, row2 = row2, row1
            pos1, pos2 = pos2, pos1
        
        # 检查pos1能否向下移动到row2
        target_row = row2
        target_pos = (target_row, col)
        
        # 检查目标位置是否被占用
        target_cell = self.grid.get_cell(target_row, col)
        if target_cell['is_empty']:
            # 目标位置是空的，可以直接移动
            return {
                'type': icon_type,
                'pos1': pos1,
                'pos2': pos2,
                'move_type': 'col_slide_align',
                'from_row': row1,
                'from_col': col,
                'to_row': target_row,
                'to_col': col,
                'distance': 1,
                'priority': 1,
                'will_create_match': True
            }
        
        # 目标位置被占用，检查占用的方块能否移动
        blocking_type = target_cell['type']
        blocking_pos = (target_row, col)
        
        # 寻找阻挡方块的可行移动
        clearing_moves = self.find_moves_for_position(blocking_pos, blocking_type)
        
        if clearing_moves:
            # 返回清理移动序列
            return {
                'type': icon_type,
                'pos1': pos1,
                'pos2': pos2,
                'move_type': 'clearing_sequence',
                'clearing_moves': clearing_moves,
                'final_move': {
                    'from_row': row1,
                    'from_col': col,
                    'to_row': target_row,
                    'to_col': col
                },
                'distance': len(clearing_moves) + 1,
                'priority': len(clearing_moves) + 10,  # 清理移动优先级较低
                'will_create_match': True
            }
        
        return None
    
    def find_clearing_for_adjacent_cols(self, pos1, pos2, icon_type):
        """为相邻列的配对寻找清理移动"""
        row, col1 = pos1
        _, col2 = pos2
        
        # 确保col1 < col2
        if col1 > col2:
            col1, col2 = col2, col1
            pos1, pos2 = pos2, pos1
        
        # 检查pos1能否向右移动到col2
        target_col = col2
        target_pos = (row, target_col)
        
        # 检查目标位置是否被占用
        target_cell = self.grid.get_cell(row, target_col)
        if target_cell['is_empty']:
            # 目标位置是空的，可以直接移动
            return {
                'type': icon_type,
                'pos1': pos1,
                'pos2': pos2,
                'move_type': 'row_slide_align',
                'from_row': row,
                'from_col': col1,
                'to_row': row,
                'to_col': target_col,
                'distance': 1,
                'priority': 1,
                'will_create_match': True
            }
        
        # 目标位置被占用，检查占用的方块能否移动
        blocking_type = target_cell['type']
        blocking_pos = (row, target_col)
        
        # 寻找阻挡方块的可行移动
        clearing_moves = self.find_moves_for_position(blocking_pos, blocking_type)
        
        if clearing_moves:
            # 返回清理移动序列
            return {
                'type': icon_type,
                'pos1': pos1,
                'pos2': pos2,
                'move_type': 'clearing_sequence',
                'clearing_moves': clearing_moves,
                'final_move': {
                    'from_row': row,
                    'from_col': col1,
                    'to_row': row,
                    'to_col': target_col
                },
                'distance': len(clearing_moves) + 1,
                'priority': len(clearing_moves) + 10,
                'will_create_match': True
            }
        
        return None
    
    def find_moves_for_position(self, pos, piece_type):
        """为指定位置的方块寻找可行的移动"""
        row, col = pos
        possible_moves = []
        
        # 检查四个方向的移动
        directions = [
            ('up', -1, 0),
            ('down', 1, 0),
            ('left', 0, -1),
            ('right', 0, 1)
        ]
        
        for direction, dr, dc in directions:
            # 检查能移动多远
            max_distance = 0
            for distance in range(1, max(self.grid.rows, self.grid.cols)):
                new_row = row + dr * distance
                new_col = col + dc * distance
                
                # 检查边界
                if (new_row < 0 or new_row >= self.grid.rows or 
                    new_col < 0 or new_col >= self.grid.cols):
                    break
                
                # 检查目标位置是否为空
                target_cell = self.grid.get_cell(new_row, new_col)
                if not target_cell['is_empty']:
                    break
                
                max_distance = distance
            
            # 如果能移动，添加到可能移动列表
            if max_distance > 0:
                possible_moves.append({
                    'from_pos': pos,
                    'to_pos': (row + dr * max_distance, col + dc * max_distance),
                    'direction': direction,
                    'distance': max_distance,
                    'type': piece_type
                })
        
        return possible_moves

    def find_one_move_pairs(self):
        """查找只需一步移动就能配对的图标（不包括中间只有空格的情况）"""
        opportunities = []
        
        # 统计每种类型的位置
        type_positions = defaultdict(list)
        for row in range(self.grid.rows):
            for col in range(self.grid.cols):
                cell = self.grid.get_cell(row, col)
                if not cell['is_empty']:
                    type_positions[cell['type']].append((row, col))
        
        # 对于每种有2个或以上的类型，检查是否能通过一步移动配对
        for icon_type, positions in type_positions.items():
            if len(positions) < 2:
                continue
            
            # 检查所有配对组合
            for i in range(len(positions)):
                for j in range(i + 1, len(positions)):
                    pos1 = positions[i]
                    pos2 = positions[j]
                    
                    # 情况1：在同一行，通过行滑动对齐
                    if pos1[0] == pos2[0]:
                        row = pos1[0]
                        col1, col2 = sorted([pos1[1], pos2[1]])
                        
                        # 检查是否已经相邻（紧挨着）
                        if col2 - col1 == 1:
                            continue  # 已经相邻，应该直接消除，不需要移动
                        
                        # 检查能否通过行滑动让它们相邻
                        can_slide = self._can_slide_row(row, col1, col2)
                        if can_slide:
                            distance = col2 - col1
                            opportunities.append({
                                'type': icon_type,
                                'pos1': pos1,
                                'pos2': pos2,
                                'move_type': 'row_slide',
                                'row': row,
                                'from_col': col1,
                                'to_col': col2,
                                'distance': distance,
                                'priority': distance,
                                'will_create_match': True  # 标记这个移动会创造匹配
                            })
                    
                    # 情况2：在同一列，通过列滑动对齐
                    elif pos1[1] == pos2[1]:
                        col = pos1[1]
                        row1, row2 = sorted([pos1[0], pos2[0]])
                        
                        # 检查是否已经相邻（紧挨着）
                        if row2 - row1 == 1:
                            continue  # 已经相邻，应该直接消除，不需要移动
                        
                        # 检查能否通过列滑动让它们相邻
                        can_slide = self._can_slide_col(col, row1, row2)
                        if can_slide:
                            distance = row2 - row1
                            opportunities.append({
                                'type': icon_type,
                                'pos1': pos1,
                                'pos2': pos2,
                                'move_type': 'col_slide',
                                'col': col,
                                'from_row': row1,
                                'to_row': row2,
                                'distance': distance,
                                'priority': distance,
                                'will_create_match': True
                            })
                    
                    # 情况3：在相邻列，通过列滑动让它们在同一行
                    elif abs(pos1[1] - pos2[1]) == 1:
                        # 两个图标在相邻列
                        row1, row2 = pos1[0], pos2[0]
                        col1, col2 = pos1[1], pos2[1]
                        
                        # 尝试滑动第一个图标到第二个图标的行
                        can_slide1 = self._can_slide_to_align(row1, col1, row2, col2)
                        if can_slide1:
                            distance = abs(row2 - row1)
                            opportunities.append({
                                'type': icon_type,
                                'pos1': pos1,
                                'pos2': pos2,
                                'move_type': 'col_slide_align',
                                'from_row': row1,
                                'from_col': col1,
                                'to_row': row2,
                                'to_col': col1,  # 列不变
                                'distance': distance,
                                'priority': distance + 5,  # 稍低优先级
                                'will_create_match': True
                            })
                        
                        # 尝试滑动第二个图标到第一个图标的行
                        can_slide2 = self._can_slide_to_align(row2, col2, row1, col1)
                        if can_slide2:
                            distance = abs(row1 - row2)
                            opportunities.append({
                                'type': icon_type,
                                'pos1': pos2,
                                'pos2': pos1,
                                'move_type': 'col_slide_align',
                                'from_row': row2,
                                'from_col': col2,
                                'to_row': row1,
                                'to_col': col2,  # 列不变
                                'distance': distance,
                                'priority': distance + 5,
                                'will_create_match': True
                            })
                    
                    # 情况4：在相邻行，通过行滑动让它们在同一列
                    elif abs(pos1[0] - pos2[0]) == 1:
                        # 两个图标在相邻行
                        row1, row2 = pos1[0], pos2[0]
                        col1, col2 = pos1[1], pos2[1]
                        
                        # 尝试滑动第一个图标到第二个图标的列
                        can_slide1 = self._can_slide_to_align_row(row1, col1, row2, col2)
                        if can_slide1:
                            distance = abs(col2 - col1)
                            opportunities.append({
                                'type': icon_type,
                                'pos1': pos1,
                                'pos2': pos2,
                                'move_type': 'row_slide_align',
                                'from_row': row1,
                                'from_col': col1,
                                'to_row': row1,  # 行不变
                                'to_col': col2,
                                'distance': distance,
                                'priority': distance + 5,
                                'will_create_match': True
                            })
                        
                        # 尝试滑动第二个图标到第一个图标的列
                        can_slide2 = self._can_slide_to_align_row(row2, col2, row1, col1)
                        if can_slide2:
                            distance = abs(col1 - col2)
                            opportunities.append({
                                'type': icon_type,
                                'pos1': pos2,
                                'pos2': pos1,
                                'move_type': 'row_slide_align',
                                'from_row': row2,
                                'from_col': col2,
                                'to_row': row2,  # 行不变
                                'to_col': col1,
                                'distance': distance,
                                'priority': distance + 5,
                                'will_create_match': True
                            })
        
        # 按优先级排序（距离小的优先）
        opportunities.sort(key=lambda x: x['priority'])
        
        return opportunities
    
    def find_connected_group(self, start_row, start_col, direction='down'):
        """找到从指定位置开始的连续砖块组"""
        group = [(start_row, start_col)]
        
        if direction == 'down':
            # 向下查找连续的砖块
            current_row = start_row + 1
            while current_row < self.grid.rows:
                cell = self.grid.get_cell(current_row, start_col)
                if cell['is_empty']:
                    break
                group.append((current_row, start_col))
                current_row += 1
        elif direction == 'up':
            # 向上查找连续的砖块
            current_row = start_row - 1
            while current_row >= 0:
                cell = self.grid.get_cell(current_row, start_col)
                if cell['is_empty']:
                    break
                group.append((current_row, start_col))
                current_row -= 1
        elif direction == 'right':
            # 向右查找连续的砖块
            current_col = start_col + 1
            while current_col < self.grid.cols:
                cell = self.grid.get_cell(start_row, current_col)
                if cell['is_empty']:
                    break
                group.append((start_row, current_col))
                current_col += 1
        elif direction == 'left':
            # 向左查找连续的砖块
            current_col = start_col - 1
            while current_col >= 0:
                cell = self.grid.get_cell(start_row, current_col)
                if cell['is_empty']:
                    break
                group.append((start_row, current_col))
                current_col -= 1
        
        return group
    
    def can_move_group(self, group, direction, distance):
        """检查砖块组是否可以移动指定距离"""
        for row, col in group:
            if direction == 'down':
                # 检查从当前位置到目标位置的整个路径
                for step in range(1, distance + 1):
                    target_row = row + step
                    if target_row >= self.grid.rows:
                        return False
                    # 检查路径上的位置是否为空（且不在组内）
                    if (target_row, col) not in group:
                        target_cell = self.grid.get_cell(target_row, col)
                        if not target_cell['is_empty']:
                            return False
            elif direction == 'up':
                # 检查从当前位置到目标位置的整个路径
                for step in range(1, distance + 1):
                    target_row = row - step
                    if target_row < 0:
                        return False
                    if (target_row, col) not in group:
                        target_cell = self.grid.get_cell(target_row, col)
                        if not target_cell['is_empty']:
                            return False
            elif direction == 'right':
                # 检查从当前位置到目标位置的整个路径
                for step in range(1, distance + 1):
                    target_col = col + step
                    if target_col >= self.grid.cols:
                        return False
                    if (row, target_col) not in group:
                        target_cell = self.grid.get_cell(row, target_col)
                        if not target_cell['is_empty']:
                            return False
            elif direction == 'left':
                # 检查从当前位置到目标位置的整个路径
                for step in range(1, distance + 1):
                    target_col = col - step
                    if target_col < 0:
                        return False
                    if (row, target_col) not in group:
                        target_cell = self.grid.get_cell(row, target_col)
                        if not target_cell['is_empty']:
                            return False
        
        return True
    
    def _can_slide_to_align(self, from_row, from_col, to_row, to_col):
        """检查是否可以通过列滑动让图标对齐（用于相邻列的情况）"""
        # 检查from_row到to_row之间是否可以滑动
        if from_row == to_row:
            return False  # 已经对齐
        
        # 首先检查简单情况：路径上都是空的
        if from_row < to_row:
            # 向下移动：检查from_row+1到to_row之间是否都是空的
            all_empty = True
            for check_row in range(from_row + 1, to_row + 1):
                cell = self.grid.get_cell(check_row, from_col)
                if not cell['is_empty']:
                    all_empty = False
                    break
            if all_empty:
                return True
        else:
            # 向上移动：检查to_row到from_row-1之间是否都是空的
            all_empty = True
            for check_row in range(to_row, from_row):
                cell = self.grid.get_cell(check_row, from_col)
                if not cell['is_empty']:
                    all_empty = False
                    break
            if all_empty:
                return True
        
        # 如果简单移动不行，检查方块组移动
        if from_row < to_row:
            # 向下移动：找到从from_row开始向下的连续块组
            direction = 'down'
            distance = to_row - from_row
            group = self.find_connected_group(from_row, from_col, direction)
        else:
            # 向上移动：找到从from_row开始向上的连续块组
            direction = 'up'
            distance = from_row - to_row
            group = self.find_connected_group(from_row, from_col, direction)
        
        # 检查组是否可以移动
        can_move = self.can_move_group(group, direction, distance)
        
        return can_move
    
    def _can_slide_to_align_row(self, from_row, from_col, to_row, to_col):
        """检查是否可以通过行滑动让图标对齐（用于相邻行的情况）"""
        # 检查from_col到to_col之间是否可以滑动
        if from_col == to_col:
            return False  # 已经对齐
        
        # 首先检查简单情况：路径上都是空的
        if from_col < to_col:
            # 向右移动：检查from_col+1到to_col之间是否都是空的
            all_empty = True
            for check_col in range(from_col + 1, to_col + 1):
                cell = self.grid.get_cell(from_row, check_col)
                if not cell['is_empty']:
                    all_empty = False
                    break
            if all_empty:
                return True
        else:
            # 向左移动：检查to_col到from_col-1之间是否都是空的
            all_empty = True
            for check_col in range(to_col, from_col):
                cell = self.grid.get_cell(from_row, check_col)
                if not cell['is_empty']:
                    all_empty = False
                    break
            if all_empty:
                return True
        
        # 如果简单移动不行，检查方块组移动
        if from_col < to_col:
            # 向右移动：找到从from_col开始向右的连续块组
            direction = 'right'
            distance = to_col - from_col
            group = self.find_connected_group(from_row, from_col, direction)
        else:
            # 向左移动：找到从from_col开始向左的连续块组
            direction = 'left'
            distance = from_col - to_col
            group = self.find_connected_group(from_row, from_col, direction)
        
        # 检查组是否可以移动
        can_move = self.can_move_group(group, direction, distance)
        
        return can_move
        
        return can_move
    
    def _can_slide_row(self, row, col1, col2):
        """检查是否可以滑动行使两个格子相邻"""
        # 只有当中间都是空格时才能滑动
        all_empty = True
        for col in range(col1 + 1, col2):
            cell = self.grid.get_cell(row, col)
            if not cell['is_empty']:
                all_empty = False
                break
        
        return all_empty
    
    def _can_slide_col(self, col, row1, row2):
        """检查是否可以滑动列使两个格子相邻"""
        # 只有当中间都是空格时才能滑动
        all_empty = True
        for row in range(row1 + 1, row2):
            cell = self.grid.get_cell(row, col)
            if not cell['is_empty']:
                all_empty = False
                break
        
        return all_empty
    
    def validate_move_opportunity(self, opportunity):
        """验证移动机会是否真的有效"""
        pos1 = opportunity['pos1']
        pos2 = opportunity['pos2']
        
        # 检查两个位置是否都存在且类型相同
        cell1 = self.grid.get_cell(pos1[0], pos1[1])
        cell2 = self.grid.get_cell(pos2[0], pos2[1])
        
        if not cell1 or not cell2:
            print(f"  验证失败: 位置不存在")
            return False
            
        if cell1['is_empty'] or cell2['is_empty']:
            print(f"  验证失败: 位置为空")
            return False
            
        if cell1['type'] != cell2['type']:
            print(f"  验证失败: 类型不匹配 {cell1['type']} vs {cell2['type']}")
            return False
            
        if cell1['type'] != opportunity['type']:
            print(f"  验证失败: 类型与机会不符 {cell1['type']} vs {opportunity['type']}")
            return False
            
        return True
    
    def execute_slide(self, opportunity):
        """执行滑动操作"""
        # 再次验证移动机会（双重保险）
        if not self.validate_move_opportunity(opportunity):
            print(f"执行前验证失败，取消移动")
            return False
            
        print(f"执行滑动: {opportunity['type']} ({opportunity['move_type']})")
        move_type = opportunity['move_type']
        
        if move_type == 'row_slide':
            row = opportunity['row']
            from_col = opportunity['from_col']
            to_col = opportunity['to_col']
            
            from_cell = self.grid.get_cell(row, from_col)
            
            # 计算需要移动的实际距离
            empty_count = 0
            for col in range(from_col + 1, to_col):
                cell = self.grid.get_cell(row, col)
                if cell['is_empty']:
                    empty_count += 1
            
            move_cells = to_col - from_col - empty_count - 1
            
            if move_cells <= 0:
                print(f"警告：计算的移动距离为 {move_cells}，跳过此操作")
                return
            
            distance = move_cells * self.grid.cell_width
            start_x = from_cell['abs_center_x']
            start_y = from_cell['abs_center_y']
            
            print(f"行滑动: 从 ({start_x}, {start_y}) 向右滑动 {move_cells} 格 ({distance} 像素)")
            
            pyautogui.moveTo(start_x, start_y)
            time.sleep(0.1)
            self._drag_rel(start_x, start_y, distance, 0, duration=0.5)
            time.sleep(0.5)
            
        elif move_type == 'col_slide':
            col = opportunity['col']
            from_row = opportunity['from_row']
            to_row = opportunity['to_row']
            
            from_cell = self.grid.get_cell(from_row, col)
            
            # 计算需要移动的实际距离
            empty_count = 0
            for row in range(from_row + 1, to_row):
                cell = self.grid.get_cell(row, col)
                if cell['is_empty']:
                    empty_count += 1
            
            move_cells = to_row - from_row - empty_count - 1
            
            if move_cells <= 0:
                print(f"警告：计算的移动距离为 {move_cells}，跳过此操作")
                return
            
            distance = move_cells * self.grid.cell_height
            start_x = from_cell['abs_center_x']
            start_y = from_cell['abs_center_y']
            
            print(f"列滑动: 从 ({start_x}, {start_y}) 向下滑动 {move_cells} 格 ({distance} 像素)")
            
            pyautogui.moveTo(start_x, start_y)
            time.sleep(0.1)
            self._drag_rel(start_x, start_y, 0, distance, duration=0.5)
            time.sleep(0.5)
            
        elif move_type == 'col_slide_align':
            # 列滑动对齐（用于相邻列的情况）- 使用块组移动
            from_row = opportunity['from_row']
            from_col = opportunity['from_col']
            to_row = opportunity['to_row']
            
            from_cell = self.grid.get_cell(from_row, from_col)
            
            # 确定移动方向和距离
            if to_row > from_row:
                direction = 'down'
                move_distance = to_row - from_row
                group = self.find_connected_group(from_row, from_col, direction)
            else:
                direction = 'up'
                move_distance = from_row - to_row
                group = self.find_connected_group(from_row, from_col, direction)
            
            print(f"列滑动对齐（块组移动）: 移动 {len(group)} 个砖块 {direction} {move_distance} 格")
            
            # 计算实际像素距离
            pixel_distance = move_distance * self.grid.cell_height
            if direction == 'up':
                pixel_distance = -pixel_distance
            
            start_x = from_cell['abs_center_x']
            start_y = from_cell['abs_center_y']
            
            pyautogui.moveTo(start_x, start_y)
            time.sleep(0.1)
            self._drag_rel(start_x, start_y, 0, pixel_distance, duration=0.8)  # 稍慢一点确保块组一起移动
            time.sleep(0.5)
            
        elif move_type == 'clearing_sequence':
            # 执行清理移动序列
            print(f"执行清理移动序列: {len(opportunity['clearing_moves'])} 步清理 + 1 步目标移动")
            
            # 先执行所有清理移动
            for i, clearing_move in enumerate(opportunity['clearing_moves']):
                print(f"  清理步骤 {i+1}: 移动 {clearing_move['type']} 从 {clearing_move['from_pos']} 到 {clearing_move['to_pos']}")
                
                # 执行单个清理移动
                success = self.execute_simple_move(clearing_move)
                if not success:
                    print(f"清理移动失败，中止序列")
                    return False
                
                # 等待动画完成
                time.sleep(0.8)
            
            # 执行最终的目标移动
            final_move = opportunity['final_move']
            print(f"  最终移动: {opportunity['type']} 从 ({final_move['from_row']}, {final_move['from_col']}) 到 ({final_move['to_row']}, {final_move['to_col']})")
            
            final_move_opp = {
                'type': opportunity['type'],
                'move_type': 'col_slide_align' if final_move['from_col'] == final_move['to_col'] else 'row_slide_align',
                'from_row': final_move['from_row'],
                'from_col': final_move['from_col'],
                'to_row': final_move['to_row'],
                'to_col': final_move['to_col']
            }
            
            return self.execute_slide(final_move_opp)
            
        elif move_type == 'row_slide_align':
            # 行滑动对齐（用于相邻行的情况）- 使用块组移动
            from_row = opportunity['from_row']
            from_col = opportunity['from_col']
            to_col = opportunity['to_col']
            
            from_cell = self.grid.get_cell(from_row, from_col)
            
            # 确定移动方向和距离
            if to_col > from_col:
                direction = 'right'
                move_distance = to_col - from_col
                group = self.find_connected_group(from_row, from_col, direction)
            else:
                direction = 'left'
                move_distance = from_col - to_col
                group = self.find_connected_group(from_row, from_col, direction)
            
            print(f"行滑动对齐（块组移动）: 移动 {len(group)} 个砖块 {direction} {move_distance} 格")
            
            # 计算实际像素距离
            pixel_distance = move_distance * self.grid.cell_width
            if direction == 'left':
                pixel_distance = -pixel_distance
            
            start_x = from_cell['abs_center_x']
            start_y = from_cell['abs_center_y']
            
            pyautogui.moveTo(start_x, start_y)
            time.sleep(0.1)
            self._drag_rel(start_x, start_y, pixel_distance, 0, duration=0.8)  # 稍慢一点确保块组一起移动
            time.sleep(0.5)
        
        self.move_count += 1
        return True
    
    def execute_simple_move(self, move):
        """执行简单的单步移动"""
        from_pos = move['from_pos']
        to_pos = move['to_pos']
        direction = move['direction']
        
        from_row, from_col = from_pos
        to_row, to_col = to_pos
        
        from_cell = self.grid.get_cell(from_row, from_col)
        if from_cell['is_empty']:
            print(f"警告: 起始位置 {from_pos} 为空，无法移动")
            return False
        
        # 计算移动距离
        if direction in ['left', 'right']:
            pixel_distance = abs(to_col - from_col) * self.grid.cell_width
            if direction == 'left':
                pixel_distance = -pixel_distance
            
            start_x = from_cell['abs_center_x']
            start_y = from_cell['abs_center_y']
            
            print(f"    简单移动: 从 ({start_x}, {start_y}) 向{direction}移动 {abs(to_col - from_col)} 格")
            
            pyautogui.moveTo(start_x, start_y)
            time.sleep(0.1)
            self._drag_rel(start_x, start_y, pixel_distance, 0, duration=0.5)
            
        else:  # up, down
            pixel_distance = abs(to_row - from_row) * self.grid.cell_height
            if direction == 'up':
                pixel_distance = -pixel_distance
            
            start_x = from_cell['abs_center_x']
            start_y = from_cell['abs_center_y']
            
            print(f"    简单移动: 从 ({start_x}, {start_y}) 向{direction}移动 {abs(to_row - from_row)} 格")
            
            pyautogui.moveTo(start_x, start_y)
            time.sleep(0.1)
            self._drag_rel(start_x, start_y, 0, pixel_distance, duration=0.5)
        
        return True
    
    def play_one_round(self):
        """执行一轮游戏"""
        # 1. 查找可直接消除的配对（相邻或中间只有空格）
        adjacent_pairs = self.find_adjacent_pairs()
        
        if adjacent_pairs:
            # 按距离排序，优先消除距离近的
            adjacent_pairs.sort(key=lambda x: x.get('distance', 1))
            
            pair = adjacent_pairs[0]
            
            if pair.get('distance', 1) == 1:
                print(f"找到相邻配对: {pair['type']} at {pair['pos1']} 和 {pair['pos2']}")
            else:
                print(f"找到可消除配对: {pair['type']} at {pair['pos1']} 和 {pair['pos2']} (中间有 {pair['distance']-1} 个空格)")
            
            # 消除配对
            self.eliminate_pair(pair)
            return True
        
        print("没有找到可直接消除的配对，寻找需要移动的机会...")
        
        # 2. 使用智能移动查找（包括清理移动）
        opportunities = self.find_smart_moves()
        
        # 过滤掉最近执行过的移动和重复的移动
        filtered_opportunities = []
        seen_moves = set()
        
        for opp in opportunities:
            move_signature = f"{opp['type']}_{opp['move_type']}_{opp['pos1']}_{opp['pos2']}"
            
            # 检查是否在历史记录中
            if move_signature in self.last_moves:
                continue
                
            # 检查是否在当前轮次中重复
            if move_signature in seen_moves:
                continue
                
            seen_moves.add(move_signature)
            filtered_opportunities.append(opp)
        
        if filtered_opportunities:
            print(f"找到 {len(filtered_opportunities)} 个可行移动机会")
            
            # 验证并执行第一个有效的机会
            for i, opp in enumerate(filtered_opportunities):
                print(f"  机会{i+1}: {opp['type']} at {opp['pos1']} 和 {opp['pos2']}, "
                      f"移动类型: {opp['move_type']}")
                
                # 验证移动机会
                if self.validate_move_opportunity(opp):
                    print(f"验证通过，执行移动")
                    
                    # 记录这次移动
                    move_signature = f"{opp['type']}_{opp['move_type']}_{opp['pos1']}_{opp['pos2']}"
                    self.last_moves.append(move_signature)
                    if len(self.last_moves) > self.max_history:
                        self.last_moves.pop(0)
                    
                    self.execute_slide(opp)
                    return True
                else:
                    print(f"验证失败，跳过此机会")
            
            print("所有移动机会验证都失败")
            return False
        
        print("没有找到可行的移动")
        return False
    
    def auto_play(self, max_rounds=100):
        """自动玩游戏"""
        print("\n" + "=" * 50)
        print("开始自动游戏")
        print("=" * 50)
        
        for round_num in range(1, max_rounds + 1):
            print(f"\n{'='*50}")
            print(f"第 {round_num} 轮 (已执行 {self.move_count} 次操作)")
            print(f"{'='*50}")
            
            # 执行一轮
            success = self.play_one_round()
            
            if not success:
                print("\n无法继续，游戏结束或需要人工干预")
                break
            
            # 重新识别游戏状态
            time.sleep(1)
            if not self.update_game_state():
                print("识别失败")
                break
            
            # 检查是否通关
            filled_count = sum(1 for cell in self.grid.grid.values() if not cell['is_empty'])
            if filled_count == 0:
                print("\n" + "=" * 50)
                print("恭喜通关！")
                print(f"总共执行了 {self.move_count} 次操作")
                print("=" * 50)
                break
        
        print(f"\n游戏结束，共执行 {self.move_count} 次操作")


def main():
    """主函数"""
    # 设置pyautogui安全设置
    pyautogui.PAUSE = 0.1
    pyautogui.FAILSAFE = True  # 鼠标移到屏幕角落可以紧急停止
    
    player = GameAutoPlayer()
    
    # 初始化
    if not player.initialize():
        print("初始化失败")
        return
    
    # 选择游戏模式
    print("\n" + "=" * 60)
    print("选择游戏模式")
    print("=" * 60)
    print("1. GBFS智能求解（推荐） - 一次性求解并执行所有步骤")
    print("2. 逐轮自动游戏 - 每轮识别并寻找移动机会")
    print("\n请选择模式 (1/2，回车=1): ", end="")
    
    choice = input().strip()
    
    if choice == "" or choice == "1":
        # GBFS模式
        print("\n使用 GBFS 智能求解模式")
        
        # 求解
        path = player.solve_with_gbfs()
        
        if path:
            # 预览模式：输出棋盘和每步移动
            player.preview_solution()
            
            # 询问是否执行
            print("\n是否执行此方案？(y/n，回车=y): ", end="")
            choice = input().strip().lower()
            
            if choice == '' or choice == 'y':
                # 询问执行模式
                print("\n选择执行模式:")
                print("  1. 自动执行（连续自动完成所有步骤）")
                print("  2. 手动执行（按空格/回车执行每一步）")
                print("请选择 (1/2，回车=1): ", end="")
                mode_choice = input().strip()
                
                if mode_choice == '2':
                    player.execute_solution(move_delay=0.5, manual_mode=True)
                else:
                    player.execute_solution(move_delay=0.5, manual_mode=False)
            else:
                print("已取消执行")
        else:
            print("求解失败，尝试使用逐轮模式...")
            player.auto_play()
    else:
        # 逐轮模式
        print("\n使用逐轮自动游戏模式")
        print("注意：鼠标将被自动控制")
        print("如需紧急停止，将鼠标移到屏幕左上角")
        input("按回车键开始...")
        player.auto_play()


if __name__ == '__main__':
    main()
