# coding: utf-8
"""
CapsWriter Offline 服务端主程序门面类 (Facade)

采用外观模式统一管理进程管理器 (ProcessManager) 和网络管理器 (SocketManager)。
该类负责初始化生命周期，并协调子进程与 WebSocket 服务的启动与退出。
"""

import os
import sys
import signal
import asyncio
from pathlib import Path
from config_server import ServerConfig as Config, __version__, resolve_http_settings
from .state import ServerState, console
from .worker.process_manager import ProcessManager
from .connection.server_manager import SocketManager
from .http_server import HttpServer
from .http_file_runner import HttpFileRunner
from . import logger

class CapsWriterServer:
    """
    CapsWriter 服务端外观类
    
    管理的外部接口极其简洁：start()。
    """
    def __init__(self):
        # 确保正确的工作目录
        self.base_dir = Path(__file__).parents[2]
        os.chdir(self.base_dir)

        # 初始化事件循环
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        # 初始化状态容器
        self.state = ServerState(app=self)

        # 基本配置与组件实例化
        self.process_manager = ProcessManager(self)
        self.socket_manager = SocketManager(self)
        # HTTP 文件任务默认关闭；仅在显式提供 CW_HTTP_PORT + CW_HTTP_DATA_DIR 时装配
        self.http_server = None
        self.http_file_runner = None
        self.exit_code = 0

        self.version = __version__
        self.is_alive = False


    def _print_banner(self):
        """打印启动信息"""
        console.line(2)
        console.rule('[bold #d55252]CapsWriter Offline Server[/]'); console.line()
        console.print(f'版本：[bold green]{self.version}[/]', end='\n\n')
        console.print(f'项目地址：[cyan underline]https://github.com/HaujetZhao/CapsWriter-Offline', end='\n\n')
        console.print(f'当前基文件夹：[cyan underline]{self.base_dir}[/]', end='\n\n')
        console.print(f'绑定的服务地址：[cyan underline]{Config.addr}:{Config.port}[/]', end='\n\n')

    def stop(self):
        """
        清理服务端资源
        """
        # 防连续触发
        if not self.is_alive: return
        self.is_alive = False 

        logger.info("=" * 50)
        logger.info("开始清理服务端资源...")

        self.state.queue_out.put(None)

        # 1. 关闭 WebSocket 服务（立即释放端口）
        self.socket_manager.stop()

        # 2. 终止识别子进程
        self.process_manager.stop()

        # 3. 收尾 HTTP 文件任务（等在途 I/O 结束后再停 loop）
        if self.http_server is not None:
            future = asyncio.ensure_future(self.http_server.stop())

            def finish_http_shutdown(done):
                error = done.exception()
                if error is not None:
                    self.exit_code = 1
                    logger.error("HTTP 收尾失败：%s", error)
                self.loop.stop()

            future.add_done_callback(finish_http_shutdown)
        else:
            self.loop.stop()

        logger.info("服务端资源清理完成")
        console.print('[green4]再见！')


    def _register_exit_signals(self):
        """
        注册退出信号处理（服务端专用）

        无头守护（pm2 / systemd / Windows 计划任务）下没有「第二次按键」的
        交互机会，SIGINT / SIGTERM 任一收到一次即触发 stop() 清理（停子进程、
        关 loop），让进程以退出码 0 结束。Windows 无法投递 SIGTERM，仅注册
        SIGINT（hasattr + 平台判断，不写 try-except 吞错）。
        """
        def _stop_on_signal(signum):
            logger.info(f"收到 {signal.Signals(signum).name}，开始清理退出")
            self.stop()

        if sys.platform == 'win32':
            def _schedule_stop_on_signal(signum, _frame):
                self.loop.call_soon_threadsafe(_stop_on_signal, signum)

            signal.signal(signal.SIGINT, _schedule_stop_on_signal)
        else:
            # 由 asyncio 自管道唤醒 selector，避免 PEP 475 自动重试 select 时挂住。
            self.loop.add_signal_handler(signal.SIGINT, _stop_on_signal, signal.SIGINT)
            if hasattr(signal, 'SIGTERM'):
                self.loop.add_signal_handler(signal.SIGTERM, _stop_on_signal, signal.SIGTERM)

    def start(self):
        """
        同步启动服务端 (主入口)

        注册信号处理、拉起子进程并进入网络服务监听循环。

        正常 SIGINT/SIGTERM 走 stop() 收尾并以 0 退出；启动期装配失败与运行期
        的任何 fatal 都先按同一顺序回收资源，再以非零退出——不能出现「端口已关、
        识别子进程还在」而进程本身不退出（监督看不到退出，也就不会重启）。
        """
        # 防连续触发
        if self.is_alive: return
        self.is_alive = True

        # 注册退出信号处理
        self._register_exit_signals()

        self._print_banner()

        try:
            # 拉起识别子进程
            self.process_manager.start()

            # 装配 HTTP listener：显式启用后任何初始化错误都 fail fast 非零退出，不退回 disabled
            http_settings = resolve_http_settings()
            if http_settings is not None:
                self.http_server = HttpServer(self, *http_settings).prepare()
                # 装配真实文件 runner：ffmpeg 不可用时同样 fail fast，不假受理
                self.http_file_runner = HttpFileRunner(self.state, self.http_server)
                self.http_server.attach_runner(self.http_file_runner)
                self.state.http_result_sink = self.http_file_runner.result_sink

            # 开启网络服务监听 (接管当前线程直至退出)
            self.loop.run_until_complete(self._serve_all())
        except RuntimeError:
            # 正常信号会先将 is_alive 置 False，再由收尾回调 stop loop；
            # 这条路径的收尾已经由 stop() 发起，不再重复。
            if self.is_alive:
                # 运行中的 listener RuntimeError 必须继续失败，不能按正常退出处理；
                # 但同样要先回收资源（见下面 except 分支的说明）。
                self.exit_code = self.exit_code or 1
                self._drain_after_fatal()
                raise
        except BaseException as fatal:
            # 启动期的装配失败与运行期的监督 fatal 同一条 root：异常本身只把
            # 监听关掉，识别子进程、共享 Manager、ffmpeg 解码进程与 I/O 线程
            # 只在 stop() 里回收。不回收就是“端口已关、子进程还活着”的假存活，
            # systemd 看到进程还在就不会重启，真实的不可用被报成存活。
            #
            # 回收完再原样重抛：traceback 仍由解释器打到 stderr（既有诊断口径），
            # 进程以非零状态真正退出，监督才能看到并重启。
            self.exit_code = self.exit_code or 1
            logger.error("服务端启动/运行失败，按非零退出收尾：%r", fatal)
            self._drain_after_fatal()
            raise
        if self.exit_code:
            raise SystemExit(self.exit_code)

    def _drain_after_fatal(self) -> None:
        """fatal 之后把既有 stop() 真正跑完，并观察它的异步收尾。

        复用 stop()（不再造第二套回收顺序）：它把 HTTP 收尾挂在 loop 的 done
        callback 上，只有回到事件循环里跑到那个 callback 才算“等到了”，否则
        等于只发起了收尾。异常在 finish_http_shutdown 里被读到并转成 exit_code，
        在途 I/O 也不会被 loop.stop 取消。

        HTTP 未启用时 stop() 同步停 loop，没有 future 可等，直接返回。
        """
        self.stop()
        if self.http_server is not None:
            self.loop.run_forever()

    async def _serve_all(self):
        """WS 与 HTTP 两条监听并行；任一真实失败让进程以非零退出。"""
        ws_task = asyncio.ensure_future(self.socket_manager.start())
        tasks = {ws_task}
        http_task = None
        if self.http_server is not None:
            http_task = asyncio.ensure_future(self.http_server.serve())
            tasks.add(http_task)
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        error = None
        for task in done:
            if task.cancelled():
                continue
            exc = task.exception()
            if exc is not None and error is None:
                error = exc
        if error is not None:
            self.exit_code = 1
        for task in pending:
            task.cancel()
        if pending:
            outcomes = await asyncio.gather(*pending, return_exceptions=True)
            for outcome in outcomes:
                if isinstance(outcome, BaseException) and not isinstance(outcome, asyncio.CancelledError):
                    if error is None:
                        error = outcome
                    self.exit_code = 1
        if error is not None:
            raise error
