import logging.handlers
import logging
import os
import logging.handlers
from typing import Any
import uuid
from tornado import httputil
from tornado.web import RequestHandler, Application, HTTPError

# ==== 日志记录 ====
# 获取项目根目录路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")

# 确保日志目录存在
os.makedirs(LOG_DIR, exist_ok=True)

# 日志工具类
class LoggingHandler:
    # 使用类变量存储已创建的logger实例，避免重复创建
    _loggers = {}

    def __init__(self, api_name):
        self.api_name = api_name

    def get_logger(self):
        # 如果已经为该API创建过logger，直接返回
        if self.api_name in LoggingHandler._loggers:
            return LoggingHandler._loggers[self.api_name]

        # 创建新的logger
        logger = logging.getLogger(self.api_name)
        logger.setLevel(logging.INFO)

        # 日志文件路径（按日期滚动）
        log_file = os.path.join(LOG_DIR, f"{self.api_name}.log")

        # 创建文件处理器 - 使用RotatingFileHandler自动滚动
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=15 * 1024 * 1024,  # 15MB
            backupCount=5  # 保留5个历史文件
        )

        # 创建日志格式
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)

        # 添加处理器到记录器
        logger.addHandler(file_handler)

        # 缓存logger实例
        LoggingHandler._loggers[self.api_name] = logger

        return logger


# 构建标准的日志记录流程
class BaseHandler(RequestHandler):
    def __init__(self, application, request, **kwargs):
        super().__init__(application, request, **kwargs)
        self.api_name = None
        self.request_id = f"{str(uuid.uuid4())[:8]}"
        self.logger = None

    def initialize(self, api_name=None):
        """Tornado 在创建 Handler 实例后自动调用"""
        if not api_name:
            api_name = self.__class__.__name__
        self.api_name = api_name
        # 始终通过 LoggingHandler 获取 logger（会做缓存）
        self.logger = LoggingHandler(self.api_name).get_logger()
        # 每个请求重新生成 request_id 更好追踪
        self.request_id = f"{str(uuid.uuid4())[:8]}"

    def _ensure_logger(self):
        """保证 logger 总是存在，防止未初始化报错（兜底）"""
        if not getattr(self, "logger", None):
            self.api_name = self.api_name or self.__class__.__name__
            try:
                self.logger = LoggingHandler(self.api_name).get_logger()
            except Exception:
                # 最后兜底创建一个简单的 stdout logger，避免 None
                fallback = logging.getLogger("fallback")
                if not fallback.handlers:
                    ch = logging.StreamHandler()
                    ch.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
                    fallback.addHandler(ch)
                self.logger = fallback

    def prepare(self):
        """请求准备阶段，记录请求开始"""
        # 使用 _ensure_logger 保证安全
        self._ensure_logger()
        # 现在安全调用日志
        try:
            self.log_request_start()
        except Exception:
            # 若日志记录本身异常，不要抛出，避免导致 500
            self._ensure_logger()
            self.logger.exception("Failed in log_request_start")

    def log_request_start(self):
        """记录请求开始信息"""
        # 再次确保 logger
        self._ensure_logger()

        # 保证 request_id 存在
        if not getattr(self, "request_id", None):
            self.request_id = f"{str(uuid.uuid4())[:8]}"

        # 记录信息（try/except 防止日志导致业务失败）
        try:
            self.logger.info(
                f"[{self.request_id}] Request Start: "
                f"{self.request.remote_ip}, "
                f"{self.request.method} {self.request.uri}"
            )
        except Exception as e:
            # 如果 logger 出问题，用 fallback 打印并继续
            print("log_request_start logger error:", e)

        # 记录请求体（如果是POST且有内容）
        if self.request.method.upper() == "POST" and getattr(self.request, "body", None):
            try:
                body_str = self.request.body.decode("utf-8", errors="ignore")
                if len(body_str) > 200:
                    body_str = body_str[:200] + " [TRUNCATED]"
                self.logger.info(f"[{self.request_id}] Request Body: {body_str}")
            except Exception as e:
                self.logger.warning(f"[{self.request_id}] Failed to decode request body: {str(e)}")

    def log_message(self, message, level=logging.INFO):
        """记录自定义消息"""
        self._ensure_logger()
        try:
            self.logger.log(level, f"[{self.request_id}] {message}")
        except Exception as e:
            # 防御：避免日志调用抛异常影响业务
            print("log_message error:", e)

    def log_exception(self, typ, value, tb):
        """统一异常日志（覆盖 tornado 默认行为）"""
        # 兜底确保 logger
        self._ensure_logger()

        if isinstance(value, HTTPError):
            message = f"HTTP {value.status_code}: {value.reason}"
        else:
            message = f"Unhandled exception: {value}"

        try:
            self.logger.error(f"[{self.request_id}] {message}", exc_info=(typ, value, tb))
        except Exception as e:
            # fallback print
            print("log_exception error:", e)

