# 更新说明

## 主要修改内容

### 1. 添加上下文感知的PDF处理机制

**问题背景：**
之前系统存在一个关键问题：当VLLM需要处理本地下载的PDF文件时（如提取文本、图片），它仍然会基于网页截图和DOM信息进行决策，导致无法正确理解当前上下文已从"网页浏览"切换到"本地文件处理"。

**解决方案：**
- 在 `Agent` 类中新增上下文模式跟踪机制，区分两种工作模式：
  - `web_browsing`：正常的网页浏览模式，基于截图和DOM进行操作
  - `local_file_processing`：本地文件处理模式，处理已下载的PDF文件
- 当PDF下载成功后，系统自动切换到 `local_file_processing` 模式
- 在history中添加明确的上下文切换通知，告知VLLM：
  - PDF已成功下载到本地
  - 应使用本地文件处理工具（`pdf_extract_text`、`pdf_extract_images`、`ocr_image_to_text`）
  - 这些工具不依赖浏览器操作
  - 处理本地文件时应忽略截图/DOM信息

### 2. 改进OCR图片路径处理

**问题：**
VLLM调用OCR工具时只提供了文件名（如 `"page_4_img_1.png"`），但图片实际保存在子目录中（如 `extracted_images/page_4_img_1.png`），导致找不到文件。

**解决方案：**
- 修改 `pdf_extract_images` 函数，返回相对路径（相对于 `artifacts/` 目录）而不是绝对路径
- 在返回信息中明确提示VLLM使用这些相对路径进行OCR
- 增强 `ocr_image_to_text` 函数，如果直接路径找不到文件，会在常见子目录中自动搜索：
  - `extracted_images/`
  - `images/`
  - `output_images/`
- 更新system prompt，明确说明使用OCR工具时需要提供完整的相对路径

### 3. 改进PDF图片提取的错误提示

**问题：**
当VLLM只提取第1页的图片时，如果第1页没有图片，会返回简单的"未找到图片"错误，导致VLLM误以为整个PDF都没有图片而放弃任务。

**解决方案：**
- 改进 `pdf_extract_images` 的错误提示，当指定页面没有图片时：
  - 告知PDF总页数
  - 建议尝试其他页面（如 `page_num=2, page_num=3`）
  - 建议省略 `page_num` 参数以提取所有页面的图片
- 更新system prompt，明确说明第一张图片可能不在第1页，建议在找不到图片时尝试提取所有页面

### 4. 移除自动处理逻辑

**修改：**
- 移除了之前实现的自动处理逻辑（`_auto_process_pdf` 方法）
- 让VLLM根据上下文提示自主决定何时调用处理工具
- 保持VLLM的自主决策能力，不强制自动执行

## 技术细节

### 修改的文件

1. **`vision_llm_web_agent/agent_controller.py`**
   - 添加 `context_mode` 和 `downloaded_pdf_files` 属性
   - 修改 `execute_tool` 方法，在PDF下载成功后切换上下文模式
   - 在history中添加上下文切换通知
   - 修改 `execute_round` 方法，根据上下文模式调整状态信息

2. **`vision_llm_web_agent/vllm_client.py`**
   - 添加 `summarize_text` 方法（用于生成文本总结）
   - 更新system prompt，明确说明两种上下文模式的区别
   - 在 `plan_next_action` 中根据上下文模式决定是否提供截图

3. **`vision_llm_web_agent/tools/file_operations.py`**
   - 改进 `pdf_extract_images` 函数，返回相对路径和更详细的错误提示
   - 增强 `ocr_image_to_text` 函数，支持智能路径搜索
   - 添加PDF总页数信息到返回结果中

## 使用效果

修改后，系统能够：
- ✅ 正确识别上下文切换，VLLM知道何时使用本地文件处理工具
- ✅ 正确处理OCR图片路径，自动在常见目录中搜索
- ✅ 提供更好的错误提示，引导VLLM尝试其他页面或提取所有页面
- ✅ 保持VLLM的自主决策能力，不强制自动执行

## 工作流程示例

1. **网页浏览模式**：VLLM基于截图和DOM进行网页操作
2. **PDF下载成功**：
   - 自动切换到 `local_file_processing` 模式
   - 在history中添加明确的上下文提示
   - 下一轮不再提供截图，DOM标记为不相关
3. **本地文件处理模式**：VLLM知道应该使用 `pdf_extract_text`、`pdf_extract_images` 等工具处理本地文件
4. **图片提取**：如果指定页面没有图片，VLLM会收到提示，知道应该尝试其他页面或提取所有页面
5. **OCR处理**：VLLM使用完整的相对路径调用OCR工具，或OCR工具自动在常见目录中搜索

