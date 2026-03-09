"""
游戏自动玩家
功能：自动识别、分析并执行游戏操作
"""

import cv2
import numpy as np
from PIL import ImageGrab
import pyautogui
import time
from collections import defaultdict
from game_icon_matcher import GameIconMatcher


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
            print("建议检查 debug_screenshot.png 和 debug_matched.png")
        
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
            line = ""
            for col in range(self.cols):
                cell = self.grid[(row, col)]
                if cell['is_empty']:
                    line += "  . "
                else:
                    line += f" {cell['type']}"
            print(line)


class GameAutoPlayer:
    """游戏自动玩家"""
    
    def __init__(self):
        self.matcher = GameIconMatcher()
        self.grid = GameGrid()
        self.game_region = None  # (x1, y1, x2, y2)
        self.move_count = 0
        
    def initialize(self):
        """初始化游戏"""
        print("\n" + "=" * 50)
        print("游戏自动玩家初始化")
        print("=" * 50)
        
        print("\n请手动输入游戏区域坐标")
        print("提示：可以先运行 game_icon_matcher.py 来可视化选择区域并记录坐标")
        print("或者使用截图工具（如QQ截图）查看坐标")
        
        try:
            x1 = int(input("请输入左上角 X 坐标: "))
            y1 = int(input("请输入左上角 Y 坐标: "))
            x2 = int(input("请输入右下角 X 坐标: "))
            y2 = int(input("请输入右下角 Y 坐标: "))
            
            self.game_region = (x1, y1, x2, y2)
            print(f"\n游戏区域: ({x1}, {y1}) 到 ({x2}, {y2})")
            print(f"区域尺寸: {x2-x1} x {y2-y1}")
            
        except ValueError:
            print("输入错误，初始化失败")
            return False
        
        # 首次识别（保存调试信息）
        return self.update_game_state(save_debug=True)
    
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
            cv2.imwrite('debug_screenshot.png', screenshot)
            print("调试截图已保存到 debug_screenshot.png")
        
        # 识别图标 - 降低阈值以识别更多图标
        results = self.matcher.match_icons(screenshot, threshold=0.70, use_multiscale=True)
        print(f"识别到 {len(results)} 个图标")
        
        # 如果识别数量明显不足，尝试更低的阈值
        if len(results) < 100:
            print(f"警告：识别数量偏少 ({len(results)}), 尝试降低阈值重新识别...")
            results = self.matcher.match_icons(screenshot, threshold=0.65, use_multiscale=True)
            print(f"重新识别到 {len(results)} 个图标")
        
        # 保存标注结果用于调试
        if save_debug:
            debug_output = self.matcher.draw_results(screenshot, results)
            cv2.imwrite('debug_matched.png', debug_output)
            print("标注结果已保存到 debug_matched.png")
        
        # 构建网格
        region_offset = (x1, y1)
        success = self.grid.build_from_results(results, region_offset)
        
        if success:
            self.grid.print_grid()
        
        return success
    
    def find_adjacent_pairs(self):
        """查找所有相邻的相同图标对"""
        pairs = []
        
        for row in range(self.grid.rows):
            for col in range(self.grid.cols):
                cell = self.grid.get_cell(row, col)
                if cell['is_empty']:
                    continue
                
                cell_type = cell['type']
                
                # 检查右边
                if col + 1 < self.grid.cols:
                    right_cell = self.grid.get_cell(row, col + 1)
                    if not right_cell['is_empty'] and right_cell['type'] == cell_type:
                        pairs.append({
                            'type': cell_type,
                            'pos1': (row, col),
                            'pos2': (row, col + 1),
                            'direction': 'horizontal'
                        })
                
                # 检查下边
                if row + 1 < self.grid.rows:
                    bottom_cell = self.grid.get_cell(row + 1, col)
                    if not bottom_cell['is_empty'] and bottom_cell['type'] == cell_type:
                        pairs.append({
                            'type': cell_type,
                            'pos1': (row, col),
                            'pos2': (row + 1, col),
                            'direction': 'vertical'
                        })
        
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
    
    def find_one_move_pairs(self):
        """查找只需一步移动就能配对的图标"""
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
                    
                    # 检查是否在同一行
                    if pos1[0] == pos2[0]:
                        row = pos1[0]
                        col1, col2 = sorted([pos1[1], pos2[1]])
                        
                        # 检查是否相邻或中间只有空格
                        if col2 - col1 == 1:
                            continue  # 已经相邻，不需要移动
                        
                        # 检查能否通过行滑动让它们相邻
                        can_slide = self._can_slide_row(row, col1, col2)
                        if can_slide:
                            # 计算优先级（距离越近越好）
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
                                'priority': distance  # 距离越小优先级越高
                            })
                    
                    # 检查是否在同一列
                    elif pos1[1] == pos2[1]:
                        col = pos1[1]
                        row1, row2 = sorted([pos1[0], pos2[0]])
                        
                        if row2 - row1 == 1:
                            continue  # 已经相邻
                        
                        # 检查能否通过列滑动让它们相邻
                        can_slide = self._can_slide_col(col, row1, row2)
                        if can_slide:
                            # 计算优先级
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
                                'priority': distance
                            })
        
        # 按优先级排序（距离小的优先）
        opportunities.sort(key=lambda x: x['priority'])
        
        return opportunities
    
    def _can_slide_row(self, row, col1, col2):
        """检查是否可以滑动行使两个格子相邻"""
        # 检查col1和col2之间是否都是空格（可以滑动）
        # 或者是否有连续的砖块可以一起滑动
        
        # 情况1：中间都是空格，可以直接滑动
        all_empty = True
        for col in range(col1 + 1, col2):
            cell = self.grid.get_cell(row, col)
            if not cell['is_empty']:
                all_empty = False
                break
        
        if all_empty:
            return True
        
        # 情况2：检查是否有连续的砖块可以一起滑动
        # 暂时返回False，需要更复杂的逻辑
        return False
    
    def _can_slide_col(self, col, row1, row2):
        """检查是否可以滑动列使两个格子相邻"""
        # 检查row1和row2之间是否都是空格（可以滑动）
        
        # 情况1：中间都是空格，可以直接滑动
        all_empty = True
        for row in range(row1 + 1, row2):
            cell = self.grid.get_cell(row, col)
            if not cell['is_empty']:
                all_empty = False
                break
        
        if all_empty:
            return True
        
        # 情况2：检查是否有连续的砖块可以一起滑动
        # 暂时返回False，需要更复杂的逻辑
        return False
    
    def execute_slide(self, opportunity):
        """执行滑动操作"""
        print(f"\n执行滑动: {opportunity['type']}")
        
        if opportunity['move_type'] == 'row_slide':
            row = opportunity['row']
            from_col = opportunity['from_col']
            to_col = opportunity['to_col']
            
            # 获取两个格子
            from_cell = self.grid.get_cell(row, from_col)
            to_cell = self.grid.get_cell(row, to_col)
            
            # 计算需要移动的实际距离
            # 目标：让from_col的砖块移动到to_col旁边（相邻）
            
            # 检查中间有多少个空格
            empty_count = 0
            for col in range(from_col + 1, to_col):
                cell = self.grid.get_cell(row, col)
                if cell['is_empty']:
                    empty_count += 1
            
            # 实际需要移动的格子数 = 总距离 - 空格数 - 1（保持相邻）
            move_cells = to_col - from_col - empty_count - 1
            
            if move_cells <= 0:
                print(f"警告：计算的移动距离为 {move_cells}，跳过此操作")
                return
            
            # 计算像素距离
            distance = move_cells * self.grid.cell_width
            
            start_x = from_cell['abs_center_x']
            start_y = from_cell['abs_center_y']
            
            print(f"行滑动: 从 ({start_x}, {start_y}) 向右滑动 {move_cells} 格 ({distance} 像素)")
            
            pyautogui.moveTo(start_x, start_y)
            time.sleep(0.2)
            pyautogui.drag(distance, 0, duration=0.5)
            time.sleep(0.5)
            
        elif opportunity['move_type'] == 'col_slide':
            col = opportunity['col']
            from_row = opportunity['from_row']
            to_row = opportunity['to_row']
            
            from_cell = self.grid.get_cell(from_row, col)
            to_cell = self.grid.get_cell(to_row, col)
            
            # 计算需要移动的实际距离
            # 检查中间有多少个空格
            empty_count = 0
            for row in range(from_row + 1, to_row):
                cell = self.grid.get_cell(row, col)
                if cell['is_empty']:
                    empty_count += 1
            
            # 实际需要移动的格子数
            move_cells = to_row - from_row - empty_count - 1
            
            if move_cells <= 0:
                print(f"警告：计算的移动距离为 {move_cells}，跳过此操作")
                return
            
            # 计算像素距离
            distance = move_cells * self.grid.cell_height
            
            start_x = from_cell['abs_center_x']
            start_y = from_cell['abs_center_y']
            
            print(f"列滑动: 从 ({start_x}, {start_y}) 向下滑动 {move_cells} 格 ({distance} 像素)")
            
            pyautogui.moveTo(start_x, start_y)
            time.sleep(0.2)
            pyautogui.drag(0, distance, duration=0.5)
            time.sleep(0.5)
        
        self.move_count += 1
    
    def play_one_round(self):
        """执行一轮游戏"""
        # 1. 查找直接相邻的配对
        adjacent_pairs = self.find_adjacent_pairs()
        
        if adjacent_pairs:
            print(f"\n找到 {len(adjacent_pairs)} 个相邻配对")
            # 消除第一个配对
            self.eliminate_pair(adjacent_pairs[0])
            return True
        
        print("\n没有找到相邻配对，寻找需要移动的机会...")
        
        # 2. 查找一步移动的机会
        opportunities = self.find_one_move_pairs()
        
        if opportunities:
            print(f"找到 {len(opportunities)} 个一步移动机会（已过滤不可行的）")
            
            # 显示前3个机会
            for i, opp in enumerate(opportunities[:3]):
                print(f"  机会{i+1}: {opp['type']} at {opp['pos1']} 和 {opp['pos2']}, "
                      f"距离: {opp['distance']}, 类型: {opp['move_type']}")
            
            # 执行第一个机会
            self.execute_slide(opportunities[0])
            return True
        
        print("\n没有找到可行的移动")
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
    
    # 询问是否开始自动游戏
    print("\n准备开始自动游戏")
    print("注意：鼠标将被自动控制")
    print("如需紧急停止，将鼠标移到屏幕左上角")
    input("按回车键开始...")
    
    # 开始自动游戏
    player.auto_play()


if __name__ == '__main__':
    main()
