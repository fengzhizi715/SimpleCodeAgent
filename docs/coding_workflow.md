# 编程工作流

当任务属于“小范围编程任务”时，推荐流程是：

1. 用 `file_search` 定位相关实现
2. 用 `read_file` 阅读关键文件
3. 用 `retrieve_docs` 获取项目约定或开发文档
4. 用 `write_file` / `replace_in_file` / `append_file` 进行最小改动
5. 用 `shell_run` 执行 `pytest`、`python -m py_compile` 或 `python -m ...` 做验证

适用任务：

- 新建工具类
- 新增简单 CRUD 方法
- 仿照已有模块生成相似模块
- 小范围代码修复
- 执行测试并分析失败原因

不建议的行为：

- 未阅读现有代码就直接大改
- 一次性跨多个模块做大规模重构
- 修改后不做验证
- 遇到工具错误后重复相同调用
