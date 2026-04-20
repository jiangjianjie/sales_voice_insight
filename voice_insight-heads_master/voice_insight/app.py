import logging
from multiprocessing import Process
import tornado.httpserver
import tornado.ioloop
import tornado.netutil
import tornado.process
import tornado.web
from handlers.asr import MultimodalInferAsrTextHandler

def make_app():
    return tornado.web.Application([
        (r"/api/v1/multimodal/infer/asr", MultimodalInferAsrTextHandler,
         dict(api_name="MultimodalInferAsrTextHandler")),
    ],
    )

def start_server():
    logging.info("服务已启动")

    server = tornado.httpserver.HTTPServer(make_app())
    server.bind(8898)
    server.start(1)  # 在多进程模式下，start(0)会自动根据CPU核心数量启动相应数量的子进程
    tornado.ioloop.IOLoop.current().start()


if __name__ == "__main__":
    num_processes = 1  # 指定启动的子进程数量
    processes = []
    for _ in range(num_processes):
        process = Process(target=start_server)
        process.start()
        processes.append(process)

    for process in processes:
        process.join()
