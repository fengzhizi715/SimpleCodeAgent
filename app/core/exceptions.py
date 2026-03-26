"""应用自定义异常。"""


class AppError(Exception):
    """应用层异常基类。"""


class RuntimeTimeoutError(AppError):
    """运行时超时异常。"""


class RuntimeMaxStepsError(AppError):
    """运行时达到最大步数异常。"""


class LLMResponseFormatError(AppError):
    """模型响应格式异常。"""


class UnsupportedAgentVersionError(AppError):
    """未支持的 Agent 版本异常。"""
