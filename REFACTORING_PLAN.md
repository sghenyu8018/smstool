# 代码重构计划：utils/sms_success_rate_query.py

## 当前问题分析

### 1. 文件结构问题
- **文件长度**：1590行，只有3个函数
- **函数长度**：`query_sms_success_rate` 函数有950行，严重违反单一职责原则
- **代码重复**：多个功能模块在两个函数中重复实现

### 2. 重复代码统计
- **数据提取逻辑**：约200行代码在两个函数中完全重复（337-544行 vs 1296-1491行）
- **滚动页面逻辑**：约30行代码重复（156-182行 vs 1062-1088行）
- **等待数据加载**：约100行代码重复（223-330行 vs 1198-1288行）
- **时间范围选择**：约120行代码重复（64-202行 vs 984-1094行）
- **查找SLS iframe**：多处重复

## 重构方案

### 方案1：提取辅助函数（推荐）
将重复的逻辑提取为独立的辅助函数，保持文件结构不变。

#### 建议提取的函数：

1. **`_find_sls_iframe(page: Page) -> Optional[Frame]`**
   - 功能：查找并返回SLS iframe
   - 位置：多处使用
   - 代码量：约15行

2. **`_wait_for_iframe_load(sls_frame: Frame, timeout: int = 15000) -> bool`**
   - 功能：等待iframe加载完成
   - 位置：query_sms_success_rate中使用
   - 代码量：约50行

3. **`_find_pid_input(sls_frame: Frame) -> Optional[Locator]`**
   - 功能：查找PID输入框（包含多种尝试方式）
   - 位置：query_sms_success_rate中使用
   - 代码量：约140行
   - **这是最复杂的函数，包含多种查找策略**

4. **`_fill_pid(pid_input_locator: Locator, pid: str) -> bool`**
   - 功能：填写PID到输入框
   - 位置：query_sms_success_rate中使用
   - 代码量：约50行

5. **`_select_time_range(sls_frame: Frame, time_range: str) -> bool`**
   - 功能：选择时间范围
   - 位置：两个函数中都使用
   - 代码量：约120行

6. **`_scroll_to_bottom(sls_frame: Frame) -> None`**
   - 功能：滚动页面到底部
   - 位置：两个函数中都使用
   - 代码量：约30行

7. **`_wait_for_table_ready(sls_frame: Frame, page: Page, pid: Optional[str], max_retries: int = 30) -> Tuple[bool, Optional[Locator]]`**
   - 功能：等待表格数据加载完成
   - 位置：两个函数中都使用
   - 代码量：约100行
   - 返回：是否就绪，表格容器定位器

8. **`_extract_table_data(sls_frame: Frame, pid: Optional[str]) -> Dict[str, any]`**
   - 功能：从表格中提取数据
   - 位置：两个函数中都使用
   - 代码量：约200行
   - 返回：包含all_data, matched_data, success_rate的字典

### 方案2：拆分为多个文件（可选）
如果文件继续增长，可以考虑拆分为多个文件：

```
utils/
  ├── sms_success_rate_query.py      # 主入口函数
  ├── sms_success_rate_helpers.py    # 辅助函数
  │   ├── iframe_helpers.py          # iframe相关
  │   ├── input_helpers.py            # 输入框相关
  │   ├── table_helpers.py           # 表格相关
  │   └── scroll_helpers.py           # 滚动相关
```

## 重构后的代码结构

### 重构后的 `query_sms_success_rate` 函数（约200行）
```python
async def query_sms_success_rate(...):
    # 1. 导航到页面
    # 2. 点击菜单
    # 3. 查找SLS iframe
    sls_frame = await _find_sls_iframe(page)
    # 4. 等待iframe加载
    await _wait_for_iframe_load(sls_frame)
    # 5. 查找并填写PID
    pid_input = await _find_pid_input(sls_frame)
    await _fill_pid(pid_input, pid)
    # 6. 选择时间范围
    await _select_time_range(sls_frame, time_range)
    # 7. 滚动页面
    await _scroll_to_bottom(sls_frame)
    # 8. 等待表格加载
    table_ready, table_container = await _wait_for_table_ready(sls_frame, page, pid)
    # 9. 提取数据
    result = await _extract_table_data(sls_frame, pid)
    return result
```

### 重构后的 `_select_time_range_only` 函数（约100行）
```python
async def _select_time_range_only(...):
    # 1. 查找SLS iframe
    sls_frame = await _find_sls_iframe(page)
    # 2. 选择时间范围
    await _select_time_range(sls_frame, time_range)
    # 3. 重新获取iframe（切换后可能重新加载）
    sls_frame = await _find_sls_iframe(page)
    await _wait_for_iframe_load(sls_frame)
    # 4. 滚动页面
    await _scroll_to_bottom(sls_frame)
    # 5. 等待表格加载
    table_ready, table_container = await _wait_for_table_ready(sls_frame, page, pid)
    # 6. 提取数据
    result = await _extract_table_data(sls_frame, pid)
    return result
```

## 重构收益

1. **代码可读性**：主函数逻辑清晰，每个步骤一目了然
2. **代码复用**：消除重复代码，减少维护成本
3. **易于测试**：每个辅助函数可以独立测试
4. **易于维护**：修改某个功能只需要修改对应的辅助函数
5. **代码量减少**：预计可以减少约300-400行重复代码

## 实施建议

1. **第一阶段**：提取数据提取函数（`_extract_table_data`），这是最大的重复代码块
2. **第二阶段**：提取等待表格加载函数（`_wait_for_table_ready`）
3. **第三阶段**：提取时间范围选择函数（`_select_time_range`）
4. **第四阶段**：提取其他辅助函数
5. **测试**：每个阶段完成后进行充分测试

## 注意事项

1. **保持向后兼容**：重构后函数接口不变
2. **充分测试**：每个提取的函数都需要单独测试
3. **逐步重构**：不要一次性重构所有代码，分阶段进行
4. **保留注释**：提取函数时保留原有的注释和文档
