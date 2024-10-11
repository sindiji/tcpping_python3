#!/usr/bin/env python3
# encoding: utf-8
# Author: huigher@126.com
# Modified for Python 3 compatibility

import argparse
import time
import socket
import struct
import logging
import logging.handlers
import signal
import random
from datetime import datetime

__VERSION__ = '0.3.2'

def current_time():
    """Return current time as formatted string."""
    t = datetime.fromtimestamp(time.time())
    return t.strftime('%Y%m%d-%H:%M:%S')

def conn_tcp(dst_host, dst_port, timeout, src_host=None, src_port=None, rst=False, reuse=False, delay_close_second=0):
    """
    Open a TCP connection to host:port
    Return conn time, close time and error (if exist)
    :param dst_host: remote host
    :param dst_port: remote port
    :param src_host: local host
    :param src_port: local port
    :param rst: if set, use RESET to close connection
    :param timeout: wait TIMEOUT second in connection period
    :param reuse: if set, allow reuse of local address
    :param delay_close_second: delay before closing the connection
    :return: (conn_time, close_time, err, local_addr), connection time, close time, error message, and local address
    """
    t1, t2, t3, te, conn_time, close_time, err, local_addr = -1, -1, -1, -1, -1, -1, '', None
    
    # 若指定了RST参数，那么开始设定相关参数
    if rst:
        l_onoff, l_linger = 1, 0
    
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # 开始设定发送RST需要的参数
        if rst:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER,
                         struct.pack('ii', l_onoff, l_linger))
        # 如果设置了reuse参数，允许地址和端口重用
        # 这对于快速重复测试特别有用，可以避免 "Address already in use" 错误
        if reuse:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if src_host and src_port and src_port < 65536:
            s.bind((src_host, int(src_port)))
        
        t1 = time.time()
        s.settimeout(timeout)
        s.connect((dst_host, int(dst_port)))
        local_addr = s.getsockname()
        t2 = time.time()
        # 延迟指定的秒数关闭
        time.sleep(delay_close_second)
        s.close()
        t3 = time.time()
    except Exception as e:
        local_addr = s.getsockname()
        err = e
        te = time.time()
    finally:
        try:
            # finally块中就不延迟关闭了
            s.close()
        except Exception as e2:
            print(e2)

    # 计算连接时间和关闭时间
    if t2 >= 0:
        conn_time = t2 - t1
    if t3 >= 0:
        close_time = t3 - t2
    if te >= 0:
        if t2 >= 0:
            conn_time = t2 - t1
            close_time = t3 - t2
        else:
            conn_time = te - t1
    return (conn_time, close_time, err, local_addr)

def judge_count(count):
    """
    判断是否继续执行
    :param count: 剩余执行次数
    :return: 是否继续执行
    """
    return count > 0 if count is not None else True

def judge_args(argument):
    """
    判断一下传入的参数是否合法，对于只给定源地址的情况，自动补充一个源端口
    :param argument: 通过agrparse解析参数得到的对象
    :return: 参数是否合法
    """
    if bool(argument.src_host) ^ (bool(argument.src_port) or bool(argument.src_rotate_port)):
        # 随机出一个源端口，注意这里没有校验，可能会失败（比如源端口已经被占用）
        argument.src_port = random.randint(10000, 60000)
        tip = f'Missing src_port or src_rotate_port. A random local port will be given: {argument.src_port}'
        mylogger.warning(tip)
    return True

def give_tips(argument):
    """
    提供一些友好的提示信息
    :param argument: 解析得到的参数
    """
    # 如果指定的本地源端口，但是发现没有用-R参数，给出提示告知可能碰到TIME_WAIT问题
    if bool(argument.src_port) and not bool(argument.rst):
        tip = 'It is RECOMMENDED that -R flag should be set if a static local port is set. ' \
              'Or you may see an error message like "Address already in use".'
        mylogger.warning(tip)

def go(dst_host, dst_port, timeout, interval, src_host=None, src_port=None, src_rotate_port=None, rst=False,
       reuse=False, count=None, delay_close_second=0):
    """
    主要的执行函数，进行TCP连接测试
    :param dst_host: 目标主机
    :param dst_port: 目标端口
    :param timeout: 超时时间
    :param interval: 间隔时间
    :param src_host: 源主机
    :param src_port: 源端口
    :param src_rotate_port: 源端口（自动递增）
    :param rst: 是否使用RST关闭连接
    :param reuse: 是否允许地址重用
    :param count: 执行次数
    :param delay_close_second: 延迟关闭时间
    """
    error_flag = False
    if src_rotate_port:
        src_port = src_rotate_port

    while judge_count(count):
        conn_time, close_time, err, local_addr = conn_tcp(dst_host, dst_port, timeout=timeout, src_host=src_host,
                                                          src_port=src_port, rst=rst, reuse=reuse,
                                                          delay_close_second=delay_close_second)
        result.put(conn_time, not bool(err))
        
        # 初始化存放输出信息的列表
        output = []
        if local_addr:
            output.append(f'{local_addr[0]}:{local_addr[1]}')
        output.append(f'{dst_host}:{dst_port}')
        if conn_time >= 0:
            output.append(f'conn_time: {conn_time:.6f}')
        if len(str(err)) > 0:
            error_flag = True
            output.append(f'ERROR: {err}')

        final_output = ', '.join(output)
        mylogger.error(final_output) if error_flag else mylogger.info(final_output)

        # 清除错误标志，执行本次循环的收尾工作
        error_flag = False

        # 检查是否需要源端口自增
        if src_rotate_port:
            src_port += 1
            if src_port >= 65536:
                mylogger.warning('Local port reached 65535, resetting src port to 1024.')
                src_port = 1024

        # 若有 count，自减1
        if count is not None:
            count -= 1

        # 连接间隔
        time.sleep(interval)

def initial(arguments):
    """
    初始化信号处理器
    :param arguments: 命令行参数
    """
    signal.signal(signal.SIGINT, my_exit)
    signal.signal(signal.SIGTERM, my_exit)

def get_version():
    """返回脚本版本"""
    return __VERSION__

def getargs():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description=f'A tiny tool to connect target using TCP Connection. Version: {__VERSION__}')

    # 本地IP地址
    parser.add_argument('-H', '--src-host', dest='src_host', help='Set local IP', type=str)
    # 本地源端口
    parser.add_argument('-P', '--src-port', dest='src_port', help="Set local port", type=int, default=0)
    # 本地源端口，自增的进行连接，一般用来地毯式的查找本地有问题的源端口
    parser.add_argument('-L', '--src-rotate-port', dest='src_rotate_port', help="Set local port(rotate)", type=int)
    # 连接间隔
    parser.add_argument('-i', '--interval', dest='interval', help="Set connection interval(second),default==1",
                        type=float, default=1)
    # 连接超时时间
    parser.add_argument('-t', '--timeout', dest='timeout', help="Set timeout(second),default==2", type=float, default=2)
    # 总的连接次数
    parser.add_argument('-c', '--count', dest='count', help="Stop after sending count packets", type=int)
    # 是否以RESET断开连接，可以加快两端的系统回收连接
    parser.add_argument('-R', '--rst', dest='rst', action='store_true',
                        help="Sending reset to close connection instead of FIN")
    # 设置 SO_REUSEADDR 选项，允许地址和端口重用
    # 这在进行快速、重复的连接测试时特别有用，可以避免 "Address already in use" 错误
    # 允许在 TIME_WAIT 状态下重用地址和端口，适合高频率测试场景
    parser.add_argument('--reuse', dest='reuse', action='store_true',
                        help='Set SO_REUSEADDR flag so client can reuse address and port. '
                             'Useful for rapid, repeated tests to avoid "Address already in use" errors.')
    # 是否需要输出log日志
    parser.add_argument('-l', '--log', dest='log', action='store_true',
                        help="Set to write log file to disk")
    # 是否需要延迟关闭已建立的连接，用来排查三次握手最后一个ACK丢包的场景
    parser.add_argument('-D', '--delay-close', dest='delay_close_second',
                        help="Delay specified number of seconds before send FIN or RST", type=int, default=0)
    # 连接的目标主机
    parser.add_argument('dst_host', nargs=1, action='store', help='Target host or IP')
    # 连接的目标端口
    parser.add_argument('dst_port', nargs=1, action="store", type=int, help='Target port')

    return parser.parse_args()

def my_exit(signum, frame):
    """
    处理退出信号
    :param signum: 信号数
    :param frame: 当前帧
    """
    result_string = result.get_statistics()
    mylogger.info(result_string)
    exit()

class ResultBucket:
    """存储和计算TCP ping结果统计信息的类"""
    
    def __init__(self, dst_host, dst_port):
        self.dst_host = dst_host
        self.dst_port = dst_port
        self.is_initialled = False
        self.ok_count = 0
        self.error_count = 0
        self.min_time = 0.0
        self.max_time = 0.0
        self.avg_time = 0.0

    def put(self, conn_time, status):
        """
        添加新的结果到桶中
        :param conn_time: 连接时间
        :param status: 连接状态
        """
        if not status:
            self.error_count += 1
        else:
            if not self.is_initialled:
                self.min_time = self.max_time = self.avg_time = conn_time
                self.is_initialled = True
            else:
                self.min_time = min(self.min_time, conn_time)
                self.max_time = max(self.max_time, conn_time)
                self.avg_time = (self.avg_time * self.ok_count + conn_time) / (self.ok_count + 1)
            self.ok_count += 1

    def get_statistics(self):
        """返回格式化的统计信息字符串"""
        total_count = self.ok_count + self.error_count
        error_rate = self.error_count / total_count * 100 if total_count > 0 else 0
        return f"""--- {self.dst_host}:{self.dst_port} tcpping statistics ---
{total_count} connection(s) attempted, {self.ok_count} connected, {error_rate:.2f}% failed
min/avg/max = {self.min_time:.6f}/{self.avg_time:.6f}/{self.max_time:.6f} ms"""

if __name__ == '__main__':
    args = getargs()
    result = ResultBucket(args.dst_host[0], args.dst_port[0])

    # 设置输出的日志格式
    console_formatter = logging.Formatter('[%(asctime)s] %(message)s')
    file_formatter = logging.Formatter('%(levelname)s: [%(asctime)s] - %(filename)s[line:%(lineno)d] -  %(message)s')

    # 设置输出到屏幕的handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_formatter)

    # 创建logging
    mylogger = logging.getLogger('tcpping3')
    mylogger.setLevel(logging.INFO)
    mylogger.addHandler(console_handler)

    # 判断一下是否需要打log文件
    if args.log:
        # 设置输出到文件的handler
        file_handler = logging.handlers.RotatingFileHandler(
            f'tcpping3_{args.dst_host[0]}_{args.dst_port[0]}.log', mode='w',
            maxBytes=10 * 1024 * 1024, backupCount=5)
        file_handler.setFormatter(file_formatter)
        mylogger.addHandler(file_handler)

    initial(args)
    # 打印最开始的分隔行
    mylogger.info('=' * 50)
    if judge_args(args):
        give_tips(args)
        go(args.dst_host[0],
           args.dst_port[0],
           timeout=args.timeout,
           interval=args.interval,
           src_host=args.src_host,
           src_port=args.src_port,
           src_rotate_port=args.src_rotate_port,
           rst=args.rst,
           count=args.count,
           reuse=args.reuse,
           delay_close_second=args.delay_close_second)
        mylogger.info(result.get_statistics())
