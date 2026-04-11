# Tooling

当前系统内置多种工具：

- `read_file`：读取文件内容
- `file_search`：搜索关键字
- `write_file`：创建或覆盖文件
- `replace_in_file`：替换文件内容
- `append_file`：追加文件内容
- `multi_file_patch`：一次调用中批量修改多个文件
- `shell_run`：执行命令并返回结构化结果
- `retrieve_docs`：从文档知识库检索相关片段

如果要根据文档生成简单代码，推荐流程是：

1. 调用 `retrieve_docs` 获取相关规范
2. 调用 `write_file` 生成文件
3. 调用 `shell_run` 执行校验命令

如果一次任务需要同时修改多个文件，优先考虑使用 `multi_file_patch`，这样可以在一次工具调用中查看全部 diff 预览并统一落盘。
